#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🌿 Relax Manager – النسخة النهائية مع جميع التحسينات
================================================================================
بوت تلغرام متكامل لإدارة القنوات والمجموعات مع نظام دفع عبر Telegram Stars
مع تحسينات الردود التلقائية (كاش LRU، تحديث مجمع، تصدير/استيراد JSON)

الإصدار: 5.0.5-ultimate
================================================================================
"""

# =====================================================================
# 1. الاستيرادات الأساسية
# =====================================================================
import asyncio
import sys
import os
import secrets
import re
import shutil
import logging
import traceback
import random
import gc
import sqlite3
import json
import time
import tempfile
import hashlib
import html
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple, Any, Union, Callable, Awaitable
from enum import Enum, auto
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from collections import OrderedDict

# =====================================================================
# 2. تثبيت الحزم والاستيرادات الإضافية
# =====================================================================
def ensure_packages() -> None:
    required = [
        ("python-dotenv", "dotenv"),
        ("cachetools", "cachetools"),
        ("psutil", "psutil"),
        ("aiosqlite", "aiosqlite"),
        ("cryptography", "cryptography"),
        ("aiohttp", "aiohttp"),
        ("python-telegram-bot", "telegram"),
    ]
    for pkg, imp in required:
        try:
            __import__(imp)
        except ImportError:
            import subprocess
            result = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", pkg],
                                    capture_output=True, text=True, check=False)
            if result.returncode != 0:
                print(f"⚠️ فشل تثبيت {pkg}: {result.stderr}")

ensure_packages()

import aiosqlite
from dotenv import load_dotenv
load_dotenv()

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMember, BotCommand, LabeledPrice, ChatPermissions,
    ChatMemberUpdated, ChatJoinRequest, MessageEntity, Message
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler,
    ChatMemberHandler, ChatJoinRequestHandler
)
from telegram.error import TimedOut, NetworkError, BadRequest, Forbidden
from telegram.request import HTTPXRequest

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64
import aiohttp
from aiohttp import web
from cachetools import TTLCache

# =====================================================================
# 3. إعدادات التطبيق
# =====================================================================
@dataclass(frozen=True)
class AppConfig:
    TOKEN: str = os.getenv("BOT_TOKEN", "")
    PRIMARY_OWNER_ID: int = int(os.getenv("MAIN_ADMIN_ID", "0"))
    BOT_NAME: str = os.getenv("BOT_NAME", "ريلاكس مانيجر")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "Reelaaaxbot")
    USE_PROXY: bool = os.getenv("USE_PROXY", "false").lower() in ['true', '1']
    PROXY_URL: str = os.getenv("PROXY_URL", "http://127.0.0.1:10809")
    WEB_PORT: int = int(os.getenv("PORT", "10000"))
    MAX_CONNECTIONS: int = 20
    MAX_BACKUPS: int = 20
    ANONYMOUS_ADMIN_ID: int = 1087968824
    DEFAULT_PUBLISH_INTERVAL: int = 720
    MAX_CHANNELS_PER_CYCLE: int = 20
    PUBLISH_RETRY_DELAY: int = 300
    MAX_UNPUBLISHED_POSTS: int = 1000
    DB_TIMEOUT: int = 30
    MAX_DAILY_REFERRALS: int = 5
    MAX_GLOBAL_BANNED_WORDS: int = 100
    CACHE_TTL: int = 30
    XTR_CURRENCY: str = "XTR"
    HEARTBEAT_INTERVAL: int = 300
    ENABLE_SELF_PING: bool = os.getenv("ENABLE_SELF_PING", "true").lower() in ['true', '1']

    def validate(self) -> None:
        if not self.TOKEN or self.PRIMARY_OWNER_ID == 0:
            raise ValueError("BOT_TOKEN and MAIN_ADMIN_ID are required")

CONFIG = AppConfig()
CONFIG.validate()

# =====================================================================
# 4. إدارة المسارات والسجلات
# =====================================================================
class PathManager:
    _instance: Optional['PathManager'] = None

    def __new__(cls) -> 'PathManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_paths()
        return cls._instance

    def _init_paths(self) -> None:
        self.BASE = Path(__file__).parent.resolve()
        self.DATA = self.BASE / "data"
        self.BACKUPS = self.BASE / "backups"
        self.LOGS = self.BASE / "logs"
        self.DB = self.DATA / "bot_data.db"
        self.LOG_FILE = self.LOGS / "bot.log"
        for d in [self.DATA, self.BACKUPS, self.LOGS]:
            d.mkdir(parents=True, exist_ok=True)

PATHS = PathManager()

class SecureLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if CONFIG.TOKEN and CONFIG.TOKEN in msg:
            record.msg = msg.replace(CONFIG.TOKEN, "[TOKEN_HIDDEN]")
        return True

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(PATHS.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
for h in logger.handlers:
    h.addFilter(SecureLogFilter())

def log_error(error: Exception, context: Optional[Dict] = None) -> str:
    error_id = secrets.token_hex(4)
    logger.error(f"[{error_id}] {type(error).__name__}: {str(error)[:300]}")
    if context:
        logger.debug(f"Context: {context}")
    return error_id

# =====================================================================
# 5. أدوات مساعدة
# =====================================================================
class TimeUtils:
    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def mecca_now() -> datetime:
        return TimeUtils.utc_now() + timedelta(hours=3)

    @staticmethod
    def utc_iso() -> str:
        return TimeUtils.utc_now().isoformat()

    @staticmethod
    def mecca_iso() -> str:
        return TimeUtils.mecca_now().isoformat()

    @staticmethod
    def mecca_to_utc(dt: datetime) -> datetime:
        return dt - timedelta(hours=3) if dt else None

    @staticmethod
    def utc_to_mecca(dt: datetime) -> datetime:
        return dt + timedelta(hours=3) if dt else None

    @staticmethod
    def safe_parse_iso(date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            return None

class TextUtils:
    @staticmethod
    def contains_link(text: Optional[str]) -> bool:
        if not text:
            return False
        return bool(re.search(r'(?:https?://|www\.|t\.me/|telegram\.me/)\S+', text, re.IGNORECASE))

    @staticmethod
    def contains_mention(text: Optional[str]) -> bool:
        return bool(re.search(r'@\w+', text)) if text else False

    @staticmethod
    def sanitize(text: str, max_len: int = 4096) -> str:
        if not text:
            return ""
        text = re.sub(r'[\u200b\u200c\u200d\u2060\uFEFF]', '', text)
        return text[:max_len]

    @staticmethod
    def escape_markdown_v2(text: str) -> str:
        if not text:
            return ""
        special = r'_*[]()~`>#+\-=|{}.!\\\''
        return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\\'])', r'\\\1', text)

    @staticmethod
    def truncate(text: str, max_len: int = 200) -> str:
        return text[:max_len] + ("..." if len(text) > max_len else "")

class EncryptionManager:
    _instance: Optional['EncryptionManager'] = None

    def __new__(cls) -> 'EncryptionManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_cipher()
        return cls._instance

    def _init_cipher(self) -> None:
        env_key = os.getenv("DB_ENCRYPTION_KEY")
        if env_key:
            key = env_key.encode()
        else:
            key_file = PATHS.DATA / ".db_key"
            if key_file.exists():
                key = key_file.read_bytes()
            else:
                key = Fernet.generate_key()
                key_file.write_bytes(key)
                key_file.chmod(0o600)
        self._cipher = Fernet(key)

    def encrypt(self, data: bytes) -> bytes:
        return self._cipher.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._cipher.decrypt(data)

    def encrypt_text(self, text: str) -> bytes:
        return self.encrypt(text.encode('utf-8'))

    def decrypt_text(self, data: bytes) -> str:
        return self.decrypt(data).decode('utf-8')

ENCRYPT = EncryptionManager()

def get_ram_usage() -> dict:
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {'total': round(mem.total / (1024 ** 3), 1), 'used': round(mem.used / (1024 ** 3), 1),
                'percent': mem.percent}
    except:
        return {'total': 0, 'used': 0, 'percent': 0}

# =====================================================================
# 6. كاش LRU للردود التلقائية (تحسين جديد)
# =====================================================================
class AutoReplyCache:
    """ذاكرة تخزين مؤقت للردود الأكثر استخداماً (LRU)"""
    def __init__(self, maxsize: int = 200):
        self.cache = OrderedDict()
        self.maxsize = maxsize

    def get(self, key: str):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key: str, value: dict):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)

    def invalidate(self, key: str = None):
        if key:
            self.cache.pop(key, None)
        else:
            self.cache.clear()

    def size(self) -> int:
        return len(self.cache)

_auto_reply_cache = AutoReplyCache(maxsize=200)
_usage_updates: Dict[Tuple[int, str], int] = {}
_USAGE_FLUSH_LIMIT = 50
_USAGE_FLUSH_INTERVAL = 60

# =====================================================================
# 7. الترجمات
# =====================================================================
LOCALES = {
    'ar': {
        'main_menu': "🌿 **{bot_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 المعرف: `{user_id}`\n👥 مجموعاتي: {groups}\n💎 الاشتراك: {sub}\n📡 القناة: {channel}\n📝 غير المنشورة: {pending}\n⚙️ النشر: {auto}",
        'subscription_active': "✅ مفعل حتى {date}",
        'subscription_inactive': "❌ غير مفعل",
        'trial_activated': "✅ تم تفعيل {days} يوم تجريبي",
        'trial_used': "❌ استخدمت التجربة سابقاً",
        'payment_success': "✅ تم الدفع بنجاح، تم تفعيل {plan} لمدة {days} يوم",
        'payment_failed': "❌ فشل الدفع، يرجى المحاولة مرة أخرى",
        'help_text': "❓ **المساعدة**\n/start - القائمة الرئيسية\n/subscribe - الاشتراك\n/syncgroup - تفعيل المجموعة\n/security - الأمان\n/panel - لوحة التحكم\n/stats - الإحصائيات\n/contests - المسابقات\n/support - الدعم\n/trial - تجربة مجانية",
        'referral_claimed': "✅ تم إضافة {days} يوم",
        'no_referrals': "❌ لا يوجد إحالات",
        'channels_empty': "📭 لا توجد قنوات",
        'posts_empty': "📭 لا توجد منشورات",
        'groups_empty': "📭 لا توجد مجموعات",
        'no_groups': "📭 لا توجد مجموعات",
        'plan_selector': "💎 اختر الباقة المناسبة لك:",
        'subscribe_1_day': "💎 1 يوم - 5 نجوم",
        'subscribe_7_days': "💎 7 أيام - 25 نجوم",
        'subscribe_30_days': "💎 30 يوم - 75 نجوم",
        'subscribe_90_days': "💎 90 يوم - 200 نجوم",
        'referral_header': "🔗 رابطك: `{link}`\n👥 {total} | 🎁 {available} يوم",
        'referral_list': "📋 قائمة المُحالين:\n{list}",
        'security_header': "🔐 إعدادات الأمان",
        'settings_header': "⚙️ الإعدادات",
        'schedule_current': "⏰ الجدولة (الحالي: {type})",
        'schedule_updated': "✅ تم التحديث",
        'admin_panel': "👑 لوحة التحكم",
        'admin_stats': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'stats': "📊 الإحصائيات",
        'back': "🔙 رجوع",
        'close': "🔙 إغلاق",
        'add_channel': "➕ إضافة قناة",
        'my_channels': "📡 قنواتي",
        'add_posts': "📥 إضافة منشورات",
        'publish_one': "📤 نشر واحد",
        'my_posts': "📋 منشوراتي",
        'recycle': "♻️ إعادة تدوير",
        'publish_all': "📤 نشر الكل",
        'help': "❓ مساعدة",
        'trial': "🎁 تجربة",
        'subscribe': "💎 اشتراك",
        'developer': "👨‍💻 المطور",
        'language': "🌐 اللغة",
        'support': "📞 دعم",
        'referral': "🔗 إحالات",
        'reminder': "⏰ تذكيرات",
        'translation': "🌐 ترجمة",
        'contests': "🏆 مسابقات",
        'admin_panel_btn': "👑 لوحة الأدمن",
        'claim_reward': "🎁 صرف المكافأة",
        'reminder_header': "⏰ إعدادات التذكيرات",
        'send_support_message': "📞 أرسل رسالتك (نص أو صورة أو فيديو) وسنرد عليك",
        'support_ticket_created': "✅ تم إنشاء تذكرة #{num}",
        'not_authorized': "🔒 غير مصرح",
        'invalid_channel': "❌ ليس قناة",
        'bot_not_admin': "❌ البوت ليس مشرفاً أو لا يملك صلاحية النشر",
        'channel_exists': "⚠️ القناة موجودة مسبقاً",
        'channel_added': "✅ تمت الإضافة",
        'invalid_format': "❌ صيغة خاطئة",
        'enter_minutes': "⏱️ أرسل عدد الدقائق (1-1440):",
        'enter_hours': "⏱️ أرسل عدد الساعات (1-168):",
        'enter_days': "⏱️ أرسل عدد الأيام (1-365):",
        'enter_publish_time': "🕐 أرسل وقت النشر (مثال: 14:30)",
        'schedule_updated_ok': "✅ تم تحديث الجدولة",
        'enter_channel_id': "📡 أرسل معرف القناة (@username أو -100...)",
        'enter_posts': "📥 أرسل {count} منشور (نص، صورة، فيديو، مستند، صوت، صوتي، متحرك)",
        'subscription_expired': "⚠️ اشتراكك منتهٍ، يرجى التجديد",
        'no_active_channel': "⚠️ اختر قناة أولاً",
        'max_posts_reached': "⚠️ وصلت للحد الأقصى من المنشورات",
        'post_saved': "✅ {saved}/{target} | متبقي {remaining}",
        'all_posts_saved': "✅ تم حفظ جميع المنشورات",
        'publish_success': "✅ تم النشر",
        'publish_fail': "❌ فشل النشر: {error}",
        'no_posts': "📭 لا توجد منشورات",
        'my_posts_title': "📋 **منشوراتي**",
        'no_channels': "📭 لا توجد قنوات",
        'groups_list': "👥 **مجموعاتي**",
        'add_group': "➕ أضف المجموعة",
        'settings_auto': "⚙️ نشر تلقائي: {status}",
        'security_text': "🔐 <b>إعدادات الأمان للمجموعة</b>\n━━━━━━━━━━━━━━━━━━━━\n🔗 الروابط: {links}\n@ المعرفات: {mentions}\n⏱️ البطيء: {slow} ({slow_sec}ث)\n🎯 الترحيب: {welcome}\n👋 الوداع: {goodbye}\n🎬 فيديوهات: {video}\n🎵 صوتيات: {audio}\n🎞️ متحركات: {animation}\n🛠️ الخدمة: {service}\n📄 ملفات: {documents}\n🖼️ ملصقات: {stickers}\n📨 المُعاد: {forwarded}\n📊 استطلاعات: {polls}\n🎮 ألعاب: {games}\n🎤 صوتيات: {voice}\n🎥 فيديو نوت: {video_note}\n🌊 مضاد الفيضان: {flood}\n🌙 ليلي: {night}\n📏 الطول: {max_len}\n⚖️ العقوبة الأساسية: {auto_penalty}\n⚖️ عقوبة الحذف: {delete_penalty}\n━━━━━━━━━━━━━━━━━━━━\n📌 اختر الإعداد:",
        'warning_settings': "⚠️ **إعدادات التحذير**\nالحد الأقصى للتحذيرات: {max_warnings}\nعقوبة التجاوز: {warn_penalty}",
        'warning_count_updated': "✅ تم تعيين {count} تحذيرات كحد أقصى",
        'warning_penalty_updated': "✅ تم تعيين عقوبة التجاوز: {penalty}",
        'word_added': "✅ تمت إضافة '{word}'",
        'word_exists': "⚠️ الكلمة '{word}' موجودة مسبقاً",
        'word_removed': "✅ تم حذف '{word}'",
        'word_too_short': "❌ الكلمة قصيرة جداً (يجب أن تكون حرفين على الأقل)",
        'enter_word': "✏️ أرسل الكلمة:",
        'enter_word_to_remove': "✏️ أرسل الكلمة للحذف:",
        'banned_words_list': "🚫 **الكلمات المحظورة**\n{words}",
        'no_banned_words': "📭 لا توجد كلمات محظورة",
        'no_tickets': "📭 لا توجد تذاكر",
        'tickets_list': "📋 التذاكر:\n{tickets}",
        'tickets_deleted': "✅ تم حذف جميع التذاكر",
        'confirm_delete_tickets': "⚠️ هل أنت متأكد من حذف جميع التذاكر؟",
        'auto_reply_settings': "📝 إعدادات الردود التلقائية",
        'auto_reply_enabled': "🟢 مفعل",
        'auto_reply_disabled': "🔴 معطل",
        'auto_reply_users': "👥 المستخدمون: {mode}",
        'auto_reply_mode_all': "الجميع",
        'auto_reply_mode_admins': "المشرفين فقط",
        'auto_reply_stats': "📊 **أكثر الردود استخداماً**\n{stats}",
        'no_auto_reply_stats': "📊 لا توجد إحصائيات",
        'auto_reply_list': "📋 **قائمة الردود التلقائية**\n{replies}",
        'no_auto_replies': "📭 لا توجد ردود",
        'enter_keyword': "✏️ أرسل الكلمة المفتاحية للرد:",
        'enter_reply': "✏️ أرسل الرد:",
        'enter_keyword_to_delete': "✏️ أرسل الكلمة المفتاحية لحذف الرد:",
        'auto_reply_added': "✅ تم إضافة رد لـ '{keyword}'",
        'auto_reply_deleted': "✅ تم حذف الرد لـ '{keyword}'",
        'auto_reply_not_found': "❌ لا يوجد رد لـ '{keyword}'",
        'referral_link_copied': "🔗 رابط الإحالة: {link}",
        'referral_stats': "👥 الإحالات: {total}\n🎁 المكافآت المتاحة: {available} يوم",
        'reminder_settings_updated': "✅ تم تحديث إعدادات التذكيرات",
        'reminder_days_updated': "✅ تم تعيين {days} أيام",
        'translation_off': "✅ تم إيقاف الترجمة",
        'translation_set': "✅ تم تفعيل الترجمة إلى {lang}",
        'contest_created': "✅ تم إنشاء المسابقة #{id}",
        'contest_joined': "✅ تمت المشاركة في المسابقة",
        'contest_no_active': "🏆 لا توجد مسابقات نشطة",
        'contest_winners': "🏆 **الفائزون السابقون**\n{winners}",
        'no_contest_winners': "🏆 لا يوجد فائزون بعد",
        'admin_actions': "👑 **لوحة الأدمن**",
        'admin_users': "👥 المستخدمين: {users}\n🚫 محظورين: {banned}",
        'admin_banned_list': "🚫 المحظورين:\n{list}",
        'admin_unbanned_all': "✅ تم إلغاء حظر الكل",
        'admin_channels_list': "📡 القنوات:\n{list}",
        'admin_banned_channels': "🚫 القنوات المحظورة:\n{list}",
        'admin_activated_channels': "✅ تم تفعيل جميع القنوات",
        'admin_groups_list': "👥 المجموعات:\n{list}",
        'admin_banned_groups': "🚫 المجموعات المحظورة:\n{list}",
        'admin_unbanned_groups': "✅ تم إلغاء حظر جميع المجموعات",
        'admin_add_admin': "👑 أرسل معرف المشرف:",
        'admin_rem_admin': "🗑️ أرسل معرف المشرف:",
        'admin_added': "✅ تمت إضافة {user} كمشرف",
        'admin_removed': "✅ تمت إزالة {user} من المشرفين",
        'admin_ram': "💾 {used}/{total} GB ({percent}%)",
        'admin_stats_text': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'admin_metrics': "📊 **المقاييس**\n👥 المستخدمون النشطون: {active}\n📝 منشورات اليوم: {today}\n💾 حجم DB: {db_size:.2f} MB",
        'admin_backup_created': "✅ تم إنشاء نسخة احتياطية: {filename}",
        'admin_backup_failed': "❌ فشل النسخ الاحتياطي: {error}",
        'admin_restore_choose': "اختر النسخة الاحتياطية:",
        'admin_restore_success': "✅ تمت الاستعادة بنجاح",
        'admin_restore_failed': "❌ فشل الاستعادة: {error}",
        'admin_update_sent': "📢 تم إرسال التحديث",
        'admin_update_failed': "❌ فشل إرسال التحديث",
        'admin_force_sub_off': "🔒 الاشتراك الإجباري غير مفعل",
        'admin_force_sub_on': "🔒 الاشتراك الإجباري مفعل على @{channel}",
        'admin_force_sub_set': "✅ تم تعيين قناة الاشتراك الإجباري: @{channel}",
        'admin_broadcast_sent': "✅ تم الإرسال لـ {sent} مستخدم",
        'admin_broadcast_confirm': "📨 تأكيد الإرسال:\n{text}",
        'admin_log_channel_set': "✅ تم تعيين قناة السجلات: {channel}",
        'admin_log_channel_not_channel': "❌ ليس قناة",
        'admin_log_channel_failed': "❌ فشل تعيين قناة السجلات",
        'admin_banned_words_global': "🚫 الكلمات المحظورة عالمياً:\n{words}",
        'admin_contest_created': "✅ تم إنشاء المسابقة",
        'admin_contest_declared': "🏆 الفائز في المسابقة '{title}': `{winner}`",
        'admin_contest_no_participants': "لا يوجد مشاركون في هذه المسابقة",
        'admin_contest_deleted': "✅ تم حذف المسابقة",
        'invoice_list': "🧾 **فواتيري**\n{invoices}",
        'no_invoices': "📭 لا توجد فواتير",
        'payment_failed_generic': "❌ فشل الدفع، يرجى المحاولة مرة أخرى",
        'plan_not_found': "❌ الباقة غير متوفرة",
        'payment_init_failed': "❌ فشل إنشاء الدفع",
        'buy_plan': "شراء {plan}",
        'plan_description': "{description} - {price} نجوم",
        'invoice_number': "رقم الفاتورة: {number}",
        'heartbeat_status': "💓 نبض البوت - {time} - الرام: {ram}%",
        'days': "يوم",
        'no_backups': "📭 لا توجد نسخ احتياطية",
        'file_not_found': "❌ الملف غير موجود",
        'no_active_contests': "📭 لا توجد مسابقات نشطة",
        'contest_not_found': "❌ المسابقة غير موجودة",
        'reminder_subscription_expires': "⏰ تذكير: اشتراكك ينتهي خلال {days} يوم",
    },
    'en': {
        'main_menu': "🌿 **{bot_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 ID: `{user_id}`\n👥 Groups: {groups}\n💎 Subscription: {sub}\n📡 Channel: {channel}\n📝 Unpublished: {pending}\n⚙️ Auto: {auto}",
        'subscription_active': "✅ Active until {date}",
        'subscription_inactive': "❌ Inactive",
        'trial_activated': "✅ {days} days trial activated",
        'trial_used': "❌ Trial already used",
        'payment_success': "✅ Payment successful, {plan} activated for {days} days",
        'payment_failed': "❌ Payment failed, please try again",
        'help_text': "❓ **Help**\n/start - Main menu\n/subscribe - Subscribe\n/syncgroup - Activate group\n/security - Security\n/panel - Panel\n/stats - Stats\n/contests - Contests\n/support - Support\n/trial - Free trial",
        'referral_claimed': "✅ Added {days} days",
        'no_referrals': "❌ No referrals",
        'channels_empty': "📭 No channels",
        'posts_empty': "📭 No posts",
        'groups_empty': "📭 No groups",
        'no_groups': "📭 No groups",
        'plan_selector': "💎 Choose your plan:",
        'subscribe_1_day': "💎 1 Day - 5 Stars",
        'subscribe_7_days': "💎 7 Days - 25 Stars",
        'subscribe_30_days': "💎 30 Days - 75 Stars",
        'subscribe_90_days': "💎 90 Days - 200 Stars",
        'referral_header': "🔗 Your link: `{link}`\n👥 {total} | 🎁 {available} days",
        'referral_list': "📋 Referrals:\n{list}",
        'security_header': "🔐 Security Settings",
        'settings_header': "⚙️ Settings",
        'schedule_current': "⏰ Schedule (current: {type})",
        'schedule_updated': "✅ Updated",
        'admin_panel': "👑 Admin Panel",
        'admin_stats': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'stats': "📊 Stats",
        'back': "🔙 Back",
        'close': "🔙 Close",
        'add_channel': "➕ Add Channel",
        'my_channels': "📡 My Channels",
        'add_posts': "📥 Add Posts",
        'publish_one': "📤 Publish One",
        'my_posts': "📋 My Posts",
        'recycle': "♻️ Recycle",
        'publish_all': "📤 Publish All",
        'help': "❓ Help",
        'trial': "🎁 Trial",
        'subscribe': "💎 Subscribe",
        'developer': "👨‍💻 Developer",
        'language': "🌐 Language",
        'support': "📞 Support",
        'referral': "🔗 Referrals",
        'reminder': "⏰ Reminders",
        'translation': "🌐 Translation",
        'contests': "🏆 Contests",
        'admin_panel_btn': "👑 Admin Panel",
        'claim_reward': "🎁 Claim Reward",
        'reminder_header': "⏰ Reminder Settings",
        'send_support_message': "📞 Send your message (text, photo, video, etc.) and we'll reply",
        'support_ticket_created': "✅ Ticket #{num} created",
        'not_authorized': "🔒 Not authorized",
        'invalid_channel': "❌ Not a channel",
        'bot_not_admin': "❌ Bot is not an admin or cannot post",
        'channel_exists': "⚠️ Channel already exists",
        'channel_added': "✅ Added",
        'invalid_format': "❌ Invalid format",
        'enter_minutes': "⏱️ Enter minutes (1-1440):",
        'enter_hours': "⏱️ Enter hours (1-168):",
        'enter_days': "⏱️ Enter days (1-365):",
        'enter_publish_time': "🕐 Enter publish time (e.g., 14:30)",
        'schedule_updated_ok': "✅ Schedule updated",
        'enter_channel_id': "📡 Send channel ID (@username or -100...)",
        'enter_posts': "📥 Send {count} posts (text, photo, video, document, audio, voice, animation)",
        'subscription_expired': "⚠️ Subscription expired, please renew",
        'no_active_channel': "⚠️ Select a channel first",
        'max_posts_reached': "⚠️ Maximum posts reached",
        'post_saved': "✅ {saved}/{target} | Remaining {remaining}",
        'all_posts_saved': "✅ All posts saved",
        'publish_success': "✅ Published",
        'publish_fail': "❌ Publish failed: {error}",
        'no_posts': "📭 No posts",
        'my_posts_title': "📋 **My Posts**",
        'no_channels': "📭 No channels",
        'groups_list': "👥 **My Groups**",
        'add_group': "➕ Add Group",
        'settings_auto': "⚙️ Auto publish: {status}",
        'security_text': "🔐 <b>Security Settings</b>\n━━━━━━━━━━━━━━━━━━━━\n🔗 Links: {links}\n@ Mentions: {mentions}\n⏱️ Slow mode: {slow} ({slow_sec}s)\n🎯 Welcome: {welcome}\n👋 Goodbye: {goodbye}\n🎬 Videos: {video}\n🎵 Audio: {audio}\n🎞️ Animation: {animation}\n🛠️ Service: {service}\n📄 Documents: {documents}\n🖼️ Stickers: {stickers}\n📨 Forwarded: {forwarded}\n📊 Polls: {polls}\n🎮 Games: {games}\n🎤 Voice: {voice}\n🎥 Video note: {video_note}\n🌊 Antiflood: {flood}\n🌙 Night mode: {night}\n📏 Max length: {max_len}\n⚖️ Default penalty: {auto_penalty}\n⚖️ Delete penalty: {delete_penalty}\n━━━━━━━━━━━━━━━━━━━━\n📌 Choose setting:",
        'warning_settings': "⚠️ **Warning Settings**\nMax warnings: {max_warnings}\nPenalty: {warn_penalty}",
        'warning_count_updated': "✅ Max warnings set to {count}",
        'warning_penalty_updated': "✅ Penalty set to {penalty}",
        'word_added': "✅ Added '{word}'",
        'word_exists': "⚠️ '{word}' already exists",
        'word_removed': "✅ Removed '{word}'",
        'word_too_short': "❌ Word too short (min 2 characters)",
        'enter_word': "✏️ Send the word:",
        'enter_word_to_remove': "✏️ Send the word to remove:",
        'banned_words_list': "🚫 **Banned Words**\n{words}",
        'no_banned_words': "📭 No banned words",
        'no_tickets': "📭 No tickets",
        'tickets_list': "📋 Tickets:\n{tickets}",
        'tickets_deleted': "✅ All tickets deleted",
        'confirm_delete_tickets': "⚠️ Are you sure you want to delete all tickets?",
        'auto_reply_settings': "📝 Auto-reply settings",
        'auto_reply_enabled': "🟢 Enabled",
        'auto_reply_disabled': "🔴 Disabled",
        'auto_reply_users': "👥 Users: {mode}",
        'auto_reply_mode_all': "Everyone",
        'auto_reply_mode_admins': "Admins only",
        'auto_reply_stats': "📊 **Most used replies**\n{stats}",
        'no_auto_reply_stats': "📊 No statistics",
        'auto_reply_list': "📋 **Auto-replies**\n{replies}",
        'no_auto_replies': "📭 No replies",
        'enter_keyword': "✏️ Send the keyword:",
        'enter_reply': "✏️ Send the reply:",
        'enter_keyword_to_delete': "✏️ Send the keyword to delete:",
        'auto_reply_added': "✅ Added reply for '{keyword}'",
        'auto_reply_deleted': "✅ Deleted reply for '{keyword}'",
        'auto_reply_not_found': "❌ No reply found for '{keyword}'",
        'referral_link_copied': "🔗 Referral link: {link}",
        'referral_stats': "👥 Referrals: {total}\n🎁 Available reward: {available} days",
        'reminder_settings_updated': "✅ Reminder settings updated",
        'reminder_days_updated': "✅ Set {days} days",
        'translation_off': "✅ Translation turned off",
        'translation_set': "✅ Translation set to {lang}",
        'contest_created': "✅ Contest #{id} created",
        'contest_joined': "✅ Joined contest",
        'contest_no_active': "🏆 No active contests",
        'contest_winners': "🏆 **Previous Winners**\n{winners}",
        'no_contest_winners': "🏆 No winners yet",
        'admin_actions': "👑 **Admin Panel**",
        'admin_users': "👥 Users: {users}\n🚫 Banned: {banned}",
        'admin_banned_list': "🚫 Banned users:\n{list}",
        'admin_unbanned_all': "✅ All unbanned",
        'admin_channels_list': "📡 Channels:\n{list}",
        'admin_banned_channels': "🚫 Banned channels:\n{list}",
        'admin_activated_channels': "✅ All channels activated",
        'admin_groups_list': "👥 Groups:\n{list}",
        'admin_banned_groups': "🚫 Banned groups:\n{list}",
        'admin_unbanned_groups': "✅ All groups unbanned",
        'admin_add_admin': "👑 Send the admin ID:",
        'admin_rem_admin': "🗑️ Send the admin ID:",
        'admin_added': "✅ Added {user} as admin",
        'admin_removed': "✅ Removed {user} from admins",
        'admin_ram': "💾 {used}/{total} GB ({percent}%)",
        'admin_stats_text': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'admin_metrics': "📊 **Metrics**\n👥 Active users: {active}\n📝 Today's posts: {today}\n💾 DB size: {db_size:.2f} MB",
        'admin_backup_created': "✅ Backup created: {filename}",
        'admin_backup_failed': "❌ Backup failed: {error}",
        'admin_restore_choose': "Choose backup:",
        'admin_restore_success': "✅ Restore successful",
        'admin_restore_failed': "❌ Restore failed: {error}",
        'admin_update_sent': "📢 Update sent",
        'admin_update_failed': "❌ Failed to send update",
        'admin_force_sub_off': "🔒 Force subscribe is off",
        'admin_force_sub_on': "🔒 Force subscribe is on for @{channel}",
        'admin_force_sub_set': "✅ Force subscribe channel set: @{channel}",
        'admin_broadcast_sent': "✅ Sent to {sent} users",
        'admin_broadcast_confirm': "📨 Confirm broadcast:\n{text}",
        'admin_log_channel_set': "✅ Log channel set: {channel}",
        'admin_log_channel_not_channel': "❌ Not a channel",
        'admin_log_channel_failed': "❌ Failed to set log channel",
        'admin_banned_words_global': "🚫 Global banned words:\n{words}",
        'admin_contest_created': "✅ Contest created",
        'admin_contest_declared': "🏆 Winner of '{title}': `{winner}`",
        'admin_contest_no_participants': "No participants in this contest",
        'admin_contest_deleted': "✅ Contest deleted",
        'invoice_list': "🧾 **My Invoices**\n{invoices}",
        'no_invoices': "📭 No invoices",
        'payment_failed_generic': "❌ Payment failed, please try again",
        'plan_not_found': "❌ Plan not available",
        'payment_init_failed': "❌ Failed to initiate payment",
        'buy_plan': "Buy {plan}",
        'plan_description': "{description} - {price} stars",
        'invoice_number': "Invoice: {number}",
        'heartbeat_status': "💓 Heartbeat - {time} - RAM: {ram}%",
        'days': "days",
        'no_backups': "📭 No backups",
        'file_not_found': "❌ File not found",
        'no_active_contests': "📭 No active contests",
        'contest_not_found': "❌ Contest not found",
        'reminder_subscription_expires': "⏰ Reminder: Your subscription expires in {days} days",
    }
}

def get_text(lang: str, key: str, **kwargs) -> str:
    if lang not in LOCALES:
        lang = 'ar'
    text = LOCALES[lang].get(key, key)
    try:
        return text.format(**kwargs)
    except KeyError:
        return text

# =====================================================================
# 8. قاعدة البيانات (مع اتصال لكل استعلام)
# =====================================================================
class Database:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls) -> 'Database':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @asynccontextmanager
    async def _get_connection(self):
        async with aiosqlite.connect(
            str(PATHS.DB),
            timeout=CONFIG.DB_TIMEOUT,
            check_same_thread=False
        ) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            yield conn

    async def execute(self, query: str, params: tuple = ()) -> None:
        async with self._get_connection() as conn:
            await conn.execute(query, params)
            await conn.commit()

    async def fetchone(self, query: str, params: tuple = ()):
        async with self._get_connection() as conn:
            async with conn.execute(query, params) as cur:
                return await cur.fetchone()

    async def fetchall(self, query: str, params: tuple = ()):
        async with self._get_connection() as conn:
            async with conn.execute(query, params) as cur:
                return await cur.fetchall()

    async def executemany(self, query: str, params: list) -> None:
        async with self._get_connection() as conn:
            await conn.executemany(query, params)
            await conn.commit()

    async def initialize(self) -> None:
        async with self._get_connection() as conn:
            await self._create_tables(conn)
            await self._create_indexes(conn)
            await self._init_default_data(conn)

    async def _create_tables(self, conn) -> None:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                language TEXT DEFAULT 'ar',
                auto_publish INTEGER DEFAULT 1,
                auto_recycle INTEGER DEFAULT 1,
                banned INTEGER DEFAULT 0,
                trial_used INTEGER DEFAULT 0,
                subscription_end TEXT,
                referral_code TEXT UNIQUE,
                created_at TEXT,
                updated_at TEXT,
                active_channel INTEGER
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id TEXT,
                channel_name TEXT,
                banned INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_db_id INTEGER,
                text TEXT,
                media_type TEXT,
                media_file_id TEXT,
                published INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                created_at TEXT,
                published_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schedule (
                channel_db_id INTEGER PRIMARY KEY,
                schedule_type TEXT DEFAULT 'interval_minutes',
                interval_minutes INTEGER DEFAULT 12,
                interval_hours INTEGER DEFAULT 0,
                interval_days INTEGER DEFAULT 0,
                days_of_week TEXT DEFAULT '[]',
                specific_dates TEXT DEFAULT '[]',
                publish_time TEXT DEFAULT '00:00',
                cron_expression TEXT,
                next_publish_date TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS last_publish (
                channel_db_id INTEGER PRIMARY KEY,
                last_publish_time TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_groups (
                chat_id INTEGER PRIMARY KEY,
                chat_name TEXT,
                username TEXT,
                added_by INTEGER,
                added_at TEXT,
                updated_at TEXT,
                banned INTEGER DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_admins (
                chat_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_owner_groups (
                chat_id INTEGER,
                owner_id INTEGER,
                is_hidden INTEGER DEFAULT 1,
                PRIMARY KEY (chat_id, owner_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_admins (
                chat_id INTEGER,
                admin_id INTEGER,
                added_by INTEGER,
                added_at TEXT,
                PRIMARY KEY (chat_id, admin_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_security (
                chat_id INTEGER PRIMARY KEY,
                delete_links INTEGER DEFAULT 0,
                mentions INTEGER DEFAULT 0,
                slow_mode INTEGER DEFAULT 0,
                slow_mode_seconds INTEGER DEFAULT 5,
                welcome_enabled INTEGER DEFAULT 0,
                welcome_text TEXT DEFAULT 'مرحباً {user} في {chat} 🤍',
                goodbye_enabled INTEGER DEFAULT 0,
                goodbye_text TEXT DEFAULT 'وداعاً {user} 👋',
                delete_banned_words INTEGER DEFAULT 0,
                auto_penalty TEXT DEFAULT 'none',
                auto_mute_duration INTEGER DEFAULT 60,
                delete_videos INTEGER DEFAULT 0,
                delete_audio INTEGER DEFAULT 0,
                delete_animation INTEGER DEFAULT 0,
                delete_service INTEGER DEFAULT 0,
                delete_documents INTEGER DEFAULT 0,
                delete_stickers INTEGER DEFAULT 0,
                delete_forwarded INTEGER DEFAULT 0,
                delete_polls INTEGER DEFAULT 0,
                delete_games INTEGER DEFAULT 0,
                delete_voice INTEGER DEFAULT 0,
                delete_video_note INTEGER DEFAULT 0,
                delete_penalty TEXT DEFAULT 'none',
                delete_penalty_duration INTEGER DEFAULT 0,
                antiflood_enabled INTEGER DEFAULT 0,
                antiflood_messages INTEGER DEFAULT 5,
                antiflood_seconds INTEGER DEFAULT 10,
                antiflood_penalty TEXT DEFAULT 'mute',
                max_warnings INTEGER DEFAULT 3,
                warn_penalty TEXT DEFAULT 'ban',
                max_message_length INTEGER DEFAULT 0,
                night_mode_enabled INTEGER DEFAULT 0,
                night_mode_start TEXT DEFAULT '23:00',
                night_mode_end TEXT DEFAULT '06:00',
                night_mode_action TEXT DEFAULT 'mute',
                nsfw_enabled INTEGER DEFAULT 0,
                nsfw_threshold REAL DEFAULT 0.7
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_locks (
                chat_id INTEGER PRIMARY KEY,
                locked INTEGER DEFAULT 0,
                locked_at TEXT,
                locked_by INTEGER
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS banned_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT,
                chat_id INTEGER,
                added_by INTEGER,
                added_at TEXT,
                UNIQUE(word, chat_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_replies (
                chat_id INTEGER,
                keyword TEXT,
                reply TEXT,
                reply_type TEXT DEFAULT 'text',
                reply_media_id TEXT,
                reply_buttons TEXT,
                created_at TEXT,
                is_active INTEGER DEFAULT 1,
                usage_count INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, keyword)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_reply_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                only_admins INTEGER DEFAULT 0,
                ignore_bots INTEGER DEFAULT 1,
                updated_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                message TEXT,
                media_type TEXT,
                media_file_id TEXT,
                ticket_number INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                replied INTEGER DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('publish_interval', '720')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_backup', '1')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_ticket_number', '0')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_backup', '')")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                created_at TEXT,
                UNIQUE(referrer_id, referred_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_rewards (
                user_id INTEGER PRIMARY KEY,
                referral_count INTEGER DEFAULT 0,
                total_reward_days INTEGER DEFAULT 0,
                claimed_reward_days INTEGER DEFAULT 0,
                last_referral_date TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_reminder_settings (
                user_id INTEGER PRIMARY KEY,
                subscription_reminder INTEGER DEFAULT 1,
                daily_stats_reminder INTEGER DEFAULT 0,
                weekly_report INTEGER DEFAULT 1,
                reminder_days_before INTEGER DEFAULT 3,
                last_reminder_sent TEXT,
                notification_lang TEXT DEFAULT 'ar'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_translation (
                user_id INTEGER PRIMARY KEY,
                lang TEXT DEFAULT 'off'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER,
                title TEXT,
                description TEXT,
                prize TEXT,
                end_date TEXT,
                status TEXT DEFAULT 'active',
                winner_id INTEGER,
                created_at TEXT,
                contest_type TEXT DEFAULT 'raffle'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contest_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                contest_id INTEGER,
                answer TEXT,
                joined_at TEXT,
                UNIQUE(user_id, contest_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contest_winners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER,
                winner_id INTEGER,
                announced_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                admin_id INTEGER,
                action TEXT,
                target_id INTEGER,
                reason TEXT,
                created_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_warnings (
                user_id INTEGER,
                chat_id INTEGER,
                warnings INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_rules (
                chat_id INTEGER PRIMARY KEY,
                rules_text TEXT,
                updated_by INTEGER,
                updated_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_messages (
                user_id INTEGER,
                chat_id INTEGER,
                message_time TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                text TEXT,
                publish_time TEXT,
                fail_count INTEGER DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                text_encrypted BLOB,
                sentiment TEXT,
                score REAL,
                created_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                price INTEGER,
                currency TEXT DEFAULT 'XTR',
                duration_days INTEGER,
                max_channels INTEGER,
                max_posts INTEGER,
                features TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                plan_id INTEGER,
                status TEXT DEFAULT 'active',
                start_date TEXT,
                end_date TEXT,
                auto_renew INTEGER DEFAULT 0,
                provider TEXT DEFAULT 'xtr',
                provider_subscription_id TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT UNIQUE,
                user_id INTEGER,
                plan_id INTEGER,
                amount INTEGER,
                currency TEXT DEFAULT 'XTR',
                status TEXT DEFAULT 'pending',
                provider TEXT DEFAULT 'xtr',
                provider_payment_id TEXT,
                paid_at TEXT,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payment_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                provider TEXT DEFAULT 'xtr',
                event_type TEXT,
                data TEXT,
                created_at TEXT
            )
        """)
        await conn.commit()

    async def _create_indexes(self, conn) -> None:
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_uc_user ON user_channels(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sched_next ON schedule(next_publish_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bw_word ON banned_words(word)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_status ON subscriptions(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_user ON invoices(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_status ON invoices(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ar_chat ON auto_replies(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ar_keyword ON auto_replies(keyword)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_auto_replies_lookup ON auto_replies(chat_id, keyword, is_active)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_user ON support_tickets(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status)")
        await conn.commit()

    async def _init_default_data(self, conn) -> None:
        default_plans = [
            {"name": "يوم", "description": "باقة يوم واحد", "price": 5, "duration_days": 1, "max_channels": 1, "max_posts": 50, "features": '{"auto_publish":true}'},
            {"name": "أسبوع", "description": "باقة 7 أيام", "price": 25, "duration_days": 7, "max_channels": 3, "max_posts": 300, "features": '{"auto_publish":true,"security":true}'},
            {"name": "شهر", "description": "باقة 30 يوم", "price": 75, "duration_days": 30, "max_channels": 10, "max_posts": 1500, "features": '{"auto_publish":true,"security":true,"support":true}'},
            {"name": "3 أشهر", "description": "باقة 90 يوم", "price": 200, "duration_days": 90, "max_channels": 999, "max_posts": 99999, "features": '{"auto_publish":true,"security":true,"support":true,"analytics":true}'},
        ]
        for plan in default_plans:
            row = await conn.execute("SELECT id FROM plans WHERE name=?", (plan["name"],))
            if not await row.fetchone():
                await conn.execute(
                    "INSERT INTO plans (name, description, price, currency, duration_days, max_channels, max_posts, features, is_active, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (plan["name"], plan["description"], plan["price"], "XTR", plan["duration_days"], plan["max_channels"], plan["max_posts"], plan["features"], 1, TimeUtils.utc_iso())
                )
        await conn.commit()

DB = Database()

# =====================================================================
# 9. المستودعات (Repositories)
# =====================================================================
class UserRepository:
    @staticmethod
    async def register(user_id: int) -> bool:
        row = await DB.fetchone("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if row:
            await DB.execute("UPDATE users SET updated_at=? WHERE user_id=?", (TimeUtils.utc_iso(), user_id))
            return False
        code = secrets.token_urlsafe(6)
        await DB.execute("INSERT INTO users (user_id, referral_code, created_at, updated_at) VALUES (?,?,?,?)",
                         (user_id, code, TimeUtils.utc_iso(), TimeUtils.utc_iso()))
        return True

    @staticmethod
    async def get_language(user_id: int) -> str:
        row = await DB.fetchone("SELECT language FROM users WHERE user_id=?", (user_id,))
        return row[0] if row else 'ar'

    @staticmethod
    async def set_language(user_id: int, lang: str) -> None:
        await DB.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))

    @staticmethod
    async def has_active_subscription(user_id: int) -> bool:
        row = await DB.fetchone("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        if row and row[0]:
            end = TimeUtils.safe_parse_iso(row[0])
            if end:
                return end > TimeUtils.utc_now()
        return False

    @staticmethod
    async def get_subscription_end(user_id: int) -> Optional[datetime]:
        row = await DB.fetchone("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        if row and row[0]:
            return TimeUtils.safe_parse_iso(row[0])
        return None

    @staticmethod
    async def activate_subscription(user_id: int, days: int) -> None:
        row = await DB.fetchone("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        current_end = None
        if row and row[0]:
            current_end = TimeUtils.safe_parse_iso(row[0])
        new_end = (current_end if current_end and current_end > TimeUtils.utc_now() else TimeUtils.utc_now()) + timedelta(days=days)
        await DB.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (new_end.isoformat(), user_id))

    @staticmethod
    async def get_all_users() -> List[tuple]:
        return await DB.fetchall("SELECT user_id, banned FROM users")

    @staticmethod
    async def is_banned(user_id: int) -> bool:
        row = await DB.fetchone("SELECT banned FROM users WHERE user_id=?", (user_id,))
        return row and row[0] == 1

    @staticmethod
    async def get_stats() -> Dict[str, int]:
        total = (await DB.fetchone("SELECT COUNT(*) FROM users"))[0]
        banned = (await DB.fetchone("SELECT COUNT(*) FROM users WHERE banned=1"))[0]
        posts = (await DB.fetchone("SELECT COUNT(*) FROM posts"))[0]
        groups = (await DB.fetchone("SELECT COUNT(*) FROM bot_groups"))[0]
        channels = (await DB.fetchone("SELECT COUNT(*) FROM user_channels"))[0]
        return {'users': total, 'banned': banned, 'posts': posts, 'groups': groups, 'channels': channels}

    @staticmethod
    async def get_referral_code(user_id: int) -> Optional[str]:
        row = await DB.fetchone("SELECT referral_code FROM users WHERE user_id=?", (user_id,))
        return row[0] if row else None

    @staticmethod
    async def get_user_by_referral_code(code: str) -> Optional[int]:
        row = await DB.fetchone("SELECT user_id FROM users WHERE referral_code=?", (code,))
        return row[0] if row else None

    @staticmethod
    async def has_used_trial(user_id: int) -> bool:
        row = await DB.fetchone("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        return row and row[0] == 1

    @staticmethod
    async def activate_trial(user_id: int) -> int:
        row = await DB.fetchone("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        if row and row[0] == 1:
            return 0
        end = (TimeUtils.utc_now() + timedelta(days=30)).isoformat()
        await DB.execute("UPDATE users SET trial_used=1, subscription_end=? WHERE user_id=?", (end, user_id))
        return 30

    @staticmethod
    async def get_auto_status(user_id: int) -> bool:
        row = await DB.fetchone("SELECT auto_publish FROM users WHERE user_id=?", (user_id,))
        return row and row[0] == 1

    @staticmethod
    async def set_auto(user_id: int, enabled: bool) -> None:
        await DB.execute("UPDATE users SET auto_publish=? WHERE user_id=?", (1 if enabled else 0, user_id))

class ChannelRepository:
    @staticmethod
    async def add(user_id: int, channel_id: str, channel_name: str) -> Optional[int]:
        row = await DB.fetchone("SELECT id FROM user_channels WHERE user_id=? AND channel_id=?", (user_id, channel_id))
        if row:
            return None
        result = await DB.fetchone(
            "INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) VALUES (?,?,?,?) RETURNING id",
            (user_id, channel_id, channel_name, TimeUtils.utc_iso()))
        ch_db_id = result[0] if result else None
        if ch_db_id:
            interval = 720
            next_date = TimeUtils.utc_now() + timedelta(seconds=interval)
            await DB.execute("INSERT OR IGNORE INTO schedule (channel_db_id, next_publish_date) VALUES (?,?)",
                             (ch_db_id, next_date.isoformat()))
        return ch_db_id

    @staticmethod
    async def get_all(user_id: int) -> List[dict]:
        rows = await DB.fetchall(
            "SELECT id, channel_id, channel_name, banned FROM user_channels WHERE user_id=? ORDER BY id", (user_id,))
        return [dict(row) for row in rows]

    @staticmethod
    async def get_info(channel_db_id: int) -> Optional[dict]:
        row = await DB.fetchone("SELECT channel_id, channel_name FROM user_channels WHERE id=?", (channel_db_id,))
        return dict(row) if row else None

    @staticmethod
    async def delete(user_id: int, channel_db_id: int) -> bool:
        await DB.execute("DELETE FROM posts WHERE channel_db_id=?", (channel_db_id,))
        await DB.execute("DELETE FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        await DB.execute("DELETE FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
        await DB.execute("DELETE FROM user_channels WHERE id=? AND user_id=?", (channel_db_id, user_id))
        return True

    @staticmethod
    async def get_active(user_id: int) -> Optional[int]:
        row = await DB.fetchone("SELECT active_channel FROM users WHERE user_id=?", (user_id,))
        if row and row[0]:
            banned = await DB.fetchone("SELECT banned FROM user_channels WHERE id=?", (row[0],))
            if banned and banned[0] == 0:
                return row[0]
        row2 = await DB.fetchone("SELECT id FROM user_channels WHERE user_id=? AND banned=0 ORDER BY id LIMIT 1", (user_id,))
        return row2[0] if row2 else None

    @staticmethod
    async def set_active(user_id: int, channel_db_id: int) -> None:
        row = await DB.fetchone("SELECT banned FROM user_channels WHERE id=? AND user_id=?", (channel_db_id, user_id))
        if row and row[0] == 0:
            await DB.execute("UPDATE users SET active_channel=? WHERE user_id=?", (channel_db_id, user_id))

    @staticmethod
    async def get_stats(channel_db_id: int) -> Dict[str, int]:
        total = (await DB.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,)))[0]
        published = (await DB.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=1", (channel_db_id,)))[0]
        return {'total': total, 'published': published, 'unpublished': total - published}

class PostRepository:
    @staticmethod
    async def save(channel_db_id: int, posts: List[tuple]) -> int:
        vals = [(channel_db_id, TextUtils.sanitize(t), m, f, TimeUtils.utc_iso()) for t, m, f in posts]
        await DB.executemany(
            "INSERT INTO posts (channel_db_id, text, media_type, media_file_id, created_at) VALUES (?,?,?,?,?)", vals)
        return len(vals)

    @staticmethod
    async def get_next(channel_db_id: int) -> Optional[dict]:
        row = await DB.fetchone(
            "SELECT id, text, media_type, media_file_id FROM posts WHERE channel_db_id=? AND published=0 AND (fail_count IS NULL OR fail_count < 3) ORDER BY id LIMIT 1",
            (channel_db_id,))
        return dict(row) if row else None

    @staticmethod
    async def mark_published(post_id: int) -> None:
        await DB.execute("UPDATE posts SET published=1, published_at=? WHERE id=?", (TimeUtils.utc_iso(), post_id))

    @staticmethod
    async def increment_fail(post_id: int) -> None:
        await DB.execute("UPDATE posts SET fail_count = fail_count + 1 WHERE id=?", (post_id,))

    @staticmethod
    async def get_unpublished_count(channel_db_id: int) -> int:
        return (await DB.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=0", (channel_db_id,)))[0]

    @staticmethod
    async def reset_all(channel_db_id: int) -> int:
        await DB.execute("UPDATE posts SET published=0, fail_count=0 WHERE channel_db_id=?", (channel_db_id,))
        return (await DB.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,)))[0]

    @staticmethod
    async def get_user_posts(channel_db_id: int, limit: int = 15) -> List[dict]:
        rows = await DB.fetchall(
            "SELECT id, text, media_type, media_file_id FROM posts WHERE channel_db_id=? AND published=0 ORDER BY id LIMIT ?",
            (channel_db_id, limit))
        return [dict(row) for row in rows]

    @staticmethod
    async def delete_single(post_id: int, user_id: int, channel_db_id: int) -> bool:
        row = await DB.fetchone("SELECT 1 FROM user_channels WHERE id=? AND user_id=? AND banned=0", (channel_db_id, user_id))
        if not row:
            return False
        await DB.execute("DELETE FROM posts WHERE id=? AND channel_db_id=?", (post_id, channel_db_id))
        return True

    @staticmethod
    async def get_user_unpublished(user_id: int) -> int:
        return (await DB.fetchone(
            "SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=? AND p.published=0 AND uc.banned=0",
            (user_id,)))[0]

    @staticmethod
    async def get_user_total(user_id: int) -> int:
        return (await DB.fetchone(
            "SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=? AND uc.banned=0",
            (user_id,)))[0]

class ScheduleRepository:
    @staticmethod
    async def save(channel_db_id: int, schedule_type: str, **kwargs) -> None:
        next_date = None
        if schedule_type == 'interval_minutes':
            next_date = TimeUtils.utc_now() + timedelta(minutes=kwargs.get('interval_minutes', 12))
        elif schedule_type == 'interval_hours':
            next_date = TimeUtils.utc_now() + timedelta(hours=kwargs.get('interval_hours', 1))
        elif schedule_type == 'interval_days':
            next_date = TimeUtils.utc_now() + timedelta(days=kwargs.get('interval_days', 1))
        else:
            next_date = TimeUtils.utc_now() + timedelta(minutes=12)
        await DB.execute("""
            INSERT OR REPLACE INTO schedule
            (channel_db_id, schedule_type, interval_minutes, interval_hours, interval_days,
             days_of_week, specific_dates, publish_time, cron_expression, next_publish_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (channel_db_id, schedule_type,
              kwargs.get('interval_minutes', 12),
              kwargs.get('interval_hours', 0),
              kwargs.get('interval_days', 0),
              kwargs.get('days_of_week', '[]'),
              kwargs.get('specific_dates', '[]'),
              kwargs.get('publish_time', '00:00'),
              kwargs.get('cron_expression'),
              next_date.isoformat() if next_date else None))

    @staticmethod
    async def get(channel_db_id: int) -> dict:
        row = await DB.fetchone(
            "SELECT schedule_type, interval_minutes, interval_hours, interval_days, days_of_week, specific_dates, publish_time, cron_expression, next_publish_date FROM schedule WHERE channel_db_id=?",
            (channel_db_id,))
        if row:
            return {'type': row[0] or 'interval_minutes', 'interval_minutes': row[1] or 12, 'interval_hours': row[2] or 0,
                    'interval_days': row[3] or 0, 'days_of_week': row[4] or '[]', 'specific_dates': row[5] or '[]',
                    'publish_time': row[6] or '00:00', 'cron_expression': row[7], 'next_publish_date': row[8]}
        return {'type': 'interval_minutes', 'interval_minutes': 12, 'interval_hours': 0, 'interval_days': 0,
                'days_of_week': '[]', 'specific_dates': '[]', 'publish_time': '00:00', 'cron_expression': None,
                'next_publish_date': None}

    @staticmethod
    async def set_next_publish_date(channel_db_id: int, next_date: Optional[datetime]) -> None:
        await DB.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?",
                         (next_date.isoformat() if next_date else None, channel_db_id))

    @staticmethod
    async def set_last_publish(channel_db_id: int, publish_time: datetime) -> None:
        await DB.execute("INSERT OR REPLACE INTO last_publish (channel_db_id, last_publish_time) VALUES (?,?)",
                         (channel_db_id, publish_time.isoformat()))

    @staticmethod
    async def get_last_publish(channel_db_id: int) -> Optional[datetime]:
        row = await DB.fetchone("SELECT last_publish_time FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
        if row and row[0]:
            return TimeUtils.safe_parse_iso(row[0])
        return None

    @staticmethod
    async def update_next(channel_db_id: int) -> None:
        last_time = await ScheduleRepository.get_last_publish(channel_db_id) or TimeUtils.utc_now()
        s = await ScheduleRepository.get(channel_db_id)
        st = s.get('type', 'interval_minutes')
        if st == 'interval_minutes':
            interval = s.get('interval_minutes', 12)
            nd = last_time + timedelta(minutes=interval)
        elif st == 'interval_hours':
            interval = s.get('interval_hours', 1)
            nd = last_time + timedelta(hours=interval)
        elif st == 'interval_days':
            interval = s.get('interval_days', 1)
            nd = last_time + timedelta(days=interval)
        else:
            nd = last_time + timedelta(minutes=12)
        while nd <= TimeUtils.utc_now():
            if st == 'interval_minutes':
                nd += timedelta(minutes=s.get('interval_minutes', 12))
            elif st == 'interval_hours':
                nd += timedelta(hours=s.get('interval_hours', 1))
            elif st == 'interval_days':
                nd += timedelta(days=s.get('interval_days', 1))
            else:
                nd += timedelta(minutes=12)
        await DB.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?", (nd.isoformat(), channel_db_id))

class SettingRepository:
    @staticmethod
    async def get(key: str) -> Optional[str]:
        row = await DB.fetchone("SELECT value FROM settings WHERE key=?", (key,))
        return row[0] if row else None

    @staticmethod
    async def set(key: str, value: str) -> None:
        await DB.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))

    @staticmethod
    async def get_publish_interval() -> int:
        v = await SettingRepository.get('publish_interval')
        return int(v) if v else 720

    @staticmethod
    async def get_auto_backup() -> bool:
        v = await SettingRepository.get('auto_backup')
        return v == '1'

    @staticmethod
    async def get_updates_channel() -> Optional[str]:
        return await SettingRepository.get('updates_channel')

    @staticmethod
    async def get_force_subscribe_channel() -> Optional[str]:
        return await SettingRepository.get('force_subscribe_channel')

    @staticmethod
    async def get_log_channel_id() -> Optional[int]:
        v = await SettingRepository.get('log_channel_id')
        return int(v) if v else None

class GroupRepository:
    @staticmethod
    async def register(chat_id: int, chat_name: str, added_by: int, username: str = None) -> bool:
        row = await DB.fetchone("SELECT chat_id, banned FROM bot_groups WHERE chat_id=?", (chat_id,))
        if row:
            await DB.execute("UPDATE bot_groups SET chat_name=?, username=?, added_by=?, updated_at=? WHERE chat_id=?",
                             (chat_name[:255], username[:100] if username else None, added_by, TimeUtils.utc_iso(), chat_id))
            return not row[1]
        await DB.execute(
            "INSERT INTO bot_groups (chat_id, chat_name, username, added_by, added_at) VALUES (?,?,?,?,?)",
            (chat_id, chat_name[:255], username[:100] if username else None, added_by, TimeUtils.utc_iso()))
        return True

    @staticmethod
    async def get_user_groups(user_id: int) -> List[tuple]:
        result = []
        seen = set()
        async with DB._get_connection() as conn:
            for table, col in [("hidden_owner_groups", "owner_id"), ("hidden_admins", "admin_id"), ("group_admins", "user_id")]:
                async with conn.execute(
                    f"SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned FROM bot_groups bg INNER JOIN {table} h ON bg.chat_id=h.chat_id WHERE h.{col}=?",
                    (user_id,)
                ) as cur:
                    rows = await cur.fetchall()
                    for row in rows:
                        if row[0] not in seen:
                            seen.add(row[0])
                            result.append(row)
        return result

    @staticmethod
    async def sync_admins(chat_id: int, bot) -> int:
        try:
            admins = await bot.get_chat_administrators(chat_id)
            ids = [a.user.id for a in admins]
            if not ids:
                return 0
            await DB.execute("DELETE FROM group_admins WHERE chat_id=?", (chat_id,))
            await DB.executemany("INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?,?)",
                                 [(chat_id, uid) for uid in ids])
            return len(ids)
        except:
            return 0

class SecurityRepository:
    _cache = TTLCache(maxsize=500, ttl=CONFIG.CACHE_TTL)
    _ALLOWED_COLUMNS = {
        'delete_links', 'mentions', 'slow_mode', 'slow_mode_seconds',
        'welcome_enabled', 'welcome_text', 'goodbye_enabled', 'goodbye_text',
        'delete_banned_words', 'auto_penalty', 'auto_mute_duration',
        'delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
        'delete_documents', 'delete_stickers', 'delete_forwarded',
        'delete_polls', 'delete_games', 'delete_voice', 'delete_video_note',
        'delete_penalty', 'delete_penalty_duration',
        'antiflood_enabled', 'antiflood_messages', 'antiflood_seconds', 'antiflood_penalty',
        'max_warnings', 'warn_penalty', 'max_message_length',
        'night_mode_enabled', 'night_mode_start', 'night_mode_end', 'night_mode_action',
        'nsfw_enabled', 'nsfw_threshold'
    }
    _DEFAULTS = {
        'delete_links': False, 'mentions': False, 'slow_mode': False, 'slow_mode_seconds': 5,
        'welcome_enabled': False, 'welcome_text': "مرحباً {user} في {chat} 🤍",
        'goodbye_enabled': False, 'goodbye_text': "وداعاً {user} 👋",
        'delete_banned_words': False, 'auto_penalty': 'none', 'auto_mute_duration': 60,
        'delete_videos': False, 'delete_audio': False, 'delete_animation': False,
        'delete_service': False, 'delete_documents': False, 'delete_stickers': False,
        'delete_forwarded': False, 'delete_polls': False, 'delete_games': False,
        'delete_voice': False, 'delete_video_note': False,
        'delete_penalty': 'none', 'delete_penalty_duration': 0,
        'antiflood_enabled': False, 'antiflood_messages': 5, 'antiflood_seconds': 10,
        'antiflood_penalty': 'mute', 'max_warnings': 3, 'warn_penalty': 'ban',
        'max_message_length': 0, 'night_mode_enabled': False,
        'night_mode_start': '23:00', 'night_mode_end': '06:00', 'night_mode_action': 'mute',
        'nsfw_enabled': False, 'nsfw_threshold': 0.7
    }

    @classmethod
    async def get(cls, chat_id: int, force_refresh: bool = False) -> dict:
        if not force_refresh and chat_id in cls._cache:
            return cls._cache[chat_id].copy()
        row = await DB.fetchone("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
        if row:
            settings = {}
            for k in cls._DEFAULTS:
                if k in row.keys():
                    v = row[k]
                    if isinstance(cls._DEFAULTS[k], bool):
                        settings[k] = (v == 1) if v is not None else cls._DEFAULTS[k]
                    else:
                        settings[k] = v if v is not None else cls._DEFAULTS[k]
                else:
                    settings[k] = cls._DEFAULTS[k]
            cls._cache[chat_id] = settings
            return settings
        await DB.execute("INSERT INTO group_security (chat_id) VALUES (?)", (chat_id,))
        cls._cache[chat_id] = cls._DEFAULTS.copy()
        return cls._DEFAULTS.copy()

    @classmethod
    async def set(cls, chat_id: int, **kwargs) -> bool:
        bool_fields = {
            'delete_links', 'mentions', 'slow_mode', 'delete_banned_words',
            'welcome_enabled', 'goodbye_enabled', 'delete_videos', 'delete_audio',
            'delete_animation', 'delete_service', 'delete_documents', 'delete_stickers',
            'delete_forwarded', 'delete_polls', 'delete_games', 'delete_voice',
            'delete_video_note', 'antiflood_enabled', 'night_mode_enabled', 'nsfw_enabled'
        }
        allowed_penalties = ['none', 'warn', 'mute', 'kick', 'ban']
        validated = {}
        for k, v in kwargs.items():
            if k not in cls._ALLOWED_COLUMNS:
                continue
            if k in bool_fields:
                validated[k] = 1 if v in (True, 1, '1', 'true', 'True', 'on') else 0
            elif k.endswith('_penalty') or k == 'auto_penalty':
                validated[k] = v if v in allowed_penalties else 'none'
            elif k == 'nsfw_threshold':
                try:
                    validated[k] = float(v)
                except:
                    validated[k] = 0.7
            else:
                try:
                    validated[k] = int(v) if v is not None else 0
                except:
                    validated[k] = 0
        if not validated:
            return False
        row = await DB.fetchone("SELECT 1 FROM group_security WHERE chat_id=?", (chat_id,))
        if not row:
            await DB.execute("INSERT INTO group_security (chat_id) VALUES (?)", (chat_id,))
        updates = [f"{k}=?" for k in validated]
        vals = list(validated.values()) + [chat_id]
        await DB.execute(f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id=?", vals)
        cls._cache.pop(chat_id, None)
        return True

    @classmethod
    async def add_banned_word(cls, word: str, chat_id: int, added_by: int) -> Tuple[bool, bool]:
        if not word or len(word) < 2:
            return False, False
        word = word.strip().lower()[:100]
        if chat_id == -1:
            if not await BotAdminRepository.is_admin(added_by):
                return False, False
            count = (await DB.fetchone("SELECT COUNT(*) FROM banned_words WHERE chat_id=-1"))[0]
            if count >= CONFIG.MAX_GLOBAL_BANNED_WORDS:
                return False, False
        try:
            await DB.execute("INSERT INTO banned_words (word, chat_id, added_by, added_at) VALUES (?,?,?,?)",
                             (word, chat_id, added_by, TimeUtils.utc_iso()))
            return True, False
        except sqlite3.IntegrityError:
            return False, True

    @classmethod
    async def remove_banned_word(cls, word: str, chat_id: int) -> bool:
        await DB.execute("DELETE FROM banned_words WHERE word=? AND chat_id=?", (word.strip().lower(), chat_id))
        return True

    @classmethod
    async def get_banned_words(cls, chat_id: int) -> List[tuple]:
        if chat_id == -1:
            rows = await DB.fetchall("SELECT word, added_by, added_at FROM banned_words WHERE chat_id=-1 ORDER BY word")
        else:
            rows = await DB.fetchall(
                "SELECT word, added_by, added_at FROM banned_words WHERE chat_id=? OR chat_id=-1 ORDER BY word", (chat_id,))
        return rows

    @classmethod
    async def contains_banned_word(cls, text: str, chat_id: int) -> Optional[str]:
        if not text:
            return None
        words = await cls.get_banned_words(chat_id)
        tl = text.lower()
        for w, _, _ in words:
            if w in tl:
                return w
        return None

class ChatLockRepository:
    @staticmethod
    async def is_locked(chat_id: int) -> bool:
        row = await DB.fetchone("SELECT 1 FROM chat_locks WHERE chat_id=? AND locked=1", (chat_id,))
        return row is not None

    @staticmethod
    async def set_lock(chat_id: int, locked: bool, locked_by: int = None) -> bool:
        if locked:
            await DB.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?,1,?,?)",
                             (chat_id, TimeUtils.utc_iso(), locked_by))
        else:
            await DB.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        return True

class AutoReplyRepository:
    _cache = TTLCache(maxsize=200, ttl=CONFIG.CACHE_TTL)

    @classmethod
    async def get_settings(cls, chat_id: int) -> dict:
        if chat_id in cls._cache:
            return cls._cache[chat_id]
        row = await DB.fetchone("SELECT enabled, only_admins, ignore_bots FROM auto_reply_settings WHERE chat_id=?", (chat_id,))
        if row:
            res = {'enabled': row[0] == 1, 'only_admins': row[1] == 1, 'ignore_bots': row[2] == 1}
        else:
            res = {'enabled': False, 'only_admins': False, 'ignore_bots': True}
        cls._cache[chat_id] = res
        return res

    @classmethod
    async def set_enabled(cls, chat_id: int, enabled: bool) -> None:
        await DB.execute("INSERT OR REPLACE INTO auto_reply_settings (chat_id, enabled, updated_at) VALUES (?,?,?)",
                         (chat_id, 1 if enabled else 0, TimeUtils.utc_iso()))
        cls._cache.pop(chat_id, None)

    @classmethod
    async def set_only_admins(cls, chat_id: int, only_admins: bool) -> None:
        await DB.execute("UPDATE auto_reply_settings SET only_admins=?, updated_at=? WHERE chat_id=?",
                         (1 if only_admins else 0, TimeUtils.utc_iso(), chat_id))
        cls._cache.pop(chat_id, None)

    @classmethod
    async def add_reply(cls, chat_id: int, keyword: str, reply: str, reply_type: str = 'text',
                        reply_media_id: str = None, reply_buttons: str = None) -> None:
        await DB.execute(
            "INSERT OR REPLACE INTO auto_replies (chat_id, keyword, reply, reply_type, reply_media_id, reply_buttons, created_at) VALUES (?,?,?,?,?,?,?)",
            (chat_id, keyword.lower(), reply, reply_type, reply_media_id, reply_buttons, TimeUtils.utc_iso()))
        cls._cache.pop(chat_id, None)

    @classmethod
    async def remove_reply(cls, chat_id: int, keyword: str) -> bool:
        await DB.execute("DELETE FROM auto_replies WHERE chat_id=? AND keyword=?", (chat_id, keyword.lower()))
        cls._cache.pop(chat_id, None)
        return True

    @classmethod
    async def get_reply(cls, keyword: str, chat_id: int = 0) -> Optional[dict]:
        """نسخة محسّنة مع كاش LRU وتحديث مجمع"""
        cache_key = f"{chat_id}:{keyword.lower()}"
        
        # 1. حاول جلب الرد من الكاش
        cached = _auto_reply_cache.get(cache_key)
        if cached:
            # زيادة العداد في الخلفية دون انتظار
            asyncio.create_task(_increment_usage_async(chat_id, keyword.lower()))
            return cached.copy()
        
        # 2. غير موجود في الكاش → استعلام من قاعدة البيانات
        async with DB._get_connection() as conn:
            async with conn.execute(
                "SELECT reply, reply_type, reply_media_id, reply_buttons FROM auto_replies "
                "WHERE chat_id=? AND keyword=? AND is_active=1 LIMIT 1",
                (chat_id, keyword.lower())
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                
                # زيادة العداد
                await conn.execute(
                    "UPDATE auto_replies SET usage_count = usage_count + 1 WHERE chat_id=? AND keyword=?",
                    (chat_id, keyword.lower())
                )
                await conn.commit()
                
                try:
                    buttons = json.loads(row[3]) if row[3] else None
                except:
                    buttons = None
                
                reply_data = {
                    'reply': row[0],
                    'type': row[1],
                    'media_id': row[2],
                    'buttons': buttons
                }
                
                # تخزين في الكاش
                _auto_reply_cache.set(cache_key, reply_data)
                return reply_data

    @classmethod
    async def get_stats(cls, chat_id: int, limit: int = 10) -> List[tuple]:
        if chat_id == -1:
            return await DB.fetchall(
                "SELECT keyword, usage_count FROM auto_replies WHERE is_active=1 ORDER BY usage_count DESC LIMIT ?", (limit,))
        else:
            return await DB.fetchall(
                "SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? AND is_active=1 ORDER BY usage_count DESC LIMIT ?",
                (chat_id, limit))

    @classmethod
    async def reset(cls, chat_id: int) -> None:
        await DB.execute("DELETE FROM auto_replies WHERE chat_id=?", (chat_id,))
        cls._cache.pop(chat_id, None)
        _auto_reply_cache.invalidate()

async def _increment_usage_async(chat_id: int, keyword: str):
    """زيادة العداد بشكل غير متزامن (تجميع)"""
    global _usage_updates
    key = (chat_id, keyword.lower())
    _usage_updates[key] = _usage_updates.get(key, 0) + 1
    if len(_usage_updates) >= _USAGE_FLUSH_LIMIT:
        await _flush_usage_updates()

async def _flush_usage_updates():
    """حفظ التحديثات المجمعة لـ usage_count في قاعدة البيانات"""
    global _usage_updates
    if not _usage_updates:
        return
    data = list(_usage_updates.items())
    _usage_updates.clear()
    
    async with DB._get_connection() as conn:
        for (chat_id, keyword), count in data:
            await conn.execute(
                "UPDATE auto_replies SET usage_count = usage_count + ? WHERE chat_id=? AND keyword=?",
                (count, chat_id, keyword)
            )
        await conn.commit()

async def flush_usage_periodically():
    """مهمة خلفية لتخزين الإحصائيات كل 60 ثانية"""
    while True:
        await asyncio.sleep(_USAGE_FLUSH_INTERVAL)
        await _flush_usage_updates()

async def export_auto_replies(chat_id: int, file_path: str = None) -> int:
    """تصدير جميع الردود النشطة لمجموعة معينة إلى ملف JSON"""
    rows = await DB.fetchall(
        "SELECT keyword, reply, reply_type, reply_media_id, reply_buttons "
        "FROM auto_replies WHERE chat_id=? AND is_active=1",
        (chat_id,)
    )
    if not rows:
        return 0
    
    data = [dict(row) for row in rows]
    if file_path is None:
        file_path = f"auto_replies_{chat_id}.json"
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(data)

async def import_auto_replies(chat_id: int, file_path: str, overwrite: bool = False) -> int:
    """استيراد الردود من ملف JSON إلى مجموعة معينة"""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    count = 0
    for item in data:
        keyword = item.get('keyword', '').strip().lower()
        if not keyword:
            continue
        reply = item.get('reply', '').strip()
        if not reply:
            continue
        
        if overwrite:
            await DB.execute(
                "DELETE FROM auto_replies WHERE chat_id=? AND keyword=?",
                (chat_id, keyword)
            )
        
        await AutoReplyRepository.add_reply(
            chat_id,
            keyword,
            reply,
            item.get('reply_type', 'text'),
            item.get('reply_media_id'),
            item.get('reply_buttons')
        )
        count += 1
    
    _auto_reply_cache.invalidate()
    return count

class TicketRepository:
    @staticmethod
    async def save(user_id: int, username: str, message: str, ticket_num: int,
                   media_type: str = None, media_file_id: str = None) -> None:
        await DB.execute("""
            INSERT INTO support_tickets (user_id, username, message, media_type, media_file_id, ticket_number, created_at)
            VALUES (?,?,?,?,?,?,?)
        """, (user_id, username, message, media_type, media_file_id, ticket_num, TimeUtils.utc_iso()))

    @staticmethod
    async def get_next_number() -> int:
        row = await DB.fetchone("SELECT value FROM settings WHERE key='last_ticket_number'")
        return int(row[0]) if row else 0

    @staticmethod
    async def get_all() -> List[dict]:
        rows = await DB.fetchall(
            "SELECT id, user_id, username, message, media_type, media_file_id, ticket_number, status, created_at FROM support_tickets ORDER BY created_at DESC LIMIT 20")
        return [dict(row) for row in rows]

    @staticmethod
    async def mark_replied(ticket_id: int) -> None:
        await DB.execute("UPDATE support_tickets SET status='replied', replied=1 WHERE id=?", (ticket_id,))

    @staticmethod
    async def delete_all() -> None:
        await DB.execute("DELETE FROM support_tickets")

class ReferralRepository:
    @staticmethod
    async def add(referrer_id: int, referred_id: int) -> bool:
        if referrer_id == referred_id:
            return False
        if await UserRepository.is_banned(referrer_id):
            return False
        today = TimeUtils.utc_now().date().isoformat()
        count = (await DB.fetchone("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND date(created_at)=?", (referrer_id, today)))[0]
        if count >= CONFIG.MAX_DAILY_REFERRALS:
            return False
        row = await DB.fetchone("SELECT 1 FROM referrals WHERE referred_id=?", (referred_id,))
        if row:
            return False
        await DB.execute("INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?,?,?)",
                         (referrer_id, referred_id, TimeUtils.utc_iso()))
        return True

    @staticmethod
    async def auto_reward(referrer_id: int) -> int:
        await DB.execute("""
            INSERT INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days, last_referral_date)
            VALUES (?,1,3,0,?) ON CONFLICT(user_id) DO UPDATE SET
            referral_count=referral_count+1, total_reward_days=total_reward_days+3, last_referral_date=?
        """, (referrer_id, TimeUtils.utc_iso(), TimeUtils.utc_iso()))
        return 3

    @staticmethod
    async def get_stats(user_id: int) -> dict:
        total = (await DB.fetchone("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,)))[0]
        row = await DB.fetchone(
            "SELECT referral_count, total_reward_days, claimed_reward_days FROM referral_rewards WHERE user_id=?", (user_id,))
        if row:
            return {'total': total, 'count': row[0], 'total_days': row[1], 'claimed': row[2], 'available': row[1] - row[2]}
        return {'total': total, 'count': 0, 'total_days': 0, 'claimed': 0, 'available': 0}

    @staticmethod
    async def claim(user_id: int) -> int:
        stats = await ReferralRepository.get_stats(user_id)
        av = stats['available']
        if av <= 0:
            return 0
        row = await DB.fetchone("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        current_end = TimeUtils.safe_parse_iso(row[0]) if row and row[0] else None
        if current_end and current_end > TimeUtils.utc_now():
            days_left = (current_end - TimeUtils.utc_now()).days
        else:
            days_left = 0
        new_end = TimeUtils.utc_now() + timedelta(days=days_left + av)
        await DB.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (new_end.isoformat(), user_id))
        await DB.execute("UPDATE referral_rewards SET claimed_reward_days=claimed_reward_days+? WHERE user_id=?", (av, user_id))
        return av

    @staticmethod
    async def get_list(user_id: int) -> List[int]:
        rows = await DB.fetchall("SELECT referred_id FROM referrals WHERE referrer_id=? ORDER BY created_at DESC", (user_id,))
        return [row[0] for row in rows]

class PlanRepository:
    @staticmethod
    async def get_all_active() -> List[dict]:
        rows = await DB.fetchall("SELECT * FROM plans WHERE is_active=1 ORDER BY price")
        return [dict(row) for row in rows]

    @staticmethod
    async def get_by_id(plan_id: int) -> Optional[dict]:
        row = await DB.fetchone("SELECT * FROM plans WHERE id=?", (plan_id,))
        return dict(row) if row else None

    @staticmethod
    async def get_by_name(name: str) -> Optional[dict]:
        row = await DB.fetchone("SELECT * FROM plans WHERE name=?", (name,))
        return dict(row) if row else None

class SubscriptionRepository:
    @staticmethod
    async def create(user_id: int, plan_id: int, provider: str = 'xtr', provider_sub_id: str = None) -> int:
        plan = await PlanRepository.get_by_id(plan_id)
        result = await DB.fetchone(
            "INSERT INTO subscriptions (user_id, plan_id, status, start_date, end_date, auto_renew, provider, provider_subscription_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?) RETURNING id",
            (user_id, plan_id, 'active', TimeUtils.utc_iso(),
             (TimeUtils.utc_now() + timedelta(days=plan['duration_days'])).isoformat(), 0, provider, provider_sub_id,
             TimeUtils.utc_iso(), TimeUtils.utc_iso()))
        return result[0]

    @staticmethod
    async def get_active(user_id: int) -> Optional[dict]:
        row = await DB.fetchone(
            "SELECT s.*, p.name, p.duration_days, p.max_channels, p.max_posts, p.features FROM subscriptions s JOIN plans p ON s.plan_id = p.id WHERE s.user_id=? AND s.status='active' AND s.end_date > datetime('now') ORDER BY s.end_date DESC LIMIT 1",
            (user_id,))
        return dict(row) if row else None

    @staticmethod
    async def expire_subscription(subscription_id: int) -> None:
        await DB.execute("UPDATE subscriptions SET status='expired' WHERE id=?", (subscription_id,))

    @staticmethod
    async def set_auto_renew(subscription_id: int, enabled: bool) -> None:
        await DB.execute("UPDATE subscriptions SET auto_renew=? WHERE id=?", (1 if enabled else 0, subscription_id))

class InvoiceRepository:
    @staticmethod
    async def create(user_id: int, plan_id: int, amount: int, currency: str = 'XTR', provider: str = 'xtr') -> str:
        number = f"INV-{TimeUtils.utc_now().strftime('%Y%m')}-{secrets.token_hex(4).upper()}"
        await DB.execute(
            "INSERT INTO invoices (number, user_id, plan_id, amount, currency, status, provider, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (number, user_id, plan_id, amount, currency, 'pending', provider, TimeUtils.utc_iso()))
        return number

    @staticmethod
    async def mark_paid(invoice_number: str, payment_id: str) -> None:
        await DB.execute("UPDATE invoices SET status='paid', provider_payment_id=?, paid_at=? WHERE number=?",
                         (payment_id, TimeUtils.utc_iso(), invoice_number))

    @staticmethod
    async def get_by_number(number: str) -> Optional[dict]:
        row = await DB.fetchone("SELECT * FROM invoices WHERE number=?", (number,))
        return dict(row) if row else None

    @staticmethod
    async def get_user_invoices(user_id: int, limit: int = 20) -> List[dict]:
        rows = await DB.fetchall("SELECT * FROM invoices WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit))
        return [dict(row) for row in rows]

class PaymentService:
    @staticmethod
    async def create_payment(user_id: int, plan_id: int) -> Tuple[Optional[str], Optional[dict]]:
        plan = await PlanRepository.get_by_id(plan_id)
        if not plan:
            return None, None
        invoice_number = await InvoiceRepository.create(user_id, plan_id, plan['price'], 'XTR', 'xtr')
        payment_data = {
            'invoice_number': invoice_number,
            'amount': plan['price'],
            'currency': 'XTR',
            'title': f"{plan['name']} - {CONFIG.BOT_NAME}",
            'description': plan['description'],
            'payload': json.dumps({'plan_id': plan_id, 'invoice': invoice_number})
        }
        return invoice_number, payment_data

    @staticmethod
    async def handle_successful_payment(user_id: int, payload: str) -> bool:
        try:
            data = json.loads(payload)
            plan_id = data.get('plan_id')
            invoice_number = data.get('invoice')
            if not plan_id or not invoice_number:
                return False
            plan = await PlanRepository.get_by_id(plan_id)
            if not plan:
                return False
            await InvoiceRepository.mark_paid(invoice_number, f"XTR_{secrets.token_hex(8)}")
            await UserRepository.activate_subscription(user_id, plan['duration_days'])
            await SubscriptionRepository.create(user_id, plan_id, 'xtr')
            await DB.execute(
                "INSERT INTO payment_logs (user_id, provider, event_type, data, created_at) VALUES (?,?,?,?,?)",
                (user_id, 'xtr', 'payment_success', json.dumps({'plan': plan['name'], 'amount': plan['price']}),
                 TimeUtils.utc_iso()))
            return True
        except Exception as e:
            log_error(e, {'payload': payload, 'user_id': user_id})
            return False

class ContestRepository:
    @staticmethod
    async def create(creator_id: int, title: str, description: str, prize: str, end_date: datetime, contest_type: str = 'raffle') -> Optional[int]:
        result = await DB.fetchone(
            "INSERT INTO contests (creator_id, title, description, prize, end_date, contest_type, created_at) VALUES (?,?,?,?,?,?,?) RETURNING id",
            (creator_id, title, description, prize, end_date.isoformat(), contest_type, TimeUtils.utc_iso()))
        return result[0] if result else None

    @staticmethod
    async def participate(user_id: int, contest_id: int, answer: str = "") -> bool:
        try:
            await DB.execute("INSERT INTO contest_participants (user_id, contest_id, answer, joined_at) VALUES (?,?,?,?)",
                             (user_id, contest_id, answer, TimeUtils.utc_iso()))
            return True
        except:
            return False

    @staticmethod
    async def get_active(limit: int = 10) -> List[dict]:
        rows = await DB.fetchall("""
            SELECT c.id, c.title, c.description, c.prize, c.end_date, c.contest_type,
                   (SELECT COUNT(*) FROM contest_participants WHERE contest_id=c.id) as participants
            FROM contests c WHERE c.status='active' ORDER BY c.end_date ASC LIMIT ?
        """, (limit,))
        return [dict(row) for row in rows]

    @staticmethod
    async def get_winners(limit: int = 10) -> List[dict]:
        rows = await DB.fetchall("""
            SELECT c.id, c.title, c.prize, cw.winner_id, cw.announced_at FROM contest_winners cw
            JOIN contests c ON cw.contest_id = c.id ORDER BY cw.announced_at DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in rows]

    @staticmethod
    async def set_winner(contest_id: int, winner_id: int) -> bool:
        await DB.execute("UPDATE contests SET status='finished', winner_id=? WHERE id=?", (winner_id, contest_id))
        await DB.execute("INSERT INTO contest_winners (contest_id, winner_id, announced_at) VALUES (?,?,?)",
                         (contest_id, winner_id, TimeUtils.utc_iso()))
        return True

    @staticmethod
    async def delete(contest_id: int, user_id: int) -> bool:
        row = await DB.fetchone("SELECT creator_id FROM contests WHERE id=?", (contest_id,))
        if row and (row[0] == user_id or await BotAdminRepository.is_admin(user_id)):
            await DB.execute("DELETE FROM contest_participants WHERE contest_id=?", (contest_id,))
            await DB.execute("DELETE FROM contests WHERE id=?", (contest_id,))
            return True
        return False

class ReminderRepository:
    @staticmethod
    async def update_settings(user_id: int, **kwargs) -> None:
        await DB.execute("INSERT OR IGNORE INTO user_reminder_settings (user_id) VALUES (?)", (user_id,))
        updates = [f"{k}=?" for k in kwargs]
        vals = list(kwargs.values()) + [user_id]
        if updates:
            await DB.execute(f"UPDATE user_reminder_settings SET {', '.join(updates)} WHERE user_id=?", vals)

    @staticmethod
    async def get_settings(user_id: int) -> dict:
        row = await DB.fetchone(
            "SELECT subscription_reminder, daily_stats_reminder, weekly_report, reminder_days_before, notification_lang FROM user_reminder_settings WHERE user_id=?",
            (user_id,))
        if row:
            return {'sub': row[0] == 1, 'daily': row[1] == 1, 'weekly': row[2] == 1, 'days': row[3] or 3, 'lang': row[4] or 'ar'}
        return {'sub': True, 'daily': False, 'weekly': True, 'days': 3, 'lang': 'ar'}

    @staticmethod
    async def get_users_needing_reminder() -> List[dict]:
        now = TimeUtils.utc_now()
        users = []
        rows = await DB.fetchall("""
            SELECT u.user_id, u.subscription_end, COALESCE(r.reminder_days_before,3) as days_before, COALESCE(r.notification_lang,'ar') as lang, r.last_reminder_sent
            FROM users u
            LEFT JOIN user_reminder_settings r ON u.user_id = r.user_id
            WHERE u.subscription_end IS NOT NULL AND u.subscription_end > datetime('now') AND u.banned=0
        """)
        for row in rows:
            try:
                ed = TimeUtils.safe_parse_iso(row[1])
                if not ed:
                    continue
                dl = (ed - now).days
                if 0 < dl <= row[2]:
                    last = row[4]
                    if not last or (now - TimeUtils.safe_parse_iso(last)).days >= 1:
                        users.append({'user_id': row[0], 'days_left': dl, 'lang': row[3]})
            except:
                pass
        return users

class BotAdminRepository:
    @staticmethod
    async def is_admin(user_id: int) -> bool:
        if user_id == CONFIG.PRIMARY_OWNER_ID:
            return True
        row = await DB.fetchone("SELECT 1 FROM bot_admins WHERE user_id=?", (user_id,))
        return row is not None

    @staticmethod
    async def add(user_id: int) -> bool:
        await DB.execute("INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)",
                         (user_id, CONFIG.PRIMARY_OWNER_ID, TimeUtils.utc_iso()))
        return True

    @staticmethod
    async def remove(user_id: int) -> bool:
        await DB.execute("DELETE FROM bot_admins WHERE user_id=?", (user_id,))
        return True

# =====================================================================
# 10. تحليل المشاعر
# =====================================================================
class SentimentAnalyzer:
    def __init__(self):
        self.positive = {"جميل", "رائع", "ممتاز", "حلو", "شكرا", "شكراً", "تسلم", "فرح", "سعيد", "مبسوط", "الحمد", "تفاؤل", "أمل", "نجاح", "مبدع", "خير", "بركة", "نعمة"}
        self.negative = {"زعل", "حزين", "متعب", "محبط", "غضب", "غاضب", "مزعج", "سيء", "سخيف", "غبي", "ممل", "كره", "موت", "ألم", "جرح", "نكد", "فشل", "خسر", "ظلم", "حرب", "شر", "لعنة"}
        self.neutral = {"تمام", "حاضر", "اوك", "بخير", "ماشي", "طيب", "جيد", "عادي", "موافق"}

    def analyze(self, text: str) -> dict:
        if not text:
            return {'sentiment': 'neutral', 'score': 0.0}
        words = re.findall(r'\b\w+\b', text.lower())
        pc = sum(1 for w in words if w in self.positive)
        nc = sum(1 for w in words if w in self.negative)
        nuc = sum(1 for w in words if w in self.neutral)
        total = pc + nc + nuc
        if total == 0:
            return {'sentiment': 'neutral', 'score': 0.0}
        score = (pc - nc) / max(total, 1)
        sentiment = 'positive' if score > 0.2 else 'negative' if score < -0.2 else 'neutral'
        return {'sentiment': sentiment, 'score': round(score, 3)}

SENTIMENT = SentimentAnalyzer()
_sentiment_buffer = []
_SENTIMENT_BUFFER_LIMIT = 50

async def _flush_sentiment_buffer():
    global _sentiment_buffer
    if not _sentiment_buffer:
        return
    data = _sentiment_buffer.copy()
    _sentiment_buffer.clear()
    async with DB._get_connection() as conn:
        await conn.executemany(
            "INSERT INTO sentiment_history (user_id, chat_id, text_encrypted, sentiment, score, created_at) VALUES (?,?,?,?,?,?)",
            data
        )
        await conn.commit()

async def save_sentiment(user_id: int, chat_id: int, text: str, sentiment: str, score: float) -> None:
    encrypted = ENCRYPT.encrypt_text(text[:500])
    _sentiment_buffer.append((user_id, chat_id, encrypted, sentiment, score, TimeUtils.utc_iso()))
    if len(_sentiment_buffer) >= _SENTIMENT_BUFFER_LIMIT:
        await _flush_sentiment_buffer()

# =====================================================================
# 11. الصلاحيات والمصادقة
# =====================================================================
_auth_cache = TTLCache(maxsize=1000, ttl=10)

async def is_authorized_in_group(bot, chat_id: int, user_id: int) -> bool:
    if user_id == CONFIG.PRIMARY_OWNER_ID:
        return True
    cache_key = f"auth_{chat_id}_{user_id}"
    if cache_key in _auth_cache:
        return _auth_cache[cache_key]
    authorized = False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            authorized = True
        else:
            row = await DB.fetchone(
                "SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=? AND is_hidden=1", (chat_id, user_id))
            if row:
                authorized = True
            else:
                row2 = await DB.fetchone("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, user_id))
                authorized = row2 is not None
    except:
        authorized = False
    _auth_cache[cache_key] = authorized
    return authorized

def invalidate_auth_cache(chat_id: int = None, user_id: int = None) -> None:
    try:
        if chat_id and user_id:
            _auth_cache.pop(f"auth_{chat_id}_{user_id}", None)
        elif chat_id:
            for k in list(_auth_cache.keys()):
                if k.startswith(f"auth_{chat_id}_"):
                    _auth_cache.pop(k, None)
        else:
            _auth_cache.clear()
    except:
        pass

async def check_bot_permissions(bot, chat_id: int) -> dict:
    try:
        me = await bot.get_chat_member(chat_id, bot.id)
        if me.status not in ['administrator', 'creator']:
            return {'can_act': False, 'reason': 'البوت ليس مشرفاً'}
        can_delete = getattr(me, 'can_delete_messages', False)
        can_ban = getattr(me, 'can_restrict_members', False)
        if not can_delete or not can_ban:
            return {'can_act': False, 'reason': 'صلاحيات ناقصة (حذف/تقييد)'}
        return {'can_act': True, 'reason': '', 'permissions': {'can_delete': can_delete, 'can_ban': can_ban}}
    except:
        return {'can_act': False, 'reason': 'خطأ في التحقق'}

# =====================================================================
# 12. دوال الإرسال الآمن
# =====================================================================
async def safe_send(bot, chat_id: int, text: str, reply_markup=None, **kwargs):
    if not text:
        return
    try:
        escaped = TextUtils.escape_markdown_v2(text)
        if len(escaped) > 4096:
            escaped = escaped[:4093] + "..."
        return await bot.send_message(chat_id=chat_id, text=escaped, parse_mode='MarkdownV2', reply_markup=reply_markup, **kwargs)
    except:
        try:
            html_text = html.escape(text)
            if len(html_text) > 4096:
                html_text = html_text[:4093] + "..."
            return await bot.send_message(chat_id=chat_id, text=html_text, parse_mode='HTML', reply_markup=reply_markup, **kwargs)
        except:
            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', text)
            if len(plain) > 4096:
                plain = plain[:4093] + "..."
            return await bot.send_message(chat_id=chat_id, text=plain, reply_markup=reply_markup, **kwargs)

# =====================================================================
# 13. تعريفات الكيبوردات (الأزرار)
# =====================================================================
class CB:
    MAIN = "main"
    BACK = "back"
    CANCEL = "cancel"
    CH_ADD = "ch_add"
    CH_LIST = "ch_list"
    CH_DEL = "ch_del:"
    CH_SEL = "ch_sel:"
    POST_ADD = "post_add"
    POST_PUB = "post_pub"
    POST_LIST = "post_list"
    POST_REC = "post_rec"
    POST_DEL = "post_del:"
    POST_CLEAR = "post_clear:"
    PUB_ALL = "pub_all"
    STATS_PEND = "stats_pend"
    STATS_FULL = "stats_full"
    GROUPS = "groups"
    GRP_SET = "grp_set:"
    SETTINGS = "settings"
    TOGGLE_AUTO = "toggle_auto"
    TOGGLE_REC = "toggle_rec"
    SCHEDULE = "schedule:"
    SCHED_MIN = "sched_min:"
    SCHED_HOUR = "sched_hour:"
    SCHED_DAY = "sched_day:"
    SCHED_TIME = "sched_time:"
    SEC_BANNED = "sec_banned:"
    SEC_CLOSE = "sec_close"
    SEC_ENABLE_ALL = "sec_enable_all:"
    SEC_DISABLE_ALL = "sec_disable_all:"
    SEC_DEL_PEN = "sec_del_pen:"
    BAN_ADD = "ban_add:"
    BAN_LIST = "ban_list:"
    BAN_REM = "ban_rem:"
    PENALTY = "penalty:"
    PEN_KICK = "pen_kick:"
    PEN_BAN = "pen_ban:"
    PEN_MUTE = "pen_mute:"
    PEN_WARN = "pen_warn:"
    PEN_RESTRICT = "pen_restrict:"
    PEN_NONE = "pen_none:"
    ADV_ACT = "adv_act:"
    ACT_BAN = "act_ban:"
    ACT_MUTE = "act_mute:"
    ACT_WARN = "act_warn:"
    ACT_KICK = "act_kick:"
    ACT_RESTRICT = "act_restrict:"
    ACT_PIN = "act_pin:"
    ACT_LOG = "act_log:"
    ACT_UNBAN = "act_unban:"
    MUTE_DUR = "mute_dur:"
    PANEL_LOCK = "panel_lock:"
    PANEL_UNLOCK = "panel_unlock:"
    PANEL_CLOSE = "panel_close"
    HELP = "help"
    SUPPORT = "support"
    SUPPORT_TICKET = "support_ticket"
    TRIAL = "trial"
    SUBSCRIBE = "subscribe"
    BUY_SUB = "buy_sub:"
    DEVELOPER = "developer"
    UPDATES = "updates"
    REFERRAL = "referral"
    REF_CLAIM = "ref_claim"
    REF_LIST = "ref_list"
    REMINDER = "reminder"
    REM_TOGGLE_SUB = "rem_sub"
    REM_TOGGLE_DAILY = "rem_daily"
    REM_TOGGLE_WEEKLY = "rem_weekly"
    REM_SET_DAYS = "rem_days"
    REM_SET_LANG = "rem_lang"
    REM_LANG = "rem_lang:"
    TRANSLATION = "translation"
    TRANS_OFF = "trans_off"
    TRANS_SET = "trans_set:"
    CONTESTS = "contests"
    CONTEST_JOIN = "contest_join:"
    CONTEST_WINNERS = "contest_winners"
    ADMIN = "admin"
    ADMIN_USERS = "admin_users"
    ADMIN_BANNED = "admin_banned"
    ADMIN_UNBAN_ALL = "admin_unban_all"
    ADMIN_CHANNELS = "admin_channels"
    ADMIN_BANNED_CH = "admin_banned_ch"
    ADMIN_ACTIVATE_CH = "admin_activate_ch"
    ADMIN_GROUPS = "admin_groups"
    ADMIN_BANNED_GR = "admin_banned_gr"
    ADMIN_UNBAN_GR = "admin_unban_gr"
    ADMIN_ADD_ADMIN = "admin_add_admin"
    ADMIN_REM_ADMIN = "admin_rem_admin"
    ADMIN_RAM = "admin_ram"
    ADMIN_STATS = "admin_stats"
    ADMIN_METRICS = "admin_metrics"
    ADMIN_BACKUP = "admin_backup"
    ADMIN_RESTORE = "admin_restore"
    ADMIN_RESTORE_SEL = "admin_restore_sel:"
    ADMIN_SEND_UPDATE = "admin_send_update"
    ADMIN_SET_UPDATE_CH = "admin_set_update_ch"
    ADMIN_SHOW_UPDATE = "admin_show_update"
    ADMIN_FORCE_SUB = "admin_force_sub"
    ADMIN_SET_FORCE = "admin_set_force"
    ADMIN_BROADCAST = "admin_broadcast"
    ADMIN_CONFIRM_BROADCAST = "admin_confirm_broadcast"
    ADMIN_TICKETS = "admin_tickets"
    ADMIN_DEL_TICKETS = "admin_del_tickets"
    ADMIN_CONFIRM_DEL_TICKETS = "admin_confirm_del_tickets"
    ADMIN_LOG_CH = "admin_log_ch"
    ADMIN_SET_LOG_CH = "admin_set_log_ch"
    ADMIN_REPLIES = "admin_replies"
    ADMIN_ADD_REPLY = "admin_add_reply"
    ADMIN_LIST_REPLIES = "admin_list_replies"
    ADMIN_DEL_REPLY = "admin_del_reply"
    ADMIN_BANNED_WORDS = "admin_banned_words"
    ADMIN_ADD_BANNED = "admin_add_banned"
    ADMIN_LIST_BANNED = "admin_list_banned"
    ADMIN_REM_BANNED = "admin_rem_banned"
    ADMIN_CREATE_CONTEST = "admin_create_contest"
    ADMIN_DECLARE_WINNER = "admin_declare_winner"
    ADMIN_DEL_CONTEST = "admin_del_contest:"
    AUTO_REPLY_MENU = "auto_reply_menu:"
    AUTO_REPLY_TOGGLE = "auto_reply_toggle:"
    AUTO_REPLY_ADMINS = "auto_reply_admins:"
    AUTO_REPLY_RESET = "auto_reply_reset:"
    AUTO_REPLY_CONFIRM_RESET = "auto_reply_confirm_reset:"
    AUTO_REPLY_STATS = "auto_reply_stats:"
    AUTO_REPLY_ADD = "auto_reply_add:"
    AUTO_REPLY_DEL = "auto_reply_del:"
    AUTO_REPLY_LIST = "auto_reply_list:"
    CHECK_SUB = "check_sub"
    PLANS = "plans"
    INVOICES = "invoices"
    ADMIN_EXPORT_REPLIES = "admin_export_replies"
    ADMIN_IMPORT_REPLIES = "admin_import_replies"
    ADMIN_REFRESH_CACHE = "admin_refresh_cache"
    ADMIN_CONFIRM_IMPORT = "admin_confirm_import"

class KeyboardFactory:
    @staticmethod
    def security(chat_id: int, settings: dict, lang: str = 'ar') -> InlineKeyboardMarkup:
        def st(v):
            return "✅" if v else "❌"
        text = get_text(lang, 'security_text',
                        links=st(settings.get('delete_links', 0)),
                        mentions=st(settings.get('mentions', 0)),
                        slow=st(settings.get('slow_mode', 0)),
                        slow_sec=settings.get('slow_mode_seconds', 5),
                        welcome=st(settings.get('welcome_enabled', 0)),
                        goodbye=st(settings.get('goodbye_enabled', 0)),
                        video=st(settings.get('delete_videos', 0)),
                        audio=st(settings.get('delete_audio', 0)),
                        animation=st(settings.get('delete_animation', 0)),
                        service=st(settings.get('delete_service', 0)),
                        documents=st(settings.get('delete_documents', 0)),
                        stickers=st(settings.get('delete_stickers', 0)),
                        forwarded=st(settings.get('delete_forwarded', 0)),
                        polls=st(settings.get('delete_polls', 0)),
                        games=st(settings.get('delete_games', 0)),
                        voice=st(settings.get('delete_voice', 0)),
                        video_note=st(settings.get('delete_video_note', 0)),
                        flood=st(settings.get('antiflood_enabled', 0)),
                        night=st(settings.get('night_mode_enabled', 0)),
                        max_len=settings.get('max_message_length', 0) or 'غير محدود' if lang == 'ar' else 'Unlimited',
                        auto_penalty=settings.get('auto_penalty', 'none'),
                        delete_penalty=settings.get('delete_penalty', 'none'))
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 روابط", callback_data=f"sec_links:{chat_id}"),
             InlineKeyboardButton("@ معرفات", callback_data=f"sec_mentions:{chat_id}"),
             InlineKeyboardButton("⏱️ بطيء", callback_data=f"sec_slow:{chat_id}")],
            [InlineKeyboardButton("🎯 ترحيب", callback_data=f"sec_welcome:{chat_id}"),
             InlineKeyboardButton("👋 وداع", callback_data=f"sec_goodbye:{chat_id}"),
             InlineKeyboardButton("🚫 كلمات", callback_data=f"{CB.SEC_BANNED}{chat_id}")],
            [InlineKeyboardButton("🎬 فيديو", callback_data=f"sec_video:{chat_id}"),
             InlineKeyboardButton("🎵 صوت", callback_data=f"sec_audio:{chat_id}"),
             InlineKeyboardButton("🎞️ متحرك", callback_data=f"sec_anim:{chat_id}")],
            [InlineKeyboardButton("🛠️ خدمة", callback_data=f"sec_service:{chat_id}"),
             InlineKeyboardButton("📄 ملفات", callback_data=f"sec_doc:{chat_id}"),
             InlineKeyboardButton("🖼️ ملصقات", callback_data=f"sec_sticker:{chat_id}")],
            [InlineKeyboardButton("📨 مُعاد", callback_data=f"sec_forward:{chat_id}"),
             InlineKeyboardButton("📊 استطلاع", callback_data=f"sec_poll:{chat_id}"),
             InlineKeyboardButton("🎮 ألعاب", callback_data=f"sec_game:{chat_id}")],
            [InlineKeyboardButton("🎤 صوتي", callback_data=f"sec_voice:{chat_id}"),
             InlineKeyboardButton("🎥 نوت", callback_data=f"sec_videonote:{chat_id}"),
             InlineKeyboardButton("🌊 فيضان", callback_data=f"sec_flood:{chat_id}")],
            [InlineKeyboardButton("🌙 ليلي", callback_data=f"sec_night:{chat_id}"),
             InlineKeyboardButton("📏 طول", callback_data=f"sec_maxlen:{chat_id}"),
             InlineKeyboardButton("⚠️ تحذير", callback_data=f"sec_warn:{chat_id}")],
            [InlineKeyboardButton("⚖️ عقوبة", callback_data=f"{CB.SEC_DEL_PEN}{chat_id}"),
             InlineKeyboardButton("⚡ تفعيل الكل", callback_data=f"{CB.SEC_ENABLE_ALL}{chat_id}"),
             InlineKeyboardButton("⛔ تعطيل الكل", callback_data=f"{CB.SEC_DISABLE_ALL}{chat_id}")],
            [InlineKeyboardButton("⚖️ العقوبة", callback_data=f"{CB.PENALTY}{chat_id}"),
             InlineKeyboardButton("🛠️ متقدم", callback_data=f"{CB.ADV_ACT}{chat_id}"),
             InlineKeyboardButton("📜 سجل", callback_data=f"{CB.ACT_LOG}{chat_id}")],
            [InlineKeyboardButton("📝 ردود تلقائية", callback_data=f"{CB.AUTO_REPLY_MENU}{chat_id}")],
            [InlineKeyboardButton("🔙 إغلاق", callback_data=CB.SEC_CLOSE)]
        ])

    @staticmethod
    def admin(lang: str = 'ar') -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 المستخدمين", callback_data=CB.ADMIN_USERS),
             InlineKeyboardButton("⛔ المحظورين", callback_data=CB.ADMIN_BANNED)],
            [InlineKeyboardButton("📡 قنوات", callback_data=CB.ADMIN_CHANNELS),
             InlineKeyboardButton("👥 المجموعات", callback_data=CB.ADMIN_GROUPS)],
            [InlineKeyboardButton("👑 + مشرف", callback_data=CB.ADMIN_ADD_ADMIN),
             InlineKeyboardButton("🗑️ - مشرف", callback_data=CB.ADMIN_REM_ADMIN)],
            [InlineKeyboardButton("💬 ردود", callback_data=CB.ADMIN_REPLIES),
             InlineKeyboardButton("🚫 كلمات", callback_data=CB.ADMIN_BANNED_WORDS)],
            [InlineKeyboardButton("🖥️ الرام", callback_data=CB.ADMIN_RAM),
             InlineKeyboardButton("📊 إحصائيات", callback_data=CB.ADMIN_STATS)],
            [InlineKeyboardButton("💾 نسخ", callback_data=CB.ADMIN_BACKUP),
             InlineKeyboardButton("🔄 استعادة", callback_data=CB.ADMIN_RESTORE)],
            [InlineKeyboardButton("📢 تحديث", callback_data=CB.ADMIN_SEND_UPDATE),
             InlineKeyboardButton("📨 بث", callback_data=CB.ADMIN_BROADCAST)],
            [InlineKeyboardButton("📋 تذاكر", callback_data=CB.ADMIN_TICKETS),
             InlineKeyboardButton("📋 تقارير", callback_data=CB.ADMIN_LOG_CH)],
            [InlineKeyboardButton("🔒 اشتراك إجباري", callback_data=CB.ADMIN_FORCE_SUB),
             InlineKeyboardButton("📊 مراقبة", callback_data=CB.ADMIN_METRICS)],
            [InlineKeyboardButton("💎 الباقات", callback_data=CB.PLANS),
             InlineKeyboardButton("🧾 فواتيري", callback_data=CB.INVOICES)],
            [InlineKeyboardButton("📤 تصدير الردود", callback_data=CB.ADMIN_EXPORT_REPLIES),
             InlineKeyboardButton("📥 استيراد الردود", callback_data=CB.ADMIN_IMPORT_REPLIES)],
            [InlineKeyboardButton("🔄 تحديث الكاش", callback_data=CB.ADMIN_REFRESH_CACHE)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]
        ])

    @staticmethod
    def plans(lang: str = 'ar') -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(lang, 'subscribe_1_day'), callback_data=f"{CB.BUY_SUB}1"),
             InlineKeyboardButton(get_text(lang, 'subscribe_7_days'), callback_data=f"{CB.BUY_SUB}7")],
            [InlineKeyboardButton(get_text(lang, 'subscribe_30_days'), callback_data=f"{CB.BUY_SUB}30"),
             InlineKeyboardButton(get_text(lang, 'subscribe_90_days'), callback_data=f"{CB.BUY_SUB}90")],
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)]
        ])

    @staticmethod
    def banned_words(chat_id: int, lang: str = 'ar') -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة كلمة", callback_data=f"{CB.BAN_ADD}{chat_id}"),
             InlineKeyboardButton("📋 عرض الكلمات", callback_data=f"{CB.BAN_LIST}{chat_id}")],
            [InlineKeyboardButton("🗑️ حذف كلمة", callback_data=f"{CB.BAN_REM}{chat_id}"),
             InlineKeyboardButton("🔙 رجوع", callback_data=f"{CB.GRP_SET}{chat_id}")]
        ])

    @staticmethod
    def advanced_actions(chat_id: int, lang: str = 'ar') -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 حظر", callback_data=f"{CB.ACT_BAN}{chat_id}"),
             InlineKeyboardButton("🔇 كتم", callback_data=f"{CB.ACT_MUTE}{chat_id}")],
            [InlineKeyboardButton("⚠️ تحذير", callback_data=f"{CB.ACT_WARN}{chat_id}"),
             InlineKeyboardButton("👢 طرد", callback_data=f"{CB.ACT_KICK}{chat_id}")],
            [InlineKeyboardButton("🔒 تقييد", callback_data=f"{CB.ACT_RESTRICT}{chat_id}"),
             InlineKeyboardButton("📌 تثبيت", callback_data=f"{CB.ACT_PIN}{chat_id}")],
            [InlineKeyboardButton("🔓 إلغاء حظر", callback_data=f"{CB.ACT_UNBAN}{chat_id}"),
             InlineKeyboardButton("📜 سجل", callback_data=f"{CB.ACT_LOG}{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CB.GRP_SET}{chat_id}")]
        ])

    @staticmethod
    def mute_duration(chat_id: int, lang: str = 'ar') -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("⏱️ 5 دقائق", callback_data=f"{CB.MUTE_DUR}5:{chat_id}"),
             InlineKeyboardButton("⏱️ 30 دقيقة", callback_data=f"{CB.MUTE_DUR}30:{chat_id}")],
            [InlineKeyboardButton("⏱️ 1 ساعة", callback_data=f"{CB.MUTE_DUR}60:{chat_id}"),
             InlineKeyboardButton("⏱️ 12 ساعة", callback_data=f"{CB.MUTE_DUR}720:{chat_id}")],
            [InlineKeyboardButton("📆 يوم", callback_data=f"{CB.MUTE_DUR}1440:{chat_id}"),
             InlineKeyboardButton("📆 أسبوع", callback_data=f"{CB.MUTE_DUR}10080:{chat_id}")],
            [InlineKeyboardButton("🔇 كتم دائم", callback_data=f"{CB.MUTE_DUR}0:{chat_id}"),
             InlineKeyboardButton("🔙 رجوع", callback_data=f"{CB.ADV_ACT}{chat_id}")]
        ])

    @staticmethod
    def penalty(chat_id: int, lang: str = 'ar') -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👢 طرد", callback_data=f"{CB.PEN_KICK}{chat_id}"),
             InlineKeyboardButton("🛑 حظر", callback_data=f"{CB.PEN_BAN}{chat_id}")],
            [InlineKeyboardButton("🔇 كتم", callback_data=f"{CB.PEN_MUTE}{chat_id}"),
             InlineKeyboardButton("⚠️ تحذير", callback_data=f"{CB.PEN_WARN}{chat_id}")],
            [InlineKeyboardButton("🔒 تقييد", callback_data=f"{CB.PEN_RESTRICT}{chat_id}"),
             InlineKeyboardButton("❌ لا شيء", callback_data=f"{CB.PEN_NONE}{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CB.GRP_SET}{chat_id}")]
        ])

    @staticmethod
    def auto_reply_settings(chat_id: int, settings: dict, lang: str = 'ar') -> InlineKeyboardMarkup:
        st = get_text(lang, 'auto_reply_enabled') if settings.get('enabled') else get_text(lang, 'auto_reply_disabled')
        mode = get_text(lang, 'auto_reply_mode_admins') if settings.get('only_admins') else get_text(lang, 'auto_reply_mode_all')
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📝 الردود: {st}", callback_data=f"{CB.AUTO_REPLY_TOGGLE}{chat_id}")],
            [InlineKeyboardButton(f"👥 المستخدمون: {mode}", callback_data=f"{CB.AUTO_REPLY_ADMINS}{chat_id}")],
            [InlineKeyboardButton("🔄 إعادة تعيين", callback_data=f"{CB.AUTO_REPLY_CONFIRM_RESET}{chat_id}")],
            [InlineKeyboardButton("📊 إحصائيات", callback_data=f"{CB.AUTO_REPLY_STATS}{chat_id}")],
            [InlineKeyboardButton("📝 إدارة الردود", callback_data=f"{CB.AUTO_REPLY_MENU}{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CB.GRP_SET}{chat_id}")]
        ])

    @staticmethod
    def auto_reply_manage(chat_id: int, lang: str = 'ar') -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة رد", callback_data=f"{CB.AUTO_REPLY_ADD}{chat_id}"),
             InlineKeyboardButton("🗑️ حذف رد", callback_data=f"{CB.AUTO_REPLY_DEL}{chat_id}")],
            [InlineKeyboardButton("📋 قائمة الردود", callback_data=f"{CB.AUTO_REPLY_LIST}{chat_id}"),
             InlineKeyboardButton("🔙 رجوع", callback_data=f"{CB.AUTO_REPLY_MENU}{chat_id}")]
        ])

    @staticmethod
    async def main_menu(user_id: int) -> tuple:
        channels = await ChannelRepository.get_all(user_id)
        active = await ChannelRepository.get_active(user_id)
        cnt = 0
        ch_display = "لا توجد قنوات"
        if active:
            cnt = await PostRepository.get_unpublished_count(active)
            ch_info = await ChannelRepository.get_info(active)
            if ch_info:
                ch_display = f"{ch_info['channel_name']} ({ch_info['channel_id']})"
        groups = len(await GroupRepository.get_user_groups(user_id))
        has_sub = await UserRepository.has_active_subscription(user_id)
        sub_text = "✅ مفعل" if has_sub else "❌ غير مفعل"
        auto = await UserRepository.get_auto_status(user_id)
        auto_text = "مفعل" if auto else "معطل"
        lang = await UserRepository.get_language(user_id)
        title = get_text(lang, 'main_menu',
                         bot_name=CONFIG.BOT_NAME,
                         user_id=user_id,
                         groups=groups,
                         sub=sub_text,
                         channel=ch_display,
                         pending=cnt,
                         auto=auto_text)
        kb = []
        kb.append([InlineKeyboardButton(get_text(lang, 'groups'), callback_data=CB.GROUPS),
                   InlineKeyboardButton(get_text(lang, 'add_channel'), callback_data=CB.CH_ADD)])
        kb.append([InlineKeyboardButton(get_text(lang, 'my_channels'), callback_data=CB.CH_LIST),
                   InlineKeyboardButton(get_text(lang, 'settings'), callback_data=CB.SETTINGS)])
        if channels:
            kb.append([InlineKeyboardButton(get_text(lang, 'add_posts'), callback_data=CB.POST_ADD),
                       InlineKeyboardButton(get_text(lang, 'publish_one'), callback_data=CB.POST_PUB)])
            kb.append([InlineKeyboardButton(get_text(lang, 'my_posts'), callback_data=CB.POST_LIST),
                       InlineKeyboardButton(get_text(lang, 'recycle'), callback_data=CB.POST_REC)])
            kb.append([InlineKeyboardButton(f"📊 إحصائيات ({cnt})", callback_data=CB.STATS_PEND),
                       InlineKeyboardButton(get_text(lang, 'stats'), callback_data=CB.STATS_FULL)])
            if active:
                kb.append([InlineKeyboardButton("⏰ الجدولة", callback_data=f"{CB.SCHEDULE}{active}"),
                           InlineKeyboardButton("📊 القناة", callback_data=f"ch_stats:{active}")])
            kb.append([InlineKeyboardButton(get_text(lang, 'publish_all'), callback_data=CB.PUB_ALL)])
        kb.append([InlineKeyboardButton(get_text(lang, 'help'), callback_data=CB.HELP),
                   InlineKeyboardButton(get_text(lang, 'trial'), callback_data=CB.TRIAL)])
        kb.append([InlineKeyboardButton(get_text(lang, 'subscribe'), callback_data=CB.SUBSCRIBE),
                   InlineKeyboardButton(get_text(lang, 'developer'), callback_data=CB.DEVELOPER)])
        kb.append([InlineKeyboardButton(get_text(lang, 'language'), callback_data="language"),
                   InlineKeyboardButton(get_text(lang, 'support'), callback_data=CB.SUPPORT)])
        kb.append([InlineKeyboardButton(get_text(lang, 'referral'), callback_data=CB.REFERRAL),
                   InlineKeyboardButton(get_text(lang, 'reminder'), callback_data=CB.REMINDER)])
        kb.append([InlineKeyboardButton(get_text(lang, 'translation'), callback_data=CB.TRANSLATION),
                   InlineKeyboardButton(get_text(lang, 'contests'), callback_data=CB.CONTESTS)])
        kb.append([InlineKeyboardButton(get_text(lang, 'add_group'), url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")])
        if await BotAdminRepository.is_admin(user_id):
            kb.append([InlineKeyboardButton(get_text(lang, 'admin_panel_btn'), callback_data=CB.ADMIN)])
        return InlineKeyboardMarkup(kb), title

# =====================================================================
# 14. إدارة حالات المستخدم
# =====================================================================
class UserState(Enum):
    NONE = auto()
    ADDING_POSTS = auto()
    WAIT_CHANNEL = auto()
    WAIT_MIN = auto()
    WAIT_HOUR = auto()
    WAIT_DAY = auto()
    WAIT_PUB_TIME = auto()
    WAIT_ADMIN_ADD = auto()
    WAIT_ADMIN_REM = auto()
    WAIT_BROADCAST = auto()
    WAIT_UPDATE = auto()
    WAIT_UPDATE_CH = auto()
    WAIT_FORCE = auto()
    WAIT_REM_DAYS = auto()
    WAIT_BAN = auto()
    WAIT_MUTE = auto()
    WAIT_WARN = auto()
    WAIT_KICK = auto()
    WAIT_RESTRICT = auto()
    WAIT_UNBAN = auto()
    WAIT_PIN = auto()
    WAIT_GROUP_BAN = auto()
    WAIT_REM_GROUP_BAN = auto()
    WAIT_GLOBAL_BAN = auto()
    WAIT_REM_GLOBAL_BAN = auto()
    WAIT_KEYWORD = auto()
    WAIT_REPLY = auto()
    WAIT_SENDCODE = auto()
    WAIT_LOG_CH = auto()
    WAIT_CONTEST_TITLE = auto()
    WAIT_CONTEST_DESC = auto()
    WAIT_CONTEST_PRIZE = auto()
    WAIT_CONTEST_DATE = auto()
    WAIT_CONTEST_ANSWER = auto()
    WAIT_MAX_LEN = auto()
    WAIT_WARN_COUNT = auto()
    WAIT_AUTO_KEY = auto()
    WAIT_AUTO_REPLY = auto()
    WAIT_AUTO_DEL = auto()
    WAIT_BACKUP_INTERVAL = auto()
    WAIT_IMPORT_FILE = auto()
    SUPPORT_MODE = auto()

class StateManager:
    _states: Dict[int, UserState] = {}

    @classmethod
    def get(cls, user_id: int) -> UserState:
        return cls._states.get(user_id, UserState.NONE)

    @classmethod
    def set(cls, user_id: int, state: UserState) -> None:
        cls._states[user_id] = state

    @classmethod
    def clear(cls, user_id: int) -> None:
        cls._states.pop(user_id, None)

# =====================================================================
# 15. معالج الأوامر
# =====================================================================
class CommandHandlers:
    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        username = update.effective_user.username or ""
        first_name = update.effective_user.first_name or ""
        await UserRepository.register(user_id)
        row = await DB.fetchone("SELECT username, first_name FROM users WHERE user_id=?", (user_id,))
        if row and (row[0] != username or row[1] != first_name):
            await DB.execute("UPDATE users SET username=?, first_name=?, updated_at=? WHERE user_id=?",
                             (username, first_name, TimeUtils.utc_iso(), user_id))
        args = context.args
        if args and args[0].startswith('ref_'):
            ref_code = args[0][4:]
            referrer = await UserRepository.get_user_by_referral_code(ref_code)
            if referrer and referrer != user_id and not await UserRepository.is_banned(referrer):
                if await ReferralRepository.add(referrer, user_id):
                    reward = await ReferralRepository.auto_reward(referrer)
                    await safe_send(update.effective_chat.bot, referrer, f"🎁 تمت إحالة `{user_id}` (+{reward} يوم)")
        force_ch = await SettingRepository.get_force_subscribe_channel()
        if force_ch:
            try:
                chat = await context.bot.get_chat(f"@{force_ch}")
                member = await context.bot.get_chat_member(chat.id, user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("📢 اشترك", url=f"https://t.me/{force_ch}"),
                         InlineKeyboardButton("✅ تحقق", callback_data=CB.CHECK_SUB)]
                    ])
                    await safe_send(context.bot, user_id, f"⚠️ اشترك في @{force_ch}", reply_markup=kb)
                    return
            except:
                pass
        keyboard, title = await KeyboardFactory.main_menu(user_id)
        await safe_send(context.bot, user_id, title, reply_markup=keyboard)

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        await safe_send(context.bot, user_id, get_text(lang, 'help_text'))

    @staticmethod
    async def trial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        if await UserRepository.has_used_trial(user_id):
            await safe_send(context.bot, user_id, get_text(lang, 'trial_used'))
            return
        days = await UserRepository.activate_trial(user_id)
        await safe_send(context.bot, user_id, get_text(lang, 'trial_activated', days=days))

    @staticmethod
    async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        kb = KeyboardFactory.plans(lang)
        await safe_send(context.bot, user_id, get_text(lang, 'plan_selector'), reply_markup=kb)

    @staticmethod
    async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 تذكرة", callback_data=CB.SUPPORT_TICKET)],
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)]
        ])
        await safe_send(context.bot, user_id, get_text(lang, 'send_support_message'), reply_markup=kb)

    @staticmethod
    async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        await safe_send(context.bot, user_id, f"👨‍💻 {CONFIG.BOT_NAME}\n@RelaxMgr")

    @staticmethod
    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        stats = await UserRepository.get_stats()
        await safe_send(context.bot, user_id,
                        get_text(lang, 'admin_stats',
                                 users=stats['users'],
                                 banned=stats['banned'],
                                 posts=stats['posts'],
                                 groups=stats['groups'],
                                 channels=stats['channels']))

    @staticmethod
    async def syncgroup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            await safe_send(context.bot, update.effective_user.id, "❌ هذا الأمر يستخدم فقط في المجموعات")
            return
        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "بدون اسم"
        user_id = update.effective_user.id
        await GroupRepository.register(chat_id, chat_name, user_id, update.effective_chat.username)
        perms = await check_bot_permissions(context.bot, chat_id)
        if not perms['can_act']:
            await safe_send(context.bot, user_id,
                            f"⚠️ البوت ليس مشرفاً في المجموعة!\nتم تسجيل المجموعة `{chat_name}`.\nلتفعيل الميزات اجعل البوت مشرفاً واستخدم الأمر مجدداً.")
            return
        is_admin = False
        real_user_id = user_id
        if user_id == CONFIG.ANONYMOUS_ADMIN_ID:
            try:
                admins = await context.bot.get_chat_administrators(chat_id)
                for admin in admins:
                    if admin.status == 'creator':
                        real_user_id = admin.user.id
                        is_admin = True
                        break
                if not is_admin and admins:
                    real_user_id = admins[0].user.id
                    is_admin = True
            except:
                is_admin = False
        else:
            try:
                member = await context.bot.get_chat_member(chat_id, user_id)
                is_admin = member.status in ['administrator', 'creator']
                real_user_id = user_id
            except:
                is_admin = False
        if is_admin:
            await DB.execute("INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,1)",
                             (chat_id, real_user_id))
            invalidate_auth_cache(chat_id, real_user_id)
            admin_count = await GroupRepository.sync_admins(chat_id, context.bot)
            await safe_send(context.bot, real_user_id,
                            f"✅ تم تفعيل المجموعة بنجاح!\n👤 تم تسجيلك كمالك مخفي (المعرف: `{real_user_id}`)\n👥 تم مزامنة {admin_count} مشرف")
            try:
                await safe_send(context.bot, chat_id,
                                f"🤖 تم تفعيل البوت في المجموعة!\n🔹 استخدم /security للأمان\n🔹 /panel للوحة التحكم")
            except:
                pass
        else:
            await safe_send(context.bot, user_id,
                            f"✅ تم تسجيل المجموعة!\n🔹 لتأكيد التفعيل، يجب أن يكون البوت مشرفاً ويقوم مشرف بتنفيذ الأمر.")

    @staticmethod
    async def security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        lang = await UserRepository.get_language(user_id)
        settings = await SecurityRepository.get(chat_id)
        await safe_send(context.bot, user_id, get_text(lang, 'security_text',
                         links='✅' if settings.get('delete_links') else '❌',
                         mentions='✅' if settings.get('mentions') else '❌',
                         slow='✅' if settings.get('slow_mode') else '❌',
                         slow_sec=settings.get('slow_mode_seconds', 5),
                         welcome='✅' if settings.get('welcome_enabled') else '❌',
                         goodbye='✅' if settings.get('goodbye_enabled') else '❌',
                         video='✅' if settings.get('delete_videos') else '❌',
                         audio='✅' if settings.get('delete_audio') else '❌',
                         animation='✅' if settings.get('delete_animation') else '❌',
                         service='✅' if settings.get('delete_service') else '❌',
                         documents='✅' if settings.get('delete_documents') else '❌',
                         stickers='✅' if settings.get('delete_stickers') else '❌',
                         forwarded='✅' if settings.get('delete_forwarded') else '❌',
                         polls='✅' if settings.get('delete_polls') else '❌',
                         games='✅' if settings.get('delete_games') else '❌',
                         voice='✅' if settings.get('delete_voice') else '❌',
                         video_note='✅' if settings.get('delete_video_note') else '❌',
                         flood='✅' if settings.get('antiflood_enabled') else '❌',
                         night='✅' if settings.get('night_mode_enabled') else '❌',
                         max_len=settings.get('max_message_length', 0) or 'غير محدود',
                         auto_penalty=settings.get('auto_penalty', 'none'),
                         delete_penalty=settings.get('delete_penalty', 'none')),
                        reply_markup=KeyboardFactory.security(chat_id, settings, lang))

    @staticmethod
    async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        is_locked = await ChatLockRepository.is_locked(chat_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔒 قفل", callback_data=f"{CB.PANEL_LOCK}{chat_id}"),
             InlineKeyboardButton("🔓 فتح", callback_data=f"{CB.PANEL_UNLOCK}{chat_id}")],
            [InlineKeyboardButton(get_text('ar', 'close'), callback_data=CB.PANEL_CLOSE)]
        ])
        await safe_send(context.bot, user_id, f"📋 لوحة تحكم المجموعة\nالحالة: {'مقفلة' if is_locked else 'مفتوحة'}",
                        reply_markup=kb)

    @staticmethod
    async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        await ChatLockRepository.set_lock(chat_id, True, user_id)
        await safe_send(context.bot, user_id, "🔒 تم القفل")

    @staticmethod
    async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        await ChatLockRepository.set_lock(chat_id, False)
        await safe_send(context.bot, user_id, "🔓 تم الفتح")

    @staticmethod
    async def contests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        contests = await ContestRepository.get_active(10)
        if not contests:
            await safe_send(context.bot, user_id, get_text(lang, 'contest_no_active'))
            return
        text = "🏆 **المسابقات**\n"
        kb = []
        for c in contests:
            text += f"• {c['title']} - {c['participants']} مشارك\n"
            kb.append([InlineKeyboardButton(f"📝 شارك في {c['title']}", callback_data=f"{CB.CONTEST_JOIN}{c['id']}")])
        kb.append([InlineKeyboardButton("🏆 الفائزون", callback_data=CB.CONTEST_WINNERS)])
        kb.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)])
        await safe_send(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(kb))

    @staticmethod
    async def language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇸🇦 عربي", callback_data="lang_ar"),
             InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton(get_text('ar', 'back'), callback_data=CB.BACK)]
        ])
        await safe_send(context.bot, user_id, "🌐 اختر اللغة", reply_markup=kb)

    @staticmethod
    async def add_hidden_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        args = context.args
        if not args:
            await safe_send(context.bot, user_id, "📝 /add_hidden_admin معرف_المستخدم")
            return
        try:
            target = int(args[0])
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            return
        if await DB.fetchone("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, target)):
            await safe_send(context.bot, user_id, "❌ موجود مسبقاً")
            return
        await DB.execute("INSERT INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?,?,?,?)",
                         (chat_id, target, user_id, TimeUtils.utc_iso()))
        invalidate_auth_cache(chat_id, target)
        await safe_send(context.bot, user_id, f"✅ تم إضافة المشرف المخفي `{target}`")

    @staticmethod
    async def remove_hidden_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        args = context.args
        if not args:
            await safe_send(context.bot, user_id, "📝 /remove_hidden_admin معرف_المستخدم")
            return
        try:
            target = int(args[0])
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            return
        await DB.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, target))
        invalidate_auth_cache(chat_id, target)
        await safe_send(context.bot, user_id, f"✅ تم إزالة المشرف المخفي `{target}`")

    @staticmethod
    async def list_hidden_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        rows = await DB.fetchall(
            "SELECT admin_id, added_by, added_at FROM hidden_admins WHERE chat_id=? ORDER BY added_at DESC", (chat_id,))
        if not rows:
            await safe_send(context.bot, user_id, "📭 لا يوجد مشرفين مخفيين")
            return
        text = "🔒 **المشرفون المخفيون**\n" + "\n".join([f"• `{row[0]}` (أضيف بواسطة `{row[1]}`)" for row in rows])
        await safe_send(context.bot, user_id, text)

    @staticmethod
    async def moderation(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        args = context.args
        if not args:
            await safe_send(context.bot, user_id, f"📝 /{command} معرف_المستخدم [سبب]")
            return
        try:
            target = int(args[0])
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            return
        reason = " ".join(args[1:]) if len(args) > 1 else ""
        duration = None
        if command == 'mute' and len(args) > 2 and args[1].isdigit():
            duration = int(args[1])
            reason = " ".join(args[2:]) if len(args) > 2 else ""
        if command == 'unban':
            try:
                await context.bot.unban_chat_member(chat_id, target)
                await safe_send(context.bot, user_id, f"✅ تم إلغاء حظر {target}")
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ {str(e)[:100]}")
            return
        if command == 'pin':
            if update.message.reply_to_message:
                try:
                    await context.bot.pin_chat_message(chat_id, update.message.reply_to_message.message_id)
                    await safe_send(context.bot, user_id, "📌 تم التثبيت")
                except Exception as e:
                    await safe_send(context.bot, user_id, f"❌ {str(e)[:100]}")
            else:
                await safe_send(context.bot, user_id, "❌ رد على رسالة لتثبيتها")
            return
        success, msg = await apply_penalty(context.bot, chat_id, target, command, duration, reason, user_id)
        await safe_send(context.bot, user_id, msg)

# =====================================================================
# 16. معالج الكولباك (مع الأزرار الجديدة)
# =====================================================================
class CallbackHandlers:
    @staticmethod
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        data = query.data
        if not data:
            return
        await query.answer()
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)

        # أزرار عامة
        if data in (CB.MAIN, CB.BACK):
            await CommandHandlers.start(update, context)
            return
        if data == CB.CANCEL:
            StateManager.clear(user_id)
            await query.edit_message_text("❌ تم الإلغاء")
            await CommandHandlers.start(update, context)
            return
        if data == CB.HELP:
            await CommandHandlers.help_command(update, context)
            return
        if data == CB.TRIAL:
            await CommandHandlers.trial(update, context)
            return
        if data == CB.DEVELOPER:
            await CommandHandlers.developer(update, context)
            return
        if data == CB.SUBSCRIBE:
            await CommandHandlers.subscribe(update, context)
            return
        if data == CB.SUPPORT:
            await CommandHandlers.support(update, context)
            return
        if data == CB.SUPPORT_TICKET:
            StateManager.set(user_id, UserState.SUPPORT_MODE)
            await safe_send(context.bot, user_id, get_text(lang, 'send_support_message'))
            try:
                await query.message.delete()
            except:
                pass
            return
        if data == CB.CHECK_SUB:
            await CommandHandlers.start(update, context)
            return

        # أزرار تحسينات الردود التلقائية
        if data == CB.ADMIN_EXPORT_REPLIES:
            chat_id = -1  # يمكن تعديلها لتصدير ردود مجموعة محددة
            count = await export_auto_replies(chat_id)
            await query.edit_message_text(f"✅ تم تصدير {count} رد إلى ملف `auto_replies_{chat_id}.json`")
            return
        if data == CB.ADMIN_IMPORT_REPLIES:
            StateManager.set(user_id, UserState.WAIT_IMPORT_FILE)
            context.user_data['import_chat_id'] = -1
            await query.edit_message_text("📤 أرسل ملف JSON للاستيراد (سيتم استبدال الردود الموجودة)")
            return
        if data == CB.ADMIN_REFRESH_CACHE:
            _auto_reply_cache.invalidate()
            await query.edit_message_text("🔄 تم تحديث الكاش بنجاح")
            return

        # الدفع
        if data.startswith(CB.BUY_SUB):
            days = int(data.split(":")[-1])
            plan_names = {1: "يوم", 7: "أسبوع", 30: "شهر", 90: "3 أشهر"}
            plan_name = plan_names.get(days)
            if not plan_name:
                await query.answer(get_text(lang, 'plan_not_found'), show_alert=True)
                return
            plan = await PlanRepository.get_by_name(plan_name)
            if not plan:
                await query.answer(get_text(lang, 'plan_not_found'), show_alert=True)
                return
            invoice_number, payment_data = await PaymentService.create_payment(user_id, plan['id'])
            if not invoice_number:
                await query.answer(get_text(lang, 'payment_init_failed'), show_alert=True)
                return
            try:
                await context.bot.send_invoice(
                    chat_id=user_id,
                    title=get_text(lang, 'buy_plan', plan=plan['name']),
                    description=get_text(lang, 'plan_description', description=plan['description'], price=plan['price']),
                    payload=payment_data['payload'],
                    provider_token="",
                    currency="XTR",
                    prices=[LabeledPrice(f"{plan['name']} ({plan['duration_days']} {get_text(lang, 'days')})", plan['price'])]
                )
                await query.message.delete()
            except Exception as e:
                log_error(e, {'user_id': user_id, 'plan': plan_name})
                await query.answer(f"❌ {str(e)[:50]}", show_alert=True)
            return

        if data == CB.PLANS:
            kb = KeyboardFactory.plans(lang)
            await query.edit_message_text(get_text(lang, 'plan_selector'), reply_markup=kb)
            return

        if data == CB.INVOICES:
            invoices = await InvoiceRepository.get_user_invoices(user_id, 10)
            if not invoices:
                await query.edit_message_text(get_text(lang, 'no_invoices'))
                return
            text = get_text(lang, 'invoice_list',
                            invoices="\n".join([f"• #{inv['number']} - {inv['amount']} {inv['currency']} - {inv['status']}" for inv in invoices]))
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)]])
            await query.edit_message_text(text, reply_markup=kb)
            return

        # القنوات
        if data == CB.CH_ADD:
            StateManager.set(user_id, UserState.WAIT_CHANNEL)
            await query.edit_message_text(get_text(lang, 'enter_channel_id'))
            return
        if data == CB.CH_LIST:
            await CallbackHandlers._my_channels(query, user_id, lang)
            return
        if data.startswith(CB.CH_DEL):
            ch_id = int(data.split(":")[-1])
            await ChannelRepository.delete(user_id, ch_id)
            await query.edit_message_text("✅ تم الحذف")
            await CallbackHandlers._my_channels(query, user_id, lang)
            return
        if data.startswith(CB.CH_SEL):
            ch_id = int(data.split(":")[-1])
            await ChannelRepository.set_active(user_id, ch_id)
            await query.edit_message_text("✅ تم التحديد")
            await CommandHandlers.start(update, context)
            return

        # المنشورات
        if data == CB.POST_ADD:
            await CallbackHandlers._add_posts(query, context, user_id, lang)
            return
        if data == CB.POST_PUB:
            await CallbackHandlers._publish_one(query, context, user_id, lang)
            return
        if data == CB.POST_LIST:
            await CallbackHandlers._my_posts(query, context, user_id, lang)
            return
        if data == CB.POST_REC:
            active = await ChannelRepository.get_active(user_id)
            if active:
                await PostRepository.reset_all(active)
                await query.edit_message_text("♻️ تم")
            else:
                await query.edit_message_text(get_text(lang, 'no_active_channel'))
            return
        if data.startswith(CB.POST_DEL):
            parts = data.split(":")[-1].split("_")
            if len(parts) >= 2:
                pid, active = int(parts[0]), int(parts[1])
                await PostRepository.delete_single(pid, user_id, active)
                await CallbackHandlers._my_posts(query, context, user_id, lang)
            return
        if data.startswith(CB.POST_CLEAR):
            active = int(data.split(":")[-1])
            await DB.execute("DELETE FROM posts WHERE channel_db_id=?", (active,))
            await query.edit_message_text("✅ تم الحذف")
            return
        if data == CB.PUB_ALL:
            await CallbackHandlers._publish_all(query, context, user_id, lang)
            return

        # الإحصائيات
        if data == CB.STATS_PEND:
            u = await PostRepository.get_user_unpublished(user_id)
            t = await PostRepository.get_user_total(user_id)
            await query.edit_message_text(f"📊 غير المنشورة: {u}\n📋 الإجمالي: {t}")
            return
        if data == CB.STATS_FULL:
            ch = len(await ChannelRepository.get_all(user_id))
            t = await PostRepository.get_user_total(user_id)
            u = await PostRepository.get_user_unpublished(user_id)
            g = len(await GroupRepository.get_user_groups(user_id))
            auto = "مفعل" if await UserRepository.get_auto_status(user_id) else "معطل"
            await query.edit_message_text(f"📈 قنوات: {ch}\n📝 منشورات: {t}\n⏳ غير منشورة: {u}\n👥 مجموعات: {g}\n⚙️ النشر: {auto}")
            return
        if data.startswith("ch_stats:"):
            active = int(data.split(":")[-1])
            stats = await ChannelRepository.get_stats(active)
            await query.edit_message_text(f"📊 {stats['total']} | ✅ {stats['published']} | ⏳ {stats['unpublished']}")
            return

        # المجموعات
        if data == CB.GROUPS:
            await CallbackHandlers._my_groups(query, context, user_id, lang)
            return
        if data.startswith(CB.GRP_SET):
            await CallbackHandlers._group_settings(query, context, user_id, lang)
            return

        # الإعدادات
        if data == CB.SETTINGS:
            await CallbackHandlers._settings(query, user_id, lang)
            return
        if data == CB.TOGGLE_AUTO:
            cur = await UserRepository.get_auto_status(user_id)
            await UserRepository.set_auto(user_id, not cur)
            await CallbackHandlers._settings(query, user_id, lang)
            return

        # الجدولة
        if data.startswith(CB.SCHEDULE):
            ch_id = int(data.split(":")[-1])
            context.user_data['schedule_ch'] = ch_id
            s = await ScheduleRepository.get(ch_id)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏱️ دقائق", callback_data=f"{CB.SCHED_MIN}{ch_id}"),
                 InlineKeyboardButton("⏱️ ساعات", callback_data=f"{CB.SCHED_HOUR}{ch_id}")],
                [InlineKeyboardButton("⏱️ أيام", callback_data=f"{CB.SCHED_DAY}{ch_id}"),
                 InlineKeyboardButton("🕐 وقت النشر", callback_data=f"{CB.SCHED_TIME}{ch_id}")],
                [InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)]
            ])
            await query.edit_message_text(get_text(lang, 'schedule_current', type=s['type']), reply_markup=kb)
            return
        if data.startswith(CB.SCHED_MIN):
            ch_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_MIN)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text(get_text(lang, 'enter_minutes'))
            return
        if data.startswith(CB.SCHED_HOUR):
            ch_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_HOUR)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text(get_text(lang, 'enter_hours'))
            return
        if data.startswith(CB.SCHED_DAY):
            ch_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_DAY)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text(get_text(lang, 'enter_days'))
            return
        if data.startswith(CB.SCHED_TIME):
            ch_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_PUB_TIME)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text(get_text(lang, 'enter_publish_time'))
            return

        # الأمان
        if data.startswith("sec_"):
            await CallbackHandlers._security_toggle(query, context, user_id, lang)
            return
        if data == CB.SEC_CLOSE:
            try:
                await query.message.delete()
            except:
                pass
            return
        if data.startswith(CB.SEC_BANNED):
            chat_id = int(data.split(":")[-1])
            await query.edit_message_text("🚫 **الكلمات المحظورة**", reply_markup=KeyboardFactory.banned_words(chat_id, lang))
            return
        if data.startswith(CB.SEC_ENABLE_ALL):
            chat_id = int(data.split(":")[-1])
            await SecurityRepository.set(chat_id, **{f: 1 for f in
                                                     ['delete_videos', 'delete_audio', 'delete_animation',
                                                      'delete_service', 'delete_documents', 'delete_stickers',
                                                      'delete_forwarded', 'delete_polls', 'delete_games', 'delete_voice',
                                                      'delete_video_note']})
            settings = await SecurityRepository.get(chat_id, force_refresh=True)
            await query.edit_message_text(get_text(lang, 'security_text',
                         links='✅' if settings.get('delete_links') else '❌',
                         mentions='✅' if settings.get('mentions') else '❌',
                         slow='✅' if settings.get('slow_mode') else '❌',
                         slow_sec=settings.get('slow_mode_seconds', 5),
                         welcome='✅' if settings.get('welcome_enabled') else '❌',
                         goodbye='✅' if settings.get('goodbye_enabled') else '❌',
                         video='✅' if settings.get('delete_videos') else '❌',
                         audio='✅' if settings.get('delete_audio') else '❌',
                         animation='✅' if settings.get('delete_animation') else '❌',
                         service='✅' if settings.get('delete_service') else '❌',
                         documents='✅' if settings.get('delete_documents') else '❌',
                         stickers='✅' if settings.get('delete_stickers') else '❌',
                         forwarded='✅' if settings.get('delete_forwarded') else '❌',
                         polls='✅' if settings.get('delete_polls') else '❌',
                         games='✅' if settings.get('delete_games') else '❌',
                         voice='✅' if settings.get('delete_voice') else '❌',
                         video_note='✅' if settings.get('delete_video_note') else '❌',
                         flood='✅' if settings.get('antiflood_enabled') else '❌',
                         night='✅' if settings.get('night_mode_enabled') else '❌',
                         max_len=settings.get('max_message_length', 0) or 'غير محدود',
                         auto_penalty=settings.get('auto_penalty', 'none'),
                         delete_penalty=settings.get('delete_penalty', 'none')),
                        reply_markup=KeyboardFactory.security(chat_id, settings, lang))
            return
        if data.startswith(CB.SEC_DISABLE_ALL):
            chat_id = int(data.split(":")[-1])
            await SecurityRepository.set(chat_id, **{f: 0 for f in
                                                     ['delete_videos', 'delete_audio', 'delete_animation',
                                                      'delete_service', 'delete_documents', 'delete_stickers',
                                                      'delete_forwarded', 'delete_polls', 'delete_games', 'delete_voice',
                                                      'delete_video_note']})
            settings = await SecurityRepository.get(chat_id, force_refresh=True)
            await query.edit_message_text(get_text(lang, 'security_text',
                         links='✅' if settings.get('delete_links') else '❌',
                         mentions='✅' if settings.get('mentions') else '❌',
                         slow='✅' if settings.get('slow_mode') else '❌',
                         slow_sec=settings.get('slow_mode_seconds', 5),
                         welcome='✅' if settings.get('welcome_enabled') else '❌',
                         goodbye='✅' if settings.get('goodbye_enabled') else '❌',
                         video='✅' if settings.get('delete_videos') else '❌',
                         audio='✅' if settings.get('delete_audio') else '❌',
                         animation='✅' if settings.get('delete_animation') else '❌',
                         service='✅' if settings.get('delete_service') else '❌',
                         documents='✅' if settings.get('delete_documents') else '❌',
                         stickers='✅' if settings.get('delete_stickers') else '❌',
                         forwarded='✅' if settings.get('delete_forwarded') else '❌',
                         polls='✅' if settings.get('delete_polls') else '❌',
                         games='✅' if settings.get('delete_games') else '❌',
                         voice='✅' if settings.get('delete_voice') else '❌',
                         video_note='✅' if settings.get('delete_video_note') else '❌',
                         flood='✅' if settings.get('antiflood_enabled') else '❌',
                         night='✅' if settings.get('night_mode_enabled') else '❌',
                         max_len=settings.get('max_message_length', 0) or 'غير محدود',
                         auto_penalty=settings.get('auto_penalty', 'none'),
                         delete_penalty=settings.get('delete_penalty', 'none')),
                        reply_markup=KeyboardFactory.security(chat_id, settings, lang))
            return
        if data.startswith(CB.SEC_DEL_PEN):
            chat_id = int(data.split(":")[-1])
            await query.edit_message_text("⚖️ اختر عقوبة حذف الوسائط:", reply_markup=KeyboardFactory.penalty(chat_id, lang))
            return

        # الكلمات المحظورة
        if data.startswith(CB.BAN_ADD):
            chat_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            await query.edit_message_text(get_text(lang, 'enter_word'))
            return
        if data.startswith(CB.BAN_LIST):
            chat_id = int(data.split(":")[-1])
            words = await SecurityRepository.get_banned_words(chat_id)
            if not words:
                await query.edit_message_text(get_text(lang, 'no_banned_words'))
                return
            text = get_text(lang, 'banned_words_list', words="\n".join([f"• `{w[0]}`" for w in words]))
            await query.edit_message_text(text)
            return
        if data.startswith(CB.BAN_REM):
            chat_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_REM_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            await query.edit_message_text(get_text(lang, 'enter_word_to_remove'))
            return

        # العقوبات
        if data.startswith(CB.PENALTY):
            chat_id = int(data.split(":")[-1])
            await query.edit_message_text("⚖️ اختر العقوبة الأساسية:", reply_markup=KeyboardFactory.penalty(chat_id, lang))
            return
        for p in ['kick', 'ban', 'mute', 'warn', 'restrict', 'none']:
            if data.startswith(f"pen_{p}:"):
                chat_id = int(data.split(":")[-1])
                await SecurityRepository.set(chat_id, auto_penalty=p)
                await query.edit_message_text(f"✅ تم تعيين العقوبة: {p}")
                return

        # الإجراءات المتقدمة
        if data.startswith(CB.ADV_ACT):
            chat_id = int(data.split(":")[-1])
            await query.edit_message_text("🛠️ إجراءات متقدمة:", reply_markup=KeyboardFactory.advanced_actions(chat_id, lang))
            return
        if data.startswith(CB.ACT_BAN):
            chat_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_BAN)
            context.user_data['adv_chat'] = chat_id
            await query.edit_message_text("🚫 أرسل معرف المستخدم:")
            return
        if data.startswith(CB.ACT_MUTE):
            chat_id = int(data.split(":")[-1])
            await query.edit_message_text("🔇 اختر المدة:", reply_markup=KeyboardFactory.mute_duration(chat_id, lang))
            return
        if data.startswith(CB.MUTE_DUR):
            parts = data.split(":")
            minutes = int(parts[1])
            chat_id = int(parts[2])
            context.user_data['mute_minutes'] = minutes if minutes > 0 else None
            StateManager.set(user_id, UserState.WAIT_MUTE)
            context.user_data['adv_chat'] = chat_id
            await query.edit_message_text(f"🔇 كتم {minutes} دقيقة\nأرسل معرف المستخدم:")
            return
        if data.startswith(CB.ACT_WARN):
            chat_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_WARN)
            context.user_data['adv_chat'] = chat_id
            await query.edit_message_text("⚠️ أرسل معرف المستخدم:")
            return
        if data.startswith(CB.ACT_KICK):
            chat_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_KICK)
            context.user_data['adv_chat'] = chat_id
            await query.edit_message_text("👢 أرسل معرف المستخدم:")
            return
        if data.startswith(CB.ACT_RESTRICT):
            chat_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_RESTRICT)
            context.user_data['adv_chat'] = chat_id
            await query.edit_message_text("🔒 أرسل معرف المستخدم:")
            return
        if data.startswith(CB.ACT_UNBAN):
            chat_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_UNBAN)
            context.user_data['adv_chat'] = chat_id
            await query.edit_message_text("🔓 أرسل معرف المستخدم:")
            return
        if data.startswith(CB.ACT_PIN):
            chat_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_PIN)
            context.user_data['adv_chat'] = chat_id
            await query.edit_message_text("📌 أرسل معرف الرسالة أو رد على الرسالة لتثبيتها:")
            return
        if data.startswith(CB.ACT_LOG):
            chat_id = int(data.split(":")[-1])
            logs = await DB.fetchall(
                "SELECT admin_id, action, target_id, reason, created_at FROM admin_logs WHERE chat_id=? ORDER BY id DESC LIMIT 20",
                (chat_id,))
            if not logs:
                await query.edit_message_text("📭 لا توجد سجلات")
                return
            text = "📜 **آخر الإجراءات**\n"
            for admin_id, action, target_id, reason, created_at in logs:
                time_str = TimeUtils.safe_parse_iso(created_at)
                if time_str:
                    time_str = time_str.strftime("%H:%M")
                else:
                    time_str = "??"
                text += f"• {time_str} - `{admin_id}` {action}"
                if target_id:
                    text += f" → `{target_id}`"
                if reason:
                    text += f" ({reason})"
                text += "\n"
            await query.edit_message_text(text)
            return

        # لوحة التحكم
        if data.startswith(CB.PANEL_LOCK):
            chat_id = int(data.split(":")[-1])
            await ChatLockRepository.set_lock(chat_id, True, user_id)
            await CommandHandlers.panel(update, context)
            return
        if data.startswith(CB.PANEL_UNLOCK):
            chat_id = int(data.split(":")[-1])
            await ChatLockRepository.set_lock(chat_id, False)
            await CommandHandlers.panel(update, context)
            return
        if data == CB.PANEL_CLOSE:
            try:
                await query.message.delete()
            except:
                pass
            return

        # الإحالات
        if data == CB.REFERRAL:
            await CallbackHandlers._referral(query, user_id, lang)
            return
        if data == CB.REF_CLAIM:
            days = await ReferralRepository.claim(user_id)
            await query.edit_message_text(get_text(lang, 'referral_claimed', days=days) if days else get_text(lang, 'no_referrals'))
            return
        if data == CB.REF_LIST:
            referrals = await ReferralRepository.get_list(user_id)
            if not referrals:
                await query.edit_message_text(get_text(lang, 'no_referrals'))
            else:
                text = get_text(lang, 'referral_list', list="\n".join([f"• `{r}`" for r in referrals[:20]]))
                await query.edit_message_text(text)
            return

        # التذكيرات
        if data == CB.REMINDER:
            await CallbackHandlers._reminder(query, user_id, lang)
            return
        if data == CB.REM_TOGGLE_SUB:
            settings = await ReminderRepository.get_settings(user_id)
            await ReminderRepository.update_settings(user_id, subscription_reminder=not settings['sub'])
            await CallbackHandlers._reminder(query, user_id, lang)
            return
        if data == CB.REM_TOGGLE_DAILY:
            settings = await ReminderRepository.get_settings(user_id)
            await ReminderRepository.update_settings(user_id, daily_stats_reminder=not settings['daily'])
            await CallbackHandlers._reminder(query, user_id, lang)
            return
        if data == CB.REM_TOGGLE_WEEKLY:
            settings = await ReminderRepository.get_settings(user_id)
            await ReminderRepository.update_settings(user_id, weekly_report=not settings['weekly'])
            await CallbackHandlers._reminder(query, user_id, lang)
            return
        if data == CB.REM_SET_DAYS:
            StateManager.set(user_id, UserState.WAIT_REM_DAYS)
            await query.edit_message_text("📅 أرسل عدد الأيام قبل انتهاء الاشتراك (1-30):")
            return
        if data == CB.REM_SET_LANG:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🇸🇦 عربي", callback_data=f"{CB.REM_LANG}ar"),
                 InlineKeyboardButton("🇬🇧 English", callback_data=f"{CB.REM_LANG}en")],
                [InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.REMINDER)]
            ])
            await query.edit_message_text("🌐 اختر لغة الإشعارات:", reply_markup=kb)
            return
        if data.startswith(CB.REM_LANG):
            lang_set = data.split(":")[-1]
            await ReminderRepository.update_settings(user_id, notification_lang=lang_set)
            await CallbackHandlers._reminder(query, user_id, lang)
            return

        # الترجمة
        if data == CB.TRANSLATION:
            await CallbackHandlers._translation(query, user_id, lang)
            return
        if data == CB.TRANS_OFF:
            await UserRepository.set_language(user_id, 'off')
            await query.edit_message_text(get_text(lang, 'translation_off'))
            return
        if data.startswith(CB.TRANS_SET):
            lang_set = data.split(":")[-1]
            await UserRepository.set_language(user_id, lang_set)
            await query.edit_message_text(get_text(lang, 'translation_set', lang=lang_set))
            return

        # المسابقات
        if data == CB.CONTESTS:
            await CommandHandlers.contests(update, context)
            return
        if data.startswith(CB.CONTEST_JOIN):
            cid = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
            context.user_data['contest_join'] = cid
            await safe_send(context.bot, user_id, "📝 أرسل إجابتك (أو /skip للتخطي):")
            return
        if data == CB.CONTEST_WINNERS:
            winners = await ContestRepository.get_winners(10)
            if not winners:
                await query.edit_message_text(get_text(lang, 'no_contest_winners'))
                return
            text = get_text(lang, 'contest_winners',
                            winners="\n".join([f"• {w['title']} → `{w['winner_id']}`" for w in winners]))
            await query.edit_message_text(text)
            return

        # الردود التلقائية
        if data.startswith(CB.AUTO_REPLY_MENU):
            chat_id = int(data.split(":")[-1])
            await query.edit_message_text(get_text(lang, 'auto_reply_settings'),
                                          reply_markup=KeyboardFactory.auto_reply_manage(chat_id, lang))
            return
        if data.startswith(CB.AUTO_REPLY_TOGGLE):
            chat_id = int(data.split(":")[-1])
            settings = await AutoReplyRepository.get_settings(chat_id)
            new_status = not settings['enabled']
            await AutoReplyRepository.set_enabled(chat_id, new_status)
            settings = await AutoReplyRepository.get_settings(chat_id)
            await query.edit_message_text(get_text(lang, 'auto_reply_settings'),
                                          reply_markup=KeyboardFactory.auto_reply_settings(chat_id, settings, lang))
            return
        if data.startswith(CB.AUTO_REPLY_ADMINS):
            chat_id = int(data.split(":")[-1])
            settings = await AutoReplyRepository.get_settings(chat_id)
            new_admins = not settings['only_admins']
            await AutoReplyRepository.set_only_admins(chat_id, new_admins)
            settings = await AutoReplyRepository.get_settings(chat_id)
            await query.edit_message_text(get_text(lang, 'auto_reply_settings'),
                                          reply_markup=KeyboardFactory.auto_reply_settings(chat_id, settings, lang))
            return
        if data.startswith(CB.AUTO_REPLY_CONFIRM_RESET):
            chat_id = int(data.split(":")[-1])
            await AutoReplyRepository.reset(chat_id)
            settings = await AutoReplyRepository.get_settings(chat_id)
            await query.edit_message_text(get_text(lang, 'auto_reply_settings'),
                                          reply_markup=KeyboardFactory.auto_reply_settings(chat_id, settings, lang))
            return
        if data.startswith(CB.AUTO_REPLY_STATS):
            chat_id = int(data.split(":")[-1])
            stats = await AutoReplyRepository.get_stats(chat_id, 10)
            if not stats:
                await query.edit_message_text(get_text(lang, 'no_auto_reply_stats'))
                return
            text = get_text(lang, 'auto_reply_stats',
                            stats="\n".join([f"• `{kw}`: {count} مرة" for kw, count in stats]))
            await query.edit_message_text(text)
            return
        if data.startswith(CB.AUTO_REPLY_ADD):
            chat_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_AUTO_KEY)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text(get_text(lang, 'enter_keyword'))
            return
        if data.startswith(CB.AUTO_REPLY_DEL):
            chat_id = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text(get_text(lang, 'enter_keyword_to_delete'))
            return
        if data.startswith(CB.AUTO_REPLY_LIST):
            chat_id = int(data.split(":")[-1])
            replies = await AutoReplyRepository.get_stats(chat_id, 20)
            if not replies:
                await query.edit_message_text(get_text(lang, 'no_auto_replies'))
                return
            text = get_text(lang, 'auto_reply_list',
                            replies="\n".join([f"• `{kw}`: {count} مرة" for kw, count in replies]))
            await query.edit_message_text(text)
            return

        # لوحة الأدمن
        if data == CB.ADMIN:
            if user_id == CONFIG.PRIMARY_OWNER_ID or await BotAdminRepository.is_admin(user_id):
                await query.edit_message_text(get_text(lang, 'admin_panel'), reply_markup=KeyboardFactory.admin(lang))
            else:
                await query.answer(get_text(lang, 'not_authorized'), show_alert=True)
            return

        # أزرار الأدمن
        if data.startswith("admin_"):
            await CallbackHandlers._admin_router(query, context, user_id, lang)
            return

        # أزرار اللغة
        if data.startswith("lang_"):
            lang_set = data.split("_")[-1]
            await UserRepository.set_language(user_id, lang_set)
            await query.answer(f"✅ تم تغيير اللغة إلى {lang_set}")
            await CommandHandlers.start(update, context)
            return

        if data == "language":
            await CommandHandlers.language(update, context)
            return
        if data == CB.CHECK_SUB:
            await CommandHandlers.start(update, context)
            return

        await query.answer()

    # دوال مساعدة داخلية
    @staticmethod
    async def _my_channels(query, user_id, lang):
        channels = await ChannelRepository.get_all(user_id)
        if not channels:
            await query.edit_message_text(get_text(lang, 'channels_empty'))
            return
        kb = []
        for ch in channels:
            st = "🚫" if ch['banned'] else "✅"
            kb.append([InlineKeyboardButton(f"{st} {ch['channel_name']}", callback_data=f"{CB.CH_SEL}{ch['id']}"),
                       InlineKeyboardButton("🗑️", callback_data=f"{CB.CH_DEL}{ch['id']}")])
        kb.append([InlineKeyboardButton(get_text(lang, 'add_channel'), callback_data=CB.CH_ADD)])
        kb.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)])
        await query.edit_message_text("📡 **قنواتي**", reply_markup=InlineKeyboardMarkup(kb))

    @staticmethod
    async def _add_posts(query, context, user_id, lang):
        if not await UserRepository.has_active_subscription(user_id) and not await UserRepository.has_used_trial(user_id):
            await query.edit_message_text(get_text(lang, 'subscription_expired'))
            return
        active = context.user_data.get('active_channel') or await ChannelRepository.get_active(user_id)
        if not active:
            await query.edit_message_text(get_text(lang, 'no_active_channel'))
            return
        unpub = await PostRepository.get_unpublished_count(active)
        if unpub >= CONFIG.MAX_UNPUBLISHED_POSTS:
            await query.edit_message_text(get_text(lang, 'max_posts_reached'))
            return
        target = min(15, CONFIG.MAX_UNPUBLISHED_POSTS - unpub)
        context.user_data[f"session_{user_id}"] = []
        context.user_data[f"session_target_{user_id}"] = target
        StateManager.set(user_id, UserState.ADDING_POSTS)
        await query.edit_message_text(get_text(lang, 'enter_posts', count=target))

    @staticmethod
    async def _publish_one(query, context, user_id, lang):
        if not await UserRepository.has_active_subscription(user_id) and not await UserRepository.has_used_trial(user_id):
            await query.edit_message_text(get_text(lang, 'subscription_expired'))
            return
        active = context.user_data.get('active_channel') or await ChannelRepository.get_active(user_id)
        if not active:
            await query.edit_message_text(get_text(lang, 'no_active_channel'))
            return
        post = await PostRepository.get_next(active)
        if not post:
            await query.edit_message_text(get_text(lang, 'posts_empty'))
            return
        ch_info = await ChannelRepository.get_info(active)
        if not ch_info:
            return
        try:
            if post['media_type'] == 'photo' and post['media_file_id']:
                await context.bot.send_photo(ch_info['channel_id'], post['media_file_id'],
                                             caption=post['text'][:1024] if post['text'] else None)
            elif post['media_type'] == 'video' and post['media_file_id']:
                await context.bot.send_video(ch_info['channel_id'], post['media_file_id'],
                                             caption=post['text'][:1024] if post['text'] else None)
            elif post['media_type'] == 'document' and post['media_file_id']:
                await context.bot.send_document(ch_info['channel_id'], post['media_file_id'],
                                                caption=post['text'][:1024] if post['text'] else None)
            else:
                await context.bot.send_message(ch_info['channel_id'], post['text'][:4096] if post['text'] else ".")
            await PostRepository.mark_published(post['id'])
            await ScheduleRepository.set_last_publish(active, TimeUtils.utc_now())
            await ScheduleRepository.update_next(active)
            await query.edit_message_text(get_text(lang, 'publish_success'))
        except Exception as e:
            await PostRepository.increment_fail(post['id'])
            await query.edit_message_text(get_text(lang, 'publish_fail', error=str(e)[:100]))

    @staticmethod
    async def _my_posts(query, context, user_id, lang):
        active = context.user_data.get('active_channel') or await ChannelRepository.get_active(user_id)
        if not active:
            await query.edit_message_text(get_text(lang, 'no_active_channel'))
            return
        posts = await PostRepository.get_user_posts(active, 15)
        if not posts:
            await query.edit_message_text(get_text(lang, 'posts_empty'))
            return
        text = get_text(lang, 'my_posts_title') + "\n"
        kb = []
        for p in posts[:10]:
            short = (p['text'] or "بدون نص")[:50]
            text += f"🆔 {p['id']}: {short}...\n"
            kb.append([InlineKeyboardButton(f"🗑️ حذف #{p['id']}", callback_data=f"{CB.POST_DEL}{p['id']}_{active}")])
        kb.append([InlineKeyboardButton("🗑️ حذف الكل", callback_data=f"{CB.POST_CLEAR}{active}")])
        kb.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

    @staticmethod
    async def _publish_all(query, context, user_id, lang):
        channels = await ChannelRepository.get_all(user_id)
        if not channels:
            return
        tasks = []
        for ch in channels:
            if ch['banned']:
                continue
            post = await PostRepository.get_next(ch['id'])
            if not post:
                continue
            tasks.append(CallbackHandlers._publish_single(context.bot, ch['id'], ch['channel_id'], post))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await safe_send(context.bot, user_id, get_text(lang, 'publish_success'))

    @staticmethod
    async def _publish_single(bot, ch_db_id, ch_tele, post):
        try:
            if post['media_type'] == 'photo' and post['media_file_id']:
                await bot.send_photo(ch_tele, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
            else:
                await bot.send_message(ch_tele, post['text'][:4096] if post['text'] else ".")
            await PostRepository.mark_published(post['id'])
            await ScheduleRepository.set_last_publish(ch_db_id, TimeUtils.utc_now())
            await ScheduleRepository.update_next(ch_db_id)
        except:
            await PostRepository.increment_fail(post['id'])

    @staticmethod
    async def _my_groups(query, context, user_id, lang):
        groups = await GroupRepository.get_user_groups(user_id)
        valid = []
        for chat_id, chat_name, username, banned in groups:
            if await is_authorized_in_group(context.bot, chat_id, user_id):
                valid.append((chat_id, chat_name, banned))
        if not valid:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(lang, 'add_group'), url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")],
                                       [InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)]])
            await query.edit_message_text(get_text(lang, 'groups_empty'), reply_markup=kb)
            return
        kb = []
        for chat_id, chat_name, banned in valid:
            st = "⛔" if banned else "✅"
            kb.append([InlineKeyboardButton(f"{st} {chat_name[:25]}", callback_data=f"{CB.GRP_SET}{chat_id}")])
            kb.append([InlineKeyboardButton("🔐 أمان", callback_data=f"sec_links:{chat_id}"),
                       InlineKeyboardButton("📜 سجل", callback_data=f"{CB.ACT_LOG}{chat_id}"),
                       InlineKeyboardButton("⚙️ متقدم", callback_data=f"{CB.ADV_ACT}{chat_id}")])
        kb.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)])
        await query.edit_message_text(get_text(lang, 'groups_list'), reply_markup=InlineKeyboardMarkup(kb))

    @staticmethod
    async def _group_settings(query, context, user_id, lang):
        chat_id = int(query.data.split(":")[-1])
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer(get_text(lang, 'not_authorized'), show_alert=True)
            return
        settings = await SecurityRepository.get(chat_id)
        text = get_text(lang, 'security_text',
                        links='✅' if settings.get('delete_links') else '❌',
                        mentions='✅' if settings.get('mentions') else '❌',
                        slow='✅' if settings.get('slow_mode') else '❌',
                        slow_sec=settings.get('slow_mode_seconds', 5),
                        welcome='✅' if settings.get('welcome_enabled') else '❌',
                        goodbye='✅' if settings.get('goodbye_enabled') else '❌',
                        video='✅' if settings.get('delete_videos') else '❌',
                        audio='✅' if settings.get('delete_audio') else '❌',
                        animation='✅' if settings.get('delete_animation') else '❌',
                        service='✅' if settings.get('delete_service') else '❌',
                        documents='✅' if settings.get('delete_documents') else '❌',
                        stickers='✅' if settings.get('delete_stickers') else '❌',
                        forwarded='✅' if settings.get('delete_forwarded') else '❌',
                        polls='✅' if settings.get('delete_polls') else '❌',
                        games='✅' if settings.get('delete_games') else '❌',
                        voice='✅' if settings.get('delete_voice') else '❌',
                        video_note='✅' if settings.get('delete_video_note') else '❌',
                        flood='✅' if settings.get('antiflood_enabled') else '❌',
                        night='✅' if settings.get('night_mode_enabled') else '❌',
                        max_len=settings.get('max_message_length', 0) or 'غير محدود',
                        auto_penalty=settings.get('auto_penalty', 'none'),
                        delete_penalty=settings.get('delete_penalty', 'none'))
        await query.edit_message_text(text, reply_markup=KeyboardFactory.security(chat_id, settings, lang))

    @staticmethod
    async def _settings(query, user_id, lang):
        auto = "✅" if await UserRepository.get_auto_status(user_id) else "❌"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(lang, 'settings_auto', status=auto), callback_data=CB.TOGGLE_AUTO)],
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)]
        ])
        await query.edit_message_text(get_text(lang, 'settings_header'), reply_markup=kb)

    @staticmethod
    async def _security_toggle(query, context, user_id, lang):
        parts = query.data.split(":")
        if len(parts) < 3:
            return
        action = parts[1]
        try:
            chat_id = int(parts[2])
        except:
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer(get_text(lang, 'not_authorized'), show_alert=True)
            return
        field_map = {
            "links": "delete_links", "mentions": "mentions", "slow": "slow_mode",
            "video": "delete_videos", "audio": "delete_audio", "anim": "delete_animation",
            "service": "delete_service", "doc": "delete_documents", "sticker": "delete_stickers",
            "forward": "delete_forwarded", "poll": "delete_polls", "game": "delete_games",
            "voice": "delete_voice", "videonote": "delete_video_note",
            "welcome": "welcome_enabled", "goodbye": "goodbye_enabled",
            "flood": "antiflood_enabled", "night": "night_mode_enabled"
        }
        if action in field_map:
            col = field_map[action]
            settings = await SecurityRepository.get(chat_id, force_refresh=True)
            current = settings.get(col, 0)
            new_val = 1 if current == 0 else 0
            await SecurityRepository.set(chat_id, **{col: new_val})
            settings = await SecurityRepository.get(chat_id, force_refresh=True)
            await query.edit_message_text(get_text(lang, 'security_text',
                        links='✅' if settings.get('delete_links') else '❌',
                        mentions='✅' if settings.get('mentions') else '❌',
                        slow='✅' if settings.get('slow_mode') else '❌',
                        slow_sec=settings.get('slow_mode_seconds', 5),
                        welcome='✅' if settings.get('welcome_enabled') else '❌',
                        goodbye='✅' if settings.get('goodbye_enabled') else '❌',
                        video='✅' if settings.get('delete_videos') else '❌',
                        audio='✅' if settings.get('delete_audio') else '❌',
                        animation='✅' if settings.get('delete_animation') else '❌',
                        service='✅' if settings.get('delete_service') else '❌',
                        documents='✅' if settings.get('delete_documents') else '❌',
                        stickers='✅' if settings.get('delete_stickers') else '❌',
                        forwarded='✅' if settings.get('delete_forwarded') else '❌',
                        polls='✅' if settings.get('delete_polls') else '❌',
                        games='✅' if settings.get('delete_games') else '❌',
                        voice='✅' if settings.get('delete_voice') else '❌',
                        video_note='✅' if settings.get('delete_video_note') else '❌',
                        flood='✅' if settings.get('antiflood_enabled') else '❌',
                        night='✅' if settings.get('night_mode_enabled') else '❌',
                        max_len=settings.get('max_message_length', 0) or 'غير محدود',
                        auto_penalty=settings.get('auto_penalty', 'none'),
                        delete_penalty=settings.get('delete_penalty', 'none')),
                        reply_markup=KeyboardFactory.security(chat_id, settings, lang))
            return
        if action == "maxlen":
            StateManager.set(user_id, UserState.WAIT_MAX_LEN)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("📏 أرسل الحد الأقصى لطول الرسالة (0 = غير محدود):")
            return
        if action == "warn":
            settings = await SecurityRepository.get(chat_id)
            text = get_text(lang, 'warning_settings',
                            max_warnings=settings.get('max_warnings', 3),
                            warn_penalty=settings.get('warn_penalty', 'ban'))
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 تغيير عدد التحذيرات", callback_data=f"warn_count:{chat_id}"),
                 InlineKeyboardButton("⚖️ تغيير العقوبة", callback_data=f"warn_penalty:{chat_id}")],
                [InlineKeyboardButton(get_text(lang, 'back'), callback_data=f"{CB.GRP_SET}{chat_id}")]
            ])
            await query.edit_message_text(text, reply_markup=kb)
            return
        if action == "warn_count":
            StateManager.set(user_id, UserState.WAIT_WARN_COUNT)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("📝 أرسل الحد الأقصى للتحذيرات (1-10):")
            return
        if action == "warn_penalty":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 حظر", callback_data=f"set_warn_penalty:{chat_id}:ban"),
                 InlineKeyboardButton("🔇 كتم", callback_data=f"set_warn_penalty:{chat_id}:mute")],
                [InlineKeyboardButton(get_text(lang, 'back'), callback_data=f"sec_warn:{chat_id}")]
            ])
            await query.edit_message_text("⚖️ اختر عقوبة تجاوز التحذيرات:", reply_markup=kb)
            return
        if action.startswith("set_warn_penalty:"):
            _, chat_id_str, penalty = action.split(":")
            chat_id = int(chat_id_str)
            await SecurityRepository.set(chat_id, warn_penalty=penalty)
            settings = await SecurityRepository.get(chat_id, force_refresh=True)
            text = get_text(lang, 'warning_settings',
                            max_warnings=settings.get('max_warnings', 3),
                            warn_penalty=settings.get('warn_penalty', 'ban'))
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 تغيير عدد التحذيرات", callback_data=f"warn_count:{chat_id}"),
                 InlineKeyboardButton("⚖️ تغيير العقوبة", callback_data=f"warn_penalty:{chat_id}")],
                [InlineKeyboardButton(get_text(lang, 'back'), callback_data=f"{CB.GRP_SET}{chat_id}")]
            ])
            await query.edit_message_text(text, reply_markup=kb)
            return
        await query.answer()

    @staticmethod
    async def _referral(query, user_id, lang):
        stats = await ReferralRepository.get_stats(user_id)
        code = await UserRepository.get_referral_code(user_id)
        text = get_text(lang, 'referral_header',
                        link=f"https://t.me/{CONFIG.BOT_USERNAME}?start=ref_{code}",
                        total=stats['total'],
                        available=stats['available'])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(lang, 'claim_reward'), callback_data=CB.REF_CLAIM)],
            [InlineKeyboardButton(get_text(lang, 'referral_list'), callback_data=CB.REF_LIST)],
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)]
        ])
        await query.edit_message_text(text, reply_markup=kb)

    @staticmethod
    async def _reminder(query, user_id, lang):
        settings = await ReminderRepository.get_settings(user_id)
        sub = "✅" if settings['sub'] else "❌"
        daily = "✅" if settings['daily'] else "❌"
        weekly = "✅" if settings['weekly'] else "❌"
        days = settings['days']
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🔔 تذكير الاشتراك: {sub}", callback_data=CB.REM_TOGGLE_SUB)],
            [InlineKeyboardButton(f"📊 يومي: {daily}", callback_data=CB.REM_TOGGLE_DAILY)],
            [InlineKeyboardButton(f"📈 أسبوعي: {weekly}", callback_data=CB.REM_TOGGLE_WEEKLY)],
            [InlineKeyboardButton(f"📅 عدد الأيام: {days}", callback_data=CB.REM_SET_DAYS)],
            [InlineKeyboardButton("🌐 لغة الإشعارات", callback_data=CB.REM_SET_LANG)],
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)]
        ])
        await query.edit_message_text(get_text(lang, 'reminder_header'), reply_markup=kb)

    @staticmethod
    async def _translation(query, user_id, lang):
        current_lang = await UserRepository.get_language(user_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇸🇦 عربي", callback_data=f"{CB.TRANS_SET}ar"),
             InlineKeyboardButton("🇬🇧 English", callback_data=f"{CB.TRANS_SET}en")],
            [InlineKeyboardButton("🚫 إيقاف", callback_data=CB.TRANS_OFF)],
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.BACK)]
        ])
        await query.edit_message_text(f"🌐 الترجمة: {current_lang}", reply_markup=kb)

    @staticmethod
    async def _admin_router(query, context, user_id, lang):
        data = query.data
        if user_id != CONFIG.PRIMARY_OWNER_ID and not await BotAdminRepository.is_admin(user_id):
            await query.answer(get_text(lang, 'not_authorized'), show_alert=True)
            return

        if data == CB.ADMIN_USERS:
            stats = await UserRepository.get_stats()
            await query.edit_message_text(get_text(lang, 'admin_users', users=stats['users'], banned=stats['banned']))
        elif data == CB.ADMIN_BANNED:
            users = await UserRepository.get_all_users()
            banned_list = [u for u in users if u[1] == 1]
            text = get_text(lang, 'admin_banned_list', list="\n".join([f"• `{u[0]}`" for u in banned_list[:20]])) if banned_list else "لا يوجد"
            await query.edit_message_text(text)
        elif data == CB.ADMIN_UNBAN_ALL:
            await DB.execute("UPDATE users SET banned=0 WHERE banned=1")
            await query.edit_message_text(get_text(lang, 'admin_unbanned_all'))
        elif data == CB.ADMIN_CHANNELS:
            channels = await ChannelRepository.get_all(-1)
            text = get_text(lang, 'admin_channels_list',
                            list="\n".join([f"• `{ch['channel_id']}` - {ch['channel_name']} {'🚫' if ch['banned'] else '✅'}" for ch in channels[:50]])) if channels else get_text(lang, 'no_channels')
            await query.edit_message_text(text)
        elif data == CB.ADMIN_BANNED_CH:
            channels = await DB.fetchall("SELECT channel_id, channel_name FROM user_channels WHERE banned=1")
            text = get_text(lang, 'admin_banned_channels',
                            list="\n".join([f"• `{ch[0]}` - {ch[1]}" for ch in channels[:50]])) if channels else "لا توجد"
            await query.edit_message_text(text)
        elif data == CB.ADMIN_ACTIVATE_CH:
            await DB.execute("UPDATE user_channels SET banned=0 WHERE banned=1")
            await query.edit_message_text(get_text(lang, 'admin_activated_channels'))
        elif data == CB.ADMIN_GROUPS:
            rows = await DB.fetchall("SELECT chat_id, chat_name, username, banned FROM bot_groups ORDER BY chat_id LIMIT 50")
            text = get_text(lang, 'admin_groups_list',
                            list="\n".join([f"• `{r[0]}` - {r[1]} {'🚫' if r[3] else '✅'}" for r in rows])) if rows else get_text(lang, 'no_groups')
            await query.edit_message_text(text)
        elif data == CB.ADMIN_BANNED_GR:
            rows = await DB.fetchall("SELECT chat_id, chat_name, username FROM bot_groups WHERE banned=1")
            text = get_text(lang, 'admin_banned_groups',
                            list="\n".join([f"• `{r[0]}` - {r[1]}" for r in rows[:50]])) if rows else "لا توجد"
            await query.edit_message_text(text)
        elif data == CB.ADMIN_UNBAN_GR:
            await DB.execute("UPDATE bot_groups SET banned=0 WHERE banned=1")
            await query.edit_message_text(get_text(lang, 'admin_unbanned_groups'))
        elif data == CB.ADMIN_ADD_ADMIN:
            StateManager.set(user_id, UserState.WAIT_ADMIN_ADD)
            await query.edit_message_text(get_text(lang, 'admin_add_admin'))
        elif data == CB.ADMIN_REM_ADMIN:
            StateManager.set(user_id, UserState.WAIT_ADMIN_REM)
            await query.edit_message_text(get_text(lang, 'admin_rem_admin'))
        elif data == CB.ADMIN_RAM:
            ram = get_ram_usage()
            await query.edit_message_text(get_text(lang, 'admin_ram', used=ram['used'], total=ram['total'], percent=ram['percent']))
        elif data == CB.ADMIN_STATS:
            stats = await UserRepository.get_stats()
            await query.edit_message_text(get_text(lang, 'admin_stats_text',
                                                   users=stats['users'], banned=stats['banned'],
                                                   posts=stats['posts'], groups=stats['groups'], channels=stats['channels']))
        elif data == CB.ADMIN_METRICS:
            active = (await DB.fetchone("SELECT COUNT(*) FROM users WHERE updated_at > datetime('now', '-30 days')"))[0]
            today = (await DB.fetchone(
                "SELECT COUNT(*) FROM posts WHERE published_at > datetime('now', 'start of day')"))[0]
            db_size = (PATHS.DB.stat().st_size / (1024 * 1024)) if PATHS.DB.exists() else 0
            await query.edit_message_text(get_text(lang, 'admin_metrics', active=active, today=today, db_size=db_size))
        elif data == CB.ADMIN_BACKUP:
            try:
                backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2(PATHS.DB, backup_file)
                await safe_send(context.bot, user_id, get_text(lang, 'admin_backup_created', filename=backup_file.name))
            except Exception as e:
                await safe_send(context.bot, user_id, get_text(lang, 'admin_backup_failed', error=str(e)[:100]))
        elif data == CB.ADMIN_RESTORE:
            backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
            if not backups:
                await query.edit_message_text(get_text(lang, 'no_backups'))
                return
            kb = [[InlineKeyboardButton(b.name, callback_data=f"{CB.ADMIN_RESTORE_SEL}{b.name}")] for b in backups[:10]]
            kb.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.ADMIN)])
            await query.edit_message_text(get_text(lang, 'admin_restore_choose'), reply_markup=InlineKeyboardMarkup(kb))
        elif data.startswith(CB.ADMIN_RESTORE_SEL):
            filename = data.split(":")[-1]
            filepath = PATHS.BACKUPS / filename
            if not filepath.exists():
                await query.edit_message_text(get_text(lang, 'file_not_found'))
                return
            try:
                shutil.copy2(filepath, PATHS.DB)
                await query.edit_message_text(get_text(lang, 'admin_restore_success'))
            except Exception as e:
                await query.edit_message_text(get_text(lang, 'admin_restore_failed', error=str(e)[:100]))
        elif data == CB.ADMIN_SEND_UPDATE:
            StateManager.set(user_id, UserState.WAIT_UPDATE)
            await query.edit_message_text("📢 أرسل نص التحديث:")
        elif data == CB.ADMIN_SET_UPDATE_CH:
            StateManager.set(user_id, UserState.WAIT_UPDATE_CH)
            await query.edit_message_text("📢 أرسل معرف القناة (بدون @):")
        elif data == CB.ADMIN_SHOW_UPDATE:
            ch = await SettingRepository.get_updates_channel()
            await query.edit_message_text(f"📢 القناة: @{ch}" if ch else "لا توجد")
        elif data == CB.ADMIN_FORCE_SUB:
            ch = await SettingRepository.get_force_subscribe_channel()
            await query.edit_message_text(get_text(lang, 'admin_force_sub_on', channel=ch) if ch else get_text(lang, 'admin_force_sub_off'))
        elif data == CB.ADMIN_SET_FORCE:
            StateManager.set(user_id, UserState.WAIT_FORCE)
            await query.edit_message_text("🔒 أرسل معرف القناة (بدون @):")
        elif data == CB.ADMIN_BROADCAST:
            StateManager.set(user_id, UserState.WAIT_BROADCAST)
            await query.edit_message_text("📨 أرسل الرسالة:")
        elif data == CB.ADMIN_CONFIRM_BROADCAST:
            text = context.user_data.get('broadcast_text')
            if not text:
                await query.edit_message_text("لا توجد رسالة")
                return
            users = await UserRepository.get_all_users()
            sent = 0
            for uid, banned in users:
                if banned:
                    continue
                try:
                    await safe_send(context.bot, uid, text)
                    sent += 1
                except:
                    pass
            await query.edit_message_text(get_text(lang, 'admin_broadcast_sent', sent=sent))
            context.user_data.pop('broadcast_text', None)
        elif data == CB.ADMIN_TICKETS:
            tickets = await TicketRepository.get_all()
            if not tickets:
                await query.edit_message_text(get_text(lang, 'no_tickets'))
                return
            text = get_text(lang, 'tickets_list',
                            tickets="\n".join([f"#{t['ticket_number']} - من `{t['user_id']}` ({t['username'] or 'لا يوجد'})\n{t['message'][:50]}..." for t in tickets]))
            await query.edit_message_text(text)
        elif data == CB.ADMIN_DEL_TICKETS:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ نعم", callback_data=CB.ADMIN_CONFIRM_DEL_TICKETS),
                 InlineKeyboardButton("❌ لا", callback_data=CB.ADMIN)]
            ])
            await query.edit_message_text(get_text(lang, 'confirm_delete_tickets'), reply_markup=kb)
        elif data == CB.ADMIN_CONFIRM_DEL_TICKETS:
            await TicketRepository.delete_all()
            await query.edit_message_text(get_text(lang, 'tickets_deleted'))
        elif data == CB.ADMIN_LOG_CH:
            log_id = await SettingRepository.get_log_channel_id()
            await query.edit_message_text(f"📋 {log_id}" if log_id else "📋 غير محدد")
        elif data == CB.ADMIN_SET_LOG_CH:
            StateManager.set(user_id, UserState.WAIT_LOG_CH)
            await query.edit_message_text("📋 أرسل معرف القناة:")
        elif data == CB.ADMIN_REPLIES:
            stats = await AutoReplyRepository.get_stats(-1, 20)
            if not stats:
                await query.edit_message_text(get_text(lang, 'no_auto_replies'))
                return
            text = get_text(lang, 'auto_reply_stats',
                            stats="\n".join([f"• `{kw}`: {cnt} مرة" for kw, cnt in stats]))
            await query.edit_message_text(text)
        elif data == CB.ADMIN_ADD_REPLY:
            StateManager.set(user_id, UserState.WAIT_KEYWORD)
            await query.edit_message_text(get_text(lang, 'enter_keyword'))
        elif data == CB.ADMIN_LIST_REPLIES:
            replies = await DB.fetchall(
                "SELECT keyword, reply, usage_count FROM auto_replies WHERE chat_id=0 ORDER BY keyword LIMIT 20")
            if not replies:
                await query.edit_message_text(get_text(lang, 'no_auto_replies'))
                return
            text = get_text(lang, 'auto_reply_list',
                            replies="\n".join([f"• `{r[0]}` → {r[1][:30]}... ({r[2]})" for r in replies]))
            await query.edit_message_text(text)
        elif data == CB.ADMIN_DEL_REPLY:
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = -1
            await query.edit_message_text(get_text(lang, 'enter_keyword_to_delete'))
        elif data == CB.ADMIN_BANNED_WORDS:
            words = await SecurityRepository.get_banned_words(-1)
            text = get_text(lang, 'admin_banned_words_global',
                            words="\n".join([f"• `{w[0]}`" for w in words])) if words else get_text(lang, 'no_banned_words')
            await query.edit_message_text(text)
        elif data == CB.ADMIN_ADD_BANNED:
            StateManager.set(user_id, UserState.WAIT_GLOBAL_BAN)
            await query.edit_message_text(get_text(lang, 'enter_word'))
        elif data == CB.ADMIN_REM_BANNED:
            StateManager.set(user_id, UserState.WAIT_REM_GLOBAL_BAN)
            await query.edit_message_text(get_text(lang, 'enter_word_to_remove'))
        elif data == CB.ADMIN_CREATE_CONTEST:
            StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
            await query.edit_message_text("🏆 أرسل عنوان المسابقة:")
        elif data == CB.ADMIN_DECLARE_WINNER:
            contests = await DB.fetchall("SELECT id, title FROM contests WHERE status='active'")
            if not contests:
                await query.edit_message_text(get_text(lang, 'no_active_contests'))
                return
            kb = [[InlineKeyboardButton(title, callback_data=f"declare_winner_sel:{cid}")] for cid, title in contests]
            kb.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data=CB.ADMIN)])
            await query.edit_message_text("اختر المسابقة:", reply_markup=InlineKeyboardMarkup(kb))
        elif data.startswith("declare_winner_sel:"):
            cid = int(data.split(":")[-1])
            contest = await DB.fetchone("SELECT title FROM contests WHERE id=?", (cid,))
            if not contest:
                await query.edit_message_text(get_text(lang, 'contest_not_found'))
                return
            winner = await DB.fetchone(
                "SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,))
            if not winner:
                await query.edit_message_text(get_text(lang, 'admin_contest_no_participants'))
                return
            await ContestRepository.set_winner(cid, winner[0])
            await query.edit_message_text(get_text(lang, 'admin_contest_declared', title=contest[0], winner=winner[0]))
        elif data.startswith(CB.ADMIN_DEL_CONTEST):
            cid = int(data.split(":")[-1])
            await ContestRepository.delete(cid, user_id)
            await query.edit_message_text(get_text(lang, 'admin_contest_deleted'))
        else:
            await query.answer("⚠️ قيد التطوير", show_alert=True)

# =====================================================================
# 17. معالج الرسائل (مع دعم استيراد الملفات)
# =====================================================================
class MessageHandlers:
    @staticmethod
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        msg = update.message
        text = msg.text.strip() if msg.text else ""
        state = StateManager.get(user_id)
        chat_id = update.effective_chat.id if update.effective_chat else None
        lang = await UserRepository.get_language(user_id)

        # معالج استيراد ملف JSON
        if state == UserState.WAIT_IMPORT_FILE:
            if not msg.document:
                await safe_send(context.bot, user_id, "❌ أرسل ملف JSON (بامتداد .json)")
                return
            
            file = msg.document
            if not file.file_name.endswith('.json'):
                await safe_send(context.bot, user_id, "❌ الملف يجب أن يكون JSON")
                return
            
            try:
                file_obj = await context.bot.get_file(file.file_id)
                temp_path = f"/tmp/import_{user_id}.json"
                await file_obj.download_to_drive(temp_path)
                
                import_chat_id = context.user_data.get('import_chat_id', -1)
                count = await import_auto_replies(import_chat_id, temp_path, overwrite=True)
                await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد بنجاح")
                
                Path(temp_path).unlink(missing_ok=True)
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ فشل الاستيراد: {str(e)[:100]}")
            
            StateManager.clear(user_id)
            context.user_data.pop('import_chat_id', None)
            return

        # إضافة قناة
        if state == UserState.WAIT_CHANNEL:
            channel_id = text.strip()
            if not (channel_id.startswith('@') or channel_id.lstrip('-').isdigit()):
                await safe_send(context.bot, user_id, get_text(lang, 'invalid_format'))
                StateManager.clear(user_id)
                return
            try:
                chat = await context.bot.get_chat(channel_id)
                if chat.type != 'channel':
                    await safe_send(context.bot, user_id, get_text(lang, 'invalid_channel'))
                    StateManager.clear(user_id)
                    return
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status not in ['administrator', 'creator'] or not bot_member.can_post_messages:
                    await safe_send(context.bot, user_id, get_text(lang, 'bot_not_admin'))
                    StateManager.clear(user_id)
                    return
                result = await ChannelRepository.add(user_id, str(chat.id), chat.title or "بدون اسم")
                await safe_send(context.bot, user_id, get_text(lang, 'channel_added') if result else get_text(lang, 'channel_exists'))
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ {str(e)[:100]}")
            StateManager.clear(user_id)
            return

        # إضافة منشورات
        if state == UserState.ADDING_POSTS:
            session = context.user_data.get(f"session_{user_id}", [])
            target = context.user_data.get(f"session_target_{user_id}", 15)
            media_type = 'text'
            media_file_id = None
            if msg.photo:
                media_type = 'photo'
                media_file_id = msg.photo[-1].file_id
            elif msg.video:
                media_type = 'video'
                media_file_id = msg.video.file_id
            elif msg.document:
                media_type = 'document'
                media_file_id = msg.document.file_id
            elif msg.audio:
                media_type = 'audio'
                media_file_id = msg.audio.file_id
            elif msg.voice:
                media_type = 'voice'
                media_file_id = msg.voice.file_id
            elif msg.animation:
                media_type = 'animation'
                media_file_id = msg.animation.file_id
            elif msg.text:
                media_type = 'text'
            else:
                await safe_send(context.bot, user_id, "⚠️ غير مدعوم")
                return
            content = msg.caption or "" if media_type != 'text' else text
            session.append((content, media_type, media_file_id))
            context.user_data[f"session_{user_id}"] = session
            remaining = target - len(session)
            await safe_send(context.bot, user_id, get_text(lang, 'post_saved', saved=len(session), target=target, remaining=remaining))
            if len(session) >= target:
                active = context.user_data.get('active_channel') or await ChannelRepository.get_active(user_id)
                if active:
                    await PostRepository.save(active, session)
                context.user_data.pop(f"session_{user_id}", None)
                context.user_data.pop(f"session_target_{user_id}", None)
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, get_text(lang, 'all_posts_saved'))
            return

        # الجدولة
        if state == UserState.WAIT_MIN:
            try:
                val = int(text)
                if 1 <= val <= 1440:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await ScheduleRepository.save(ch, 'interval_minutes', interval_minutes=val)
                        await safe_send(context.bot, user_id, get_text(lang, 'schedule_updated_ok'))
                else:
                    await safe_send(context.bot, user_id, "❌ بين 1 و 1440")
            except:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_HOUR:
            try:
                val = int(text)
                if 1 <= val <= 168:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await ScheduleRepository.save(ch, 'interval_hours', interval_hours=val)
                        await safe_send(context.bot, user_id, get_text(lang, 'schedule_updated_ok'))
                else:
                    await safe_send(context.bot, user_id, "❌ بين 1 و 168")
            except:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_DAY:
            try:
                val = int(text)
                if 1 <= val <= 365:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await ScheduleRepository.save(ch, 'interval_days', interval_days=val)
                        await safe_send(context.bot, user_id, get_text(lang, 'schedule_updated_ok'))
                else:
                    await safe_send(context.bot, user_id, "❌ بين 1 و 365")
            except:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PUB_TIME:
            if ':' in text:
                try:
                    h, m = map(int, text.split(':'))
                    if 0 <= h <= 23 and 0 <= m <= 59:
                        ch = context.user_data.get('schedule_ch')
                        if ch:
                            await ScheduleRepository.save(ch, 'interval_minutes', publish_time=text)
                            await safe_send(context.bot, user_id, get_text(lang, 'schedule_updated_ok'))
                    else:
                        await safe_send(context.bot, user_id, "❌ وقت غير صالح")
                except:
                    await safe_send(context.bot, user_id, "❌ صيغة خاطئة")
            else:
                await safe_send(context.bot, user_id, "❌ أرسل وقت صحيح مثل 14:30")
            StateManager.clear(user_id)
            return

        # الكلمات المحظورة
        if state == UserState.WAIT_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            if chat_id_ban and await is_authorized_in_group(context.bot, chat_id_ban, user_id):
                word = text.strip().lower()
                if len(word) < 2:
                    await safe_send(context.bot, user_id, get_text(lang, 'word_too_short'))
                else:
                    added, exists = await SecurityRepository.add_banned_word(word, chat_id_ban, user_id)
                    if exists:
                        await safe_send(context.bot, user_id, get_text(lang, 'word_exists', word=word))
                    else:
                        await safe_send(context.bot, user_id, get_text(lang, 'word_added', word=word))
            else:
                await safe_send(context.bot, user_id, get_text(lang, 'not_authorized'))
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            if chat_id_ban and await is_authorized_in_group(context.bot, chat_id_ban, user_id):
                word = text.strip().lower()
                if word:
                    await SecurityRepository.remove_banned_word(word, chat_id_ban)
                    await safe_send(context.bot, user_id, get_text(lang, 'word_removed', word=word))
                else:
                    await safe_send(context.bot, user_id, get_text(lang, 'word_not_found'))
            else:
                await safe_send(context.bot, user_id, get_text(lang, 'not_authorized'))
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GLOBAL_BAN:
            word = text.strip().lower()
            if len(word) < 2:
                await safe_send(context.bot, user_id, get_text(lang, 'word_too_short'))
            else:
                added, exists = await SecurityRepository.add_banned_word(word, -1, user_id)
                if exists:
                    await safe_send(context.bot, user_id, get_text(lang, 'word_exists', word=word))
                else:
                    await safe_send(context.bot, user_id, get_text(lang, 'word_added', word=word))
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GLOBAL_BAN:
            word = text.strip().lower()
            if word:
                await SecurityRepository.remove_banned_word(word, -1)
                await safe_send(context.bot, user_id, get_text(lang, 'word_removed', word=word))
            else:
                await safe_send(context.bot, user_id, get_text(lang, 'word_not_found'))
            StateManager.clear(user_id)
            return

        # المشرفين
        if state == UserState.WAIT_ADMIN_ADD:
            try:
                target = int(text)
                await BotAdminRepository.add(target)
                await safe_send(context.bot, user_id, get_text(lang, 'admin_added', user=target))
            except:
                await safe_send(context.bot, user_id, "❌ خطأ")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ADMIN_REM:
            try:
                target = int(text)
                await BotAdminRepository.remove(target)
                await safe_send(context.bot, user_id, get_text(lang, 'admin_removed', user=target))
            except:
                await safe_send(context.bot, user_id, "❌ خطأ")
            StateManager.clear(user_id)
            return

        # البث
        if state == UserState.WAIT_BROADCAST:
            context.user_data['broadcast_text'] = text
            StateManager.clear(user_id)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد", callback_data=CB.ADMIN_CONFIRM_BROADCAST),
                                        InlineKeyboardButton("❌ إلغاء", callback_data=CB.ADMIN)]])
            await safe_send(context.bot, user_id, get_text(lang, 'admin_broadcast_confirm', text=text[:200]), reply_markup=kb)
            return

        # التحديثات
        if state == UserState.WAIT_UPDATE:
            ch = await SettingRepository.get_updates_channel()
            if ch:
                try:
                    await context.bot.send_message(f"@{ch}", f"📢 {text}")
                    await safe_send(context.bot, user_id, get_text(lang, 'admin_update_sent'))
                except:
                    await safe_send(context.bot, user_id, get_text(lang, 'admin_update_failed'))
            else:
                await safe_send(context.bot, user_id, "❌ لا توجد قناة")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_UPDATE_CH:
            await SettingRepository.set('updates_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, get_text(lang, 'admin_update_channel_set', channel=text.replace('@', '')))
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_FORCE:
            await SettingRepository.set('force_subscribe_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, get_text(lang, 'admin_force_sub_set', channel=text.replace('@', '')))
            StateManager.clear(user_id)
            return

        # التذكيرات
        if state == UserState.WAIT_REM_DAYS:
            try:
                val = int(text)
                if 1 <= val <= 30:
                    await ReminderRepository.update_settings(user_id, reminder_days_before=val)
                    await safe_send(context.bot, user_id, get_text(lang, 'reminder_days_updated', days=val))
                else:
                    await safe_send(context.bot, user_id, "❌ بين 1 و 30")
            except:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        # الإجراءات المتقدمة
        if state in (UserState.WAIT_BAN, UserState.WAIT_MUTE, UserState.WAIT_WARN,
                     UserState.WAIT_KICK, UserState.WAIT_RESTRICT, UserState.WAIT_UNBAN):
            chat_id_adv = context.user_data.get('adv_chat')
            if chat_id_adv:
                try:
                    target = int(text.split()[0]) if text.split()[0].isdigit() else None
                    if target:
                        action_map = {
                            UserState.WAIT_BAN: "ban",
                            UserState.WAIT_MUTE: "mute",
                            UserState.WAIT_WARN: "warn",
                            UserState.WAIT_KICK: "kick",
                            UserState.WAIT_RESTRICT: "restrict",
                            UserState.WAIT_UNBAN: "unban"
                        }
                        action = action_map.get(state)
                        if action:
                            dur = context.user_data.get('mute_minutes', 60) if action == 'mute' else None
                            success, msg = await apply_penalty(context.bot, chat_id_adv, target, action, dur, "", user_id)
                            await safe_send(context.bot, user_id, msg)
                except:
                    pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PIN:
            chat_id_adv = context.user_data.get('adv_chat')
            if chat_id_adv:
                try:
                    if update.message.reply_to_message:
                        msg_id = update.message.reply_to_message.message_id
                    else:
                        msg_id = int(text.strip())
                    await context.bot.pin_chat_message(chat_id_adv, msg_id)
                    await safe_send(context.bot, user_id, "📌 تم التثبيت")
                except Exception as e:
                    await safe_send(context.bot, user_id, f"❌ {str(e)[:100]}")
            StateManager.clear(user_id)
            return

        # المسابقات
        if state == UserState.WAIT_CONTEST_TITLE:
            context.user_data['contest_title'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_DESC)
            await safe_send(context.bot, user_id, "📝 أرسل الوصف:")
            return

        if state == UserState.WAIT_CONTEST_DESC:
            context.user_data['contest_desc'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_PRIZE)
            await safe_send(context.bot, user_id, "🎁 أرسل الجائزة:")
            return

        if state == UserState.WAIT_CONTEST_PRIZE:
            context.user_data['contest_prize'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_DATE)
            await safe_send(context.bot, user_id, "📅 أرسل تاريخ الانتهاء (YYYY-MM-DD HH:MM):")
            return

        if state == UserState.WAIT_CONTEST_DATE:
            try:
                end_date = datetime.strptime(text, "%Y-%m-%d %H:%M")
                if end_date > TimeUtils.mecca_now():
                    cid = await ContestRepository.create(
                        user_id,
                        context.user_data.pop('contest_title', ''),
                        context.user_data.pop('contest_desc', ''),
                        context.user_data.pop('contest_prize', ''),
                        TimeUtils.mecca_to_utc(end_date)
                    )
                    await safe_send(context.bot, user_id, get_text(lang, 'contest_created', id=cid))
                else:
                    await safe_send(context.bot, user_id, "❌ وقت في الماضي")
            except:
                await safe_send(context.bot, user_id, "❌ صيغة خاطئة")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_CONTEST_ANSWER:
            cid = context.user_data.get('contest_join')
            if cid:
                answer = text if text != '/skip' else ""
                await ContestRepository.participate(user_id, cid, answer)
                await safe_send(context.bot, user_id, get_text(lang, 'contest_joined'))
            StateManager.clear(user_id)
            return

        # الردود التلقائية
        if state == UserState.WAIT_AUTO_KEY:
            keyword = text.strip().lower()
            if keyword:
                context.user_data['auto_key'] = keyword
                StateManager.set(user_id, UserState.WAIT_AUTO_REPLY)
                await safe_send(context.bot, user_id, get_text(lang, 'enter_reply'))
            else:
                await safe_send(context.bot, user_id, "❌ كلمة غير صالحة")
                StateManager.clear(user_id)
            return

        if state == UserState.WAIT_AUTO_REPLY:
            chat_id_auto = context.user_data.get('auto_chat')
            keyword = context.user_data.get('auto_key')
            if chat_id_auto is not None and keyword:
                await AutoReplyRepository.add_reply(chat_id_auto, keyword, text)
                await safe_send(context.bot, user_id, get_text(lang, 'auto_reply_added', keyword=keyword))
            else:
                await safe_send(context.bot, user_id, "❌ خطأ في البيانات")
            StateManager.clear(user_id)
            context.user_data.pop('auto_key', None)
            context.user_data.pop('auto_chat', None)
            return

        if state == UserState.WAIT_AUTO_DEL:
            chat_id_auto = context.user_data.get('auto_chat')
            if chat_id_auto is not None:
                keyword = text.strip().lower()
                if keyword:
                    if await AutoReplyRepository.remove_reply(chat_id_auto, keyword):
                        await safe_send(context.bot, user_id, get_text(lang, 'auto_reply_deleted', keyword=keyword))
                    else:
                        await safe_send(context.bot, user_id, get_text(lang, 'auto_reply_not_found', keyword=keyword))
                else:
                    await safe_send(context.bot, user_id, "❌ كلمة غير صالحة")
            else:
                await safe_send(context.bot, user_id, "❌ خطأ في البيانات")
            StateManager.clear(user_id)
            context.user_data.pop('auto_chat', None)
            return

        # الردود العامة (الأدمن)
        if state == UserState.WAIT_KEYWORD:
            context.user_data['keyword'] = text.strip().lower()
            StateManager.set(user_id, UserState.WAIT_REPLY)
            await safe_send(context.bot, user_id, get_text(lang, 'enter_reply'))
            return

        if state == UserState.WAIT_REPLY:
            keyword = context.user_data.get('keyword')
            if keyword:
                await AutoReplyRepository.add_reply(0, keyword, text)
                await safe_send(context.bot, user_id, get_text(lang, 'auto_reply_added', keyword=keyword))
            StateManager.clear(user_id)
            context.user_data.pop('keyword', None)
            return

        # إعدادات أخرى
        if state == UserState.WAIT_LOG_CH:
            try:
                chat = await context.bot.get_chat(text)
                if chat.type == 'channel':
                    await SettingRepository.set('log_channel_id', str(chat.id))
                    await safe_send(context.bot, user_id, get_text(lang, 'admin_log_channel_set', channel=chat.title))
                else:
                    await safe_send(context.bot, user_id, get_text(lang, 'admin_log_channel_not_channel'))
            except:
                await safe_send(context.bot, user_id, get_text(lang, 'admin_log_channel_failed'))
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_MAX_LEN:
            try:
                val = int(text)
                if val >= 0:
                    chat_id_sec = context.user_data.get('sec_chat')
                    if chat_id_sec:
                        await SecurityRepository.set(chat_id_sec, max_message_length=val)
                    await safe_send(context.bot, user_id, f"✅ تم تعيين {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ يجب أن يكون 0 أو أكبر")
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_WARN_COUNT:
            try:
                val = int(text)
                if 1 <= val <= 10:
                    chat_id_sec = context.user_data.get('sec_chat')
                    if chat_id_sec:
                        await SecurityRepository.set(chat_id_sec, max_warnings=val)
                    await safe_send(context.bot, user_id, get_text(lang, 'warning_count_updated', count=val))
                else:
                    await safe_send(context.bot, user_id, "❌ بين 1 و 10")
            except:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        # الدعم (تذكرة) مع دعم الوسائط
        if state == UserState.SUPPORT_MODE:
            media_type = None
            media_file_id = None
            if msg.photo:
                media_type = 'photo'
                media_file_id = msg.photo[-1].file_id
            elif msg.video:
                media_type = 'video'
                media_file_id = msg.video.file_id
            elif msg.document:
                media_type = 'document'
                media_file_id = msg.document.file_id
            elif msg.audio:
                media_type = 'audio'
                media_file_id = msg.audio.file_id
            elif msg.voice:
                media_type = 'voice'
                media_file_id = msg.voice.file_id
            elif msg.animation:
                media_type = 'animation'
                media_file_id = msg.animation.file_id
            elif msg.text:
                media_type = 'text'
            else:
                await safe_send(context.bot, user_id, "⚠️ نوع الملف غير مدعوم")
                return
            content = msg.caption or "" if media_type != 'text' else text
            if not content and not media_file_id:
                await safe_send(context.bot, user_id, "❌ أرسل نصاً أو وسيطاً")
                return
            ticket_num = await TicketRepository.get_next_number() + 1
            await SettingRepository.set('last_ticket_number', str(ticket_num))
            await TicketRepository.save(user_id, update.effective_user.username or "", content, ticket_num, media_type, media_file_id)
            await safe_send(context.bot, user_id, get_text(lang, 'support_ticket_created', num=ticket_num))
            admins = await DB.fetchall("SELECT user_id FROM bot_admins")
            for admin_id, in admins:
                try:
                    await safe_send(context.bot, admin_id,
                                    f"📞 تذكرة جديدة #{ticket_num} من `{user_id}`\n{content[:100]}...")
                except:
                    pass
            StateManager.clear(user_id)
            return

        # ردود تلقائية في المجموعات
        if text and update.effective_chat and update.effective_chat.type in ['group', 'supergroup']:
            chat_id_grp = update.effective_chat.id
            ars = await AutoReplyRepository.get_settings(chat_id_grp)
            if ars.get('enabled'):
                can_reply = True
                if ars.get('only_admins'):
                    can_reply = await is_authorized_in_group(context.bot, chat_id_grp, user_id)
                if ars.get('ignore_bots') and update.effective_user.is_bot:
                    can_reply = False
                if can_reply:
                    reply_data = await AutoReplyRepository.get_reply(text.lower(), chat_id_grp)
                    if reply_data:
                        try:
                            if reply_data['type'] == 'text':
                                await update.message.reply_text(reply_data['reply'])
                            elif reply_data['type'] == 'photo' and reply_data['media_id']:
                                await update.message.reply_photo(reply_data['media_id'], caption=reply_data['reply'])
                            elif reply_data['type'] == 'video' and reply_data['media_id']:
                                await update.message.reply_video(reply_data['media_id'], caption=reply_data['reply'])
                            elif reply_data['type'] == 'document' and reply_data['media_id']:
                                await update.message.reply_document(reply_data['media_id'], caption=reply_data['reply'])
                            if reply_data['buttons']:
                                kb = InlineKeyboardMarkup(reply_data['buttons'])
                                await update.message.reply_text("", reply_markup=kb)
                        except:
                            pass
            if len(text) > 3:
                try:
                    res = SENTIMENT.analyze(text)
                    await save_sentiment(user_id, chat_id_grp, text, res['sentiment'], res['score'])
                except:
                    pass

        # الحالة غير المعروفة
        await CommandHandlers.start(update, context)

# =====================================================================
# 18. نظام العقوبات
# =====================================================================
class PenaltyFactory:
    @staticmethod
    def get_strategy(penalty_type: str):
        if penalty_type == 'ban':
            return BanPenalty()
        elif penalty_type == 'mute':
            return MutePenalty()
        elif penalty_type == 'kick':
            return KickPenalty()
        elif penalty_type == 'warn':
            return WarnPenalty()
        elif penalty_type == 'restrict':
            return RestrictPenalty()
        elif penalty_type == 'unban':
            return UnbanPenalty()
        return WarnPenalty()

class PenaltyStrategy(ABC):
    @abstractmethod
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        pass

class BanPenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        if user_id == bot.id:
            return False, "لا يمكن حظر البوت"
        try:
            await bot.ban_chat_member(chat_id, user_id)
            return True, "✅ تم الحظر"
        except Exception as e:
            return False, str(e)[:100]

class MutePenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        if user_id == bot.id:
            return False, "لا يمكن كتم البوت"
        duration = kwargs.get('duration', 60)
        until = TimeUtils.utc_now() + timedelta(minutes=duration) if duration else None
        try:
            await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False), until_date=until)
            return True, f"✅ تم الكتم {duration} دقيقة"
        except Exception as e:
            return False, str(e)[:100]

class KickPenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        if user_id == bot.id:
            return False, "لا يمكن طرد البوت"
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
            return True, "✅ تم الطرد"
        except Exception as e:
            return False, str(e)[:100]

class WarnPenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        if user_id == bot.id:
            return False, "لا يمكن تحذير البوت"
        async def _warn():
            row = await DB.fetchone("SELECT warnings FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            w = (row[0] if row else 0) + 1
            await DB.execute("INSERT OR REPLACE INTO user_warnings (user_id, chat_id, warnings) VALUES (?,?,?)", (user_id, chat_id, w))
            return w
        w = await _warn()
        settings = await SecurityRepository.get(chat_id)
        if w >= settings.get('max_warnings', 3):
            wp = settings.get('warn_penalty', 'ban')
            if wp == 'ban':
                await bot.ban_chat_member(chat_id, user_id)
            elif wp == 'mute':
                await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False))
            return True, f"⚠️ تجاوز الحد ({w}) → {wp}"
        return True, f"⚠️ تحذير {w}/{settings.get('max_warnings', 3)}"

class RestrictPenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        if user_id == bot.id:
            return False, "لا يمكن تقييد البوت"
        try:
            await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=True, can_send_media_messages=False))
            return True, "✅ تم التقييد"
        except Exception as e:
            return False, str(e)[:100]

class UnbanPenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        try:
            await bot.unban_chat_member(chat_id, user_id)
            return True, "✅ تم إلغاء الحظر"
        except Exception as e:
            return False, str(e)[:100]

async def apply_penalty(bot, chat_id: int, user_id: int, penalty: str, duration: int = 0, reason: str = "", moderator: int = None) -> Tuple[bool, str]:
    if user_id == CONFIG.PRIMARY_OWNER_ID:
        return False, "لا يمكن معاملة المالك"
    if user_id == bot.id:
        return False, "لا يمكن معاملة البوت"
    perms = await check_bot_permissions(bot, chat_id)
    if not perms['can_act']:
        return False, "الصلاحيات غير كافية"
    strategy = PenaltyFactory.get_strategy(penalty)
    return await strategy.apply(bot, chat_id, user_id, duration=duration, reason=reason)

# =====================================================================
# 19. المهام الخلفية
# =====================================================================
class BackgroundTasks:
    @staticmethod
    async def auto_publish(bot) -> None:
        await asyncio.sleep(10)
        while True:
            try:
                rows = await DB.fetchall("""
                    SELECT uc.id, uc.channel_id, p.id, p.text, p.media_type, p.media_file_id
                    FROM user_channels uc
                    JOIN users u ON uc.user_id = u.user_id
                    LEFT JOIN schedule s ON uc.id = s.channel_db_id
                    JOIN posts p ON uc.id = p.channel_db_id
                    WHERE u.auto_publish = 1 AND u.banned = 0 AND uc.banned = 0
                    AND p.published = 0 AND (p.fail_count IS NULL OR p.fail_count < 3)
                    AND (s.next_publish_date IS NULL OR s.next_publish_date <= ?)
                    ORDER BY COALESCE(s.next_publish_date, '1970-01-01') ASC
                    LIMIT ?
                """, (TimeUtils.utc_iso(), CONFIG.MAX_CHANNELS_PER_CYCLE))
                for ch_db_id, ch_tele, post_id, text, media_type, media_file_id in rows:
                    try:
                        if media_type == 'photo' and media_file_id:
                            await bot.send_photo(ch_tele, media_file_id, caption=text[:1024] if text else None)
                        elif media_type == 'video' and media_file_id:
                            await bot.send_video(ch_tele, media_file_id, caption=text[:1024] if text else None)
                        elif media_type == 'document' and media_file_id:
                            await bot.send_document(ch_tele, media_file_id, caption=text[:1024] if text else None)
                        else:
                            await bot.send_message(ch_tele, text[:4096] if text else ".")
                        await PostRepository.mark_published(post_id)
                        await ScheduleRepository.set_last_publish(ch_db_id, TimeUtils.utc_now())
                        await ScheduleRepository.update_next(ch_db_id)
                    except Exception as e:
                        await PostRepository.increment_fail(post_id)
                        logger.warning(f"Publish fail for post {post_id}: {e}")
                await asyncio.sleep(max(60, await SettingRepository.get_publish_interval()))
            except Exception as e:
                logger.error(f"Auto publish error: {e}")
                await asyncio.sleep(60)

    @staticmethod
    async def auto_backup() -> None:
        while True:
            await asyncio.sleep(86400)
            try:
                if await SettingRepository.get_auto_backup():
                    backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                    shutil.copy2(PATHS.DB, backup_file)
                    await SettingRepository.set('last_backup', TimeUtils.utc_iso())
                    backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
                    for old in backups[CONFIG.MAX_BACKUPS:]:
                        old.unlink()
            except Exception as e:
                logger.error(f"Auto backup error: {e}")

    @staticmethod
    async def reminders(bot) -> None:
        while True:
            await asyncio.sleep(3600)
            try:
                for u in await ReminderRepository.get_users_needing_reminder():
                    try:
                        lang = u.get('lang', 'ar')
                        days = u['days_left']
                        text = get_text(lang, 'reminder_subscription_expires', days=days)
                        await bot.send_message(u['user_id'], text)
                    except:
                        pass
            except Exception as e:
                logger.error(f"Reminders error: {e}")

    @staticmethod
    async def cleanup() -> None:
        while True:
            await asyncio.sleep(86400)
            try:
                old_date = (TimeUtils.utc_now() - timedelta(days=90)).isoformat()
                await DB.execute("DELETE FROM sentiment_history WHERE created_at < ?", (old_date,))
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    @staticmethod
    async def reset_warnings_daily() -> None:
        while True:
            await asyncio.sleep(86400)
            try:
                await DB.execute("DELETE FROM user_warnings")
            except Exception as e:
                logger.error(f"Reset warnings error: {e}")

    @staticmethod
    async def memory_monitor() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                ram = get_ram_usage()
                if ram['percent'] > 80:
                    gc.collect()
            except:
                pass

    @staticmethod
    async def heartbeat(bot) -> None:
        while True:
            await asyncio.sleep(CONFIG.HEARTBEAT_INTERVAL)
            try:
                log_channel = await SettingRepository.get_log_channel_id()
                ram = get_ram_usage()
                msg = get_text('ar', 'heartbeat_status', time=TimeUtils.mecca_iso(), ram=ram['percent'])
                if log_channel:
                    await bot.send_message(log_channel, msg)
                else:
                    await bot.send_message(CONFIG.PRIMARY_OWNER_ID, msg)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    @staticmethod
    async def self_ping() -> None:
        if not CONFIG.ENABLE_SELF_PING:
            return
        while True:
            await asyncio.sleep(CONFIG.HEARTBEAT_INTERVAL)
            try:
                async with aiohttp.ClientSession() as session:
                    await session.get(f"http://127.0.0.1:{CONFIG.WEB_PORT}/health", timeout=5)
            except Exception as e:
                logger.warning(f"Self-ping failed: {e}")

    @staticmethod
    async def flush_sentiment_periodically() -> None:
        while True:
            await asyncio.sleep(60)
            await _flush_sentiment_buffer()

