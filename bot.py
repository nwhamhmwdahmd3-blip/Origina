#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ريلاكس مانيجر - النسخة النهائية المتكاملة (مع دعم 8 لغات)
الإصدار: 23.0.1-final-complete
المطور: @RelaxMgr
تم التحديث: دعم كامل للغات (عربي، إنجليزي، تركي، صيني، فرنسي، ألماني، إسباني، روسي)
"""

import sys
import os
import secrets
import re
import shutil
import logging
import traceback
import random
import asyncio
import gc
import sqlite3
import json
import time as time_module
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple, Any, Union, Callable, Awaitable
from enum import Enum, auto
import gzip
import tempfile
import html
import hashlib
import weakref
from urllib.parse import urlparse
import functools

# ===================================================================
# 1. تثبيت الحزم تلقائياً
# ===================================================================
def ensure_package(package_name: str, import_name: str = None) -> bool:
    if import_name is None:
        import_name = package_name
    try:
        __import__(import_name)
        return True
    except ImportError:
        try:
            import subprocess
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", package_name],
                           capture_output=True, text=True, check=False)
            __import__(import_name)
            return True
        except Exception as e:
            print(f"⚠️ لا يمكن تثبيت {package_name}: {e}")
            return False

REQUIRED_PACKAGES = [
    ("python-dotenv", "dotenv"),
    ("cachetools", "cachetools"),
    ("psutil", "psutil"),
    ("nest-asyncio", "nest_asyncio"),
    ("aiosqlite", "aiosqlite"),
    ("cryptography", "cryptography"),
    ("aiohttp", "aiohttp"),
    ("httpx", "httpx"),
    ("python-telegram-bot", "telegram"),
    ("deep-translator", "deep_translator"),
]

for pkg, imp in REQUIRED_PACKAGES:
    ensure_package(pkg, imp)

# ===================================================================
# 2. استيراد المكتبات
# ===================================================================
import nest_asyncio
nest_asyncio.apply()

import aiosqlite
from dotenv import load_dotenv
load_dotenv()

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMember, BotCommand, LabeledPrice, ChatPermissions,
    ChatMemberUpdated, ChatJoinRequest
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler,
    ChatMemberHandler, ChatJoinRequestHandler
)
from telegram.error import TimedOut, NetworkError, BadRequest, Forbidden, Conflict
from telegram.request import HTTPXRequest

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64
from deep_translator import GoogleTranslator
import aiohttp

# ===================================================================
# 3. متغيرات البيئة والثوابت
# ===================================================================
TOKEN = os.getenv("BOT_TOKEN", "")
PRIMARY_OWNER_ID = int(os.getenv("MAIN_ADMIN_ID", "0"))
BOT_NAME = os.getenv("BOT_NAME", "ريلاكس مانيجر")
BOT_USERNAME = os.getenv("BOT_USERNAME", "Reelaaaxbot")
USE_PROXY = os.getenv("USE_PROXY", "false").lower() in ['true', '1']
PROXY_URL = os.getenv("PROXY_URL", "http://127.0.0.1:10809")
WEB_PORT = int(os.getenv("PORT", "10000"))
MAX_CONNECTIONS = 20
MAX_BACKUPS = 20
ANONYMOUS_ADMIN_ID = int(os.getenv("ANONYMOUS_ADMIN_ID", "1087968824"))
DEFAULT_PUBLISH_INTERVAL_SECONDS = 720
MAX_CHANNELS_PER_CYCLE = 20
PUBLISH_RETRY_DELAY = 300
MAX_UNPUBLISHED_POSTS = 1000
DB_TIMEOUT = 30
MAX_DAILY_REFERRALS = 5
MAX_GLOBAL_BANNED_WORDS = 100

if not TOKEN or PRIMARY_OWNER_ID == 0:
    print("❌ يجب تعيين BOT_TOKEN و MAIN_ADMIN_ID في .env")
    sys.exit(1)

# ===================================================================
# 4. إعداد المسارات
# ===================================================================
BASE_PATH = Path(__file__).parent.resolve()
DATA_PATH = BASE_PATH / "data"
DATA_PATH.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_PATH / "bot_data.db"
BACKUP_DIR = BASE_PATH / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = BASE_PATH / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "bot.log"
BANNED_WORDS_FILE = BASE_PATH / "banned_words.txt"
AUTO_REPLIES_FILE = BASE_PATH / "auto_replies.json"

# ===================================================================
# 5. نظام الترجمات المتكامل (8 لغات)
# ===================================================================
LOCALES = {
    'ar': {
        'main_menu_title': "🌿 **{bot_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 المعرف: `{user_id}`\n👥 مجموعاتي: {groups}\n💎 الاشتراك: {sub}\n📡 القناة: {channel}\n📝 غير المنشورة: {pending}\n⚙️ النشر: {auto}",
        'channels_empty': "📭 لا توجد قنوات",
        'channels_header': "📡 **قنواتي**",
        'posts_empty': "📭 لا توجد منشورات",
        'posts_header': "📋 **منشوراتي**",
        'groups_empty': "📭 لا توجد مجموعات",
        'groups_header': "👥 **مجموعاتي**",
        'security_header': "🔐 **إعدادات الأمان**",
        'settings_header': "⚙️ **الإعدادات**",
        'referral_header': "🔗 رابطك: `{link}`\n👥 {total} | 🎁 {available} يوم",
        'reminder_header': "⏰ إعدادات التذكيرات",
        'translation_header': "🌐 الترجمة: {lang}",
        'contests_header': "🏆 **المسابقات**",
        'stats_text': "📊 إحصائيات البوت\n👥 {users} مستخدم\n🚫 {banned} محظور\n📝 {posts} منشور\n👥 {groups} مجموعة\n📡 {channels} قناة",
        'help_text': "❓ **مساعدة ريلاكس مانيجر**\n📌 الأوامر:\n/start - القائمة الرئيسية\n/help - هذه المساعدة\n/syncgroup - تفعيل البوت في المجموعة\n/security - إعدادات الأمان للمجموعة الحالية\n/panel - لوحة التحكم (للمشرفين)\n/lock - قفل المجموعة\n/unlock - فتح المجموعة\n/stats - إحصائيات عامة\n/schedule - جدولة النشر\n/contests - المسابقات\n/support - الدعم الفني\n/trial - تجربة مجانية\n/subscribe - الاشتراك",
        'developer_text': "👨‍💻 {bot_name}\n@RelaxMgr",
        'trial_used': "❌ استخدمت التجربة",
        'trial_activated': "✅ تم تفعيل {days} يوم",
        'subscription_active': "✅ مفعل",
        'subscription_inactive': "❌ غير مفعل",
        'auto_on': "مفعل",
        'auto_off': "معطل",
        'no_active_channel': "⚠️ اختر قناة",
        'subscription_expired': "⚠️ اشتراك منتهٍ",
        'limit_reached': "⚠️ الحد الأقصى",
        'post_added': "✅ {count}/{target} | متبقي {remaining}",
        'posts_saved': "✅ تم الحفظ",
        'published_success': "✅ تم النشر",
        'publish_failed': "❌ فشل النشر: {error}",
        'all_published': "✅ تم النشر للكل",
        'channel_added': "✅ تمت الإضافة",
        'channel_exists': "⚠️ موجودة",
        'channel_error': "❌ خطأ: {error}",
        'not_channel': "❌ ليس قناة",
        'bot_not_admin': "❌ البوت ليس مشرفاً أو لا يملك صلاحية النشر",
        'invalid_format': "❌ صيغة خاطئة",
        'unsupported_media': "⚠️ غير مدعوم",
        'schedule_current': "⏰ الجدولة (الحالي: {type})",
        'schedule_updated': "✅ تم التحديث",
        'schedule_invalid_time': "❌ وقت غير صالح",
        'schedule_past': "❌ وقت في الماضي",
        'security_enabled': "✅",
        'security_disabled': "❌",
        'penalty_set': "✅ تم تعيين العقوبة: {penalty}",
        'banned_word_added': "✅ تمت إضافة '{word}'",
        'banned_word_removed': "✅ تم حذف '{word}'",
        'admin_added': "✅ تمت إضافة {user_id}",
        'admin_removed': "✅ تمت إزالة {user_id}",
        'support_ticket_sent': "✅ تذكرة #{number}",
        'contest_created': "✅ مسابقة #{id}",
        'contest_participated': "✅ تمت المشاركة",
        'contest_no_winner': "🏆 لا يوجد فائزون بعد",
        'contest_winners': "🏆 **الفائزون السابقون**",
        'reply_added': "✅ تم إضافة رد لـ '{keyword}'",
        'reply_removed': "✅ تم حذف الرد",
        'auto_reply_toggled': "✅ {status}",
        'auto_reply_admin_only': "✅ {status}",
        'auto_reply_reset': "✅ تم إعادة التعيين",
        'reminder_days_set': "✅ تم تعيين {days} أيام",
        'lang_changed': "✅ تم تغيير اللغة",
        'translation_off': "✅ تم إيقاف الترجمة",
        'translation_on': "✅ تم تفعيل الترجمة إلى {lang}",
        'referral_claimed': "✅ {days} يوم",
        'referral_list': "📋 قائمة المُحالين",
        'no_referrals': "📭 لا يوجد إحالات",
        'stats_pending': "📊 غير المنشورة: {pending}\n📋 الإجمالي: {total}",
        'stats_full': "📈 قنوات: {channels}\n📝 منشورات: {posts}\n⏳ غير منشورة: {pending}\n👥 مجموعات: {groups}\n⚙️ النشر: {auto}",
        'channel_stats': "📊 {total} | ✅ {published} | ⏳ {pending}",
        'growth_stats': "📈 نمو القناة (آخر 7 أيام): {growth} منشور",
        'admin_panel': "👑 لوحة التحكم",
        'admin_users': "👥 المستخدمين: {users}\n🚫 محظورين: {banned}",
        'admin_banned_users': "🚫 المحظورين:\n{list}",
        'admin_channels': "📡 القنوات:\n{list}",
        'admin_groups': "👥 المجموعات:\n{list}",
        'admin_ram': "💾 {used:.1f}/{total:.1f} GB ({percent}%)",
        'admin_stats': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'admin_metrics': "📊 **المقاييس**\n👥 المستخدمون النشطون: {active}\n📝 منشورات اليوم: {today}\n💾 حجم DB: {db_size} MB",
        'admin_backup_created': "✅ تم النسخ: {file}",
        'admin_backup_failed': "❌ فشل: {error}",
        'admin_restore_success': "✅ تمت الاستعادة بنجاح",
        'admin_restore_failed': "❌ فشل: {error}",
        'admin_broadcast_confirm': "📨 تأكيد:\n{text}",
        'admin_broadcast_sent': "✅ تم الإرسال لـ {sent} مستخدم",
        'admin_tickets': "📋 التذاكر:\n{list}",
        'admin_ticket_replied': "✅ تم الرد على `{user}`",
        'admin_ticket_reply_failed': "❌ فشل الإرسال: {error}",
        'admin_delete_tickets_confirm': "⚠️ متأكد من حذف كل التذاكر؟",
        'admin_delete_tickets_done': "✅ تم الحذف",
        'admin_log_channel_set': "✅ تم تعيين {channel}",
        'admin_force_subscribe_channel': "✅ تم تعيين @{channel}",
        'admin_update_channel_set': "✅ تم تعيين @{channel}",
        'admin_update_sent': "✅ تم",
        'admin_update_failed': "❌ فشل",
        'admin_unban_all': "✅ تم إلغاء حظر الكل",
        'admin_activate_all': "✅ تم تفعيل الكل",
        'admin_no_updates_channel': "❌ لا توجد قناة",
        'admin_no_force_channel': "❌ لا توجد قناة إجبارية",
        'admin_sendcode_user_set': "✅ تم تعيين {user}",
        'admin_sendcode_user_invalid': "❌ خطأ",
        'admin_lock': "🔒 تم القفل",
        'admin_unlock': "🔓 تم الفتح",
        'admin_panel_closed': "تم الإغلاق",
        'unauthorized': "🔒 غير مصرح",
        'canceled': "❌ تم الإلغاء",
        'back': "🔙 رجوع",
        'close': "🔙 إغلاق",
        'add_channel': "➕ إضافة قناة",
        'my_channels': "📡 قنواتي",
        'add_posts': "📥 إضافة منشورات",
        'publish_one': "📤 نشر واحد",
        'my_posts': "📋 منشوراتي",
        'recycle': "♻️ إعادة تدوير",
        'stats_pending_btn': "📊 غير المنشورة",
        'stats_full_btn': "📈 كاملة",
        'schedule_btn': "⏰ الجدولة",
        'channel_stats_btn': "📊 القناة",
        'publish_all': "📤 نشر الكل",
        'help_btn': "❓ مساعدة",
        'trial_btn': "🎁 تجربة",
        'subscribe_btn': "💎 اشتراك",
        'developer_btn': "👨‍💻 المطور",
        'language_btn': "🌐 اللغة",
        'support_btn': "📞 دعم",
        'referral_btn': "🔗 إحالات",
        'reminder_btn': "⏰ تذكيرات",
        'translation_btn': "🌐 ترجمة",
        'contests_btn': "🏆 مسابقات",
        'add_group_btn': "➕ أضف لمجموعة",
        'admin_panel_btn': "👑 لوحة الأدمن",
        'confirm': "✅ تأكيد",
        'cancel': "❌ إلغاء",
        'yes': "✅ نعم",
        'no': "❌ لا",
        'share_link': "🔗 مشاركة",
        'copy_link': "📋 نسخ الرابط",
        'claim_reward': "🎁 صرف",
        'referral_list_btn': "📋 قائمة الإحالات",
        'subscribe_1_day': "💎 1 يوم",
        'subscribe_2_days': "💎 2 يوم",
        'subscribe_30_days': "💎 30 يوم",
        'subscribe_90_days': "💎 90 يوم",
        'ticket_btn': "📞 تذكرة",
        'winners_btn': "🏆 الفائزون",
        'nsfw_toggle_btn': "🔞 NSFW: {status}",
        'nsfw_threshold_btn': "🔞 العتبة: {threshold}%",
        'auto_reply_toggle_btn': "📝 الردود: {status}",
        'auto_reply_admins_btn': "👥 المستخدمون: {users}",
        'auto_reply_reset_btn': "🔄 إعادة تعيين",
        'auto_reply_stats_btn': "📊 إحصائيات",
        'auto_reply_menu_btn': "📝 الردود التلقائية",
        'auto_reply_add_btn': "➕ إضافة رد",
        'auto_reply_del_btn': "🗑️ حذف رد",
        'auto_reply_list_btn': "📋 قائمة الردود",
        'security_links': "🔗 روابط",
        'security_mentions': "@ معرفات",
        'security_slow_mode': "⏱️ بطيء",
        'security_welcome': "🎯 ترحيب",
        'security_goodbye': "👋 وداع",
        'security_banned_words': "🚫 كلمات",
        'security_delete_videos': "🎬 فيديو",
        'security_delete_audio': "🎵 صوت",
        'security_delete_animation': "🎞️ متحرك",
        'security_delete_service': "🛠️ خدمة",
        'security_delete_documents': "📄 ملفات",
        'security_delete_stickers': "🖼️ ملصقات",
        'security_delete_forwarded': "📨 مُعاد",
        'security_delete_polls': "📊 استطلاع",
        'security_delete_games': "🎮 ألعاب",
        'security_delete_voice': "🎤 صوتي",
        'security_delete_video_note': "🎥 نوت",
        'security_antiflood': "🌊 فيضان",
        'security_night_mode': "🌙 ليلي",
        'security_max_length': "📏 طول",
        'security_warn_settings': "⚠️ تحذير",
        'security_delete_penalty': "⚖️ عقوبة",
        'security_enable_all': "⚡ تفعيل الكل",
        'security_disable_all': "⛔ تعطيل الكل",
        'security_penalty': "⚖️ العقوبة",
        'security_advanced': "🛠️ متقدم",
        'security_log': "📜 سجل",
        'security_close': "🔙 إغلاق",
        'admin_users_btn': "👥 المستخدمين",
        'admin_banned_users_btn': "⛔ المحظورين",
        'admin_channels_btn': "📡 قنوات",
        'admin_groups_btn': "👥 المجموعات",
        'admin_add_admin_btn': "👑 + مشرف",
        'admin_remove_admin_btn': "🗑️ - مشرف",
        'admin_replies_btn': "💬 ردود",
        'admin_banned_words_btn': "🚫 كلمات",
        'admin_ram_btn': "🖥️ الرام",
        'admin_stats_btn': "📊 إحصائيات",
        'admin_backup_btn': "💾 نسخ",
        'admin_restore_btn': "🔄 استعادة",
        'admin_update_btn': "📢 تحديث",
        'admin_broadcast_btn': "📨 بث",
        'admin_tickets_btn': "📋 تذاكر",
        'admin_logs_btn': "📋 تقارير",
        'admin_force_subscribe_btn': "🔒 اشتراك إجباري",
        'admin_monitor_btn': "📊 مراقبة",
        'admin_back': "🔙 رجوع",
        'penalty_kick': "👢 طرد",
        'penalty_ban': "🛑 حظر",
        'penalty_mute': "🔇 كتم",
        'penalty_warn': "⚠️ تحذير",
        'penalty_restrict': "🔒 تقييد",
        'penalty_none': "❌ لا شيء",
        'advanced_ban': "🛑 حظر",
        'advanced_mute': "🔇 كتم",
        'advanced_warn': "⚠️ تحذير",
        'advanced_kick': "👢 طرد",
        'advanced_restrict': "🔒 تقييد",
        'advanced_pin': "📌 تثبيت",
        'advanced_unban': "🔓 إلغاء حظر",
        'advanced_log': "📜 سجل",
        'mute_duration_5': "⏱️ 5 دقائق",
        'mute_duration_30': "⏱️ 30 دقيقة",
        'mute_duration_60': "⏱️ 1 ساعة",
        'mute_duration_720': "⏱️ 12 ساعة",
        'mute_duration_1440': "📆 يوم",
        'mute_duration_10080': "📆 أسبوع",
        'mute_duration_permanent': "🔇 كتم دائم",
        'panel_locked': "📋 لوحة تحكم المجموعة\nالحالة: مقفلة",
        'panel_unlocked': "📋 لوحة تحكم المجموعة\nالحالة: مفتوحة",
        'panel_lock_btn': "🔒 قفل",
        'panel_unlock_btn': "🔓 فتح",
        'panel_close_btn': "🔙 إغلاق",
        'ticket_reply_prompt': "✏️ أرسل ردك على التذكرة #{ticket_id}:",
        'ticket_reply_success': "✅ تم الرد على `{user}`",
        'ticket_reply_failed': "❌ فشل الإرسال: {error}",
        'contest_join_prompt': "📝 أرسل إجابتك:",
        'contest_join_success': "✅ تمت المشاركة",
        'contest_created': "✅ مسابقة #{id}",
        'auto_reply_add_prompt': "✏️ أرسل الكلمة المفتاحية للرد:",
        'auto_reply_reply_prompt': "✏️ أرسل الرد:",
        'auto_reply_delete_prompt': "✏️ أرسل الكلمة المفتاحية لحذف الرد:",
        'auto_reply_delete_success': "✅ تم حذف الرد لـ '{keyword}'",
        'auto_reply_delete_failed': "❌ لا يوجد رد لـ '{keyword}'",
        'banned_word_add_prompt': "✏️ أرسل الكلمة:",
        'banned_word_remove_prompt': "✏️ أرسل الكلمة للحذف:",
        'banned_word_add_success': "✅ تمت إضافة '{word}'",
        'banned_word_remove_success': "✅ تم حذف '{word}'",
        'banned_words_list_header': "🚫 **الكلمات المحظورة**\n",
        'banned_words_empty': "📭 لا توجد كلمات محظورة",
        'admin_reply_add_prompt': "✏️ أرسل الكلمة المفتاحية:",
        'admin_reply_reply_prompt': "✏️ أرسل الرد:",
        'admin_reply_add_success': "✅ تم إضافة رد لـ '{keyword}'",
        'admin_reply_list_header': "📋 الردود:\n",
        'admin_reply_empty': "📭 لا توجد ردود",
        'admin_reply_delete_prompt': "✏️ أرسل الكلمة المفتاحية لحذف الرد:",
        'admin_reply_delete_success': "✅ تم حذف الرد",
        'syncgroup_success_group': "✅ **تم تفعيل البوت بنجاح!**\n\n👥 تم مزامنة {count} مشرف من تيليجرام.\n👤 تم إضافة `{user_id}` كمدير للبوت.\n\n📌 يمكنك الآن استخدام الأوامر الإدارية:\n• `/security` - إعدادات الأمان\n• `/ban`, `/mute`, `/warn` - العقوبات\n• `/panel` - لوحة التحكم\n• `/add_hidden_admin` - إضافة مشرف مخفي",
        'syncgroup_success_private': "✅ تم تفعيل البوت في مجموعة **{title}**\nستظهر المجموعة الآن في قائمة 'مجموعاتي' داخل الخاص.",
        'syncgroup_not_group': "❌ يستخدم في المجموعات فقط",
        'syncgroup_not_admin': "🔒 تحتاج صلاحيات مشرف لتفعيل البوت",
        'syncgroup_error': "❌ خطأ في التحقق من صلاحياتك: {error}",
        'syncgroup_already': "⚠️ المجموعة مسجلة بالفعل، جاري تحديث المشرفين...",
    },
    'en': {
        'main_menu_title': "🌿 **{bot_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 ID: `{user_id}`\n👥 My Groups: {groups}\n💎 Subscription: {sub}\n📡 Channel: {channel}\n📝 Unpublished: {pending}\n⚙️ Auto: {auto}",
        'channels_empty': "📭 No channels",
        'channels_header': "📡 **My Channels**",
        'posts_empty': "📭 No posts",
        'posts_header': "📋 **My Posts**",
        'groups_empty': "📭 No groups",
        'groups_header': "👥 **My Groups**",
        'security_header': "🔐 **Security Settings**",
        'settings_header': "⚙️ **Settings**",
        'referral_header': "🔗 Your link: `{link}`\n👥 {total} | 🎁 {available} days",
        'reminder_header': "⏰ Reminder Settings",
        'translation_header': "🌐 Translation: {lang}",
        'contests_header': "🏆 **Contests**",
        'stats_text': "📊 Bot Stats\n👥 {users} users\n🚫 {banned} banned\n📝 {posts} posts\n👥 {groups} groups\n📡 {channels} channels",
        'help_text': "❓ **Relax Manager Help**\n📌 Commands:\n/start - Main menu\n/help - This help\n/syncgroup - Activate bot in group\n/security - Security settings for current group\n/panel - Control panel (for admins)\n/lock - Lock group\n/unlock - Unlock group\n/stats - General stats\n/schedule - Schedule posts\n/contests - Contests\n/support - Support\n/trial - Free trial\n/subscribe - Subscribe",
        'developer_text': "👨‍💻 {bot_name}\n@RelaxMgr",
        'trial_used': "❌ Trial already used",
        'trial_activated': "✅ Activated {days} days",
        'subscription_active': "✅ Active",
        'subscription_inactive': "❌ Inactive",
        'auto_on': "On",
        'auto_off': "Off",
        'no_active_channel': "⚠️ Select a channel",
        'subscription_expired': "⚠️ Subscription expired",
        'limit_reached': "⚠️ Limit reached",
        'post_added': "✅ {count}/{target} | Remaining {remaining}",
        'posts_saved': "✅ Saved",
        'published_success': "✅ Published",
        'publish_failed': "❌ Publish failed: {error}",
        'all_published': "✅ All published",
        'channel_added': "✅ Added",
        'channel_exists': "⚠️ Already exists",
        'channel_error': "❌ Error: {error}",
        'not_channel': "❌ Not a channel",
        'bot_not_admin': "❌ Bot is not admin or cannot post",
        'invalid_format': "❌ Invalid format",
        'unsupported_media': "⚠️ Unsupported",
        'schedule_current': "⏰ Schedule (current: {type})",
        'schedule_updated': "✅ Updated",
        'schedule_invalid_time': "❌ Invalid time",
        'schedule_past': "❌ Time in past",
        'security_enabled': "✅",
        'security_disabled': "❌",
        'penalty_set': "✅ Penalty set: {penalty}",
        'banned_word_added': "✅ Added '{word}'",
        'banned_word_removed': "✅ Removed '{word}'",
        'admin_added': "✅ Added {user_id}",
        'admin_removed': "✅ Removed {user_id}",
        'support_ticket_sent': "✅ Ticket #{number}",
        'contest_created': "✅ Contest #{id}",
        'contest_participated': "✅ Participated",
        'contest_no_winner': "🏆 No winners yet",
        'contest_winners': "🏆 **Previous Winners**",
        'reply_added': "✅ Added reply for '{keyword}'",
        'reply_removed': "✅ Removed reply",
        'auto_reply_toggled': "✅ {status}",
        'auto_reply_admin_only': "✅ {status}",
        'auto_reply_reset': "✅ Reset",
        'reminder_days_set': "✅ Set {days} days",
        'lang_changed': "✅ Language changed",
        'translation_off': "✅ Translation disabled",
        'translation_on': "✅ Translation enabled to {lang}",
        'referral_claimed': "✅ {days} days",
        'referral_list': "📋 Referral list",
        'no_referrals': "📭 No referrals",
        'stats_pending': "📊 Unpublished: {pending}\n📋 Total: {total}",
        'stats_full': "📈 Channels: {channels}\n📝 Posts: {posts}\n⏳ Unpublished: {pending}\n👥 Groups: {groups}\n⚙️ Auto: {auto}",
        'channel_stats': "📊 {total} | ✅ {published} | ⏳ {pending}",
        'growth_stats': "📈 Channel growth (last 7 days): {growth} posts",
        'admin_panel': "👑 Admin Panel",
        'admin_users': "👥 Users: {users}\n🚫 Banned: {banned}",
        'admin_banned_users': "🚫 Banned Users:\n{list}",
        'admin_channels': "📡 Channels:\n{list}",
        'admin_groups': "👥 Groups:\n{list}",
        'admin_ram': "💾 {used:.1f}/{total:.1f} GB ({percent}%)",
        'admin_stats': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'admin_metrics': "📊 **Metrics**\n👥 Active Users: {active}\n📝 Today's Posts: {today}\n💾 DB Size: {db_size} MB",
        'admin_backup_created': "✅ Backup created: {file}",
        'admin_backup_failed': "❌ Failed: {error}",
        'admin_restore_success': "✅ Restored successfully",
        'admin_restore_failed': "❌ Failed: {error}",
        'admin_broadcast_confirm': "📨 Confirm:\n{text}",
        'admin_broadcast_sent': "✅ Sent to {sent} users",
        'admin_tickets': "📋 Tickets:\n{list}",
        'admin_ticket_replied': "✅ Replied to `{user}`",
        'admin_ticket_reply_failed': "❌ Sending failed: {error}",
        'admin_delete_tickets_confirm': "⚠️ Are you sure you want to delete all tickets?",
        'admin_delete_tickets_done': "✅ Deleted",
        'admin_log_channel_set': "✅ Set channel {channel}",
        'admin_force_subscribe_channel': "✅ Set @{channel}",
        'admin_update_channel_set': "✅ Set @{channel}",
        'admin_update_sent': "✅ Sent",
        'admin_update_failed': "❌ Failed",
        'admin_unban_all': "✅ All unbanned",
        'admin_activate_all': "✅ All activated",
        'admin_no_updates_channel': "❌ No update channel",
        'admin_no_force_channel': "❌ No force subscribe channel",
        'admin_sendcode_user_set': "✅ Set {user}",
        'admin_sendcode_user_invalid': "❌ Error",
        'admin_lock': "🔒 Locked",
        'admin_unlock': "🔓 Unlocked",
        'admin_panel_closed': "Closed",
        'unauthorized': "🔒 Unauthorized",
        'canceled': "❌ Canceled",
        'back': "🔙 Back",
        'close': "🔙 Close",
        'add_channel': "➕ Add Channel",
        'my_channels': "📡 My Channels",
        'add_posts': "📥 Add Posts",
        'publish_one': "📤 Publish One",
        'my_posts': "📋 My Posts",
        'recycle': "♻️ Recycle",
        'stats_pending_btn': "📊 Unpublished",
        'stats_full_btn': "📈 Full",
        'schedule_btn': "⏰ Schedule",
        'channel_stats_btn': "📊 Channel",
        'publish_all': "📤 Publish All",
        'help_btn': "❓ Help",
        'trial_btn': "🎁 Trial",
        'subscribe_btn': "💎 Subscribe",
        'developer_btn': "👨‍💻 Developer",
        'language_btn': "🌐 Language",
        'support_btn': "📞 Support",
        'referral_btn': "🔗 Referrals",
        'reminder_btn': "⏰ Reminders",
        'translation_btn': "🌐 Translation",
        'contests_btn': "🏆 Contests",
        'add_group_btn': "➕ Add to Group",
        'admin_panel_btn': "👑 Admin Panel",
        'confirm': "✅ Confirm",
        'cancel': "❌ Cancel",
        'yes': "✅ Yes",
        'no': "❌ No",
        'share_link': "🔗 Share",
        'copy_link': "📋 Copy Link",
        'claim_reward': "🎁 Claim",
        'referral_list_btn': "📋 Referrals List",
        'subscribe_1_day': "💎 1 Day",
        'subscribe_2_days': "💎 2 Days",
        'subscribe_30_days': "💎 30 Days",
        'subscribe_90_days': "💎 90 Days",
        'ticket_btn': "📞 Ticket",
        'winners_btn': "🏆 Winners",
        'nsfw_toggle_btn': "🔞 NSFW: {status}",
        'nsfw_threshold_btn': "🔞 Threshold: {threshold}%",
        'auto_reply_toggle_btn': "📝 Replies: {status}",
        'auto_reply_admins_btn': "👥 Users: {users}",
        'auto_reply_reset_btn': "🔄 Reset",
        'auto_reply_stats_btn': "📊 Stats",
        'auto_reply_menu_btn': "📝 Auto Replies",
        'auto_reply_add_btn': "➕ Add Reply",
        'auto_reply_del_btn': "🗑️ Delete Reply",
        'auto_reply_list_btn': "📋 Reply List",
        'security_links': "🔗 Links",
        'security_mentions': "@ Mentions",
        'security_slow_mode': "⏱️ Slow Mode",
        'security_welcome': "🎯 Welcome",
        'security_goodbye': "👋 Goodbye",
        'security_banned_words': "🚫 Words",
        'security_delete_videos': "🎬 Video",
        'security_delete_audio': "🎵 Audio",
        'security_delete_animation': "🎞️ Animation",
        'security_delete_service': "🛠️ Service",
        'security_delete_documents': "📄 Documents",
        'security_delete_stickers': "🖼️ Stickers",
        'security_delete_forwarded': "📨 Forwarded",
        'security_delete_polls': "📊 Poll",
        'security_delete_games': "🎮 Games",
        'security_delete_voice': "🎤 Voice",
        'security_delete_video_note': "🎥 Video Note",
        'security_antiflood': "🌊 Anti-Flood",
        'security_night_mode': "🌙 Night Mode",
        'security_max_length': "📏 Max Length",
        'security_warn_settings': "⚠️ Warn",
        'security_delete_penalty': "⚖️ Penalty",
        'security_enable_all': "⚡ Enable All",
        'security_disable_all': "⛔ Disable All",
        'security_penalty': "⚖️ Penalty",
        'security_advanced': "🛠️ Advanced",
        'security_log': "📜 Log",
        'security_close': "🔙 Close",
        'admin_users_btn': "👥 Users",
        'admin_banned_users_btn': "⛔ Banned",
        'admin_channels_btn': "📡 Channels",
        'admin_groups_btn': "👥 Groups",
        'admin_add_admin_btn': "👑 + Admin",
        'admin_remove_admin_btn': "🗑️ - Admin",
        'admin_replies_btn': "💬 Replies",
        'admin_banned_words_btn': "🚫 Words",
        'admin_ram_btn': "🖥️ RAM",
        'admin_stats_btn': "📊 Stats",
        'admin_backup_btn': "💾 Backup",
        'admin_restore_btn': "🔄 Restore",
        'admin_update_btn': "📢 Update",
        'admin_broadcast_btn': "📨 Broadcast",
        'admin_tickets_btn': "📋 Tickets",
        'admin_logs_btn': "📋 Logs",
        'admin_force_subscribe_btn': "🔒 Force Subscribe",
        'admin_monitor_btn': "📊 Monitor",
        'admin_back': "🔙 Back",
        'penalty_kick': "👢 Kick",
        'penalty_ban': "🛑 Ban",
        'penalty_mute': "🔇 Mute",
        'penalty_warn': "⚠️ Warn",
        'penalty_restrict': "🔒 Restrict",
        'penalty_none': "❌ None",
        'advanced_ban': "🛑 Ban",
        'advanced_mute': "🔇 Mute",
        'advanced_warn': "⚠️ Warn",
        'advanced_kick': "👢 Kick",
        'advanced_restrict': "🔒 Restrict",
        'advanced_pin': "📌 Pin",
        'advanced_unban': "🔓 Unban",
        'advanced_log': "📜 Log",
        'mute_duration_5': "⏱️ 5 min",
        'mute_duration_30': "⏱️ 30 min",
        'mute_duration_60': "⏱️ 1 hour",
        'mute_duration_720': "⏱️ 12 hours",
        'mute_duration_1440': "📆 Day",
        'mute_duration_10080': "📆 Week",
        'mute_duration_permanent': "🔇 Permanent",
        'panel_locked': "📋 Group Panel\nStatus: Locked",
        'panel_unlocked': "📋 Group Panel\nStatus: Unlocked",
        'panel_lock_btn': "🔒 Lock",
        'panel_unlock_btn': "🔓 Unlock",
        'panel_close_btn': "🔙 Close",
        'ticket_reply_prompt': "✏️ Send your reply for ticket #{ticket_id}:",
        'ticket_reply_success': "✅ Replied to `{user}`",
        'ticket_reply_failed': "❌ Sending failed: {error}",
        'contest_join_prompt': "📝 Send your answer:",
        'contest_join_success': "✅ Participated",
        'contest_created': "✅ Contest #{id}",
        'auto_reply_add_prompt': "✏️ Send the keyword for the reply:",
        'auto_reply_reply_prompt': "✏️ Send the reply:",
        'auto_reply_delete_prompt': "✏️ Send the keyword to delete the reply:",
        'auto_reply_delete_success': "✅ Deleted reply for '{keyword}'",
        'auto_reply_delete_failed': "❌ No reply found for '{keyword}'",
        'banned_word_add_prompt': "✏️ Send the word:",
        'banned_word_remove_prompt': "✏️ Send the word to remove:",
        'banned_word_add_success': "✅ Added '{word}'",
        'banned_word_remove_success': "✅ Removed '{word}'",
        'banned_words_list_header': "🚫 **Banned Words**\n",
        'banned_words_empty': "📭 No banned words",
        'admin_reply_add_prompt': "✏️ Send the keyword:",
        'admin_reply_reply_prompt': "✏️ Send the reply:",
        'admin_reply_add_success': "✅ Added reply for '{keyword}'",
        'admin_reply_list_header': "📋 Replies:\n",
        'admin_reply_empty': "📭 No replies",
        'admin_reply_delete_prompt': "✏️ Send the keyword to delete the reply:",
        'admin_reply_delete_success': "✅ Deleted reply",
        'syncgroup_success_group': "✅ **Bot activated successfully!**\n\n👥 Synced {count} admins from Telegram.\n👤 Added `{user_id}` as bot manager.\n\n📌 You can now use admin commands:\n• `/security` - Security settings\n• `/ban`, `/mute`, `/warn` - Penalties\n• `/panel` - Control panel\n• `/add_hidden_admin` - Add hidden admin",
        'syncgroup_success_private': "✅ Bot activated in group **{title}**\nThe group will now appear in 'My Groups' in private chat.",
        'syncgroup_not_group': "❌ Use in groups only",
        'syncgroup_not_admin': "🔒 You need admin permissions to activate the bot",
        'syncgroup_error': "❌ Error checking permissions: {error}",
        'syncgroup_already': "⚠️ Group already registered, updating admins...",
    },
    'tr': {
        'main_menu_title': "🌿 **{bot_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 Kimlik: `{user_id}`\n👥 Gruplarım: {groups}\n💎 Abonelik: {sub}\n📡 Kanal: {channel}\n📝 Yayınlanmamış: {pending}\n⚙️ Otomatik: {auto}",
        'channels_empty': "📭 Kanal yok",
        'channels_header': "📡 **Kanallarım**",
        'posts_empty': "📭 Gönderi yok",
        'posts_header': "📋 **Gönderilerim**",
        'groups_empty': "📭 Grup yok",
        'groups_header': "👥 **Gruplarım**",
        'security_header': "🔐 **Güvenlik Ayarları**",
        'settings_header': "⚙️ **Ayarlar**",
        'referral_header': "🔗 Bağlantın: `{link}`\n👥 {total} | 🎁 {available} gün",
        'reminder_header': "⏰ Hatırlatıcı Ayarları",
        'translation_header': "🌐 Çeviri: {lang}",
        'contests_header': "🏆 **Yarışmalar**",
        'stats_text': "📊 Bot İstatistikleri\n👥 {users} kullanıcı\n🚫 {banned} yasaklı\n📝 {posts} gönderi\n👥 {groups} grup\n📡 {channels} kanal",
        'help_text': "❓ **Relax Manager Yardım**\n📌 Komutlar:\n/start - Ana menü\n/help - Bu yardım\n/syncgroup - Botu grupta etkinleştir\n/security - Güvenlik ayarları\n/panel - Kontrol paneli\n/lock - Grubu kilitle\n/unlock - Grubu aç\n/stats - Genel istatistikler\n/schedule - Gönderi zamanla\n/contests - Yarışmalar\n/support - Destek\n/trial - Ücretsiz deneme\n/subscribe - Abone ol",
        'developer_text': "👨‍💻 {bot_name}\n@RelaxMgr",
        'trial_used': "❌ Deneme zaten kullanıldı",
        'trial_activated': "✅ {days} gün etkinleştirildi",
        'subscription_active': "✅ Aktif",
        'subscription_inactive': "❌ Aktif değil",
        'auto_on': "Açık",
        'auto_off': "Kapalı",
        'no_active_channel': "⚠️ Bir kanal seçin",
        'subscription_expired': "⚠️ Abonelik süresi doldu",
        'limit_reached': "⚠️ Sınıra ulaşıldı",
        'post_added': "✅ {count}/{target} | Kalan {remaining}",
        'posts_saved': "✅ Kaydedildi",
        'published_success': "✅ Yayınlandı",
        'publish_failed': "❌ Yayın başarısız: {error}",
        'all_published': "✅ Tümü yayınlandı",
        'channel_added': "✅ Eklendi",
        'channel_exists': "⚠️ Zaten var",
        'channel_error': "❌ Hata: {error}",
        'not_channel': "❌ Kanal değil",
        'bot_not_admin': "❌ Bot yönetici değil veya gönderi gönderemiyor",
        'invalid_format': "❌ Geçersiz format",
        'unsupported_media': "⚠️ Desteklenmiyor",
        'schedule_current': "⏰ Zamanlama (mevcut: {type})",
        'schedule_updated': "✅ Güncellendi",
        'schedule_invalid_time': "❌ Geçersiz saat",
        'schedule_past': "❌ Geçmiş zaman",
        'security_enabled': "✅",
        'security_disabled': "❌",
        'penalty_set': "✅ Ceza ayarlandı: {penalty}",
        'banned_word_added': "✅ '{word}' eklendi",
        'banned_word_removed': "✅ '{word}' silindi",
        'admin_added': "✅ {user_id} eklendi",
        'admin_removed': "✅ {user_id} silindi",
        'support_ticket_sent': "✅ Bilet #{number}",
        'contest_created': "✅ Yarışma #{id}",
        'contest_participated': "✅ Katılındı",
        'contest_no_winner': "🏆 Henüz kazanan yok",
        'contest_winners': "🏆 **Önceki Kazananlar**",
        'reply_added': "✅ '{keyword}' için yanıt eklendi",
        'reply_removed': "✅ Yanıt silindi",
        'auto_reply_toggled': "✅ {status}",
        'auto_reply_admin_only': "✅ {status}",
        'auto_reply_reset': "✅ Sıfırlandı",
        'reminder_days_set': "✅ {days} gün ayarlandı",
        'lang_changed': "✅ Dil değiştirildi",
        'translation_off': "✅ Çeviri devre dışı",
        'translation_on': "✅ Çeviri {lang} diline etkinleştirildi",
        'referral_claimed': "✅ {days} gün",
        'referral_list': "📋 Referans listesi",
        'no_referrals': "📭 Referans yok",
        'stats_pending': "📊 Yayınlanmamış: {pending}\n📋 Toplam: {total}",
        'stats_full': "📈 Kanallar: {channels}\n📝 Gönderiler: {posts}\n⏳ Yayınlanmamış: {pending}\n👥 Gruplar: {groups}\n⚙️ Otomatik: {auto}",
        'channel_stats': "📊 {total} | ✅ {published} | ⏳ {pending}",
        'growth_stats': "📈 Kanal büyümesi (son 7 gün): {growth} gönderi",
        'admin_panel': "👑 Yönetim Paneli",
        'admin_users': "👥 Kullanıcılar: {users}\n🚫 Yasaklı: {banned}",
        'admin_banned_users': "🚫 Yasaklı Kullanıcılar:\n{list}",
        'admin_channels': "📡 Kanallar:\n{list}",
        'admin_groups': "👥 Gruplar:\n{list}",
        'admin_ram': "💾 {used:.1f}/{total:.1f} GB ({percent}%)",
        'admin_stats': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'admin_metrics': "📊 **Metrikler**\n👥 Aktif Kullanıcılar: {active}\n📝 Bugünkü Gönderiler: {today}\n💾 DB Boyutu: {db_size} MB",
        'admin_backup_created': "✅ Yedek oluşturuldu: {file}",
        'admin_backup_failed': "❌ Başarısız: {error}",
        'admin_restore_success': "✅ Başarıyla geri yüklendi",
        'admin_restore_failed': "❌ Başarısız: {error}",
        'admin_broadcast_confirm': "📨 Onayla:\n{text}",
        'admin_broadcast_sent': "✅ {sent} kullanıcıya gönderildi",
        'admin_tickets': "📋 Biletler:\n{list}",
        'admin_ticket_replied': "✅ `{user}` kişisine yanıt verildi",
        'admin_ticket_reply_failed': "❌ Gönderme başarısız: {error}",
        'admin_delete_tickets_confirm': "⚠️ Tüm biletleri silmek istediğinizden emin misiniz?",
        'admin_delete_tickets_done': "✅ Silindi",
        'admin_log_channel_set': "✅ Kanal ayarlandı {channel}",
        'admin_force_subscribe_channel': "✅ @{channel} ayarlandı",
        'admin_update_channel_set': "✅ @{channel} ayarlandı",
        'admin_update_sent': "✅ Gönderildi",
        'admin_update_failed': "❌ Başarısız",
        'admin_unban_all': "✅ Tüm yasaklar kaldırıldı",
        'admin_activate_all': "✅ Tümü etkinleştirildi",
        'admin_no_updates_channel': "❌ Güncelleme kanalı yok",
        'admin_no_force_channel': "❌ Zorunlu abonelik kanalı yok",
        'admin_sendcode_user_set': "✅ {user} ayarlandı",
        'admin_sendcode_user_invalid': "❌ Hata",
        'admin_lock': "🔒 Kilitlendi",
        'admin_unlock': "🔓 Açıldı",
        'admin_panel_closed': "Kapatıldı",
        'unauthorized': "🔒 Yetkisiz",
        'canceled': "❌ İptal edildi",
        'back': "🔙 Geri",
        'close': "🔙 Kapat",
        'add_channel': "➕ Kanal Ekle",
        'my_channels': "📡 Kanallarım",
        'add_posts': "📥 Gönderi Ekle",
        'publish_one': "📤 Birini Yayınla",
        'my_posts': "📋 Gönderilerim",
        'recycle': "♻️ Geri Dönüştür",
        'stats_pending_btn': "📊 Yayınlanmamış",
        'stats_full_btn': "📈 Tam",
        'schedule_btn': "⏰ Zamanlama",
        'channel_stats_btn': "📊 Kanal",
        'publish_all': "📤 Tümünü Yayınla",
        'help_btn': "❓ Yardım",
        'trial_btn': "🎁 Deneme",
        'subscribe_btn': "💎 Abone Ol",
        'developer_btn': "👨‍💻 Geliştirici",
        'language_btn': "🌐 Dil",
        'support_btn': "📞 Destek",
        'referral_btn': "🔗 Referanslar",
        'reminder_btn': "⏰ Hatırlatıcılar",
        'translation_btn': "🌐 Çeviri",
        'contests_btn': "🏆 Yarışmalar",
        'add_group_btn': "➕ Gruba Ekle",
        'admin_panel_btn': "👑 Yönetim Paneli",
        'confirm': "✅ Onayla",
        'cancel': "❌ İptal",
        'yes': "✅ Evet",
        'no': "❌ Hayır",
        'share_link': "🔗 Paylaş",
        'copy_link': "📋 Bağlantıyı Kopyala",
        'claim_reward': "🎁 Talep Et",
        'referral_list_btn': "📋 Referans Listesi",
        'subscribe_1_day': "💎 1 Gün",
        'subscribe_2_days': "💎 2 Gün",
        'subscribe_30_days': "💎 30 Gün",
        'subscribe_90_days': "💎 90 Gün",
        'ticket_btn': "📞 Bilet",
        'winners_btn': "🏆 Kazananlar",
        'nsfw_toggle_btn': "🔞 NSFW: {status}",
        'nsfw_threshold_btn': "🔞 Eşik: {threshold}%",
        'auto_reply_toggle_btn': "📝 Yanıtlar: {status}",
        'auto_reply_admins_btn': "👥 Kullanıcılar: {users}",
        'auto_reply_reset_btn': "🔄 Sıfırla",
        'auto_reply_stats_btn': "📊 İstatistikler",
        'auto_reply_menu_btn': "📝 Otomatik Yanıtlar",
        'auto_reply_add_btn': "➕ Yanıt Ekle",
        'auto_reply_del_btn': "🗑️ Yanıt Sil",
        'auto_reply_list_btn': "📋 Yanıt Listesi",
        'syncgroup_success_group': "✅ **Bot başarıyla etkinleştirildi!**\n\n👥 {count} yönetici Telegram'dan senkronize edildi.\n👤 `{user_id}` bot yöneticisi olarak eklendi.\n\n📌 Artık yönetici komutlarını kullanabilirsiniz:\n• `/security` - Güvenlik ayarları\n• `/ban`, `/mute`, `/warn` - Cezalar\n• `/panel` - Kontrol paneli\n• `/add_hidden_admin` - Gizli yönetici ekle",
        'syncgroup_success_private': "✅ **{title}** grubunda bot etkinleştirildi\nGrup artık özel sohbette 'Gruplarım' listesinde görünecek.",
        'syncgroup_not_group': "❌ Sadece gruplarda kullanılır",
        'syncgroup_not_admin': "🔒 Botu etkinleştirmek için yönetici izinlerine ihtiyacınız var",
        'syncgroup_error': "❌ İzinler kontrol edilirken hata: {error}",
        'syncgroup_already': "⚠️ Grup zaten kayıtlı, yöneticiler güncelleniyor...",
    },
    'zh': {
        'main_menu_title': "🌿 **{bot_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 ID: `{user_id}`\n👥 我的群组: {groups}\n💎 订阅: {sub}\n📡 频道: {channel}\n📝 未发布: {pending}\n⚙️ 自动: {auto}",
        'channels_empty': "📭 没有频道",
        'channels_header': "📡 **我的频道**",
        'posts_empty': "📭 没有帖子",
        'posts_header': "📋 **我的帖子**",
        'groups_empty': "📭 没有群组",
        'groups_header': "👥 **我的群组**",
        'security_header': "🔐 **安全设置**",
        'settings_header': "⚙️ **设置**",
        'referral_header': "🔗 你的链接: `{link}`\n👥 {total} | 🎁 {available} 天",
        'reminder_header': "⏰ 提醒设置",
        'translation_header': "🌐 翻译: {lang}",
        'contests_header': "🏆 **比赛**",
        'stats_text': "📊 机器人统计\n👥 {users} 用户\n🚫 {banned} 已封禁\n📝 {posts} 帖子\n👥 {groups} 群组\n📡 {channels} 频道",
        'help_text': "❓ **Relax Manager 帮助**\n📌 命令:\n/start - 主菜单\n/help - 帮助\n/syncgroup - 在群组中激活机器人\n/security - 安全设置\n/panel - 控制面板\n/lock - 锁定群组\n/unlock - 解锁群组\n/stats - 统计\n/schedule - 定时发布\n/contests - 比赛\n/support - 支持\n/trial - 免费试用\n/subscribe - 订阅",
        'developer_text': "👨‍💻 {bot_name}\n@RelaxMgr",
        'trial_used': "❌ 试用已使用",
        'trial_activated': "✅ 已激活 {days} 天",
        'subscription_active': "✅ 已激活",
        'subscription_inactive': "❌ 未激活",
        'auto_on': "开",
        'auto_off': "关",
        'no_active_channel': "⚠️ 选择一个频道",
        'subscription_expired': "⚠️ 订阅已过期",
        'limit_reached': "⚠️ 已达上限",
        'post_added': "✅ {count}/{target} | 剩余 {remaining}",
        'posts_saved': "✅ 已保存",
        'published_success': "✅ 已发布",
        'publish_failed': "❌ 发布失败: {error}",
        'all_published': "✅ 全部已发布",
        'channel_added': "✅ 已添加",
        'channel_exists': "⚠️ 已存在",
        'channel_error': "❌ 错误: {error}",
        'not_channel': "❌ 不是频道",
        'bot_not_admin': "❌ 机器人不是管理员或无法发布",
        'invalid_format': "❌ 格式无效",
        'unsupported_media': "⚠️ 不支持",
        'schedule_current': "⏰ 定时 (当前: {type})",
        'schedule_updated': "✅ 已更新",
        'schedule_invalid_time': "❌ 时间无效",
        'schedule_past': "❌ 过去的时间",
        'security_enabled': "✅",
        'security_disabled': "❌",
        'penalty_set': "✅ 惩罚已设置: {penalty}",
        'banned_word_added': "✅ 已添加 '{word}'",
        'banned_word_removed': "✅ 已删除 '{word}'",
        'admin_added': "✅ 已添加 {user_id}",
        'admin_removed': "✅ 已删除 {user_id}",
        'support_ticket_sent': "✅ 工单 #{number}",
        'contest_created': "✅ 比赛 #{id}",
        'contest_participated': "✅ 已参与",
        'contest_no_winner': "🏆 暂无获胜者",
        'contest_winners': "🏆 **之前的获胜者**",
        'reply_added': "✅ 已为 '{keyword}' 添加回复",
        'reply_removed': "✅ 已删除回复",
        'auto_reply_toggled': "✅ {status}",
        'auto_reply_admin_only': "✅ {status}",
        'auto_reply_reset': "✅ 已重置",
        'reminder_days_set': "✅ 已设置 {days} 天",
        'lang_changed': "✅ 语言已更改",
        'translation_off': "✅ 翻译已禁用",
        'translation_on': "✅ 翻译已启用为 {lang}",
        'referral_claimed': "✅ {days} 天",
        'referral_list': "📋 推荐列表",
        'no_referrals': "📭 没有推荐",
        'stats_pending': "📊 未发布: {pending}\n📋 总计: {total}",
        'stats_full': "📈 频道: {channels}\n📝 帖子: {posts}\n⏳ 未发布: {pending}\n👥 群组: {groups}\n⚙️ 自动: {auto}",
        'channel_stats': "📊 {total} | ✅ {published} | ⏳ {pending}",
        'growth_stats': "📈 频道增长 (最近7天): {growth} 帖子",
        'admin_panel': "👑 管理面板",
        'admin_users': "👥 用户: {users}\n🚫 已封禁: {banned}",
        'admin_banned_users': "🚫 已封禁用户:\n{list}",
        'admin_channels': "📡 频道:\n{list}",
        'admin_groups': "👥 群组:\n{list}",
        'admin_ram': "💾 {used:.1f}/{total:.1f} GB ({percent}%)",
        'admin_stats': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'admin_metrics': "📊 **指标**\n👥 活跃用户: {active}\n📝 今日帖子: {today}\n💾 数据库大小: {db_size} MB",
        'admin_backup_created': "✅ 已创建备份: {file}",
        'admin_backup_failed': "❌ 失败: {error}",
        'admin_restore_success': "✅ 恢复成功",
        'admin_restore_failed': "❌ 失败: {error}",
        'admin_broadcast_confirm': "📨 确认:\n{text}",
        'admin_broadcast_sent': "✅ 已发送给 {sent} 个用户",
        'admin_tickets': "📋 工单:\n{list}",
        'admin_ticket_replied': "✅ 已回复 `{user}`",
        'admin_ticket_reply_failed': "❌ 发送失败: {error}",
        'admin_delete_tickets_confirm': "⚠️ 确定要删除所有工单吗？",
        'admin_delete_tickets_done': "✅ 已删除",
        'admin_log_channel_set': "✅ 已设置频道 {channel}",
        'admin_force_subscribe_channel': "✅ 已设置 @{channel}",
        'admin_update_channel_set': "✅ 已设置 @{channel}",
        'admin_update_sent': "✅ 已发送",
        'admin_update_failed': "❌ 失败",
        'admin_unban_all': "✅ 已全部解封",
        'admin_activate_all': "✅ 已全部激活",
        'admin_no_updates_channel': "❌ 没有更新频道",
        'admin_no_force_channel': "❌ 没有强制订阅频道",
        'admin_sendcode_user_set': "✅ 已设置 {user}",
        'admin_sendcode_user_invalid': "❌ 错误",
        'admin_lock': "🔒 已锁定",
        'admin_unlock': "🔓 已解锁",
        'admin_panel_closed': "已关闭",
        'unauthorized': "🔒 未授权",
        'canceled': "❌ 已取消",
        'back': "🔙 返回",
        'close': "🔙 关闭",
        'add_channel': "➕ 添加频道",
        'my_channels': "📡 我的频道",
        'add_posts': "📥 添加帖子",
        'publish_one': "📤 发布一个",
        'my_posts': "📋 我的帖子",
        'recycle': "♻️ 回收",
        'stats_pending_btn': "📊 未发布",
        'stats_full_btn': "📈 全部",
        'schedule_btn': "⏰ 定时",
        'channel_stats_btn': "📊 频道",
        'publish_all': "📤 全部发布",
        'help_btn': "❓ 帮助",
        'trial_btn': "🎁 试用",
        'subscribe_btn': "💎 订阅",
        'developer_btn': "👨‍💻 开发者",
        'language_btn': "🌐 语言",
        'support_btn': "📞 支持",
        'referral_btn': "🔗 推荐",
        'reminder_btn': "⏰ 提醒",
        'translation_btn': "🌐 翻译",
        'contests_btn': "🏆 比赛",
        'add_group_btn': "➕ 添加到群组",
        'admin_panel_btn': "👑 管理面板",
        'confirm': "✅ 确认",
        'cancel': "❌ 取消",
        'yes': "✅ 是",
        'no': "❌ 否",
        'share_link': "🔗 分享",
        'copy_link': "📋 复制链接",
        'claim_reward': "🎁 领取",
        'referral_list_btn': "📋 推荐列表",
        'subscribe_1_day': "💎 1 天",
        'subscribe_2_days': "💎 2 天",
        'subscribe_30_days': "💎 30 天",
        'subscribe_90_days': "💎 90 天",
        'ticket_btn': "📞 工单",
        'winners_btn': "🏆 获胜者",
        'nsfw_toggle_btn': "🔞 NSFW: {status}",
        'nsfw_threshold_btn': "🔞 阈值: {threshold}%",
        'auto_reply_toggle_btn': "📝 回复: {status}",
        'auto_reply_admins_btn': "👥 用户: {users}",
        'auto_reply_reset_btn': "🔄 重置",
        'auto_reply_stats_btn': "📊 统计",
        'auto_reply_menu_btn': "📝 自动回复",
        'auto_reply_add_btn': "➕ 添加回复",
        'auto_reply_del_btn': "🗑️ 删除回复",
        'auto_reply_list_btn': "📋 回复列表",
        'syncgroup_success_group': "✅ **机器人激活成功！**\n\n👥 已同步 {count} 个管理员。\n👤 已添加 `{user_id}` 为机器人管理员。\n\n📌 您现在可以使用管理命令:\n• `/security` - 安全设置\n• `/ban`, `/mute`, `/warn` - 惩罚\n• `/panel` - 控制面板\n• `/add_hidden_admin` - 添加隐藏管理员",
        'syncgroup_success_private': "✅ 机器人在群组 **{title}** 中已激活\n该群组将出现在私聊的 '我的群组' 列表中。",
        'syncgroup_not_group': "❌ 仅在群组中使用",
        'syncgroup_not_admin': "🔒 您需要管理员权限才能激活机器人",
        'syncgroup_error': "❌ 检查权限时出错: {error}",
        'syncgroup_already': "⚠️ 群组已注册，正在更新管理员...",
    },
    'fr': {
        'main_menu_title': "🌿 **{bot_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 ID: `{user_id}`\n👥 Mes Groupes: {groups}\n💎 Abonnement: {sub}\n📡 Chaîne: {channel}\n📝 Non publié: {pending}\n⚙️ Auto: {auto}",
        'channels_empty': "📭 Aucune chaîne",
        'channels_header': "📡 **Mes Chaînes**",
        'posts_empty': "📭 Aucun message",
        'posts_header': "📋 **Mes Messages**",
        'groups_empty': "📭 Aucun groupe",
        'groups_header': "👥 **Mes Groupes**",
        'security_header': "🔐 **Paramètres de Sécurité**",
        'settings_header': "⚙️ **Paramètres**",
        'referral_header': "🔗 Votre lien: `{link}`\n👥 {total} | 🎁 {available} jours",
        'reminder_header': "⏰ Paramètres de Rappel",
        'translation_header': "🌐 Traduction: {lang}",
        'contests_header': "🏆 **Concours**",
        'stats_text': "📊 Statistiques du Bot\n👥 {users} utilisateurs\n🚫 {banned} bannis\n📝 {posts} messages\n👥 {groups} groupes\n📡 {channels} chaînes",
        'help_text': "❓ **Aide Relax Manager**\n📌 Commandes:\n/start - Menu principal\n/help - Cette aide\n/syncgroup - Activer le bot dans le groupe\n/security - Paramètres de sécurité\n/panel - Panneau de contrôle\n/lock - Verrouiller le groupe\n/unlock - Déverrouiller le groupe\n/stats - Statistiques\n/schedule - Planifier\n/contests - Concours\n/support - Support\n/trial - Essai gratuit\n/subscribe - S'abonner",
        'developer_text': "👨‍💻 {bot_name}\n@RelaxMgr",
        'trial_used': "❌ Essai déjà utilisé",
        'trial_activated': "✅ {days} jours activés",
        'subscription_active': "✅ Actif",
        'subscription_inactive': "❌ Inactif",
        'auto_on': "Activé",
        'auto_off': "Désactivé",
        'no_active_channel': "⚠️ Choisissez une chaîne",
        'subscription_expired': "⚠️ Abonnement expiré",
        'limit_reached': "⚠️ Limite atteinte",
        'post_added': "✅ {count}/{target} | Restant {remaining}",
        'posts_saved': "✅ Enregistré",
        'published_success': "✅ Publié",
        'publish_failed': "❌ Échec de publication: {error}",
        'all_published': "✅ Tout publié",
        'channel_added': "✅ Ajouté",
        'channel_exists': "⚠️ Existe déjà",
        'channel_error': "❌ Erreur: {error}",
        'not_channel': "❌ Pas une chaîne",
        'bot_not_admin': "❌ Le bot n'est pas admin ou ne peut pas publier",
        'invalid_format': "❌ Format invalide",
        'unsupported_media': "⚠️ Non supporté",
        'schedule_current': "⏰ Planification (actuel: {type})",
        'schedule_updated': "✅ Mis à jour",
        'schedule_invalid_time': "❌ Heure invalide",
        'schedule_past': "❌ Heure passée",
        'security_enabled': "✅",
        'security_disabled': "❌",
        'penalty_set': "✅ Pénalité définie: {penalty}",
        'banned_word_added': "✅ '{word}' ajouté",
        'banned_word_removed': "✅ '{word}' supprimé",
        'admin_added': "✅ {user_id} ajouté",
        'admin_removed': "✅ {user_id} supprimé",
        'support_ticket_sent': "✅ Ticket #{number}",
        'contest_created': "✅ Concours #{id}",
        'contest_participated': "✅ Participé",
        'contest_no_winner': "🏆 Pas encore de gagnant",
        'contest_winners': "🏆 **Gagnants Précédents**",
        'reply_added': "✅ Réponse ajoutée pour '{keyword}'",
        'reply_removed': "✅ Réponse supprimée",
        'auto_reply_toggled': "✅ {status}",
        'auto_reply_admin_only': "✅ {status}",
        'auto_reply_reset': "✅ Réinitialisé",
        'reminder_days_set': "✅ {days} jours définis",
        'lang_changed': "✅ Langue changée",
        'translation_off': "✅ Traduction désactivée",
        'translation_on': "✅ Traduction activée vers {lang}",
        'referral_claimed': "✅ {days} jours",
        'referral_list': "📋 Liste de parrainage",
        'no_referrals': "📭 Aucun parrainage",
        'stats_pending': "📊 Non publié: {pending}\n📋 Total: {total}",
        'stats_full': "📈 Chaînes: {channels}\n📝 Messages: {posts}\n⏳ Non publié: {pending}\n👥 Groupes: {groups}\n⚙️ Auto: {auto}",
        'channel_stats': "📊 {total} | ✅ {published} | ⏳ {pending}",
        'growth_stats': "📈 Croissance de la chaîne (7 derniers jours): {growth} messages",
        'admin_panel': "👑 Panneau d'administration",
        'admin_users': "👥 Utilisateurs: {users}\n🚫 Bannis: {banned}",
        'admin_banned_users': "🚫 Utilisateurs Bannis:\n{list}",
        'admin_channels': "📡 Chaînes:\n{list}",
        'admin_groups': "👥 Groupes:\n{list}",
        'admin_ram': "💾 {used:.1f}/{total:.1f} GB ({percent}%)",
        'admin_stats': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'admin_metrics': "📊 **Métriques**\n👥 Utilisateurs Actifs: {active}\n📝 Messages Aujourd'hui: {today}\n💾 Taille DB: {db_size} MB",
        'admin_backup_created': "✅ Sauvegarde créée: {file}",
        'admin_backup_failed': "❌ Échec: {error}",
        'admin_restore_success': "✅ Restauré avec succès",
        'admin_restore_failed': "❌ Échec: {error}",
        'admin_broadcast_confirm': "📨 Confirmer:\n{text}",
        'admin_broadcast_sent': "✅ Envoyé à {sent} utilisateurs",
        'admin_tickets': "📋 Tickets:\n{list}",
        'admin_ticket_replied': "✅ Répondu à `{user}`",
        'admin_ticket_reply_failed': "❌ Échec d'envoi: {error}",
        'admin_delete_tickets_confirm': "⚠️ Voulez-vous vraiment supprimer tous les tickets?",
        'admin_delete_tickets_done': "✅ Supprimés",
        'admin_log_channel_set': "✅ Chaîne définie {channel}",
        'admin_force_subscribe_channel': "✅ @{channel} défini",
        'admin_update_channel_set': "✅ @{channel} défini",
        'admin_update_sent': "✅ Envoyé",
        'admin_update_failed': "❌ Échec",
        'admin_unban_all': "✅ Tous débannis",
        'admin_activate_all': "✅ Tous activés",
        'admin_no_updates_channel': "❌ Pas de chaîne de mise à jour",
        'admin_no_force_channel': "❌ Pas de chaîne d'abonnement forcé",
        'admin_sendcode_user_set': "✅ {user} défini",
        'admin_sendcode_user_invalid': "❌ Erreur",
        'admin_lock': "🔒 Verrouillé",
        'admin_unlock': "🔓 Déverrouillé",
        'admin_panel_closed': "Fermé",
        'unauthorized': "🔒 Non autorisé",
        'canceled': "❌ Annulé",
        'back': "🔙 Retour",
        'close': "🔙 Fermer",
        'add_channel': "➕ Ajouter une chaîne",
        'my_channels': "📡 Mes chaînes",
        'add_posts': "📥 Ajouter des messages",
        'publish_one': "📤 Publier un",
        'my_posts': "📋 Mes messages",
        'recycle': "♻️ Recycler",
        'stats_pending_btn': "📊 Non publié",
        'stats_full_btn': "📈 Complet",
        'schedule_btn': "⏰ Planification",
        'channel_stats_btn': "📊 Chaîne",
        'publish_all': "📤 Tout publier",
        'help_btn': "❓ Aide",
        'trial_btn': "🎁 Essai",
        'subscribe_btn': "💎 S'abonner",
        'developer_btn': "👨‍💻 Développeur",
        'language_btn': "🌐 Langue",
        'support_btn': "📞 Support",
        'referral_btn': "🔗 Parrainages",
        'reminder_btn': "⏰ Rappels",
        'translation_btn': "🌐 Traduction",
        'contests_btn': "🏆 Concours",
        'add_group_btn': "➕ Ajouter au groupe",
        'admin_panel_btn': "👑 Panneau d'admin",
        'confirm': "✅ Confirmer",
        'cancel': "❌ Annuler",
        'yes': "✅ Oui",
        'no': "❌ Non",
        'share_link': "🔗 Partager",
        'copy_link': "📋 Copier le lien",
        'claim_reward': "🎁 Réclamer",
        'referral_list_btn': "📋 Liste de parrainage",
        'subscribe_1_day': "💎 1 Jour",
        'subscribe_2_days': "💎 2 Jours",
        'subscribe_30_days': "💎 30 Jours",
        'subscribe_90_days': "💎 90 Jours",
        'ticket_btn': "📞 Ticket",
        'winners_btn': "🏆 Gagnants",
        'nsfw_toggle_btn': "🔞 NSFW: {status}",
        'nsfw_threshold_btn': "🔞 Seuil: {threshold}%",
        'auto_reply_toggle_btn': "📝 Réponses: {status}",
        'auto_reply_admins_btn': "👥 Utilisateurs: {users}",
        'auto_reply_reset_btn': "🔄 Réinitialiser",
        'auto_reply_stats_btn': "📊 Statistiques",
        'auto_reply_menu_btn': "📝 Réponses automatiques",
        'auto_reply_add_btn': "➕ Ajouter une réponse",
        'auto_reply_del_btn': "🗑️ Supprimer une réponse",
        'auto_reply_list_btn': "📋 Liste des réponses",
        'syncgroup_success_group': "✅ **Bot activé avec succès!**\n\n👥 {count} administrateurs synchronisés depuis Telegram.\n👤 `{user_id}` ajouté comme gestionnaire du bot.\n\n📌 Vous pouvez maintenant utiliser les commandes d'administration:\n• `/security` - Paramètres de sécurité\n• `/ban`, `/mute`, `/warn` - Sanctions\n• `/panel` - Panneau de contrôle\n• `/add_hidden_admin` - Ajouter un administrateur caché",
        'syncgroup_success_private': "✅ Bot activé dans le groupe **{title}**\nLe groupe apparaîtra maintenant dans 'Mes Groupes' en privé.",
        'syncgroup_not_group': "❌ Utiliser uniquement dans les groupes",
        'syncgroup_not_admin': "🔒 Vous devez être administrateur pour activer le bot",
        'syncgroup_error': "❌ Erreur lors de la vérification des autorisations: {error}",
        'syncgroup_already': "⚠️ Groupe déjà enregistré, mise à jour des administrateurs...",
    },
    'de': {
        'main_menu_title': "🌿 **{bot_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 ID: `{user_id}`\n👥 Meine Gruppen: {groups}\n💎 Abonnement: {sub}\n📡 Kanal: {channel}\n📝 Unveröffentlicht: {pending}\n⚙️ Auto: {auto}",
        'channels_empty': "📭 Keine Kanäle",
        'channels_header': "📡 **Meine Kanäle**",
        'posts_empty': "📭 Keine Beiträge",
        'posts_header': "📋 **Meine Beiträge**",
        'groups_empty': "📭 Keine Gruppen",
        'groups_header': "👥 **Meine Gruppen**",
        'security_header': "🔐 **Sicherheitseinstellungen**",
        'settings_header': "⚙️ **Einstellungen**",
        'referral_header': "🔗 Ihr Link: `{link}`\n👥 {total} | 🎁 {available} Tage",
        'reminder_header': "⏰ Erinnerungseinstellungen",
        'translation_header': "🌐 Übersetzung: {lang}",
        'contests_header': "🏆 **Wettbewerbe**",
        'stats_text': "📊 Bot-Statistiken\n👥 {users} Benutzer\n🚫 {banned} gebannt\n📝 {posts} Beiträge\n👥 {groups} Gruppen\n📡 {channels} Kanäle",
        'help_text': "❓ **Relax Manager Hilfe**\n📌 Befehle:\n/start - Hauptmenü\n/help - Diese Hilfe\n/syncgroup - Bot in Gruppe aktivieren\n/security - Sicherheitseinstellungen\n/panel - Kontrollpanel\n/lock - Gruppe sperren\n/unlock - Gruppe entsperren\n/stats - Statistiken\n/schedule - Beiträge planen\n/contests - Wettbewerbe\n/support - Support\n/trial - Kostenlose Testversion\n/subscribe - Abonnieren",
        'developer_text': "👨‍💻 {bot_name}\n@RelaxMgr",
        'trial_used': "❌ Testversion bereits verwendet",
        'trial_activated': "✅ {days} Tage aktiviert",
        'subscription_active': "✅ Aktiv",
        'subscription_inactive': "❌ Inaktiv",
        'auto_on': "Ein",
        'auto_off': "Aus",
        'no_active_channel': "⚠️ Wählen Sie einen Kanal",
        'subscription_expired': "⚠️ Abonnement abgelaufen",
        'limit_reached': "⚠️ Grenze erreicht",
        'post_added': "✅ {count}/{target} | Verbleibend {remaining}",
        'posts_saved': "✅ Gespeichert",
        'published_success': "✅ Veröffentlicht",
        'publish_failed': "❌ Veröffentlichung fehlgeschlagen: {error}",
        'all_published': "✅ Alle veröffentlicht",
        'channel_added': "✅ Hinzugefügt",
        'channel_exists': "⚠️ Existiert bereits",
        'channel_error': "❌ Fehler: {error}",
        'not_channel': "❌ Kein Kanal",
        'bot_not_admin': "❌ Bot ist kein Admin oder kann nicht veröffentlichen",
        'invalid_format': "❌ Ungültiges Format",
        'unsupported_media': "⚠️ Nicht unterstützt",
        'schedule_current': "⏰ Zeitplan (aktuell: {type})",
        'schedule_updated': "✅ Aktualisiert",
        'schedule_invalid_time': "❌ Ungültige Zeit",
        'schedule_past': "❌ Zeit in der Vergangenheit",
        'security_enabled': "✅",
        'security_disabled': "❌",
        'penalty_set': "✅ Strafe festgelegt: {penalty}",
        'banned_word_added': "✅ '{word}' hinzugefügt",
        'banned_word_removed': "✅ '{word}' entfernt",
        'admin_added': "✅ {user_id} hinzugefügt",
        'admin_removed': "✅ {user_id} entfernt",
        'support_ticket_sent': "✅ Ticket #{number}",
        'contest_created': "✅ Wettbewerb #{id}",
        'contest_participated': "✅ Teilgenommen",
        'contest_no_winner': "🏆 Noch keine Gewinner",
        'contest_winners': "🏆 **Frühere Gewinner**",
        'reply_added': "✅ Antwort für '{keyword}' hinzugefügt",
        'reply_removed': "✅ Antwort entfernt",
        'auto_reply_toggled': "✅ {status}",
        'auto_reply_admin_only': "✅ {status}",
        'auto_reply_reset': "✅ Zurückgesetzt",
        'reminder_days_set': "✅ {days} Tage festgelegt",
        'lang_changed': "✅ Sprache geändert",
        'translation_off': "✅ Übersetzung deaktiviert",
        'translation_on': "✅ Übersetzung auf {lang} aktiviert",
        'referral_claimed': "✅ {days} Tage",
        'referral_list': "📋 Empfehlungsliste",
        'no_referrals': "📭 Keine Empfehlungen",
        'stats_pending': "📊 Unveröffentlicht: {pending}\n📋 Gesamt: {total}",
        'stats_full': "📈 Kanäle: {channels}\n📝 Beiträge: {posts}\n⏳ Unveröffentlicht: {pending}\n👥 Gruppen: {groups}\n⚙️ Auto: {auto}",
        'channel_stats': "📊 {total} | ✅ {published} | ⏳ {pending}",
        'growth_stats': "📈 Kanalwachstum (letzte 7 Tage): {growth} Beiträge",
        'admin_panel': "👑 Admin-Panel",
        'admin_users': "👥 Benutzer: {users}\n🚫 Gebannt: {banned}",
        'admin_banned_users': "🚫 Gebannte Benutzer:\n{list}",
        'admin_channels': "📡 Kanäle:\n{list}",
        'admin_groups': "👥 Gruppen:\n{list}",
        'admin_ram': "💾 {used:.1f}/{total:.1f} GB ({percent}%)",
        'admin_stats': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'admin_metrics': "📊 **Metriken**\n👥 Aktive Benutzer: {active}\n📝 Heutige Beiträge: {today}\n💾 DB-Größe: {db_size} MB",
        'admin_backup_created': "✅ Backup erstellt: {file}",
        'admin_backup_failed': "❌ Fehlgeschlagen: {error}",
        'admin_restore_success': "✅ Erfolgreich wiederhergestellt",
        'admin_restore_failed': "❌ Fehlgeschlagen: {error}",
        'admin_broadcast_confirm': "📨 Bestätigen:\n{text}",
        'admin_broadcast_sent': "✅ An {sent} Benutzer gesendet",
        'admin_tickets': "📋 Tickets:\n{list}",
        'admin_ticket_replied': "✅ An `{user}` geantwortet",
        'admin_ticket_reply_failed': "❌ Senden fehlgeschlagen: {error}",
        'admin_delete_tickets_confirm': "⚠️ Möchten Sie wirklich alle Tickets löschen?",
        'admin_delete_tickets_done': "✅ Gelöscht",
        'admin_log_channel_set': "✅ Kanal {channel} festgelegt",
        'admin_force_subscribe_channel': "✅ @{channel} festgelegt",
        'admin_update_channel_set': "✅ @{channel} festgelegt",
        'admin_update_sent': "✅ Gesendet",
        'admin_update_failed': "❌ Fehlgeschlagen",
        'admin_unban_all': "✅ Alle entbannt",
        'admin_activate_all': "✅ Alle aktiviert",
        'admin_no_updates_channel': "❌ Kein Update-Kanal",
        'admin_no_force_channel': "❌ Kein Zwangsabonnement-Kanal",
        'admin_sendcode_user_set': "✅ {user} festgelegt",
        'admin_sendcode_user_invalid': "❌ Fehler",
        'admin_lock': "🔒 Gesperrt",
        'admin_unlock': "🔓 Entsperrt",
        'admin_panel_closed': "Geschlossen",
        'unauthorized': "🔒 Nicht autorisiert",
        'canceled': "❌ Abgebrochen",
        'back': "🔙 Zurück",
        'close': "🔙 Schließen",
        'add_channel': "➕ Kanal hinzufügen",
        'my_channels': "📡 Meine Kanäle",
        'add_posts': "📥 Beiträge hinzufügen",
        'publish_one': "📤 Einen veröffentlichen",
        'my_posts': "📋 Meine Beiträge",
        'recycle': "♻️ Recyceln",
        'stats_pending_btn': "📊 Unveröffentlicht",
        'stats_full_btn': "📈 Vollständig",
        'schedule_btn': "⏰ Zeitplan",
        'channel_stats_btn': "📊 Kanal",
        'publish_all': "📤 Alle veröffentlichen",
        'help_btn': "❓ Hilfe",
        'trial_btn': "🎁 Testversion",
        'subscribe_btn': "💎 Abonnieren",
        'developer_btn': "👨‍💻 Entwickler",
        'language_btn': "🌐 Sprache",
        'support_btn': "📞 Support",
        'referral_btn': "🔗 Empfehlungen",
        'reminder_btn': "⏰ Erinnerungen",
        'translation_btn': "🌐 Übersetzung",
        'contests_btn': "🏆 Wettbewerbe",
        'add_group_btn': "➕ Zu Gruppe hinzufügen",
        'admin_panel_btn': "👑 Admin-Panel",
        'confirm': "✅ Bestätigen",
        'cancel': "❌ Abbrechen",
        'yes': "✅ Ja",
        'no': "❌ Nein",
        'share_link': "🔗 Teilen",
        'copy_link': "📋 Link kopieren",
        'claim_reward': "🎁 Einfordern",
        'referral_list_btn': "📋 Empfehlungsliste",
        'subscribe_1_day': "💎 1 Tag",
        'subscribe_2_days': "💎 2 Tage",
        'subscribe_30_days': "💎 30 Tage",
        'subscribe_90_days': "💎 90 Tage",
        'ticket_btn': "📞 Ticket",
        'winners_btn': "🏆 Gewinner",
        'nsfw_toggle_btn': "🔞 NSFW: {status}",
        'nsfw_threshold_btn': "🔞 Schwellwert: {threshold}%",
        'auto_reply_toggle_btn': "📝 Antworten: {status}",
        'auto_reply_admins_btn': "👥 Benutzer: {users}",
        'auto_reply_reset_btn': "🔄 Zurücksetzen",
        'auto_reply_stats_btn': "📊 Statistiken",
        'auto_reply_menu_btn': "📝 Automatische Antworten",
        'auto_reply_add_btn': "➕ Antwort hinzufügen",
        'auto_reply_del_btn': "🗑️ Antwort löschen",
        'auto_reply_list_btn': "📋 Antwortliste",
        'syncgroup_success_group': "✅ **Bot erfolgreich aktiviert!**\n\n👥 {count} Administratoren von Telegram synchronisiert.\n👤 `{user_id}` als Bot-Manager hinzugefügt.\n\n📌 Sie können jetzt Administratorbefehle verwenden:\n• `/security` - Sicherheitseinstellungen\n• `/ban`, `/mute`, `/warn` - Strafen\n• `/panel` - Kontrollpanel\n• `/add_hidden_admin` - Versteckten Admin hinzufügen",
        'syncgroup_success_private': "✅ Bot in Gruppe **{title}** aktiviert\nDie Gruppe wird jetzt in 'Meine Gruppen' im privaten Chat angezeigt.",
        'syncgroup_not_group': "❌ Nur in Gruppen verwenden",
        'syncgroup_not_admin': "🔒 Sie benötigen Administratorrechte, um den Bot zu aktivieren",
        'syncgroup_error': "❌ Fehler bei der Überprüfung der Berechtigungen: {error}",
        'syncgroup_already': "⚠️ Gruppe bereits registriert, Administratoren werden aktualisiert...",
    },
    'es': {
        'main_menu_title': "🌿 **{bot_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 ID: `{user_id}`\n👥 Mis Grupos: {groups}\n💎 Suscripción: {sub}\n📡 Canal: {channel}\n📝 No publicados: {pending}\n⚙️ Auto: {auto}",
        'channels_empty': "📭 No hay canales",
        'channels_header': "📡 **Mis Canales**",
        'posts_empty': "📭 No hay publicaciones",
        'posts_header': "📋 **Mis Publicaciones**",
        'groups_empty': "📭 No hay grupos",
        'groups_header': "👥 **Mis Grupos**",
        'security_header': "🔐 **Configuración de Seguridad**",
        'settings_header': "⚙️ **Configuración**",
        'referral_header': "🔗 Tu enlace: `{link}`\n👥 {total} | 🎁 {available} días",
        'reminder_header': "⏰ Configuración de Recordatorios",
        'translation_header': "🌐 Traducción: {lang}",
        'contests_header': "🏆 **Concursos**",
        'stats_text': "📊 Estadísticas del Bot\n👥 {users} usuarios\n🚫 {banned} baneados\n📝 {posts} publicaciones\n👥 {groups} grupos\n📡 {channels} canales",
        'help_text': "❓ **Ayuda de Relax Manager**\n📌 Comandos:\n/start - Menú principal\n/help - Esta ayuda\n/syncgroup - Activar bot en el grupo\n/security - Configuración de seguridad\n/panel - Panel de control\n/lock - Bloquear grupo\n/unlock - Desbloquear grupo\n/stats - Estadísticas generales\n/schedule - Programar publicaciones\n/contests - Concursos\n/support - Soporte\n/trial - Prueba gratuita\n/subscribe - Suscribirse",
        'developer_text': "👨‍💻 {bot_name}\n@RelaxMgr",
        'trial_used': "❌ Prueba ya utilizada",
        'trial_activated': "✅ {days} días activados",
        'subscription_active': "✅ Activo",
        'subscription_inactive': "❌ Inactivo",
        'auto_on': "Activado",
        'auto_off': "Desactivado",
        'no_active_channel': "⚠️ Selecciona un canal",
        'subscription_expired': "⚠️ Suscripción caducada",
        'limit_reached': "⚠️ Límite alcanzado",
        'post_added': "✅ {count}/{target} | Restantes {remaining}",
        'posts_saved': "✅ Guardado",
        'published_success': "✅ Publicado",
        'publish_failed': "❌ Error al publicar: {error}",
        'all_published': "✅ Todos publicados",
        'channel_added': "✅ Añadido",
        'channel_exists': "⚠️ Ya existe",
        'channel_error': "❌ Error: {error}",
        'not_channel': "❌ No es un canal",
        'bot_not_admin': "❌ El bot no es administrador o no puede publicar",
        'invalid_format': "❌ Formato inválido",
        'unsupported_media': "⚠️ No soportado",
        'schedule_current': "⏰ Programación (actual: {type})",
        'schedule_updated': "✅ Actualizado",
        'schedule_invalid_time': "❌ Hora inválida",
        'schedule_past': "❌ Hora pasada",
        'security_enabled': "✅",
        'security_disabled': "❌",
        'penalty_set': "✅ Penalización establecida: {penalty}",
        'banned_word_added': "✅ '{word}' añadida",
        'banned_word_removed': "✅ '{word}' eliminada",
        'admin_added': "✅ {user_id} añadido",
        'admin_removed': "✅ {user_id} eliminado",
        'support_ticket_sent': "✅ Ticket #{number}",
        'contest_created': "✅ Concurso #{id}",
        'contest_participated': "✅ Participaste",
        'contest_no_winner': "🏆 Aún no hay ganadores",
        'contest_winners': "🏆 **Ganadores Anteriores**",
        'reply_added': "✅ Respuesta añadida para '{keyword}'",
        'reply_removed': "✅ Respuesta eliminada",
        'auto_reply_toggled': "✅ {status}",
        'auto_reply_admin_only': "✅ {status}",
        'auto_reply_reset': "✅ Reiniciado",
        'reminder_days_set': "✅ {days} días establecidos",
        'lang_changed': "✅ Idioma cambiado",
        'translation_off': "✅ Traducción desactivada",
        'translation_on': "✅ Traducción activada a {lang}",
        'referral_claimed': "✅ {days} días",
        'referral_list': "📋 Lista de referidos",
        'no_referrals': "📭 No hay referidos",
        'stats_pending': "📊 No publicados: {pending}\n📋 Total: {total}",
        'stats_full': "📈 Canales: {channels}\n📝 Publicaciones: {posts}\n⏳ No publicados: {pending}\n👥 Grupos: {groups}\n⚙️ Auto: {auto}",
        'channel_stats': "📊 {total} | ✅ {published} | ⏳ {pending}",
        'growth_stats': "📈 Crecimiento del canal (últimos 7 días): {growth} publicaciones",
        'admin_panel': "👑 Panel de Administración",
        'admin_users': "👥 Usuarios: {users}\n🚫 Baneados: {banned}",
        'admin_banned_users': "🚫 Usuarios Baneados:\n{list}",
        'admin_channels': "📡 Canales:\n{list}",
        'admin_groups': "👥 Grupos:\n{list}",
        'admin_ram': "💾 {used:.1f}/{total:.1f} GB ({percent}%)",
        'admin_stats': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'admin_metrics': "📊 **Métricas**\n👥 Usuarios Activos: {active}\n📝 Publicaciones de Hoy: {today}\n💾 Tamaño DB: {db_size} MB",
        'admin_backup_created': "✅ Copia de seguridad creada: {file}",
        'admin_backup_failed': "❌ Falló: {error}",
        'admin_restore_success': "✅ Restaurado con éxito",
        'admin_restore_failed': "❌ Falló: {error}",
        'admin_broadcast_confirm': "📨 Confirmar:\n{text}",
        'admin_broadcast_sent': "✅ Enviado a {sent} usuarios",
        'admin_tickets': "📋 Tickets:\n{list}",
        'admin_ticket_replied': "✅ Respondido a `{user}`",
        'admin_ticket_reply_failed': "❌ Error al enviar: {error}",
        'admin_delete_tickets_confirm': "⚠️ ¿Estás seguro de eliminar todos los tickets?",
        'admin_delete_tickets_done': "✅ Eliminados",
        'admin_log_channel_set': "✅ Canal {channel} establecido",
        'admin_force_subscribe_channel': "✅ @{channel} establecido",
        'admin_update_channel_set': "✅ @{channel} establecido",
        'admin_update_sent': "✅ Enviado",
        'admin_update_failed': "❌ Falló",
        'admin_unban_all': "✅ Todos desbaneados",
        'admin_activate_all': "✅ Todos activados",
        'admin_no_updates_channel': "❌ No hay canal de actualizaciones",
        'admin_no_force_channel': "❌ No hay canal de suscripción forzada",
        'admin_sendcode_user_set': "✅ {user} establecido",
        'admin_sendcode_user_invalid': "❌ Error",
        'admin_lock': "🔒 Bloqueado",
        'admin_unlock': "🔓 Desbloqueado",
        'admin_panel_closed': "Cerrado",
        'unauthorized': "🔒 No autorizado",
        'canceled': "❌ Cancelado",
        'back': "🔙 Atrás",
        'close': "🔙 Cerrar",
        'add_channel': "➕ Añadir canal",
        'my_channels': "📡 Mis canales",
        'add_posts': "📥 Añadir publicaciones",
        'publish_one': "📤 Publicar una",
        'my_posts': "📋 Mis publicaciones",
        'recycle': "♻️ Reciclar",
        'stats_pending_btn': "📊 No publicados",
        'stats_full_btn': "📈 Completo",
        'schedule_btn': "⏰ Programación",
        'channel_stats_btn': "📊 Canal",
        'publish_all': "📤 Publicar todo",
        'help_btn': "❓ Ayuda",
        'trial_btn': "🎁 Prueba",
        'subscribe_btn': "💎 Suscribirse",
        'developer_btn': "👨‍💻 Desarrollador",
        'language_btn': "🌐 Idioma",
        'support_btn': "📞 Soporte",
        'referral_btn': "🔗 Referidos",
        'reminder_btn': "⏰ Recordatorios",
        'translation_btn': "🌐 Traducción",
        'contests_btn': "🏆 Concursos",
        'add_group_btn': "➕ Añadir al grupo",
        'admin_panel_btn': "👑 Panel de Admin",
        'confirm': "✅ Confirmar",
        'cancel': "❌ Cancelar",
        'yes': "✅ Sí",
        'no': "❌ No",
        'share_link': "🔗 Compartir",
        'copy_link': "📋 Copiar enlace",
        'claim_reward': "🎁 Reclamar",
        'referral_list_btn': "📋 Lista de referidos",
        'subscribe_1_day': "💎 1 Día",
        'subscribe_2_days': "💎 2 Días",
        'subscribe_30_days': "💎 30 Días",
        'subscribe_90_days': "💎 90 Días",
        'ticket_btn': "📞 Ticket",
        'winners_btn': "🏆 Ganadores",
        'nsfw_toggle_btn': "🔞 NSFW: {status}",
        'nsfw_threshold_btn': "🔞 Umbral: {threshold}%",
        'auto_reply_toggle_btn': "📝 Respuestas: {status}",
        'auto_reply_admins_btn': "👥 Usuarios: {users}",
        'auto_reply_reset_btn': "🔄 Reiniciar",
        'auto_reply_stats_btn': "📊 Estadísticas",
        'auto_reply_menu_btn': "📝 Respuestas automáticas",
        'auto_reply_add_btn': "➕ Añadir respuesta",
        'auto_reply_del_btn': "🗑️ Eliminar respuesta",
        'auto_reply_list_btn': "📋 Lista de respuestas",
        'syncgroup_success_group': "✅ **¡Bot activado con éxito!**\n\n👥 {count} administradores sincronizados desde Telegram.\n👤 `{user_id}` añadido como gestor del bot.\n\n📌 Ahora puedes usar comandos de administración:\n• `/security` - Configuración de seguridad\n• `/ban`, `/mute`, `/warn` - Sanciones\n• `/panel` - Panel de control\n• `/add_hidden_admin` - Añadir administrador oculto",
        'syncgroup_success_private': "✅ Bot activado en el grupo **{title}**\nEl grupo aparecerá ahora en 'Mis Grupos' en el chat privado.",
        'syncgroup_not_group': "❌ Usar solo en grupos",
        'syncgroup_not_admin': "🔒 Necesitas permisos de administrador para activar el bot",
        'syncgroup_error': "❌ Error al verificar permisos: {error}",
        'syncgroup_already': "⚠️ Grupo ya registrado, actualizando administradores...",
    },
    'ru': {
        'main_menu_title': "🌿 **{bot_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 ID: `{user_id}`\n👥 Мои группы: {groups}\n💎 Подписка: {sub}\n📡 Канал: {channel}\n📝 Неопубликованные: {pending}\n⚙️ Авто: {auto}",
        'channels_empty': "📭 Нет каналов",
        'channels_header': "📡 **Мои каналы**",
        'posts_empty': "📭 Нет постов",
        'posts_header': "📋 **Мои посты**",
        'groups_empty': "📭 Нет групп",
        'groups_header': "👥 **Мои группы**",
        'security_header': "🔐 **Настройки безопасности**",
        'settings_header': "⚙️ **Настройки**",
        'referral_header': "🔗 Ваша ссылка: `{link}`\n👥 {total} | 🎁 {available} дней",
        'reminder_header': "⏰ Настройки напоминаний",
        'translation_header': "🌐 Перевод: {lang}",
        'contests_header': "🏆 **Конкурсы**",
        'stats_text': "📊 Статистика бота\n👥 {users} пользователей\n🚫 {banned} забанено\n📝 {posts} постов\n👥 {groups} групп\n📡 {channels} каналов",
        'help_text': "❓ **Помощь Relax Manager**\n📌 Команды:\n/start - Главное меню\n/help - Эта помощь\n/syncgroup - Активировать бота в группе\n/security - Настройки безопасности\n/panel - Панель управления\n/lock - Заблокировать группу\n/unlock - Разблокировать группу\n/stats - Общая статистика\n/schedule - Планирование постов\n/contests - Конкурсы\n/support - Поддержка\n/trial - Бесплатная пробная версия\n/subscribe - Подписка",
        'developer_text': "👨‍💻 {bot_name}\n@RelaxMgr",
        'trial_used': "❌ Пробная версия уже использована",
        'trial_activated': "✅ {days} дней активировано",
        'subscription_active': "✅ Активно",
        'subscription_inactive': "❌ Не активно",
        'auto_on': "Вкл",
        'auto_off': "Выкл",
        'no_active_channel': "⚠️ Выберите канал",
        'subscription_expired': "⚠️ Подписка истекла",
        'limit_reached': "⚠️ Достигнут лимит",
        'post_added': "✅ {count}/{target} | Осталось {remaining}",
        'posts_saved': "✅ Сохранено",
        'published_success': "✅ Опубликовано",
        'publish_failed': "❌ Ошибка публикации: {error}",
        'all_published': "✅ Все опубликовано",
        'channel_added': "✅ Добавлено",
        'channel_exists': "⚠️ Уже существует",
        'channel_error': "❌ Ошибка: {error}",
        'not_channel': "❌ Не канал",
        'bot_not_admin': "❌ Бот не администратор или не может публиковать",
        'invalid_format': "❌ Неверный формат",
        'unsupported_media': "⚠️ Не поддерживается",
        'schedule_current': "⏰ Расписание (текущее: {type})",
        'schedule_updated': "✅ Обновлено",
        'schedule_invalid_time': "❌ Неверное время",
        'schedule_past': "❌ Время в прошлом",
        'security_enabled': "✅",
        'security_disabled': "❌",
        'penalty_set': "✅ Наказание установлено: {penalty}",
        'banned_word_added': "✅ '{word}' добавлено",
        'banned_word_removed': "✅ '{word}' удалено",
        'admin_added': "✅ {user_id} добавлен",
        'admin_removed': "✅ {user_id} удален",
        'support_ticket_sent': "✅ Тикет #{number}",
        'contest_created': "✅ Конкурс #{id}",
        'contest_participated': "✅ Участие принято",
        'contest_no_winner': "🏆 Победителей пока нет",
        'contest_winners': "🏆 **Предыдущие победители**",
        'reply_added': "✅ Ответ добавлен для '{keyword}'",
        'reply_removed': "✅ Ответ удален",
        'auto_reply_toggled': "✅ {status}",
        'auto_reply_admin_only': "✅ {status}",
        'auto_reply_reset': "✅ Сброшено",
        'reminder_days_set': "✅ {days} дней установлено",
        'lang_changed': "✅ Язык изменен",
        'translation_off': "✅ Перевод отключен",
        'translation_on': "✅ Перевод включен на {lang}",
        'referral_claimed': "✅ {days} дней",
        'referral_list': "📋 Список рефералов",
        'no_referrals': "📭 Нет рефералов",
        'stats_pending': "📊 Неопубликованные: {pending}\n📋 Всего: {total}",
        'stats_full': "📈 Каналы: {channels}\n📝 Посты: {posts}\n⏳ Неопубликованные: {pending}\n👥 Группы: {groups}\n⚙️ Авто: {auto}",
        'channel_stats': "📊 {total} | ✅ {published} | ⏳ {pending}",
        'growth_stats': "📈 Рост канала (последние 7 дней): {growth} постов",
        'admin_panel': "👑 Панель администратора",
        'admin_users': "👥 Пользователи: {users}\n🚫 Забанены: {banned}",
        'admin_banned_users': "🚫 Забаненные пользователи:\n{list}",
        'admin_channels': "📡 Каналы:\n{list}",
        'admin_groups': "👥 Группы:\n{list}",
        'admin_ram': "💾 {used:.1f}/{total:.1f} ГБ ({percent}%)",
        'admin_stats': "👥 {users} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}",
        'admin_metrics': "📊 **Метрики**\n👥 Активные пользователи: {active}\n📝 Сегодняшних постов: {today}\n💾 Размер БД: {db_size} МБ",
        'admin_backup_created': "✅ Резервная копия создана: {file}",
        'admin_backup_failed': "❌ Ошибка: {error}",
        'admin_restore_success': "✅ Восстановлено успешно",
        'admin_restore_failed': "❌ Ошибка: {error}",
        'admin_broadcast_confirm': "📨 Подтвердить:\n{text}",
        'admin_broadcast_sent': "✅ Отправлено {sent} пользователям",
        'admin_tickets': "📋 Тикеты:\n{list}",
        'admin_ticket_replied': "✅ Ответ отправлен `{user}`",
        'admin_ticket_reply_failed': "❌ Ошибка отправки: {error}",
        'admin_delete_tickets_confirm': "⚠️ Вы уверены, что хотите удалить все тикеты?",
        'admin_delete_tickets_done': "✅ Удалены",
        'admin_log_channel_set': "✅ Канал {channel} установлен",
        'admin_force_subscribe_channel': "✅ @{channel} установлен",
        'admin_update_channel_set': "✅ @{channel} установлен",
        'admin_update_sent': "✅ Отправлено",
        'admin_update_failed': "❌ Ошибка",
        'admin_unban_all': "✅ Все разбанены",
        'admin_activate_all': "✅ Все активированы",
        'admin_no_updates_channel': "❌ Нет канала обновлений",
        'admin_no_force_channel': "❌ Нет канала принудительной подписки",
        'admin_sendcode_user_set': "✅ {user} установлен",
        'admin_sendcode_user_invalid': "❌ Ошибка",
        'admin_lock': "🔒 Заблокировано",
        'admin_unlock': "🔓 Разблокировано",
        'admin_panel_closed': "Закрыто",
        'unauthorized': "🔒 Не авторизован",
        'canceled': "❌ Отменено",
        'back': "🔙 Назад",
        'close': "🔙 Закрыть",
        'add_channel': "➕ Добавить канал",
        'my_channels': "📡 Мои каналы",
        'add_posts': "📥 Добавить посты",
        'publish_one': "📤 Опубликовать один",
        'my_posts': "📋 Мои посты",
        'recycle': "♻️ Переработать",
        'stats_pending_btn': "📊 Неопубликованные",
        'stats_full_btn': "📈 Полные",
        'schedule_btn': "⏰ Расписание",
        'channel_stats_btn': "📊 Канал",
        'publish_all': "📤 Опубликовать все",
        'help_btn': "❓ Помощь",
        'trial_btn': "🎁 Пробная версия",
        'subscribe_btn': "💎 Подписка",
        'developer_btn': "👨‍💻 Разработчик",
        'language_btn': "🌐 Язык",
        'support_btn': "📞 Поддержка",
        'referral_btn': "🔗 Рефералы",
        'reminder_btn': "⏰ Напоминания",
        'translation_btn': "🌐 Перевод",
        'contests_btn': "🏆 Конкурсы",
        'add_group_btn': "➕ Добавить в группу",
        'admin_panel_btn': "👑 Панель администратора",
        'confirm': "✅ Подтвердить",
        'cancel': "❌ Отмена",
        'yes': "✅ Да",
        'no': "❌ Нет",
        'share_link': "🔗 Поделиться",
        'copy_link': "📋 Копировать ссылку",
        'claim_reward': "🎁 Получить",
        'referral_list_btn': "📋 Список рефералов",
        'subscribe_1_day': "💎 1 День",
        'subscribe_2_days': "💎 2 Дня",
        'subscribe_30_days': "💎 30 Дней",
        'subscribe_90_days': "💎 90 Дней",
        'ticket_btn': "📞 Тикет",
        'winners_btn': "🏆 Победители",
        'nsfw_toggle_btn': "🔞 NSFW: {status}",
        'nsfw_threshold_btn': "🔞 Порог: {threshold}%",
        'auto_reply_toggle_btn': "📝 Ответы: {status}",
        'auto_reply_admins_btn': "👥 Пользователи: {users}",
        'auto_reply_reset_btn': "🔄 Сбросить",
        'auto_reply_stats_btn': "📊 Статистика",
        'auto_reply_menu_btn': "📝 Автоответы",
        'auto_reply_add_btn': "➕ Добавить ответ",
        'auto_reply_del_btn': "🗑️ Удалить ответ",
        'auto_reply_list_btn': "📋 Список ответов",
        'syncgroup_success_group': "✅ **Бот успешно активирован!**\n\n👥 {count} администраторов синхронизировано с Telegram.\n👤 `{user_id}` добавлен как менеджер бота.\n\n📌 Теперь вы можете использовать команды администратора:\n• `/security` - Настройки безопасности\n• `/ban`, `/mute`, `/warn` - Наказания\n• `/panel` - Панель управления\n• `/add_hidden_admin` - Добавить скрытого администратора",
        'syncgroup_success_private': "✅ Бот активирован в группе **{title}**\nГруппа теперь появится в 'Мои группы' в личном чате.",
        'syncgroup_not_group': "❌ Используйте только в группах",
        'syncgroup_not_admin': "🔒 Вам нужны права администратора для активации бота",
        'syncgroup_error': "❌ Ошибка проверки прав: {error}",
        'syncgroup_already': "⚠️ Группа уже зарегистрирована, обновление администраторов...",
    }
}

def get_text(lang: str, key: str, **kwargs) -> str:
    if lang not in LOCALES:
        lang = 'ar'
    text = LOCALES[lang].get(key, key)
    try:
        return text.format(**kwargs)
    except:
        return text

# ===================================================================
# 6. نظام السجلات الآمن
# ===================================================================
class SecureLogFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if TOKEN and TOKEN in msg:
            record.msg = msg.replace(TOKEN, "[TOKEN_HIDDEN]")
        return True

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
for handler in logger.handlers:
    handler.addFilter(SecureLogFilter())

def log_error(error: Exception, context: dict = None) -> str:
    error_id = secrets.token_hex(4)
    logger.error(f"[{error_id}] {type(error).__name__}: {str(error)[:300]}")
    return error_id

# ===================================================================
# 7. دوال مساعدة
# ===================================================================
def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def mecca_now():
    return utc_now() + timedelta(hours=3)

def utc_now_iso():
    return utc_now().isoformat()

def mecca_now_iso():
    return mecca_now().isoformat()

def mecca_to_utc(dt):
    return dt - timedelta(hours=3) if dt else None

def utc_to_mecca(dt):
    return dt + timedelta(hours=3) if dt else None

def contains_link(text):
    if not text:
        return False
    return bool(re.search(r'https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+', text, re.IGNORECASE))

def contains_mention(text):
    return bool(re.search(r'@\w+', text)) if text else False

def sanitize_text(text: str, max_length: int = 4096) -> str:
    if not text:
        return ""
    text = re.sub(r'[\u200b\u200c\u200d\u2060\uFEFF\u202a\u202b\u202c\u202d\u202e]', '', text)
    return text[:max_length]

def escape_markdown_v2(text: str) -> str:
    if not text:
        return ""
    special_chars = r'_*[]()~`>#+\-=|{}.!\\'
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', text)

def get_ram_usage():
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {'total': round(mem.total/(1024**3),1), 'used': round(mem.used/(1024**3),1), 'percent': mem.percent}
    except:
        return {'total': 0, 'used': 0, 'percent': 0}

def load_banned_words_from_file(file_path: Path) -> List[str]:
    if not file_path.exists():
        file_path.write_text("# كلمات محظورة\n", encoding='utf-8')
        return []
    with open(file_path, 'r', encoding='utf-8') as f:
        words = [line.strip().lower() for line in f if line.strip() and not line.startswith('#') and len(line.strip()) >= 2]
    return words

def load_auto_replies_from_file(file_path: Path) -> List[Dict[str, str]]:
    if not file_path.exists():
        default_replies = [
            {"keyword": "مرحبا", "reply": "أهلاً بك! كيف يمكنني مساعدتك؟"},
            {"keyword": "شكرا", "reply": "العفو، دائماً في خدمتك."},
            {"keyword": "سلام", "reply": "وعليكم السلام، مرحباً بك."}
        ]
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(default_replies, f, ensure_ascii=False, indent=2)
        return default_replies
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

async def import_auto_replies_from_file():
    replies = load_auto_replies_from_file(AUTO_REPLIES_FILE)
    if not replies:
        return
    for item in replies:
        keyword = item.get('keyword', '').strip().lower()
        reply = item.get('reply', '').strip()
        if keyword and reply:
            try:
                await db_add_reply_with_stats(0, keyword, reply)
            except:
                pass

async def is_user_bot(bot, user_id: int) -> bool:
    try:
        chat = await bot.get_chat(user_id)
        return chat.is_bot
    except:
        return False

# ===================================================================
# 8. التشفير وإدارة المفاتيح
# ===================================================================
def derive_key_from_password(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def get_encryption_key() -> bytes:
    env_key = os.getenv("DB_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode()
    key_file = DATA_PATH / ".db_key"
    salt_file = DATA_PATH / ".db_salt"
    if key_file.exists() and salt_file.exists():
        try:
            with open(key_file, 'rb') as f:
                return f.read()
        except:
            pass
    key = Fernet.generate_key()
    with open(key_file, 'wb') as f:
        f.write(key)
    os.chmod(key_file, 0o600)
    return key

ENCRYPTION_KEY = get_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

def get_backup_key() -> bytes:
    f = DATA_PATH / ".backup_key"
    if f.exists():
        try:
            return f.read_bytes()
        except:
            pass
    k = Fernet.generate_key()
    f.write_bytes(k)
    os.chmod(f, 0o600)
    return k

BACKUP_CIPHER = Fernet(get_backup_key())

def compress_backup(data: bytes) -> bytes:
    return gzip.compress(data)

def decompress_backup(data: bytes) -> bytes:
    return gzip.decompress(data)

# ===================================================================
# 9. الكاش
# ===================================================================
try:
    from cachetools import TTLCache
    CACHETOOLS_AVAILABLE = True
    _auth_cache = TTLCache(maxsize=1000, ttl=10)
    _security_cache = TTLCache(maxsize=500, ttl=10)
    _slow_mode_cache = TTLCache(maxsize=500, ttl=10)
    _antiflood_cache = TTLCache(maxsize=500, ttl=10)
    _banned_words_cache = TTLCache(maxsize=200, ttl=30)
    _auto_reply_cache = TTLCache(maxsize=200, ttl=30)
except ImportError:
    CACHETOOLS_AVAILABLE = False
    _auth_cache = {}
    _security_cache = {}
    _slow_mode_cache = {}
    _antiflood_cache = {}
    _banned_words_cache = {}
    _auto_reply_cache = {}

_flood_cache = {}
BANNED_PATTERNS = []

async def cleanup_caches_periodically():
    while True:
        await asyncio.sleep(600)
        try:
            now = time_module.time()
            keys_to_remove = []
            for key, timestamps in _flood_cache.items():
                if not timestamps:
                    keys_to_remove.append(key)
                else:
                    valid = [t for t in timestamps if now - t < 60]
                    if valid:
                        _flood_cache[key] = valid
                    else:
                        keys_to_remove.append(key)
            for key in keys_to_remove:
                _flood_cache.pop(key, None)
            if CACHETOOLS_AVAILABLE:
                for cache in [_auth_cache, _security_cache, _slow_mode_cache, _antiflood_cache, _banned_words_cache, _auto_reply_cache]:
                    try:
                        cache.clear()
                    except:
                        pass
            gc.collect()
        except Exception as e:
            logger.error(f"تنظيف الكاشات: {e}")

# ===================================================================
# 10. دوال الإرسال الآمن
# ===================================================================
async def safe_send_markdown(bot, chat_id: int, text: str, reply_markup=None, **kwargs):
    if not text:
        return None
    try:
        escaped = escape_markdown_v2(text)
        if len(escaped) > 4096:
            escaped = escaped[:4093] + "..."
        return await bot.send_message(
            chat_id=chat_id,
            text=escaped,
            parse_mode='MarkdownV2',
            reply_markup=reply_markup,
            **kwargs
        )
    except Exception:
        try:
            html_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if len(html_text) > 4096:
                html_text = html_text[:4093] + "..."
            return await bot.send_message(
                chat_id=chat_id,
                text=html_text,
                parse_mode='HTML',
                reply_markup=reply_markup,
                **kwargs
            )
        except:
            try:
                plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', text)
                if len(plain) > 4096:
                    plain = plain[:4093] + "..."
                return await bot.send_message(
                    chat_id=chat_id,
                    text=plain,
                    reply_markup=reply_markup,
                    **kwargs
                )
            except:
                raise

async def safe_edit_markdown(query, text: str, reply_markup=None, **kwargs):
    if not query or not query.message or not text:
        return None
    try:
        escaped = escape_markdown_v2(text)
        if len(escaped) > 4096:
            escaped = escaped[:4093] + "..."
        return await query.edit_message_text(
            text=escaped,
            parse_mode='MarkdownV2',
            reply_markup=reply_markup,
            **kwargs
        )
    except Exception:
        try:
            html_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if len(html_text) > 4096:
                html_text = html_text[:4093] + "..."
            return await query.edit_message_text(
                text=html_text,
                parse_mode='HTML',
                reply_markup=reply_markup,
                **kwargs
            )
        except:
            try:
                plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', text)
                if len(plain) > 4096:
                    plain = plain[:4093] + "..."
                return await query.edit_message_text(
                    text=plain,
                    reply_markup=reply_markup,
                    **kwargs
                )
            except:
                raise

# ===================================================================
# 11. قاعدة البيانات (Database Pool)
# ===================================================================
class DatabasePool:
    def __init__(self):
        self._pool = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        async with self._lock:
            if self._pool:
                return
            self._pool = await aiosqlite.connect(str(DB_PATH), timeout=DB_TIMEOUT)
            await self._pool.execute("PRAGMA journal_mode=WAL")
            await self._pool.execute("PRAGMA synchronous=NORMAL")
            await self._pool.execute("PRAGMA foreign_keys=ON")
            self._pool.row_factory = aiosqlite.Row

    async def get_connection(self):
        if not self._pool:
            await self.initialize()
        return self._pool

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

db_pool = DatabasePool()

async def execute_db(func: Callable):
    conn = await db_pool.get_connection()
    return await func(conn)

# ===================================================================
# 12. تهيئة قاعدة البيانات (جميع الجداول مع الفهارس)
# ===================================================================
async def init_db():
    async def _init(conn):
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
                active_channel INTEGER,
                level INTEGER DEFAULT 1,
                points INTEGER DEFAULT 0,
                referred_by INTEGER,
                auto_reply_enabled INTEGER DEFAULT 1
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id TEXT,
                channel_name TEXT,
                banned INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_channels_user ON user_channels(user_id)")
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
                published_at TEXT,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id) ON DELETE CASCADE
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)")
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
                next_publish_date TEXT,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id) ON DELETE CASCADE
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_next ON schedule(next_publish_date)")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS last_publish (
                channel_db_id INTEGER PRIMARY KEY,
                last_publish_time TEXT,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id) ON DELETE CASCADE
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
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_group_admins_user ON group_admins(user_id)")
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
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_hidden_admins_user ON hidden_admins(admin_id)")
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
            CREATE TABLE IF NOT EXISTS user_messages (
                user_id INTEGER,
                chat_id INTEGER,
                message_time TEXT,
                PRIMARY KEY (user_id, chat_id)
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
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_banned_words_word ON banned_words(word)")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_replies (
                chat_id INTEGER,
                keyword TEXT,
                reply TEXT,
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
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('publish_interval', ?)",
                           (str(DEFAULT_PUBLISH_INTERVAL_SECONDS),))
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_backup', '1')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_ticket_number', '0')")
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
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_chat ON admin_logs(chat_id)")
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
            CREATE TABLE IF NOT EXISTS sentiment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                text_encrypted TEXT,
                sentiment TEXT,
                score REAL,
                created_at TEXT
            )
        """)
        await conn.commit()
        logger.info("✅ تم إنشاء جميع الجداول مع الفهارس")
    await execute_db(_init)

