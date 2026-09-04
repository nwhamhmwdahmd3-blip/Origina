#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
utils.py - الأدوات المساعدة للبوت RelaxMgr
=========================================
نسخة كاملة ومصححة ومحسّنة.

الإصلاحات المهمة:
- إصلاح RateLimiter بحيث لا يحتجز القفل أثناء sleep.
- حماية callback_data من تجاوز حد Telegram بدل قصّه وتغيير معناه.
- تحسين safe_send ودعم الوسائط بشكل صحيح.
- تمرير parse_mode للوسائط التي تدعمه.
- عدم تمرير reply_markup للـ sticker/video_note.
- منع أخطاء ChatPermissions بين إصدارات python-telegram-bot.
- تحسين معالجة TimedOut وBadRequest.
- إصلاح RestrictPenalty.
- تحسين كاش الكلمات المحظورة.
- منع مشاكل أقفال asyncio عند تنظيف الكاش.
- تحسين TranslationManager.
- تحسين استيراد وتصدير الردود.
- حماية fetch_json_from_url.
- تحسين النشر التلقائي والتعامل مع الأخطاء.
- حماية النسخ الاحتياطي وإغلاق اتصالات SQLite دائمًا.
- تحسين Webhook.
- الحفاظ على جميع الواجهات والدوال والثوابت الموجودة.
"""

import asyncio
import re
import json
import time
import html
import logging
import random
import importlib
import sqlite3
import inspect
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple, Any, Union, Set
from enum import Enum, auto
from collections import OrderedDict, deque, defaultdict
from abc import ABC, abstractmethod
from functools import lru_cache
from contextlib import suppress

try:
    import psutil
except ImportError:
    psutil = None

import aiohttp
import aiohttp.web as web

from telegram import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatPermissions,
    Update,
)
from telegram.error import BadRequest, TimedOut
from telegram.ext import ContextTypes
from cachetools import TTLCache

from config import CONFIG, PATHS
from database import DB


logger = logging.getLogger(__name__)


# =====================================================================
# 0. إعداد مجلد اللغات
# =====================================================================

_locales_dir = Path(__file__).resolve().parent / "locales"

try:
    _locales_dir.mkdir(parents=True, exist_ok=True)
except Exception as e:
    logger.warning("تعذر إنشاء مجلد locales: %s", e)

try:
    if hasattr(PATHS, "LOCALES"):
        LOCALES_DIR = str(PATHS.LOCALES)
    else:
        LOCALES_DIR = str(_locales_dir)
        setattr(PATHS, "LOCALES", _locales_dir)
except Exception:
    LOCALES_DIR = str(_locales_dir)
    with suppress(Exception):
        setattr(PATHS, "LOCALES", _locales_dir)


# =====================================================================
# 1. أدوات الوقت
# =====================================================================

class TimeUtils:
    """أدوات الوقت والتاريخ."""

    __slots__ = ()

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
        return TimeUtils.utc_now().strftime("%Y-%m-%d %H:%M:%S")

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

        value = str(date_str).strip()

        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            pass

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

        return None

    @staticmethod
    def format_duration(seconds: int) -> str:
        try:
            seconds = max(0, int(seconds))
        except (ValueError, TypeError):
            seconds = 0

        if seconds < 60:
            return f"{seconds} ثانية"
        if seconds < 3600:
            return f"{seconds // 60} دقيقة"
        if seconds < 86400:
            return f"{seconds // 3600} ساعة"

        days = seconds // 86400
        return f"{days} يوم"


# =====================================================================
# 2. أدوات النصوص
# =====================================================================

class TextUtils:
    """أدوات معالجة النصوص."""

    __slots__ = ()

    @staticmethod
    def contains_link(text: Optional[str]) -> bool:
        if not text:
            return False

        return bool(
            re.search(
                r"(?:https?://|www\.|t\.me/|telegram\.me/)\S+",
                str(text),
                re.IGNORECASE,
            )
        )

    @staticmethod
    def contains_mention(text: Optional[str]) -> bool:
        return bool(re.search(r"@\w+", str(text))) if text else False

    @staticmethod
    def sanitize(text: Optional[str], max_len: int = 4096) -> str:
        if not text:
            return ""

        try:
            max_len = max(1, int(max_len))
        except (ValueError, TypeError):
            max_len = 4096

        text = str(text)
        text = re.sub(r"[\u200b\u200c\u200d\u2060\uFEFF]", "", text)
        return text[:max_len]

    @staticmethod
    def escape_markdown_v2(text: Optional[str]) -> str:
        if not text:
            return ""

        text = str(text)

        # Telegram MarkdownV2 special characters.
        special_chars = r"_*[]()~`>#+-=|{}.!\\"

        return re.sub(
            rf"([{re.escape(special_chars)}])",
            r"\\\1",
            text,
        )

    @staticmethod
    def escape_html(text: Optional[str]) -> str:
        if not text:
            return ""
        return html.escape(str(text))

    @staticmethod
    def truncate(text: Optional[str], max_len: int = 200) -> str:
        if not text:
            return ""

        try:
            max_len = max(1, int(max_len))
        except (ValueError, TypeError):
            max_len = 200

        text = str(text)

        if len(text) <= max_len:
            return text

        if max_len <= 3:
            return text[:max_len]

        return text[:max_len - 3] + "..."

    @staticmethod
    def extract_links(text: Optional[str]) -> List[str]:
        if not text:
            return []

        pattern = r"(?:https?://|www\.|t\.me/|telegram\.me/)\S+"
        return re.findall(pattern, str(text), re.IGNORECASE)

    @staticmethod
    def remove_links(text: Optional[str]) -> str:
        if not text:
            return ""

        pattern = r"(?:https?://|www\.|t\.me/|telegram\.me/)\S+"
        return re.sub(pattern, "", str(text)).strip()


# =====================================================================
# 3. Rate Limiter
# =====================================================================

class RateLimiter:
    """
    محدد معدل الإرسال.

    acquire() لا يحتجز semaphore أثناء الانتظار.
    semaphore متاح للتوافق مع الكود القديم، بينما تحديد المعدل
    يتم بصورة مستقلة.
    """

    __slots__ = (
        "semaphore",
        "_last_calls",
        "_lock",
        "max_per_second",
    )

    def __init__(
        self,
        max_concurrent: int = 10,
        max_per_second: int = 30,
    ):
        try:
            max_concurrent = max(1, int(max_concurrent))
        except (ValueError, TypeError):
            max_concurrent = 10

        try:
            max_per_second = max(1, int(max_per_second))
        except (ValueError, TypeError):
            max_per_second = 30

        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._last_calls = deque()
        self._lock = asyncio.Lock()
        self.max_per_second = max_per_second

    async def acquire(self, *args, **kwargs):
        """
        انتظار حتى يسمح معدل الإرسال.

        لا يتم إبقاء lock أثناء sleep.
        """
        while True:
            wait_time = 0.0

            async with self._lock:
                now = time.monotonic()

                while (
                    self._last_calls
                    and now - self._last_calls[0] >= 1.0
                ):
                    self._last_calls.popleft()

                if len(self._last_calls) < self.max_per_second:
                    self._last_calls.append(now)
                    return

                wait_time = max(
                    0.001,
                    1.0 - (now - self._last_calls[0]),
                )

            await asyncio.sleep(wait_time)

    async def run(self, func, *args, **kwargs):
        """
        تشغيل عملية مع تحديد المعدل والتزامن.
        """
        await self.acquire()

        async with self.semaphore:
            return await func(*args, **kwargs)


RATE_LIMITER = RateLimiter(
    max_concurrent=15,
    max_per_second=30,
)


# =====================================================================
# 4. مقاييس الأداء
# =====================================================================

class MetricsCollector:
    """جمع إحصائيات الأداء."""

    __slots__ = (
        "api_calls",
        "errors",
        "messages_processed",
        "start_time",
        "_lock",
    )

    def __init__(self):
        self.api_calls = deque(maxlen=1000)
        self.errors = deque(maxlen=1000)
        self.messages_processed = 0
        self.start_time = time.time()
        self._lock = asyncio.Lock()

    def record_api_call(self, method: str, duration: float):
        self.api_calls.append(
            (
                time.time(),
                str(method),
                max(0.0, float(duration)),
            )
        )

    def record_error(self, error_type: str, context: str = ""):
        self.errors.append(
            (
                time.time(),
                str(error_type),
                str(context),
            )
        )

    def get_stats(self) -> dict:
        now = time.time()

        return {
            "api_calls_last_hour": sum(
                1 for t, _, _ in self.api_calls
                if now - t < 3600
            ),
            "errors_last_hour": sum(
                1 for t, _, _ in self.errors
                if now - t < 3600
            ),
            "uptime_seconds": int(
                max(0, now - self.start_time)
            ),
            "messages_processed": self.messages_processed,
            "total_api_calls": len(self.api_calls),
            "total_errors": len(self.errors),
        }

    async def increment_messages(self):
        async with self._lock:
            self.messages_processed += 1


METRICS = MetricsCollector()


# =====================================================================
# 5. كاش الردود التلقائية
# =====================================================================

class AutoReplyCache:
    """كاش للردود التلقائية مع TTL."""

    __slots__ = (
        "cache",
        "maxsize",
        "ttl",
        "_lock",
    )

    def __init__(
        self,
        maxsize: int = 300,
        ttl: int = 300,
    ):
        self.cache = OrderedDict()

        try:
            self.maxsize = max(1, int(maxsize))
        except (ValueError, TypeError):
            self.maxsize = 300

        try:
            self.ttl = max(1, int(ttl))
        except (ValueError, TypeError):
            self.ttl = 300

        self._lock = asyncio.Lock()

    async def get(self, key: str):
        async with self._lock:
            item = self.cache.get(key)

            if item is None:
                return None

            value, timestamp = item

            if time.time() - timestamp >= self.ttl:
                self.cache.pop(key, None)
                return None

            self.cache.move_to_end(key)
            return value

    async def set(self, key: str, value: dict):
        async with self._lock:
            self.cache[key] = (
                value,
                time.time(),
            )

            self.cache.move_to_end(key)

            while len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)

    async def invalidate(self, key: str = None):
        async with self._lock:
            if key is None:
                self.cache.clear()
            else:
                self.cache.pop(key, None)

    async def clear(self):
        async with self._lock:
            self.cache.clear()


_auto_reply_cache = AutoReplyCache(
    maxsize=300,
    ttl=300,
)


# =====================================================================
# 5.1 كاشات الإعدادات
# =====================================================================

_security_settings_cache: Dict[int, dict] = {}
_security_settings_time: Dict[int, float] = {}

_auto_reply_settings_cache: Dict[int, dict] = {}
_auto_reply_settings_time: Dict[int, float] = {}

_security_cache_locks: Dict[int, asyncio.Lock] = {}
_auto_reply_cache_locks: Dict[int, asyncio.Lock] = {}


def _get_dict_lock(
    locks: Dict[int, asyncio.Lock],
    key: int,
) -> asyncio.Lock:
    """
    الحصول على lock ثابت بدون استخدام setdefault
    لتقليل احتمال إنشاء أكثر من Lock في ظروف التزامن.
    """
    lock = locks.get(key)

    if lock is None:
        lock = asyncio.Lock()
        locks[key] = lock

    return lock


async def get_security_settings_cached(chat_id: int) -> dict:
    """جلب إعدادات الأمان مع كاش."""
    lock = _get_dict_lock(
        _security_cache_locks,
        chat_id,
    )

    async with lock:
        now = time.time()

        if (
            chat_id in _security_settings_cache
            and (
                now
                - _security_settings_time.get(chat_id, 0)
            ) < 60
        ):
            return _security_settings_cache[chat_id]

        try:
            settings = await DB.get_security_settings(chat_id)
        except Exception:
            logger.exception(
                "❌ فشل جلب إعدادات الأمان chat_id=%s",
                chat_id,
            )
            settings = {}

        if not isinstance(settings, dict):
            settings = {}

        _security_settings_cache[chat_id] = settings
        _security_settings_time[chat_id] = time.time()

        return settings


def invalidate_security_cache(
    chat_id: int = None,
) -> None:
    """إبطال كاش إعدادات الأمان."""
    if chat_id is None:
        _security_settings_cache.clear()
        _security_settings_time.clear()

        # لا نحذف locks الموجودة أثناء استخدامها.
        for key, lock in list(_security_cache_locks.items()):
            if not lock.locked():
                _security_cache_locks.pop(key, None)

        return

    _security_settings_cache.pop(chat_id, None)
    _security_settings_time.pop(chat_id, None)

    lock = _security_cache_locks.get(chat_id)

    if lock is not None and not lock.locked():
        _security_cache_locks.pop(chat_id, None)


async def get_auto_reply_settings_cached(
    chat_id: int,
) -> dict:
    """جلب إعدادات الردود التلقائية مع كاش."""
    lock = _get_dict_lock(
        _auto_reply_cache_locks,
        chat_id,
    )

    async with lock:
        now = time.time()

        if (
            chat_id in _auto_reply_settings_cache
            and (
                now
                - _auto_reply_settings_time.get(chat_id, 0)
            ) < 60
        ):
            return _auto_reply_settings_cache[chat_id]

        try:
            settings = await DB.get_auto_reply_settings(chat_id)
        except Exception:
            logger.exception(
                "❌ فشل جلب إعدادات الردود chat_id=%s",
                chat_id,
            )
            settings = {}

        if not isinstance(settings, dict):
            settings = {}

        _auto_reply_settings_cache[chat_id] = settings
        _auto_reply_settings_time[chat_id] = time.time()

        return settings


def invalidate_auto_reply_cache(
    chat_id: int = None,
) -> None:
    """إبطال كاش إعدادات الردود التلقائية."""
    if chat_id is None:
        _auto_reply_settings_cache.clear()
        _auto_reply_settings_time.clear()

        for key, lock in list(_auto_reply_cache_locks.items()):
            if not lock.locked():
                _auto_reply_cache_locks.pop(key, None)

        return

    _auto_reply_settings_cache.pop(chat_id, None)
    _auto_reply_settings_time.pop(chat_id, None)

    lock = _auto_reply_cache_locks.get(chat_id)

    if lock is not None and not lock.locked():
        _auto_reply_cache_locks.pop(chat_id, None)


# =====================================================================
# 6. الترجمات
# =====================================================================

class TranslationManager:
    """إدارة الترجمات متعددة اللغات."""

    _translations: Dict[str, Dict] = {}
    _locales_dir: str = LOCALES_DIR
    _default_lang: str = "ar"

    _fallback_data = {
        "welcome": "مرحباً بك في البوت 🎉",
        "help": "للمساعدة، استخدم /help",
        "settings": "الإعدادات",
        "back": "🔙 رجوع",
        "main": "🌿 الرئيسية",
        "cancel": "❌ إلغاء",
    }

    @staticmethod
    def _normalize_lang(lang: Optional[str]) -> str:
        if not lang:
            return TranslationManager._default_lang

        lang = str(lang).strip().lower()

        if lang == "off":
            return TranslationManager._default_lang

        if not re.fullmatch(r"[a-z]{2,8}(?:[-_][a-zA-Z]{2,8})?", lang):
            return TranslationManager._default_lang

        return lang.replace("_", "-")

    @staticmethod
    @lru_cache(maxsize=32)
    def _load_translation_cached(lang: str) -> Dict:
        lang = TranslationManager._normalize_lang(lang)

        if lang in TranslationManager._translations:
            return TranslationManager._translations[lang]

        file_path = (
            Path(TranslationManager._locales_dir)
            / f"{lang}.json"
        )

        try:
            with open(
                file_path,
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)

            if not isinstance(data, dict):
                data = {}

            TranslationManager._translations[lang] = data
            return data

        except FileNotFoundError:
            if lang != TranslationManager._default_lang:
                return TranslationManager._load_translation_cached(
                    TranslationManager._default_lang
                )

            TranslationManager._translations[
                lang
            ] = dict(TranslationManager._fallback_data)

            return TranslationManager._translations[lang]

        except json.JSONDecodeError as e:
            logger.error(
                "❌ JSON ترجمة غير صالح %s: %s",
                file_path,
                e,
            )

        except Exception as e:
            logger.error(
                "❌ خطأ في تحميل الترجمة %s: %s",
                lang,
                e,
            )

        if lang != TranslationManager._default_lang:
            return TranslationManager._load_translation_cached(
                TranslationManager._default_lang
            )

        return dict(TranslationManager._fallback_data)

    @classmethod
    def load_translation(
        cls,
        lang: str,
    ) -> Dict:
        return cls._load_translation_cached(
            cls._normalize_lang(lang)
        )

    @classmethod
    def get_text(
        cls,
        lang: str,
        key: str,
        **kwargs,
    ) -> str:
        lang = cls._normalize_lang(lang)

        translations = cls.load_translation(lang)
        template = translations.get(key)

        if template is None and lang != cls._default_lang:
            template = cls.load_translation(
                cls._default_lang
            ).get(key)

        if template is None:
            template = key

        if not isinstance(template, str):
            template = str(template)

        try:
            return template.format_map(kwargs)
        except KeyError:
            safe_kwargs = defaultdict(str, kwargs)

            try:
                return template.format_map(safe_kwargs)
            except Exception:
                return template
        except Exception:
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
            "ko": "한국어 🇰🇷",
            "fa": "فارسی 🇮🇷",
            "ur": "اردو 🇵🇰",
            "nl": "Nederlands 🇳🇱",
            "pl": "Polski 🇵🇱",
            "hi": "हिन्दी 🇮🇳",
        }

    @classmethod
    def reload_translations(cls) -> None:
        cls._translations.clear()
        cls._load_translation_cached.cache_clear()


async def get_text(
    lang: str,
    key: str,
    **kwargs,
) -> str:
    return TranslationManager.get_text(
        lang,
        key,
        **kwargs,
    )


# =====================================================================
# 7. إدارة الحالات
# =====================================================================

class UserState(Enum):
    """حالات المستخدم."""

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
    WAIT_RESTORE = auto()

    WAIT_AD_TEXT = auto()
    WAIT_AD_CHANNEL_ID = auto()
    WAIT_AD_PRICE = auto()
    WAIT_AD_INTERNAL_ID = auto()
    WAIT_AD_OPERATION = auto()


class StateManager:
    """إدارة حالات المستخدم مع مهلة زمنية."""

    __slots__ = ()

    _states: Dict[int, UserState] = {}
    _timestamps: Dict[int, float] = {}

    _timeout = 300

    @classmethod
    def get(
        cls,
        user_id: int,
    ) -> UserState:
        timestamp = cls._timestamps.get(user_id)

        if timestamp is not None:
            if time.time() - timestamp >= cls._timeout:
                cls.clear(user_id)

        return cls._states.get(
            user_id,
            UserState.NONE,
        )

    @classmethod
    def set(
        cls,
        user_id: int,
        state: UserState,
    ) -> None:
        if not isinstance(state, UserState):
            state = UserState.NONE

        cls._states[user_id] = state
        cls._timestamps[user_id] = time.time()

    @classmethod
    def clear(cls, user_id: int) -> None:
        cls._states.pop(user_id, None)
        cls._timestamps.pop(user_id, None)

    @classmethod
    def is_expired(
        cls,
        user_id: int,
        timeout: int = None,
    ) -> bool:
        timestamp = cls._timestamps.get(user_id)

        if timestamp is None:
            return False

        ttl = (
            cls._timeout
            if timeout is None
            else max(1, int(timeout))
        )

        return time.time() - timestamp >= ttl

    @classmethod
    def get_all_states(
        cls,
    ) -> Dict[int, UserState]:
        now = time.time()

        expired = [
            uid
            for uid, timestamp in list(
                cls._timestamps.items()
            )
            if now - timestamp >= cls._timeout
        ]

        for uid in expired:
            cls.clear(uid)

        return cls._states.copy()

    @classmethod
    def cleanup_expired(cls) -> int:
        now = time.time()

        expired = [
            uid
            for uid, timestamp in list(
                cls._timestamps.items()
            )
            if now - timestamp >= cls._timeout
        ]

        for uid in expired:
            cls.clear(uid)

        return len(expired)


# =====================================================================
# 8. تعريفات الأزرار
# =====================================================================

class CB:
    """ثوابت بيانات الأزرار."""

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

    AD_CH_MENU = "ad_ch_menu"
    AD_CH_ADD = "ad_ch_add"
    AD_CH_LIST = "ad_ch_list"
    AD_CH_SET_PRICE = "ad_ch_set_price"
    AD_CH_ENABLE = "ad_ch_enable"
    AD_CH_DISABLE = "ad_ch_disable"
    AD_CH_DELETE = "ad_ch_delete"
    AD_CH_CANCEL = "ad_ch_cancel"
    AD_CH_SELECT = "ad_ch_select"


# =====================================================================
# 9. مصنع الكيبوردات
# =====================================================================

class KeyboardFactory:
    """مصنع لوحات المفاتيح مع كاش."""

    _configs: Dict[str, Dict] = {}
    _configs_time: Dict[str, float] = {}

    _default_lang = "ar"

    _config_path_template = str(
        Path(__file__).resolve().parent
        / "buttons_config_{lang}.json"
    )

    _CACHE_TTL = 300

    _lock = asyncio.Lock()

    _NO_CHAT_ID_BUTTONS = {
        "sec_close",
        "panel_close",
        "back",
        "main",
        "cancel",
        "help",
        "settings",
        "language",
        "check_sub",
        "toggle_auto",
        "toggle_rec",
        "plans",
        "subscribe",
        "support",
        "support_ticket",
        "developer",
        "trial",
        "contests",
        "contest_winners",
        "referral",
        "ref_claim",
        "ref_list",
        "reminder",
        "rem_sub",
        "rem_daily",
        "rem_weekly",
        "rem_days",
        "translation",
        "trans_off",
        "invoices",
        "groups",
        "admin",
        "pub_all",
        "post_add",
        "post_pub",
        "post_list",
        "post_rec",
        "admin_uptime",
        "admin_export_replies",
        "admin_import_replies",
        "admin_refresh_cache",
        "admin_invoices",
        "admin_payment_logs",
        "admin_grant_free",
        "admin_replies",
        "admin_banned_words",
        "admin_create_contest",
        "admin_declare_winner",
        "admin_del_contest",
        "admin_backup",
        "admin_restore",
        "admin_stats",
        "admin_ram",
        "admin_metrics",
        "admin_channels",
        "admin_groups",
        "admin_users",
        "admin_banned",
        "admin_unban_all",
        "admin_banned_ch",
        "admin_activate_ch",
        "admin_banned_gr",
        "admin_unban_gr",
        "admin_add_admin",
        "admin_rem_admin",
        "admin_list_admins",
        "admin_send_update",
        "admin_set_update_ch",
        "admin_show_update",
        "admin_force_sub",
        "admin_set_force",
        "admin_broadcast",
        "admin_tickets",
        "admin_del_tickets",
        "admin_log_ch",
        "admin_set_log_ch",
        "admin_add_reply",
        "admin_list_replies",
        "admin_del_reply",
        "admin_add_banned",
        "admin_list_banned",
        "admin_rem_banned",
        "admin_import_github",
        "ad_ch_menu",
        "ad_ch_add",
        "ad_ch_list",
        "ad_ch_set_price",
        "ad_ch_enable",
        "ad_ch_disable",
        "ad_ch_delete",
        "ad_ch_cancel",
        "ad_ch_select",
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
        "sec_service": "🗑️ رسائل الخدمة",
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

        "ad_add": "➕ إضافة قناة إعلانات",
        "ad_list": "📋 قنواتي الإعلانية",
        "ad_set_price": "💰 تحديد سعر",
        "ad_enable": "✅ تفعيل",
        "ad_disable": "❌ تعطيل",
        "ad_delete": "🗑️ حذف",
        "ad_cancel": "❌ إلغاء",
        "ad_back_to_menu": "🔙 رجوع لقائمة الإعلانات",

        "ad_menu_title":
            "📢 إدارة قنوات الإعلانات\n"
            "اختر العملية المطلوبة:",

        "ad_private_only":
            "⚠️ هذه الأزرار تعمل في المحادثة الخاصة فقط.",

        "ad_cancelled": "✅ تم الإلغاء",

        "ad_no_channels":
            "📭 لا توجد قنوات إعلانات مضافة.",

        "ad_my_channels":
            "📢 قنوات الإعلانات الخاصة بك:\n\n",

        "ad_active": "✅ مفعلة",
        "ad_inactive": "❌ معطلة",
        "ad_invalid_id": "❌ معرف غير صالح",
        "ad_not_owner": "❌ هذه القناة ليست ملكك",

        "ad_enter_price":
            "💰 أرسل السعر (بالنجوم):",

        "ad_enabled": "✅ تم التفعيل",
        "ad_disabled": "✅ تم التعطيل",
        "ad_deleted": "✅ تم الحذف",
        "ad_failed": "❌ فشل",

        "ad_enter_channel":
            "📝 أرسل معرف القناة أو @username:",

        "ad_invalid_channel_id":
            "❌ معرف قناة غير صالح. حاول مرة أخرى أو أرسل 'إلغاء'.",

        "ad_bot_not_member":
            "❌ البوت ليس عضواً في القناة. أضف البوت أولاً.",

        "ad_channel_exists":
            "❌ هذه القناة مضافة بالفعل.",

        "ad_added_success":
            "✅ تم حفظ قناة الإعلانات بنجاح!\n"
            "📛 الاسم: {name}\n"
            "🆔 المعرف الرقمي: {id}\n"
            "🆔 المعرف الداخلي: {db_id}",

        "ad_add_failed": "❌ فشل إضافة القناة.",
        "ad_requires_subscription": "❌ يتطلب اشتراكاً نشطاً",

        "ad_max_reached":
            "❌ وصلت للحد الأقصى ({limit}).",

        "ad_select_channel_price":
            "💰 اختر القناة لتحديد سعرها:",

        "ad_select_channel_enable":
            "✅ اختر القناة لتفعيلها:",

        "ad_select_channel_disable":
            "❌ اختر القناة لتعطيلها:",

        "ad_select_channel_delete":
            "🗑️ اختر القناة لحذفها:",

        "ad_invalid_price":
            "❌ سعر غير صالح (يجب أن يكون عدداً صحيحاً موجباً).",

        "ad_price_set":
            "✅ تم تحديد السعر: {price} ⭐",

        "ad_error": "❌ حدث خطأ، أعد المحاولة.",

        "ad_added_success_cmd":
            "✅ تمت إضافة القناة، المعرف الداخلي: {db_id}",

        "ad_add_usage":
            "📝 استخدم: /add_ad_channel <معرف_القناة أو @username> [اسم_القناة]",

        "ad_set_price_usage":
            "📝 استخدم: /set_ad_price <channel_db_id> <السعر>",

        "ad_invalid_values": "❌ قيم غير صالحة",

        "ad_enable_usage":
            "📝 استخدم: /enable_ad_channel <channel_db_id>",

        "ad_disable_usage":
            "📝 استخدم: /disable_ad_channel <channel_db_id>",

        "ad_remove_usage":
            "📝 استخدم: /remove_ad_channel <channel_db_id>",

        "unknown": "⚠️ غير معروف",

        "ad_ch_menu": "📢 إدارة الإعلانات",
        "ad_ch_add": "➕ إضافة قناة",
        "ad_ch_list": "📋 قائمة القنوات",
        "ad_ch_set_price": "💰 تحديد السعر",
        "ad_ch_enable": "✅ تفعيل",
        "ad_ch_disable": "❌ تعطيل",
        "ad_ch_delete": "🗑️ حذف",
        "ad_ch_cancel": "❌ إلغاء",
        "ad_ch_select": "🔘 اختيار",

        "admin_panel": "👑 لوحة الأدمن",
        "admin_users": "👥 المستخدمين",
        "admin_stats": "📊 إحصائيات",
        "admin_backup": "💾 نسخ احتياطي",
        "admin_restore": "📂 استعادة",
        "admin_ram": "🖥️ الرام",
        "admin_metrics": "📊 مقاييس",
        "admin_uptime": "⏳ مدة التشغيل",
        "admin_broadcast": "📨 بث",
        "admin_invoices": "🧾 الفواتير",
        "admin_tickets": "🎫 التذاكر",
        "admin_payment_logs": "💳 سجلات الدفع",
        "admin_grant_free": "🎁 منح اشتراك مجاني",
        "admin_add_admin": "➕ إضافة مشرف",
        "admin_rem_admin": "🗑️ إزالة مشرف",
        "admin_list_admins": "📋 قائمة المشرفين",
        "admin_log_ch": "📋 قناة السجلات",
        "admin_set_log_ch": "⚙️ تعيين قناة السجلات",
        "admin_force_sub": "🔒 الاشتراك الإجباري",
        "admin_set_force": "⚙️ تعيين الاشتراك الإجباري",
        "admin_send_update": "📢 إرسال تحديث",
        "admin_set_update_ch": "⚙️ تعيين قناة التحديثات",
        "admin_show_update": "📢 عرض قناة التحديثات",
        "admin_replies": "💬 الردود العامة",
        "admin_add_reply": "➕ إضافة رد عام",
        "admin_list_replies": "📋 قائمة الردود العامة",
        "admin_del_reply": "🗑️ حذف رد عام",
        "admin_export_replies": "📤 تصدير الردود",
        "admin_import_replies": "📥 استيراد ردود",
        "admin_import_github": "📥 استيراد من GitHub",
        "admin_banned_words": "🚫 كلمات محظورة عامة",
        "admin_add_banned": "➕ إضافة كلمة محظورة",
        "admin_list_banned": "📋 قائمة الكلمات المحظورة",
        "admin_rem_banned": "🗑️ حذف كلمة محظورة",
        "admin_create_contest": "🏆 إنشاء مسابقة",
        "admin_declare_winner": "🏆 إعلان فائز",
        "admin_del_contest": "🗑️ حذف مسابقة",
        "admin_refresh_cache": "🔄 تحديث الكاش",
        "admin_banned": "⛔ المحظورين",
        "admin_unban_all": "✅ فك حظر الكل",
        "admin_channels": "📡 القنوات",
        "admin_banned_ch": "🚫 القنوات المحظورة",
        "admin_activate_ch": "✅ تفعيل الكل",
        "admin_groups": "👥 المجموعات",
        "admin_banned_gr": "🚫 المجموعات المحظورة",
        "admin_unban_gr": "🔓 إلغاء حظر الكل",
        "admin_restore_sel": "📂 اختيار نسخة",
    }

    @classmethod
    async def _load_config_for_lang(
        cls,
        lang: str,
    ) -> Dict:
        lang = TranslationManager._normalize_lang(lang)

        async with cls._lock:
            now = time.time()

            if (
                lang in cls._configs
                and (
                    now
                    - cls._configs_time.get(lang, 0)
                ) < cls._CACHE_TTL
            ):
                return cls._configs[lang]

            file_path = cls._config_path_template.format(
                lang=lang
            )

            try:
                with open(
                    file_path,
                    "r",
                    encoding="utf-8",
                ) as f:
                    config = json.load(f)

                if not isinstance(config, dict):
                    config = {}

                if not isinstance(
                    config.get("texts"),
                    dict,
                ):
                    config["texts"] = {}

                if not isinstance(
                    config.get("menus"),
                    dict,
                ):
                    config["menus"] = {}

                cls._configs[lang] = config
                cls._configs_time[lang] = time.time()

                return config

            except FileNotFoundError:
                if lang != cls._default_lang:
                    logger.warning(
                        "⚠️ ملف buttons_config_%s.json غير موجود",
                        lang,
                    )

                    # لا نستدعي الدالة نفسها داخل نفس lock.
                    default_config = await cls._load_config_for_lang_unlocked(
                        cls._default_lang
                    )

                    return default_config

                logger.warning(
                    "⚠️ buttons_config_ar.json غير موجود"
                )

                config = {
                    "texts": dict(cls._default_texts),
                    "menus": {},
                }

                cls._configs[lang] = config
                cls._configs_time[lang] = time.time()

                return config

            except json.JSONDecodeError as e:
                logger.error(
                    "❌ JSON buttons_config_%s غير صالح: %s",
                    lang,
                    e,
                )

            except Exception as e:
                logger.error(
                    "❌ خطأ في قراءة buttons_config_%s.json: %s",
                    lang,
                    e,
                )

            if lang != cls._default_lang:
                return await cls._load_config_for_lang_unlocked(
                    cls._default_lang
                )

            config = {
                "texts": dict(cls._default_texts),
                "menus": {},
            }

            cls._configs[lang] = config
            cls._configs_time[lang] = time.time()

            return config

    @classmethod
    async def _load_config_for_lang_unlocked(
        cls,
        lang: str,
    ) -> Dict:
        lang = TranslationManager._normalize_lang(lang)

        if (
            lang in cls._configs
            and (
                time.time()
                - cls._configs_time.get(lang, 0)
            ) < cls._CACHE_TTL
        ):
            return cls._configs[lang]

        file_path = cls._config_path_template.format(
            lang=lang
        )

        try:
            with open(
                file_path,
                "r",
                encoding="utf-8",
            ) as f:
                config = json.load(f)

            if not isinstance(config, dict):
                config = {}

            if not isinstance(
                config.get("texts"),
                dict,
            ):
                config["texts"] = {}

            if not isinstance(
                config.get("menus"),
                dict,
            ):
                config["menus"] = {}

            cls._configs[lang] = config
            cls._configs_time[lang] = time.time()

            return config

        except Exception:
            config = {
                "texts": dict(cls._default_texts),
                "menus": {},
            }

            cls._configs[lang] = config
            cls._configs_time[lang] = time.time()

            return config

    @classmethod
    async def load_config(cls):
        await cls._load_config_for_lang(
            cls._default_lang
        )

    @classmethod
    async def get_config(
        cls,
        lang: str = None,
    ) -> Dict:
        return await cls._load_config_for_lang(
            lang or cls._default_lang
        )

    @classmethod
    async def get_text(
        cls,
        key: str,
        lang: str = None,
    ) -> str:
        config = await cls.get_config(lang)

        text = config.get(
            "texts",
            {},
        ).get(key)

        if text is not None:
            return str(text)

        return cls._default_texts.get(
            key,
            key,
        )

    @classmethod
    def get_text_sync(
        cls,
        key: str,
        lang: str = None,
    ) -> str:
        lang = TranslationManager._normalize_lang(lang)

        if lang in cls._configs:
            config = cls._configs[lang]

            text = config.get(
                "texts",
                {},
            ).get(key)

            if text is not None:
                return str(text)

        try:
            config = cls._load_config_for_lang_sync(
                lang
            )

            cls._configs[lang] = config
            cls._configs_time[lang] = time.time()

        except Exception:
            config = {
                "texts": dict(cls._default_texts),
                "menus": {},
            }

        return str(
            config.get(
                "texts",
                {},
            ).get(
                key,
                cls._default_texts.get(
                    key,
                    key,
                ),
            )
        )

    @classmethod
    def _load_config_for_lang_sync(
        cls,
        lang: str,
    ) -> Dict:
        lang = TranslationManager._normalize_lang(lang)

        file_path = cls._config_path_template.format(
            lang=lang
        )

        try:
            with open(
                file_path,
                "r",
                encoding="utf-8",
            ) as f:
                config = json.load(f)

            if not isinstance(config, dict):
                config = {}

            config.setdefault("texts", {})
            config.setdefault("menus", {})

            return config

        except FileNotFoundError:
            if lang != cls._default_lang:
                return cls._load_config_for_lang_sync(
                    cls._default_lang
                )

            return {
                "texts": dict(cls._default_texts),
                "menus": {},
            }

        except Exception:
            return {
                "texts": dict(cls._default_texts),
                "menus": {},
            }

    @classmethod
    async def get_menu(
        cls,
        menu_name: str,
        lang: str = None,
    ) -> List[List[str]]:
        config = await cls.get_config(lang)

        menu = config.get(
            "menus",
            {},
        ).get(menu_name, {})

        if not isinstance(menu, dict):
            return []

        rows = menu.get("rows", [])

        if not isinstance(rows, list):
            return []

        result = []

        for row in rows:
            if isinstance(row, (list, tuple)):
                result.append(
                    [
                        str(item)
                        for item in row
                        if item is not None
                    ]
                )

        return result

    @classmethod
    def _default_menus(cls):
        return {
            "banned_words": [
                ["ban_add", "ban_list"],
                ["ban_rem"],
                ["back"],
            ],

            "auto_reply_manage": [
                ["auto_reply_toggle", "auto_reply_admins"],
                ["auto_reply_add", "auto_reply_del"],
                ["auto_reply_list", "auto_reply_stats"],
                ["auto_reply_reset"],
                ["back"],
            ],

            "auto_reply": [
                ["auto_reply_toggle", "auto_reply_admins"],
                ["auto_reply_add", "auto_reply_del"],
                ["auto_reply_list", "auto_reply_stats"],
                ["auto_reply_reset"],
                ["back"],
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
                ["sec_close"],
            ],

            "penalty": [
                ["pen_ban", "pen_mute"],
                ["pen_kick", "pen_warn"],
                ["back"],
            ],

            "advanced_actions": [
                ["act_ban", "act_mute"],
                ["act_warn", "act_kick"],
                ["act_restrict", "act_unban"],
                ["act_pin"],
                ["act_log"],
                ["back"],
            ],

            "violation_penalties": [
                [
                    "sec_set_violation_strikes",
                    "sec_set_violation_duration",
                ],
                ["back"],
            ],

            "settings": [
                ["toggle_auto", "toggle_rec"],
                ["reminder", "translation"],
                ["referral", "invoices"],
                ["back"],
            ],

            "plans": [
                ["buy_sub_1", "buy_sub_7"],
                ["buy_sub_30", "buy_sub_90"],
                ["buy_sub_365"],
                ["gift_plans", "redeem_gift"],
                ["back"],
            ],

            "reminder": [
                ["rem_sub", "rem_daily"],
                ["rem_weekly"],
                ["rem_days"],
                ["back"],
            ],

            "translation": [
                ["lang_ar", "lang_en"],
                ["trans_off"],
                ["back"],
            ],

            "channel_settings": [
                ["sched_min", "sched_hour"],
                ["sched_day", "sched_time"],
                ["back"],
            ],

            "admin": [
                ["admin_users", "admin_stats"],
                ["admin_banned", "admin_unban_all"],
                ["admin_channels", "admin_groups"],
                ["admin_grant_free", "admin_add_admin"],
                ["admin_broadcast", "admin_invoices"],
                ["admin_backup", "admin_restore"],
                ["admin_ram", "admin_metrics"],
                ["back"],
            ],

            "admin_panel": [
                ["admin_users", "admin_stats"],
                ["admin_banned", "admin_unban_all"],
                ["admin_channels", "admin_groups"],
                ["admin_grant_free", "admin_add_admin"],
                ["admin_broadcast", "admin_invoices"],
                ["admin_backup", "admin_restore"],
                ["admin_ram", "admin_metrics"],
                ["admin_tickets", "admin_payment_logs"],
                ["admin_replies", "admin_banned_words"],
                [
                    "admin_create_contest",
                    "admin_declare_winner",
                ],
                [
                    "admin_del_contest",
                    "admin_refresh_cache",
                ],
                ["admin_force_sub", "admin_log_ch"],
                [
                    "admin_send_update",
                    "admin_show_update",
                ],
                [
                    "admin_list_admins",
                    "admin_rem_admin",
                ],
                ["back"],
            ],

            "ad_channels": [
                ["ad_ch_add", "ad_ch_list"],
                ["ad_ch_set_price", "ad_ch_enable"],
                ["ad_ch_disable", "ad_ch_delete"],
                ["back"],
            ],
        }

    @staticmethod
    def _callback_bytes(value: str) -> int:
        return len(value.encode("utf-8"))

    @classmethod
    def _make_callback(
        cls,
        item: str,
        chat_id: Optional[int],
    ) -> Optional[str]:
        callback = str(item)

        if (
            chat_id is not None
            and item not in cls._NO_CHAT_ID_BUTTONS
        ):
            callback = f"{item}:{chat_id}"

        # Telegram callback_data limit = 64 bytes.
        if cls._callback_bytes(callback) > 64:
            logger.error(
                "❌ callback_data أطول من 64 بايت: %s",
                callback,
            )

            # لا نقص البيانات لأنها قد تغير هوية الزر.
            # إذا كان طويلًا، نستخدم القيمة الأصلية فقط إذا كانت صالحة.
            if cls._callback_bytes(item) <= 64:
                callback = item
            else:
                return None

        return callback

    @classmethod
    async def build(
        cls,
        menu_name: str,
        chat_id: int = None,
        extra_data: Dict = None,
        lang: str = None,
    ) -> InlineKeyboardMarkup:
        rows = await cls.get_menu(
            menu_name,
            lang,
        )

        if not rows:
            rows = cls._default_menus().get(
                menu_name,
                [],
            )

        keyboard = []

        for row in rows:
            btn_row = []

            for item in row:
                if not item:
                    continue

                item = str(item)

                # أزرار URL.
                if item.endswith("_url"):
                    key = item[:-4]

                    text = await cls.get_text(
                        key,
                        lang,
                    )

                    bot_username = getattr(
                        CONFIG,
                        "BOT_USERNAME",
                        "",
                    )

                    bot_username = str(
                        bot_username or ""
                    ).lstrip("@").strip()

                    if not bot_username:
                        logger.warning(
                            "⚠️ BOT_USERNAME غير معرف، تخطي زر URL: %s",
                            item,
                        )
                        continue

                    url = (
                        f"https://t.me/"
                        f"{bot_username}"
                        f"?startgroup=true"
                    )

                    btn_row.append(
                        InlineKeyboardButton(
                            text or key,
                            url=url,
                        )
                    )

                    continue

                text = await cls.get_text(
                    item,
                    lang,
                )

                callback = cls._make_callback(
                    item,
                    chat_id,
                )

                if callback is None:
                    continue

                btn_row.append(
                    InlineKeyboardButton(
                        text or item,
                        callback_data=callback,
                    )
                )

            if btn_row:
                keyboard.append(btn_row)

        if not keyboard:
            back_text = await cls.get_text(
                "back",
                lang,
            )

            keyboard = [
                [
                    InlineKeyboardButton(
                        back_text or "🔙 رجوع",
                        callback_data="back",
                    )
                ]
            ]

        return InlineKeyboardMarkup(keyboard)

    @classmethod
    def _status_icon(
        cls,
        value: Any,
    ) -> str:
        return "✅" if bool(value) else "❌"

    @classmethod
    def _format_security_text(
        cls,
        settings: dict,
    ) -> str:
        if not isinstance(settings, dict):
            settings = {}

        st = cls._status_icon

        lines = [
            "🔐 إعدادات الأمان",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            (
                f"🔗 روابط: "
                f"{st(settings.get('delete_links', 0))} | "
                f"👤 معرفات: "
                f"{st(settings.get('mentions', 0))}"
            ),
            (
                f"🌊 فيضان: "
                f"{st(settings.get('antiflood_enabled', 0))} | "
                f"📊 رسائل: "
                f"{settings.get('antiflood_messages', 5)} | "
                f"⏱️ ثواني: "
                f"{settings.get('antiflood_seconds', 10)}"
            ),
            (
                f"📏 طول: "
                f"{settings.get('max_message_length', 0)} | "
                f"🌙 ليلي: "
                f"{st(settings.get('night_mode_enabled', 0))} | "
                f"🔞 NSFW: "
                f"{st(settings.get('nsfw_enabled', 0))}"
            ),
            (
                f"⚠️ تحذيرات: "
                f"{st(settings.get('warn_enabled', 0))} | "
                f"📊 حد: "
                f"{settings.get('max_warnings', 3)}"
            ),
            "",
            (
                f"🎯 ترحيب: "
                f"{st(settings.get('welcome_enabled', 0))} | "
                f"👋 وداع: "
                f"{st(settings.get('goodbye_enabled', 0))}"
            ),
            (
                f"🗑️ رسائل الخدمة: "
                f"{st(settings.get('delete_service', 0))}"
            ),
            (
                f"🎬 فيديو: "
                f"{st(settings.get('delete_videos', 0))} | "
                f"🎤 صوتي: "
                f"{st(settings.get('delete_voice', 0))} | "
                f"🖼️ ملصقات: "
                f"{st(settings.get('delete_stickers', 0))}"
            ),
            (
                f"📄 ملفات: "
                f"{st(settings.get('delete_documents', 0))} | "
                f"📸 صور: "
                f"{st(settings.get('delete_photos', 0))} | "
                f"🎞️ متحرك: "
                f"{st(settings.get('delete_animation', 0))}"
            ),
            (
                f"✅ موافقة: "
                f"{st(settings.get('auto_approve_join', 0))} | "
                f"❌ رفض: "
                f"{st(settings.get('auto_reject_join', 0))}"
            ),
            "",
            (
                f"⏱️ كتم: "
                f"{settings.get('mute_default_duration', 3600)}ث | "
                f"🚫 حظر: "
                f"{settings.get('ban_default_duration', 0)}ث | "
                f"🔒 تقييد: "
                f"{settings.get('restrict_default_duration', 1800)}ث"
            ),
            (
                f"⚠️ مخالفات: "
                f"{settings.get('violation_strikes', 3)} | "
                f"⏱️ مدة: "
                f"{settings.get('violation_duration', 60)}ث"
            ),
            (
                f"🌊 مدة الفيضان: "
                f"{settings.get('antiflood_penalty_duration', 3600)}ث | "
                f"🌙 مدة الليل: "
                f"{settings.get('night_mode_action_duration', 3600)}ث"
            ),
            (
                f"⚖️ مدة عقوبة التحذير: "
                f"{settings.get('warn_penalty_duration', 3600)}ث"
            ),
            "━━━━━━━━━━━━━━━━━━━━",
        ]

        return "\n".join(lines)


# =====================================================================
# 10. الكلمات المحظورة
# =====================================================================

_banned_words_cache: Dict[int, List[str]] = {}
_banned_words_cache_time: Dict[int, float] = {}
_banned_words_locks: Dict[int, asyncio.Lock] = {}

_BANNED_WORDS_CACHE_TTL = getattr(
    CONFIG,
    "BANNED_WORDS_CACHE_TTL",
    60,
)

_ENABLE_BANNED_WORDS_CACHE = getattr(
    CONFIG,
    "ENABLE_BANNED_WORDS_CACHE",
    False,
)


def _normalize_word(
    word: Any,
) -> Optional[str]:
    if not isinstance(word, str):
        return None

    word = word.strip().casefold()

    return word or None


def _normalize_words(
    values: Any,
) -> List[str]:
    if not values:
        return []

    if isinstance(values, str):
        values = [values]

    result = set()

    try:
        iterator = iter(values)
    except TypeError:
        iterator = iter(())

    for value in iterator:
        normalized = _normalize_word(value)

        if normalized:
            result.add(normalized)

    return list(result)


async def _load_banned_words(
    chat_id: int,
) -> List[str]:
    try:
        local_words = await DB.get_banned_words(
            chat_id
        ) or []

        global_words = []

        if chat_id != -1:
            global_words = await DB.get_banned_words(
                -1
            ) or []

        return _normalize_words(
            list(local_words)
            + list(global_words)
        )

    except Exception as e:
        logger.error(
            "❌ فشل جلب الكلمات المحظورة: %s",
            e,
        )
        return []


async def get_banned_words_cached(
    chat_id: int,
) -> List[str]:
    if not _ENABLE_BANNED_WORDS_CACHE:
        return await _load_banned_words(chat_id)

    lock = _get_dict_lock(
        _banned_words_locks,
        chat_id,
    )

    async with lock:
        now = time.time()

        if (
            chat_id in _banned_words_cache
            and (
                now
                - _banned_words_cache_time.get(
                    chat_id,
                    0,
                )
            ) < _BANNED_WORDS_CACHE_TTL
        ):
            return list(
                _banned_words_cache[chat_id]
            )

        try:
            words = await _load_banned_words(
                chat_id
            )

            _banned_words_cache[chat_id] = list(
                words
            )

            _banned_words_cache_time[chat_id] = (
                time.time()
            )

            return list(words)

        except Exception:
            cached = _banned_words_cache.get(
                chat_id,
                [],
            )

            return list(cached)


def invalidate_banned_words_cache(
    chat_id: int = None,
) -> None:
    if chat_id is None or chat_id == -1:
        _banned_words_cache.clear()
        _banned_words_cache_time.clear()

        for key, lock in list(
            _banned_words_locks.items()
        ):
            if not lock.locked():
                _banned_words_locks.pop(
                    key,
                    None,
                )

        return

    _banned_words_cache.pop(
        chat_id,
        None,
    )

    _banned_words_cache_time.pop(
        chat_id,
        None,
    )

    lock = _banned_words_locks.get(chat_id)

    if lock is not None and not lock.locked():
        _banned_words_locks.pop(
            chat_id,
            None,
        )


async def get_min_publish_interval() -> int:
    default_value = getattr(
        CONFIG,
        "MIN_PUBLISH_INTERVAL",
        12,
    )

    try:
        default_value = max(
            1,
            int(default_value),
        )
    except (ValueError, TypeError):
        default_value = 12

    try:
        val = await DB.get_setting(
            "min_publish_interval",
            str(default_value),
        )

        value = int(val)

        return max(1, value)

    except Exception:
        return default_value


# =====================================================================
# 11. الصلاحيات
# =====================================================================

_auth_cache = TTLCache(
    maxsize=getattr(
        CONFIG,
        "AUTH_CACHE_SIZE",
        5000,
    ),
    ttl=getattr(
        CONFIG,
        "AUTH_CACHE_TTL",
        60,
    ),
)


async def is_authorized_in_group(
    bot,
    chat_id: int,
    user_id: int,
) -> bool:
    if user_id == getattr(
        CONFIG,
        "PRIMARY_OWNER_ID",
        None,
    ):
        return True

    cache_key = (
        f"auth_{chat_id}_{user_id}"
    )

    try:
        cached = _auth_cache.get(
            cache_key
        )

        if cached is not None:
            return bool(cached)

    except Exception:
        pass

    authorized = False

    try:
        member = await bot.get_chat_member(
            chat_id,
            user_id,
        )

        if getattr(member, "status", None) in (
            "administrator",
            "creator",
        ):
            authorized = True

    except Exception:
        pass

    if not authorized:
        try:
            row = await DB.fetchone(
                """
                SELECT 1
                FROM hidden_owner_groups
                WHERE chat_id=? AND owner_id=?

                UNION ALL

                SELECT 1
                FROM hidden_admins
                WHERE chat_id=? AND admin_id=?

                UNION ALL

                SELECT 1
                FROM anonymous_admins
                WHERE chat_id=?
                  AND (
                        user_id=?
                        OR (
                            user_id IS NULL
                            AND anonymous_id=?
                        )
                  )

                LIMIT 1
                """,
                (
                    chat_id,
                    user_id,
                    chat_id,
                    user_id,
                    chat_id,
                    user_id,
                    user_id,
                ),
            )

            authorized = row is not None

        except Exception as e:
            logger.warning(
                "⚠️ فشل فحص الصلاحيات المخفية "
                "chat=%s user=%s: %s",
                chat_id,
                user_id,
                e,
            )

    try:
        _auth_cache[cache_key] = authorized
    except Exception:
        pass

    return authorized


def invalidate_auth_cache(
    chat_id: int = None,
    user_id: int = None,
) -> None:
    with suppress(Exception):
        if (
            chat_id is not None
            and user_id is not None
        ):
            _auth_cache.pop(
                f"auth_{chat_id}_{user_id}",
                None,
            )
            return

        if chat_id is not None:
            prefix = f"auth_{chat_id}_"

            for key in list(
                _auth_cache.keys()
            ):
                if str(key).startswith(prefix):
                    _auth_cache.pop(
                        key,
                        None,
                    )

            return

        _auth_cache.clear()


async def _get_bot_id(bot) -> Optional[int]:
    bot_id = getattr(bot, "id", None)

    if bot_id:
        return bot_id

    try:
        me = await bot.get_me()
        return getattr(me, "id", None)
    except Exception:
        return None


async def check_bot_permissions(
    bot,
    chat_id: int,
) -> dict:
    try:
        bot_id = await _get_bot_id(bot)

        if not bot_id:
            return {
                "can_act": False,
                "reason": "تعذر معرفة معرف البوت",
                "can_pin": False,
            }

        me = await bot.get_chat_member(
            chat_id,
            bot_id,
        )

        status = getattr(
            me,
            "status",
            None,
        )

        if status not in (
            "administrator",
            "creator",
        ):
            return {
                "can_act": False,
                "reason": "البوت ليس مشرفاً",
                "can_pin": False,
            }

        if status == "creator":
            return {
                "can_act": True,
                "reason": "",
                "can_delete": True,
                "can_restrict": True,
                "can_pin": True,
            }

        can_delete = bool(
            getattr(
                me,
                "can_delete_messages",
                False,
            )
        )

        can_restrict = bool(
            getattr(
                me,
                "can_restrict_members",
                False,
            )
        )

        can_pin = bool(
            getattr(
                me,
                "can_pin_messages",
                False,
            )
        )

        if not can_delete or not can_restrict:
            return {
                "can_act": False,
                "reason": "صلاحيات ناقصة",
                "can_delete": can_delete,
                "can_restrict": can_restrict,
                "can_pin": can_pin,
            }

        return {
            "can_act": True,
            "reason": "",
            "can_delete": can_delete,
            "can_restrict": can_restrict,
            "can_pin": can_pin,
        }

    except Exception as e:
        return {
            "can_act": False,
            "reason": str(e)[:100],
            "can_pin": False,
        }


async def is_bot_admin(
    bot,
    chat_id: int,
) -> bool:
    try:
        bot_id = await _get_bot_id(bot)

        if not bot_id:
            return False

        me = await bot.get_chat_member(
            chat_id,
            bot_id,
        )

        return getattr(
            me,
            "status",
            None,
        ) in (
            "administrator",
            "creator",
        )

    except Exception:
        return False


# =====================================================================
# 12. إرسال آمن
# =====================================================================

def _filter_kwargs_for_callable(
    func,
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    تصفية kwargs حسب توقيع الدالة عند الإمكان.
    """
    if not kwargs:
        return {}

    try:
        signature = inspect.signature(func)

        accepts_kwargs = any(
            p.kind
            == inspect.Parameter.VAR_KEYWORD
            for p in signature.parameters.values()
        )

        if accepts_kwargs:
            return dict(kwargs)

        allowed = set(
            signature.parameters.keys()
        )

        return {
            key: value
            for key, value in kwargs.items()
            if key in allowed
        }

    except Exception:
        return dict(kwargs)