# =====================================================================
# 20. خادم الصحة HTTP
# =====================================================================
async def health_check(request):
    return web.Response(text="OK", status=200)

async def run_health_server():
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host='0.0.0.0', port=CONFIG.WEB_PORT)
    await site.start()
    logger.info(f"✅ Health check server running on port {CONFIG.WEB_PORT}")
    await asyncio.Event().wait()

# =====================================================================
# 21. معالجات الأحداث
# =====================================================================
async def track_chat_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = update.my_chat_member
    if not result:
        return
    if result.new_chat_member.status in ['member', 'administrator']:
        chat = result.chat
        if chat.type in ['group', 'supergroup']:
            await GroupRepository.register(chat.id, chat.title or "", result.from_user.id, chat.username)
            await GroupRepository.sync_admins(chat.id, context.bot)

async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.new_chat_members:
        return
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        return
    settings = await SecurityRepository.get(chat.id)
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue
        if settings.get('welcome_enabled'):
            try:
                welcome_text = settings.get('welcome_text', "مرحباً {user} في {chat} 🤍")
                text = welcome_text.format(user=member.full_name or member.first_name, chat=chat.title)
                await context.bot.send_message(chat.id, text)
            except:
                pass

async def left_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.left_chat_member:
        return
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        return
    settings = await SecurityRepository.get(chat.id)
    member = update.message.left_chat_member
    if settings.get('goodbye_enabled'):
        try:
            goodbye_text = settings.get('goodbye_text', "وداعاً {user} 👋")
            text = goodbye_text.format(user=member.full_name or member.first_name)
            await context.bot.send_message(chat.id, text)
        except:
            pass

