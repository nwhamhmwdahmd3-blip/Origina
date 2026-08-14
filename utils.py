#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
utils.py - الأدوات المساعدة للبوت
==================================
تحتوي على: TimeUtils, TextUtils, RateLimiter, Metrics,
TranslationManager, KeyboardFactory, StateManager,
دوال مساعدة أخرى
"""

import asyncio
import os
import re
import json
import time
import html
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple, Any
from enum import Enum, auto
from collections import OrderedDict, deque
from telegram import Update
from telegram.ext import ContextTypes
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest
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

    async def acquire(self):
        async with self.semaphore:
            async with self._lock:
                now = time.time()
                while self._last_calls and now - self._last_calls[0] > 1:
                    self._last_calls.popleft()
                if len(self._last_calls) >= 30:
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
        calls_in_last_hour = sum(1 for t, _, _ in self.api_calls if now - t < 3600)
        errors_in_last_hour = sum(1 for t, _, _ in self.errors if now - t < 3600)
        uptime = now - self.start_time
        return {
            'api_calls_last_hour': calls_in_last_hour,
            'errors_last_hour': errors_in_last_hour,
            'uptime_seconds': int(uptime),
            'messages_processed': self.messages_processed,
            'total_api_calls': len(self.api_calls),
            'total_errors': len(self.errors)
        }

    def increment_messages(self):
        self.messages_processed += 1

METRICS = MetricsCollector()

# =====================================================================
# 5. كاش الردود التلقائية
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

_auto_reply_cache = AutoReplyCache(maxsize=300)

# =====================================================================
# 6. الترجمات
# =====================================================================

class TranslationManager:
    _translations: Dict[str, Dict] = {}
    _locales_dir: str = "locales"
    _default_lang: str = "ar"

    @classmethod
    def load_translation(cls, lang: str) -> Dict:
        if lang in cls._translations:
            return cls._translations[lang]
        file_path = Path(cls._locales_dir) / f"{lang}.json"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                cls._translations[lang] = data
                return data
        except:
            if lang != cls._default_lang:
                return cls.load_translation(cls._default_lang)
            return {}

    @classmethod
    def get_text(cls, lang: str, key: str, **kwargs) -> str:
        translations = cls.load_translation(lang)
        template = translations.get(key)
        if template is None and lang != cls._default_lang:
            translations = cls.load_translation(cls._default_lang)
            template = translations.get(key)
        if template is None:
            template = key
        try:
            return template.format(**kwargs)
        except KeyError:
            return template

    @classmethod
    def get_available_languages(cls) -> Dict[str, str]:
        languages = {
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
        available = {}
        for code, name in languages.items():
            if (Path(cls._locales_dir) / f"{code}.json").exists():
                available[code] = name
        if not available:
            available["ar"] = languages["ar"]
        return available

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
    WAIT_REPLY_BUTTONS = auto()
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
    SUPPORT_MODE = auto()

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

# =====================================================================
# 8. تعريفات الأزرار
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
    CH_DEL = "ch_del:"
    CH_SEL = "ch_sel:"
    CH_STATS = "ch_stats:"

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

    SUPPORT = "support"
    SUPPORT_TICKET = "support_ticket"

    TRIAL = "trial"
    SUBSCRIBE = "subscribe"
    BUY_SUB = "buy_sub:"
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
    REM_SET_LANG = "rem_lang"
    REM_LANG = "rem_lang:"

    TRANSLATION = "translation"
    TRANS_OFF = "trans_off"
    TRANS_SET = "trans_set:"

    CONTESTS = "contests"
    CONTEST_JOIN = "contest_join:"
    CONTEST_WINNERS = "contest_winners"
    DECLARE_WINNER_SEL = "declare_winner_sel:"

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
    ADMIN_EXPORT_REPLIES = "admin_export_replies"
    ADMIN_IMPORT_REPLIES = "admin_import_replies"
    ADMIN_REFRESH_CACHE = "admin_refresh_cache"
    ADMIN_IMPORT_GITHUB = "admin_import_github"

    AUTO_REPLY_MENU = "auto_reply_menu:"
    AUTO_REPLY_TOGGLE = "auto_reply_toggle:"
    AUTO_REPLY_ADMINS = "auto_reply_admins:"
    AUTO_REPLY_RESET = "auto_reply_reset:"
    AUTO_REPLY_CONFIRM_RESET = "auto_reply_confirm_reset:"
    AUTO_REPLY_STATS = "auto_reply_stats:"
    AUTO_REPLY_ADD = "auto_reply_add:"
    AUTO_REPLY_DEL = "auto_reply_del:"
    AUTO_REPLY_LIST = "auto_reply_list:"

# =====================================================================
# 9. مصنع الكيبوردات
# =====================================================================

class KeyboardFactory:
    _config: Dict = None
    _config_path: str = "buttons_config.json"

    @classmethod
    def load_config(cls):
        if cls._config is None:
            try:
                with open(cls._config_path, "r", encoding="utf-8") as f:
                    cls._config = json.load(f)
            except:
                cls._config = {"texts": {}, "menus": {}}
        return cls._config

    @classmethod
    def get_text(cls, key: str) -> str:
        config = cls.load_config()
        return config.get("texts", {}).get(key, key)

    @classmethod
    def get_menu(cls, menu_name: str) -> List[List[str]]:
        config = cls.load_config()
        menu = config.get("menus", {}).get(menu_name, {})
        return menu.get("rows", [])

    @classmethod
    def build(cls, menu_name: str, chat_id: int = None, extra_data: Dict = None) -> InlineKeyboardMarkup:
        rows = cls.get_menu(menu_name)
        keyboard = []
        for row in rows:
            btn_row = []
            for item in row:
                if item.endswith("_url"):
                    key = item.replace("_url", "")
                    text = cls.get_text(key)
                    url = f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup"
                    if extra_data and "url" in extra_data:
                        url = extra_data["url"]
                    btn_row.append(InlineKeyboardButton(text, url=url))
                else:
                    text = cls.get_text(item)
                    callback = item
                    if chat_id and ":" in item:
                        callback = f"{item}{chat_id}"
                    elif chat_id and item in ["sec_close", "panel_close", "back", "main"]:
                        callback = item
                    elif chat_id:
                        callback = f"{item}:{chat_id}"
                    btn_row.append(InlineKeyboardButton(text, callback_data=callback))
            keyboard.append(btn_row)
        return InlineKeyboardMarkup(keyboard)

    @classmethod
    def _status_icon(cls, value: bool) -> str:
        return "✅" if value else "❌"

    @classmethod
    async def _format_security_text(cls, settings: dict) -> str:
        st = cls._status_icon
        lines = [
            "🔐 **إعدادات الأمان**",
            "━━━━━━━━━━━━━━━━━━━━\n",
            "🛡️ **الحماية**",
            f"🔗 الروابط: {st(settings.get('delete_links', False))}",
            f"👤 المعرفات: {st(settings.get('mentions', False))}",
            f"🌊 الفيضان: {st(settings.get('antiflood_enabled', False))}\n",
            "🎬 **المحتوى**",
            f"🎬 فيديو: {st(settings.get('delete_videos', False))}",
            f"🎵 موسيقى: {st(settings.get('delete_audio', False))}",
            f"🎞️ متحرك: {st(settings.get('delete_animation', False))}",
            f"🎤 صوتي: {st(settings.get('delete_voice', False))}",
            f"🎥 فيديو نوت: {st(settings.get('delete_video_note', False))}",
            f"🖼️ ملصقات: {st(settings.get('delete_stickers', False))}",
            f"📄 ملفات: {st(settings.get('delete_documents', False))}",
            f"📨 مُعاد: {st(settings.get('delete_forwarded', False))}",
            f"📊 استطلاع: {st(settings.get('delete_polls', False))}",
            f"🎮 ألعاب: {st(settings.get('delete_games', False))}",
            f"🛠️ خدمة: {st(settings.get('delete_service', False))}\n",
            "👋 **الترحيب**",
            f"🎯 ترحيب: {st(settings.get('welcome_enabled', False))}",
            f"👋 وداع: {st(settings.get('goodbye_enabled', False))}\n",
            "⚙️ **القيود**",
            f"⏱️ بطيء: {st(settings.get('slow_mode', False))} ({settings.get('slow_mode_seconds', 5)}ث)",
            f"📏 طول: {settings.get('max_message_length', 0) or 'غير محدود'}",
            f"🌙 ليلي: {st(settings.get('night_mode_enabled', False))}",
            f"⚠️ تحذيرات: {settings.get('max_warnings', 3)}\n",
            "⚖️ **العقوبات**",
            f"🗑️ حذف: {settings.get('delete_penalty', 'none')}",
            f"⚖️ أساسية: {settings.get('auto_penalty', 'none')}",
            "━━━━━━━━━━━━━━━━━━━━"
        ]
        return "\n".join(lines)

# =====================================================================
# 10. دوال مساعدة أخرى
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
        else:
            row = await DB.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
            if row:
                authorized = True
            else:
                row2 = await DB.fetchone("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, user_id))
                if row2:
                    authorized = True
                else:
                    linked = await DB.fetchone("SELECT 1 FROM user_groups_link WHERE user_id=? AND chat_id=?", (user_id, chat_id))
                    if linked:
                        authorized = True
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
    except Exception as e:
        return {'can_act': False, 'reason': f'خطأ في التحقق: {str(e)[:50]}'}

async def safe_send(bot, chat_id: int, text: str, reply_markup=None, **kwargs):
    if not text:
        return
    await RATE_LIMITER.acquire()
    start_time = time.time()
    try:
        escaped = TextUtils.escape_markdown_v2(text)
        if len(escaped) > 4096:
            escaped = escaped[:4093] + "..."
        result = await bot.send_message(
            chat_id=chat_id,
            text=escaped,
            parse_mode='MarkdownV2',
            reply_markup=reply_markup,
            **kwargs
        )
        METRICS.record_api_call('send_message', time.time() - start_time)
        return result
    except:
        try:
            html_text = html.escape(text)
            if len(html_text) > 4096:
                html_text = html_text[:4093] + "..."
            result = await bot.send_message(
                chat_id=chat_id,
                text=html_text,
                parse_mode='HTML',
                reply_markup=reply_markup,
                **kwargs
            )
            METRICS.record_api_call('send_message_html', time.time() - start_time)
            return result
        except:
            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', text)
            if len(plain) > 4096:
                plain = plain[:4093] + "..."
            result = await bot.send_message(
                chat_id=chat_id,
                text=plain,
                reply_markup=reply_markup,
                **kwargs
            )
            METRICS.record_api_call('send_message_plain', time.time() - start_time)
            return result

def get_ram_usage() -> dict:
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {'total': round(mem.total / (1024 ** 3), 1), 'used': round(mem.used / (1024 ** 3), 1),
                'percent': mem.percent}
    except:
        return {'total': 0, 'used': 0, 'percent': 0}

# =====================================================================
# 11. نظام العقوبات
# =====================================================================

from abc import ABC, abstractmethod

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
        try:
            row = await DB.fetchone("SELECT warnings FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            w = (row[0] if row else 0) + 1
            await DB.execute("INSERT OR REPLACE INTO user_warnings (user_id, chat_id, warnings) VALUES (?,?,?)", (user_id, chat_id, w))
            return True, f"⚠️ تحذير {w}"
        except Exception as e:
            return False, str(e)[:100]

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

async def apply_penalty(bot, chat_id: int, user_id: int, penalty: str, duration: int = 0, reason: str = "", moderator: int = None) -> Tuple[bool, str]:
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
    return await strategy.apply(bot, chat_id, user_id, duration=duration)

# =====================================================================
# 12. دوال الردود التلقائية والاستيراد
# =====================================================================

_usage_updates: Dict[Tuple[int, str], int] = {}
_USAGE_FLUSH_LIMIT = 50
_USAGE_FLUSH_INTERVAL = 60

async def _increment_usage_async(chat_id: int, keyword: str):
    global _usage_updates
    key = (chat_id, keyword.lower())
    _usage_updates[key] = _usage_updates.get(key, 0) + 1
    if len(_usage_updates) >= _USAGE_FLUSH_LIMIT:
        await _flush_usage_updates()

async def _flush_usage_updates():
    global _usage_updates
    if not _usage_updates:
        return
    data = list(_usage_updates.items())
    _usage_updates.clear()
    async with DB._get_connection() as conn:
        for (chat_id, keyword), count in data:
            await conn.execute("UPDATE auto_replies SET usage_count = usage_count + ? WHERE chat_id=? AND keyword=?", (count, chat_id, keyword))
        await conn.commit()

async def export_auto_replies(chat_id: int, file_path: str = None) -> int:
    rows = await DB.fetchall("SELECT keyword, reply, reply_type, reply_media_id, reply_buttons FROM auto_replies WHERE chat_id=? AND is_active=1", (chat_id,))
    if not rows:
        return 0
    data = [dict(row) for row in rows]
    if file_path is None:
        file_path = f"auto_replies_{chat_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(data)

async def import_auto_replies(chat_id: int, file_path: str, overwrite: bool = False) -> int:
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
            await DB.execute("DELETE FROM auto_replies WHERE chat_id=? AND keyword=?", (chat_id, keyword))
        await DB.add_auto_reply(chat_id, keyword, reply, item.get('reply_type', 'text'), item.get('reply_media_id'), item.get('reply_buttons'))
        count += 1
    _auto_reply_cache.invalidate()
    return count

async def fetch_json_from_url(url: str) -> Optional[list]:
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        return data
                return None
    except:
        return None

# =====================================================================
# 13. المهام الخلفية
# =====================================================================

class BackgroundTasks:
    @staticmethod
    async def auto_publish(bot) -> None:
        await asyncio.sleep(10)
        while True:
            try:
                channels = await DB.get_channels_to_publish(CONFIG.MAX_CHANNELS_PER_CYCLE)
                if not channels:
                    await asyncio.sleep(60)
                    continue
                for ch in channels:
                    post = await DB.get_next_post(ch['id'])
                    if not post:
                        continue
                    try:
                        if post['media_type'] == 'photo' and post['media_file_id']:
                            await bot.send_photo(ch['channel_id'], post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
                        elif post['media_type'] == 'video' and post['media_file_id']:
                            await bot.send_video(ch['channel_id'], post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
                        else:
                            await bot.send_message(ch['channel_id'], post['text'][:4096] if post['text'] else ".")
                        await DB.mark_post_published(post['id'])
                        await DB.update_last_publish(ch['id'])
                        await DB.update_next_publish(ch['id'])
                    except Exception as e:
                        await DB.increment_post_fail(post['id'])
                await asyncio.sleep(max(60, await DB.get_publish_interval()))
            except Exception as e:
                logger.error(f"Auto publish error: {e}")
                await asyncio.sleep(60)

    @staticmethod
    async def auto_backup() -> None:
        while True:
            await asyncio.sleep(86400)
            try:
                if await DB.get_auto_backup():
                    backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                    shutil.copy2(PATHS.DB, backup_file)
                    await DB.set_setting('last_backup', TimeUtils.utc_iso())
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
                users = await DB.get_users_for_reminder()
                for u in users:
                    try:
                        lang = u.get('language', 'ar')
                        days = int(u['days_left'])
                        text = await get_text(lang, 'reminder_subscription_expires', days=days)
                        await bot.send_message(u['user_id'], text)
                    except:
                        pass
            except Exception as e:
                logger.error(f"Reminders error: {e}")

    @staticmethod
    async def heartbeat(bot) -> None:
        while True:
            await asyncio.sleep(CONFIG.HEARTBEAT_INTERVAL)
            try:
                log_channel = await DB.get_log_channel()
                ram = get_ram_usage()
                msg = await get_text('ar', 'heartbeat_status', time=TimeUtils.mecca_iso(), ram=ram['percent'])
                if log_channel:
                    await bot.send_message(log_channel, msg)
                else:
                    await bot.send_message(CONFIG.PRIMARY_OWNER_ID, msg)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    @staticmethod
    async def flush_sentiment_periodically() -> None:
        while True:
            await asyncio.sleep(60)
            # يتم التعامل مع تحليل المشاعر في handle_group

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
                logger.error(f"Expire subscriptions error: {e}")

# =====================================================================
# 14. خادم الويب
# =====================================================================

async def setup_webhook(app, port: int):
    from aiohttp import web
    web_app = web.Application()
    web_app.router.add_get('/health', lambda r: web.Response(text="OK"))
    web_app.router.add_post(f"/{CONFIG.TOKEN}", webhook_handler)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner

async def webhook_handler(request):
    try:
        data = await request.json()
        from telegram import Update
        from handlers import app
        await app.process_update(Update.de_json(data, app.bot))
        return web.Response(status=200, text="OK")
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500, text="ERROR")

# =====================================================================
# 15. معالج الأخطاء
# =====================================================================

class ErrorHandler:
    @staticmethod
    async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            error = context.error
            logger.error(f"Error: {error}", exc_info=True)
            if isinstance(error, BadRequest):
                if update and update.effective_user:
                    await safe_send(context.bot, update.effective_user.id, f"⚠️ {str(error)[:200]}")
        except Exception as e:
            logger.error(f"Error in error handler: {e}")