async def _send_media(
    bot,
    chat_id,
    media_type,
    media_file_id,
    caption=None,
    reply_markup=None,
    parse_mode=None,
    **kwargs,
):
    start_time = time.time()

    try:
        common = dict(kwargs)

        if parse_mode is not None:
            common["parse_mode"] = parse_mode

        if media_type == "photo":
            common["caption"] = caption
            common["reply_markup"] = reply_markup

            call_kwargs = _filter_kwargs_for_callable(
                bot.send_photo,
                common,
            )

            result = await bot.send_photo(
                chat_id,
                media_file_id,
                **call_kwargs,
            )

        elif media_type == "video":
            common["caption"] = caption
            common["reply_markup"] = reply_markup

            call_kwargs = _filter_kwargs_for_callable(
                bot.send_video,
                common,
            )

            result = await bot.send_video(
                chat_id,
                media_file_id,
                **call_kwargs,
            )

        elif media_type == "document":
            common["caption"] = caption
            common["reply_markup"] = reply_markup

            call_kwargs = _filter_kwargs_for_callable(
                bot.send_document,
                common,
            )

            result = await bot.send_document(
                chat_id,
                media_file_id,
                **call_kwargs,
            )

        elif media_type == "audio":
            common["caption"] = caption
            common["reply_markup"] = reply_markup

            call_kwargs = _filter_kwargs_for_callable(
                bot.send_audio,
                common,
            )

            result = await bot.send_audio(
                chat_id,
                media_file_id,
                **call_kwargs,
            )

        elif media_type == "voice":
            common["reply_markup"] = reply_markup

            if caption:
                common["caption"] = caption

            call_kwargs = _filter_kwargs_for_callable(
                bot.send_voice,
                common,
            )

            result = await bot.send_voice(
                chat_id,
                media_file_id,
                **call_kwargs,
            )

        elif media_type == "animation":
            common["caption"] = caption
            common["reply_markup"] = reply_markup

            call_kwargs = _filter_kwargs_for_callable(
                bot.send_animation,
                common,
            )

            result = await bot.send_animation(
                chat_id,
                media_file_id,
                **call_kwargs,
            )

        elif media_type == "sticker":
            # Telegram لا يدعم caption/reply_markup
            # بالطريقة المستخدمة للرسائل النصية هنا.
            sticker_kwargs = _filter_kwargs_for_callable(
                bot.send_sticker,
                common,
            )

            result = await bot.send_sticker(
                chat_id,
                media_file_id,
                **sticker_kwargs,
            )

            if caption:
                message_kwargs = {
                    "reply_markup": reply_markup,
                }

                if parse_mode is not None:
                    message_kwargs["parse_mode"] = (
                        parse_mode
                    )

                message_kwargs.update(kwargs)

                message_kwargs = (
                    _filter_kwargs_for_callable(
                        bot.send_message,
                        message_kwargs,
                    )
                )

                await bot.send_message(
                    chat_id,
                    caption,
                    **message_kwargs,
                )

        elif media_type == "video_note":
            # Telegram لا يدعم caption/reply_markup
            # للفيديو نوت بنفس أسلوب الرسائل.
            note_kwargs = _filter_kwargs_for_callable(
                bot.send_video_note,
                common,
            )

            result = await bot.send_video_note(
                chat_id,
                media_file_id,
                **note_kwargs,
            )

            if caption:
                message_kwargs = {
                    "reply_markup": reply_markup,
                }

                if parse_mode is not None:
                    message_kwargs["parse_mode"] = (
                        parse_mode
                    )

                await bot.send_message(
                    chat_id,
                    caption,
                    **_filter_kwargs_for_callable(
                        bot.send_message,
                        message_kwargs,
                    ),
                )

        else:
            message_kwargs = dict(kwargs)

            if reply_markup is not None:
                message_kwargs[
                    "reply_markup"
                ] = reply_markup

            if parse_mode is not None:
                message_kwargs[
                    "parse_mode"
                ] = parse_mode

            message_kwargs = (
                _filter_kwargs_for_callable(
                    bot.send_message,
                    message_kwargs,
                )
            )

            result = await bot.send_message(
                chat_id,
                caption or ".",
                **message_kwargs,
            )

        METRICS.record_api_call(
            f"send_{media_type or 'message'}",
            time.time() - start_time,
        )

        return result

    except Exception as e:
        METRICS.record_error(
            type(e).__name__,
            f"send_{media_type or 'message'}",
        )
        raise