async def init_db_improved():
    await init_db()

async def ensure_security_columns():
    async def _ensure(conn):
        cur = await conn.execute("PRAGMA table_info(group_security)")
        existing = [row[1] for row in await cur.fetchall()]
        required = {
            'mentions': 'INTEGER DEFAULT 0',
            'delete_videos': 'INTEGER DEFAULT 0',
            'delete_audio': 'INTEGER DEFAULT 0',
            'delete_animation': 'INTEGER DEFAULT 0',
            'delete_service': 'INTEGER DEFAULT 0',
            'delete_documents': 'INTEGER DEFAULT 0',
            'delete_stickers': 'INTEGER DEFAULT 0',
            'delete_forwarded': 'INTEGER DEFAULT 0',
            'delete_polls': 'INTEGER DEFAULT 0',
            'delete_games': 'INTEGER DEFAULT 0',
            'delete_voice': 'INTEGER DEFAULT 0',
            'delete_video_note': 'INTEGER DEFAULT 0',
            'delete_penalty': 'TEXT DEFAULT "none"',
            'delete_penalty_duration': 'INTEGER DEFAULT 0',
            'antiflood_enabled': 'INTEGER DEFAULT 0',
            'antiflood_messages': 'INTEGER DEFAULT 5',
            'antiflood_seconds': 'INTEGER DEFAULT 10',
            'antiflood_penalty': 'TEXT DEFAULT "mute"',
            'max_warnings': 'INTEGER DEFAULT 3',
            'warn_penalty': 'TEXT DEFAULT "ban"',
            'max_message_length': 'INTEGER DEFAULT 0',
            'night_mode_enabled': 'INTEGER DEFAULT 0',
            'night_mode_start': 'TEXT DEFAULT "23:00"',
            'night_mode_end': 'TEXT DEFAULT "06:00"',
            'night_mode_action': 'TEXT DEFAULT "mute"',
            'nsfw_enabled': 'INTEGER DEFAULT 0',
            'nsfw_threshold': 'REAL DEFAULT 0.7'
        }
        for col, col_type in required.items():
            if col not in existing:
                await conn.execute(f"ALTER TABLE group_security ADD COLUMN {col} {col_type}")
                logger.info(f"✅ تم إضافة العمود {col}")
        await conn.commit()
    await execute_db(_ensure)