# =====================================================================
# 22. معالجات الدفع
# =====================================================================
async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await update.pre_checkout_query.answer(ok=True)
    except:
        pass

async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    payload = update.message.successful_payment.invoice_payload
    lang = await UserRepository.get_language(user_id)
    success = await PaymentService.handle_successful_payment(user_id, payload)
    if success:
        await safe_send(context.bot, user_id, get_text(lang, 'payment_success', plan="الباقة", days=""))
    else:
        await safe_send(context.bot, user_id, get_text(lang, 'payment_failed'))
async def setup_unified_web_server(application, port: int):
    from aiohttp import web
    from telegram import Update

    # ✅ المفتاح: ننشئ تطبيق ويب مستقل (لا نعتمد على application.web_app)
    web_app = web.Application()

    async def health(request):
        return web.Response(text="OK")

    async def index(request):
        return web.Response(
            text="<h1>🌿 ريلاكس مانيجر</h1><p>✅ يعمل</p>",
            content_type="text/html",
            charset="utf-8"
        )

    async def webhook(request):
        try:
            data = await request.json()
            # معالجة التحديث باستخدام application الحالي
            await application.process_update(Update.de_json(data, application.bot))
            return web.Response(status=200, text="OK")
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            # نعيد 200 دائماً حتى لا يعيد تيليجرام محاولة الإرسال
            return web.Response(status=200, text="OK")

    # تسجيل المسارات (انتبه: نستخدم f"/{TOKEN}" وليس "/webhook")
    web_app.router.add_get('/', index)
    web_app.router.add_get('/health', health)
    web_app.router.add_post(f'/{TOKEN}', webhook)

    # تشغيل الخادم
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info(f"✅ خادم ويب على {port}")