async def safe_send(
    bot,
    chat_id: int,
    text: str = None,
    reply_markup=None,
    parse_mode: str = None,
    photo=None,
    video=None,
    document=None,
    audio=None,
    voice=None,
    animation=None,
    sticker=None,
    video_note=None,
    **kwargs,
):
    """
    إرسال آمن للرسائل والوسائط.

    ملاحظة:
    إعادة محاولة TimedOut قد تسبب رسالة مكررة في حالات نادرة
    إذا كان Telegram استلم الطلب ثم لم يصل الرد للبوت.
    لذلك لا تتم إعادة المحاولة إلا مرة واحدة.
    """

    if (
        not text
        and not any(
            [
                photo,
                video,
                document,
                audio,
                voice,
                animation,
                sticker,
                video_note,
            ]
        )
    ):
        return None

    await RATE_LIMITER.acquire()

    start_time = time.time()

    text = (
        TextUtils.sanitize(
            text,
            max_len=4096,
        )
        if text
        else ""
    )

    media_type = None
    media_file_id = None

    if photo:
        media_type = "photo"
        media_file_id = photo

    elif video:
        media_type = "video"
        media_file_id = video

    elif document:
        media_type = "document"
        media_file_id = document

    elif audio:
        media_type = "audio"
        media_file_id = audio

    elif voice:
        media_type = "voice"
        media_file_id = voice

    elif animation:
        media_type = "animation"
        media_file_id = animation

    elif sticker:
        media_type = "sticker"
        media_file_id = sticker

    elif video_note:
        media_type = "video_note"
        media_file_id = video_note

    caption_text = (
        text[:1024]
        if media_type
        else text[:4096]
    )

    async def _send_once():
        if media_type:
            return await _send_media(
                bot,
                chat_id,
                media_type,
                media_file_id,
                caption=caption_text or None,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                **kwargs,
            )

        message_kwargs = dict(kwargs)

        if reply_markup is not None:
            message_kwargs[
                "reply_markup"
            ] = reply_markup

        if parse_mode is not None:
            message_kwargs[
                "parse_mode"
            ] = parse_mode

        message_kwargs = (
            _filter_kwargs_for_callable(
                bot.send_message,
                message_kwargs,
            )
        )

        result = await bot.send_message(
            chat_id=chat_id,
            text=caption_text,
            **message_kwargs,
        )

        METRICS.record_api_call(
            "send_message",
            time.time() - start_time,
        )

        return result

    try:
        return await _send_once()

    except TimedOut:
        logger.warning(
            "⚠️ TimedOut أثناء الإرسال إلى %s، "
            "إعادة المحاولة مرة واحدة",
            chat_id,
        )

        try:
            await asyncio.sleep(1)
            return await _send_once()

        except Exception as e:
            METRICS.record_error(
                type(e).__name__,
                "send_retry",
            )

            logger.error(
                "❌ فشل الإرسال بعد TimedOut: %s",
                e,
            )

            return None

    except BadRequest as e:
        error_msg = str(e).lower()

        # إذا كانت المشكلة parse_mode/entity
        # نعيد الإرسال بدون parse_mode.
        parse_error = (
            "can't parse entities" in error_msg
            or "parse entities" in error_msg
            or "parse_mode" in error_msg
            or "entities" in error_msg
        )

        if parse_error:
            try:
                if media_type:
                    return await _send_media(
                        bot,
                        chat_id,
                        media_type,
                        media_file_id,
                        caption=caption_text or None,
                        reply_markup=reply_markup,
                        parse_mode=None,
                        **kwargs,
                    )

                message_kwargs = dict(kwargs)

                if reply_markup is not None:
                    message_kwargs[
                        "reply_markup"
                    ] = reply_markup

                message_kwargs.pop(
                    "parse_mode",
                    None,
                )

                message_kwargs = (
                    _filter_kwargs_for_callable(
                        bot.send_message,
                        message_kwargs,
                    )
                )

                result = await bot.send_message(
                    chat_id=chat_id,
                    text=caption_text,
                    **message_kwargs,
                )

                METRICS.record_api_call(
                    "send_message_no_parse",
                    time.time() - start_time,
                )

                return result

            except Exception as e2:
                METRICS.record_error(
                    type(e2).__name__,
                    "send_no_parse",
                )

                logger.error(
                    "❌ فشل الإرسال بدون parse_mode: %s",
                    e2,
                )

        else:
            METRICS.record_error(
                type(e).__name__,
                "bad_request",
            )

            logger.warning(
                "⚠️ Telegram BadRequest: %s",
                e,
            )

        return None

    except Exception as e:
        METRICS.record_error(
            type(e).__name__,
            "safe_send",
        )

        logger.warning(
            "⚠️ فشل الإرسال إلى %s: %s",
            chat_id,
            e,
        )

        return None