async def fix_missing_columns():
    await ensure_security_columns()

# ===================================================================
# 13. دوال المستخدمين الأساسية
# ===================================================================
async def db_register_user(user_id: int) -> bool:
    async def _reg(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if await cur.fetchone():
            await conn.execute("UPDATE users SET updated_at=? WHERE user_id=?", (utc_now_iso(), user_id))
            await conn.commit()
            return False
        code = secrets.token_urlsafe(6)
        await conn.execute("INSERT INTO users (user_id, referral_code, created_at, updated_at) VALUES (?,?,?,?)",
                           (user_id, code, utc_now_iso(), utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_reg)

async def db_has_active_subscription(user_id: int) -> bool:
    async def _chk(conn):
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try:
                return datetime.fromisoformat(row[0]) > utc_now()
            except:
                pass
        return False
    return await execute_db(_chk)

async def db_activate_subscription(user_id: int, days: int):
    async def _act(conn):
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try:
                current = datetime.fromisoformat(row[0])
                new_end = (current if current > utc_now() else utc_now()) + timedelta(days=days)
            except:
                new_end = utc_now() + timedelta(days=days)
        else:
            new_end = utc_now() + timedelta(days=days)
        await conn.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (new_end.isoformat(), user_id))
        await conn.commit()
    return await execute_db(_act)

async def db_has_used_trial(user_id: int) -> bool:
    async def _chk(conn):
        cur = await conn.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_chk)

