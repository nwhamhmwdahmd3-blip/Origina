#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
utils.py - الأدوات المساعدة للبوت
"""

import asyncio
import os
import re
import json
import time
import html
import shutil
import logging
import random
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple, Any, Union
from enum import Enum, auto
from collections import OrderedDict, deque
from abc import ABC, abstractmethod

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions, Update
from telegram.error import BadRequest
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

METRICS = MetricsCollector()


# =====================================================================
# 5. كاش الصلاحيات
# =====================================================================

_auth_cache = TTLCache(maxsize=CONFIG.AUTH_CACHE_SIZE, ttl=CONFIG.AUTH_CACHE_TTL)
_auth_cache_time = {}


def invalidate_auth_cache(chat_id: int = None, user_id: int = None) -> None:
    try:
        if chat_id and user_id:
            _auth_cache.pop(f"auth_{chat_id}_{user_id}", None)
            _auth_cache_time.pop((chat_id, user_id), None)
        elif chat_id:
            for k in list(_auth_cache.keys()):
                if k.startswith(f"auth_{chat_id}_"):
                    _auth_cache.pop(k, None)
        else:
            _auth_cache.clear()
            _auth_cache_time.clear()
    except:
        pass


# =====================================================================
# 6. دوال الصلاحيات
# =====================================================================

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

    _auth_cache[cache_key] = authorized
    return authorized


async def check_bot_permissions(bot, chat_id: int) -> dict:
    try:
        me = await bot.get_chat_member(chat_id, bot.id)
        if me.status not in ['administrator', 'creator']:
            return {'can_act': False, 'reason': 'البوت ليس مشرفاً'}
        can_delete = getattr(me, 'can_delete_messages', False)
        can_ban = getattr(me, 'can_restrict_members', False)
        if not can_delete or not can_ban:
            return {'can_act': False, 'reason': 'صلاحيات ناقصة (حذف/تقييد)'}
        return {'can_act': True, 'reason': ''}
    except Exception as e:
        return {'can_act': False, 'reason': str(e)[:50]}


async def check_bot_admin_permissions(bot, chat_id: int) -> dict:
    """فحص صلاحيات البوت الإدارية"""
    return await check_bot_permissions(bot, chat_id)


# =====================================================================
# 7. إرسال آمن
# =====================================================================

async def safe_send(bot, chat_id: int, text: str, reply_markup=None, **kwargs):
    if not text:
        return
    await RATE_LIMITER.acquire()
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


async def safe_send_markdown(bot, chat_id: int, text: str, reply_markup=None):
    """إرسال مع دعم Markdown"""
    try:
        return await bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown', reply_markup=reply_markup)
    except:
        return await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


# =====================================================================
# 8. نظام العقوبات
# =====================================================================

class PenaltyStrategy(ABC):
    @abstractmethod
    async def apply(self, bot, chat_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        pass

class BanPenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id, user_id, **kwargs):
        if user_id == bot.id:
            return False, "لا يمكن حظر البوت"
        try:
            await bot.ban_chat_member(chat_id, user_id)
            return True, "✅ تم الحظر"
        except Exception as e:
            return False, str(e)[:100]

class MutePenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id, user_id, **kwargs):
        duration = kwargs.get('duration', 60)
        try:
            await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False))
            return True, f"✅ تم الكتم {duration} دقيقة"
        except Exception as e:
            return False, str(e)[:100]

class KickPenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id, user_id, **kwargs):
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
            return True, "✅ تم الطرد"
        except Exception as e:
            return False, str(e)[:100]

class WarnPenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id, user_id, **kwargs):
        row = await DB.fetchone("SELECT warnings FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        w = (row[0] if row else 0) + 1
        await DB.execute("INSERT OR REPLACE INTO user_warnings VALUES (?,?,?)", (user_id, chat_id, w))
        return True, f"⚠️ تحذير {w}"

class UnbanPenalty(PenaltyStrategy):
    async def apply(self, bot, chat_id, user_id, **kwargs):
        try:
            await bot.unban_chat_member(chat_id, user_id)
            return True, "✅ تم إلغاء الحظر"
        except Exception as e:
            return False, str(e)[:100]

class PenaltyFactory:
    @staticmethod
    def get_strategy(penalty_type: str):
        strategies = {
            'ban': BanPenalty(), 'mute': MutePenalty(), 'kick': KickPenalty(),
            'warn': WarnPenalty(), 'unban': UnbanPenalty()
        }
        return strategies.get(penalty_type, WarnPenalty())


async def apply_penalty(bot, chat_id: int, user_id: int, penalty: str, duration: int = 0, reason: str = "", moderator: int = None) -> Tuple[bool, str]:
    if user_id == CONFIG.PRIMARY_OWNER_ID:
        return False, "لا يمكن معاملة المالك"
    if user_id == bot.id:
        return False, "لا يمكن معاملة البوت"
    if await is_authorized_in_group(bot, chat_id, user_id):
        return False, "لا يمكن معاملة مشرف"
    strategy = PenaltyFactory.get_strategy(penalty)
    return await strategy.apply(bot, chat_id, user_id, duration=duration)


# =====================================================================
# 9. إدارة الحالات
# =====================================================================

class UserState(Enum):
    NONE = auto()
    ADDING_POSTS = auto()
    WAIT_CHANNEL = auto()
    WAIT_BROADCAST = auto()
    WAIT_AUTO_KEY = auto()
    WAIT_AUTO_REPLY = auto()
    WAIT_AUTO_DEL = auto()
    WAIT_GLOBAL_BAN = auto()
    WAIT_REM_GLOBAL_BAN = auto()
    WAIT_GROUP_BAN = auto()
    WAIT_REM_GROUP_BAN = auto()
    SUPPORT_MODE = auto()

class StateManager:
    _states = {}
    _timestamps = {}
    _timeout = 300

    @classmethod
    def get(cls, user_id: int) -> UserState:
        if user_id in cls._timestamps:
            if time.time() - cls._timestamps[user_id] > cls._timeout:
                cls.clear(user_id)
        return cls._states.get(user_id, UserState.NONE)

    @classmethod
    def set(cls, user_id: int, state: UserState):
        cls._states[user_id] = state
        cls._timestamps[user_id] = time.time()

    @classmethod
    def clear(cls, user_id: int):
        cls._states.pop(user_id, None)
        cls._timestamps.pop(user_id, None)


# =====================================================================
# 10. تعريفات الأزرار
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
    POST_ADD = "post_add"
    POST_PUB = "post_pub"
    POST_LIST = "post_list"
    POST_REC = "post_rec"
    GROUPS = "groups"
    TOGGLE_AUTO = "toggle_auto"
    TOGGLE_REC = "toggle_rec"
    PLANS = "plans"
    TRIAL = "trial"
    SUBSCRIBE = "subscribe"
    SUPPORT = "support"
    DEVELOPER = "developer"
    ADMIN = "admin"
    ADMIN_USERS = "admin_users"
    ADMIN_BROADCAST = "admin_broadcast"
    ADMIN_BACKUP = "admin_backup"
    ADMIN_BANNED_WORDS = "admin_banned_words"
    ADMIN_ADD_BANNED = "admin_add_banned"
    ADMIN_REM_BANNED = "admin_rem_banned"


# =====================================================================
# 11. مصنع الكيبوردات
# =====================================================================

class KeyboardFactory:
    _config = None
    _config_path = "buttons_config.json"

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
        return config.get("menus", {}).get(menu_name, {}).get("rows", [])

    @classmethod
    def build(cls, menu_name: str, chat_id: int = None) -> InlineKeyboardMarkup:
        rows = cls.get_menu(menu_name)
        keyboard = []
        for row in rows:
            btn_row = []
            for item in row:
                if item.endswith("_url"):
                    key = item.replace("_url", "")
                    text = cls.get_text(key)
                    btn_row.append(InlineKeyboardButton(text, url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup"))
                else:
                    text = cls.get_text(item)
                    callback = item
                    if chat_id:
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
            "━━━━━━━━━━━━━━━━━━━━",
            f"🔗 الروابط: {st(settings.get('delete_links', False))}",
            f"👤 المعرفات: {st(settings.get('mentions', False))}",
            f"🎬 فيديو: {st(settings.get('delete_videos', False))}",
            f"🎵 موسيقى: {st(settings.get('delete_audio', False))}",
            f"🎞️ متحرك: {st(settings.get('delete_animation', False))}",
            f"🛠️ خدمة: {st(settings.get('delete_service', False))}",
            f"📄 ملفات: {st(settings.get('delete_documents', False))}",
            f"🖼️ ملصقات: {st(settings.get('delete_stickers', False))}",
            f"📨 مُعاد: {st(settings.get('delete_forwarded', False))}",
            f"🎯 ترحيب: {st(settings.get('welcome_enabled', False))}",
            f"👋 وداع: {st(settings.get('goodbye_enabled', False))}",
            f"🌊 فيضان: {st(settings.get('antiflood_enabled', False))}",
            "━━━━━━━━━━━━━━━━━━━━"
        ]
        return "\n".join(lines)


# =====================================================================
# 12. الترجمات
# =====================================================================

class TranslationManager:
    _translations = {}
    _locales_dir = "locales"
    _default_lang = "ar"

    @classmethod
    def load_translation(cls, lang: str) -> Dict:
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
        if template is None:
            template = key
        try:
            return template.format(**kwargs)
        except:
            return template

    @classmethod
    def get_available_languages(cls) -> Dict[str, str]:
        languages = {"ar": "العربية 🇸🇦", "en": "English 🇬🇧"}
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
# 13. الردود من ملف
# =====================================================================

def load_replies_from_file() -> dict:
    try:
        from replies import REPLIES
        return REPLIES
    except ImportError:
        return {}
    except Exception:
        return {}

_REPLIES_FROM_FILE = load_replies_from_file()

def get_reply_from_file(keyword: str) -> Optional[str]:
    if not _REPLIES_FROM_FILE or not keyword:
        return None
    keyword = keyword.lower().strip()
    if keyword in _REPLIES_FROM_FILE:
        return random.choice(_REPLIES_FROM_FILE[keyword])
    for key, replies in _REPLIES_FROM_FILE.items():
        if key in keyword or keyword in key:
            return random.choice(replies)
    return None


# =====================================================================
# 14. استيراد/تصدير الردود
# =====================================================================

async def export_auto_replies(chat_id: int, file_path: str = None) -> int:
    rows = await DB.fetchall("SELECT keyword, reply FROM auto_replies WHERE chat_id=?", (chat_id,))
    if not rows:
        return 0
    data = [dict(r) for r in rows]
    if file_path is None:
        file_path = f"auto_replies_{chat_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(data)

async def import_auto_replies(chat_id: int, file_path_or_data, overwrite: bool = False) -> int:
    if isinstance(file_path_or_data, str):
        with open(file_path_or_data, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = file_path_or_data
    count = 0
    for item in data:
        keyword = item.get('keyword', '').strip().lower()
        reply = item.get('reply', '').strip()
        if keyword and reply:
            if overwrite:
                await DB.execute("DELETE FROM auto_replies WHERE chat_id=? AND keyword=?", (chat_id, keyword))
            await DB.add_auto_reply(chat_id, keyword, reply)
            count += 1
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
# 15. المهام الخلفية
# =====================================================================

class BackgroundTasks:
    @staticmethod
    async def auto_publish(bot) -> None:
        await asyncio.sleep(10)
        while True:
            try:
                channels = await DB.fetchall("""
                    SELECT uc.id, uc.channel_id, uc.user_id FROM user_channels uc
                    JOIN users u ON uc.user_id = u.user_id
                    WHERE uc.banned = 0 AND u.banned = 0 AND u.auto_publish = 1
                    AND EXISTS (SELECT 1 FROM posts p WHERE p.channel_db_id = uc.id AND p.published = 0)
                    LIMIT 20
                """)
                for ch in channels:
                    if not await DB.has_active_subscription(ch['user_id']):
                        continue
                    post = await DB.get_next_post(ch['id'])
                    if post:
                        try:
                            await bot.send_message(ch['channel_id'], post['text'] or ".")
                            await DB.mark_post_published(post['id'])
                        except:
                            await DB.increment_post_fail(post['id'])
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Auto publish: {e}")
                await asyncio.sleep(60)

    @staticmethod
    async def auto_backup() -> None:
        while True:
            await asyncio.sleep(86400)
            try:
                backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2(PATHS.DB, backup_file)
            except:
                pass

    @staticmethod
    async def reminders(bot) -> None:
        while True:
            await asyncio.sleep(3600)
            try:
                users = await DB.fetchall("SELECT user_id FROM users WHERE subscription_end IS NOT NULL")
                for u in users:
                    try:
                        await bot.send_message(u['user_id'], "⚠️ اشتراكك سينتهي قريباً")
                    except:
                        pass
            except:
                pass

    @staticmethod
    async def heartbeat(bot) -> None:
        while True:
            await asyncio.sleep(CONFIG.HEARTBEAT_INTERVAL)
            try:
                await bot.send_message(CONFIG.PRIMARY_OWNER_ID, "💓 البوت يعمل")
            except:
                pass

    @staticmethod
    async def flush_usage_periodically() -> None:
        while True:
            await asyncio.sleep(60)

    @staticmethod
    async def expire_subscriptions() -> None:
        while True:
            await asyncio.sleep(3600)
            try:
                await DB.expire_expired_subscriptions()
            except:
                pass

    @staticmethod
    async def sync_admins_periodically(bot) -> None:
        await asyncio.sleep(60)
        while True:
            try:
                groups = await DB.fetchall("SELECT chat_id FROM bot_groups WHERE banned=0")
                for g in groups:
                    chat_id = g['chat_id']
                    try:
                        admins = await bot.get_chat_administrators(chat_id)
                        admin_ids = [a.user.id for a in admins if a.user and not a.user.is_bot]
                        await DB.sync_group_admins(chat_id, admin_ids)
                    except:
                        pass
            except:
                pass
            await asyncio.sleep(3600)


# =====================================================================
# 16. خادم الويب
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
    try:
        data = await request.json()
        if _webhook_app is None:
            return web.Response(status=500, text="Error")
        await _webhook_app.process_update(Update.de_json(data, _webhook_app.bot))
        return web.Response(status=200, text="OK")
    except Exception as e:
        return web.Response(status=500, text="ERROR")


# =====================================================================
# 17. معالج الأخطاء
# =====================================================================

class ErrorHandler:
    @staticmethod
    async def handle_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            logger.error(f"Error: {context.error}", exc_info=True)
        except:
            pass


# =====================================================================
# 18. دوال قاعدة البيانات المساعدة
# =====================================================================

async def db_register_group(chat_id: int, chat_name: str, user_id: int, username: str = None) -> None:
    await DB.register_group(chat_id, chat_name, user_id, username)

async def db_sync_group_admins(chat_id: int, bot, user_id: int) -> int:
    try:
        admins = await bot.get_chat_administrators(chat_id)
        admin_ids = [a.user.id for a in admins if a.user and not a.user.is_bot]
        return await DB.sync_group_admins(chat_id, admin_ids)
    except:
        return 0

async def db_add_hidden_admin(chat_id: int, admin_id: int, added_by: int) -> None:
    await DB.execute("INSERT OR IGNORE INTO hidden_admins VALUES (?,?,?,?)", (chat_id, admin_id, added_by, TimeUtils.utc_iso()))

async def db_add_user_group_link(user_id: int, chat_id: int) -> None:
    await DB.execute("INSERT OR IGNORE INTO user_groups_link VALUES (?,?)", (user_id, chat_id))

async def db_register_hidden_owner_group(chat_id: int, user_id: int) -> None:
    await DB.execute("INSERT OR REPLACE INTO hidden_owner_groups VALUES (?,?,0)", (chat_id, user_id))

async def db_is_hidden_admin(chat_id: int, user_id: int) -> bool:
    row = await DB.fetchone("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, user_id))
    return row is not None


# =====================================================================
# 19. أدوات إضافية
# =====================================================================

def get_ram_usage() -> dict:
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {'total': round(mem.total / (1024**3), 1), 'used': round(mem.used / (1024**3), 1), 'percent': mem.percent}
    except:
        return {'total': 0, 'used': 0, 'percent': 0}

_auto_reply_cache = None
# ========== الكاش والاستخدام ==========

_auto_reply_cache = TTLCache(maxsize=300, ttl=60)

_usage_updates = {}

async def _increment_usage_async(chat_id: int, keyword: str):
    key = (chat_id, keyword.lower())
    _usage_updates[key] = _usage_updates.get(key, 0) + 1