def get_ram_usage() -> dict:
    if psutil is None:
        return {
            "total": 0,
            "used": 0,
            "percent": 0,
        }

    try:
        mem = psutil.virtual_memory()

        return {
            "total": round(
                mem.total / (1024 ** 3),
                1,
            ),
            "used": round(
                mem.used / (1024 ** 3),
                1,
            ),
            "percent": mem.percent,
        }

    except Exception as e:
        logger.error(
            "❌ فشل جلب الرام: %s",
            e,
        )

        return {
            "total": 0,
            "used": 0,
            "percent": 0,
        }


# =====================================================================
# 13. نظام العقوبات
# =====================================================================

def _make_chat_permissions(
    *,
    can_send_messages: bool,
    can_send_media: bool,
    can_send_polls: bool,
    can_send_other: bool,
    can_add_web_page_previews: bool = False,
    can_change_info: bool = False,
    can_invite_users: bool = True,
    can_pin_messages: bool = False,
) -> ChatPermissions:
    """
    إنشاء ChatPermissions متوافق قدر الإمكان
    مع إصدارات PTB المختلفة.
    """

    values = {
        "can_send_messages": can_send_messages,

        # الإصدارات القديمة.
        "can_send_media_messages": can_send_media,
        "can_send_other_messages": can_send_other,

        # الإصدارات الحديثة.
        "can_send_audios": can_send_media,
        "can_send_documents": can_send_media,
        "can_send_photos": can_send_media,
        "can_send_videos": can_send_media,
        "can_send_video_notes": can_send_media,
        "can_send_voice_notes": can_send_media,

        "can_send_polls": can_send_polls,

        "can_add_web_page_previews":
            can_add_web_page_previews,

        "can_change_info": can_change_info,
        "can_invite_users": can_invite_users,
        "can_pin_messages": can_pin_messages,
    }

    try:
        signature = inspect.signature(
            ChatPermissions
        )

        allowed = set(
            signature.parameters.keys()
        )

        filtered = {
            key: value
            for key, value in values.items()
            if key in allowed
        }

        return ChatPermissions(
            **filtered
        )

    except Exception:
        # محاولة توافق إضافية.
        fallback = {
            "can_send_messages":
                can_send_messages,
            "can_send_media_messages":
                can_send_media,
            "can_send_polls":
                can_send_polls,
            "can_send_other_messages":
                can_send_other,
            "can_add_web_page_previews":
                can_add_web_page_previews,
            "can_change_info":
                can_change_info,
            "can_invite_users":
                can_invite_users,
            "can_pin_messages":
                can_pin_messages,
        }

        try:
            return ChatPermissions(
                **fallback
            )
        except Exception:
            return ChatPermissions()


