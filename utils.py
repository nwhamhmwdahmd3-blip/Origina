#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
utils.py - الأدوات المساعدة للبوت (النسخة النهائية الكاملة والمكتملة)
=====================================================================
جميع الدوال والفئات موجودة - جميع الحالات مكتملة - جميع الثوابت معرّفة
- معالجة لغة off تلقائياً
- دعم كامل لجميع الأزرار
- دعم المشرفين المجهولين في is_authorized_in_group
- معالجة TimedOut مع إعادة المحاولة في safe_send
- كل قناة تنشر بشكل مستقل بفاصل 12 دقيقة
- حالة WAIT_MOOD لتحليل المشاعر
- رسالة تأكيد تحميل الردود
- دعم معاملات اختيارية في RateLimiter.acquire لمنع TypeError
- إزالة رموز ** من نصوص الأمان لمنع 400 Bad Request
"""

import asyncio
import re
import json
import time
import html
import logging
import random
import importlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple, Any, Union
from enum import Enum, auto
from collections import OrderedDict, deque
from abc import ABC, abstractmethod

try:
    import psutil
except ImportError:
    psutil = None

import aiohttp

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions, Update
from telegram.error import BadRequest, TimedOut
from telegram.ext import ContextTypes
from cachetools import TTLCache

import aiohttp.web as web

from config import CONFIG, PATHS
from database import DB

logger = logging.getLogger(__name__)


# =====================================================================
# 1. أدوات الوقت
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
    def sql_iso() -> str:
        return TimeUtils.utc_now().strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def mecca_to_utc(dt: Optional[datetime]) -> Optional[datetime]:
        return dt - timedelta(hours=3) if dt else None

    @staticmethod
    def utc_to_mecca(dt: Optional[datetime]) -> Optional[datetime]:
        return dt + timedelta(hours=3) if dt else None

    @staticmethod
    def safe_parse_iso(date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return None


# =====================================================================
# 2. أدوات النصوص
# =====================================================================

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
    def escape_html(text: str) -> str:
        if not text:
            return ""
        return html.escape(text)

    @staticmethod
    def truncate(text: str, max_len: int = 200) -> str:
        return text[:max_len] + ("..." if len(text) > max_len else "")


# =====================================================================
# 3. Rate Limiter
# =====================================================================

class RateLimiter:
    def __init__(self, max_concurrent: int = 10, max_per_second: int = 30):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._last_calls = deque(maxlen=max_per_second * 2)
        self._lock = asyncio.Lock()
        self.max_per_second = max_per_second

    async def acquire(self, *args, **kwargs):
        async with self.semaphore:
            async with self._lock:
                now = time.time()
                while self._last_calls and now - self._last_calls[0] > 1:
                    self._last_calls.popleft()
                if len(self._last_calls) >= self.max_per_second:
                    wait_time = 1 - (now - self._last_calls[0])
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
                self._last_calls.append(now)


RATE_LIMITER = RateLimiter(max_concurrent=15, max_per_second=30)


# =====================================================================
# 4. مقاييس الأداء
# =====================================================================

class MetricsCollector:
    def __init__(self):
        self.api_calls = deque(maxlen=1000)
        self.errors = deque(maxlen=1000)
        self.messages_processed = 0
        self.start_time = time.time()

    def record_api_call(self, method: str, duration: float):
        self.api_calls.append((time.time(), method, duration))

    def record_error(self, error_type: str, context: str = ""):
        self.errors.append((time.time(), error_type, context))

    def get_stats(self) -> dict:
        now = time.time()
        return {
            'api_calls_last_hour': sum(1 for t, _, _ in self.api_calls if now - t < 3600),
            'errors_last_hour': sum(1 for t, _, _ in self.errors if now - t < 3600),
            'uptime_seconds': int(now - self.start_time),
            'messages_processed': self.messages_processed,
            'total_api_calls': len(self.api_calls),
            'total_errors': len(self.errors)
        }

    def increment_messages(self):
        self.messages_processed += 1


METRICS = MetricsCollector()


# =====================================================================
# 5. كاش الردود
# =====================================================================

class AutoReplyCache:
    def __init__(self, maxsize: int = 300):
        self.cache = OrderedDict()
        self.maxsize = maxsize

    def get(self, key: str):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key: str, value: dict):
        self.cache[key] = value
        if len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)

    def invalidate(self, key: str = None):
        if key:
            self.cache.pop(key, None)
        else:
            self.cache.clear()

    def clear(self):
        self.cache.clear()


_auto_reply_cache = AutoReplyCache(maxsize=300)


# =====================================================================
# 6. الترجمات
# =====================================================================

class TranslationManager:
    _translations: Dict[str, Dict] = {}
    _locales_dir: str = str(Path(__file__).resolve().parent / "locales")
    _default_lang: str = "ar"

    @classmethod
    def load_translation(cls, lang: str) -> Dict:
        if lang == 'off':
            lang = cls._default_lang
        if lang in cls._translations:
            return cls._translations[lang]
        file_path = Path(cls._locales_dir) / f"{lang}.json"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                cls._translations[lang] = json.load(f)
                return cls._translations[lang]
        except:
            if lang != cls._default_lang:
                return cls.load_translation(cls._default_lang)
            return {}

    @classmethod
    def get_text(cls, lang: str, key: str, **kwargs) -> str:
        translations = cls.load_translation(lang)
        template = translations.get(key)
        if template is None and lang != cls._default_lang:
            template = cls.load_translation(cls._default_lang).get(key)
        if template is None:
            template = key
        try:
            return template.format_map(kwargs)
        except (KeyError, IndexError):
            return template

    @classmethod
    def get_available_languages(cls) -> Dict[str, str]:
        return {
            "ar": "العربية 🇸🇦",
            "en": "English 🇬🇧",
            "fr": "Français 🇫🇷",
            "tr": "Türkçe 🇹🇷",
            "zh": "中文 🇨🇳",
            "ru": "Русский 🇷🇺",
            "de": "Deutsch 🇩🇪",
            "es": "Español 🇪🇸",
            "it": "Italiano 🇮🇹",
            "pt": "Português 🇵🇹",
            "ja": "日本語 🇯🇵",
            "ko": "한국어 🇰🇷"
        }


async def get_text(lang: str, key: str, **kwargs) -> str:
    return TranslationManager.get_text(lang, key, **kwargs)


# =====================================================================
# 7. إدارة الحالات
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
    WAIT_IMPORT_FILE = auto()
    WAIT_GITHUB_URL = auto()
    WAIT_GRANT_FREE = auto()
    WAIT_PENALTY_DURATION = auto()
    WAIT_VIOLATION_STRIKES = auto()
    WAIT_VIOLATION_DURATION = auto()
    SUPPORT_MODE = auto()
    WAIT_REDEEM_GIFT = auto()
    WAIT_ANTIFLOOD_MESSAGES = auto()
    WAIT_ANTIFLOOD_SECONDS = auto()
    WAIT_NIGHT_START = auto()
    WAIT_NIGHT_END = auto()
    WAIT_WELCOME_TEXT = auto()
    WAIT_GOODBYE_TEXT = auto()
    WAIT_SLOW_MODE_SECONDS = auto()
    WAIT_PENALTY_DEFAULT_DURATION = auto()
    WAIT_CONTEST_WINNER = auto()
    WAIT_PENALTY_MUTE_DURATION = auto()
    WAIT_PENALTY_BAN_DURATION = auto()
    WAIT_PENALTY_RESTRICT_DURATION = auto()
    WAIT_MOOD = auto()


class StateManager:
    _states: Dict[int, UserState] = {}
    _timestamps: Dict[int, float] = {}
    _timeout = 300

    @classmethod
    def get(cls, user_id: int) -> UserState:
        if user_id in cls._timestamps:
            if time.time() - cls._timestamps[user_id] > cls._timeout:
                cls.clear(user_id)
        return cls._states.get(user_id, UserState.NONE)

    @classmethod
    def set(cls, user_id: int, state: UserState) -> None:
        cls._states[user_id] = state
        cls._timestamps[user_id] = time.time()

    @classmethod
    def clear(cls, user_id: int) -> None:
        cls._states.pop(user_id, None)
        cls._timestamps.pop(user_id, None)

    @classmethod
    def is_expired(cls, user_id: int, timeout: int = None) -> bool:
        if user_id not in cls._timestamps:
            return False
        ttl = timeout or cls._timeout
        return time.time() - cls._timestamps[user_id] > ttl


# =====================================================================
# 8. تعريفات الأزرار (CB) - كاملة
# =====================================================================

class CB:
    MAIN = "main"
    BACK = "back"
    CANCEL = "cancel"
    HELP = "help"
    SETTINGS = "settings"
    LANGUAGE = "language"
    CHECK_SUB = "check_sub"

    CH_ADD = "ch_add"
    CH_LIST = "ch_list"
    CH_SEL = "ch_sel"
    CH_DEL = "ch_del"
    CH_STATS = "ch_stats"

    POST_ADD = "post_add"
    POST_PUB = "post_pub"
    POST_LIST = "post_list"
    POST_REC = "post_rec"
    POST_DEL = "post_del"
    POST_CLEAR = "post_clear"
    PUB_ALL = "pub_all"

    GROUPS = "groups"
    GRP_SET = "grp_set"

    TOGGLE_AUTO = "toggle_auto"
    TOGGLE_REC = "toggle_rec"

    SEC_CLOSE = "sec_close"
    SEC_ENABLE_ALL = "sec_enable_all"
    SEC_DISABLE_ALL = "sec_disable_all"
    SEC_NSFW = "sec_nsfw"
    SEC_DEL_PEN = "sec_del_pen"
    SEC_WARN = "sec_warn"
    SEC_VIOLATION_PENALTIES = "sec_violation_penalties"
    SEC_SET_VIOLATION_STRIKES = "sec_set_violation_strikes"
    SEC_SET_VIOLATION_DURATION = "sec_set_violation_duration"
    SEC_PENALTY_MUTE = "sec_penalty_mute"
    SEC_PENALTY_BAN = "sec_penalty_ban"
    SEC_PENALTY_RESTRICT = "sec_penalty_restrict"
    SEC_ANTIFLOOD_PENALTY = "sec_antiflood_penalty"
    SEC_NIGHT_ACTION = "sec_night_action"

    BAN_ADD = "ban_add"
    BAN_LIST = "ban_list"
    BAN_REM = "ban_rem"

    PENALTY = "penalty"
    PEN_BAN = "pen_ban"
    PEN_MUTE = "pen_mute"
    PEN_KICK = "pen_kick"
    PEN_WARN = "pen_warn"

    ADV_ACT = "adv_act"
    ACT_BAN = "act_ban"
    ACT_MUTE = "act_mute"
    ACT_WARN = "act_warn"
    ACT_KICK = "act_kick"
    ACT_RESTRICT = "act_restrict"
    ACT_PIN = "act_pin"
    ACT_LOG = "act_log"
    ACT_UNBAN = "act_unban"

    PANEL_LOCK = "panel_lock"
    PANEL_UNLOCK = "panel_unlock"
    PANEL_CLOSE = "panel_close"

    SUPPORT = "support"
    SUPPORT_TICKET = "support_ticket"

    TRIAL = "trial"
    SUBSCRIBE = "subscribe"
    PLANS = "plans"
    INVOICES = "invoices"

    DEVELOPER = "developer"

    REFERRAL = "referral"
    REF_CLAIM = "ref_claim"
    REF_LIST = "ref_list"

    REMINDER = "reminder"
    REM_TOGGLE_SUB = "rem_sub"
    REM_TOGGLE_DAILY = "rem_daily"
    REM_TOGGLE_WEEKLY = "rem_weekly"
    REM_SET_DAYS = "rem_days"
    REM_LANG = "rem_lang"

    TRANSLATION = "translation"
    TRANS_OFF = "trans_off"
    TRANS_SET = "trans_set"

    CONTESTS = "contests"
    CONTEST_JOIN = "contest_join"
    CONTEST_WINNERS = "contest_winners"
    DECLARE_WINNER_SEL = "declare_winner_sel"

    SCHED_MIN = "sched_min"
    SCHED_HOUR = "sched_hour"
    SCHED_DAY = "sched_day"
    SCHED_TIME = "sched_time"

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
    ADMIN_LIST_ADMINS = "admin_list_admins"
    ADMIN_RAM = "admin_ram"
    ADMIN_STATS = "admin_stats"
    ADMIN_METRICS = "admin_metrics"
    ADMIN_UPTIME = "admin_uptime"
    ADMIN_BACKUP = "admin_backup"
    ADMIN_RESTORE = "admin_restore"
    ADMIN_RESTORE_SEL = "admin_restore_sel"
    ADMIN_SEND_UPDATE = "admin_send_update"
    ADMIN_SET_UPDATE_CH = "admin_set_update_ch"
    ADMIN_SHOW_UPDATE = "admin_show_update"
    ADMIN_FORCE_SUB = "admin_force_sub"
    ADMIN_SET_FORCE = "admin_set_force"
    ADMIN_BROADCAST = "admin_broadcast"
    ADMIN_TICKETS = "admin_tickets"
    ADMIN_DEL_TICKETS = "admin_del_tickets"
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
    ADMIN_DEL_CONTEST = "admin_del_contest"
    ADMIN_EXPORT_REPLIES = "admin_export_replies"
    ADMIN_IMPORT_REPLIES = "admin_import_replies"
    ADMIN_REFRESH_CACHE = "admin_refresh_cache"
    ADMIN_IMPORT_GITHUB = "admin_import_github"
    ADMIN_INVOICES = "admin_invoices"
    ADMIN_PAYMENT_LOGS = "admin_payment_logs"
    ADMIN_GRANT_FREE = "admin_grant_free"

    AUTO_REPLY_MENU = "auto_reply_menu"
    AUTO_REPLY_TOGGLE = "auto_reply_toggle"
    AUTO_REPLY_ADMINS = "auto_reply_admins"
    AUTO_REPLY_RESET = "auto_reply_reset"
    AUTO_REPLY_STATS = "auto_reply_stats"
    AUTO_REPLY_ADD = "auto_reply_add"
    AUTO_REPLY_DEL = "auto_reply_del"
    AUTO_REPLY_LIST = "auto_reply_list"


# =====================================================================
# 9. مصنع الكيبوردات
# =====================================================================

class KeyboardFactory:
    _configs: Dict[str, Dict] = {}
    _default_lang: str = "ar"
    _config_path_template: str = str(Path(__file__).resolve().parent / "buttons_config_{lang}.json")

    _NO_CHAT_ID_BUTTONS = {
        "sec_close", "panel_close", "back", "main", "cancel",
        "help", "settings", "language", "check_sub",
        "toggle_auto", "toggle_rec", "plans", "subscribe",
        "support", "support_ticket", "developer", "trial",
        "contests", "contest_winners", "referral", "ref_claim",
        "ref_list", "reminder", "rem_sub", "rem_daily",
        "rem_weekly", "rem_days", "translation", "trans_off",
        "invoices", "groups", "admin", "panel_close",
        "pub_all", "post_add", "post_pub", "post_list", "post_rec",
        "sec_antiflood_settings", "sec_night_settings",
        "sec_penalty_durations", "sec_close", "admin_uptime"
    }

    _default_texts = {
        "back": "🔙 رجوع",
        "main": "🌿 الرئيسية",
        "add_group_button": "➕ أضف البوت لمجموعة",
        "security_button": "⚙️ أمان {name}",
        "ch_add": "➕ إضافة قناة",
        "sec_links": "🔗 الروابط",
        "sec_mentions": "👤 المعرفات",
        "sec_slow": "🐢 بطيء",
        "sec_flood": "🌊 الفيضان",
        "sec_video": "🎬 فيديو",
        "sec_audio": "🎵 موسيقى",
        "sec_anim": "🎞️ متحرك",
        "sec_service": "🛠️ خدمة",
        "sec_doc": "📄 ملفات",
        "sec_sticker": "🖼️ ملصقات",
        "sec_forward": "📨 مُعاد",
        "sec_poll": "📊 استطلاع",
        "sec_game": "🎮 ألعاب",
        "sec_voice": "🎤 صوتي",
        "sec_videonote": "🎥 فيديو نوت",
        "sec_banned_words": "🚫 كلمات محظورة",
        "sec_welcome": "🎯 ترحيب",
        "sec_goodbye": "👋 وداع",
        "sec_night": "🌙 وضع ليلي",
        "sec_approve_join": "✅ موافقة انضمام",
        "sec_reject_join": "❌ رفض انضمام",
        "sec_nsfw": "🔞 NSFW",
        "sec_maxlen": "📏 طول الرسالة",
        "sec_warn": "⚠️ تحذيرات",
        "sec_penalty": "🚫 العقوبات",
        "sec_del_pen": "🗑️ عقوبة الحذف",
        "sec_adv_act": "🛠️ إجراءات متقدمة",
        "sec_act_log": "📋 سجل المشرفين",
        "sec_auto_reply_menu": "🤖 الردود التلقائية",
        "sec_antiflood_settings": "🌊 إعدادات الفيضان",
        "sec_night_settings": "🌙 إعدادات الليل",
        "sec_penalty_durations": "⏱️ مدد العقوبات",
        "sec_violation_penalties": "🚨 المخالفات",
        "sec_enable_all": "✅ تفعيل الكل",
        "sec_disable_all": "❌ تعطيل الكل",
        "sec_close": "🔒 إغلاق",
        "auto_reply_toggle": "🔘 تفعيل/تعطيل",
        "auto_reply_admins": "👤 للمشرفين فقط",
        "auto_reply_add": "➕ إضافة",
        "auto_reply_del": "🗑️ حذف",
        "auto_reply_list": "📋 القائمة",
        "auto_reply_stats": "📊 إحصائيات",
        "auto_reply_reset": "🔄 إعادة تعيين",
        "act_ban": "🚫 حظر",
        "act_mute": "🔇 كتم",
        "act_warn": "⚠️ تحذير",
        "act_kick": "👢 طرد",
        "act_restrict": "🔒 تقييد",
        "act_unban": "🔓 فك حظر",
        "act_pin": "📌 تثبيت",
        "act_log": "📋 سجل",
        "pen_ban": "🚫 حظر",
        "pen_mute": "🔇 كتم",
        "pen_kick": "👢 طرد",
        "pen_warn": "⚠️ تحذير",
        "ban_add": "➕ إضافة كلمة",
        "ban_list": "📋 القائمة",
        "ban_rem": "🗑️ حذف كلمة",
    }

    @classmethod
    def _load_config_for_lang(cls, lang: str) -> Dict:
        if lang == 'off':
            lang = cls._default_lang

        if lang in cls._configs:
            return cls._configs[lang]

        file_path = cls._config_path_template.format(lang=lang)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                cls._configs[lang] = config
                logger.info(f"✅ تم تحميل buttons_config_{lang}.json: {len(config.get('texts', {}))} مفتاح")
                return config
        except FileNotFoundError:
            if lang != cls._default_lang:
                logger.warning(f"⚠️ ملف buttons_config_{lang}.json غير موجود، سيتم استخدام اللغة الافتراضية")
                return cls._load_config_for_lang(cls._default_lang)
            else:
                logger.warning("⚠️ buttons_config_ar.json غير موجود، سيتم استخدام إعدادات افتراضية")
                default_config = {
                    "texts": cls._default_texts,
                    "menus": {}
                }
                cls._configs[cls._default_lang] = default_config
                return default_config
        except Exception as e:
            logger.error(f"❌ خطأ في قراءة buttons_config_{lang}.json: {e}")
            if lang != cls._default_lang:
                return cls._load_config_for_lang(cls._default_lang)
            else:
                default_config = {
                    "texts": cls._default_texts,
                    "menus": {}
                }
                cls._configs[cls._default_lang] = default_config
                return default_config

    @classmethod
    def load_config(cls):
        cls._load_config_for_lang(cls._default_lang)

    @classmethod
    def get_config(cls, lang: str = None) -> Dict:
        if not lang:
            lang = cls._default_lang
        return cls._load_config_for_lang(lang)

    @classmethod
    def get_text(cls, key: str, lang: str = None) -> str:
        config = cls.get_config(lang)
        text = config.get("texts", {}).get(key)
        if text is not None:
            return text
        return cls._default_texts.get(key, key)

    @classmethod
    def get_menu(cls, menu_name: str, lang: str = None) -> List[List[str]]:
        config = cls.get_config(lang)
        return config.get("menus", {}).get(menu_name, {}).get("rows", [])

    @classmethod
    def build(cls, menu_name: str, chat_id: int = None, extra_data: Dict = None, lang: str = None) -> InlineKeyboardMarkup:
        rows = cls.get_menu(menu_name, lang)

        if not rows:
            default_menus = {
                "banned_words": [
                    ["ban_add", "ban_list"],
                    ["ban_rem"],
                    ["back"]
                ],
                "auto_reply_manage": [
                    ["auto_reply_toggle", "auto_reply_admins"],
                    ["auto_reply_add", "auto_reply_del"],
                    ["auto_reply_list", "auto_reply_stats"],
                    ["auto_reply_reset"],
                    ["back"]
                ],
                "auto_reply": [
                    ["auto_reply_toggle", "auto_reply_admins"],
                    ["auto_reply_add", "auto_reply_del"],
                    ["auto_reply_list", "auto_reply_stats"],
                    ["auto_reply_reset"],
                    ["back"]
                ],
                "security": [
                    ["sec_links", "sec_mentions"],
                    ["sec_slow", "sec_flood"],
                    ["sec_video", "sec_audio"],
                    ["sec_anim", "sec_service"],
                    ["sec_doc", "sec_sticker"],
                    ["sec_forward", "sec_poll"],
                    ["sec_game", "sec_voice"],
                    ["sec_videonote", "sec_banned_words"],
                    ["sec_welcome", "sec_goodbye"],
                    ["sec_night", "sec_approve_join"],
                    ["sec_reject_join", "sec_nsfw"],
                    ["sec_maxlen", "sec_warn"],
                    ["sec_penalty", "sec_del_pen"],
                    ["sec_adv_act", "sec_act_log"],
                    ["sec_auto_reply_menu"],
                    ["sec_antiflood_settings", "sec_night_settings"],
                    ["sec_penalty_durations"],
                    ["sec_violation_penalties"],
                    ["sec_enable_all", "sec_disable_all"],
                    ["sec_close"]
                ],
                "penalty": [
                    ["pen_ban", "pen_mute"],
                    ["pen_kick", "pen_warn"],
                    ["back"]
                ],
                "advanced_actions": [
                    ["act_ban", "act_mute"],
                    ["act_warn", "act_kick"],
                    ["act_restrict", "act_unban"],
                    ["act_pin"],
                    ["act_log"],
                    ["back"]
                ],
                "violation_penalties": [
                    ["sec_set_violation_strikes", "sec_set_violation_duration"],
                    ["back"]
                ]
            }
            if menu_name in default_menus:
                rows = default_menus[menu_name]
            else:
                rows = []

        keyboard = []
        for row in rows:
            btn_row = []
            for item in row:
                if item.endswith("_url"):
                    key = item.replace("_url", "")
                    text = cls.get_text(key, lang)
                    url = f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup"
                    btn_row.append(InlineKeyboardButton(text, url=url))
                else:
                    text = cls.get_text(item, lang)
                    callback = item
                    if chat_id and item not in cls._NO_CHAT_ID_BUTTONS:
                        callback = f"{item}:{chat_id}"
                    btn_row.append(InlineKeyboardButton(text, callback_data=callback))
            keyboard.append(btn_row)
        return InlineKeyboardMarkup(keyboard)

    @classmethod
    def _status_icon(cls, value: bool) -> str:
        return "✅" if value else "❌"

    @classmethod
    def _format_security_text(cls, settings: dict) -> str:
        st = cls._status_icon
        lines = [
            "🔐 إعدادات الأمان",
            "━━━━━━━━━━━━━━━━━━━━\n",
            "🛡️ الحماية",
            f"🔗 الروابط: {st(settings.get('delete_links', 0))}",
            f"👤 المعرفات: {st(settings.get('mentions', 0))}",
            f"🌊 الفيضان: {st(settings.get('antiflood_enabled', 0))}",
            f"🌙 الوضع الليلي: {st(settings.get('night_mode_enabled', 0))}",
            f"🔞 NSFW: {st(settings.get('nsfw_enabled', 0))}",
            f"⚠️ التحذيرات: {st(settings.get('warn_enabled', 0))}\n",
            "🎬 المحتوى",
            f"🎬 فيديو: {st(settings.get('delete_videos', 0))}",
            f"🎵 موسيقى: {st(settings.get('delete_audio', 0))}",
            f"🎞️ متحرك: {st(settings.get('delete_animation', 0))}",
            f"🎤 صوتي: {st(settings.get('delete_voice', 0))}",
            f"🖼️ ملصقات: {st(settings.get('delete_stickers', 0))}",
            f"📄 ملفات: {st(settings.get('delete_documents', 0))}",
            f"📨 مُعاد: {st(settings.get('delete_forwarded', 0))}",
            f"🛠️ خدمة: {st(settings.get('delete_service', 0))}\n",
            "👋 الترحيب",
            f"🎯 ترحيب: {st(settings.get('welcome_enabled', 0))}",
            f"👋 وداع: {st(settings.get('goodbye_enabled', 0))}",
            "━━━━━━━━━━━━━━━━━━━━"
        ]
        return "\n".join(lines)


# =====================================================================
# 10. كاش الكلمات المحظورة
# =====================================================================

_banned_words_cache: Dict[int, List[str]] = {}
_banned_words_cache_time: Dict[int, float] = {}
_BANNED_WORDS_CACHE_TTL = getattr(CONFIG, 'BANNED_WORDS_CACHE_TTL', 60)

async def get_banned_words_cached(chat_id: int) -> List[str]:
    if not CONFIG.ENABLE_BANNED_WORDS_CACHE:
        return await DB.get_banned_words(chat_id)

    now = time.time()
    if chat_id in _banned_words_cache and (now - _banned_words_cache_time.get(chat_id, 0)) < _BANNED_WORDS_CACHE_TTL:
        return _banned_words_cache[chat_id]

    words = await DB.get_banned_words(chat_id)
    _banned_words_cache[chat_id] = words
    _banned_words_cache_time[chat_id] = now
    return words


def invalidate_banned_words_cache(chat_id: int = None) -> None:
    if chat_id is not None:
        _banned_words_cache.pop(chat_id, None)
        _banned_words_cache_time.pop(chat_id, None)
    else:
        _banned_words_cache.clear()
        _banned_words_cache_time.clear()


async def get_min_publish_interval() -> int:
    val = await DB.get_setting('min_publish_interval', str(CONFIG.MIN_PUBLISH_INTERVAL))
    try:
        return max(1, int(val))
    except:
        return CONFIG.MIN_PUBLISH_INTERVAL


# =====================================================================
# 11. دوال الصلاحيات
# =====================================================================

_auth_cache = TTLCache(maxsize=CONFIG.AUTH_CACHE_SIZE, ttl=CONFIG.AUTH_CACHE_TTL)

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
    except:
        pass

    if not authorized:
        row = await DB.fetchone(
            "SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?",
            (chat_id, user_id)
        )
        if row:
            authorized = True
        else:
            row2 = await DB.fetchone(
                "SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?",
                (chat_id, user_id)
            )
            if row2:
                authorized = True
            else:
                if await DB.is_anonymous_admin(chat_id, user_id):
                    authorized = True

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
        can_pin = getattr(me, 'can_pin_messages', False)
        if not can_delete or not can_ban:
            return {'can_act': False, 'reason': 'صلاحيات ناقصة'}
        return {'can_act': True, 'reason': '', 'can_pin': can_pin}
    except Exception as e:
        return {'can_act': False, 'reason': str(e)[:50]}


# =====================================================================
# 12. إرسال آمن (مع معالجة TimedOut)
# =====================================================================

async def safe_send(bot, chat_id: int, text: str, reply_markup=None, parse_mode: str = None, **kwargs):
    if not text:
        return
    await RATE_LIMITER.acquire()
    text = TextUtils.sanitize(text, max_len=4096)
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            **kwargs
        )
    except TimedOut:
        logger.warning("⚠️ Timed out، محاولة إعادة الإرسال...")
        try:
            await asyncio.sleep(1)
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                **kwargs
            )
        except Exception as e2:
            logger.error(f"❌ فشل الإرسال بعد المحاولة الثانية: {e2}")
            return None
    except BadRequest as e:
        error_msg = str(e).lower()
        if "can't parse entities" in error_msg or "parse" in error_msg:
            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', text)
            if len(plain) > 4096:
                plain = plain[:4093] + "..."
            try:
                return await bot.send_message(
                    chat_id=chat_id,
                    text=plain,
                    reply_markup=reply_markup,
                    parse_mode=None,
                    **kwargs
                )
            except Exception as e2:
                logger.error(f"❌ فشل الإرسال النهائي: {e2}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ فشل الإرسال: {e}")
        return None


def get_ram_usage() -> dict:
    if psutil is None:
        return {'total': 0, 'used': 0, 'percent': 0}
    try:
        mem = psutil.virtual_memory()
        return {'total': round(mem.total / (1024**3), 1), 'used': round(mem.used / (1024**3), 1), 'percent': mem.percent}
    except Exception as e:
        logger.error(f"❌ فشل جلب إحصائيات الرام: {e}")
        return {'total': 0, 'used': 0, 'percent': 0}


# =====================================================================
# 13. نظام العقوبات
# =====================================================================

class PenaltyStrategy(ABC):
    @abstractmethod
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        pass


class BanPenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        if user_id == bot.id:
            return False, "لا يمكن حظر البوت"
        duration = kwargs.get('duration', 0)
        until_date = TimeUtils.utc_now() + timedelta(seconds=duration) if duration > 0 else None
        try:
            await bot.ban_chat_member(chat_id, user_id, until_date=until_date)
            return True, "✅ تم الحظر"
        except Exception as e:
            return False, str(e)[:100]


class MutePenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        if user_id == bot.id:
            return False, "لا يمكن كتم البوت"
        duration = kwargs.get('duration', 60)
        until_date = TimeUtils.utc_now() + timedelta(seconds=duration) if duration > 0 else None
        try:
            await bot.restrict_chat_member(
                chat_id, user_id,
                ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            return True, "✅ تم الكتم"
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
        try:
            w = await DB.add_user_warning(user_id, chat_id)
            return True, f"⚠️ تحذير {w}"
        except Exception as e:
            return False, str(e)[:100]


class RestrictPenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        if user_id == bot.id:
            return False, "لا يمكن تقييد البوت"
        duration = kwargs.get('duration', 0)
        until_date = TimeUtils.utc_now() + timedelta(seconds=duration) if duration > 0 else None
        try:
            await bot.restrict_chat_member(
                chat_id, user_id,
                ChatPermissions(can_send_messages=True, can_send_media_messages=False),
                until_date=until_date
            )
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


class PenaltyFactory:
    @staticmethod
    def get_strategy(penalty_type: str):
        strategies = {
            'ban': BanPenalty(),
            'mute': MutePenalty(),
            'kick': KickPenalty(),
            'warn': WarnPenalty(),
            'restrict': RestrictPenalty(),
            'unban': UnbanPenalty()
        }
        return strategies.get(penalty_type)


async def apply_penalty(bot, chat_id: int, user_id: int, penalty: str, duration: int = 60, reason: str = "", moderator: int = None) -> Tuple[bool, str]:
    if user_id == CONFIG.PRIMARY_OWNER_ID:
        return False, "لا يمكن معاملة المالك"
    if user_id == bot.id:
        return False, "لا يمكن معاملة البوت"
    if await is_authorized_in_group(bot, chat_id, user_id):
        return False, "لا يمكن معاملة مشرف"
    perms = await check_bot_permissions(bot, chat_id)
    if not perms['can_act']:
        return False, "الصلاحيات غير كافية"
    strategy = PenaltyFactory.get_strategy(penalty)
    if not strategy:
        return False, "نوع عقوبة غير معروف"
    success, msg = await strategy.apply(bot, chat_id, user_id, duration=duration)
    if success:
        if penalty in DB.VALID_PENALTY_TYPES:
            await DB.add_penalty(
                user_id=user_id,
                chat_id=chat_id,
                penalty_type=penalty,
                duration=duration,
                reason=reason,
                issued_by=moderator
            )
        if moderator:
            await DB.add_admin_log(chat_id, moderator, penalty, user_id, reason)
    return success, msg


# =====================================================================
# 14. الردود التلقائية
# =====================================================================

_usage_updates: Dict[Tuple[int, str], int] = {}
_USAGE_FLUSH_LIMIT = 50
_USAGE_FLUSH_INTERVAL = 60
_usage_lock = asyncio.Lock()


async def _increment_usage_async(chat_id: int, keyword: str):
    async with _usage_lock:
        key = (chat_id, keyword.lower())
        _usage_updates[key] = _usage_updates.get(key, 0) + 1
        should_flush = len(_usage_updates) >= _USAGE_FLUSH_LIMIT
    if should_flush:
        await _flush_usage_updates()


async def _flush_usage_updates():
    async with _usage_lock:
        if not _usage_updates:
            return
        data = list(_usage_updates.items())
        _usage_updates.clear()
    try:
        for (chat_id, keyword), count in data:
            await DB.execute(
                "UPDATE auto_replies SET usage_count = usage_count + ? WHERE chat_id=? AND keyword=?",
                (count, chat_id, keyword)
            )
    except Exception as e:
        logger.error(f"❌ فشل تحديث usage_count: {e}")
        async with _usage_lock:
            for key, count in data:
                _usage_updates[key] = _usage_updates.get(key, 0) + count


async def export_auto_replies(chat_id: int, file_path: str = None) -> int:
    rows = await DB.fetchall(
        "SELECT keyword, reply FROM auto_replies WHERE chat_id=? AND is_active=1",
        (chat_id,)
    )
    if not rows:
        return 0
    data = [dict(row) for row in rows]
    if file_path is None:
        file_path = f"auto_replies_{chat_id}.json"

    def _write():
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    await asyncio.to_thread(_write)
    return len(data)


async def import_auto_replies(chat_id: int, file_path_or_data: Union[str, List[Dict]], overwrite: bool = False) -> int:
    try:
        if isinstance(file_path_or_data, str):
            with open(file_path_or_data, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = file_path_or_data

        if not isinstance(data, list):
            return 0

        count = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            keyword = item.get('keyword', '').strip().lower()
            reply = item.get('reply', '').strip()
            if not keyword or not reply:
                continue
            if overwrite:
                await DB.execute("DELETE FROM auto_replies WHERE chat_id=? AND keyword=?", (chat_id, keyword))
            await DB.add_auto_reply(chat_id, keyword, reply)
            count += 1
        _auto_reply_cache.invalidate()
        return count
    except Exception as e:
        logger.error(f"❌ Import error: {e}")
        return 0


async def fetch_json_from_url(url: str) -> Optional[Union[list, dict]]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                if isinstance(data, (list, dict)):
                    return data
        return None
    except Exception as e:
        logger.error(f"❌ Fetch JSON error: {e}")
        return None


# =====================================================================
# 15. الردود من ملف
# =====================================================================

def load_replies_from_file() -> dict:
    try:
        import replies
        importlib.reload(replies)
        replies_data = replies.REPLIES
        if replies_data:
            logger.info(f"✅ تم تحميل الردود: {len(replies_data)} رد تلقائي")
        else:
            logger.warning("⚠️ ملف replies.py فارغ")
        return replies_data
    except ImportError:
        logger.info("ℹ️ لا يوجد replies.py")
        return {}
    except Exception as e:
        logger.error(f"❌ خطأ في تحميل replies.py: {e}")
        return {}


_REPLIES_FROM_FILE = load_replies_from_file()


def get_reply_from_file(keyword: str) -> Optional[str]:
    if not _REPLIES_FROM_FILE or not keyword:
        return None
    keyword = keyword.lower().strip()

    lines = keyword.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line in _REPLIES_FROM_FILE:
            replies = _REPLIES_FROM_FILE[line]
            return random.choice(replies) if replies else None

        words = line.split()
        for word in words:
            if word in _REPLIES_FROM_FILE:
                replies = _REPLIES_FROM_FILE[word]
                return random.choice(replies) if replies else None

    for key, replies in _REPLIES_FROM_FILE.items():
        if not isinstance(replies, list) or not replies:
            continue
        if re.search(rf'\b{re.escape(key)}\b', keyword):
            return random.choice(replies)

    return None


def reload_replies_from_file() -> dict:
    global _REPLIES_FROM_FILE
    _REPLIES_FROM_FILE = load_replies_from_file()
    return _REPLIES_FROM_FILE


# =====================================================================
# 16. المهام الخلفية
# =====================================================================

class BackgroundTasks:
    @staticmethod
    async def _publish_post(bot, channel_id: int, post: dict) -> bool:
        try:
            text = post.get('text', '')
            media_type = post.get('media_type')
            media_file_id = post.get('media_file_id')
            caption = text[:1024] if text else None

            if media_type == 'photo' and media_file_id:
                await bot.send_photo(channel_id, media_file_id, caption=caption)
            elif media_type == 'video' and media_file_id:
                await bot.send_video(channel_id, media_file_id, caption=caption)
            elif media_type == 'document' and media_file_id:
                await bot.send_document(channel_id, media_file_id, caption=caption)
            elif media_type == 'audio' and media_file_id:
                await bot.send_audio(channel_id, media_file_id, caption=caption)
            elif media_type == 'voice' and media_file_id:
                await bot.send_voice(channel_id, media_file_id, caption=caption)
            elif media_type == 'animation' and media_file_id:
                await bot.send_animation(channel_id, media_file_id, caption=caption)
            elif media_type == 'sticker' and media_file_id:
                await bot.send_sticker(channel_id, media_file_id)
            elif media_type == 'video_note' and media_file_id:
                await bot.send_video_note(channel_id, media_file_id)
            else:
                await bot.send_message(channel_id, text[:4096] if text else ".")
            return True
        except Exception as e:
            logger.error(f"❌ Publish error: {e}")
            return False

    @staticmethod
    async def auto_publish(bot) -> None:
        await asyncio.sleep(10)
        max_channels = getattr(CONFIG, 'MAX_CHANNELS_PER_CYCLE', 20)
        min_interval_minutes = await get_min_publish_interval()
        sleep_seconds = min_interval_minutes * 60

        while True:
            try:
                channels = await DB.get_channels_to_publish(max_channels)
                if not channels:
                    await asyncio.sleep(60)
                    continue

                tasks = []
                for ch in channels:
                    task = asyncio.create_task(
                        BackgroundTasks._publish_channel_cycle(
                            bot, ch, sleep_seconds
                        )
                    )
                    tasks.append(task)

                await asyncio.gather(*tasks, return_exceptions=True)

            except Exception as e:
                logger.error(f"❌ Auto publish: {e}")
                await asyncio.sleep(60)

    @staticmethod
    async def _publish_channel_cycle(bot, ch, sleep_seconds):
        while True:
            try:
                has_sub = await DB.has_active_subscription(ch['user_id'])
                if not has_sub:
                    logger.info(f"⏭️ تخطي القناة {ch['id']} لانتهاء الاشتراك")
                    await asyncio.sleep(300)
                    continue

                post = await DB.get_next_post(ch['id'])
                if not post:
                    auto_recycle = await DB.get_auto_recycle_status(ch['user_id'])
                    if auto_recycle:
                        await DB.reset_posts(ch['user_id'], ch['id'])
                        post = await DB.get_next_post(ch['id'])
                        if not post:
                            await asyncio.sleep(60)
                            continue
                    else:
                        await asyncio.sleep(60)
                        continue

                success = await BackgroundTasks._publish_post(bot, ch['channel_id'], post)
                if success:
                    await DB.mark_post_published(post['id'])
                    await DB.update_last_publish(ch['id'])
                    await DB.update_next_publish(ch['id'])
                    logger.info(f"✅ قناة {ch['id']} نشرت. انتظار {sleep_seconds//60} دقيقة...")
                    await asyncio.sleep(sleep_seconds)
                else:
                    await DB.increment_post_fail(post['id'])
                    await asyncio.sleep(5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ خطأ في قناة {ch.get('id', 'غير معروفة')}: {e}")
                await asyncio.sleep(60)

    @staticmethod
    async def auto_backup() -> None:
        await asyncio.sleep(60)
        try:
            await BackgroundTasks._do_backup()
        except Exception as e:
            logger.error(f"❌ Initial backup failed: {e}")

        while True:
            await asyncio.sleep(86400)
            try:
                await BackgroundTasks._do_backup()
            except Exception as e:
                logger.error(f"❌ Backup error: {e}")

    @staticmethod
    async def _do_backup() -> None:
        if await DB.get_auto_backup():
            PATHS.BACKUPS.mkdir(parents=True, exist_ok=True)
            backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"

            def _backup():
                import sqlite3 as sqlite3_sync
                source = sqlite3_sync.connect(str(PATHS.DB))
                dest = sqlite3_sync.connect(str(backup_file))
                with dest:
                    source.backup(dest)
                dest.close()
                source.close()

            await asyncio.to_thread(_backup)
            await DB.set_setting('last_backup', TimeUtils.sql_iso())
            backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
            for old in backups[CONFIG.MAX_BACKUPS:]:
                old.unlink()

    @staticmethod
    async def reminders(bot) -> None:
        while True:
            await asyncio.sleep(3600)
            try:
                users = await DB.get_users_for_reminder()
                for u in users:
                    try:
                        try:
                            days = int(u['days_left'])
                        except (ValueError, TypeError):
                            continue
                        lang = u.get('language', 'ar')
                        text = await get_text(lang, 'reminder_subscription_expires', days=days)
                        if text == 'reminder_subscription_expires':
                            text = f"⚠️ اشتراكك سينتهي بعد {days} يوم"
                        await safe_send(bot, u['user_id'], text)
                        await asyncio.sleep(0.1)
                    except:
                        pass
            except Exception as e:
                logger.error(f"❌ Reminders: {e}")

    @staticmethod
    async def heartbeat(bot) -> None:
        while True:
            await asyncio.sleep(CONFIG.HEARTBEAT_INTERVAL)
            try:
                ram = get_ram_usage()
                msg = f"💓 **Heartbeat**\n\n🕐 {TimeUtils.mecca_iso()}\n💾 RAM: {ram['percent']}%"
                log_channel = await DB.get_log_channel()
                try:
                    if log_channel:
                        await safe_send(bot, log_channel, msg)
                    else:
                        await safe_send(bot, CONFIG.PRIMARY_OWNER_ID, msg)
                except Exception as e:
                    logger.error(f"❌ فشل إرسال heartbeat: {e}")
            except Exception as e:
                logger.error(f"❌ Heartbeat error: {e}")

    @staticmethod
    async def flush_usage_periodically() -> None:
        while True:
            await asyncio.sleep(_USAGE_FLUSH_INTERVAL)
            await _flush_usage_updates()

    @staticmethod
    async def expire_subscriptions() -> None:
        while True:
            await asyncio.sleep(3600)
            try:
                await DB.expire_expired_subscriptions()
            except Exception as e:
                logger.error(f"❌ Expire subs: {e}")

    @staticmethod
    async def sync_admins_periodically(bot) -> None:
        await asyncio.sleep(60)
        while True:
            try:
                groups = await DB.fetchall("SELECT chat_id FROM bot_groups WHERE banned=0")
                for group in groups:
                    chat_id = group['chat_id'] if isinstance(group, dict) else group[0]
                    try:
                        admins = await bot.get_chat_administrators(chat_id)
                        admin_ids = [a.user.id for a in admins if a.user and not a.user.is_bot]
                        await DB.sync_group_admins(chat_id, admin_ids)
                    except:
                        pass
            except Exception as e:
                logger.error(f"❌ Sync admins: {e}")
            await asyncio.sleep(3600)

    @staticmethod
    async def expire_penalties_periodically() -> None:
        await asyncio.sleep(60)
        while True:
            await asyncio.sleep(60)
            try:
                await DB.expire_penalties()
            except Exception as e:
                logger.error(f"❌ Expire penalties: {e}")


# =====================================================================
# 17. خادم الويب
# =====================================================================

_webhook_app = None

async def setup_webhook(app, port: int):
    global _webhook_app
    _webhook_app = app

    web_app = web.Application()
    web_app.router.add_get('/health', lambda r: web.Response(text="OK"))
    web_app.router.add_get('/', lambda r: web.Response(text="🌿 Relax Manager"))
    web_app.router.add_post(f"/{CONFIG.TOKEN}", webhook_handler)
    web_app.router.add_get('/{tail:.*}', lambda r: web.Response(text="OK", status=200))
    web_app.router.add_post('/{tail:.*}', lambda r: web.Response(text="OK", status=200))

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"✅ Webhook on port {port}")
    return runner


async def webhook_handler(request):
    global _webhook_app
    if _webhook_app is None or not hasattr(_webhook_app, 'bot'):
        logger.error("❌ Webhook app not initialized")
        return web.Response(status=503, text="Service Unavailable")
    try:
        data = await request.json()
        await _webhook_app.process_update(Update.de_json(data, _webhook_app.bot))
        return web.Response(status=200, text="OK")
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return web.Response(status=500, text="ERROR")


# =====================================================================
# 18. معالج الأخطاء
# =====================================================================

class ErrorHandler:
    @staticmethod
    async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            if update:
                logger.error(f"❌ خطأ في التحديث {update.update_id}: {context.error}", exc_info=True)
            else:
                logger.error(f"❌ خطأ: {context.error}", exc_info=True)
        except Exception:
            pass