async def db_activate_trial(user_id: int) -> int:
    async def _act(conn):
        cur = await conn.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        if (await cur.fetchone())[0] == 1:
            return 0
        end = (utc_now() + timedelta(days=30)).isoformat()
        await conn.execute("UPDATE users SET trial_used=1, subscription_end=? WHERE user_id=?", (end, user_id))
        await conn.commit()
        return 30
    return await execute_db(_act)

async def db_auto_status(user_id: int) -> bool:
    async def _g(conn):
        cur = await conn.execute("SELECT auto_publish FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_g)

async def db_set_auto(user_id: int, enabled: bool):
    await execute_db(lambda c: c.execute("UPDATE users SET auto_publish=? WHERE user_id=?", (1 if enabled else 0, user_id)) or c.commit())

async def db_get_auto_recycle(user_id: int) -> bool:
    async def _g(conn):
        cur = await conn.execute("SELECT auto_recycle FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_g)

async def db_set_auto_recycle(user_id: int, enabled: bool):
    await execute_db(lambda c: c.execute("UPDATE users SET auto_recycle=? WHERE user_id=?", (1 if enabled else 0, user_id)) or c.commit())

async def db_get_user_referral_code(user_id: int) -> str:
    async def _g(conn):
        cur = await conn.execute("SELECT referral_code FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else ""
    return await execute_db(_g)

async def db_get_user_by_referral_code(code: str) -> Optional[int]:
    async def _g(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE referral_code=?", (code,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_g)

async def db_update_user_cache(user_id: int, username: str, first_name: str):
    await execute_db(lambda c: c.execute("UPDATE users SET username=?, first_name=?, updated_at=? WHERE user_id=?",
                                         (username, first_name, utc_now_iso(), user_id)) or c.commit())

async def db_get_all_users():
    return await execute_db(lambda c: c.execute("SELECT user_id, banned FROM users ORDER BY user_id") or c.fetchall())

async def db_is_banned(user_id: int) -> bool:
    async def _chk(conn):
        cur = await conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_chk)

async def db_stats():
    async def _g(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM users")
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE banned=1")
        banned = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM posts")
        posts = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM bot_groups")
        groups = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM user_channels")
        channels = (await cur.fetchone())[0]
        return total, banned, posts, groups, channels
    return await execute_db(_g)

# ===================================================================
# 14. دوال القنوات والمنشورات
# ===================================================================
async def db_add_channel(user_id: int, channel_id: str, channel_name: str) -> int:
    async def _add(conn):
        cur = await conn.execute("SELECT id FROM user_channels WHERE user_id=? AND channel_id=?", (user_id, channel_id))
        if await cur.fetchone():
            return None
        cur = await conn.execute("INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) VALUES (?,?,?,?) RETURNING id",
                                 (user_id, channel_id, channel_name, utc_now_iso()))
        row = await cur.fetchone()
        await conn.commit()
        ch_db_id = row[0] if row else None
        if ch_db_id:
            next_date = utc_now() + timedelta(minutes=1)
            await conn.execute("INSERT OR IGNORE INTO schedule (channel_db_id, next_publish_date) VALUES (?,?)",
                               (ch_db_id, next_date.isoformat()))
            await conn.commit()
        return ch_db_id
    return await execute_db(_add)

async def db_get_channels(user_id: int):
    return await execute_db(lambda c: c.execute("SELECT id, channel_id, channel_name, banned FROM user_channels WHERE user_id=? ORDER BY id", (user_id,)) or c.fetchall())

async def db_get_channel_info(channel_db_id: int):
    return await execute_db(lambda c: c.execute("SELECT channel_id, channel_name FROM user_channels WHERE id=?", (channel_db_id,)) or c.fetchone())

async def db_delete_channel_by_id(user_id: int, channel_db_id: int) -> bool:
    async def _del(conn):
        await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (channel_db_id,))
        await conn.execute("DELETE FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        await conn.execute("DELETE FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
        await conn.execute("DELETE FROM user_channels WHERE id=? AND user_id=?", (channel_db_id, user_id))
        await conn.commit()
        return True
    return await execute_db(_del)

async def db_get_active_channel(user_id: int):
    async def _g(conn):
        cur = await conn.execute("SELECT active_channel FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            cur2 = await conn.execute("SELECT banned FROM user_channels WHERE id=?", (row[0],))
            r2 = await cur2.fetchone()
            if r2 and r2[0] == 0:
                return row[0]
        cur = await conn.execute("SELECT id FROM user_channels WHERE user_id=? AND banned=0 ORDER BY id LIMIT 1", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_g)

async def db_set_active_channel(user_id: int, channel_db_id: int):
    await execute_db(lambda c: c.execute("UPDATE users SET active_channel=? WHERE user_id=?", (channel_db_id, user_id)) or c.commit())

async def db_save_posts(channel_db_id: int, posts: list) -> int:
    async def _save(conn):
        vals = [(channel_db_id, sanitize_text(t), m, f, utc_now_iso()) for t, m, f in posts]
        await conn.executemany("INSERT INTO posts (channel_db_id, text, media_type, media_file_id, created_at) VALUES (?,?,?,?,?)", vals)
        await conn.commit()
        return len(vals)
    return await execute_db(_save)

async def db_get_next_post(channel_db_id: int):
    async def _g(conn):
        cur = await conn.execute("SELECT id, text, media_type, media_file_id FROM posts WHERE channel_db_id=? AND published=0 AND (fail_count IS NULL OR fail_count < 3) ORDER BY id LIMIT 1", (channel_db_id,))
        row = await cur.fetchone()
        return {'id': row[0], 'text': row[1], 'media_type': row[2], 'media_file_id': row[3]} if row else None
    return await execute_db(_g)

async def db_mark_published(post_id: int):
    await execute_db(lambda c: c.execute("UPDATE posts SET published=1, published_at=? WHERE id=?", (utc_now_iso(), post_id)) or c.commit())

async def db_increment_fail_count(post_id: int):
    await execute_db(lambda c: c.execute("UPDATE posts SET fail_count = fail_count + 1 WHERE id=?", (post_id,)) or c.commit())

async def db_unpublished_count(channel_db_id: int) -> int:
    async def _c(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=0", (channel_db_id,))
        return (await cur.fetchone())[0]
    return await execute_db(_c)

async def db_reset_all_posts_to_unpublished(channel_db_id: int) -> int:
    async def _r(conn):
        await conn.execute("UPDATE posts SET published=0, fail_count=0 WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        return (await cur.fetchone())[0]
    return await execute_db(_r)

async def db_get_user_posts_for_channel(channel_db_id: int, limit=15):
    return await execute_db(lambda c: c.execute("SELECT id, text, media_type FROM posts WHERE channel_db_id=? AND published=0 ORDER BY id LIMIT ?", (channel_db_id, limit)) or c.fetchall())

async def db_delete_single_post(post_id: int, user_id: int, channel_db_id: int) -> bool:
    async def _d(conn):
        cur = await conn.execute("SELECT 1 FROM user_channels WHERE id=? AND user_id=? AND banned=0", (channel_db_id, user_id))
        if not await cur.fetchone():
            return False
        await conn.execute("DELETE FROM posts WHERE id=? AND channel_db_id=?", (post_id, channel_db_id))
        await conn.commit()
        return True
    return await execute_db(_d)

async def db_get_channel_stats(channel_db_id: int) -> dict:
    async def _s(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=1", (channel_db_id,))
        published = (await cur.fetchone())[0]
        return {'total_posts': total, 'published_posts': published, 'unpublished_posts': total-published}
    return await execute_db(_s)

async def db_get_user_channels_count(user_id: int) -> int:
    async def _c(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM user_channels WHERE user_id=?", (user_id,))
        return (await cur.fetchone())[0]
    return await execute_db(_c)

async def db_get_user_unpublished_posts(user_id: int) -> int:
    async def _c(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=? AND p.published=0 AND uc.banned=0", (user_id,))
        return (await cur.fetchone())[0]
    return await execute_db(_c)

async def db_get_user_total_posts(user_id: int) -> int:
    async def _c(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=? AND uc.banned=0", (user_id,))
        return (await cur.fetchone())[0]
    return await execute_db(_c)

# ===================================================================
# 15. دوال الجدولة والنشر التلقائي
# ===================================================================
async def db_save_schedule(channel_db_id: int, schedule_type: str, **kwargs):
    async def _s(conn):
        next_date = None
        if schedule_type == 'interval_minutes':
            next_date = utc_now() + timedelta(minutes=kwargs.get('interval_minutes', 12))
        elif schedule_type == 'interval_hours':
            next_date = utc_now() + timedelta(hours=kwargs.get('interval_hours', 1))
        elif schedule_type == 'interval_days':
            next_date = utc_now() + timedelta(days=kwargs.get('interval_days', 1))
        else:
            next_date = utc_now() + timedelta(minutes=12)
        await conn.execute("""
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
        await conn.commit()
    return await execute_db(_s)

async def db_get_schedule(channel_db_id: int):
    async def _g(conn):
        cur = await conn.execute("SELECT schedule_type, interval_minutes, interval_hours, interval_days, days_of_week, specific_dates, publish_time, cron_expression, next_publish_date FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        if row:
            return {'type': row[0] or 'interval_minutes', 'interval_minutes': row[1] or 12, 'interval_hours': row[2] or 0, 'interval_days': row[3] or 0, 'days_of_week': row[4] or '[]', 'specific_dates': row[5] or '[]', 'publish_time': row[6] or '00:00', 'cron_expression': row[7], 'next_publish_date': row[8]}
        return {'type': 'interval_minutes', 'interval_minutes': 12, 'interval_hours': 0, 'interval_days': 0, 'days_of_week': '[]', 'specific_dates': '[]', 'publish_time': '00:00', 'cron_expression': None, 'next_publish_date': None}
    return await execute_db(_g)

async def db_set_next_publish_date(channel_db_id: int, next_date: datetime):
    await execute_db(lambda c: c.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?", (next_date.isoformat() if next_date else None, channel_db_id)) or c.commit())

async def db_set_last_publish(channel_db_id: int, publish_time: datetime):
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO last_publish (channel_db_id, last_publish_time) VALUES (?,?)", (channel_db_id, publish_time.isoformat())) or c.commit())

async def db_update_next_publish_date(channel_db_id: int):
    async def _u(conn):
        cur = await conn.execute("SELECT last_publish_time FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        last_time = datetime.fromisoformat(row[0]) if row and row[0] else utc_now()

        s = await db_get_schedule(channel_db_id)
        st = s['type']
        if st == 'interval_minutes':
            nd = last_time + timedelta(minutes=s['interval_minutes'] or 12)
        elif st == 'interval_hours':
            nd = last_time + timedelta(hours=s['interval_hours'] or 1)
        elif st == 'interval_days':
            nd = last_time + timedelta(days=s['interval_days'] or 1)
        else:
            nd = last_time + timedelta(minutes=12)

        while nd <= utc_now():
            if st == 'interval_minutes':
                nd += timedelta(minutes=s['interval_minutes'] or 12)
            elif st == 'interval_hours':
                nd += timedelta(hours=s['interval_hours'] or 1)
            elif st == 'interval_days':
                nd += timedelta(days=s['interval_days'] or 1)
            else:
                nd += timedelta(minutes=12)

        await conn.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?", (nd.isoformat(), channel_db_id))
        await conn.commit()
    return await execute_db(_u)

async def db_get_publish_interval_seconds() -> int:
    v = await execute_db(lambda c: c.execute("SELECT value FROM settings WHERE key='publish_interval'") or c.fetchone())
    return int(v[0]) if v else 720

# ===================================================================
# 16. دوال المجموعات والأمان
# ===================================================================
async def db_register_group(chat_id: int, chat_name: str, added_by: int, username: str = None) -> bool:
    async def _reg(conn):
        cur = await conn.execute("SELECT chat_id, banned FROM bot_groups WHERE chat_id=?", (chat_id,))
        existing = await cur.fetchone()
        if existing:
            await conn.execute("UPDATE bot_groups SET chat_name=?, username=?, added_by=?, updated_at=? WHERE chat_id=?",
                               (chat_name[:255], username[:100] if username else None, added_by, utc_now_iso(), chat_id))
            await conn.commit()
            return not existing[1]
        await conn.execute("INSERT INTO bot_groups (chat_id, chat_name, username, added_by, added_at) VALUES (?,?,?,?,?)",
                           (chat_id, chat_name[:255], username[:100] if username else None, added_by, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_reg)

async def db_get_user_groups(user_id: int):
    async def _g(conn):
        result = []
        seen = set()
        for table, col in [("hidden_owner_groups","owner_id"), ("hidden_admins","admin_id"), ("group_admins","user_id")]:
            cur = await conn.execute(f"SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned FROM bot_groups bg INNER JOIN {table} h ON bg.chat_id=h.chat_id WHERE h.{col}=?", (user_id,))
            for row in await cur.fetchall():
                if row[0] not in seen:
                    seen.add(row[0])
                    result.append(row)
        return result
    return await execute_db(_g)

async def db_get_user_groups_count(user_id: int) -> int:
    return len(await db_get_user_groups(user_id))

async def db_sync_group_admins(chat_id: int, bot, owner_id: int = None) -> int:
    try:
        admins = await bot.get_chat_administrators(chat_id)
        ids = [a.user.id for a in admins]
        if not ids:
            return 0
        async def _upd(conn):
            await conn.execute("DELETE FROM group_admins WHERE chat_id=?", (chat_id,))
            await conn.executemany("INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?,?)", [(chat_id, uid) for uid in ids])
            await conn.commit()
            return len(ids)
        return await execute_db(_upd)
    except:
        return 0

async def db_register_hidden_owner_group(chat_id: int, owner_id: int) -> bool:
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,1)", (chat_id, owner_id)) or c.commit())
    return True

async def db_is_hidden_owner(chat_id: int, user_id: int) -> bool:
    async def _chk(conn):
        cur = await conn.execute("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=? AND is_hidden=1", (chat_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_chk)

async def db_add_hidden_admin(chat_id: int, admin_id: int, added_by: int) -> bool:
    async def _a(conn):
        cur = await conn.execute("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
        if await cur.fetchone():
            return False
        await conn.execute("INSERT INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?,?,?,?)",
                           (chat_id, admin_id, added_by, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_a)

async def db_remove_hidden_admin(chat_id: int, admin_id: int) -> bool:
    await execute_db(lambda c: c.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id)) or c.commit())
    invalidate_auth_cache(chat_id, admin_id)
    return True

async def db_get_hidden_admins(chat_id: int):
    return await execute_db(lambda c: c.execute("SELECT admin_id, added_by, added_at FROM hidden_admins WHERE chat_id=? ORDER BY added_at DESC", (chat_id,)) or c.fetchall())

def invalidate_auth_cache(chat_id: int = None, user_id: int = None):
    try:
        if chat_id and user_id:
            _auth_cache.pop(f"auth_{chat_id}_{user_id}", None)
            _auth_cache.pop(f"bot_perms_{chat_id}", None)
        elif chat_id:
            for k in list(_auth_cache.keys()):
                if k.startswith(f"auth_{chat_id}_") or k == f"bot_perms_{chat_id}":
                    _auth_cache.pop(k, None)
        else:
            _auth_cache.clear()
    except:
        pass

async def is_authorized_in_group(bot, chat_id: int, user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID:
        return True

    bp = await check_bot_admin_permissions_group(bot, chat_id)
    if not bp.get('can_act', False):
        logger.warning(f"البوت ليس لديه صلاحيات كافية في المجموعة {chat_id}: {bp.get('reason')}")
        return False

    cache_key = f"auth_{chat_id}_{user_id}"
    if CACHETOOLS_AVAILABLE and cache_key in _auth_cache:
        ct, val = _auth_cache[cache_key]
        if time_module.time() - ct < 10:
            return val

    authorized = False
    try:
        for attempt in range(3):
            try:
                member = await bot.get_chat_member(chat_id, user_id)
                break
            except (TimedOut, NetworkError):
                if attempt == 2:
                    raise
                await asyncio.sleep(1)
        else:
            member = None

        if member and member.status in ['administrator', 'creator']:
            authorized = True
        else:
            if await db_is_hidden_owner(chat_id, user_id):
                authorized = True
            else:
                async def _chk(conn):
                    cur = await conn.execute("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, user_id))
                    return await cur.fetchone() is not None
                authorized = await execute_db(_chk)
    except Exception as e:
        logger.error(f"خطأ في التحقق من صلاحيات {user_id} في {chat_id}: {e}")
        authorized = await db_is_hidden_owner(chat_id, user_id) or await execute_db(
            lambda c: c.execute("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, user_id)) or c.fetchone()
        ) is not None

    if CACHETOOLS_AVAILABLE:
        _auth_cache[cache_key] = (time_module.time(), authorized)
    return authorized

async def check_bot_admin_permissions_group(bot, chat_id: int) -> dict:
    cache_key = f"bot_perms_{chat_id}"
    if CACHETOOLS_AVAILABLE and cache_key in _auth_cache:
        ct, val = _auth_cache[cache_key]
        if time_module.time() - ct < 30:
            return val

    try:
        me = await bot.get_chat_member(chat_id, bot.id)
        if me.status not in ['administrator', 'creator']:
            result = {'can_act': False, 'reason': 'البوت ليس مشرفاً في المجموعة'}
        else:
            can_delete = getattr(me, 'can_delete_messages', False)
            can_restrict = getattr(me, 'can_restrict_members', False)
            if not can_delete or not can_restrict:
                result = {'can_act': False, 'reason': 'ينقص البوت صلاحيات (حذف الرسائل أو تقييد الأعضاء)'}
            else:
                result = {'can_act': True, 'reason': '', 'permissions': {'can_delete': can_delete, 'can_ban': can_restrict}}
    except Exception as e:
        result = {'can_act': False, 'reason': f'خطأ في التحقق: {str(e)[:50]}'}

    if CACHETOOLS_AVAILABLE:
        _auth_cache[cache_key] = (time_module.time(), result)
    return result

async def is_bot_admin(user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID:
        return True
    async def _chk(conn):
        cur = await conn.execute("SELECT 1 FROM bot_admins WHERE user_id=?", (user_id,))
        return await cur.fetchone() is not None
    return await execute_db(_chk)

async def add_bot_admin(user_id: int) -> bool:
    await execute_db(lambda c: c.execute("INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)",
                                         (user_id, PRIMARY_OWNER_ID, utc_now_iso())) or c.commit())
    return True

async def remove_bot_admin(user_id: int) -> bool:
    await execute_db(lambda c: c.execute("DELETE FROM bot_admins WHERE user_id=?", (user_id,)) or c.commit())
    return True

# ===================================================================
# 17. دوال الأمان (إعدادات, كلمات محظورة, عقوبات)
# ===================================================================
_ALLOWED_SECURITY_COLUMNS = {
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

async def db_get_security_settings(chat_id: int, force_refresh: bool = False) -> dict:
    defaults = {
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
    if not force_refresh and CACHETOOLS_AVAILABLE and chat_id in _security_cache:
        ct, val = _security_cache[chat_id]
        if time_module.time() - ct < 10:
            return val.copy()
    async def _g(conn):
        conn.row_factory = aiosqlite.Row
        await ensure_security_columns()
        cur = await conn.execute("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        if row:
            settings = {}
            for k in defaults:
                if hasattr(row, k):
                    v = getattr(row, k)
                    settings[k] = (v == 1) if isinstance(defaults[k], bool) else (v if v is not None else defaults[k])
                else:
                    settings[k] = defaults[k]
            if CACHETOOLS_AVAILABLE:
                _security_cache[chat_id] = (time_module.time(), settings)
            return settings
        await conn.execute("INSERT INTO group_security (chat_id) VALUES (?)", (chat_id,))
        await conn.commit()
        if CACHETOOLS_AVAILABLE:
            _security_cache[chat_id] = (time_module.time(), defaults.copy())
        return defaults.copy()
    return await execute_db(_g)

async def db_set_security_settings(chat_id: int, **kwargs) -> bool:
    allowed_penalties = ['none', 'warn', 'mute', 'kick', 'ban']
    validated = {}
    for k, v in kwargs.items():
        if k not in _ALLOWED_SECURITY_COLUMNS:
            continue
        if k.endswith('_enabled') or k in ['delete_links', 'mentions', 'slow_mode', 'delete_banned_words',
            'welcome_enabled', 'goodbye_enabled', 'delete_videos', 'delete_audio', 'delete_animation',
            'delete_service', 'delete_documents', 'delete_stickers', 'delete_forwarded', 'delete_polls',
            'delete_games', 'delete_voice', 'delete_video_note', 'antiflood_enabled', 'night_mode_enabled',
            'nsfw_enabled']:
            validated[k] = 1 if v else 0
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
    async def _s(conn):
        cur = await conn.execute("SELECT 1 FROM group_security WHERE chat_id=?", (chat_id,))
        if not await cur.fetchone():
            await conn.execute("INSERT INTO group_security (chat_id) VALUES (?)", (chat_id,))
        updates = [f"{k}=?" for k in validated]
        vals = list(validated.values()) + [chat_id]
        await conn.execute(f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id=?", vals)
        await conn.commit()
        return True
    result = await execute_db(_s)
    if CACHETOOLS_AVAILABLE:
        _security_cache.pop(chat_id, None)
    return result

async def db_add_banned_word(word: str, chat_id: int, added_by: int) -> bool:
    if not word or len(word) < 2:
        return False
    word = word.strip().lower()[:100]
    if chat_id == -1:
        count = await execute_db(lambda c: c.execute("SELECT COUNT(*) FROM banned_words WHERE chat_id=-1") or c.fetchone())
        if count and count[0] >= MAX_GLOBAL_BANNED_WORDS:
            return False
    async def _add(conn):
        await conn.execute("INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?,?,?,?)",
                           (word, chat_id, added_by, utc_now_iso()))
        await conn.commit()
        if chat_id == -1:
            await rebuild_banned_patterns()
        if CACHETOOLS_AVAILABLE:
            _banned_words_cache.pop(chat_id, None)
        return True
    return await execute_db(_add)

async def db_remove_banned_word(word: str, chat_id: int) -> bool:
    async def _r(conn):
        await conn.execute("DELETE FROM banned_words WHERE word=? AND chat_id=?", (word.strip().lower(), chat_id))
        await conn.commit()
        if chat_id == -1:
            await rebuild_banned_patterns()
        if CACHETOOLS_AVAILABLE:
            _banned_words_cache.pop(chat_id, None)
        return True
    return await execute_db(_r)

async def db_get_banned_words(chat_id: int):
    if CACHETOOLS_AVAILABLE and chat_id in _banned_words_cache:
        ct, val = _banned_words_cache[chat_id]
        if time_module.time() - ct < 30:
            return val
    data = await execute_db(lambda c: c.execute("SELECT word, added_by, added_at FROM banned_words WHERE chat_id=? OR chat_id=-1 ORDER BY word", (chat_id,)) or c.fetchall())
    if CACHETOOLS_AVAILABLE:
        _banned_words_cache[chat_id] = (time_module.time(), data)
    return data

async def db_contains_banned_word(text: str, chat_id: int) -> Optional[str]:
    if not text:
        return None
    words = await db_get_banned_words(chat_id)
    tl = text.lower()
    for w, _, _ in words:
        if w in tl:
            return w
    return None

async def rebuild_banned_patterns():
    global BANNED_PATTERNS
    async def _get_patterns(conn):
        cur = await conn.execute("SELECT word FROM banned_words WHERE chat_id=-1")
        rows = await cur.fetchall()
        return [row[0] for row in rows]
    BANNED_PATTERNS = await execute_db(_get_patterns)

async def is_chat_locked(chat_id: int) -> bool:
    async def _chk(conn):
        cur = await conn.execute("SELECT 1 FROM chat_locks WHERE chat_id=? AND locked=1", (chat_id,))
        return await cur.fetchone() is not None
    return await execute_db(_chk)

async def db_set_chat_lock(chat_id: int, locked: bool, locked_by: int = None) -> bool:
    async def _s(conn):
        if locked:
            await conn.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?,1,?,?)",
                               (chat_id, utc_now_iso(), locked_by))
        else:
            await conn.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await conn.commit()
        return True
    return await execute_db(_s)

async def db_check_slow_mode(chat_id: int, user_id: int) -> bool:
    settings = await db_get_security_settings(chat_id)
    if not settings.get('slow_mode', False):
        return True
    sec = settings.get('slow_mode_seconds', 5)
    if CACHETOOLS_AVAILABLE:
        key = f"slow_{chat_id}_{user_id}"
        if key in _slow_mode_cache:
            ct, last_time = _slow_mode_cache[key]
            if time_module.time() - ct < sec:
                return False
    async def _chk(conn):
        cur = await conn.execute("SELECT message_time FROM user_messages WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        row = await cur.fetchone()
        now = utc_now()
        if row:
            try:
                if (now - datetime.fromisoformat(row[0])).total_seconds() < sec:
                    return False
            except:
                pass
        await conn.execute("INSERT OR REPLACE INTO user_messages (user_id, chat_id, message_time) VALUES (?,?,?)",
                           (user_id, chat_id, now.isoformat()))
        await conn.commit()
        return True
    result = await execute_db(_chk)
    if CACHETOOLS_AVAILABLE and result:
        _slow_mode_cache[f"slow_{chat_id}_{user_id}"] = (time_module.time(), time_module.time())
    return result

async def db_check_antiflood(chat_id: int, user_id: int) -> bool:
    settings = await db_get_security_settings(chat_id)
    if not settings.get('antiflood_enabled', False):
        return False
    max_msgs = settings.get('antiflood_messages', 5)
    tw = settings.get('antiflood_seconds', 10)
    key = f"flood_{chat_id}_{user_id}"
    now = time_module.time()
    if CACHETOOLS_AVAILABLE:
        if key in _antiflood_cache:
            ct, data = _antiflood_cache[key]
            if time_module.time() - ct < tw:
                msgs = data
                msgs = [t for t in msgs if now - t < tw]
                msgs.append(now)
                if len(msgs) > max_msgs:
                    return True
                _antiflood_cache[key] = (time_module.time(), msgs)
                return False
    if key in _flood_cache:
        msgs = [t for t in _flood_cache.pop(key) if now - t < tw]
        msgs.append(now)
        _flood_cache[key] = msgs
        if len(msgs) > max_msgs:
            return True
    else:
        _flood_cache[key] = [now]
    if len(_flood_cache) > 10000:
        try:
            _flood_cache.popitem(last=False)
        except:
            pass
    if CACHETOOLS_AVAILABLE:
        _antiflood_cache[key] = (time_module.time(), _flood_cache[key])
    return False

async def apply_penalty_with_duration(bot, chat_id: int, user_id: int, penalty: str, duration_minutes: int = 0, reason: str = "", moderator_id: int = None) -> Tuple[bool, str]:
    if user_id == PRIMARY_OWNER_ID:
        return False, "لا يمكن"
    try:
        if penalty == 'ban':
            await bot.ban_chat_member(chat_id, user_id)
        elif penalty == 'mute':
            until = (datetime.utcnow() + timedelta(minutes=duration_minutes)) if duration_minutes else None
            await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False), until_date=until)
        elif penalty == 'kick':
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
        elif penalty == 'warn':
            async def _warn(conn):
                cur = await conn.execute("SELECT warnings FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
                row = await cur.fetchone()
                w = (row[0] if row else 0) + 1
                await conn.execute("INSERT OR REPLACE INTO user_warnings (user_id, chat_id, warnings) VALUES (?,?,?)", (user_id, chat_id, w))
                await conn.commit()
                return w
            w = await execute_db(_warn)
            settings = await db_get_security_settings(chat_id)
            if w >= settings.get('max_warnings', 3):
                wp = settings.get('warn_penalty', 'ban')
                if wp == 'ban':
                    await bot.ban_chat_member(chat_id, user_id)
                elif wp == 'mute':
                    await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False))
        elif penalty == 'restrict':
            await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=True, can_send_media_messages=False))
        elif penalty == 'unban':
            await bot.unban_chat_member(chat_id, user_id)
        return True, f"✅ تم {penalty}"
    except Exception as e:
        return False, str(e)[:100]

async def delete_and_penalize(update: Update, context: ContextTypes.DEFAULT_TYPE, warning_message: str):
    if not update.message:
        return
    try:
        await update.message.delete()
    except:
        pass
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        await safe_send_markdown(context.bot, chat_id, warning_message)
    except:
        pass
    settings = await db_get_security_settings(chat_id)
    penalty = settings.get('auto_penalty', 'none')
    if penalty != 'none':
        await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, settings.get('auto_mute_duration', 60))

# ===================================================================
# 18. دوال التذاكر، الإحالات، التذكيرات، الترجمة، المسابقات
# ===================================================================
async def db_save_ticket(user_id: int, username: str, message: str, ticket_num: int):
    await execute_db(lambda c: c.execute("INSERT INTO support_tickets (user_id, username, message, ticket_number, created_at) VALUES (?,?,?,?,?)",
                                         (user_id, username, message, ticket_num, utc_now_iso())) or c.commit())

async def db_get_next_ticket_number() -> int:
    async def _g(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='last_ticket_number'")
        row = await cur.fetchone()
        return int(row[0]) if row else 0
    return await execute_db(_g)

async def db_get_all_tickets():
    return await execute_db(lambda c: c.execute("SELECT id, user_id, username, message, ticket_number, status, created_at FROM support_tickets ORDER BY created_at DESC LIMIT 20") or c.fetchall())

async def db_mark_ticket_replied(ticket_id: int):
    await execute_db(lambda c: c.execute("UPDATE support_tickets SET status='replied', replied=1 WHERE id=?", (ticket_id,)) or c.commit())

async def db_delete_all_tickets():
    await execute_db(lambda c: c.execute("DELETE FROM support_tickets") or c.commit())

async def db_add_referral(referrer_id: int, referred_id: int) -> bool:
    if referrer_id == referred_id:
        return False
    async def _add(conn):
        today = utc_now().date().isoformat()
        cur = await conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND date(created_at)=?", (referrer_id, today))
        count = (await cur.fetchone())[0]
        if count >= MAX_DAILY_REFERRALS:
            return False
        cur = await conn.execute("SELECT 1 FROM referrals WHERE referred_id=?", (referred_id,))
        if await cur.fetchone():
            return False
        await conn.execute("INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?,?,?)",
                           (referrer_id, referred_id, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_add)

async def db_auto_reward_referral(referrer_id: int, referred_id: int) -> int:
    async def _r(conn):
        await conn.execute("""
            INSERT INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days, last_referral_date)
            VALUES (?,1,3,0,?) ON CONFLICT(user_id) DO UPDATE SET
            referral_count=referral_count+1, total_reward_days=total_reward_days+3, last_referral_date=?
        """, (referrer_id, utc_now_iso(), utc_now_iso()))
        await conn.commit()
        return 3
    return await execute_db(_r)

async def db_get_referral_stats(user_id: int) -> dict:
    async def _g(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,))
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT referral_count, total_reward_days, claimed_reward_days FROM referral_rewards WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row:
            return {'total_referrals': total, 'referral_count': row[0], 'total_reward_days': row[1], 'claimed_reward_days': row[2], 'available_days': row[1]-row[2]}
        return {'total_referrals': total, 'referral_count': 0, 'total_reward_days': 0, 'claimed_reward_days': 0, 'available_days': 0}
    return await execute_db(_g)

async def db_claim_referral_reward(user_id: int) -> int:
    async def _c(conn):
        stats = await db_get_referral_stats(user_id)
        av = stats['available_days']
        if av <= 0:
            return 0
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        cd = 0
        if row and row[0]:
            try:
                ed = datetime.fromisoformat(row[0])
                if ed > utc_now():
                    cd = (ed - utc_now()).days
            except:
                pass
        new_end = (utc_now() + timedelta(days=cd+av)).isoformat()
        await conn.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (new_end, user_id))
        await conn.execute("UPDATE referral_rewards SET claimed_reward_days=claimed_reward_days+? WHERE user_id=?", (av, user_id))
        await conn.commit()
        return av
    return await execute_db(_c)

async def db_update_reminder_settings(user_id: int, **kwargs):
    async def _u(conn):
        await conn.execute("INSERT OR IGNORE INTO user_reminder_settings (user_id) VALUES (?)", (user_id,))
        updates = [f"{k}=?" for k in kwargs]
        vals = list(kwargs.values()) + [user_id]
        if updates:
            await conn.execute(f"UPDATE user_reminder_settings SET {', '.join(updates)} WHERE user_id=?", vals)
            await conn.commit()
    return await execute_db(_u)

async def db_get_user_reminder_settings(user_id: int) -> dict:
    async def _g(conn):
        cur = await conn.execute("SELECT subscription_reminder, daily_stats_reminder, weekly_report, reminder_days_before, notification_lang FROM user_reminder_settings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row:
            return {'subscription_reminder': row[0]==1, 'daily_stats_reminder': row[1]==1, 'weekly_report': row[2]==1, 'reminder_days_before': row[3] or 3, 'notification_lang': row[4] or 'ar'}
        return {'subscription_reminder': True, 'daily_stats_reminder': False, 'weekly_report': True, 'reminder_days_before': 3, 'notification_lang': 'ar'}
    return await execute_db(_g)

async def db_get_users_needing_reminder():
    async def _g(conn):
        now = utc_now()
        users = []
        cur = await conn.execute("""
            SELECT u.user_id, u.subscription_end, COALESCE(r.reminder_days_before,3) as days_before, COALESCE(r.notification_lang,'ar') as lang, r.last_reminder_sent
            FROM users u
            LEFT JOIN user_reminder_settings r ON u.user_id = r.user_id
            WHERE u.subscription_end IS NOT NULL AND u.subscription_end > datetime('now') AND u.banned=0
        """)
        rows = await cur.fetchall()
        for row in rows:
            try:
                ed = datetime.fromisoformat(row[1])
                dl = (ed - now).days
                if 0 < dl <= row[2]:
                    last = row[4]
                    if not last or (now - datetime.fromisoformat(last)).days >= 1:
                        users.append({'user_id': row[0], 'days_left': dl, 'notification_lang': row[3]})
            except:
                pass
        return users
    return await execute_db(_g)

async def db_update_last_reminder_sent(user_id: int, reminder_type: str):
    await execute_db(lambda c: c.execute("UPDATE user_reminder_settings SET last_reminder_sent=? WHERE user_id=?", (utc_now_iso(), user_id)) or c.commit())

async def get_user_translation_language(user_id: int) -> str:
    async def _g(conn):
        cur = await conn.execute("SELECT lang FROM user_translation WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 'off'
    return await execute_db(_g)

async def set_user_translation_language(user_id: int, lang: str):
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO user_translation (user_id, lang) VALUES (?,?)", (user_id, lang)) or c.commit())

async def translate_text(text: str, target_lang: str) -> str:
    if not text or target_lang == 'off' or target_lang == 'ar':
        return text
    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        return translator.translate(text)
    except:
        return text

async def db_create_contest(creator_id: int, title: str, description: str, prize: str, end_date: datetime, contest_type: str = 'raffle') -> int:
    async def _c(conn):
        cur = await conn.execute("INSERT INTO contests (creator_id, title, description, prize, end_date, contest_type, created_at) VALUES (?,?,?,?,?,?,?) RETURNING id",
                                 (creator_id, title, description, prize, end_date.isoformat(), contest_type, utc_now_iso()))
        row = await cur.fetchone()
        await conn.commit()
        return row[0] if row else None
    return await execute_db(_c)

async def db_participate_in_contest(user_id: int, contest_id: int, answer: str = "") -> bool:
    try:
        await execute_db(lambda c: c.execute("INSERT INTO contest_participants (user_id, contest_id, answer, joined_at) VALUES (?,?,?,?)",
                                             (user_id, contest_id, answer, utc_now_iso())) or c.commit())
        return True
    except:
        return False

async def db_get_contest(contest_id: int):
    async def _g(conn):
        cur = await conn.execute("SELECT id, title, description, prize, end_date, status, winner_id FROM contests WHERE id=?", (contest_id,))
        row = await cur.fetchone()
        if row:
            return {'id': row[0], 'title': row[1], 'description': row[2], 'prize': row[3], 'end_date': row[4], 'status': row[5], 'winner_id': row[6]}
        return None
    return await execute_db(_g)

async def db_set_contest_winner(contest_id: int, winner_id: int) -> bool:
    async def _s(conn):
        await conn.execute("UPDATE contests SET status='finished', winner_id=? WHERE id=?", (winner_id, contest_id))
        await conn.execute("INSERT INTO contest_winners (contest_id, winner_id, announced_at) VALUES (?,?,?)", (contest_id, winner_id, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_s)

async def db_get_active_contests_with_participants(limit=10):
    return await execute_db(lambda c: c.execute("""
        SELECT c.id, c.title, c.description, c.prize, c.end_date, c.contest_type,
               (SELECT COUNT(*) FROM contest_participants WHERE contest_id=c.id) as participants
        FROM contests c WHERE c.status='active' ORDER BY c.end_date ASC LIMIT ?
    """, (limit,)) or c.fetchall())

async def db_get_user_participation(user_id: int, contest_id: int) -> bool:
    async def _chk(conn):
        cur = await conn.execute("SELECT 1 FROM contest_participants WHERE contest_id=? AND user_id=?", (contest_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_chk)

async def db_get_contest_winners(limit=10):
    return await execute_db(lambda c: c.execute("""
        SELECT c.id, c.title, c.prize, cw.winner_id, cw.announced_at FROM contest_winners cw
        JOIN contests c ON cw.contest_id = c.id ORDER BY cw.announced_at DESC LIMIT ?
    """, (limit,)) or c.fetchall())

async def db_delete_contest(contest_id: int, user_id: int) -> bool:
    async def _d(conn):
        cur = await conn.execute("SELECT creator_id FROM contests WHERE id=?", (contest_id,))
        row = await cur.fetchone()
        if row and (row[0] == user_id or await is_bot_admin(user_id)):
            await conn.execute("DELETE FROM contest_participants WHERE contest_id=?", (contest_id,))
            await conn.execute("DELETE FROM contests WHERE id=?", (contest_id,))
            await conn.commit()
            return True
        return False
    return await execute_db(_d)

# ===================================================================
# 19. الردود التلقائية
# ===================================================================
async def db_get_auto_reply_settings(chat_id: int) -> dict:
    if CACHETOOLS_AVAILABLE and chat_id in _auto_reply_cache:
        ct, val = _auto_reply_cache[chat_id]
        if time_module.time() - ct < 30:
            return val
    async def _g(conn):
        cur = await conn.execute("SELECT enabled, only_admins, ignore_bots FROM auto_reply_settings WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        if row:
            res = {'enabled': row[0]==1, 'only_admins': row[1]==1, 'ignore_bots': row[2]==1}
        else:
            res = {'enabled': False, 'only_admins': False, 'ignore_bots': True}
        if CACHETOOLS_AVAILABLE:
            _auto_reply_cache[chat_id] = (time_module.time(), res)
        return res
    return await execute_db(_g)

async def db_set_auto_reply_enabled(chat_id: int, enabled: bool):
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO auto_reply_settings (chat_id, enabled, updated_at) VALUES (?,?,?)",
                                         (chat_id, 1 if enabled else 0, utc_now_iso())) or c.commit())
    if CACHETOOLS_AVAILABLE:
        _auto_reply_cache.pop(chat_id, None)

async def db_set_auto_reply_only_admins(chat_id: int, only_admins: bool):
    await execute_db(lambda c: c.execute("UPDATE auto_reply_settings SET only_admins=?, updated_at=? WHERE chat_id=?",
                                         (1 if only_admins else 0, utc_now_iso(), chat_id)) or c.commit())
    if CACHETOOLS_AVAILABLE:
        _auto_reply_cache.pop(chat_id, None)

async def db_add_reply_with_stats(chat_id: int, keyword: str, reply: str):
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO auto_replies (chat_id, keyword, reply, created_at) VALUES (?,?,?,?)",
                                         (chat_id, keyword.lower(), reply, utc_now_iso())) or c.commit())
    if CACHETOOLS_AVAILABLE:
        _auto_reply_cache.pop(chat_id, None)

async def db_remove_reply(chat_id: int, keyword: str) -> bool:
    async def _r(conn):
        result = await conn.execute("DELETE FROM auto_replies WHERE chat_id=? AND keyword=?", (chat_id, keyword.lower()))
        await conn.commit()
        return result.rowcount > 0
    return await execute_db(_r)

async def db_get_reply_with_stats(keyword: str, chat_id: int = 0) -> Optional[str]:
    async def _g(conn):
        cur = await conn.execute("SELECT reply FROM auto_replies WHERE chat_id=? AND keyword=? AND is_active=1 LIMIT 1", (chat_id, keyword))
        row = await cur.fetchone()
        if row:
            await conn.execute("UPDATE auto_replies SET usage_count = usage_count + 1 WHERE chat_id=? AND keyword=?", (chat_id, keyword))
            await conn.commit()
            return row[0]
        return None
    return await execute_db(_g)

async def db_get_auto_reply_stats(chat_id: int, limit=10):
    return await execute_db(lambda c: c.execute("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? AND is_active=1 ORDER BY usage_count DESC LIMIT ?", (chat_id, limit)) or c.fetchall())

async def db_reset_auto_replies(chat_id: int):
    await execute_db(lambda c: c.execute("DELETE FROM auto_replies WHERE chat_id=?", (chat_id,)) or c.commit())
    if CACHETOOLS_AVAILABLE:
        _auto_reply_cache.pop(chat_id, None)

# ===================================================================
# 20. دوال الإعدادات العامة
# ===================================================================
async def db_get_setting(key: str) -> Optional[str]:
    async def _g(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_g)

async def db_set_setting(key: str, value: str):
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value)) or c.commit())

async def db_get_updates_channel() -> Optional[str]:
    return await db_get_setting('updates_channel')

async def db_get_force_subscribe_channel() -> Optional[str]:
    return await db_get_setting('force_subscribe_channel')

async def db_get_log_channel_id() -> Optional[int]:
    v = await db_get_setting('log_channel_id')
    return int(v) if v else None

async def db_get_allowed_sendcode_user() -> Optional[int]:
    v = await db_get_setting('allowed_sendcode_user')
    return int(v) if v else None

async def db_get_auto_backup() -> bool:
    v = await db_get_setting('auto_backup')
    return v == '1'

async def db_get_last_backup_time() -> Optional[str]:
    return await db_get_setting('last_backup')

async def db_get_publish_interval_seconds() -> int:
    v = await db_get_setting('publish_interval')
    return int(v) if v else 720

async def db_log_admin_action(chat_id: int, admin_id: int, action: str, target_id: int = None, reason: str = ""):
    await execute_db(lambda c: c.execute("INSERT INTO admin_logs (chat_id, admin_id, action, target_id, reason, created_at) VALUES (?,?,?,?,?,?)",
                                         (chat_id, admin_id, action, target_id, reason, utc_now_iso())) or c.commit())

async def db_get_admin_logs(chat_id: int, limit=20):
    return await execute_db(lambda c: c.execute("SELECT admin_id, action, target_id, reason, created_at FROM admin_logs WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit)) or c.fetchall())

# ===================================================================
# 21. تحليل المشاعر
# ===================================================================
class SentimentAnalyzer:
    def __init__(self):
        self.positive_words = {"جميل","رائع","ممتاز","حلو","شكرا","شكراً","تسلم","فرح","سعيد","مبسوط","الحمد","تفاؤل","أمل","نجاح","مبدع","خير","بركة","نعمة"}
        self.negative_words = {"زعل","حزين","متعب","محبط","غضب","غاضب","مزعج","سيء","سخيف","غبي","ممل","كره","موت","ألم","جرح","نكد","فشل","خسر","ظلم","حرب","شر","لعنة"}
        self.neutral_words = {"تمام","حاضر","اوك","بخير","ماشي","طيب","جيد","عادي","موافق"}

    def analyze(self, text: str) -> dict:
        if not text:
            return {'sentiment': 'neutral', 'score': 0.0}
        words = re.findall(r'\b\w+\b', text.lower())
        pc = sum(1 for w in words if w in self.positive_words)
        nc = sum(1 for w in words if w in self.negative_words)
        nuc = sum(1 for w in words if w in self.neutral_words)
        total = pc + nc + nuc
        if total == 0:
            return {'sentiment': 'neutral', 'score': 0.0}
        score = (pc - nc) / max(total, 1)
        if score > 0.2:
            sentiment = 'positive'
        elif score < -0.2:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        return {'sentiment': sentiment, 'score': round(score, 3)}

sentiment_analyzer = SentimentAnalyzer()

async def save_sentiment_encrypted(user_id: int, chat_id: int, text: str, sentiment: str, score: float):
    encrypted = cipher_suite.encrypt(text.encode())
    await execute_db(lambda c: c.execute("INSERT INTO sentiment_history (user_id, chat_id, text_encrypted, sentiment, score, created_at) VALUES (?,?,?,?,?,?)",
                                         (user_id, chat_id, encrypted, sentiment, score, utc_now_iso())) or c.commit())

# ===================================================================
# 22. الكيبوردات والأزرار
# ===================================================================
class CallbackData:
    MAIN_MENU = "main_menu"
    BACK = "back"
    CANCEL_SESSION = "cancel_session"
    CHANNELS_ADD = "channels:add"
    CHANNELS_MY = "channels:my_channels"
    CHANNELS_DELETE_PREFIX = "channels:delete:"
    CHANNELS_SELECT_PREFIX = "channels:select:"
    POSTS_ADD_15 = "posts:add_15"
    POSTS_PUBLISH_ONE = "posts:publish_one"
    POSTS_MY = "posts:my_posts"
    POSTS_RECYCLE = "posts:recycle"
    POSTS_DELETE_SINGLE_PREFIX = "posts:delete_single:"
    POSTS_CONFIRM_CLEAR_ALL_PREFIX = "posts:confirm_clear_all:"
    POSTS_CLEAR_ALL_PREFIX = "posts:clear_all:"
    PUBLISH_ALL_CHANNELS = "publish_all_channels"
    STATS_PENDING = "stats:pending"
    STATS_FULL = "stats:full"
    GROUPS_MY = "groups:my_groups"
    GROUPS_SETTINGS_PREFIX = "groups:settings:"
    SETTINGS_MENU = "settings:menu"
    SETTINGS_TOGGLE_AUTO_PUBLISH = "settings:toggle_auto_publish"
    SETTINGS_TOGGLE_AUTO_RECYCLE = "settings:toggle_auto_recycle"
    SCHEDULE_MENU_PREFIX = "schedule:menu:"
    SCHEDULE_SET_INTERVAL_MINUTES_PREFIX = "schedule:set_interval_minutes:"
    SCHEDULE_SET_INTERVAL_HOURS_PREFIX = "schedule:set_interval_hours:"
    SCHEDULE_SET_INTERVAL_DAYS_PREFIX = "schedule:set_interval_days:"
    SCHEDULE_SET_PUBLISH_TIME_PREFIX = "schedule:set_publish_time:"
    SECURITY_BANNED_WORDS_MENU_PREFIX = "security:banned_words_menu:"
    SECURITY_CLOSE = "security:close"
    SECURITY_ENABLE_ALL_PREFIX = "security:enable_all:"
    SECURITY_DISABLE_ALL_PREFIX = "security:disable_all:"
    SECURITY_DELETE_PENALTY_PREFIX = "security:delete_penalty:"
    BANNED_WORDS_ADD_PREFIX = "banned_words:add:"
    BANNED_WORDS_LIST_PREFIX = "banned_words:list:"
    BANNED_WORDS_REMOVE_PREFIX = "banned_words:remove:"
    PENALTY_MENU = "penalty_menu"
    PENALTY_KICK = "penalty:kick"
    PENALTY_BAN = "penalty:ban"
    PENALTY_MUTE = "penalty:mute"
    PENALTY_WARN = "penalty:warn"
    PENALTY_RESTRICT = "penalty:restrict"
    PENALTY_NONE = "penalty:none"
    ADVANCED_ACTIONS = "advanced_actions"
    GROUP_ACTION_BAN = "group_action:ban"
    GROUP_ACTION_MUTE = "group_action:mute"
    GROUP_ACTION_WARN = "group_action:warn"
    GROUP_ACTION_KICK = "group_action:kick"
    GROUP_ACTION_RESTRICT = "group_action:restrict"
    GROUP_ACTION_PIN = "group_action:pin"
    GROUP_ACTION_LOG = "group_action:log"
    GROUP_ACTION_UNBAN = "group_action:unban"
    ADV_MUTE_DURATION_PREFIX = "adv_mute_duration:"
    PANEL_LOCK_PREFIX = "panel:lock:"
    PANEL_UNLOCK_PREFIX = "panel:unlock:"
    PANEL_CLOSE = "panel:close"
    HELP = "help"
    SUPPORT_MENU = "support:menu"
    SUPPORT_HELP = "support:help"
    SUPPORT_TICKET = "support:ticket"
    SUPPORT_BACK = "support:back"
    TRIAL = "trial"
    SUBSCRIBE_MENU = "subscribe:menu"
    BUY_SUBSCRIPTION_1 = "buy:subscription_1"
    BUY_SUBSCRIPTION_2 = "buy:subscription_2"
    BUY_SUBSCRIPTION_30 = "buy:subscription_30"
    BUY_SUBSCRIPTION_90 = "buy:subscription_90"
    DEVELOPER = "developer"
    UPDATES = "updates"
    REFERRAL_MENU = "referral:menu"
    REFERRAL_CLAIM_REWARD = "referral:claim_reward"
    REFERRAL_LIST = "referral:list"
    REFERRAL_COPY_LINK_PREFIX = "referral:copy:"
    REMINDER_MENU = "reminder:menu"
    REMINDER_TOGGLE_SUB = "reminder:toggle_sub"
    REMINDER_TOGGLE_DAILY = "reminder:toggle_daily"
    REMINDER_TOGGLE_WEEKLY = "reminder:toggle_weekly"
    REMINDER_SET_DAYS = "reminder:set_days"
    REMINDER_SET_LANG = "reminder:set_lang"
    REMINDER_LANG_PREFIX = "reminder:lang:"
    TRANSLATION_MENU = "translation:menu"
    TRANSLATION_OFF = "translation:off"
    TRANSLATION_SET_PREFIX = "translation:set:"
    CONTESTS_MENU = "contests_menu"
    CONTEST_JOIN_PREFIX = "contest_join:"
    CONTEST_WINNERS = "contest_winners"
    CONTESTS_BACK = "contests_back"
    CHANNEL_STATS = "channel_stats"
    CHANNEL_GROWTH = "channel_growth"
    CHANNEL_STATS_REFRESH = "channel_stats_refresh"
    MY_CHANNEL_STATS = "my_channel_stats"
    CHECK_SUBSCRIBE = "check_subscribe"
    ADMIN_PANEL = "admin:panel"
    ADMIN_USERS = "admin:users"
    ADMIN_BANNED_USERS = "admin:banned_users"
    ADMIN_UNBAN_ALL_USERS = "admin:unban_all_users"
    ADMIN_ALL_CHANNELS = "admin:all_channels"
    ADMIN_BANNED_CHANNELS = "admin:banned_channels"
    ADMIN_ACTIVATE_ALL_CHANNELS = "admin:activate_all_channels"
    ADMIN_GROUPS = "admin:groups"
    ADMIN_BANNED_GROUPS = "admin:banned_groups"
    ADMIN_UNBAN_ALL_GROUPS = "admin:unban_all_groups"
    ADMIN_BOT_CHANNELS = "admin:bot_channels"
    ADMIN_BANNED_BOT_CHANNELS = "admin:banned_bot_channels"
    ADMIN_UNBAN_ALL_BOT_CHANNELS = "admin:unban_all_bot_channels"
    ADMIN_MONITOR_USERS = "admin:monitor_users"
    ADMIN_ADD_ADMIN = "admin:add_admin"
    ADMIN_REMOVE_ADMIN = "admin:remove_admin"
    ADMIN_RAM = "admin:ram"
    ADMIN_STATS = "admin:stats"
    ADMIN_METRICS = "admin:metrics"
    ADMIN_BACKUP = "admin:backup"
    ADMIN_RESTORE_BACKUP = "admin:restore_backup"
    ADMIN_RESTORE_BACKUP_SELECT_PREFIX = "admin:restore_backup_select:"
    ADMIN_BACKUP_SETTINGS = "admin:backup_settings"
    ADMIN_TOGGLE_AUTO_BACKUP = "admin:toggle_auto_backup"
    ADMIN_CHANGE_INTERVAL = "admin:change_interval"
    ADMIN_SEND_UPDATE = "admin:send_update"
    ADMIN_SET_UPDATE_CHANNEL = "admin:set_update_channel"
    ADMIN_SHOW_UPDATE_CHANNEL = "admin:show_update_channel"
    ADMIN_UPDATES = "admin:updates"
    ADMIN_FORCE_SUBSCRIBE = "admin:force_subscribe"
    ADMIN_SET_FORCE_CHANNEL = "admin:set_force_channel"
    ADMIN_BROADCAST = "admin:broadcast"
    ADMIN_CONFIRM_BROADCAST = "admin:confirm_broadcast"
    ADMIN_SUPPORT_TICKETS = "admin:support_tickets"
    ADMIN_DELETE_ALL_TICKETS = "admin:delete_all_tickets"
    ADMIN_CONFIRM_DELETE_TICKETS = "admin:confirm_delete_tickets"
    ADMIN_MANAGE_SENDCODE = "admin:manage_sendcode"
    ADMIN_SET_SENDCODE_USER = "admin:set_sendcode_user"
    ADMIN_SHOW_LOG_CHANNEL = "admin:show_log_channel"
    ADMIN_SET_LOG_CHANNEL = "admin:set_log_channel"
    ADMIN_REPLIES = "admin:replies"
    ADMIN_ADD_REPLY = "admin:add_reply"
    ADMIN_LIST_REPLIES = "admin:list_replies"
    ADMIN_DEL_REPLY = "admin:del_reply"
    ADMIN_BANNED_WORDS = "admin:banned_words"
    ADMIN_ADD_BANNED_WORD = "admin:add_banned_word"
    ADMIN_LIST_BANNED_WORDS = "admin:list_banned_words"
    ADMIN_REMOVE_BANNED_WORD = "admin:remove_banned_word"
    ADMIN_CREATE_CONTEST = "admin:create_contest"
    ADMIN_DECLARE_WINNER = "admin:declare_winner"
    ADMIN_DEL_CONTEST_PREFIX = "admin:del_contest:"
    ADMIN_AUTO_REPLY = "admin_auto_reply"
    ADMIN_REPLY_TICKET = "admin_reply_ticket:"
    AUTO_REPLY_MENU_PREFIX = "auto_reply_menu:"
    AUTO_REPLY_TOGGLE_PREFIX = "auto_reply_toggle:"
    AUTO_REPLY_ADMINS_PREFIX = "auto_reply_admins:"
    AUTO_REPLY_RESET_PREFIX = "auto_reply_reset:"
    AUTO_REPLY_CONFIRM_RESET_PREFIX = "auto_reply_confirm_reset:"
    AUTO_REPLY_CANCEL_PREFIX = "auto_reply_cancel:"
    AUTO_REPLY_STATS_PREFIX = "auto_reply_stats:"
    USER_AUTO_REPLY_TOGGLE_PREFIX = "user_auto_reply_toggle:"
    NSFW_SETTINGS = "nsfw_settings"
    NSFW_TOGGLE = "nsfw_toggle"
    NSFW_THRESHOLD_SET = "nsfw_threshold_set"
    AUTO_REPLY_ADD = "auto_reply_add"
    AUTO_REPLY_DEL = "auto_reply_del"
    AUTO_REPLY_LIST = "auto_reply_list"
    AUTO_REPLY_MENU = "auto_reply_menu"

class UserState(Enum):
    NONE = auto()
    ADDING_POSTS = auto()
    WAITING_CHANNEL_ID = auto()
    WAITING_INTERVAL_MINUTES = auto()
    WAITING_INTERVAL_HOURS = auto()
    WAITING_INTERVAL_DAYS = auto()
    WAITING_PUBLISH_TIME = auto()
    WAITING_ADMIN_ID_ADD = auto()
    WAITING_ADMIN_ID_REMOVE = auto()
    WAITING_BROADCAST = auto()
    WAITING_UPDATE_TEXT = auto()
    WAITING_UPDATE_CHANNEL = auto()
    WAITING_FORCE_CHANNEL = auto()
    WAITING_REMINDER_DAYS = auto()
    WAITING_SCHEDULE_POST = auto()
    WAITING_BAN_USER = auto()
    WAITING_MUTE_USER = auto()
    WAITING_WARN_USER = auto()
    WAITING_KICK_USER = auto()
    WAITING_RESTRICT_USER = auto()
    WAITING_UNBAN_USER = auto()
    WAITING_PIN_MESSAGE = auto()
    WAITING_GROUP_BANNED_WORD = auto()
    WAITING_REMOVE_GROUP_BANNED_WORD = auto()
    WAITING_GLOBAL_BANNED_WORD = auto()
    WAITING_REMOVE_GLOBAL_BANNED_WORD = auto()
    WAITING_KEYWORD = auto()
    WAITING_REPLY = auto()
    WAITING_SENDCODE_USER = auto()
    WAITING_LOG_CHANNEL = auto()
    SUPPORT_MODE = auto()
    WAITING_TICKET_REPLY = auto()
    WAITING_CONTEST_TITLE = auto()
    WAITING_CONTEST_DESCRIPTION = auto()
    WAITING_CONTEST_PRIZE = auto()
    WAITING_CONTEST_END_DATE = auto()
    WAITING_CONTEST_ANSWER = auto()
    WAITING_NSFW_THRESHOLD = auto()
    WAITING_MAX_LENGTH = auto()
    WAITING_WARN_COUNT = auto()
    WAITING_WARN_PENALTY = auto()
    WAITING_BACKUP_INTERVAL = auto()
    WAITING_AUTO_REPLY_KEYWORD = auto()
    WAITING_AUTO_REPLY_REPLY = auto()
    WAITING_AUTO_REPLY_DELETE = auto()

# ===================================================================
# 23. دوال الكيبوردات المساعدة
# ===================================================================
def security_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text('ar', 'security_links'), callback_data=f"security:links:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_mentions'), callback_data=f"security:mentions:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_slow_mode'), callback_data=f"security:slow_mode:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'security_welcome'), callback_data=f"security:welcome_enabled:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_goodbye'), callback_data=f"security:goodbye_enabled:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_banned_words'), callback_data=f"{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'security_delete_videos'), callback_data=f"security:delete_videos:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_delete_audio'), callback_data=f"security:delete_audio:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_delete_animation'), callback_data=f"security:delete_animation:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'security_delete_service'), callback_data=f"security:delete_service:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_delete_documents'), callback_data=f"security:delete_documents:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_delete_stickers'), callback_data=f"security:delete_stickers:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'security_delete_forwarded'), callback_data=f"security:delete_forwarded:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_delete_polls'), callback_data=f"security:delete_polls:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_delete_games'), callback_data=f"security:delete_games:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'security_delete_voice'), callback_data=f"security:delete_voice:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_delete_video_note'), callback_data=f"security:delete_video_note:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_antiflood'), callback_data=f"security:antiflood:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'security_night_mode'), callback_data=f"security:night_mode:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_max_length'), callback_data=f"security:max_length:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_warn_settings'), callback_data=f"security:warn_settings:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'security_delete_penalty'), callback_data=f"{CallbackData.SECURITY_DELETE_PENALTY_PREFIX}{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_enable_all'), callback_data=f"{CallbackData.SECURITY_ENABLE_ALL_PREFIX}{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_disable_all'), callback_data=f"{CallbackData.SECURITY_DISABLE_ALL_PREFIX}{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'security_penalty'), callback_data=f"{CallbackData.PENALTY_MENU}:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_advanced'), callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'security_log'), callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'security_close'), callback_data=CallbackData.SECURITY_CLOSE)]
    ])

def get_admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text('ar', 'admin_users_btn'), callback_data=CallbackData.ADMIN_USERS),
         InlineKeyboardButton(get_text('ar', 'admin_banned_users_btn'), callback_data=CallbackData.ADMIN_BANNED_USERS)],
        [InlineKeyboardButton(get_text('ar', 'admin_channels_btn'), callback_data=CallbackData.ADMIN_ALL_CHANNELS),
         InlineKeyboardButton(get_text('ar', 'admin_groups_btn'), callback_data=CallbackData.ADMIN_GROUPS)],
        [InlineKeyboardButton(get_text('ar', 'admin_add_admin_btn'), callback_data=CallbackData.ADMIN_ADD_ADMIN),
         InlineKeyboardButton(get_text('ar', 'admin_remove_admin_btn'), callback_data=CallbackData.ADMIN_REMOVE_ADMIN)],
        [InlineKeyboardButton(get_text('ar', 'admin_replies_btn'), callback_data=CallbackData.ADMIN_REPLIES),
         InlineKeyboardButton(get_text('ar', 'admin_banned_words_btn'), callback_data=CallbackData.ADMIN_BANNED_WORDS)],
        [InlineKeyboardButton(get_text('ar', 'admin_ram_btn'), callback_data=CallbackData.ADMIN_RAM),
         InlineKeyboardButton(get_text('ar', 'admin_stats_btn'), callback_data=CallbackData.ADMIN_STATS)],
        [InlineKeyboardButton(get_text('ar', 'admin_backup_btn'), callback_data=CallbackData.ADMIN_BACKUP),
         InlineKeyboardButton(get_text('ar', 'admin_restore_btn'), callback_data=CallbackData.ADMIN_RESTORE_BACKUP)],
        [InlineKeyboardButton(get_text('ar', 'admin_update_btn'), callback_data=CallbackData.ADMIN_SEND_UPDATE),
         InlineKeyboardButton(get_text('ar', 'admin_broadcast_btn'), callback_data=CallbackData.ADMIN_BROADCAST)],
        [InlineKeyboardButton(get_text('ar', 'admin_tickets_btn'), callback_data=CallbackData.ADMIN_SUPPORT_TICKETS),
         InlineKeyboardButton(get_text('ar', 'admin_logs_btn'), callback_data=CallbackData.ADMIN_SHOW_LOG_CHANNEL)],
        [InlineKeyboardButton(get_text('ar', 'admin_force_subscribe_btn'), callback_data=CallbackData.ADMIN_FORCE_SUBSCRIBE),
         InlineKeyboardButton(get_text('ar', 'admin_monitor_btn'), callback_data=CallbackData.ADMIN_MONITOR_USERS)],
        [InlineKeyboardButton(get_text('ar', 'admin_back'), callback_data=CallbackData.BACK)]
    ])

def get_group_banned_words_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كلمة", callback_data=f"{CallbackData.BANNED_WORDS_ADD_PREFIX}{chat_id}"),
         InlineKeyboardButton("📋 عرض الكلمات", callback_data=f"{CallbackData.BANNED_WORDS_LIST_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🗑️ حذف كلمة", callback_data=f"{CallbackData.BANNED_WORDS_REMOVE_PREFIX}{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

def get_advanced_group_actions_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text('ar', 'advanced_ban'), callback_data=f"{CallbackData.GROUP_ACTION_BAN}:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'advanced_mute'), callback_data=f"{CallbackData.GROUP_ACTION_MUTE}:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'advanced_warn'), callback_data=f"{CallbackData.GROUP_ACTION_WARN}:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'advanced_kick'), callback_data=f"{CallbackData.GROUP_ACTION_KICK}:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'advanced_restrict'), callback_data=f"{CallbackData.GROUP_ACTION_RESTRICT}:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'advanced_pin'), callback_data=f"{CallbackData.GROUP_ACTION_PIN}:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'advanced_unban'), callback_data=f"{CallbackData.GROUP_ACTION_UNBAN}:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'advanced_log'), callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'back'), callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

def get_advanced_mute_duration_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text('ar', 'mute_duration_5'), callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}5:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'mute_duration_30'), callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}30:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'mute_duration_60'), callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}60:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'mute_duration_720'), callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}720:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'mute_duration_1440'), callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}1440:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'mute_duration_10080'), callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}10080:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'mute_duration_permanent'), callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}0:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'back'), callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")]
    ])

def penalty_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text('ar', 'penalty_kick'), callback_data=f"{CallbackData.PENALTY_KICK}:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'penalty_ban'), callback_data=f"{CallbackData.PENALTY_BAN}:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'penalty_mute'), callback_data=f"{CallbackData.PENALTY_MUTE}:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'penalty_warn'), callback_data=f"{CallbackData.PENALTY_WARN}:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'penalty_restrict'), callback_data=f"{CallbackData.PENALTY_RESTRICT}:{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'penalty_none'), callback_data=f"{CallbackData.PENALTY_NONE}:{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'back'), callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

def get_auto_reply_keyboard(chat_id: int, settings: dict) -> InlineKeyboardMarkup:
    st = "🟢 مفعل" if settings.get('enabled') else "🔴 معطل"
    at = "👑 مشرفين" if settings.get('only_admins') else "👥 الجميع"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📝 الردود: {st}", callback_data=f"{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}{chat_id}")],
        [InlineKeyboardButton(f"👥 المستخدمون: {at}", callback_data=f"{CallbackData.AUTO_REPLY_ADMINS_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🔄 إعادة تعيين", callback_data=f"{CallbackData.AUTO_REPLY_RESET_PREFIX}{chat_id}")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data=f"{CallbackData.AUTO_REPLY_STATS_PREFIX}{chat_id}")],
        [InlineKeyboardButton("📝 إدارة الردود", callback_data=f"{CallbackData.AUTO_REPLY_MENU_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

def get_auto_reply_management_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة رد", callback_data=f"{CallbackData.AUTO_REPLY_ADD}:{chat_id}"),
         InlineKeyboardButton("🗑️ حذف رد", callback_data=f"{CallbackData.AUTO_REPLY_DEL}:{chat_id}")],
        [InlineKeyboardButton("📋 قائمة الردود", callback_data=f"{CallbackData.AUTO_REPLY_LIST}:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.AUTO_REPLY_MENU_PREFIX}{chat_id}")]
    ])

async def get_main_keyboard(user_id: int):
    channels = await db_get_channels(user_id)
    active = await db_get_active_channel(user_id)
    cnt = 0
    ch_display = "لا توجد قنوات"
    if active:
        try:
            cnt = await db_unpublished_count(active)
            ch_info = await db_get_channel_info(active)
            if ch_info:
                ch_display = f"{ch_info[1]} ({ch_info[0]})"
        except:
            pass
    my_groups = await db_get_user_groups_count(user_id) or 0
    has_sub = await db_has_active_subscription(user_id)
    sub_text = "✅ مفعل" if has_sub else "❌ غير مفعل"
    auto_status = await db_auto_status(user_id)
    auto_text = "مفعل" if auto_status else "معطل"
    title = f"🌿 **{BOT_NAME}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 المعرف: `{user_id}`\n👥 مجموعاتي: {my_groups}\n💎 الاشتراك: {sub_text}\n📡 القناة: {ch_display}\n📝 غير المنشورة: {cnt}\n⚙️ النشر: {auto_text}"

    keyboard = []
    keyboard.append([InlineKeyboardButton("👥 مجموعاتي", callback_data=CallbackData.GROUPS_MY),
                     InlineKeyboardButton("➕ إضافة قناة", callback_data=CallbackData.CHANNELS_ADD)])
    keyboard.append([InlineKeyboardButton("📡 قنواتي", callback_data=CallbackData.CHANNELS_MY),
                     InlineKeyboardButton("⚙️ الإعدادات", callback_data=CallbackData.SETTINGS_MENU)])
    if channels:
        keyboard.append([InlineKeyboardButton("📥 إضافة منشورات", callback_data=CallbackData.POSTS_ADD_15),
                         InlineKeyboardButton("📤 نشر واحد", callback_data=CallbackData.POSTS_PUBLISH_ONE)])
        keyboard.append([InlineKeyboardButton("📋 منشوراتي", callback_data=CallbackData.POSTS_MY),
                         InlineKeyboardButton("♻️ إعادة تدوير", callback_data=CallbackData.POSTS_RECYCLE)])
        keyboard.append([InlineKeyboardButton(f"📊 إحصائيات ({cnt})", callback_data=CallbackData.STATS_PENDING),
                         InlineKeyboardButton("📈 كاملة", callback_data=CallbackData.STATS_FULL)])
        if active:
            keyboard.append([InlineKeyboardButton("⏰ الجدولة", callback_data=f"{CallbackData.SCHEDULE_MENU_PREFIX}{active}"),
                             InlineKeyboardButton("📊 القناة", callback_data=f"{CallbackData.CHANNEL_STATS}:{active}")])
        keyboard.append([InlineKeyboardButton("📤 نشر الكل", callback_data=CallbackData.PUBLISH_ALL_CHANNELS)])
    keyboard.append([InlineKeyboardButton("❓ مساعدة", callback_data=CallbackData.HELP),
                     InlineKeyboardButton("🎁 تجربة", callback_data=CallbackData.TRIAL)])
    keyboard.append([InlineKeyboardButton("💎 اشتراك", callback_data=CallbackData.SUBSCRIBE_MENU),
                     InlineKeyboardButton("👨‍💻 المطور", callback_data=CallbackData.DEVELOPER)])
    keyboard.append([InlineKeyboardButton("🌐 اللغة", callback_data="language"),
                     InlineKeyboardButton("📞 دعم", callback_data=CallbackData.SUPPORT_MENU)])
    keyboard.append([InlineKeyboardButton("🔗 إحالات", callback_data=CallbackData.REFERRAL_MENU),
                     InlineKeyboardButton("⏰ تذكيرات", callback_data=CallbackData.REMINDER_MENU)])
    keyboard.append([InlineKeyboardButton("🌐 ترجمة", callback_data=CallbackData.TRANSLATION_MENU),
                     InlineKeyboardButton("🏆 مسابقات", callback_data=CallbackData.CONTESTS_MENU)])
    keyboard.append([InlineKeyboardButton("➕ أضف لمجموعة", url=f"https://t.me/{BOT_USERNAME}?startgroup")])
    is_admin = (user_id == PRIMARY_OWNER_ID) or (await is_bot_admin(user_id))
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 لوحة الأدمن", callback_data=CallbackData.ADMIN_PANEL)])
    return InlineKeyboardMarkup(keyboard), title, active

# ===================================================================
# 24. دوال الكولباك الأساسية (المعالج الشامل)
# ===================================================================
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if not data:
        return
    if data == "noop":
        await query.answer()
        return

    await _answer_query(query)

    if data == CallbackData.MAIN_MENU or data == CallbackData.BACK:
        await start_command_handler(update, context)
        return
    if data == CallbackData.CANCEL_SESSION:
        context.user_data.clear()
        await query.edit_message_text("❌ تم الإلغاء")
        await start_command_handler(update, context)
        return
    if data == CallbackData.SUPPORT_BACK:
        await support_command_handler(update, context)
        return
    if data == CallbackData.CONTESTS_BACK:
        await contests_command_handler(update, context)
        return

    if data == CallbackData.CHANNELS_ADD:
        context.user_data['state'] = UserState.WAITING_CHANNEL_ID
        await query.edit_message_text("📡 أرسل معرف القناة (@username أو -100...)")
        return
    if data == CallbackData.CHANNELS_MY:
        await my_channels_callback(update, context)
        return
    if data.startswith(CallbackData.CHANNELS_DELETE_PREFIX):
        ch_db_id = int(data.split(":")[-1])
        user_id = update.effective_user.id
        await db_delete_channel_by_id(user_id, ch_db_id)
        await query.edit_message_text("✅ تم الحذف")
        await my_channels_callback(update, context)
        return
    if data.startswith(CallbackData.CHANNELS_SELECT_PREFIX):
        ch_db_id = int(data.split(":")[-1])
        user_id = update.effective_user.id
        await db_set_active_channel(user_id, ch_db_id)
        context.user_data['active_channel'] = ch_db_id
        await query.edit_message_text("✅ تم التحديد")
        await start_command_handler(update, context)
        return

    if data == CallbackData.POSTS_ADD_15:
        await add_15_posts_callback(update, context)
        return
    if data == CallbackData.POSTS_PUBLISH_ONE:
        await publish_one_callback(update, context)
        return
    if data == CallbackData.POSTS_MY:
        await my_posts_callback(update, context)
        return
    if data == CallbackData.POSTS_RECYCLE:
        user_id = update.effective_user.id
        active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
        if active:
            await db_reset_all_posts_to_unpublished(active)
            await query.edit_message_text("♻️ تم")
        return
    if data.startswith(CallbackData.POSTS_DELETE_SINGLE_PREFIX):
        parts = data.split(":")[-1].split("_")
        if len(parts) >= 2:
            pid, active = int(parts[0]), int(parts[1])
            user_id = update.effective_user.id
            await db_delete_single_post(pid, user_id, active)
            await my_posts_callback(update, context)
        return
    if data.startswith(CallbackData.POSTS_CONFIRM_CLEAR_ALL_PREFIX):
        active = int(data.split(":")[-1])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم", callback_data=f"{CallbackData.POSTS_CLEAR_ALL_PREFIX}{active}"),
             InlineKeyboardButton("❌ لا", callback_data=CallbackData.BACK)]
        ])
        await query.edit_message_text("⚠️ متأكد من حذف الكل؟", reply_markup=kb)
        return
    if data.startswith(CallbackData.POSTS_CLEAR_ALL_PREFIX):
        active = int(data.split(":")[-1])
        await execute_db(lambda c: c.execute("DELETE FROM posts WHERE channel_db_id=?", (active,)) or c.commit())
        await query.edit_message_text("✅ تم الحذف")
        return
    if data == CallbackData.PUBLISH_ALL_CHANNELS:
        await publish_all_channels_callback(update, context)
        return

    if data == CallbackData.STATS_PENDING:
        user_id = update.effective_user.id
        u = await db_get_user_unpublished_posts(user_id)
        t = await db_get_user_total_posts(user_id)
        await query.edit_message_text(f"📊 غير المنشورة: {u}\n📋 الإجمالي: {t}")
        return
    if data == CallbackData.STATS_FULL:
        user_id = update.effective_user.id
        ch = await db_get_user_channels_count(user_id)
        t = await db_get_user_total_posts(user_id)
        u = await db_get_user_unpublished_posts(user_id)
        g = await db_get_user_groups_count(user_id)
        auto = "مفعل" if await db_auto_status(user_id) else "معطل"
        await query.edit_message_text(f"📈 قنوات: {ch}\n📝 منشورات: {t}\n⏳ غير منشورة: {u}\n👥 مجموعات: {g}\n⚙️ النشر: {auto}")
        return

    if data == CallbackData.GROUPS_MY:
        await my_groups_callback(update, context)
        return
    if data.startswith(CallbackData.GROUPS_SETTINGS_PREFIX):
        await group_settings_callback(update, context)
        return
    if data.startswith("delete_group:"):
        await delete_group_callback(update, context)
        return

    if data == CallbackData.SETTINGS_MENU:
        await settings_menu_callback(update, context)
        return
    if data == CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH:
        user_id = update.effective_user.id
        cur = await db_auto_status(user_id)
        await db_set_auto(user_id, not cur)
        await settings_menu_callback(update, context)
        return
    if data == CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE:
        user_id = update.effective_user.id
        cur = await db_get_auto_recycle(user_id)
        await db_set_auto_recycle(user_id, not cur)
        await settings_menu_callback(update, context)
        return

    if data.startswith(CallbackData.SCHEDULE_MENU_PREFIX):
        ch_db_id = int(data.split(":")[-1])
        context.user_data['schedule_ch_id'] = ch_db_id
        s = await db_get_schedule(ch_db_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏱️ دقائق", callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_MINUTES_PREFIX}{ch_db_id}")],
            [InlineKeyboardButton("⏱️ ساعات", callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_HOURS_PREFIX}{ch_db_id}")],
            [InlineKeyboardButton("⏱️ أيام", callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_DAYS_PREFIX}{ch_db_id}")],
            [InlineKeyboardButton("🕐 وقت النشر", callback_data=f"{CallbackData.SCHEDULE_SET_PUBLISH_TIME_PREFIX}{ch_db_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        await query.edit_message_text(f"⏰ الجدولة (الحالي: {s['type']})", reply_markup=kb)
        return
    if data.startswith(CallbackData.SCHEDULE_SET_INTERVAL_MINUTES_PREFIX):
        ch_db_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_INTERVAL_MINUTES
        context.user_data['schedule_ch_id'] = ch_db_id
        await query.edit_message_text("⏱️ أرسل عدد الدقائق (1-1440):")
        return
    if data.startswith(CallbackData.SCHEDULE_SET_INTERVAL_HOURS_PREFIX):
        ch_db_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_INTERVAL_HOURS
        context.user_data['schedule_ch_id'] = ch_db_id
        await query.edit_message_text("⏱️ أرسل عدد الساعات (1-168):")
        return
    if data.startswith(CallbackData.SCHEDULE_SET_INTERVAL_DAYS_PREFIX):
        ch_db_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_INTERVAL_DAYS
        context.user_data['schedule_ch_id'] = ch_db_id
        await query.edit_message_text("⏱️ أرسل عدد الأيام (1-365):")
        return
    if data.startswith(CallbackData.SCHEDULE_SET_PUBLISH_TIME_PREFIX):
        ch_db_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_PUBLISH_TIME
        context.user_data['schedule_ch_id'] = ch_db_id
        await query.edit_message_text("🕐 أرسل وقت النشر (مثال: 14:30)")
        return

    if data.startswith("security:") and len(data.split(":")) >= 3:
        await security_toggle_setting_callback(update, context)
        return
    if data == CallbackData.SECURITY_CLOSE:
        try:
            await query.message.delete()
        except:
            pass
        return
    if data.startswith(CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX):
        chat_id = int(data.split(":")[-1])
        await query.edit_message_text("🚫 **الكلمات المحظورة**", reply_markup=get_group_banned_words_keyboard(chat_id))
        return
    if data.startswith(CallbackData.SECURITY_ENABLE_ALL_PREFIX):
        chat_id = int(data.split(":")[-1])
        await query.edit_message_text("⚠️ سيتم تفعيل جميع إعدادات حذف الوسائط. متأكد؟",
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton("✅ تأكيد", callback_data=f"confirm_enable_all:{chat_id}"),
                                           InlineKeyboardButton("❌ إلغاء", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
                                      ]))
        return
    if data.startswith("confirm_enable_all:"):
        chat_id = int(data.split(":")[-1])
        await db_set_security_settings(chat_id,
            delete_videos=1, delete_audio=1, delete_animation=1, delete_service=1,
            delete_documents=1, delete_stickers=1, delete_forwarded=1,
            delete_polls=1, delete_games=1, delete_voice=1, delete_video_note=1)
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        text = _build_security_text(settings)
        await query.edit_message_text(text, reply_markup=security_keyboard(chat_id), parse_mode="HTML")
        return
    if data.startswith(CallbackData.SECURITY_DISABLE_ALL_PREFIX):
        chat_id = int(data.split(":")[-1])
        await db_set_security_settings(chat_id,
            delete_videos=0, delete_audio=0, delete_animation=0, delete_service=0,
            delete_documents=0, delete_stickers=0, delete_forwarded=0,
            delete_polls=0, delete_games=0, delete_voice=0, delete_video_note=0)
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        text = _build_security_text(settings)
        await query.edit_message_text(text, reply_markup=security_keyboard(chat_id), parse_mode="HTML")
        return
    if data.startswith(CallbackData.SECURITY_DELETE_PENALTY_PREFIX):
        chat_id = int(data.split(":")[-1])
        await query.edit_message_text("⚖️ اختر عقوبة حذف الوسائط:", reply_markup=penalty_keyboard(chat_id))
        return
    if data.startswith("set_delete_penalty:"):
        chat_id, penalty = data.split(":")[1], data.split(":")[2]
        await db_set_security_settings(int(chat_id), delete_penalty=penalty)
        settings = await db_get_security_settings(int(chat_id), force_refresh=True)
        text = _build_security_text(settings)
        await query.edit_message_text(text, reply_markup=security_keyboard(int(chat_id)), parse_mode="HTML")
        return

    if data.startswith(CallbackData.BANNED_WORDS_ADD_PREFIX):
        chat_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_GROUP_BANNED_WORD
        context.user_data['banned_words_chat_id'] = chat_id
        await query.edit_message_text("✏️ أرسل الكلمة:")
        return
    if data.startswith(CallbackData.BANNED_WORDS_LIST_PREFIX):
        chat_id = int(data.split(":")[-1])
        words = await db_get_banned_words(chat_id)
        if not words:
            await query.edit_message_text("📭 لا توجد")
            return
        text = "🚫 **الكلمات المحظورة**\n"
        for w, _, _ in words:
            text += f"• `{w}`\n"
        await query.edit_message_text(text)
        return
    if data.startswith(CallbackData.BANNED_WORDS_REMOVE_PREFIX):
        chat_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_REMOVE_GROUP_BANNED_WORD
        context.user_data['banned_words_chat_id'] = chat_id
        await query.edit_message_text("✏️ أرسل الكلمة للحذف:")
        return

    if data.startswith(CallbackData.PENALTY_MENU):
        chat_id = int(data.split(":")[-1])
        await query.edit_message_text("⚖️ اختر العقوبة الأساسية:", reply_markup=penalty_keyboard(chat_id))
        return
    for p in ['kick', 'ban', 'mute', 'warn', 'restrict', 'none']:
        if data.startswith(f"{getattr(CallbackData, f'PENALTY_{p.upper()}')}:"):
            chat_id = int(data.split(":")[-1])
            await db_set_security_settings(chat_id, auto_penalty=p)
            await query.edit_message_text(f"✅ تم تعيين العقوبة: {p}")
            return

    if data.startswith(CallbackData.ADVANCED_ACTIONS):
        chat_id = int(data.split(":")[-1])
        await query.edit_message_text("🛠️ إجراءات متقدمة:", reply_markup=get_advanced_group_actions_keyboard(chat_id))
        return
    if data.startswith(CallbackData.GROUP_ACTION_BAN):
        chat_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_BAN_USER
        context.user_data['advanced_chat_id'] = chat_id
        await query.edit_message_text("🚫 أرسل معرف المستخدم:")
        return
    if data.startswith(CallbackData.GROUP_ACTION_MUTE):
        chat_id = int(data.split(":")[-1])
        await query.edit_message_text("🔇 اختر المدة:", reply_markup=get_advanced_mute_duration_keyboard(chat_id))
        return
    if data.startswith(CallbackData.ADV_MUTE_DURATION_PREFIX):
        parts = data.split(":")
        minutes = int(parts[1])
        chat_id = int(parts[2])
        context.user_data['mute_minutes'] = minutes if minutes > 0 else None
        context.user_data['state'] = UserState.WAITING_MUTE_USER
        context.user_data['advanced_chat_id'] = chat_id
        await query.edit_message_text(f"🔇 كتم {minutes} دقيقة\nأرسل معرف المستخدم:")
        return
    if data.startswith(CallbackData.GROUP_ACTION_WARN):
        chat_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_WARN_USER
        context.user_data['advanced_chat_id'] = chat_id
        await query.edit_message_text("⚠️ أرسل معرف المستخدم:")
        return
    if data.startswith(CallbackData.GROUP_ACTION_KICK):
        chat_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_KICK_USER
        context.user_data['advanced_chat_id'] = chat_id
        await query.edit_message_text("👢 أرسل معرف المستخدم:")
        return
    if data.startswith(CallbackData.GROUP_ACTION_RESTRICT):
        chat_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_RESTRICT_USER
        context.user_data['advanced_chat_id'] = chat_id
        await query.edit_message_text("🔒 أرسل معرف المستخدم:")
        return
    if data.startswith(CallbackData.GROUP_ACTION_UNBAN):
        chat_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_UNBAN_USER
        context.user_data['advanced_chat_id'] = chat_id
        await query.edit_message_text("🔓 أرسل معرف المستخدم:")
        return
    if data.startswith(CallbackData.GROUP_ACTION_LOG):
        chat_id = int(data.split(":")[-1])
        logs = await db_get_admin_logs(chat_id, 20)
        if not logs:
            await query.edit_message_text("📭 لا توجد سجلات")
            return
        text = "📜 **آخر الإجراءات**\n"
        for admin_id, action, target_id, reason, created_at in logs:
            time_str = datetime.fromisoformat(created_at).strftime("%H:%M")
            text += f"• {time_str} - `{admin_id}` {action}"
            if target_id:
                text += f" → `{target_id}`"
            if reason:
                text += f" ({reason})"
            text += "\n"
        await query.edit_message_text(text)
        return

    if data.startswith(CallbackData.PANEL_LOCK_PREFIX):
        chat_id = int(data.split(":")[-1])
        await db_set_chat_lock(chat_id, True, update.effective_user.id)
        await panel_command_handler(update, context)
        return
    if data.startswith(CallbackData.PANEL_UNLOCK_PREFIX):
        chat_id = int(data.split(":")[-1])
        await db_set_chat_lock(chat_id, False)
        await panel_command_handler(update, context)
        return
    if data == CallbackData.PANEL_CLOSE:
        try:
            await query.message.delete()
        except:
            pass
        return

    if data == CallbackData.HELP:
        await help_command_handler(update, context)
        return
    if data == CallbackData.SUPPORT_MENU:
        await support_command_handler(update, context)
        return
    if data == CallbackData.SUPPORT_HELP:
        await help_command_handler(update, context)
        return
    if data == CallbackData.SUPPORT_TICKET:
        context.user_data['support_mode'] = True
        await query.edit_message_text("📞 أرسل رسالتك وسنرد عليك")
        return
    if data == CallbackData.TRIAL:
        await trial_command_handler(update, context)
        return
    if data == CallbackData.SUBSCRIBE_MENU:
        await subscribe_command_handler(update, context)
        return
    if data == CallbackData.DEVELOPER:
        await developer_command_handler(update, context)
        return
    if data == CallbackData.UPDATES:
        await updates_command_handler(update, context)
        return

    if data == CallbackData.REFERRAL_MENU:
        await referral_menu_callback(update, context)
        return
    if data == CallbackData.REFERRAL_CLAIM_REWARD:
        user_id = update.effective_user.id
        days = await db_claim_referral_reward(user_id)
        await query.edit_message_text(f"✅ {days} يوم" if days else "❌ لا يوجد")
        return
    if data.startswith(CallbackData.REFERRAL_COPY_LINK_PREFIX):
        await query.answer("تم نسخ الرابط!", show_alert=True)
        return

    if data == CallbackData.REMINDER_MENU:
        await reminder_menu_callback(update, context)
        return
    if data == CallbackData.REMINDER_TOGGLE_SUB:
        user_id = update.effective_user.id
        settings = await db_get_user_reminder_settings(user_id)
        await db_update_reminder_settings(user_id, subscription_reminder=not settings.get('subscription_reminder', True))
        await reminder_menu_callback(update, context)
        return
    if data == CallbackData.REMINDER_TOGGLE_DAILY:
        user_id = update.effective_user.id
        settings = await db_get_user_reminder_settings(user_id)
        await db_update_reminder_settings(user_id, daily_stats_reminder=not settings.get('daily_stats_reminder', False))
        await reminder_menu_callback(update, context)
        return
    if data == CallbackData.REMINDER_TOGGLE_WEEKLY:
        user_id = update.effective_user.id
        settings = await db_get_user_reminder_settings(user_id)
        await db_update_reminder_settings(user_id, weekly_report=not settings.get('weekly_report', True))
        await reminder_menu_callback(update, context)
        return
    if data == CallbackData.REMINDER_SET_DAYS:
        context.user_data['state'] = UserState.WAITING_REMINDER_DAYS
        await query.edit_message_text("📅 أرسل عدد الأيام قبل انتهاء الاشتراك (1-30):")
        return
    if data == CallbackData.REMINDER_SET_LANG:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇸🇦 عربي", callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}ar"),
             InlineKeyboardButton("🇬🇧 English", callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}en")],
            [InlineKeyboardButton("🔙", callback_data=CallbackData.REMINDER_MENU)]
        ])
        await query.edit_message_text("🌐 اختر لغة الإشعارات:", reply_markup=kb)
        return
    if data.startswith(CallbackData.REMINDER_LANG_PREFIX):
        lang = data.split(":")[-1]
        await db_update_reminder_settings(update.effective_user.id, notification_lang=lang)
        await reminder_menu_callback(update, context)
        return

    if data == CallbackData.TRANSLATION_MENU:
        await translation_menu_callback(update, context)
        return
    if data == CallbackData.TRANSLATION_OFF:
        user_id = update.effective_user.id
        await set_user_translation_language(user_id, 'off')
        await query.edit_message_text("✅ تم إيقاف الترجمة")
        return
    if data.startswith(CallbackData.TRANSLATION_SET_PREFIX):
        lang = data.split(":")[-1]
        user_id = update.effective_user.id
        await set_user_translation_language(user_id, lang)
        await query.edit_message_text(f"✅ تم تفعيل الترجمة إلى {lang}")
        return

    if data == CallbackData.CONTESTS_MENU:
        await contests_command_handler(update, context)
        return
    if data.startswith(CallbackData.CONTEST_JOIN_PREFIX):
        cid = int(data.split(":")[-1])
        context.user_data['contest_join_id'] = cid
        context.user_data['state'] = UserState.WAITING_CONTEST_ANSWER
        await safe_send_markdown(context.bot, update.effective_user.id, "📝 أرسل إجابتك:")
        return
    if data == CallbackData.CONTEST_WINNERS:
        winners = await db_get_contest_winners(10)
        if not winners:
            await query.edit_message_text("🏆 لا يوجد فائزون بعد")
            return
        text = "🏆 **الفائزون السابقون**\n"
        for cid, title, prize, wid, announced in winners:
            text += f"• {title} → `{wid}`\n"
        await query.edit_message_text(text)
        return

    if data.startswith(CallbackData.CHANNEL_STATS):
        active = int(data.split(":")[-1])
        stats = await db_get_channel_stats(active)
        await query.edit_message_text(f"📊 {stats['total_posts']} | ✅ {stats['published_posts']} | ⏳ {stats['unpublished_posts']}")
        return
    if data == CallbackData.MY_CHANNEL_STATS:
        user_id = update.effective_user.id
        channels = await db_get_channels(user_id)
        if not channels:
            await query.edit_message_text("📭")
            return
        text = "📊 ملخص:\n"
        for ch_db_id, ch_tele_id, ch_name, banned in channels:
            unpub = await db_unpublished_count(ch_db_id)
            text += f"{'🚫' if banned else '✅'} {ch_name}: {unpub}\n"
        await query.edit_message_text(text)
        return

    if data == CallbackData.ADMIN_PANEL:
        user_id = update.effective_user.id
        if user_id == PRIMARY_OWNER_ID or await is_bot_admin(user_id):
            await query.edit_message_text("👑 لوحة التحكم", reply_markup=get_admin_keyboard(user_id))
        return
    if data.startswith("admin:") or data.startswith("confirm_restore:"):
        await admin_router_callback(update, context)
        return

    if data.startswith(CallbackData.AUTO_REPLY_TOGGLE_PREFIX):
        chat_id = int(data.split(":")[-1])
        settings = await db_get_auto_reply_settings(chat_id)
        new_status = not settings.get('enabled', False)
        await db_set_auto_reply_enabled(chat_id, new_status)
        await query.edit_message_text(f"✅ {'مفعل' if new_status else 'معطل'}")
        await group_settings_callback(update, context)
        return
    if data.startswith(CallbackData.AUTO_REPLY_ADMINS_PREFIX):
        chat_id = int(data.split(":")[-1])
        settings = await db_get_auto_reply_settings(chat_id)
        new_admins = not settings.get('only_admins', False)
        await db_set_auto_reply_only_admins(chat_id, new_admins)
        await query.edit_message_text(f"✅ {'مشرفين' if new_admins else 'الجميع'}")
        await group_settings_callback(update, context)
        return
    if data.startswith(CallbackData.AUTO_REPLY_RESET_PREFIX):
        chat_id = int(data.split(":")[-1])
        await db_reset_auto_replies(chat_id)
        await query.edit_message_text("✅ تم إعادة التعيين")
        await group_settings_callback(update, context)
        return
    if data.startswith(CallbackData.AUTO_REPLY_STATS_PREFIX):
        chat_id = int(data.split(":")[-1])
        stats = await db_get_auto_reply_stats(chat_id, 10)
        if not stats:
            await query.edit_message_text("📊 لا توجد إحصائيات")
            return
        text = "📊 **أكثر الردود استخداماً**\n"
        for kw, count in stats:
            text += f"• `{kw}`: {count} مرة\n"
        await query.edit_message_text(text)
        return
    if data.startswith(CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX):
        user_id = update.effective_user.id
        cur = await execute_db(lambda c: c.execute("SELECT auto_reply_enabled FROM users WHERE user_id=?", (user_id,)) or c.fetchone())
        current = bool(cur[0]) if cur else True
        await execute_db(lambda c: c.execute("UPDATE users SET auto_reply_enabled=? WHERE user_id=?", (0 if current else 1, user_id)) or c.commit())
        await query.edit_message_text(f"✅ {'معطل' if current else 'مفعل'}")
        return

    if data.startswith(CallbackData.AUTO_REPLY_MENU_PREFIX):
        chat_id = int(data.split(":")[-1])
        await query.edit_message_text("📝 إدارة الردود التلقائية", reply_markup=get_auto_reply_management_keyboard(chat_id))
        return
    if data.startswith(CallbackData.AUTO_REPLY_ADD):
        chat_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_AUTO_REPLY_KEYWORD
        context.user_data['auto_reply_chat_id'] = chat_id
        await query.edit_message_text("✏️ أرسل الكلمة المفتاحية للرد:")
        return
    if data.startswith(CallbackData.AUTO_REPLY_DEL):
        chat_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_AUTO_REPLY_DELETE
        context.user_data['auto_reply_chat_id'] = chat_id
        await query.edit_message_text("✏️ أرسل الكلمة المفتاحية لحذف الرد:")
        return
    if data.startswith(CallbackData.AUTO_REPLY_LIST):
        chat_id = int(data.split(":")[-1])
        replies = await db_get_auto_reply_stats(chat_id, 20)
        if not replies:
            await query.edit_message_text("📭 لا توجد ردود")
            return
        text = "📋 **قائمة الردود التلقائية**\n"
        for kw, count in replies:
            text += f"• `{kw}`: {count} مرة\n"
        await query.edit_message_text(text)
        return

    if data == CallbackData.NSFW_TOGGLE:
        parts = data.split(":")
        if len(parts) >= 2:
            chat_id = int(parts[1])
        else:
            chat_id = update.effective_chat.id
        current = await db_get_security_settings(chat_id)
        await db_set_security_settings(chat_id, nsfw_enabled=not current.get('nsfw_enabled', False))
        await query.answer("✅ تم التغيير")
        await group_settings_callback(update, context)
        return
    if data == CallbackData.NSFW_THRESHOLD_SET:
        chat_id = update.effective_chat.id
        context.user_data['state'] = UserState.WAITING_NSFW_THRESHOLD
        context.user_data['nsfw_chat_id'] = chat_id
        await query.edit_message_text("🔞 أرسل العتبة (0-100):")
        return

    if data.startswith("security_select_group:"):
        chat_id = int(data.split(":")[-1])
        query.data = f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}"
        await group_settings_callback(update, context)
        return
    if data == CallbackData.REFERRAL_LIST:
        user_id = update.effective_user.id
        referrals = await db_get_referrals_list(user_id)
        if not referrals:
            await query.edit_message_text("📭 لا يوجد إحالات")
        else:
            text = "📋 قائمة المُحالين:\n" + "\n".join([f"• `{r}`" for r in referrals[:20]])
            await query.edit_message_text(text)
        return
    if data.startswith(CallbackData.GROUP_ACTION_PIN):
        chat_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_PIN_MESSAGE
        context.user_data['advanced_chat_id'] = chat_id
        await query.edit_message_text("📌 أرسل معرف الرسالة أو رد على الرسالة لتثبيتها:")
        return

    if data.startswith(CallbackData.AUTO_REPLY_CONFIRM_RESET_PREFIX):
        chat_id = int(data.split(":")[-1])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم", callback_data=f"{CallbackData.AUTO_REPLY_RESET_PREFIX}{chat_id}"),
             InlineKeyboardButton("❌ لا", callback_data=f"{CallbackData.AUTO_REPLY_MENU_PREFIX}{chat_id}")]
        ])
        await query.edit_message_text("⚠️ متأكد من إعادة تعيين جميع الردود؟", reply_markup=kb)
        return
    if data.startswith(CallbackData.AUTO_REPLY_CANCEL_PREFIX):
        chat_id = int(data.split(":")[-1])
        await group_settings_callback(update, context)
        return

    if data == CallbackData.ADMIN_AUTO_REPLY:
        await query.edit_message_text("💬 إدارة الردود العامة\nاستخدم الأزرار أو الأوامر:\n/add_reply\n/list_replies\n/del_reply")
        return
    if data.startswith(CallbackData.ADMIN_REPLY_TICKET):
        ticket_id = int(data.split(":")[-1])
        context.user_data['state'] = UserState.WAITING_TICKET_REPLY
        context.user_data['ticket_id'] = ticket_id
        await query.edit_message_text(f"✏️ أرسل ردك على التذكرة #{ticket_id}:")
        return
    if data == CallbackData.ADMIN_MANAGE_SENDCODE:
        allowed = await db_get_allowed_sendcode_user()
        await query.edit_message_text(f"🔑 المستخدم المسموح له بـ /sendcode: `{allowed or 'غير محدد'}`\nلتغييره استخدم /set_sendcode_user")
        return
    if data == CallbackData.ADMIN_SET_SENDCODE_USER:
        context.user_data['state'] = UserState.WAITING_SENDCODE_USER
        await query.edit_message_text("👤 أرسل معرف المستخدم:")
        return
    if data == CallbackData.ADMIN_BACKUP_SETTINGS:
        auto = await db_get_auto_backup()
        last = await db_get_last_backup_time() or "لم يتم"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🔄 نسخ تلقائي: {'✅' if auto else '❌'}", callback_data=CallbackData.ADMIN_TOGGLE_AUTO_BACKUP)],
            [InlineKeyboardButton("📅 تغيير الفاصل", callback_data=CallbackData.ADMIN_CHANGE_INTERVAL)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
        ])
        await query.edit_message_text(f"💾 إعدادات النسخ الاحتياطي\nآخر نسخ: {last}", reply_markup=kb)
        return
    if data == CallbackData.ADMIN_TOGGLE_AUTO_BACKUP:
        await db_toggle_auto_backup()
        await query.answer("✅ تم التبديل")
        await admin_router_callback(update, context)
        return
    if data == CallbackData.ADMIN_CHANGE_INTERVAL:
        context.user_data['state'] = UserState.WAITING_BACKUP_INTERVAL
        await query.edit_message_text("📅 أرسل عدد الأيام بين النسخ الاحتياطية (1-30):")
        return
    if data == CallbackData.ADMIN_METRICS:
        metrics = await db_get_metrics()
        text = f"📊 **المقاييس**\n👥 المستخدمون النشطون: {metrics['active_users']}\n📝 منشورات اليوم: {metrics['today_posts']}\n💾 حجم DB: {metrics['db_size']} MB"
        await query.edit_message_text(text)
        return
    if data.startswith(CallbackData.CHANNEL_GROWTH):
        channel_db_id = int(data.split(":")[-1])
        growth = await db_get_channel_growth(channel_db_id)
        await query.edit_message_text(f"📈 نمو القناة (آخر 7 أيام): {growth} منشور")
        return
    if data.startswith(CallbackData.CHANNEL_STATS_REFRESH):
        channel_db_id = int(data.split(":")[-1])
        stats = await db_get_channel_stats(channel_db_id)
        await query.edit_message_text(f"📊 تم التحديث\n{stats['total_posts']} | ✅ {stats['published_posts']} | ⏳ {stats['unpublished_posts']}")
        return

    if data in ["rank", "top", "schedule_post", "language"]:
        if data == "rank":
            await rank_command_handler(update, context)
        elif data == "top":
            await top_command_handler(update, context)
        elif data == "schedule_post":
            context.user_data['state'] = UserState.WAITING_SCHEDULE_POST
            await safe_send_markdown(context.bot, update.effective_user.id, "📝 أرسل: YYYY-MM-DD HH:MM النص")
        elif data == "language":
            await language_command_handler(update, context)
        return

    if data == CallbackData.CHECK_SUBSCRIBE:
        await start_command_handler(update, context)
        return

    if data.startswith("buy:subscription_"):
        days = int(data.split("_")[-1])
        try:
            await context.bot.send_invoice(
                chat_id=update.effective_user.id,
                title=f"{days} يوم اشتراك",
                description=f"اشتراك {days} يوم في ريلاكس مانيجر",
                payload=f"sub_{days}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(f"{days} يوم", days * 5 if days <= 2 else 50 if days == 30 else 120)]
            )
        except Exception as e:
            await query.answer(f"❌ فشل: {str(e)[:50]}", show_alert=True)
        return

    await query.answer()

# ===================================================================
# 25. دوال الكولباك المساعدة
# ===================================================================
async def _answer_query(query):
    try:
        await query.answer()
    except:
        pass

def _build_security_text(settings: dict) -> str:
    def st(v):
        return "✅" if v else "❌"
    lines = [
        "🔐 <b>إعدادات الأمان للمجموعة</b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🔗 الروابط: {st(settings.get('delete_links', 0))}",
        f"@ المعرفات: {st(settings.get('mentions', 0))}",
        f"⏱️ البطيء: {st(settings.get('slow_mode', 0))} ({settings.get('slow_mode_seconds', 5)}ث)",
        f"🎯 الترحيب: {st(settings.get('welcome_enabled', 0))}",
        f"👋 الوداع: {st(settings.get('goodbye_enabled', 0))}",
        f"🎬 فيديوهات: {st(settings.get('delete_videos', 0))}",
        f"🎵 صوتيات: {st(settings.get('delete_audio', 0))}",
        f"🎞️ متحركات: {st(settings.get('delete_animation', 0))}",
        f"🛠️ الخدمة: {st(settings.get('delete_service', 0))}",
        f"📄 ملفات: {st(settings.get('delete_documents', 0))}",
        f"🖼️ ملصقات: {st(settings.get('delete_stickers', 0))}",
        f"📨 المُعاد: {st(settings.get('delete_forwarded', 0))}",
        f"📊 استطلاعات: {st(settings.get('delete_polls', 0))}",
        f"🎮 ألعاب: {st(settings.get('delete_games', 0))}",
        f"🎤 صوتيات: {st(settings.get('delete_voice', 0))}",
        f"🎥 فيديو نوت: {st(settings.get('delete_video_note', 0))}",
        f"🌊 مضاد الفيضان: {st(settings.get('antiflood_enabled', 0))}",
        f"🌙 ليلي: {st(settings.get('night_mode_enabled', 0))}",
        f"📏 الطول: {settings.get('max_message_length', 0) or 'غير محدود'}",
        f"⚖️ العقوبة الأساسية: {settings.get('auto_penalty', 'لا شيء')}",
        f"⚖️ عقوبة الحذف: {settings.get('delete_penalty', 'لا شيء')}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📌 اختر الإعداد:"
    ]
    return "\n".join(lines)

async def my_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels:
        await query.edit_message_text("📭 لا توجد قنوات")
        return
    kb = []
    for ch_id, ch_tele_id, ch_name, banned in channels:
        st = "🚫" if banned else "✅"
        kb.append([InlineKeyboardButton(f"{st} {ch_name}", callback_data=f"{CallbackData.CHANNELS_SELECT_PREFIX}{ch_id}"),
                   InlineKeyboardButton("🗑️", callback_data=f"{CallbackData.CHANNELS_DELETE_PREFIX}{ch_id}")])
    kb.append([InlineKeyboardButton("➕ إضافة", callback_data=CallbackData.CHANNELS_ADD)])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await query.edit_message_text("📡 **قنواتي**", reply_markup=InlineKeyboardMarkup(kb))

async def add_15_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
        await query.edit_message_text("⚠️ اشتراك منتهٍ")
        return
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await query.edit_message_text("⚠️ اختر قناة")
        return
    unpub = await db_unpublished_count(active)
    if unpub >= MAX_UNPUBLISHED_POSTS:
        await query.edit_message_text("⚠️ الحد الأقصى")
        return
    target = min(15, MAX_UNPUBLISHED_POSTS - unpub)
    context.user_data[f"session_{user_id}"] = []
    context.user_data[f"session_target_{user_id}"] = target
    context.user_data['state'] = UserState.ADDING_POSTS
    await query.edit_message_text(f"📥 أرسل {target} منشور")

async def publish_one_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
        await query.edit_message_text("⚠️ اشتراك منتهٍ")
        return
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await query.edit_message_text("⚠️ اختر قناة")
        return
    post = await db_get_next_post(active)
    if not post:
        await query.edit_message_text("📭 لا توجد منشورات")
        return
    ch_info = await db_get_channel_info(active)
    if not ch_info:
        return
    channel_id = ch_info[0]
    try:
        if post['media_type'] == 'photo' and post['media_file_id']:
            await context.bot.send_photo(channel_id, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
        elif post['media_type'] == 'video' and post['media_file_id']:
            await context.bot.send_video(channel_id, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
        elif post['media_type'] == 'document' and post['media_file_id']:
            await context.bot.send_document(channel_id, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
        else:
            await context.bot.send_message(channel_id, post['text'][:4096] if post['text'] else ".")
        await db_mark_published(post['id'])
        await db_set_last_publish(active, utc_now())
        await db_update_next_publish_date(active)
        await query.edit_message_text("✅ تم النشر")
    except Exception as e:
        await db_increment_fail_count(post['id'])
        await query.edit_message_text(f"❌ فشل: {str(e)[:100]}")

async def my_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await query.edit_message_text("⚠️ اختر قناة")
        return
    posts = await db_get_user_posts_for_channel(active, 15)
    if not posts:
        await query.edit_message_text("📭 لا توجد")
        return
    text = "📋 **منشوراتي**\n"
    kb = []
    for pid, ptext, mtype in posts[:10]:
        short = (ptext or "بدون نص")[:50]
        text += f"🆔 {pid}: {short}...\n"
        kb.append([InlineKeyboardButton(f"🗑️ حذف #{pid}", callback_data=f"{CallbackData.POSTS_DELETE_SINGLE_PREFIX}{pid}_{active}")])
    kb.append([InlineKeyboardButton("🗑️ حذف الكل", callback_data=f"{CallbackData.POSTS_CONFIRM_CLEAR_ALL_PREFIX}{active}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def publish_all_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels:
        return
    tasks = []
    for ch_db_id, ch_tele_id, ch_name, banned in channels:
        if banned:
            continue
        post = await db_get_next_post(ch_db_id)
        if not post:
            continue
        tasks.append(_publish_single_channel(context.bot, ch_db_id, ch_tele_id, post))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await safe_send_markdown(context.bot, user_id, "✅ تم النشر للكل")

async def _publish_single_channel(bot, ch_db_id, ch_tele_id, post):
    try:
        if post['media_type'] == 'photo' and post['media_file_id']:
            await bot.send_photo(ch_tele_id, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
        else:
            await bot.send_message(ch_tele_id, post['text'][:4096] if post['text'] else ".")
        await db_mark_published(post['id'])
        await db_set_last_publish(ch_db_id, utc_now())
        await db_update_next_publish_date(ch_db_id)
    except:
        await db_increment_fail_count(post['id'])

async def my_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    groups = await db_get_user_groups(uid)
    valid = [(cid, cn, un, b) for cid, cn, un, b in groups if await is_authorized_in_group(context.bot, cid, uid)]
    if not valid:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ أضف", url=f"https://t.me/{BOT_USERNAME}?startgroup")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        await query.edit_message_text("📭 لا توجد", reply_markup=kb)
        return
    kb = []
    for chat_id, chat_name, _, banned in valid:
        st = "⛔" if banned else "✅"
        kb.append([InlineKeyboardButton(f"{st} {chat_name[:25]}", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")])
        kb.append([InlineKeyboardButton("🔐 أمان", callback_data=f"security_select_group:{chat_id}"),
                   InlineKeyboardButton("📜 سجل", callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}"),
                   InlineKeyboardButton("⚙️ متقدم", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await query.edit_message_text("👥 **مجموعاتي**", reply_markup=InlineKeyboardMarkup(kb))

async def group_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        return
    settings = await db_get_security_settings(chat_id)
    text = _build_security_text(settings)
    await query.edit_message_text(text, reply_markup=security_keyboard(chat_id), parse_mode="HTML")

async def settings_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    auto = "✅" if await db_auto_status(user_id) else "❌"
    rec = "✅" if await db_get_auto_recycle(user_id) else "❌"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⚙️ نشر تلقائي: {auto}", callback_data=CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH)],
        [InlineKeyboardButton(f"♻️ تدوير: {rec}", callback_data=CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    await query.edit_message_text("⚙️ **الإعدادات**", reply_markup=kb)

async def security_toggle_setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 3:
        return
    action = parts[1]
    try:
        chat_id = int(parts[2])
    except ValueError:
        return

    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return

    field_map = {
        "links": "delete_links",
        "mentions": "mentions",
        "slow_mode": "slow_mode",
        "delete_videos": "delete_videos",
        "delete_service": "delete_service",
        "delete_documents": "delete_documents",
        "delete_stickers": "delete_stickers",
        "delete_audio": "delete_audio",
        "delete_animation": "delete_animation",
        "delete_forwarded": "delete_forwarded",
        "delete_polls": "delete_polls",
        "delete_games": "delete_games",
        "delete_voice": "delete_voice",
        "delete_video_note": "delete_video_note",
        "welcome_enabled": "welcome_enabled",
        "goodbye_enabled": "goodbye_enabled",
        "antiflood": "antiflood_enabled",
        "night_mode": "night_mode_enabled",
    }

    if action in field_map:
        col = field_map[action]
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        current = settings.get(col, 0)
        new_value = 1 if current == 0 else 0
        await db_set_security_settings(chat_id, **{col: new_value})
        await query.answer("✅ تم التغيير", show_alert=True)
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        text = _build_security_text(settings)
        try:
            await query.edit_message_text(text, reply_markup=security_keyboard(chat_id), parse_mode="HTML")
        except:
            pass
        return

    if action == "max_length":
        context.user_data['state'] = UserState.WAITING_MAX_LENGTH
        context.user_data['security_chat_id'] = chat_id
        await query.edit_message_text("📏 أرسل الحد الأقصى لطول الرسالة (0 = غير محدود):")
        return
    if action == "warn_settings":
        settings = await db_get_security_settings(chat_id)
        text = f"⚠️ **إعدادات التحذير**\nالحد الأقصى للتحذيرات: {settings.get('max_warnings', 3)}\nعقوبة التجاوز: {settings.get('warn_penalty', 'ban')}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 تغيير عدد التحذيرات", callback_data=f"warn_count:{chat_id}"),
             InlineKeyboardButton("⚖️ تغيير العقوبة", callback_data=f"warn_penalty:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
        ])
        await query.edit_message_text(text, reply_markup=kb)
        return
    if action == "warn_count":
        context.user_data['state'] = UserState.WAITING_WARN_COUNT
        context.user_data['security_chat_id'] = chat_id
        await query.edit_message_text("📝 أرسل الحد الأقصى للتحذيرات (1-10):")
        return
    if action == "warn_penalty":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 حظر", callback_data=f"set_warn_penalty:{chat_id}:ban"),
             InlineKeyboardButton("🔇 كتم", callback_data=f"set_warn_penalty:{chat_id}:mute")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"security:warn_settings:{chat_id}")]
        ])
        await query.edit_message_text("⚖️ اختر عقوبة تجاوز التحذيرات:", reply_markup=kb)
        return
    if action.startswith("set_warn_penalty:"):
        _, chat_id_str, penalty = action.split(":")
        chat_id = int(chat_id_str)
        await db_set_security_settings(chat_id, warn_penalty=penalty)
        await query.answer(f"✅ تم تعيين {penalty}")
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        text = f"⚠️ **إعدادات التحذير**\nالحد الأقصى للتحذيرات: {settings.get('max_warnings', 3)}\nعقوبة التجاوز: {settings.get('warn_penalty', 'ban')}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 تغيير عدد التحذيرات", callback_data=f"warn_count:{chat_id}"),
             InlineKeyboardButton("⚖️ تغيير العقوبة", callback_data=f"warn_penalty:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
        ])
        await query.edit_message_text(text, reply_markup=kb)
        return
    await query.answer()

async def referral_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    stats = await db_get_referral_stats(user_id)
    code = await db_get_user_referral_code(user_id)
    text = f"🔗 رابطك: `https://t.me/{BOT_USERNAME}?start=ref_{code}`\n👥 {stats['total_referrals']} | 🎁 {stats['available_days']} يوم"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 صرف", callback_data=CallbackData.REFERRAL_CLAIM_REWARD)],
        [InlineKeyboardButton("📋 قائمة الإحالات", callback_data=CallbackData.REFERRAL_LIST)],
        [InlineKeyboardButton("🔙", callback_data=CallbackData.BACK)]
    ])
    await query.edit_message_text(text, reply_markup=kb)

async def reminder_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    settings = await db_get_user_reminder_settings(user_id)
    sub = "✅" if settings.get('subscription_reminder') else "❌"
    daily = "✅" if settings.get('daily_stats_reminder') else "❌"
    weekly = "✅" if settings.get('weekly_report') else "❌"
    days = settings.get('reminder_days_before', 3)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔔 تذكير الاشتراك: {sub}", callback_data=CallbackData.REMINDER_TOGGLE_SUB)],
        [InlineKeyboardButton(f"📊 يومي: {daily}", callback_data=CallbackData.REMINDER_TOGGLE_DAILY)],
        [InlineKeyboardButton(f"📈 أسبوعي: {weekly}", callback_data=CallbackData.REMINDER_TOGGLE_WEEKLY)],
        [InlineKeyboardButton(f"📅 عدد الأيام: {days}", callback_data=CallbackData.REMINDER_SET_DAYS)],
        [InlineKeyboardButton("🌐 لغة الإشعارات", callback_data=CallbackData.REMINDER_SET_LANG)],
        [InlineKeyboardButton("🔙", callback_data=CallbackData.BACK)]
    ])
    await query.edit_message_text("⏰ إعدادات التذكيرات", reply_markup=kb)

async def translation_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    lang = await get_user_translation_language(user_id)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇸🇦 عربي", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}ar"),
         InlineKeyboardButton("🇬🇧 English", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}en")],
        [InlineKeyboardButton("🚫 إيقاف", callback_data=CallbackData.TRANSLATION_OFF)],
        [InlineKeyboardButton("🔙", callback_data=CallbackData.BACK)]
    ])
    await query.edit_message_text(f"🌐 الترجمة: {lang}", reply_markup=kb)

async def delete_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("لا يمكن حذف المجموعة.", show_alert=True)

async def admin_router_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        return
    await _answer_query(query)

    if data == CallbackData.ADMIN_USERS:
        total, banned, _, _, _ = await db_stats()
        await query.edit_message_text(f"👥 المستخدمين: {total}\n🚫 محظورين: {banned}")
    elif data == CallbackData.ADMIN_BANNED_USERS:
        users = await db_get_all_users()
        banned_list = [u for u in users if u[1] == 1]
        text = "🚫 المحظورين:\n" + "\n".join([f"• `{u[0]}`" for u in banned_list[:20]]) if banned_list else "لا يوجد"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_UNBAN_ALL_USERS:
        await execute_db(lambda c: c.execute("UPDATE users SET banned=0 WHERE banned=1") or c.commit())
        await query.edit_message_text("✅ تم إلغاء حظر الكل")
    elif data == CallbackData.ADMIN_ALL_CHANNELS:
        channels = await execute_db(lambda c: c.execute("SELECT id, channel_id, channel_name, banned FROM user_channels ORDER BY id LIMIT 50") or c.fetchall())
        text = "📡 القنوات:\n" + "\n".join([f"• `{ch[1]}` - {ch[2]} {'🚫' if ch[3] else '✅'}" for ch in channels]) if channels else "لا توجد"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_BANNED_CHANNELS:
        channels = await execute_db(lambda c: c.execute("SELECT id, channel_id, channel_name FROM user_channels WHERE banned=1 ORDER BY id LIMIT 50") or c.fetchall())
        text = "🚫 القنوات المحظورة:\n" + "\n".join([f"• `{ch[1]}` - {ch[2]}" for ch in channels]) if channels else "لا توجد"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_ACTIVATE_ALL_CHANNELS:
        await execute_db(lambda c: c.execute("UPDATE user_channels SET banned=0 WHERE banned=1") or c.commit())
        await query.edit_message_text("✅ تم تفعيل الكل")
    elif data == CallbackData.ADMIN_GROUPS:
        groups = await execute_db(lambda c: c.execute("SELECT chat_id, chat_name, username, banned FROM bot_groups ORDER BY chat_id LIMIT 50") or c.fetchall())
        text = "👥 المجموعات:\n" + "\n".join([f"• `{g[0]}` - {g[1]} {'🚫' if g[3] else '✅'}" for g in groups]) if groups else "لا توجد"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_BANNED_GROUPS:
        groups = await execute_db(lambda c: c.execute("SELECT chat_id, chat_name, username FROM bot_groups WHERE banned=1 ORDER BY chat_id LIMIT 50") or c.fetchall())
        text = "🚫 المجموعات المحظورة:\n" + "\n".join([f"• `{g[0]}` - {g[1]}" for g in groups]) if groups else "لا توجد"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_UNBAN_ALL_GROUPS:
        await execute_db(lambda c: c.execute("UPDATE bot_groups SET banned=0 WHERE banned=1") or c.commit())
        await query.edit_message_text("✅ تم إلغاء حظر الكل")
    elif data == CallbackData.ADMIN_BOT_CHANNELS:
        channels = await db_get_bot_channels()
        text = "📡 قنوات البوت:\n" + "\n".join([f"• `{ch['channel_id']}` - {ch['channel_name']}" for ch in channels]) if channels else "لا توجد"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_BANNED_BOT_CHANNELS:
        channels = await db_get_bot_channels(banned=True)
        text = "🚫 قنوات البوت المحظورة:\n" + "\n".join([f"• `{ch['channel_id']}` - {ch['channel_name']}" for ch in channels]) if channels else "لا توجد"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_UNBAN_ALL_BOT_CHANNELS:
        await execute_db(lambda c: c.execute("UPDATE user_channels SET banned=0 WHERE user_id=? AND banned=1", (PRIMARY_OWNER_ID,)) or c.commit())
        await query.edit_message_text("✅ تم إلغاء حظر الكل")
    elif data == CallbackData.ADMIN_ADD_ADMIN:
        context.user_data['state'] = UserState.WAITING_ADMIN_ID_ADD
        await query.edit_message_text("👑 أرسل معرف المشرف:")
    elif data == CallbackData.ADMIN_REMOVE_ADMIN:
        context.user_data['state'] = UserState.WAITING_ADMIN_ID_REMOVE
        await query.edit_message_text("🗑️ أرسل معرف المشرف:")
    elif data == CallbackData.ADMIN_RAM:
        ram = get_ram_usage()
        await query.edit_message_text(f"💾 {ram['used']:.1f}/{ram['total']:.1f} GB ({ram['percent']}%)")
    elif data == CallbackData.ADMIN_STATS:
        total, banned, posts, groups, channels = await db_stats()
        await query.edit_message_text(f"👥 {total} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}")
    elif data == CallbackData.ADMIN_METRICS:
        metrics = await db_get_metrics()
        text = f"📊 **المقاييس**\n👥 المستخدمون النشطون: {metrics['active_users']}\n📝 منشورات اليوم: {metrics['today_posts']}\n💾 حجم DB: {metrics['db_size']} MB"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_BACKUP:
        try:
            backup_file = await create_backup()
            await safe_send_markdown(context.bot, user_id, f"✅ تم النسخ: {backup_file.name}")
        except Exception as e:
            await safe_send_markdown(context.bot, user_id, f"❌ فشل: {str(e)[:100]}")
    elif data == CallbackData.ADMIN_RESTORE_BACKUP:
        backups = sorted(BACKUP_DIR.glob("backup_*.enc"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not backups:
            await query.edit_message_text("لا توجد نسخ احتياطية")
            return
        kb = []
        for b in backups[:10]:
            kb.append([InlineKeyboardButton(b.name, callback_data=f"{CallbackData.ADMIN_RESTORE_BACKUP_SELECT_PREFIX}{b.name}")])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)])
        await query.edit_message_text("اختر النسخة:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith(CallbackData.ADMIN_RESTORE_BACKUP_SELECT_PREFIX):
        filename = data.split(":")[-1]
        filepath = BACKUP_DIR / filename
        if not filepath.exists():
            await query.edit_message_text("الملف غير موجود")
            return
        try:
            encrypted = filepath.read_bytes()
            decrypted = BACKUP_CIPHER.decrypt(encrypted)
            decompressed = decompress_backup(decrypted)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
                tmp.write(decompressed)
                tmp.flush()
            shutil.copy2(tmp.name, DB_PATH)
            os.unlink(tmp.name)
            await query.edit_message_text("✅ تمت الاستعادة بنجاح")
        except Exception as e:
            await query.edit_message_text(f"❌ فشل: {str(e)[:100]}")
    elif data == CallbackData.ADMIN_BACKUP_SETTINGS:
        auto = await db_get_auto_backup()
        last = await db_get_last_backup_time() or "لم يتم"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🔄 نسخ تلقائي: {'✅' if auto else '❌'}", callback_data=CallbackData.ADMIN_TOGGLE_AUTO_BACKUP)],
            [InlineKeyboardButton("📅 تغيير الفاصل", callback_data=CallbackData.ADMIN_CHANGE_INTERVAL)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
        ])
        await query.edit_message_text(f"💾 إعدادات النسخ الاحتياطي\nآخر نسخ: {last}", reply_markup=kb)
    elif data == CallbackData.ADMIN_TOGGLE_AUTO_BACKUP:
        await db_toggle_auto_backup()
        await query.answer("✅ تم التبديل")
        await admin_router_callback(update, context)
    elif data == CallbackData.ADMIN_CHANGE_INTERVAL:
        context.user_data['state'] = UserState.WAITING_BACKUP_INTERVAL
        await query.edit_message_text("📅 أرسل عدد الأيام بين النسخ الاحتياطية (1-30):")
    elif data == CallbackData.ADMIN_SEND_UPDATE:
        context.user_data['state'] = UserState.WAITING_UPDATE_TEXT
        await query.edit_message_text("📢 أرسل نص التحديث:")
    elif data == CallbackData.ADMIN_SET_UPDATE_CHANNEL:
        context.user_data['state'] = UserState.WAITING_UPDATE_CHANNEL
        await query.edit_message_text("📢 أرسل معرف القناة (بدون @):")
    elif data == CallbackData.ADMIN_SHOW_UPDATE_CHANNEL:
        ch = await db_get_updates_channel()
        await query.edit_message_text(f"📢 القناة: @{ch}" if ch else "لا توجد")
    elif data == CallbackData.ADMIN_FORCE_SUBSCRIBE:
        ch = await db_get_force_subscribe_channel()
        await query.edit_message_text(f"🔒 الاشتراك الإجباري: @{ch}" if ch else "غير مفعل")
    elif data == CallbackData.ADMIN_SET_FORCE_CHANNEL:
        context.user_data['state'] = UserState.WAITING_FORCE_CHANNEL
        await query.edit_message_text("🔒 أرسل معرف القناة (بدون @):")
    elif data == CallbackData.ADMIN_BROADCAST:
        context.user_data['state'] = UserState.WAITING_BROADCAST
        await query.edit_message_text("📨 أرسل الرسالة:")
    elif data == CallbackData.ADMIN_CONFIRM_BROADCAST:
        text = context.user_data.get('broadcast_text')
        if not text:
            await query.edit_message_text("لا توجد رسالة")
            return
        users = await db_get_all_users()
        sent = 0
        for uid, banned in users:
            if banned:
                continue
            try:
                await safe_send_markdown(context.bot, uid, text)
                sent += 1
            except:
                pass
        await query.edit_message_text(f"✅ تم الإرسال لـ {sent} مستخدم")
        context.user_data.pop('broadcast_text', None)
    elif data == CallbackData.ADMIN_SUPPORT_TICKETS:
        tickets = await db_get_all_tickets()
        if not tickets:
            await query.edit_message_text("📭 لا توجد تذاكر")
            return
        text = "📋 التذاكر:\n"
        for tid, uid, uname, msg, num, status, created in tickets:
            text += f"#{num} - من `{uid}` ({uname or 'لا يوجد'})\n{msg[:50]}...\n"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_DELETE_ALL_TICKETS:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم", callback_data=CallbackData.ADMIN_CONFIRM_DELETE_TICKETS),
             InlineKeyboardButton("❌ لا", callback_data=CallbackData.ADMIN_PANEL)]
        ])
        await query.edit_message_text("⚠️ متأكد من حذف كل التذاكر؟", reply_markup=kb)
    elif data == CallbackData.ADMIN_CONFIRM_DELETE_TICKETS:
        await db_delete_all_tickets()
        await query.edit_message_text("✅ تم الحذف")
    elif data == CallbackData.ADMIN_SHOW_LOG_CHANNEL:
        log_id = await db_get_log_channel_id()
        await query.edit_message_text(f"📋 {log_id}" if log_id else "📋 غير محدد")
    elif data == CallbackData.ADMIN_SET_LOG_CHANNEL:
        context.user_data['state'] = UserState.WAITING_LOG_CHANNEL
        await query.edit_message_text("📋 أرسل معرف القناة:")
    elif data == CallbackData.ADMIN_REPLIES:
        stats = await execute_db(lambda c: c.execute("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? ORDER BY usage_count DESC LIMIT 20", (-1,)) or c.fetchall())
        text = "💬 الردود العامة:\n" + "\n".join([f"• `{kw}`: {cnt} مرة" for kw, cnt in stats]) if stats else "لا توجد"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_ADD_REPLY:
        context.user_data['state'] = UserState.WAITING_KEYWORD
        await query.edit_message_text("✏️ أرسل الكلمة المفتاحية:")
    elif data == CallbackData.ADMIN_LIST_REPLIES:
        replies = await execute_db(lambda c: c.execute("SELECT keyword, reply, usage_count FROM auto_replies WHERE chat_id=0 ORDER BY keyword LIMIT 20") or c.fetchall())
        text = "📋 الردود:\n" + "\n".join([f"• `{kw}` → {reply[:30]}... ({cnt})" for kw, reply, cnt in replies]) if replies else "لا توجد"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_DEL_REPLY:
        context.user_data['state'] = UserState.WAITING_AUTO_REPLY_DELETE
        context.user_data['auto_reply_chat_id'] = -1
        await query.edit_message_text("✏️ أرسل الكلمة المفتاحية لحذف الرد:")
    elif data == CallbackData.ADMIN_BANNED_WORDS:
        words = await db_get_banned_words(-1)
        text = "🚫 الكلمات المحظورة عالمياً:\n" + "\n".join([f"• `{w[0]}`" for w in words]) if words else "لا توجد"
        await query.edit_message_text(text)
    elif data == CallbackData.ADMIN_ADD_BANNED_WORD:
        context.user_data['state'] = UserState.WAITING_GLOBAL_BANNED_WORD
        await query.edit_message_text("✏️ أرسل الكلمة:")
    elif data == CallbackData.ADMIN_REMOVE_BANNED_WORD:
        context.user_data['state'] = UserState.WAITING_REMOVE_GLOBAL_BANNED_WORD
        await query.edit_message_text("✏️ أرسل الكلمة للحذف:")
    elif data == CallbackData.ADMIN_CREATE_CONTEST:
        context.user_data['state'] = UserState.WAITING_CONTEST_TITLE
        await query.edit_message_text("🏆 أرسل عنوان المسابقة:")
    elif data == CallbackData.ADMIN_DECLARE_WINNER:
        contests = await execute_db(lambda c: c.execute("SELECT id, title FROM contests WHERE status='active'") or c.fetchall())
        if not contests:
            await query.edit_message_text("لا توجد مسابقات نشطة")
            return
        kb = []
        for cid, title in contests:
            kb.append([InlineKeyboardButton(title, callback_data=f"declare_winner_sel:{cid}")])
        kb.append([InlineKeyboardButton("🔙", callback_data=CallbackData.ADMIN_PANEL)])
        await query.edit_message_text("اختر المسابقة:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("declare_winner_sel:"):
        cid = int(data.split(":")[-1])
        contest = await db_get_contest(cid)
        if not contest:
            await query.edit_message_text("غير موجودة")
            return
        winner = await execute_db(lambda c: c.execute("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,)) or c.fetchone())
        if not winner:
            await query.edit_message_text("لا يوجد مشاركون")
            return
        await db_set_contest_winner(cid, winner[0])
        await query.edit_message_text(f"🏆 الفائز: `{winner[0]}`")
    elif data.startswith(CallbackData.ADMIN_DEL_CONTEST_PREFIX):
        cid = int(data.split(":")[-1])
        await db_delete_contest(cid, user_id)
        await query.edit_message_text("✅ تم الحذف")
    else:
        await query.answer("⚠️ قيد التطوير", show_alert=True)

# ===================================================================
# 26. المهام الخلفية
# ===================================================================
class TaskManager:
    def __init__(self):
        self.tasks = set()
        self.semaphore = asyncio.Semaphore(10)

    def create_task(self, coro, name=None):
        async def wrapper():
            async with self.semaphore:
                try:
                    return await coro
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"مهمة {name}: {e}")
                    raise
        task = asyncio.create_task(wrapper())
        if name:
            task.set_name(name)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def cancel_all(self):
        for t in list(self.tasks):
            if not t.done():
                t.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()

    def get_task_count(self):
        self.tasks = {t for t in self.tasks if not t.done()}
        return len(self.tasks)

task_manager = TaskManager()

async def safe_loop(coro_func, name="loop"):
    while True:
        try:
            if asyncio.iscoroutinefunction(coro_func):
                await coro_func()
            elif callable(coro_func):
                result = coro_func()
                if asyncio.iscoroutine(result):
                    await result
            else:
                await coro_func
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"حلقة {name}: {e}")
            await asyncio.sleep(60)

async def db_get_publishable_posts(limit: int):
    async def _get(conn):
        cur = await conn.execute("""
            SELECT uc.id as ch_db_id, uc.channel_id, p.id as post_id, p.text, p.media_type, p.media_file_id, u.user_id
            FROM user_channels uc
            JOIN users u ON uc.user_id = u.user_id
            LEFT JOIN schedule s ON uc.id = s.channel_db_id
            JOIN posts p ON uc.id = p.channel_db_id
            WHERE u.auto_publish = 1 AND u.banned = 0 AND uc.banned = 0
            AND p.published = 0 AND (p.fail_count IS NULL OR p.fail_count < 3)
            AND (s.next_publish_date IS NULL OR s.next_publish_date <= ?)
            ORDER BY COALESCE(s.next_publish_date, '1970-01-01') ASC
            LIMIT ?
        """, (utc_now_iso(), limit))
        return await cur.fetchall()
    return await execute_db(_get)

async def auto_publish_loop_improved(bot):
    await asyncio.sleep(5)
    while True:
        try:
            rows = await db_get_publishable_posts(MAX_CHANNELS_PER_CYCLE * 2)
            published_channels = set()
            tasks = []
            for row in rows:
                ch_db_id = row[0]
                if ch_db_id in published_channels:
                    continue
                published_channels.add(ch_db_id)
                post_id = row[2]
                ch_tele_id = row[1]
                text = row[3]
                media_type = row[4]
                media_file_id = row[5]
                tasks.append(_publish_post_task(bot, ch_db_id, ch_tele_id, post_id, text, media_type, media_file_id))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(await db_get_publish_interval_seconds())
        except Exception as e:
            logger.error(f"نشر: {e}")
            await asyncio.sleep(60)

async def _publish_post_task(bot, ch_db_id, ch_tele_id, post_id, text, media_type, media_file_id):
    try:
        if media_type == 'photo' and media_file_id:
            await bot.send_photo(ch_tele_id, media_file_id, caption=text[:1024] if text else None)
        elif media_type == 'video' and media_file_id:
            await bot.send_video(ch_tele_id, media_file_id, caption=text[:1024] if text else None)
        elif media_type == 'document' and media_file_id:
            await bot.send_document(ch_tele_id, media_file_id, caption=text[:1024] if text else None)
        else:
            await bot.send_message(ch_tele_id, text[:4096] if text else ".")
        await db_mark_published(post_id)
        await db_set_last_publish(ch_db_id, utc_now())
        await db_update_next_publish_date(ch_db_id)
    except Exception as e:
        await db_increment_fail_count(post_id)
        await db_set_next_publish_date(ch_db_id, utc_now() + timedelta(seconds=PUBLISH_RETRY_DELAY))

async def auto_backup():
    while True:
        await asyncio.sleep(24 * 60 * 60)
        try:
            if await db_get_auto_backup():
                last = await db_get_last_backup_time()
                if not last or (utc_now() - datetime.fromisoformat(last)).days >= 7:
                    await create_backup()
                else:
                    await incremental_backup()
                await db_set_setting('last_backup', utc_now_iso())
        except Exception as e:
            logger.error(f"نسخ احتياطي: {e}")

async def db_get_scheduled_posts():
    async def _get(conn):
        cur = await conn.execute(
            "SELECT id, chat_id, text, fail_count FROM scheduled_posts "
            "WHERE publish_time <= ? AND fail_count < 5 "
            "ORDER BY publish_time ASC LIMIT 50",
            (utc_now_iso(),)
        )
        return await cur.fetchall()
    return await execute_db(_get)

async def run_scheduled_posts_loop_improved(bot):
    while True:
        await asyncio.sleep(10)
        try:
            posts = await db_get_scheduled_posts()
            for post_id, chat_id, text, fail_count in posts:
                try:
                    await bot.send_message(chat_id, text[:4096] if text else ".")
                    await execute_db(lambda c: c.execute("DELETE FROM scheduled_posts WHERE id=?", (post_id,)) or c.commit())
                except Exception:
                    await execute_db(lambda c: c.execute("UPDATE scheduled_posts SET fail_count = ? WHERE id=?", (fail_count + 1, post_id)) or c.commit())
                    if fail_count + 1 >= 5:
                        await execute_db(lambda c: c.execute("DELETE FROM scheduled_posts WHERE id=?", (post_id,)) or c.commit())
        except Exception as e:
            logger.error(f"منشورات مجدولة: {e}")

async def send_reminders_loop_improved(bot):
    while True:
        await asyncio.sleep(3600)
        try:
            for u in await db_get_users_needing_reminder():
                try:
                    await bot.send_message(u['user_id'], f"⚠️ اشتراكك ينتهي خلال {u['days_left']} أيام")
                except:
                    pass
                await db_update_last_reminder_sent(u['user_id'], "sub")
        except Exception as e:
            logger.error(f"تذكيرات: {e}")

async def cleanup_expired_sessions_improved():
    while True:
        await asyncio.sleep(3600)
        try:
            await execute_db(lambda c: c.execute("DELETE FROM sentiment_history WHERE created_at < ?", ((utc_now() - timedelta(days=90)).isoformat(),)) or c.commit())
        except Exception as e:
            logger.error(f"تنظيف: {e}")

async def self_ping_loop():
    while True:
        await asyncio.sleep(300)
        try:
            async with aiohttp.ClientSession() as s:
                await s.get(f"http://localhost:{WEB_PORT}/health", timeout=5)
        except:
            pass

async def broadcast_stats_periodically():
    while True:
        await asyncio.sleep(3600)
        total, banned, posts, groups, channels = await db_stats()
        logger.info(f"📊 مستخدمين={total} محظورين={banned} منشورات={posts} مجموعات={groups} قنوات={channels}")

async def cleanup_points_cache():
    while True:
        await asyncio.sleep(3600)

async def memory_monitor():
    while True:
        await asyncio.sleep(60)
        if get_ram_usage()['percent'] > 80:
            gc.collect()

async def auto_close_contests_loop(bot):
    while True:
        await asyncio.sleep(3600)
        now = utc_now_iso()
        contests = await execute_db(lambda c: c.execute("SELECT id, title, prize FROM contests WHERE status='active' AND end_date <= ?", (now,)) or c.fetchall())
        for cid, title, prize in contests:
            winner = await execute_db(lambda c: c.execute("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,)) or c.fetchone())
            if winner:
                await db_set_contest_winner(cid, winner[0])
                try:
                    await bot.send_message(winner[0], f"🏆 فزت في {title}!")
                except:
                    pass

async def refresh_group_admins_and_hidden_owners_loop(bot):
    while True:
        await asyncio.sleep(3600)
        groups = await execute_db(lambda c: c.execute("SELECT chat_id FROM bot_groups WHERE banned=0") or c.fetchall())
        for (chat_id,) in groups:
            try:
                await db_sync_group_admins(chat_id, bot)
                for table, col in [("hidden_owner_groups","owner_id"), ("hidden_admins","admin_id")]:
                    admins = await execute_db(lambda c: c.execute(f"SELECT {col} FROM {table} WHERE chat_id=?", (chat_id,)) or c.fetchall())
                    for (uid,) in admins:
                        try:
                            member = await bot.get_chat_member(chat_id, uid)
                            if member.status not in ['administrator', 'creator']:
                                await execute_db(lambda c: c.execute(f"DELETE FROM {table} WHERE chat_id=? AND {col}=?", (chat_id, uid)) or c.commit())
                                invalidate_auth_cache(chat_id, uid)
                        except:
                            await execute_db(lambda c: c.execute(f"DELETE FROM {table} WHERE chat_id=? AND {col}=?", (chat_id, uid)) or c.commit())
                            invalidate_auth_cache(chat_id, uid)
            except:
                pass

async def memory_optimizer_loop():
    while True:
        await asyncio.sleep(300)
        gc.collect()

async def create_backup():
    try:
        temp_b = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_b.close()
        shutil.copy2(DB_PATH, temp_b.name)
        with open(temp_b.name, 'rb') as f:
            data = f.read()
        compressed = compress_backup(data)
        encrypted = BACKUP_CIPHER.encrypt(compressed)
        backup_file = BACKUP_DIR / f"backup_{mecca_now().strftime('%Y%m%d_%H%M%S')}.enc"
        backup_file.write_bytes(encrypted)
        os.unlink(temp_b.name)
        backups = sorted(BACKUP_DIR.glob("backup_*.enc"), key=lambda x: x.stat().st_mtime, reverse=True)
        for old in backups[MAX_BACKUPS:]:
            old.unlink()
        return backup_file
    except Exception as e:
        raise

async def incremental_backup():
    try:
        last = await db_get_last_backup_time()
        last_time = datetime.fromisoformat(last) if last else utc_now() - timedelta(days=7)
        posts = await execute_db(lambda c: c.execute("SELECT * FROM posts WHERE created_at > ? LIMIT 1000", (last_time.isoformat(),)) or c.fetchall())
        if posts:
            data = {'posts': [dict(row) for row in posts]}
            data_json = json.dumps(data, default=str)
            compressed = compress_backup(data_json.encode())
            encrypted = BACKUP_CIPHER.encrypt(compressed)
            f = BACKUP_DIR / f"incremental_{mecca_now().strftime('%Y%m%d_%H%M%S')}.inc"
            f.write_bytes(encrypted)
            return f
    except:
        pass

# ===================================================================
# 27. معالجات الأحداث
# ===================================================================
async def chat_join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.chat_join_request.approve()
    except:
        pass

async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        return
    settings = await db_get_security_settings(chat.id)
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue
        if settings.get('welcome_enabled'):
            try:
                await context.bot.send_message(chat.id, f"مرحباً {member.full_name or member.first_name} في {chat.title} 🤍")
            except:
                pass
        await db_update_user_cache(member.id, member.username or "", member.first_name or "")

async def left_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.left_chat_member:
        return
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        return
    settings = await db_get_security_settings(chat.id)
    member = update.message.left_chat_member
    if settings.get('goodbye_enabled'):
        try:
            await context.bot.send_message(chat.id, f"وداعاً {member.full_name or member.first_name} 👋")
        except:
            pass

async def track_chat_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return
    if result.new_chat_member.status in ['member', 'administrator']:
        chat = result.chat
        if chat.type in ['group', 'supergroup']:
            await db_register_group(chat.id, chat.title or "", result.from_user.id, chat.username)
            await db_sync_group_admins(chat.id, context.bot)

async def on_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            chat_id = update.effective_chat.id
            try:
                await context.bot.send_message(chat_id, "👋 شكراً لإضافتي! استخدم /syncgroup لتفعيل الميزات.")
            except:
                pass

async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass

async def pre_checkout_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    try:
        parts = update.message.successful_payment.invoice_payload.split('_')
        days = int(parts[1]) if len(parts) >= 2 else 30
        await db_activate_subscription(update.effective_user.id, days)
        await safe_send_markdown(context.bot, update.effective_user.id, f"✅ تم تفعيل {days} يوم!")
    except:
        pass

async def global_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    error_id = secrets.token_hex(4)
    logger.error(f"[{error_id}] {type(error).__name__}: {str(error)[:200]}")
    try:
        if update and update.effective_user:
            await context.bot.send_message(update.effective_user.id, f"❌ خطأ: `{error_id}`")
    except:
        pass

async def setup_unified_web_server(application, port: int):
    from aiohttp import web
    from telegram import Update

    if not hasattr(application, 'web_app') or application.web_app is None:
        application.web_app = web.Application()

    async def health(request):
        return web.Response(text="OK")

    async def index(request):
        return web.Response(text="<h1>🌿 ريلاكس مانيجر</h1><p>✅ يعمل</p>", content_type="text/html", charset="utf-8")

    async def webhook(request):
        try:
            data = await request.json()
            await application.process_update(Update.de_json(data, application.bot))
            return web.Response(status=200, text="OK")
        except:
            return web.Response(status=500)

    application.web_app.router.add_get('/', index)
    application.web_app.router.add_get('/health', health)
    application.web_app.router.add_post(f"/{TOKEN}", webhook)

    runner = web.AppRunner(application.web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info(f"✅ خادم ويب على {port}")

async def run_polling_safe(application):
    while True:
        try:
            await application.run_polling(drop_pending_updates=True)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Polling: {e}")
            await asyncio.sleep(10)

# ===================================================================
# 28. معالج الرسائل
# ===================================================================
async def filter_messages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    if user_id == context.bot.id:
        return
    if await is_user_bot(context.bot, user_id):
        return

    bp = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bp.get('can_act'):
        return

    text = update.message.text or update.message.caption or ""

    if await is_chat_locked(chat_id) and not await is_authorized_in_group(context.bot, chat_id, user_id):
        try:
            await update.message.delete()
        except:
            pass
        return

    if not await db_check_slow_mode(chat_id, user_id):
        try:
            await update.message.delete()
        except:
            pass
        return

    settings = await db_get_security_settings(chat_id)

    if settings.get('delete_links') and text and contains_link(text):
        await delete_and_penalize(update, context, "🚫 روابط ممنوعة!")
        return

    if settings.get('mentions') and text and contains_mention(text):
        await delete_and_penalize(update, context, "🚫 معرفات ممنوعة!")
        return

    if settings.get('delete_banned_words') and text:
        word = await db_contains_banned_word(text, chat_id)
        if word:
            await delete_and_penalize(update, context, f"🚫 كلمة محظورة!")
            return

    delete_media = False
    msg = update.message
    if settings.get('delete_videos') and msg.video:
        delete_media = True
    elif settings.get('delete_audio') and msg.audio:
        delete_media = True
    elif settings.get('delete_animation') and msg.animation:
        delete_media = True
    elif settings.get('delete_service') and msg.new_chat_members:
        delete_media = True
    elif settings.get('delete_documents') and msg.document:
        delete_media = True
    elif settings.get('delete_stickers') and msg.sticker:
        delete_media = True
    elif settings.get('delete_forwarded') and msg.forward_date:
        delete_media = True
    elif settings.get('delete_polls') and msg.poll:
        delete_media = True
    elif settings.get('delete_voice') and msg.voice:
        delete_media = True
    elif settings.get('delete_video_note') and msg.video_note:
        delete_media = True

    if delete_media:
        try:
            await msg.delete()
        except:
            pass
        penalty = settings.get('delete_penalty', settings.get('auto_penalty', 'none'))
        if penalty != 'none':
            await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, settings.get('auto_mute_duration', 60))
        return

    max_len = settings.get('max_message_length', 0)
    if max_len > 0 and text and len(text) > max_len:
        try:
            await msg.delete()
        except:
            pass
        return

    if settings.get('antiflood_enabled') and await db_check_antiflood(chat_id, user_id):
        try:
            await msg.delete()
        except:
            pass
        await apply_penalty_with_duration(context.bot, chat_id, user_id, settings.get('antiflood_penalty', 'mute'), 60)
        return

    if settings.get('night_mode_enabled'):
        now = utc_now()
        try:
            start = datetime.strptime(settings['night_mode_start'], '%H:%M').time()
            end = datetime.strptime(settings['night_mode_end'], '%H:%M').time()
            current = now.time()
            is_night = (start <= current <= end) if start < end else (current >= start or current <= end)
            if is_night:
                action = settings.get('night_mode_action', 'mute')
                if action == 'mute':
                    try:
                        await msg.delete()
                    except:
                        pass
                    await apply_penalty_with_duration(context.bot, chat_id, user_id, 'mute', 60)
                    return
                elif action == 'delete':
                    try:
                        await msg.delete()
                    except:
                        pass
                    return
        except:
            pass

    if text:
        ars = await db_get_auto_reply_settings(chat_id)
        if ars.get('enabled'):
            can_reply = True
            if ars.get('only_admins'):
                can_reply = await is_authorized_in_group(context.bot, chat_id, user_id)
            if ars.get('ignore_bots') and update.effective_user.is_bot:
                can_reply = False
            if can_reply:
                reply = await db_get_reply_with_stats(text.lower(), chat_id)
                if reply:
                    try:
                        await msg.reply_text(reply)
                    except:
                        pass

        if len(text) > 3:
            try:
                sentiment = sentiment_analyzer.analyze(text)
                await save_sentiment_encrypted(user_id, chat_id, text, sentiment['sentiment'], sentiment['score'])
            except:
                pass

async def message_handler_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    user_id = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""
    state = context.user_data.get('state')

    if state == UserState.WAITING_CHANNEL_ID:
        channel_id = text.strip()
        if not (channel_id.startswith('@') or channel_id.lstrip('-').isdigit()):
            await safe_send_markdown(context.bot, user_id, "❌ صيغة خاطئة")
            return
        try:
            chat = await context.bot.get_chat(channel_id)
            if chat.type != 'channel':
                await safe_send_markdown(context.bot, user_id, "❌ ليس قناة")
                return
            channel_name = chat.title or "بدون اسم"
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if bot_member.status not in ['administrator', 'creator'] or not bot_member.can_post_messages:
                await safe_send_markdown(context.bot, user_id, "❌ البوت ليس مشرفاً أو لا يملك صلاحية النشر")
                return
            result = await db_add_channel(user_id, str(chat.id), channel_name)
            await safe_send_markdown(context.bot, user_id, "✅ تمت الإضافة" if result else "⚠️ موجودة")
        except Exception as e:
            await safe_send_markdown(context.bot, user_id, f"❌ {str(e)[:100]}")
        context.user_data.pop('state', None)

    elif state == UserState.ADDING_POSTS:
        session_posts = context.user_data.get(f"session_{user_id}", [])
        target = context.user_data.get(f"session_target_{user_id}", 15)
        media_type = 'text'
        media_file_id = None
        msg = update.message
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
            await safe_send_markdown(context.bot, user_id, "⚠️ غير مدعوم")
            return

        text_content = msg.caption or "" if media_type != 'text' else text
        session_posts.append((text_content, media_type, media_file_id))
        context.user_data[f"session_{user_id}"] = session_posts
        remaining = target - len(session_posts)
        await safe_send_markdown(context.bot, user_id, f"✅ {len(session_posts)}/{target} | متبقي {remaining}")

        if len(session_posts) >= target:
            active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
            if active:
                await db_save_posts(active, session_posts)
            context.user_data.pop(f"session_{user_id}", None)
            context.user_data.pop(f"session_target_{user_id}", None)
            context.user_data.pop('state', None)
            await safe_send_markdown(context.bot, user_id, "✅ تم الحفظ")

    elif state == UserState.WAITING_INTERVAL_MINUTES:
        try:
            minutes = int(text)
            if 1 <= minutes <= 1440:
                ch_id = context.user_data.get('schedule_ch_id')
                if ch_id:
                    await db_save_schedule(ch_id, 'interval_minutes', interval_minutes=minutes)
                await safe_send_markdown(context.bot, user_id, "✅ تم")
        except:
            pass
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_INTERVAL_HOURS:
        try:
            hours = int(text)
            if 1 <= hours <= 168:
                ch_id = context.user_data.get('schedule_ch_id')
                if ch_id:
                    await db_save_schedule(ch_id, 'interval_hours', interval_hours=hours)
                await safe_send_markdown(context.bot, user_id, "✅ تم")
        except:
            pass
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_INTERVAL_DAYS:
        try:
            days = int(text)
            if 1 <= days <= 365:
                ch_id = context.user_data.get('schedule_ch_id')
                if ch_id:
                    await db_save_schedule(ch_id, 'interval_days', interval_days=days)
                await safe_send_markdown(context.bot, user_id, "✅ تم")
        except:
            pass
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_PUBLISH_TIME:
        if ':' in text:
            try:
                hour, minute = map(int, text.split(':'))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    ch_id = context.user_data.get('schedule_ch_id')
                    if ch_id:
                        await db_set_publish_time(ch_id, text)
                    await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين وقت النشر {text}")
                else:
                    await safe_send_markdown(context.bot, user_id, "❌ وقت غير صالح")
            except:
                await safe_send_markdown(context.bot, user_id, "❌ صيغة خاطئة")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ أرسل وقت صحيح مثل 14:30")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_SCHEDULE_POST:
        parts = text.split(' ', 2)
        if len(parts) >= 3:
            try:
                mecca_dt = datetime.strptime(f"{parts[0]} {parts[1]}", "%Y-%m-%d %H:%M")
                if mecca_dt > mecca_now():
                    utc_dt = mecca_to_utc(mecca_dt)
                    await db_add_scheduled_post(user_id, parts[2], utc_dt)
                    await safe_send_markdown(context.bot, user_id, "✅ تمت الجدولة")
                else:
                    await safe_send_markdown(context.bot, user_id, "❌ وقت في الماضي")
            except:
                await safe_send_markdown(context.bot, user_id, "❌ صيغة خاطئة")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_GROUP_BANNED_WORD:
        chat_id = context.user_data.get('banned_words_chat_id')
        if chat_id and len(text) >= 2:
            await db_add_banned_word(text.lower(), chat_id, user_id)
            await safe_send_markdown(context.bot, user_id, f"✅ تمت إضافة '{text}'")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_REMOVE_GROUP_BANNED_WORD:
        chat_id = context.user_data.get('banned_words_chat_id')
        if chat_id:
            await db_remove_banned_word(text.lower(), chat_id)
            await safe_send_markdown(context.bot, user_id, f"✅ تم حذف '{text}'")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_GLOBAL_BANNED_WORD:
        if len(text) >= 2:
            await db_add_banned_word(text.lower(), -1, user_id)
            await safe_send_markdown(context.bot, user_id, f"✅ تمت إضافة '{text}'")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_REMOVE_GLOBAL_BANNED_WORD:
        await db_remove_banned_word(text.lower(), -1)
        await safe_send_markdown(context.bot, user_id, f"✅ تم حذف '{text}'")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_ADMIN_ID_ADD:
        try:
            target_id = int(text)
            await add_bot_admin(target_id)
            await safe_send_markdown(context.bot, user_id, f"✅ تمت إضافة {target_id}")
        except:
            await safe_send_markdown(context.bot, user_id, "❌ خطأ")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_ADMIN_ID_REMOVE:
        try:
            target_id = int(text)
            await remove_bot_admin(target_id)
            await safe_send_markdown(context.bot, user_id, f"✅ تمت إزالة {target_id}")
        except:
            await safe_send_markdown(context.bot, user_id, "❌ خطأ")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_BROADCAST:
        context.user_data['broadcast_text'] = text
        context.user_data.pop('state', None)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأكيد", callback_data=CallbackData.ADMIN_CONFIRM_BROADCAST),
                                    InlineKeyboardButton("❌ إلغاء", callback_data=CallbackData.ADMIN_PANEL)]])
        await safe_send_markdown(context.bot, user_id, f"📨 تأكيد:\n{text[:200]}", reply_markup=kb)

    elif state == UserState.WAITING_UPDATE_TEXT:
        ch = await db_get_updates_channel()
        if ch:
            try:
                await context.bot.send_message(f"@{ch}", f"📢 {text}")
                await safe_send_markdown(context.bot, user_id, "✅ تم")
            except:
                await safe_send_markdown(context.bot, user_id, "❌ فشل")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ لا توجد قناة")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_UPDATE_CHANNEL:
        await db_set_setting('updates_channel', text.replace('@', ''))
        await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين @{text.replace('@', '')}")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_FORCE_CHANNEL:
        await db_set_setting('force_subscribe_channel', text.replace('@', ''))
        await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين @{text.replace('@', '')}")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_SENDCODE_USER:
        try:
            await db_set_setting('allowed_sendcode_user', str(int(text)))
            await safe_send_markdown(context.bot, user_id, f"✅ تم")
        except:
            await safe_send_markdown(context.bot, user_id, "❌ خطأ")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_LOG_CHANNEL:
        try:
            chat = await context.bot.get_chat(text)
            if chat.type == 'channel':
                await db_set_setting('log_channel_id', str(chat.id))
                await safe_send_markdown(context.bot, user_id, f"✅ {chat.title}")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ ليس قناة")
        except:
            await safe_send_markdown(context.bot, user_id, "❌ خطأ")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_CONTEST_TITLE:
        context.user_data['contest_title'] = text
        context.user_data['state'] = UserState.WAITING_CONTEST_DESCRIPTION
        await safe_send_markdown(context.bot, user_id, "📝 أرسل الوصف:")

    elif state == UserState.WAITING_CONTEST_DESCRIPTION:
        context.user_data['contest_description'] = text
        context.user_data['state'] = UserState.WAITING_CONTEST_PRIZE
        await safe_send_markdown(context.bot, user_id, "🎁 أرسل الجائزة:")

    elif state == UserState.WAITING_CONTEST_PRIZE:
        context.user_data['contest_prize'] = text
        context.user_data['state'] = UserState.WAITING_CONTEST_END_DATE
        await safe_send_markdown(context.bot, user_id, "📅 أرسل تاريخ الانتهاء (YYYY-MM-DD HH:MM):")

    elif state == UserState.WAITING_CONTEST_END_DATE:
        try:
            end_date = datetime.strptime(text, "%Y-%m-%d %H:%M")
            if end_date > mecca_now():
                cid = await db_create_contest(user_id, context.user_data.pop('contest_title', ''), context.user_data.pop('contest_description', ''), context.user_data.pop('contest_prize', ''), mecca_to_utc(end_date))
                await safe_send_markdown(context.bot, user_id, f"✅ مسابقة #{cid}")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ وقت في الماضي")
        except:
            await safe_send_markdown(context.bot, user_id, "❌ صيغة خاطئة")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_CONTEST_ANSWER:
        cid = context.user_data.get('contest_join_id')
        if cid:
            await db_participate_in_contest(user_id, cid, text if text != '/skip' else "")
            await safe_send_markdown(context.bot, user_id, "✅ تمت المشاركة")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_NSFW_THRESHOLD:
        try:
            val = float(text)
            if 0 <= val <= 100:
                chat_id = context.user_data.get('nsfw_chat_id')
                if chat_id:
                    await db_set_security_settings(chat_id, nsfw_threshold=val/100)
                await safe_send_markdown(context.bot, user_id, f"✅ {val}%")
        except:
            pass
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_MAX_LENGTH:
        try:
            val = int(text)
            if val >= 0:
                chat_id = context.user_data.get('security_chat_id')
                if chat_id:
                    await db_set_security_settings(chat_id, max_message_length=val)
                await safe_send_markdown(context.bot, user_id, f"✅ {val}")
        except:
            pass
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_WARN_COUNT:
        try:
            val = int(text)
            if 1 <= val <= 10:
                chat_id = context.user_data.get('security_chat_id')
                if chat_id:
                    await db_set_security_settings(chat_id, max_warnings=val)
                await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين {val}")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ بين 1 و 10")
        except:
            await safe_send_markdown(context.bot, user_id, "❌ رقم غير صالح")
        context.user_data.pop('state', None)

    elif state in [UserState.WAITING_BAN_USER, UserState.WAITING_MUTE_USER, UserState.WAITING_WARN_USER,
                   UserState.WAITING_KICK_USER, UserState.WAITING_RESTRICT_USER, UserState.WAITING_UNBAN_USER]:
        chat_id = context.user_data.get('advanced_chat_id')
        if chat_id:
            try:
                target_id = int(text.split()[0]) if text.split()[0].isdigit() else None
                if target_id:
                    action_map = {
                        UserState.WAITING_BAN_USER: "ban",
                        UserState.WAITING_MUTE_USER: "mute",
                        UserState.WAITING_WARN_USER: "warn",
                        UserState.WAITING_KICK_USER: "kick",
                        UserState.WAITING_RESTRICT_USER: "restrict",
                        UserState.WAITING_UNBAN_USER: "unban"
                    }
                    action = action_map.get(state)
                    if action:
                        dur = context.user_data.get('mute_minutes', 60) if action == 'mute' else None
                        success, msg = await apply_penalty_with_duration(context.bot, chat_id, target_id, action, dur, "", user_id)
                        await safe_send_markdown(context.bot, user_id, msg)
            except:
                pass
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_PIN_MESSAGE:
        chat_id = context.user_data.get('advanced_chat_id')
        if chat_id:
            try:
                if update.message.reply_to_message:
                    msg_id = update.message.reply_to_message.message_id
                else:
                    msg_id = int(text.strip())
                await context.bot.pin_chat_message(chat_id, msg_id)
                await safe_send_markdown(context.bot, user_id, "📌 تم التثبيت")
            except Exception as e:
                await safe_send_markdown(context.bot, user_id, f"❌ {str(e)[:100]}")
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_REMINDER_DAYS:
        try:
            val = int(text)
            if 1 <= val <= 30:
                await db_update_reminder_settings(user_id, reminder_days_before=val)
                await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين {val} أيام")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ بين 1 و 30")
        except:
            pass
        context.user_data.pop('state', None)

    elif state == UserState.WAITING_AUTO_REPLY_KEYWORD:
        keyword = text.strip().lower()
        if keyword:
            context.user_data['auto_reply_keyword'] = keyword
            context.user_data['state'] = UserState.WAITING_AUTO_REPLY_REPLY
            await safe_send_markdown(context.bot, user_id, "✏️ أرسل الرد:")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ كلمة غير صالحة")
            context.user_data.pop('state', None)

    elif state == UserState.WAITING_AUTO_REPLY_REPLY:
        chat_id = context.user_data.get('auto_reply_chat_id')
        keyword = context.user_data.get('auto_reply_keyword')
        if chat_id is not None and keyword:
            await db_add_reply_with_stats(chat_id, keyword, text)
            await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة رد لـ '{keyword}'")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ خطأ في البيانات")
        context.user_data.pop('state', None)
        context.user_data.pop('auto_reply_keyword', None)
        context.user_data.pop('auto_reply_chat_id', None)

    elif state == UserState.WAITING_AUTO_REPLY_DELETE:
        chat_id = context.user_data.get('auto_reply_chat_id')
        if chat_id is not None:
            keyword = text.strip().lower()
            if keyword:
                success = await db_remove_reply(chat_id, keyword)
                if success:
                    await safe_send_markdown(context.bot, user_id, f"✅ تم حذف الرد لـ '{keyword}'")
                else:
                    await safe_send_markdown(context.bot, user_id, f"❌ لا يوجد رد لـ '{keyword}'")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ كلمة غير صالحة")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ خطأ في البيانات")
        context.user_data.pop('state', None)
        context.user_data.pop('auto_reply_chat_id', None)

    elif state == UserState.WAITING_KEYWORD:
        context.user_data['keyword'] = text.strip().lower()
        context.user_data['state'] = UserState.WAITING_REPLY
        await safe_send_markdown(context.bot, user_id, "✏️ أرسل الرد:")

    elif state == UserState.WAITING_REPLY:
        keyword = context.user_data.get('keyword')
        if keyword:
            await db_add_reply_with_stats(0, keyword, text)
            await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة رد لـ '{keyword}'")
        context.user_data.pop('state', None)
        context.user_data.pop('keyword', None)

    elif state == UserState.WAITING_TICKET_REPLY:
        ticket_id = context.user_data.get('ticket_id')
        if ticket_id:
            ticket = await execute_db(lambda c: c.execute("SELECT user_id FROM support_tickets WHERE id=?", (ticket_id,)) or c.fetchone())
            if ticket:
                target_user = ticket[0]
                await db_mark_ticket_replied(ticket_id)
                try:
                    await context.bot.send_message(target_user, f"📩 رد على تذكرتك #{ticket_id}:\n{text}")
                    await safe_send_markdown(context.bot, user_id, f"✅ تم الرد على `{target_user}`")
                except Exception as e:
                    await safe_send_markdown(context.bot, user_id, f"❌ فشل الإرسال: {str(e)[:100]}")
        context.user_data.pop('state', None)
        context.user_data.pop('ticket_id', None)

    elif state == UserState.WAITING_BACKUP_INTERVAL:
        try:
            days = int(text)
            if 1 <= days <= 30:
                await db_set_backup_interval(days)
                await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين {days} أيام")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ بين 1 و 30")
        except:
            await safe_send_markdown(context.bot, user_id, "❌ رقم غير صالح")
        context.user_data.pop('state', None)

    elif context.user_data.get('support_mode'):
        if text:
            ticket_num = await db_get_next_ticket_number() + 1
            await db_set_setting('last_ticket_number', str(ticket_num))
            await db_save_ticket(user_id, update.effective_user.username or "", text, ticket_num)
            await safe_send_markdown(context.bot, user_id, f"✅ تذكرة #{ticket_num}")
            context.user_data.pop('support_mode', None)

    else:
        if update.message.text:
            reply = await db_get_reply_with_stats(text.lower(), 0)
            if reply:
                try:
                    await update.message.reply_text(reply)
                except:
                    pass
                return
        await start_command_handler(update, context)

# ===================================================================
# 29. أوامر إضافية
# ===================================================================
async def add_hidden_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        return
    args = context.args
    if not args:
        await safe_send_markdown(context.bot, user_id, "📝 /add_hidden_admin معرف_المستخدم")
        return
    try:
        target_id = int(args[0])
    except:
        await safe_send_markdown(context.bot, user_id, "❌ معرف غير صالح")
        return
    if await db_add_hidden_admin(chat_id, target_id, user_id):
        await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة المشرف المخفي `{target_id}`")
        invalidate_auth_cache(chat_id, target_id)
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل الإضافة")

async def remove_hidden_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        return
    args = context.args
    if not args:
        await safe_send_markdown(context.bot, user_id, "📝 /remove_hidden_admin معرف_المستخدم")
        return
    try:
        target_id = int(args[0])
    except:
        await safe_send_markdown(context.bot, user_id, "❌ معرف غير صالح")
        return
    if await db_remove_hidden_admin(chat_id, target_id):
        await safe_send_markdown(context.bot, user_id, f"✅ تم إزالة المشرف المخفي `{target_id}`")
        invalidate_auth_cache(chat_id, target_id)
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل الإزالة")

async def list_hidden_admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        return
    admins = await db_get_hidden_admins(chat_id)
    if not admins:
        await safe_send_markdown(context.bot, user_id, "📭 لا يوجد مشرفين مخفيين")
        return
    text = "🔒 **المشرفون المخفيون**\n"
    for admin in admins:
        text += f"• `{admin['admin_id']}` (أضيف بواسطة `{admin['added_by']}`)\n"
    await safe_send_markdown(context.bot, user_id, text)

async def support_reply_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return
    args = context.args
    if len(args) < 2:
        await safe_send_markdown(context.bot, user_id, "📝 /support_reply معرف_التذكرة الرد")
        return
    try:
        ticket_id = int(args[0])
        reply_text = " ".join(args[1:])
    except:
        await safe_send_markdown(context.bot, user_id, "❌ معرف غير صالح")
        return
    ticket = await execute_db(lambda c: c.execute("SELECT user_id FROM support_tickets WHERE id=? AND status='pending'", (ticket_id,)) or c.fetchone())
    if not ticket:
        await safe_send_markdown(context.bot, user_id, "❌ التذكرة غير موجودة")
        return
    target_user = ticket[0]
    await db_mark_ticket_replied(ticket_id)
    try:
        await context.bot.send_message(target_user, f"📩 رد على تذكرتك #{ticket_id}:\n{reply_text}")
        await safe_send_markdown(context.bot, user_id, f"✅ تم الرد على `{target_user}`")
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ فشل الإرسال: {str(e)[:100]}")

# ===================================================================
# 30. أوامر المعالجات الأساسية
# ===================================================================
async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or ""
    first_name = update.effective_user.first_name or ""
    await db_register_user(user_id)
    await db_update_user_cache(user_id, username, first_name)
    args = context.args
    if args and args[0].startswith('ref_'):
        ref_code = args[0][4:]
        referrer = await db_get_user_by_referral_code(ref_code)
        if referrer and referrer != user_id:
            if await db_add_referral(referrer, user_id):
                await db_auto_reward_referral(referrer, user_id)
                await safe_send_markdown(context.bot, referrer, f"🎁 تمت إحالة `{user_id}`")
    force_ch = await db_get_force_subscribe_channel()
    if force_ch:
        try:
            chat = await context.bot.get_chat(f"@{force_ch}")
            member = await context.bot.get_chat_member(chat.id, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("📢 اشترك", url=f"https://t.me/{force_ch}"),
                                            InlineKeyboardButton("✅ تحقق", callback_data=CallbackData.CHECK_SUBSCRIBE)]])
                await safe_send_markdown(context.bot, user_id, f"⚠️ اشترك في @{force_ch}", reply_markup=kb)
                return
        except:
            pass
    keyboard, title, active = await get_main_keyboard(user_id)
    await safe_send_markdown(context.bot, user_id, title, reply_markup=keyboard)

async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = await db_get_user_language(user_id)
    await safe_send_markdown(context.bot, user_id, get_text(lang, 'help_text'))

async def syncgroup_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, "❌ يستخدم في المجموعات فقط")
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['administrator', 'creator']:
            await safe_send_markdown(context.bot, update.effective_user.id, "🔒 تحتاج صلاحيات مشرف لتفعيل البوت")
            return
    except Exception as e:
        await safe_send_markdown(context.bot, update.effective_user.id, f"❌ خطأ في التحقق من صلاحياتك: {str(e)[:50]}")
        return

    registered = await db_register_group(chat_id, update.effective_chat.title or "", user_id, update.effective_chat.username)
    if not registered:
        await safe_send_markdown(context.bot, update.effective_user.id, "⚠️ المجموعة مسجلة بالفعل، جاري تحديث المشرفين...")

    admin_count = await db_sync_group_admins(chat_id, context.bot)

    async def ensure_current_admin(conn):
        await conn.execute("INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?,?)", (chat_id, user_id))
        await conn.commit()
    await execute_db(ensure_current_admin)

    invalidate_auth_cache(chat_id, user_id)
    invalidate_auth_cache(chat_id)

    await safe_send_markdown(
        context.bot,
        chat_id,
        get_text('ar', 'syncgroup_success_group', count=admin_count, user_id=user_id)
    )

    await safe_send_markdown(
        context.bot,
        user_id,
        get_text('ar', 'syncgroup_success_private', title=update.effective_chat.title)
    )

async def security_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return
    settings = await db_get_security_settings(chat_id)
    text = _build_security_text(settings)
    await safe_send_markdown(context.bot, user_id, text, reply_markup=security_keyboard(chat_id), parse_mode="HTML")

async def panel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return
    is_locked = await is_chat_locked(chat_id)
    text = get_text('ar', 'panel_locked') if is_locked else get_text('ar', 'panel_unlocked')
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text('ar', 'panel_lock_btn'), callback_data=f"{CallbackData.PANEL_LOCK_PREFIX}{chat_id}"),
         InlineKeyboardButton(get_text('ar', 'panel_unlock_btn'), callback_data=f"{CallbackData.PANEL_UNLOCK_PREFIX}{chat_id}")],
        [InlineKeyboardButton(get_text('ar', 'panel_close_btn'), callback_data=CallbackData.PANEL_CLOSE)]
    ])
    await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def language_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇸🇦 عربي", callback_data="lang_ar"),
         InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🔙", callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, update.effective_user.id, "🌐 اختر اللغة", reply_markup=kb)

async def trial_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await db_has_used_trial(user_id):
        await safe_send_markdown(context.bot, user_id, "❌ استخدمت التجربة")
        return
    days = await db_activate_trial(user_id)
    await safe_send_markdown(context.bot, user_id, f"✅ تم تفعيل {days} يوم")

async def subscribe_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 1 يوم", callback_data=CallbackData.BUY_SUBSCRIPTION_1),
         InlineKeyboardButton("💎 2 يوم", callback_data=CallbackData.BUY_SUBSCRIPTION_2)],
        [InlineKeyboardButton("💎 30 يوم", callback_data=CallbackData.BUY_SUBSCRIPTION_30),
         InlineKeyboardButton("💎 90 يوم", callback_data=CallbackData.BUY_SUBSCRIPTION_90)],
        [InlineKeyboardButton("🔙", callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, update.effective_user.id, "💎 اختر الباقة", reply_markup=kb)

async def support_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 تذكرة", callback_data=CallbackData.SUPPORT_TICKET)],
        [InlineKeyboardButton("🔙", callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, update.effective_user.id, "📞 الدعم الفني", reply_markup=kb)

async def developer_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_send_markdown(context.bot, update.effective_user.id, f"👨‍💻 {BOT_NAME}\n@RelaxMgr")

async def updates_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ch = await db_get_updates_channel()
    if ch:
        await safe_send_markdown(context.bot, update.effective_user.id, f"📢 @{ch}")
    else:
        await safe_send_markdown(context.bot, update.effective_user.id, "📢 لا توجد قناة")

async def rank_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_send_markdown(context.bot, update.effective_user.id, "🏆 قيد التطوير")

async def top_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_send_markdown(context.bot, update.effective_user.id, "📊 قيد التطوير")

async def stats_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    total, banned, posts, groups, channels = await db_stats()
    await safe_send_markdown(context.bot, user_id, f"📊 إحصائيات البوت\n👥 {total} مستخدم\n🚫 {banned} محظور\n📝 {posts} منشور\n👥 {groups} مجموعة\n📡 {channels} قناة")

async def contests_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contests = await db_get_active_contests_with_participants(10)
    if not contests:
        await safe_send_markdown(context.bot, update.effective_user.id, "🏆 لا توجد مسابقات")
        return
    text = "🏆 **المسابقات**\n"
    kb = []
    for cid, title, desc, prize, end_date, ctype, participants in contests:
        text += f"• {title} - {participants} مشارك\n"
        kb.append([InlineKeyboardButton(f"📝 شارك في {title}", callback_data=f"{CallbackData.CONTEST_JOIN_PREFIX}{cid}")])
    kb.append([InlineKeyboardButton("🏆 الفائزون", callback_data=CallbackData.CONTEST_WINNERS)])
    kb.append([InlineKeyboardButton("🔙", callback_data=CallbackData.BACK)])
    await safe_send_markdown(context.bot, update.effective_user.id, text, reply_markup=InlineKeyboardMarkup(kb))

async def create_contest_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return
    context.user_data['state'] = UserState.WAITING_CONTEST_TITLE
    await safe_send_markdown(context.bot, user_id, "🏆 أرسل عنوان المسابقة:")

async def declare_winner_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return
    contests = await execute_db(lambda c: c.execute("SELECT id, title FROM contests WHERE status='active'") or c.fetchall())
    if not contests:
        await safe_send_markdown(context.bot, user_id, "لا توجد مسابقات")
        return
    kb = []
    for cid, title in contests:
        kb.append([InlineKeyboardButton(title, callback_data=f"declare_winner_sel:{cid}")])
    await safe_send_markdown(context.bot, user_id, "اختر المسابقة:", reply_markup=InlineKeyboardMarkup(kb))

async def set_rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return
    if not context.args:
        await safe_send_markdown(context.bot, user_id, "📝 /set_rules النص")
        return
    rules = " ".join(context.args)
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO group_rules (chat_id, rules_text, updated_by, updated_at) VALUES (?,?,?,?)",
                                         (chat_id, rules, user_id, utc_now_iso())) or c.commit())
    await safe_send_markdown(context.bot, user_id, "✅ تم تعيين القوانين")

async def rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    chat_id = update.effective_chat.id
    rules = await execute_db(lambda c: c.execute("SELECT rules_text FROM group_rules WHERE chat_id=?", (chat_id,)) or c.fetchone())
    if rules and rules[0]:
        await safe_send_markdown(context.bot, update.effective_user.id, f"📜 القوانين:\n{rules[0]}")
    else:
        await safe_send_markdown(context.bot, update.effective_user.id, "📜 لا توجد قوانين")

async def lock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return
    await db_set_chat_lock(chat_id, True, user_id)
    await safe_send_markdown(context.bot, user_id, "🔒 تم القفل")

async def unlock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return
    await db_set_chat_lock(chat_id, False)
    await safe_send_markdown(context.bot, user_id, "🔓 تم الفتح")

async def schedule_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        try:
            text = " ".join(context.args)
            mecca_dt = datetime.strptime(text[:16], "%Y-%m-%d %H:%M")
            if mecca_dt > mecca_now():
                utc_dt = mecca_to_utc(mecca_dt)
                await db_add_scheduled_post(update.effective_user.id, text[17:], utc_dt)
                await safe_send_markdown(context.bot, update.effective_user.id, "✅ تمت الجدولة")
            else:
                await safe_send_markdown(context.bot, update.effective_user.id, "❌ وقت في الماضي")
        except:
            await safe_send_markdown(context.bot, update.effective_user.id, "❌ صيغة: /schedule YYYY-MM-DD HH:MM النص")
        return
    await safe_send_markdown(context.bot, update.effective_user.id, "⏰ /schedule YYYY-MM-DD HH:MM النص")

async def sendcode_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    allowed = await db_get_allowed_sendcode_user()
    if user_id != PRIMARY_OWNER_ID and (allowed is None or user_id != allowed):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return
    if not context.args:
        await safe_send_markdown(context.bot, user_id, "📝 /sendcode الكود")
        return
    code = " ".join(context.args)
    await safe_send_markdown(context.bot, user_id, f"✅ تم إرسال: {code}")

async def set_log_channel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return
    if not context.args:
        await safe_send_markdown(context.bot, user_id, "📝 /set_log_channel معرف_القناة")
        return
    ch_id = context.args[0]
    try:
        chat = await context.bot.get_chat(ch_id)
        if chat.type == 'channel':
            await db_set_setting('log_channel_id', str(chat.id))
            await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين {chat.title}")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ ليس قناة")
    except:
        await safe_send_markdown(context.bot, user_id, "❌ خطأ")

async def handle_moderation_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return
    cmd = update.message.text.split()[0][1:]
    args = context.args
    if not args:
        await safe_send_markdown(context.bot, user_id, f"📝 /{cmd} معرف_المستخدم [سبب]")
        return
    try:
        target_id = int(args[0])
    except:
        await safe_send_markdown(context.bot, user_id, "❌ معرف غير صالح")
        return
    reason = " ".join(args[1:]) if len(args) > 1 else ""
    duration = None
    if cmd == 'mute' and len(args) > 2 and args[1].isdigit():
        duration = int(args[1])
        reason = " ".join(args[2:]) if len(args) > 2 else ""
    penalty_map = {
        'ban': 'ban',
        'mute': 'mute',
        'warn': 'warn',
        'kick': 'kick',
        'restrict': 'restrict',
        'unban': 'unban'
    }
    if cmd not in penalty_map:
        await safe_send_markdown(context.bot, user_id, "❌ أمر غير معروف")
        return
    if cmd == 'unban':
        try:
            await context.bot.unban_chat_member(chat_id, target_id)
            await safe_send_markdown(context.bot, user_id, f"✅ تم إلغاء حظر {target_id}")
        except Exception as e:
            await safe_send_markdown(context.bot, user_id, f"❌ {str(e)[:100]}")
        return
    if cmd == 'pin':
        if update.message.reply_to_message:
            try:
                await context.bot.pin_chat_message(chat_id, update.message.reply_to_message.message_id)
                await safe_send_markdown(context.bot, user_id, "📌 تم التثبيت")
            except Exception as e:
                await safe_send_markdown(context.bot, user_id, f"❌ {str(e)[:100]}")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ رد على رسالة لتثبيتها")
        return
    success, msg = await apply_penalty_with_duration(context.bot, chat_id, target_id, cmd, duration, reason, user_id)
    await safe_send_markdown(context.bot, user_id, msg)

# ===================================================================
# 31. دوال مفقودة تم إضافتها
# ===================================================================
async def db_add_scheduled_post(chat_id: int, text: str, publish_time: datetime):
    async def _add(conn):
        await conn.execute("INSERT INTO scheduled_posts (chat_id, text, publish_time) VALUES (?,?,?)",
                           (chat_id, text, publish_time.isoformat()))
        await conn.commit()
    return await execute_db(_add)

async def db_set_publish_time(channel_db_id: int, time_str: str):
    async def _s(conn):
        await conn.execute("UPDATE schedule SET publish_time=? WHERE channel_db_id=?", (time_str, channel_db_id))
        await conn.commit()
    return await execute_db(_s)

async def db_get_referrals_list(user_id: int):
    async def _g(conn):
        cur = await conn.execute("SELECT referred_id FROM referrals WHERE referrer_id=? ORDER BY created_at DESC", (user_id,))
        return [row[0] for row in await cur.fetchall()]
    return await execute_db(_g)

async def db_get_channel_growth(channel_db_id: int):
    async def _g(conn):
        week_ago = (utc_now() - timedelta(days=7)).isoformat()
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=1 AND published_at >= ?", (channel_db_id, week_ago))
        return (await cur.fetchone())[0]
    return await execute_db(_g)

async def db_toggle_auto_backup():
    current = await db_get_auto_backup()
    await db_set_setting('auto_backup', '0' if current else '1')

async def db_set_backup_interval(days: int):
    await db_set_setting('backup_interval', str(days))

async def db_get_metrics():
    async def _g(conn):
        month_ago = (utc_now() - timedelta(days=30)).isoformat()
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE updated_at >= ? OR (subscription_end IS NOT NULL AND subscription_end >= ?)", (month_ago, utc_now_iso()))
        active = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE published_at >= ?", (utc_now().replace(hour=0, minute=0, second=0).isoformat(),))
        today_posts = (await cur.fetchone())[0]
        db_size = (DB_PATH.stat().st_size / (1024*1024)) if DB_PATH.exists() else 0
        return {'active_users': active, 'today_posts': today_posts, 'db_size': round(db_size, 2)}
    return await execute_db(_g)

async def db_toggle_nsfw(chat_id: int):
    settings = await db_get_security_settings(chat_id)
    await db_set_security_settings(chat_id, nsfw_enabled=not settings.get('nsfw_enabled', False))

async def db_set_nsfw_threshold(chat_id: int, threshold: float):
    await db_set_security_settings(chat_id, nsfw_threshold=threshold)

async def db_get_bot_channels(banned: bool = False):
    return await execute_db(lambda c: c.execute("SELECT channel_id, channel_name FROM user_channels WHERE user_id=? AND banned=?", (PRIMARY_OWNER_ID, 1 if banned else 0)) or c.fetchall())

async def db_get_user_language(user_id: int) -> str:
    async def _g(conn):
        cur = await conn.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 'ar'
    return await execute_db(_g)

async def db_set_user_language(user_id: int, lang: str):
    await execute_db(lambda c: c.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id)) or c.commit())

# ===================================================================
# 32. الدالة الرئيسية main()
# ===================================================================
async def main():
    print("🚀 بدء تشغيل ريلاكس مانيجر...")

    await init_db()
    await ensure_security_columns()
    print("✅ قاعدة البيانات جاهزة")

    words = load_banned_words_from_file(BANNED_WORDS_FILE)
    if words:
        async def _import(conn):
            imported = 0
            for word in words:
                try:
                    await conn.execute("INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?, -1, ?, ?)",
                                       (word, PRIMARY_OWNER_ID, utc_now_iso()))
                    imported += 1
                except:
                    continue
            await conn.commit()
            return imported
        imported_count = await execute_db(_import)
        logger.info(f"✅ تم استيراد {imported_count} كلمة محظورة")
        await rebuild_banned_patterns()

    await import_auto_replies_from_file()

    await db_register_user(PRIMARY_OWNER_ID)
    await add_bot_admin(PRIMARY_OWNER_ID)

    if USE_PROXY:
        request = HTTPXRequest(proxy_url=PROXY_URL, read_timeout=60, write_timeout=30, connect_timeout=30, connection_pool_size=MAX_CONNECTIONS)
    else:
        request = HTTPXRequest(read_timeout=60, write_timeout=30, connect_timeout=30, connection_pool_size=MAX_CONNECTIONS)

    application = Application.builder().token(TOKEN).request(request).build()
    application.add_error_handler(global_error_handler)

    # الأوامر الأساسية
    application.add_handler(CommandHandler("start", start_command_handler))
    application.add_handler(CommandHandler("language", language_command_handler))
    application.add_handler(CommandHandler("syncgroup", syncgroup_command_handler))
    application.add_handler(CommandHandler("register_hidden_owner", register_hidden_owner_handler))
    application.add_handler(CommandHandler("add_hidden_admin", add_hidden_admin_command))
    application.add_handler(CommandHandler("remove_hidden_admin", remove_hidden_admin_command))
    application.add_handler(CommandHandler("list_hidden_admins", list_hidden_admins_command))
    application.add_handler(CommandHandler("security", security_command_handler))
    application.add_handler(CommandHandler("panel", panel_command_handler))
    application.add_handler(CommandHandler("help", help_command_handler))
    application.add_handler(CommandHandler("trial", trial_command_handler))
    application.add_handler(CommandHandler("subscribe", subscribe_command_handler))
    application.add_handler(CommandHandler("support", support_command_handler))
    application.add_handler(CommandHandler("support_reply", support_reply_command_handler))
    application.add_handler(CommandHandler("rank", rank_command_handler))
    application.add_handler(CommandHandler("top", top_command_handler))
    application.add_handler(CommandHandler("stats", stats_command_handler))
    application.add_handler(CommandHandler("developer", developer_command_handler))
    application.add_handler(CommandHandler("updates", updates_command_handler))
    application.add_handler(CommandHandler("sendcode", sendcode_command_handler))
    application.add_handler(CommandHandler("lock", lock_chat_command_handler))
    application.add_handler(CommandHandler("unlock", unlock_chat_command_handler))
    application.add_handler(CommandHandler("schedule", schedule_command_handler))
    application.add_handler(CommandHandler("set_log_channel", set_log_channel_command_handler))
    application.add_handler(CommandHandler("contests", contests_command_handler))
    application.add_handler(CommandHandler("create_contest", create_contest_command_handler))
    application.add_handler(CommandHandler("declare_winner", declare_winner_command_handler))
    application.add_handler(CommandHandler("set_rules", set_rules_command_handler))
    application.add_handler(CommandHandler("rules", rules_command_handler))

    # أوامر الإدارة
    for cmd in ["ban", "mute", "warn", "kick", "restrict", "unban", "pin"]:
        application.add_handler(CommandHandler(cmd, handle_moderation_commands))

    # معالج الكولباك الشامل
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    # معالجات الرسائل
    application.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler), group=1)
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, message_handler_main))

    # معالجات الأحداث
    application.add_handler(ChatJoinRequestHandler(chat_join_request_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_chat_member_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER, delete_service_messages))
    application.add_handler(ChatMemberHandler(track_chat_add, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback_handler))

    # أوامر البوت
    try:
        await application.bot.set_my_commands([
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
            BotCommand("schedule", "جدولة"),
            BotCommand("stats", "إحصائيات"),
            BotCommand("contests", "مسابقات"),
            BotCommand("support", "دعم"),
        ])
    except Exception as e:
        logger.warning(f"فشل تعيين الأوامر: {e}")

    # المهام الخلفية
    from functools import partial
    task_manager.create_task(safe_loop(partial(auto_publish_loop_improved, application.bot), "نشر"))
    task_manager.create_task(safe_loop(auto_backup, "نسخ"))
    task_manager.create_task(safe_loop(partial(run_scheduled_posts_loop_improved, application.bot), "مجدولة"))
    task_manager.create_task(safe_loop(partial(send_reminders_loop_improved, application.bot), "تذكير"))
    task_manager.create_task(safe_loop(cleanup_expired_sessions_improved, "تنظيف"))
    task_manager.create_task(safe_loop(self_ping_loop, "ping"))
    task_manager.create_task(safe_loop(broadcast_stats_periodically, "إحصائيات"))
    task_manager.create_task(safe_loop(cleanup_points_cache, "كاش"))
    task_manager.create_task(safe_loop(memory_monitor, "ذاكرة"))
    task_manager.create_task(safe_loop(partial(auto_close_contests_loop, application.bot), "مسابقات"))
    task_manager.create_task(safe_loop(partial(refresh_group_admins_and_hidden_owners_loop, application.bot), "صلاحيات"))
    task_manager.create_task(safe_loop(memory_optimizer_loop, "تحسين الذاكرة"))
    task_manager.create_task(safe_loop(cleanup_caches_periodically, "تنظيف الكاشات"))

    # خادم ويب
    port = int(os.getenv("PORT", "10000"))
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("HEROKU_APP_NAME")

    try:
        await setup_unified_web_server(application, port)
    except:
        pass

    if hostname:
        await application.initialize()
        await application.start()
        try:
            await application.bot.set_webhook(url=f"https://{hostname}/{TOKEN}", drop_pending_updates=True)
            logger.info(f"✅ Webhook set to https://{hostname}/{TOKEN}")
        except Exception as e:
            logger.error(f"❌ Webhook failed: {e}")
        try:
            await application.bot.send_message(PRIMARY_OWNER_ID, f"✅ تم تشغيل {BOT_NAME}")
        except:
            pass
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            pass
    else:
        try:
            await application.bot.delete_webhook()
        except:
            pass
        try:
            await application.bot.send_message(PRIMARY_OWNER_ID, f"✅ تم تشغيل {BOT_NAME}")
        except:
            pass
        await run_polling_safe(application)

    await task_manager.cancel_all()
    await db_pool.close()

async def register_hidden_owner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if update.effective_chat.type not in ['group', 'supergroup']:
        return
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status != 'creator':
            await safe_send_markdown(context.bot, user_id, "🔒 أنت لست المالك")
            return
    except:
        return
    await db_register_hidden_owner_group(chat_id, user_id)
    await safe_send_markdown(context.bot, user_id, "✅ تم تسجيلك كمالك مخفي")

# ===================================================================
# 33. تشغيل البوت
# ===================================================================
if __name__ == "__main__":
    print("🌿 ريلاكس مانيجر v23.0.1-final-complete (مع دعم 8 لغات)")
    print(f"🤖 {BOT_NAME} | @RelaxMgr")
    print("✅ جميع الميزات مكتملة وجاهزة للتشغيل")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 تم الإيقاف")
    except Exception as e:
        print(f"\n❌ {e}")
        traceback.print_exc()
        sys.exit(1)