class PenaltyStrategy(ABC):
    @abstractmethod
    async def apply(
        self,
        bot,
        chat_id: int,
        user_id: int,
        **kwargs,
    ) -> Tuple[bool, str]:
        raise NotImplementedError


class BanPenalty(PenaltyStrategy):
    async def apply(
        self,
        bot,
        chat_id: int,
        user_id: int,
        **kwargs,
    ) -> Tuple[bool, str]:

        bot_id = await _get_bot_id(bot)

        if bot_id and user_id == bot_id:
            return False, "لا يمكن حظر البوت"

        try:
            duration = int(
                kwargs.get("duration", 0) or 0
            )

            until_date = (
                TimeUtils.utc_now()
                + timedelta(seconds=duration)
                if duration > 0
                else None
            )

            await bot.ban_chat_member(
                chat_id,
                user_id,
                until_date=until_date,
            )

            return True, "✅ تم الحظر"

        except Exception as e:
            return False, str(e)[:100]


class MutePenalty(PenaltyStrategy):
    async def apply(
        self,
        bot,
        chat_id: int,
        user_id: int,
        **kwargs,
    ) -> Tuple[bool, str]:

        bot_id = await _get_bot_id(bot)

        if bot_id and user_id == bot_id:
            return False, "لا يمكن كتم البوت"

        try:
            duration = int(
                kwargs.get("duration", 60) or 60
            )

            duration = max(0, duration)

            until_date = (
                TimeUtils.utc_now()
                + timedelta(seconds=duration)
                if duration > 0
                else None
            )

            permissions = _make_chat_permissions(
                can_send_messages=False,
                can_send_media=False,
                can_send_polls=False,
                can_send_other=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
            )

            await bot.restrict_chat_member(
                chat_id,
                user_id,
                permissions,
                until_date=until_date,
            )

            return True, "✅ تم الكتم"

        except Exception as e:
            return False, str(e)[:100]