# =====================================================================
# 23. الدالة الرئيسية
# =====================================================================
async def main():
    logger.info(f"🚀 Starting {CONFIG.BOT_NAME} v5.0.5-ultimate")
    await DB.initialize()
    await UserRepository.register(CONFIG.PRIMARY_OWNER_ID)
    await BotAdminRepository.add(CONFIG.PRIMARY_OWNER_ID)

    if CONFIG.USE_PROXY:
        request = HTTPXRequest(proxy_url=CONFIG.PROXY_URL, read_timeout=60, write_timeout=30, connect_timeout=30, connection_pool_size=CONFIG.MAX_CONNECTIONS)
    else:
        request = HTTPXRequest(read_timeout=60, write_timeout=30, connect_timeout=30, connection_pool_size=CONFIG.MAX_CONNECTIONS)

    app = Application.builder().token(CONFIG.TOKEN).request(request).build()

    # إضافة المعالجات
    app.add_handler(CommandHandler("start", CommandHandlers.start))
    app.add_handler(CommandHandler("help", CommandHandlers.help_command))
    app.add_handler(CommandHandler("syncgroup", CommandHandlers.syncgroup))
    app.add_handler(CommandHandler("security", CommandHandlers.security))
    app.add_handler(CommandHandler("panel", CommandHandlers.panel))
    app.add_handler(CommandHandler("lock", CommandHandlers.lock))
    app.add_handler(CommandHandler("unlock", CommandHandlers.unlock))
    app.add_handler(CommandHandler("stats", CommandHandlers.stats))
    app.add_handler(CommandHandler("contests", CommandHandlers.contests))
    app.add_handler(CommandHandler("support", CommandHandlers.support))
    app.add_handler(CommandHandler("trial", CommandHandlers.trial))
    app.add_handler(CommandHandler("subscribe", CommandHandlers.subscribe))
    app.add_handler(CommandHandler("developer", CommandHandlers.developer))
    app.add_handler(CommandHandler("language", CommandHandlers.language))
    app.add_handler(CommandHandler("add_hidden_admin", CommandHandlers.add_hidden_admin))
    app.add_handler(CommandHandler("remove_hidden_admin", CommandHandlers.remove_hidden_admin))
    app.add_handler(CommandHandler("list_hidden_admins", CommandHandlers.list_hidden_admins))

    for cmd in ["ban", "mute", "warn", "kick", "restrict", "unban", "pin"]:
        app.add_handler(CommandHandler(cmd, lambda u, c, cmd=cmd: CommandHandlers.moderation(u, c, cmd)))

    app.add_handler(CallbackQueryHandler(CallbackHandlers.handle))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, MessageHandlers.handle))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, MessageHandlers.handle), group=1)

    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    app.add_handler(ChatJoinRequestHandler(lambda u, c: u.chat_join_request.approve()))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_chat_member_handler))
    app.add_handler(ChatMemberHandler(track_chat_add, ChatMemberHandler.MY_CHAT_MEMBER))

    try:
        await app.bot.set_my_commands([
            BotCommand("start", "الرئيسية"),
            BotCommand("help", "مساعدة"),
            BotCommand("syncgroup", "تفعيل مجموعة"),
            BotCommand("security", "الأمان"),
            BotCommand("panel", "لوحة تحكم"),
            BotCommand("lock", "قفل"),
            BotCommand("unlock", "فتح"),
            BotCommand("ban", "حظر"),
            BotCommand("mute", "كتم"),
            BotCommand("warn", "تحذير"),
            BotCommand("stats", "إحصائيات"),
            BotCommand("contests", "مسابقات"),
            BotCommand("support", "دعم"),
            BotCommand("subscribe", "اشتراك"),
            BotCommand("trial", "تجربة"),
        ])
    except Exception as e:
        logger.warning(f"Failed to set commands: {e}")

    # تشغيل خادم الصحة
    asyncio.create_task(run_health_server())

    # المهام الخلفية
    tasks = [
        asyncio.create_task(BackgroundTasks.auto_publish(app.bot)),
        asyncio.create_task(BackgroundTasks.auto_backup()),
        asyncio.create_task(BackgroundTasks.reminders(app.bot)),
        asyncio.create_task(BackgroundTasks.cleanup()),
        asyncio.create_task(BackgroundTasks.reset_warnings_daily()),
        asyncio.create_task(BackgroundTasks.memory_monitor()),
        asyncio.create_task(BackgroundTasks.heartbeat(app.bot)),
        asyncio.create_task(BackgroundTasks.self_ping()),
        asyncio.create_task(flush_usage_periodically()),
        asyncio.create_task(BackgroundTasks.flush_sentiment_periodically()),
    ]

    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("HEROKU_APP_NAME")
    if hostname:
        await app.initialize()
        await app.start()
        await app.bot.set_webhook(url=f"https://{hostname}/{CONFIG.TOKEN}", drop_pending_updates=True)
        logger.info(f"✅ Webhook set on https://{hostname}/{CONFIG.TOKEN}")
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    else:
        try:
            await app.run_polling(drop_pending_updates=True)
        except KeyboardInterrupt:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

# =====================================================================
# 24. تشغيل البرنامج
# =====================================================================
if __name__ == "__main__":
    print(f"🌿 {CONFIG.BOT_NAME} v5.0.5-ultimate - @RelaxMgr")
    print("✅ Ultimate Edition with all improvements and fixes")
    print("📊 Auto-reply cache: 200 replies | Usage batch updates: 50 operations")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 تم الإيقاف")
    except Exception as e:
        print(f"❌ {e}")
        traceback.print_exc()