class KickPenalty(PenaltyStrategy):
    async def apply(
        self,
        bot,
        chat_id: int,
        user_id: int,
        **kwargs,
    ) -> Tuple[bool, str]:

        bot_id = await _get_bot_id(bot)

        if bot_id and user_id == bot_id:
            return False, "لا يمكن طرد البوت"

        try:
            await bot.ban_chat_member(
                chat_id,
                user_id,
            )

            await bot.unban_chat_member(
                chat_id,
                user_id,
            )

            return True, "✅ تم الطرد"

        except Exception as e:
            return False, str(e)[:100]


class WarnPenalty(PenaltyStrategy):
    async def apply(
        self,
        bot,
        chat_id: int,
        user_id: int,
        **kwargs,
    ) -> Tuple[bool, str]:

        bot_id = await _get_bot_id(bot)

        if bot_id and user_id == bot_id:
            return False, "لا يمكن تحذير البوت"

        try:
            warning = await DB.add_user_warning(
                user_id,
                chat_id,
            )

            if warning is None:
                return True, "⚠️ تم تسجيل التحذير"

            return True, f"⚠️ تحذير {warning}"

        except Exception as e:
            return False, str(e)[:100]


class RestrictPenalty(PenaltyStrategy):
    async def apply(
        self,
        bot,
        chat_id: int,
        user_id: int,
        **kwargs,
    ) -> Tuple[bool, str]:

        bot_id = await _get_bot_id(bot)

        if bot_id and user_id == bot_id:
            return False, "لا يمكن تقييد البوت"

        try:
            duration = int(
                kwargs.get("duration", 0) or 0
            )

            duration = max(0, duration)

            until_date = (
                TimeUtils.utc_now()
                + timedelta(seconds=duration)
                if duration > 0
                else None
            )

            # التقييد يسمح بالنصوص ويمنع الوسائط.
            permissions = _make_chat_permissions(
                can_send_messages=True,
                can_send_media=False,
                can_send_polls=False,
                can_send_other=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
            )

            await bot.restrict_chat_member(
                chat_id,
                user_id,
                permissions,
                until_date=until_date,
            )

            return True, "✅ تم التقييد"

        except Exception as e:
            return False, str(e)[:100]


class UnbanPenalty(PenaltyStrategy):
    async def apply(
        self,
        bot,
        chat_id: int,
        user_id: int,
        **kwargs,
    ) -> Tuple[bool, str]:

        try:
            await bot.unban_chat_member(
                chat_id,
                user_id,
            )

            return True, "✅ تم إلغاء الحظر"

        except Exception as e:
            return False, str(e)[:100]


class PenaltyFactory:
    @staticmethod
    def get_strategy(
        penalty_type: str,
    ):
        if not penalty_type:
            return None

        penalty_type = str(
            penalty_type
        ).strip().lower()

        strategies = {
            "ban": BanPenalty,
            "mute": MutePenalty,
            "kick": KickPenalty,
            "warn": WarnPenalty,
            "restrict": RestrictPenalty,
            "unban": UnbanPenalty,
        }

        strategy = strategies.get(
            penalty_type
        )

        return strategy() if strategy else None


async def apply_penalty(
    bot,
    chat_id: int,
    user_id: int,
    penalty: str,
    duration: int = 60,
    reason: str = "",
    moderator: int = None,
) -> Tuple[bool, str]:

    owner_id = getattr(
        CONFIG,
        "PRIMARY_OWNER_ID",
        None,
    )

    bot_id = await _get_bot_id(bot)

    if owner_id is not None and user_id == owner_id:
        return False, "لا يمكن معاملة المالك"

    if bot_id and user_id == bot_id:
        return False, "لا يمكن معاملة البوت"

    penalty = str(
        penalty or ""
    ).strip().lower()

    if penalty not in {
        "ban",
        "mute",
        "kick",
        "warn",
        "restrict",
        "unban",
    }:
        return False, "نوع عقوبة غير معروف"

    if penalty != "unban":
        if await is_authorized_in_group(
            bot,
            chat_id,
            user_id,
        ):
            return False, "لا يمكن معاملة مشرف"

    perms = await check_bot_permissions(
        bot,
        chat_id,
    )

    if not perms.get("can_act"):
        return False, "الصلاحيات غير كافية"

    if penalty == "unban":
        if not perms.get(
            "can_restrict",
            True,
        ):
            return False, "صلاحية فك الحظر غير متوفرة"

    strategy = PenaltyFactory.get_strategy(
        penalty
    )

    if not strategy:
        return False, "نوع عقوبة غير معروف"

    try:
        duration = max(
            0,
            int(duration or 0),
        )
    except (ValueError, TypeError):
        duration = 60

    success, msg = await strategy.apply(
        bot,
        chat_id,
        user_id,
        duration=duration,
    )

    if not success:
        return success, msg

    valid_penalties = getattr(
        DB,
        "VALID_PENALTY_TYPES",
        {
            "ban",
            "mute",
            "kick",
            "warn",
            "restrict",
            "unban",
        },
    )

    try:
        if penalty in valid_penalties:
            await DB.add_penalty(
                user_id=user_id,
                chat_id=chat_id,
                penalty_type=penalty,
                duration=duration,
                reason=reason,
                issued_by=moderator,
            )
    except Exception as e:
        logger.error(
            "❌ فشل تسجيل العقوبة في DB: %s",
            e,
        )

    if moderator:
        try:
            await DB.add_admin_log(
                chat_id,
                moderator,
                penalty,
                user_id,
                reason,
            )
        except Exception as e:
            logger.error(
                "❌ فشل تسجيل سجل المشرف: %s",
                e,
            )

    return True, msg


# =====================================================================
# 14. الردود التلقائية
# =====================================================================

_usage_updates: Dict[
    Tuple[int, str],
    int,
] = {}

_USAGE_FLUSH_LIMIT = 50
_USAGE_FLUSH_INTERVAL = 60

_usage_lock = asyncio.Lock()


async def _increment_usage_async(
    chat_id: int,
    keyword: str,
):
    keyword = str(
        keyword or ""
    ).strip().lower()

    if not keyword:
        return

    async with _usage_lock:
        key = (
            chat_id,
            keyword,
        )

        _usage_updates[key] = (
            _usage_updates.get(key, 0)
            + 1
        )

        should_flush = (
            len(_usage_updates)
            >= _USAGE_FLUSH_LIMIT
        )

    if should_flush:
        await _flush_usage_updates()


async def _flush_usage_updates():
    async with _usage_lock:
        if not _usage_updates:
            return

        data = list(
            _usage_updates.items()
        )

        _usage_updates.clear()

    failed = {}

    for (chat_id, keyword), count in data:
        try:
            await DB.execute(
                """
                UPDATE auto_replies
                SET usage_count = usage_count + ?
                WHERE chat_id=? AND keyword=?
                """,
                (
                    count,
                    chat_id,
                    keyword,
                ),
            )

        except Exception as e:
            failed[
                (chat_id, keyword)
            ] = count

            logger.error(
                "❌ فشل تحديث usage_count "
                "chat=%s keyword=%s: %s",
                chat_id,
                keyword,
                e,
            )

    if failed:
        async with _usage_lock:
            for key, count in failed.items():
                _usage_updates[key] = (
                    _usage_updates.get(
                        key,
                        0,
                    )
                    + count
                )


async def flush_usage_periodically():
    while True:
        await asyncio.sleep(
            _USAGE_FLUSH_INTERVAL
        )

        try:
            await _flush_usage_updates()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "❌ خطأ في flush_usage_periodically"
            )


async def export_auto_replies(
    chat_id: int,
    file_path: str = None,
) -> int:
    try:
        rows = await DB.fetchall(
            """
            SELECT keyword, reply
            FROM auto_replies
            WHERE chat_id=? AND is_active=1
            """,
            (chat_id,),
        )

        if not rows:
            return 0

        data = []

        for row in rows:
            try:
                data.append(dict(row))
            except Exception:
                if isinstance(row, (tuple, list)):
                    if len(row) >= 2:
                        data.append(
                            {
                                "keyword": row[0],
                                "reply": row[1],
                            }
                        )

        if not data:
            return 0

        if file_path is None:
            file_path = (
                f"auto_replies_{chat_id}.json"
            )

        file_path = str(file_path)

        def _write():
            target = Path(file_path)
            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with open(
                target,
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(
                    data,
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        await asyncio.to_thread(_write)

        return len(data)

    except Exception as e:
        logger.error(
            "❌ Export error: %s",
            e,
        )
        return 0


async def import_auto_replies(
    chat_id: int,
    file_path_or_data: Union[
        str,
        List[Dict],
    ],
    overwrite: bool = False,
) -> int:
    try:
        if isinstance(
            file_path_or_data,
            str,
        ):
            with open(
                file_path_or_data,
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)
        else:
            data = file_path_or_data

        if not isinstance(data, list):
            return 0

        count = 0

        for item in data:
            if not isinstance(item, dict):
                continue

            keyword = str(
                item.get(
                    "keyword",
                    "",
                )
                or ""
            ).strip().lower()

            reply = str(
                item.get(
                    "reply",
                    "",
                )
                or ""
            ).strip()

            if not keyword or not reply:
                continue

            if overwrite:
                try:
                    await DB.execute(
                        """
                        DELETE FROM auto_replies
                        WHERE chat_id=? AND keyword=?
                        """,
                        (
                            chat_id,
                            keyword,
                        ),
                    )
                except Exception as e:
                    logger.warning(
                        "⚠️ تعذر حذف الرد القديم: %s",
                        e,
                    )

            reply_type = str(
                item.get(
                    "reply_type",
                    "text",
                )
                or "text"
            )

            media_id = item.get(
                "media_file_id"
            )

            buttons = item.get(
                "buttons"
            )

            if buttons is not None:
                try:
                    buttons = json.dumps(
                        buttons,
                        ensure_ascii=False,
                    )
                except Exception:
                    buttons = None

            try:
                await DB.add_auto_reply(
                    chat_id,
                    keyword,
                    reply,
                    reply_type=reply_type,
                    media_id=media_id,
                    buttons=buttons,
                )

                count += 1

            except TypeError:
                # توافق مع تنفيذات DB التي لا تحتوي
                # معاملات الوسائط الإضافية.
                await DB.add_auto_reply(
                    chat_id,
                    keyword,
                    reply,
                )

                count += 1

        await _auto_reply_cache.clear()

        invalidate_auto_reply_cache(
            chat_id
        )

        return count

    except Exception as e:
        logger.error(
            "❌ Import error: %s",
            e,
        )
        return 0


async def fetch_json_from_url(
    url: str,
) -> Optional[
    Union[
        list,
        dict,
    ]
]:
    """
    تحميل JSON من HTTP/HTTPS.

    يتم رفض البروتوكولات غير HTTP/HTTPS.
    """

    if not url:
        return None

    url = str(url).strip()

    if not re.match(
        r"^https?://",
        url,
        re.IGNORECASE,
    ):
        logger.warning(
            "⚠️ رابط غير مسموح: %s",
            url[:100],
        )
        return None

    timeout = aiohttp.ClientTimeout(
        total=10,
        connect=5,
        sock_read=10,
    )

    headers = {
        "Accept": "application/json",
        "User-Agent": "RelaxMgr/1.0",
    }

    try:
        connector = aiohttp.TCPConnector(
            limit=10,
            ttl_dns_cache=300,
            ssl=True,
        )

        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
            connector=connector,
        ) as session:

            async with session.get(
                url,
                allow_redirects=True,
                max_redirects=5,
            ) as response:

                response.raise_for_status()

                content_length = response.headers.get(
                    "Content-Length"
                )

                if content_length:
                    try:
                        if int(content_length) > (
                            5 * 1024 * 1024
                        ):
                            logger.warning(
                                "⚠️ JSON أكبر من الحد المسموح"
                            )
                            return None
                    except ValueError:
                        pass

                data = await response.json(
                    content_type=None
                )

                if isinstance(
                    data,
                    (list, dict),
                ):
                    return data

                return None

    except asyncio.TimeoutError:
        logger.error(
            "❌ انتهت مهلة تحميل JSON"
        )
        return None

    except aiohttp.ClientError as e:
        logger.error(
            "❌ خطأ HTTP عند تحميل JSON: %s",
            e,
        )
        return None

    except json.JSONDecodeError as e:
        logger.error(
            "❌ الاستجابة ليست JSON صالحًا: %s",
            e,
        )
        return None

    except Exception as e:
        logger.error(
            "❌ Fetch JSON error: %s",
            e,
        )
        return None


# =====================================================================
# 15. الردود من replies.py
# =====================================================================

def load_replies_from_file() -> dict:
    try:
        import replies

        replies_module = importlib.reload(
            replies
        )

        replies_data = getattr(
            replies_module,
            "REPLIES",
            {},
        )

        if not isinstance(
            replies_data,
            dict,
        ):
            logger.warning(
                "⚠️ REPLIES ليس dict"
            )
            return {}

        logger.info(
            "✅ تم تحميل ملف الردود: %s رد",
            len(replies_data),
        )

        return replies_data

    except ImportError:
        logger.info(
            "ℹ️ لا يوجد replies.py"
        )
        return {}

    except Exception as e:
        logger.error(
            "❌ خطأ في تحميل replies.py: %s",
            e,
        )
        return {}


_REPLIES_FROM_FILE = (
    load_replies_from_file()
)


def _choose_reply(
    replies: Any,
) -> Optional[str]:
    if isinstance(
        replies,
        str,
    ):
        return replies

    if isinstance(
        replies,
        (tuple, list),
    ):
        values = [
            str(value)
            for value in replies
            if value is not None
        ]

        if values:
            return random.choice(values)

    return None


def get_reply_from_file(
    keyword: str,
) -> Optional[str]:
    if (
        not _REPLIES_FROM_FILE
        or not keyword
    ):
        return None

    keyword = str(
        keyword
    ).lower().strip()

    if not keyword:
        return None

    lines = keyword.splitlines()

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line in _REPLIES_FROM_FILE:
            return _choose_reply(
                _REPLIES_FROM_FILE[line]
            )

        words = line.split()

        for word in words:
            if word in _REPLIES_FROM_FILE:
                result = _choose_reply(
                    _REPLIES_FROM_FILE[word]
                )

                if result is not None:
                    return result

    for key, replies in (
        _REPLIES_FROM_FILE.items()
    ):
        if not isinstance(
            key,
            str,
        ):
            continue

        if not key.strip():
            continue

        if re.search(
            rf"\b{re.escape(key.lower())}\b",
            keyword,
            re.IGNORECASE,
        ):
            result = _choose_reply(
                replies
            )

            if result is not None:
                return result

    return None


def reload_replies_from_file() -> dict:
    global _REPLIES_FROM_FILE

    _REPLIES_FROM_FILE = (
        load_replies_from_file()
    )

    return _REPLIES_FROM_FILE


# =====================================================================
# 16. المهام الخلفية
# =====================================================================

class BackgroundTasks:
    """المهام الخلفية للبوت."""

    @staticmethod
    async def _publish_post(
        bot,
        channel_id: int,
        post: dict,
    ) -> bool:
        if not isinstance(post, dict):
            return False

        try:
            text = str(
                post.get(
                    "text",
                    "",
                )
                or ""
            )

            media_type = post.get(
                "media_type"
            )

            media_file_id = post.get(
                "media_file_id"
            )

            if media_type and media_file_id:
                await safe_send(
                    bot,
                    channel_id,
                    text=text or None,
                    **{
                        str(media_type): media_file_id
                    },
                )
            else:
                if not text:
                    text = "."

                await safe_send(
                    bot,
                    channel_id,
                    text=text[:4096],
                )

            return True

        except Exception as e:
            logger.error(
                "❌ Publish error channel=%s: %s",
                channel_id,
                e,
            )

            return False

    @staticmethod
    async def _publish_single_channel(
        bot,
        ch,
        sleep_seconds,
    ):
        if not isinstance(ch, dict):
            return

        channel_db_id = ch.get("id")

        try:
            user_id = ch.get("user_id")

            if user_id is None:
                logger.warning(
                    "⚠️ قناة بدون user_id: %s",
                    channel_db_id,
                )
                return

            has_sub = await DB.has_active_subscription(
                user_id
            )

            if not has_sub:
                logger.info(
                    "⏭️ تخطي القناة %s لانتهاء الاشتراك",
                    channel_db_id,
                )
                return

            post = await DB.get_next_post(
                channel_db_id
            )

            if not post:
                auto_recycle = (
                    await DB.get_auto_recycle_status(
                        user_id
                    )
                )

                if auto_recycle:
                    await DB.reset_posts(
                        user_id,
                        channel_db_id,
                    )

                    post = await DB.get_next_post(
                        channel_db_id
                    )

                if not post:
                    return

            post_id = (
                post.get("id")
                if isinstance(post, dict)
                else None
            )

            if post_id is None:
                logger.error(
                    "❌ المنشور لا يحتوي id: %s",
                    post,
                )
                return

            channel_id = ch.get(
                "channel_id"
            )

            if channel_id is None:
                logger.error(
                    "❌ القناة لا تحتوي channel_id: %s",
                    channel_db_id,
                )
                return

            success = (
                await BackgroundTasks._publish_post(
                    bot,
                    channel_id,
                    post,
                )
            )

            if success:
                await DB.mark_post_published(
                    post_id
                )

                await DB.update_last_publish(
                    channel_db_id
                )

                await DB.update_next_publish(
                    channel_db_id
                )

                logger.info(
                    "✅ تم نشر المنشور في القناة %s",
                    channel_db_id,
                )

                try:
                    await safe_send(
                        bot,
                        user_id,
                        "✅ تم نشر منشور في قناتك",
                    )
                except Exception as e:
                    logger.warning(
                        "⚠️ تعذر إرسال إشعار النشر: %s",
                        e,
                    )

                if sleep_seconds > 0:
                    await asyncio.sleep(
                        sleep_seconds
                    )

            else:
                try:
                    await DB.increment_post_fail(
                        post_id
                    )
                except Exception as e:
                    logger.warning(
                        "⚠️ فشل تسجيل فشل المنشور: %s",
                        e,
                    )

        except asyncio.CancelledError:
            raise

        except Exception as e:
            logger.error(
                "❌ خطأ في قناة %s: %s",
                channel_db_id,
                e,
            )

    @staticmethod
    async def auto_publish(
        bot,
    ) -> None:
        await asyncio.sleep(10)

        max_channels = getattr(
            CONFIG,
            "MAX_CHANNELS_PER_CYCLE",
            20,
        )

        try:
            max_channels = max(
                1,
                int(max_channels),
            )
        except (ValueError, TypeError):
            max_channels = 20

        min_interval_minutes = (
            await get_min_publish_interval()
        )

        sleep_seconds = (
            min_interval_minutes * 60
        )

        publish_semaphore = asyncio.Semaphore(
            max_channels
        )

        active_tasks = {}

        while True:
            try:
                channels = await asyncio.wait_for(
                    DB.get_channels_to_publish(
                        max_channels
                    ),
                    timeout=10,
                )

                if not channels:
                    await asyncio.sleep(60)
                    continue

                for ch in channels:
                    if not isinstance(ch, dict):
                        continue

                    channel_key = ch.get("id")

                    if channel_key is None:
                        continue

                    existing = active_tasks.get(
                        channel_key
                    )

                    if (
                        existing is not None
                        and not existing.done()
                    ):
                        continue

                    async def run_publish(
                        ch=ch,
                    ):
                        async with publish_semaphore:
                            await (
                                BackgroundTasks
                                ._publish_single_channel(
                                    bot,
                                    ch,
                                    sleep_seconds,
                                )
                            )

                    task = asyncio.create_task(
                        run_publish()
                    )

                    active_tasks[
                        channel_key
                    ] = task

                    await asyncio.sleep(
                        0.2
                    )

                for cid, task in list(
                    active_tasks.items()
                ):
                    if task.done():
                        active_tasks.pop(
                            cid,
                            None,
                        )

                        with suppress(
                            asyncio.CancelledError
                        ):
                            try:
                                task.result()
                            except Exception as e:
                                logger.error(
                                    "❌ مهمة نشر فشلت: %s",
                                    e,
                                )

                await asyncio.sleep(60)

            except asyncio.CancelledError:
                for task in active_tasks.values():
                    task.cancel()

                await asyncio.gather(
                    *active_tasks.values(),
                    return_exceptions=True,
                )

                raise

            except asyncio.TimeoutError:
                logger.error(
                    "❌ استعلام القنوات تجاوز 10 ثوانٍ"
                )

                await asyncio.sleep(30)

            except Exception as e:
                logger.error(
                    "❌ خطأ في auto_publish: %s",
                    e,
                )

                await asyncio.sleep(60)

    @staticmethod
    async def auto_backup() -> None:
        await asyncio.sleep(60)

        try:
            await BackgroundTasks._do_backup()
        except Exception as e:
            logger.error(
                "❌ Initial backup failed: %s",
                e,
            )

        while True:
            await asyncio.sleep(86400)

            try:
                await BackgroundTasks._do_backup()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    "❌ Backup error: %s",
                    e,
                )

    @staticmethod
    async def _do_backup() -> None:
        try:
            enabled = await DB.get_auto_backup()
        except Exception as e:
            logger.error(
                "❌ تعذر معرفة حالة النسخ الاحتياطي: %s",
                e,
            )
            return

        if not enabled:
            return

        backup_dir = Path(
            PATHS.BACKUPS
        )

        backup_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        backup_file = (
            backup_dir
            / (
                "backup_"
                f"{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}"
                ".db"
            )
        )

        def _backup():
            source = None
            dest = None

            try:
                source = sqlite3.connect(
                    str(PATHS.DB),
                    timeout=30,
                )

                dest = sqlite3.connect(
                    str(backup_file),
                    timeout=30,
                )

                with dest:
                    source.backup(dest)

            finally:
                if dest is not None:
                    with suppress(Exception):
                        dest.close()

                if source is not None:
                    with suppress(Exception):
                        source.close()

        await asyncio.to_thread(
            _backup
        )

        await DB.set_setting(
            "last_backup",
            TimeUtils.sql_iso(),
        )

        max_backups = getattr(
            CONFIG,
            "MAX_BACKUPS",
            10,
        )

        try:
            max_backups = max(
                1,
                int(max_backups),
            )
        except (ValueError, TypeError):
            max_backups = 10

        backups = sorted(
            backup_dir.glob(
                "backup_*.db"
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for old in backups[max_backups:]:
            with suppress(
                FileNotFoundError
            ):
                old.unlink()

    @staticmethod
    async def reminders(
        bot,
    ) -> None:
        while True:
            await asyncio.sleep(3600)

            try:
                users = (
                    await DB.get_users_for_reminder()
                )

                for user in users or []:
                    try:
                        if not isinstance(
                            user,
                            dict,
                        ):
                            continue

                        try:
                            days = int(
                                user.get(
                                    "days_left"
                                )
                            )
                        except (
                            ValueError,
                            TypeError,
                        ):
                            continue

                        user_id = user.get(
                            "user_id"
                        )

                        if user_id is None:
                            continue

                        lang = user.get(
                            "language",
                            "ar",
                        )

                        text = await get_text(
                            lang,
                            "reminder_subscription_expires",
                            days=days,
                        )

                        if (
                            text
                            == "reminder_subscription_expires"
                        ):
                            text = (
                                f"⚠️ اشتراكك سينتهي "
                                f"بعد {days} يوم"
                            )

                        await safe_send(
                            bot,
                            user_id,
                            text,
                        )

                        await asyncio.sleep(
                            0.1
                        )

                    except asyncio.CancelledError:
                        raise

                    except Exception:
                        continue

            except asyncio.CancelledError:
                raise

            except Exception as e:
                logger.error(
                    "❌ Reminders: %s",
                    e,
                )

    @staticmethod
    async def heartbeat(
        bot,
    ) -> None:
        interval = getattr(
            CONFIG,
            "HEARTBEAT_INTERVAL",
            3600,
        )

        try:
            interval = max(
                30,
                int(interval),
            )
        except (ValueError, TypeError):
            interval = 3600

        while True:
            await asyncio.sleep(interval)

            try:
                ram = get_ram_usage()

                msg = (
                    "💓 Heartbeat\n\n"
                    f"🕐 {TimeUtils.mecca_iso()}\n"
                    f"💾 RAM: {ram['percent']}%"
                )

                log_channel = (
                    await DB.get_log_channel()
                )

                target = (
                    log_channel
                    or getattr(
                        CONFIG,
                        "PRIMARY_OWNER_ID",
                        None,
                    )
                )

                if target:
                    await safe_send(
                        bot,
                        target,
                        msg,
                    )

            except asyncio.CancelledError:
                raise

            except Exception as e:
                logger.error(
                    "❌ Heartbeat error: %s",
                    e,
                )

    @staticmethod
    async def flush_usage_periodically() -> None:
        await flush_usage_periodically()

    @staticmethod
    async def expire_subscriptions() -> None:
        while True:
            await asyncio.sleep(3600)

            try:
                await DB.expire_expired_subscriptions()

            except asyncio.CancelledError:
                raise

            except Exception as e:
                logger.error(
                    "❌ Expire subs: %s",
                    e,
                )

    @staticmethod
    async def sync_admins_periodically(
        bot,
    ) -> None:
        await asyncio.sleep(60)

        while True:
            try:
                groups = await asyncio.wait_for(
                    DB.fetchall(
                        """
                        SELECT chat_id
                        FROM bot_groups
                        WHERE banned=0
                        """
                    ),
                    timeout=15,
                )

                for group in groups or []:
                    try:
                        if isinstance(
                            group,
                            dict,
                        ):
                            chat_id = group.get(
                                "chat_id"
                            )
                        else:
                            chat_id = group[0]

                        if chat_id is None:
                            continue

                        admins = (
                            await bot.get_chat_administrators(
                                chat_id
                            )
                        )

                        admin_ids = [
                            admin.user.id
                            for admin in admins
                            if getattr(
                                admin,
                                "user",
                                None,
                            )
                            and not getattr(
                                admin.user,
                                "is_bot",
                                False,
                            )
                        ]

                        await DB.sync_group_admins(
                            chat_id,
                            admin_ids,
                        )

                        # لا نعتبر حسابات bot العادية
                        # مشرفين مجهولين تلقائيًا.
                        # يتم الاعتماد على DB/handlers
                        # لمعالجة الحالات الخاصة.
                        anonymous_ids = []

                        for admin in admins:
                            user = getattr(
                                admin,
                                "user",
                                None,
                            )

                            if (
                                user
                                and getattr(
                                    user,
                                    "is_bot",
                                    False,
                                )
                                and getattr(
                                    admin,
                                    "status",
                                    None
                                )
                                == "administrator"
                            ):
                                anonymous_ids.append(
                                    user.id
                                )

                        if anonymous_ids:
                            with suppress(
                                Exception
                            ):
                                await DB.sync_anonymous_admins(
                                    chat_id,
                                    anonymous_ids,
                                    added_by=getattr(
                                        CONFIG,
                                        "PRIMARY_OWNER_ID",
                                        None,
                                    ),
                                    user_id_map={},
                                )

                    except asyncio.CancelledError:
                        raise

                    except Exception as e:
                        logger.debug(
                            "⚠️ تعذر مزامنة المجموعة %s: %s",
                            chat_id if "chat_id" in locals() else "?",
                            e,
                        )

            except asyncio.CancelledError:
                raise

            except asyncio.TimeoutError:
                logger.error(
                    "❌ استعلام المجموعات تجاوز 15 ثانية"
                )

            except Exception as e:
                logger.error(
                    "❌ Sync admins: %s",
                    e,
                )

            await asyncio.sleep(3600)

    @staticmethod
    async def expire_penalties_periodically() -> None:
        await asyncio.sleep(60)

        while True:
            try:
                await DB.expire_penalties()

            except asyncio.CancelledError:
                raise

            except Exception as e:
                logger.error(
                    "❌ Expire penalties: %s",
                    e,
                )

            await asyncio.sleep(60)

    @staticmethod
    async def cleanup_old_data() -> None:
        while True:
            await asyncio.sleep(3600)

            try:
                _security_settings_cache.clear()
                _security_settings_time.clear()

                _auto_reply_settings_cache.clear()
                _auto_reply_settings_time.clear()

                _banned_words_cache.clear()
                _banned_words_cache_time.clear()

                await _auto_reply_cache.clear()

                _auth_cache.clear()

                StateManager.cleanup_expired()

                # تنظيف الأقفال غير المستخدمة فقط.
                for lock_dict in (
                    _security_cache_locks,
                    _auto_reply_cache_locks,
                    _banned_words_locks,
                ):
                    for key, lock in list(
                        lock_dict.items()
                    ):
                        if not lock.locked():
                            lock_dict.pop(
                                key,
                                None,
                            )

                logger.info(
                    "✅ تم تنظيف الكاش المؤقت والحالات المنتهية"
                )

            except asyncio.CancelledError:
                raise

            except Exception as e:
                logger.error(
                    "❌ فشل تنظيف الكاش: %s",
                    e,
                )

            # تنظيف جداول البيانات بشكل مستقل.
            cleanup_queries = [
                (
                    """
                    DELETE FROM admin_logs
                    WHERE created_at <
                    datetime('now', '-30 days')
                    """,
                    "admin_logs",
                ),
                (
                    """
                    DELETE FROM user_penalties
                    WHERE created_at <
                    datetime('now', '-60 days')
                    """,
                    "user_penalties",
                ),
                (
                    """
                    DELETE FROM payment_logs
                    WHERE created_at <
                    datetime('now', '-90 days')
                    """,
                    "payment_logs",
                ),
            ]

            for query, table_name in cleanup_queries:
                try:
                    await DB.execute(query)

                except asyncio.CancelledError:
                    raise

                except Exception as e:
                    logger.warning(
                        "⚠️ تعذر تنظيف %s: %s",
                        table_name,
                        e,
                    )


# =====================================================================
# 17. خادم الويب / Webhook
# =====================================================================

_webhook_app = None
_webhook_runner = None


async def setup_webhook(
    app,
    port: int,
    webhook_secret: str = None,
):
    """
    تشغيل Webhook HTTP.

    يدعم secret token اختياريًا عبر:
    X-Telegram-Bot-Api-Secret-Token
    """

    global _webhook_app
    global _webhook_runner

    _webhook_app = app

    web_app = web.Application(
        client_max_size=10 * 1024 * 1024
    )

    async def health_handler(request):
        return web.Response(
            text="OK",
            status=200,
        )

    async def root_handler(request):
        return web.Response(
            text="🌿 Relax Manager",
            status=200,
        )

    async def fallback_handler(request):
        return web.Response(
            text="OK",
            status=200,
        )

    web_app.router.add_get(
        "/health",
        health_handler,
    )

    web_app.router.add_get(
        "/",
        root_handler,
    )

    token = str(
        getattr(
            CONFIG,
            "TOKEN",
            "",
        )
        or ""
    ).strip()

    if not token:
        raise RuntimeError(
            "CONFIG.TOKEN غير معرف"
        )

    web_app.router.add_post(
        f"/{token}",
        webhook_handler,
    )

    web_app.router.add_get(
        "/{tail:.*}",
        fallback_handler,
    )

    web_app.router.add_post(
        "/{tail:.*}",
        fallback_handler,
    )

    runner = web.AppRunner(
        web_app,
        access_log=logger,
    )

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        int(port),
    )

    await site.start()

    _webhook_runner = runner

    logger.info(
        "✅ Webhook يعمل على المنفذ %s",
        port,
    )

    return runner


async def webhook_handler(
    request,
):
    global _webhook_app

    if (
        _webhook_app is None
        or not hasattr(
            _webhook_app,
            "bot",
        )
    ):
        logger.error(
            "❌ Webhook app غير مهيأ"
        )

        return web.Response(
            status=503,
            text="Service Unavailable",
        )

    configured_secret = getattr(
        CONFIG,
        "WEBHOOK_SECRET",
        None,
    )

    if not configured_secret:
        configured_secret = getattr(
            CONFIG,
            "TELEGRAM_WEBHOOK_SECRET",
            None,
        )

    if configured_secret:
        received_secret = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token"
        )

        if received_secret != configured_secret:
            logger.warning(
                "⚠️ Webhook secret غير صحيح"
            )

            return web.Response(
                status=403,
                text="Forbidden",
            )

    content_type = (
        request.content_type or ""
    ).lower()

    if content_type != "application/json":
        logger.warning(
            "⚠️ Webhook غير JSON"
        )

        return web.Response(
            status=400,
            text="Bad Request",
        )

    try:
        data = await request.json()

        if not isinstance(
            data,
            dict,
        ):
            return web.Response(
                status=400,
                text="Bad Request",
            )

        update = Update.de_json(
            data,
            _webhook_app.bot,
        )

        if update is None:
            return web.Response(
                status=400,
                text="Bad Request",
            )

        await _webhook_app.process_update(
            update
        )

        return web.Response(
            status=200,
            text="OK",
        )

    except json.JSONDecodeError:
        return web.Response(
            status=400,
            text="Bad Request",
        )

    except Exception as e:
        logger.exception(
            "❌ Webhook error: %s",
            e,
        )

        return web.Response(
            status=500,
            text="ERROR",
        )


async def cleanup_webhook():
    global _webhook_runner

    if _webhook_runner is None:
        return

    try:
        await _webhook_runner.cleanup()

    except Exception as e:
        logger.warning(
            "⚠️ خطأ أثناء إغلاق Webhook: %s",
            e,
        )

    finally:
        _webhook_runner = None


# =====================================================================
# 18. معالج الأخطاء
# =====================================================================

class ErrorHandler:
    @staticmethod
    async def handle_error(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        try:
            error = getattr(
                context,
                "error",
                None,
            )

            error_text = (
                str(error)
                if error is not None
                else "Unknown error"
            )

            METRICS.record_error(
                type(error).__name__
                if error
                else "UnknownError",
                "telegram_update",
            )

            if update is not None:
                logger.error(
                    "❌ خطأ في التحديث %s: %s",
                    getattr(
                        update,
                        "update_id",
                        "?",
                    ),
                    error_text,
                    exc_info=error
                    if isinstance(
                        error,
                        BaseException,
                    )
                    else None,
                )
            else:
                logger.error(
                    "❌ خطأ Telegram: %s",
                    error_text,
                    exc_info=error
                    if isinstance(
                        error,
                        BaseException,
                    )
                    else None,
                )

        except Exception:
            logger.exception(
                "❌ فشل ErrorHandler"
            )


# =====================================================================
# 19. التصدير
# =====================================================================

__all__ = [
    "TimeUtils",
    "TextUtils",

    "RateLimiter",
    "RATE_LIMITER",

    "MetricsCollector",
    "METRICS",

    "AutoReplyCache",

    "TranslationManager",
    "get_text",

    "UserState",
    "StateManager",

    "CB",
    "KeyboardFactory",

    "get_banned_words_cached",
    "invalidate_banned_words_cache",
    "get_min_publish_interval",

    "is_authorized_in_group",
    "invalidate_auth_cache",
    "check_bot_permissions",
    "is_bot_admin",

    "safe_send",
    "get_ram_usage",

    "apply_penalty",

    "export_auto_replies",
    "import_auto_replies",
    "fetch_json_from_url",

    "load_replies_from_file",
    "get_reply_from_file",
    "reload_replies_from_file",

    "BackgroundTasks",

    "setup_webhook",
    "webhook_handler",
    "cleanup_webhook",

    "ErrorHandler",

    "get_security_settings_cached",
    "invalidate_security_cache",

    "get_auto_reply_settings_cached",
    "invalidate_auto_reply_cache",

    "_auto_reply_cache",
    "_increment_usage_async",
    "_flush_usage_updates",
    "flush_usage_periodically",
]
