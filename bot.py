#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ريلاكس مانيجر - بوت متكامل لإدارة القنوات والمجموعات
الإصدار: 22.2.0 - النسخة النهائية الكاملة
المطور: @RelaxMgr
"""

import sys, os, secrets, re, shutil, logging, traceback, random, asyncio, gc, sqlite3, json
import time as time_module
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict, OrderedDict
from typing import Optional, List, Dict, Tuple, Any, Union, Callable, Awaitable
from enum import Enum, auto
import gzip, tempfile, html

# ===================================================================
# 1. تثبيت الحزم تلقائياً
# ===================================================================
def ensure_package(package_name: str, import_name: str = None) -> bool:
    if import_name is None: import_name = package_name
    try:
        __import__(import_name)
        return True
    except:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", package_name], capture_output=True, text=True)
            __import__(import_name)
            return True
        except Exception as e:
            print(f"⚠️ لا يمكن تثبيت {package_name}: {e}")
            return False

REQUIRED = [
    ("python-dotenv", "dotenv"), ("cachetools", "cachetools"), ("psutil", "psutil"),
    ("nest-asyncio", "nest_asyncio"), ("aiosqlite", "aiosqlite"),
    ("cryptography", "cryptography"), ("aiohttp", "aiohttp"), ("httpx", "httpx"),
    ("python-telegram-bot", "telegram"),
]
for pkg, imp in REQUIRED:
    ensure_package(pkg, imp)

# ===================================================================
# 2. استيراد المكتبات
# ===================================================================
import nest_asyncio; nest_asyncio.apply()
import aiosqlite
from dotenv import load_dotenv

load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember, BotCommand, LabeledPrice, ChatPermissions, ChatMemberUpdated, ChatJoinRequest
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler, ChatMemberHandler, ChatJoinRequestHandler
from telegram.error import TimedOut, NetworkError, BadRequest, Forbidden, Conflict
from telegram.request import HTTPXRequest
from cryptography.fernet import Fernet
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
POLL_INTERVAL = 1.0
SCHEDULED_POSTS_SLEEP = 10
REMINDERS_SLEEP = 3600
AUTO_BACKUP_SLEEP = 86400
CLEANUP_SLEEP = 3600
MAX_CHANNELS_PER_CYCLE = 20
PUBLISH_RETRY_DELAY = 300
MAX_UNPUBLISHED_POSTS = 1000
DB_TIMEOUT = 30
ANONYMOUS_ADMIN_ID = int(os.getenv("ANONYMOUS_ADMIN_ID", "1087968824"))

if not TOKEN or PRIMARY_OWNER_ID == 0:
    print("❌ يجب تعيين BOT_TOKEN و MAIN_ADMIN_ID في .env")
    sys.exit(1)

# ===================================================================
# 4. إعداد المسارات
# ===================================================================
BASE_PATH = Path(__file__).parent.resolve()
DATA_PATH = BASE_PATH / "data"; DATA_PATH.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_PATH / "bot_data.db"
BACKUP_DIR = BASE_PATH / "backups"; BACKUP_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = BASE_PATH / "logs"; LOG_PATH.mkdir(parents=True, exist_ok=True)
BANNED_WORDS_FILE = BASE_PATH / "banned_words.txt"

# ===================================================================
# 5. نظام السجلات
# ===================================================================
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO,
    handlers=[logging.FileHandler(LOG_PATH / "bot.log", encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

def log_error(error: Exception, context: dict = None) -> str:
    error_id = secrets.token_hex(4)
    logger.error(f"[{error_id}] {type(error).__name__}: {str(error)[:200]}")
    return error_id

# ===================================================================
# 6. دوال مساعدة
# ===================================================================
def utc_now(): return datetime.now(timezone.utc).replace(tzinfo=None)
def mecca_now(): return utc_now() + timedelta(hours=3)
def utc_now_iso(): return utc_now().isoformat()
def mecca_now_iso(): return mecca_now().isoformat()
def mecca_to_utc(dt): return dt - timedelta(hours=3) if dt else None
def utc_to_mecca(dt): return dt + timedelta(hours=3) if dt else None

def contains_link(text):
    return bool(re.search(r'https?://\S+|www\.\S+|t\.me/\S+', text, re.IGNORECASE))

def contains_mention(text):
    return bool(re.search(r'@\w+', text))

def sanitize_text(text: str, max_length: int = 4096) -> str:
    if not text: return ""
    return text[:max_length]

def escape_markdown_v2(text: str) -> str:
    if not text: return ""
    special_chars = r'_*[]()~`>#+\-=|{}.!\\'
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', text)

def get_ram_usage():
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {'total': round(mem.total/(1024**3),1), 'used': round(mem.used/(1024**3),1), 'percent': mem.percent}
    except: return {'total':0, 'used':0, 'percent':0}

def load_banned_words_from_file(file_path: Path) -> List[str]:
    if not file_path.exists():
        file_path.write_text("# كلمات محظورة\n", encoding='utf-8')
        return []
    return [line.strip().lower() for line in file_path.read_text(encoding='utf-8').splitlines() if line.strip() and not line.startswith('#') and len(line.strip()) >= 2]

async def is_user_bot(bot, user_id: int) -> bool:
    try: return (await bot.get_chat(user_id)).is_bot
    except: return False

# ===================================================================
# 7. نظام التشفير
# ===================================================================
def get_encryption_key() -> bytes:
    key_file = DATA_PATH / ".db_key"
    if key_file.exists():
        return key_file.read_bytes()
    key = Fernet.generate_key()
    key_file.write_bytes(key)
    return key

ENCRYPTION_KEY = get_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

def get_backup_key() -> bytes:
    f = DATA_PATH / ".backup_key"
    if f.exists(): return f.read_bytes()
    k = Fernet.generate_key(); f.write_bytes(k); return k

BACKUP_CIPHER = Fernet(get_backup_key())

def compress_backup(data: bytes) -> bytes: return gzip.compress(data)
def decompress_backup(data: bytes) -> bytes: return gzip.decompress(data)

# ===================================================================
# 8. الكاش
# ===================================================================
try:
    from cachetools import TTLCache
    CACHETOOLS_AVAILABLE = True
    _auth_cache = TTLCache(maxsize=1000, ttl=30)
    _security_cache = TTLCache(maxsize=500, ttl=30)
except:
    CACHETOOLS_AVAILABLE = False
    _auth_cache = {}; _security_cache = {}

_flood_cache = OrderedDict()
_flood_cache_time = {'last_cleanup': 0}
BANNED_PATTERNS = []
_AUTH_CACHE_TTL = 300
_FLOOD_CACHE_MAX_SIZE = 10000
_ALLOWED_SECURITY_COLUMNS = {
    'delete_links', 'links', 'mentions', 'slow_mode', 'slow_mode_seconds',
    'welcome_enabled', 'welcome_text', 'goodbye_enabled', 'goodbye_text',
    'delete_banned_words', 'auto_penalty', 'auto_mute_duration',
    'delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
    'delete_documents', 'delete_stickers', 'delete_forwarded', 'delete_polls',
    'delete_games', 'delete_voice', 'delete_video_note',
    'delete_penalty', 'delete_penalty_duration',
    'antiflood_enabled', 'antiflood_messages', 'antiflood_seconds', 'antiflood_penalty',
    'max_warnings', 'warn_penalty', 'max_message_length',
    'night_mode_enabled', 'night_mode_start', 'night_mode_end', 'night_mode_action'
}

# ===================================================================
# 9. دوال الإرسال
# ===================================================================
async def safe_send_markdown(bot, chat_id: int, text: str, reply_markup=None, **kwargs):
    if not text: return None
    try:
        return await bot.send_message(chat_id=chat_id, text=text[:4096], reply_markup=reply_markup, **kwargs)
    except: return None

async def safe_edit_markdown(query, text: str, reply_markup=None, **kwargs):
    if not query or not query.message: return None
    try:
        return await query.edit_message_text(text=text[:4096], reply_markup=reply_markup, **kwargs)
    except: return None

# ===================================================================
# 10. قاعدة البيانات
# ===================================================================
class DatabasePool:
    def __init__(self): self._pool = None; self._lock = asyncio.Lock()
    
    async def initialize(self):
        async with self._lock:
            if self._pool: return
            self._pool = await aiosqlite.connect(str(DB_PATH), timeout=DB_TIMEOUT)
            await self._pool.execute("PRAGMA journal_mode=WAL")
            await self._pool.execute("PRAGMA synchronous=NORMAL")
            await self._pool.execute("PRAGMA foreign_keys=ON")
            self._pool.row_factory = aiosqlite.Row
    
    async def get_connection(self):
        if not self._pool: await self.initialize()
        return self._pool
    
    async def close(self):
        if self._pool: await self._pool.close(); self._pool = None

db_pool = DatabasePool()

async def execute_db(func: Callable):
    conn = await db_pool.get_connection()
    return await func(conn)

# ===================================================================
# 11. جداول قاعدة البيانات
# ===================================================================
async def init_db():
    async def _init(conn):
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        
        # المستخدمين
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
                language TEXT DEFAULT 'ar', auto_publish INTEGER DEFAULT 1,
                auto_recycle INTEGER DEFAULT 1, banned INTEGER DEFAULT 0,
                trial_used INTEGER DEFAULT 0, subscription_end TEXT,
                referral_code TEXT UNIQUE, created_at TEXT, updated_at TEXT,
                active_channel INTEGER, level INTEGER DEFAULT 1,
                points INTEGER DEFAULT 0, referred_by INTEGER,
                auto_reply_enabled INTEGER DEFAULT 1
            )
        """)
        
        # القنوات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                channel_id TEXT, channel_name TEXT, banned INTEGER DEFAULT 0,
                created_at TEXT, FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # المنشورات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, channel_db_id INTEGER,
                text TEXT, media_type TEXT, media_file_id TEXT,
                published INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0,
                created_at TEXT, published_at TEXT,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
            )
        """)
        
        # الجدولة
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schedule (
                channel_db_id INTEGER PRIMARY KEY,
                schedule_type TEXT DEFAULT 'interval_minutes',
                interval_minutes INTEGER DEFAULT 12, interval_hours INTEGER DEFAULT 0,
                interval_days INTEGER DEFAULT 0, days_of_week TEXT DEFAULT '[]',
                specific_dates TEXT DEFAULT '[]', publish_time TEXT DEFAULT '00:00',
                cron_expression TEXT, next_publish_date TEXT,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
            )
        """)
        
        # المجموعات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_groups (
                chat_id INTEGER PRIMARY KEY, chat_name TEXT, username TEXT,
                added_by INTEGER, added_at TEXT, banned INTEGER DEFAULT 0
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_admins (
                chat_id INTEGER, user_id INTEGER, PRIMARY KEY (chat_id, user_id)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_owner_groups (
                chat_id INTEGER PRIMARY KEY, owner_id INTEGER
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_admins (
                chat_id INTEGER, admin_id INTEGER, added_by INTEGER, added_at TEXT,
                PRIMARY KEY (chat_id, admin_id)
            )
        """)
        
        # الأمان
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_security (
                chat_id INTEGER PRIMARY KEY, delete_links INTEGER DEFAULT 0,
                mentions INTEGER DEFAULT 0, slow_mode INTEGER DEFAULT 0,
                slow_mode_seconds INTEGER DEFAULT 5,
                welcome_enabled INTEGER DEFAULT 0,
                welcome_text TEXT DEFAULT 'مرحباً {user} في {chat} 🤍',
                goodbye_enabled INTEGER DEFAULT 0,
                goodbye_text TEXT DEFAULT 'وداعاً {user} 👋',
                delete_banned_words INTEGER DEFAULT 0,
                auto_penalty TEXT DEFAULT 'none', auto_mute_duration INTEGER DEFAULT 60,
                delete_videos INTEGER DEFAULT 0, delete_audio INTEGER DEFAULT 0,
                delete_animation INTEGER DEFAULT 0, delete_service INTEGER DEFAULT 0,
                delete_documents INTEGER DEFAULT 0, delete_stickers INTEGER DEFAULT 0,
                delete_forwarded INTEGER DEFAULT 0, delete_polls INTEGER DEFAULT 0,
                delete_games INTEGER DEFAULT 0, delete_voice INTEGER DEFAULT 0,
                delete_video_note INTEGER DEFAULT 0,
                delete_penalty TEXT DEFAULT 'none', delete_penalty_duration INTEGER DEFAULT 0,
                antiflood_enabled INTEGER DEFAULT 0, antiflood_messages INTEGER DEFAULT 5,
                antiflood_seconds INTEGER DEFAULT 10, antiflood_penalty TEXT DEFAULT 'mute',
                max_warnings INTEGER DEFAULT 3, warn_penalty TEXT DEFAULT 'ban',
                max_message_length INTEGER DEFAULT 0,
                night_mode_enabled INTEGER DEFAULT 0,
                night_mode_start TEXT DEFAULT '23:00', night_mode_end TEXT DEFAULT '06:00',
                night_mode_action TEXT DEFAULT 'mute'
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_locks (
                chat_id INTEGER PRIMARY KEY, locked INTEGER DEFAULT 0,
                locked_at TEXT, locked_by INTEGER
            )
        """)
        
        # الكلمات المحظورة
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS banned_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT, word TEXT NOT NULL,
                chat_id INTEGER DEFAULT -1, added_by INTEGER, added_at TEXT,
                UNIQUE(word, chat_id)
            )
        """)
        
        # الإحالات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER, referred_id INTEGER, created_at TEXT,
                UNIQUE(referrer_id, referred_id)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_rewards (
                user_id INTEGER PRIMARY KEY, referral_count INTEGER DEFAULT 0,
                total_reward_days INTEGER DEFAULT 0, claimed_reward_days INTEGER DEFAULT 0
            )
        """)
        
        # التذاكر
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                username TEXT, message TEXT, ticket_number INTEGER,
                status TEXT DEFAULT 'pending', created_at TEXT, replied INTEGER DEFAULT 0
            )
        """)
        
        # التذكيرات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_reminder_settings (
                user_id INTEGER PRIMARY KEY, subscription_reminder INTEGER DEFAULT 1,
                daily_stats_reminder INTEGER DEFAULT 0, weekly_report INTEGER DEFAULT 1,
                reminder_days_before INTEGER DEFAULT 3, last_reminder_sent TEXT,
                notification_lang TEXT DEFAULT 'ar'
            )
        """)
        
        # الترجمة
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_translation (
                user_id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'off'
            )
        """)
        
        # المسابقات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id INTEGER,
                title TEXT, description TEXT, prize TEXT, end_date TEXT,
                status TEXT DEFAULT 'active', winner_id INTEGER, created_at TEXT,
                contest_type TEXT DEFAULT 'raffle'
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contest_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                contest_id INTEGER, answer TEXT, joined_at TEXT,
                UNIQUE(user_id, contest_id)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contest_winners (
                id INTEGER PRIMARY KEY AUTOINCREMENT, contest_id INTEGER,
                winner_id INTEGER, announced_at TEXT
            )
        """)
        
        # الردود التلقائية
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_replies (
                chat_id INTEGER, keyword TEXT, reply TEXT, created_at TEXT,
                is_active INTEGER DEFAULT 1, PRIMARY KEY (chat_id, keyword)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_reply_settings (
                chat_id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 0,
                only_admins INTEGER DEFAULT 0, ignore_bots INTEGER DEFAULT 1
            )
        """)
        
        # التعلم الذكي
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                chat_id INTEGER, text TEXT, sentiment TEXT, score REAL, created_at TEXT
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS response_learning (
                id INTEGER PRIMARY KEY AUTOINCREMENT, pattern_key TEXT UNIQUE,
                success_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0,
                score REAL DEFAULT 0, last_used TEXT, best_response TEXT
            )
        """)
        
        # الإعدادات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT
            )
        """)
        await conn.execute("INSERT OR IGNORE INTO settings VALUES ('publish_interval', '720')")
        await conn.execute("INSERT OR IGNORE INTO settings VALUES ('auto_backup', '1')")
        await conn.execute("INSERT OR IGNORE INTO settings VALUES ('last_ticket_number', '0')")
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TEXT
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS last_publish (
                channel_db_id INTEGER PRIMARY KEY, last_publish_time TEXT
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_messages (
                user_id INTEGER, chat_id INTEGER, message_time TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER,
                text TEXT, publish_time TEXT, fail_count INTEGER DEFAULT 0
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_rules (
                chat_id INTEGER PRIMARY KEY, rules_text TEXT,
                updated_by INTEGER, updated_at TEXT
            )
        """)
        
        await conn.commit()
        logger.info("✅ تم إنشاء جميع الجداول")
    
    await execute_db(_init)

# ===================================================================
# 12. دوال قاعدة البيانات الأساسية
# ===================================================================
async def db_register_user(user_id: int) -> bool:
    async def _reg(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if await cur.fetchone():
            await conn.execute("UPDATE users SET updated_at=? WHERE user_id=?", (utc_now_iso(), user_id))
            await conn.commit()
            return False
        code = secrets.token_urlsafe(6)
        await conn.execute("INSERT INTO users (user_id, referral_code, created_at, updated_at) VALUES (?,?,?,?)", (user_id, code, utc_now_iso(), utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_reg)

async def db_has_active_subscription(user_id: int) -> bool:
    async def _chk(conn):
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try: return datetime.fromisoformat(row[0]) > utc_now()
            except: pass
        return False
    return await execute_db(_chk)

async def db_has_used_trial(user_id: int) -> bool:
    async def _chk(conn):
        cur = await conn.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_chk)

async def db_activate_trial(user_id: int) -> int:
    async def _act(conn):
        cur = await conn.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        if (await cur.fetchone())[0] == 1: return 0
        end = (utc_now() + timedelta(days=30)).isoformat()
        await conn.execute("UPDATE users SET trial_used=1, subscription_end=? WHERE user_id=?", (end, user_id))
        await conn.commit()
        return 30
    return await execute_db(_act)

async def db_activate_subscription(user_id: int, days: int):
    async def _act(conn):
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try:
                current = datetime.fromisoformat(row[0])
                new_end = (current if current > utc_now() else utc_now()) + timedelta(days=days)
            except: new_end = utc_now() + timedelta(days=days)
        else: new_end = utc_now() + timedelta(days=days)
        await conn.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (new_end.isoformat(), user_id))
        await conn.commit()
    return await execute_db(_act)

async def db_get_subscription_days_left(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try: return max(0, (datetime.fromisoformat(row[0]) - utc_now()).days)
            except: pass
        return 0
    return await execute_db(_get)

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

async def db_get_user_by_referral_code(code: str) -> Optional[int]:
    async def _g(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE referral_code=?", (code,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_g)

async def db_get_user_referral_code(user_id: int) -> str:
    async def _g(conn):
        cur = await conn.execute("SELECT referral_code FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else ""
    return await execute_db(_g)

async def db_update_user_cache(user_id: int, username: str, first_name: str):
    await execute_db(lambda c: c.execute("UPDATE users SET username=?, first_name=?, updated_at=? WHERE user_id=?", (username, first_name, utc_now_iso(), user_id)) or c.commit())

# ===================================================================
# 13. دوال القنوات والمنشورات
# ===================================================================
async def db_add_channel(user_id: int, channel_id: str, channel_name: str) -> int:
    async def _add(conn):
        cur = await conn.execute("SELECT id FROM user_channels WHERE user_id=? AND channel_id=?", (user_id, channel_id))
        if await cur.fetchone(): return None
        cur = await conn.execute("INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) VALUES (?,?,?,?) RETURNING id", (user_id, channel_id, channel_name, utc_now_iso()))
        row = await cur.fetchone()
        await conn.commit()
        return row[0] if row else None
    return await execute_db(_add)

async def db_get_channels(user_id: int):
    return await execute_db(lambda c: c.execute("SELECT id, channel_id, channel_name, banned FROM user_channels WHERE user_id=? ORDER BY id", (user_id,)) or c.fetchall())

async def db_get_channel_info(channel_db_id: int):
    return await execute_db(lambda c: c.execute("SELECT channel_id, channel_name FROM user_channels WHERE id=?", (channel_db_id,)) or c.fetchone())

async def db_delete_channel_by_id(user_id: int, channel_db_id: int) -> bool:
    async def _del(conn):
        await conn.execute("DELETE FROM user_channels WHERE id=? AND user_id=?", (channel_db_id, user_id))
        await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (channel_db_id,))
        await conn.execute("DELETE FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        await conn.execute("DELETE FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
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
            if r2 and r2[0] == 0: return row[0]
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

async def db_reset_posts_to_unpublished(channel_db_id: int, user_id: int = None) -> int:
    return await db_reset_all_posts_to_unpublished(channel_db_id)

async def db_get_user_posts_for_channel(channel_db_id: int, limit=15):
    return await execute_db(lambda c: c.execute("SELECT id, text, media_type FROM posts WHERE channel_db_id=? AND published=0 ORDER BY id LIMIT ?", (channel_db_id, limit)) or c.fetchall())

async def db_delete_single_post(post_id: int, user_id: int, channel_db_id: int) -> bool:
    async def _d(conn):
        cur = await conn.execute("SELECT 1 FROM user_channels WHERE id=? AND user_id=? AND banned=0", (channel_db_id, user_id))
        if not await cur.fetchone(): return False
        await conn.execute("DELETE FROM posts WHERE id=? AND channel_db_id=?", (post_id, channel_db_id))
        await conn.commit()
        return True
    return await execute_db(_d)

async def db_increment_fail_count(post_id: int):
    await execute_db(lambda c: c.execute("UPDATE posts SET fail_count=COALESCE(fail_count,0)+1 WHERE id=?", (post_id,)) or c.commit())

async def db_get_posts_count(channel_db_id: int) -> int:
    async def _c(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        return (await cur.fetchone())[0]
    return await execute_db(_c)

async def db_get_published_count(channel_db_id: int) -> int:
    async def _c(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=1", (channel_db_id,))
        return (await cur.fetchone())[0]
    return await execute_db(_c)

# ===================================================================
# 14. دوال المجموعات
# ===================================================================
async def db_register_group(chat_id: int, chat_name: str, added_by: int, username: str = None) -> bool:
    async def _reg(conn):
        cur = await conn.execute("SELECT chat_id, banned FROM bot_groups WHERE chat_id=?", (chat_id,))
        existing = await cur.fetchone()
        if existing:
            await conn.execute("UPDATE bot_groups SET chat_name=?, username=?, added_by=?, updated_at=? WHERE chat_id=?", (chat_name[:255], username[:100] if username else None, added_by, utc_now_iso(), chat_id))
            await conn.commit()
            return not existing[1]
        await conn.execute("INSERT INTO bot_groups (chat_id, chat_name, username, added_by, added_at) VALUES (?,?,?,?,?)", (chat_id, chat_name[:255], username[:100] if username else None, added_by, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_reg)

async def db_get_user_groups(user_id: int):
    async def _g(conn):
        result = []; seen = set()
        for table, col in [("hidden_owner_groups","owner_id"), ("hidden_admins","admin_id"), ("group_admins","user_id")]:
            cur = await conn.execute(f"SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned FROM bot_groups bg INNER JOIN {table} h ON bg.chat_id=h.chat_id WHERE h.{col}=?", (user_id,))
            for row in await cur.fetchall():
                if row[0] not in seen: seen.add(row[0]); result.append(row)
        return result
    return await execute_db(_g)

async def db_get_user_groups_count(user_id: int) -> int:
    return len(await db_get_user_groups(user_id))

async def db_sync_group_admins(chat_id: int, bot, owner_id: int = None) -> int:
    try:
        admins = await bot.get_chat_administrators(chat_id)
        ids = [a.user.id for a in admins]
        if not ids: return 0
        async def _upd(conn):
            await conn.execute("DELETE FROM group_admins WHERE chat_id=?", (chat_id,))
            await conn.executemany("INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?,?)", [(chat_id, uid) for uid in ids])
            await conn.commit()
            return len(ids)
        return await execute_db(_upd)
    except: return 0

# ===================================================================
# 15. دوال الأمان
# ===================================================================
async def check_bot_admin_permissions_group(bot, chat_id: int) -> dict:
    try:
        me = await bot.get_chat_member(chat_id, bot.id)
        if me.status not in ['administrator', 'creator']: return {'can_act': False, 'reason': 'البوت ليس مشرفاً'}
        perms = {'can_delete': getattr(me, 'can_delete_messages', False), 'can_ban': getattr(me, 'can_restrict_members', False)}
        if not perms['can_delete'] or not perms['can_ban']: return {'can_act': False, 'reason': 'ينقص البوت صلاحيات'}
        return {'can_act': True, 'reason': '', 'permissions': perms}
    except: return {'can_act': False, 'reason': 'خطأ في التحقق'}

async def check_bot_permissions(bot, channel_id: str) -> Tuple[bool, str]:
    try:
        chat = await bot.get_chat(channel_id)
        if chat.type != 'channel': return False, "ليست قناة"
        member = await bot.get_chat_member(chat.id, bot.id)
        if member.status not in ['administrator', 'creator']: return False, "البوت ليس مشرفاً"
        if not member.can_post_messages: return False, "لا يملك صلاحية النشر"
        return True, ""
    except: return False, "خطأ"

async def is_currently_admin_in_group(bot, chat_id: int, user_id: int) -> bool:
    try:
        if user_id == ANONYMOUS_ADMIN_ID: return len(await bot.get_chat_administrators(chat_id)) > 0
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except: return False

def invalidate_auth_cache(chat_id: int = None, user_id: int = None):
    try:
        if chat_id and user_id: _auth_cache.pop(f"auth_{chat_id}_{user_id}", None)
        elif chat_id:
            for k in list(_auth_cache.keys()):
                if k.startswith(f"auth_{chat_id}_"): del _auth_cache[k]
        else: _auth_cache.clear()
    except: pass

async def is_authorized_in_group(bot, chat_id: int, user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID: return True
    bp = await check_bot_admin_permissions_group(bot, chat_id)
    if not bp.get('can_act', False): return False
    cache_key = f"auth_{chat_id}_{user_id}"
    if CACHETOOLS_AVAILABLE and cache_key in _auth_cache:
        ct, val = _auth_cache[cache_key]
        if time_module.time() - ct < 60: return val
    authorized = False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']: authorized = True
        else:
            async def _chk(conn):
                for table, col in [("hidden_owner_groups","owner_id"), ("hidden_admins","admin_id"), ("group_admins","user_id")]:
                    cur = await conn.execute(f"SELECT 1 FROM {table} WHERE chat_id=? AND {col}=?", (chat_id, user_id))
                    if await cur.fetchone(): return True
                return False
            authorized = await execute_db(_chk)
    except:
        async def _chk(conn):
            for table, col in [("hidden_owner_groups","owner_id"), ("hidden_admins","admin_id"), ("group_admins","user_id")]:
                cur = await conn.execute(f"SELECT 1 FROM {table} WHERE chat_id=? AND {col}=?", (chat_id, user_id))
                if await cur.fetchone(): return True
            return False
        authorized = await execute_db(_chk)
    if CACHETOOLS_AVAILABLE: _auth_cache[cache_key] = (time_module.time(), authorized)
    return authorized

async def is_bot_admin(user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID: return True
    async def _chk(conn):
        cur = await conn.execute("SELECT 1 FROM bot_admins WHERE user_id=?", (user_id,))
        return await cur.fetchone() is not None
    return await execute_db(_chk)

async def db_get_security_settings(chat_id: int, force_refresh: bool = False) -> dict:
    defaults = {
        'delete_links': False, 'mentions': False, 'slow_mode': False, 'slow_mode_seconds': 5,
        'welcome_enabled': False, 'goodbye_enabled': False, 'delete_banned_words': False,
        'auto_penalty': 'none', 'auto_mute_duration': 60,
        'delete_videos': False, 'delete_audio': False, 'delete_animation': False,
        'delete_service': False, 'delete_documents': False, 'delete_stickers': False,
        'delete_forwarded': False, 'delete_polls': False, 'delete_games': False,
        'delete_voice': False, 'delete_video_note': False,
        'delete_penalty': 'none', 'delete_penalty_duration': 0,
        'antiflood_enabled': False, 'antiflood_messages': 5, 'antiflood_seconds': 10,
        'antiflood_penalty': 'mute', 'max_warnings': 3, 'warn_penalty': 'ban',
        'max_message_length': 0, 'night_mode_enabled': False,
        'night_mode_start': '23:00', 'night_mode_end': '06:00', 'night_mode_action': 'mute'
    }
    if not force_refresh and CACHETOOLS_AVAILABLE and chat_id in _security_cache:
        ct, val = _security_cache[chat_id]
        if time_module.time() - ct < _AUTH_CACHE_TTL: return val.copy()
    async def _g(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        if row:
            settings = {}
            for k in defaults:
                if hasattr(row, k):
                    v = getattr(row, k)
                    settings[k] = (v == 1) if isinstance(defaults[k], bool) else (v if v is not None else defaults[k])
                else: settings[k] = defaults[k]
            if CACHETOOLS_AVAILABLE: _security_cache[chat_id] = (time_module.time(), settings)
            return settings
        await conn.execute("INSERT INTO group_security (chat_id) VALUES (?)", (chat_id,))
        await conn.commit()
        if CACHETOOLS_AVAILABLE: _security_cache[chat_id] = (time_module.time(), defaults.copy())
        return defaults.copy()
    return await execute_db(_g)

async def db_set_security_settings(chat_id: int, **kwargs) -> bool:
    allowed_penalties = ['none', 'warn', 'mute', 'kick', 'ban']
    validated = {}
    for k, v in kwargs.items():
        if k not in _ALLOWED_SECURITY_COLUMNS: continue
        if k.endswith('_enabled') or k in ['delete_links', 'mentions', 'slow_mode', 'delete_banned_words',
            'welcome_enabled', 'goodbye_enabled', 'delete_videos', 'delete_audio', 'delete_animation',
            'delete_service', 'delete_documents', 'delete_stickers', 'delete_forwarded', 'delete_polls',
            'delete_games', 'delete_voice', 'delete_video_note', 'antiflood_enabled', 'night_mode_enabled']:
            validated[k] = 1 if v else 0
        elif k.endswith('_penalty') or k == 'auto_penalty': validated[k] = v if v in allowed_penalties else 'none'
        else:
            try: validated[k] = int(v) if v is not None else 0
            except: validated[k] = 0
    if not validated: return False
    async def _s(conn):
        cur = await conn.execute("SELECT 1 FROM group_security WHERE chat_id=?", (chat_id,))
        if not await cur.fetchone(): await conn.execute("INSERT INTO group_security (chat_id) VALUES (?)", (chat_id,))
        updates = [f"{k}=?" for k in validated]
        vals = list(validated.values()) + [chat_id]
        await conn.execute(f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id=?", vals)
        await conn.commit()
        return True
    result = await execute_db(_s)
    if CACHETOOLS_AVAILABLE: _security_cache.pop(chat_id, None)
    return result

async def is_chat_locked(chat_id: int) -> bool:
    async def _chk(conn):
        cur = await conn.execute("SELECT 1 FROM chat_locks WHERE chat_id=? AND locked=1", (chat_id,))
        return await cur.fetchone() is not None
    return await execute_db(_chk)

async def db_set_chat_lock(chat_id: int, locked: bool, locked_by: int = None) -> bool:
    async def _s(conn):
        if locked: await conn.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?,1,?,?)", (chat_id, utc_now_iso(), locked_by))
        else: await conn.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await conn.commit()
        return True
    return await execute_db(_s)

async def db_check_slow_mode(chat_id: int, user_id: int) -> bool:
    settings = await db_get_security_settings(chat_id)
    if not settings.get('slow_mode', False): return True
    sec = settings.get('slow_mode_seconds', 5)
    async def _chk(conn):
        cur = await conn.execute("SELECT message_time FROM user_messages WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        row = await cur.fetchone()
        now = utc_now()
        if row:
            try:
                if (now - datetime.fromisoformat(row[0])).total_seconds() < sec: return False
            except: pass
        await conn.execute("INSERT OR REPLACE INTO user_messages (user_id, chat_id, message_time) VALUES (?,?,?)", (user_id, chat_id, now.isoformat()))
        await conn.commit()
        return True
    return await execute_db(_chk)

async def db_add_banned_word(word: str, chat_id: int, added_by: int) -> bool:
    if not word or len(word) < 2: return False
    word = word.strip().lower()[:100]
    async def _add(conn):
        await conn.execute("INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?,?,?,?)", (word, chat_id, added_by, utc_now_iso()))
        await conn.commit()
        if chat_id == -1: await rebuild_banned_patterns()
        return True
    return await execute_db(_add)

async def db_remove_banned_word(word: str, chat_id: int) -> bool:
    async def _r(conn):
        await conn.execute("DELETE FROM banned_words WHERE word=? AND chat_id=?", (word.strip().lower(), chat_id))
        await conn.commit()
        if chat_id == -1: await rebuild_banned_patterns()
        return True
    return await execute_db(_r)

async def db_get_banned_words(chat_id: int):
    return await execute_db(lambda c: c.execute("SELECT word, added_by, added_at FROM banned_words WHERE chat_id=? OR chat_id=-1 ORDER BY word", (chat_id,)) or c.fetchall())

async def db_contains_banned_word(text: str, chat_id: int) -> Optional[str]:
    if not text: return None
    words = await db_get_banned_words(chat_id)
    tl = text.lower()
    for w, _, _ in words:
        if w in tl: return w
    return None

async def rebuild_banned_patterns():
    global BANNED_PATTERNS
    async def _get(conn):
        cur = await conn.execute("SELECT word FROM banned_words WHERE chat_id=-1")
        rows = await cur.fetchall()
        return [row[0] for row in rows]
    BANNED_PATTERNS = await execute_db(_get)

async def apply_penalty_with_duration(bot, chat_id: int, user_id: int, penalty: str, duration_minutes: int = 0, reason: str = "", moderator_id: int = None) -> Tuple[bool, str]:
    if user_id == PRIMARY_OWNER_ID: return False, "لا يمكن"
    try:
        if penalty == 'ban': await bot.ban_chat_member(chat_id, user_id)
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
                if wp == 'ban': await bot.ban_chat_member(chat_id, user_id)
                elif wp == 'mute': await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False))
        elif penalty == 'restrict':
            await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=True, can_send_media_messages=False))
        return True, f"✅ تم {penalty}"
    except Exception as e: return False, str(e)[:100]

async def delete_and_penalize(update: Update, context: ContextTypes.DEFAULT_TYPE, warning_message: str):
    if not update.message: return
    try: await update.message.delete()
    except: pass
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try: await safe_send_markdown(context.bot, chat_id, warning_message)
    except: pass
    settings = await db_get_security_settings(chat_id)
    penalty = settings.get('auto_penalty', 'none')
    if penalty != 'none': await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, settings.get('auto_mute_duration', 60))

async def db_check_antiflood(chat_id: int, user_id: int) -> bool:
    settings = await db_get_security_settings(chat_id)
    if not settings.get('antiflood_enabled', False): return False
    max_msgs = settings.get('antiflood_messages', 5)
    tw = settings.get('antiflood_seconds', 10)
    key = f"flood_{chat_id}_{user_id}"
    now = time_module.time()
    if key in _flood_cache:
        msgs = [t for t in _flood_cache.pop(key) if now - t < tw]
        msgs.append(now); _flood_cache[key] = msgs
        return len(msgs) > max_msgs
    _flood_cache[key] = [now]
    if len(_flood_cache) > _FLOOD_CACHE_MAX_SIZE:
        try: _flood_cache.popitem(last=False)
        except: pass
    return False

# ===================================================================
# 16. دوال الإحالات
# ===================================================================
async def db_add_referral(referrer_id: int, referred_id: int) -> bool:
    if referrer_id == referred_id: return False
    async def _add(conn):
        cur = await conn.execute("SELECT 1 FROM referrals WHERE referred_id=?", (referred_id,))
        if await cur.fetchone(): return False
        await conn.execute("INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?,?,?)", (referrer_id, referred_id, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_add)

async def db_auto_reward_referral(referrer_id: int, referred_id: int) -> int:
    async def _r(conn):
        await conn.execute("INSERT INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days) VALUES (?,1,3,0) ON CONFLICT(user_id) DO UPDATE SET referral_count=referral_count+1, total_reward_days=total_reward_days+3", (referrer_id,))
        await conn.commit()
        return 3
    return await execute_db(_r)

async def db_get_referral_stats(user_id: int) -> dict:
    async def _g(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,))
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT referral_count, total_reward_days, claimed_reward_days FROM referral_rewards WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row: return {'total_referrals': total, 'referral_count': row[0], 'total_reward_days': row[1], 'claimed_reward_days': row[2], 'available_days': row[1]-row[2]}
        return {'total_referrals': total, 'referral_count': 0, 'total_reward_days': 0, 'claimed_reward_days': 0, 'available_days': 0}
    return await execute_db(_g)

async def db_claim_referral_reward(user_id: int) -> int:
    async def _c(conn):
        stats = await db_get_referral_stats(user_id)
        av = stats['available_days']
        if av <= 0: return 0
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        cd = 0
        if row and row[0]:
            try:
                ed = datetime.fromisoformat(row[0])
                if ed > utc_now(): cd = (ed - utc_now()).days
            except: pass
        new_end = (utc_now() + timedelta(days=cd+av)).isoformat()
        await conn.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (new_end, user_id))
        await conn.execute("UPDATE referral_rewards SET claimed_reward_days=claimed_reward_days+? WHERE user_id=?", (av, user_id))
        await conn.commit()
        return av
    return await execute_db(_c)

# ===================================================================
# 17. دوال المسابقات
# ===================================================================
async def db_create_contest(creator_id: int, title: str, description: str, prize: str, end_date: datetime, contest_type: str = 'raffle') -> int:
    async def _c(conn):
        cur = await conn.execute("INSERT INTO contests (creator_id, title, description, prize, end_date, contest_type, created_at) VALUES (?,?,?,?,?,?,?) RETURNING id", (creator_id, title, description, prize, end_date.isoformat(), contest_type, utc_now_iso()))
        row = await cur.fetchone()
        await conn.commit()
        return row[0] if row else None
    return await execute_db(_c)

async def db_participate_in_contest(user_id: int, contest_id: int, answer: str = "") -> bool:
    try:
        await execute_db(lambda c: c.execute("INSERT INTO contest_participants (user_id, contest_id, answer, joined_at) VALUES (?,?,?,?)", (user_id, contest_id, answer, utc_now_iso())) or c.commit())
        return True
    except: return False

async def db_get_contest(contest_id: int):
    async def _g(conn):
        cur = await conn.execute("SELECT id, title, description, prize, end_date, status, winner_id FROM contests WHERE id=?", (contest_id,))
        row = await cur.fetchone()
        return {'id': row[0], 'title': row[1], 'description': row[2], 'prize': row[3], 'end_date': row[4], 'status': row[5], 'winner_id': row[6]} if row else None
    return await execute_db(_g)

async def db_set_contest_winner(contest_id: int, winner_id: int) -> bool:
    async def _s(conn):
        await conn.execute("UPDATE contests SET status='finished', winner_id=? WHERE id=?", (winner_id, contest_id))
        await conn.execute("INSERT INTO contest_winners (contest_id, winner_id, announced_at) VALUES (?,?,?)", (contest_id, winner_id, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_s)

async def db_get_active_contests_with_participants(limit=10):
    return await execute_db(lambda c: c.execute("SELECT c.id, c.title, c.description, c.prize, c.end_date, c.contest_type, (SELECT COUNT(*) FROM contest_participants WHERE contest_id=c.id) as participants FROM contests c WHERE c.status='active' ORDER BY c.end_date ASC LIMIT ?", (limit,)) or c.fetchall())

async def db_get_user_participation(user_id: int, contest_id: int) -> bool:
    async def _chk(conn):
        cur = await conn.execute("SELECT 1 FROM contest_participants WHERE contest_id=? AND user_id=?", (contest_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_chk)

# ===================================================================
# 18. دوال التذاكر والردود
# ===================================================================
async def db_get_next_ticket_number() -> int:
    async def _g(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='last_ticket_number'")
        row = await cur.fetchone()
        return int(row[0]) if row else 0
    return await execute_db(_g)

async def db_save_ticket(user_id: int, username: str, message: str, ticket_num: int):
    await execute_db(lambda c: c.execute("INSERT INTO support_tickets (user_id, username, message, ticket_number, created_at) VALUES (?,?,?,?,?)", (user_id, username, message, ticket_num, utc_now_iso())) or c.commit())

async def db_get_reply(keyword: str):
    async def _g(conn):
        cur = await conn.execute("SELECT reply FROM auto_replies WHERE keyword=? AND is_active=1 LIMIT 1", (keyword,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_g)

async def db_add_reply(keyword: str, reply: str):
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO auto_replies (chat_id, keyword, reply, created_at) VALUES (0,?,?,?)", (keyword, reply, utc_now_iso())) or c.commit())

async def db_del_reply(keyword: str) -> bool:
    await execute_db(lambda c: c.execute("DELETE FROM auto_replies WHERE keyword=? AND chat_id=0", (keyword,)) or c.commit())
    return True

async def db_get_auto_reply_settings(chat_id: int) -> dict:
    async def _g(conn):
        cur = await conn.execute("SELECT * FROM auto_reply_settings WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        if row: return {'enabled': bool(row[1]) if len(row) > 1 else False, 'only_admins': bool(row[2]) if len(row) > 2 else False, 'ignore_bots': bool(row[3]) if len(row) > 3 else True}
        return {'enabled': False, 'only_admins': False, 'ignore_bots': True}
    return await execute_db(_g)

# ===================================================================
# 19. دوال الإعدادات العامة
# ===================================================================
async def db_get_settings(key: str) -> Optional[str]:
    async def _g(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_g)

async def db_set_setting(key: str, value: str):
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value)) or c.commit())

async def db_get_updates_channel() -> Optional[str]: return await db_get_settings('updates_channel')
async def db_get_force_subscribe_channel() -> Optional[str]: return await db_get_settings('force_subscribe_channel')
async def db_get_log_channel_id() -> Optional[int]:
    v = await db_get_settings('log_channel_id')
    return int(v) if v else None
async def db_get_allowed_sendcode_user() -> Optional[int]:
    v = await db_get_settings('allowed_sendcode_user')
    return int(v) if v else None
async def db_get_publish_interval_seconds() -> int:
    v = await db_get_settings('publish_interval')
    return int(v) if v else 720
async def db_get_auto_backup() -> bool:
    v = await db_get_settings('auto_backup')
    return v == '1'
async def db_get_last_backup_time() -> Optional[str]: return await db_get_settings('last_backup')

async def db_get_users_needing_reminder():
    async def _g(conn):
        cur = await conn.execute("""
            SELECT u.user_id, u.subscription_end, COALESCE(r.reminder_days_before,3) as rdb, COALESCE(r.notification_lang,'ar') as nl, COALESCE(r.last_reminder_sent,0) as lrs
            FROM users u LEFT JOIN user_reminder_settings r ON u.user_id=r.user_id
            WHERE u.subscription_end IS NOT NULL AND u.subscription_end > datetime('now') AND u.banned=0
        """)
        rows = await cur.fetchall()
        results = []
        now = utc_now()
        for row in rows:
            try:
                ed = datetime.fromisoformat(row[1])
                dl = (ed - now).days
                if 0 < dl <= row[2]:
                    last = row[4]
                    if not last or (now - datetime.fromisoformat(last)).days >= 1:
                        results.append({'user_id': row[0], 'days_left': dl, 'notification_lang': row[3]})
            except: pass
        return results
    return await execute_db(_g)

async def db_update_last_reminder_sent(user_id: int, reminder_type: str):
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO user_reminder_settings (user_id, last_reminder_sent) VALUES (?,?)", (user_id, utc_now_iso())) or c.commit())

async def db_update_reminder_settings(user_id: int, **kwargs):
    async def _u(conn):
        await conn.execute("INSERT OR IGNORE INTO user_reminder_settings (user_id) VALUES (?)", (user_id,))
        updates = [f"{k}=?" for k in kwargs]
        vals = list(kwargs.values()) + [user_id]
        if updates: await conn.execute(f"UPDATE user_reminder_settings SET {', '.join(updates)} WHERE user_id=?", vals)
        await conn.commit()
    await execute_db(_u)

async def get_user_translation_language(user_id: int) -> str:
    async def _g(conn):
        cur = await conn.execute("SELECT lang FROM user_translation WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 'off'
    return await execute_db(_g)

async def db_get_due_scheduled_posts(now: datetime, limit: int = 50):
    return await execute_db(lambda c: c.execute("SELECT id, chat_id, text, fail_count FROM scheduled_posts WHERE publish_time <= ? AND fail_count < 5 ORDER BY publish_time ASC LIMIT ?", (now.isoformat(), limit)) or c.fetchall())

async def db_delete_scheduled_post(post_id: int):
    await execute_db(lambda c: c.execute("DELETE FROM scheduled_posts WHERE id=?", (post_id,)) or c.commit())

async def db_update_scheduled_post_fail(post_id: int, fail_count: int):
    await execute_db(lambda c: c.execute("UPDATE scheduled_posts SET fail_count=? WHERE id=?", (fail_count, post_id)) or c.commit())

async def db_get_all_users():
    return await execute_db(lambda c: c.execute("SELECT user_id, banned FROM users ORDER BY user_id") or c.fetchall())

async def db_is_banned(user_id: int) -> bool:
    async def _chk(conn):
        cur = await conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_chk)

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

async def db_stats():
    async def _g(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM users"); total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE banned=1"); banned = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM posts"); posts = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM bot_groups"); groups = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM user_channels"); channels = (await cur.fetchone())[0]
        return total, banned, posts, groups, channels
    return await execute_db(_g)

async def db_get_learning_stats():
    async def _g(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM sentiment_history"); sentiments = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM response_learning"); patterns = (await cur.fetchone())[0]
        return {'patterns': patterns, 'sentiments': sentiments}
    return await execute_db(_g)

async def db_get_channel_stats(channel_db_id: int) -> dict:
    async def _s(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=1", (channel_db_id,))
        published = (await cur.fetchone())[0]
        return {'total_posts': total, 'published_posts': published, 'unpublished_posts': total-published, 'total_views': 0, 'avg_views': 0}
    return await execute_db(_s)

async def db_save_schedule(channel_db_id: int, schedule_type: str, **kwargs):
    async def _s(conn):
        await conn.execute("INSERT OR REPLACE INTO schedule (channel_db_id, schedule_type, interval_minutes, interval_hours, interval_days, days_of_week, specific_dates, publish_time, cron_expression, next_publish_date) VALUES (?,?,?,?,?,?,?,?,?,NULL)",
            (channel_db_id, schedule_type, kwargs.get('interval_minutes',12), kwargs.get('interval_hours',0), kwargs.get('interval_days',0), kwargs.get('days_of_week','[]'), kwargs.get('specific_dates','[]'), kwargs.get('publish_time','00:00'), kwargs.get('cron_expression')))
        await conn.commit()
    await execute_db(_s)

async def db_get_schedule(channel_db_id: int):
    async def _g(conn):
        cur = await conn.execute("SELECT schedule_type, interval_minutes, interval_hours, interval_days, days_of_week, specific_dates, publish_time, cron_expression, next_publish_date FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        if row: return {'type': row[0] or 'interval_minutes', 'interval_minutes': row[1] or 12, 'interval_hours': row[2] or 0, 'interval_days': row[3] or 0, 'days_of_week': row[4] or '[]', 'specific_dates': row[5] or '[]', 'publish_time': row[6] or '00:00', 'cron_expression': row[7], 'next_publish_date': row[8]}
        return {'type': 'interval_minutes', 'interval_minutes': 12, 'interval_hours': 0, 'interval_days': 0, 'days_of_week': '[]', 'specific_dates': '[]', 'publish_time': '00:00', 'cron_expression': None, 'next_publish_date': None}
    return await execute_db(_g)

async def db_set_next_publish_date(channel_db_id: int, next_date: datetime):
    await execute_db(lambda c: c.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?", (next_date.isoformat() if next_date else None, channel_db_id)) or c.commit())

async def db_set_last_publish(channel_db_id: int, publish_time: datetime):
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO last_publish (channel_db_id, last_publish_time) VALUES (?,?)", (channel_db_id, publish_time.isoformat())) or c.commit())

async def db_set_publish_time(channel_db_id: int, time_str: str):
    await execute_db(lambda c: c.execute("UPDATE schedule SET publish_time=?, next_publish_date=NULL WHERE channel_db_id=?", (time_str, channel_db_id)) or c.commit())

async def db_update_next_publish_date(channel_db_id: int):
    async def _u(conn):
        cur = await conn.execute("SELECT last_publish_time FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        last_time = datetime.fromisoformat(row[0]) if row and row[0] else utc_now()
        cur = await conn.execute("SELECT schedule_type, interval_minutes, interval_hours, interval_days FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        if not row: return
        st = row[0] or 'interval_minutes'
        if st == 'interval_minutes': nd = last_time + timedelta(minutes=row[1] or 12)
        elif st == 'interval_hours': nd = last_time + timedelta(hours=row[2] or 1)
        elif st == 'interval_days': nd = last_time + timedelta(days=row[3] or 1)
        else: nd = last_time + timedelta(minutes=12)
        if nd <= utc_now():
            while nd <= utc_now():
                if st == 'interval_minutes': nd += timedelta(minutes=row[1] or 12)
                elif st == 'interval_hours': nd += timedelta(hours=row[2] or 1)
                elif st == 'interval_days': nd += timedelta(days=row[3] or 1)
                else: nd += timedelta(minutes=12)
        await conn.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?", (nd.isoformat(), channel_db_id))
        await conn.commit()
    await execute_db(_u)

async def db_add_scheduled_post(chat_id: int, text: str, publish_time: datetime):
    await execute_db(lambda c: c.execute("INSERT INTO scheduled_posts (chat_id, text, publish_time) VALUES (?,?,?)", (chat_id, text, publish_time.isoformat())) or c.commit())

async def db_register_hidden_owner_group(chat_id: int, owner_id: int) -> bool:
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id) VALUES (?,?)", (chat_id, owner_id)) or c.commit())
    return True

async def db_add_hidden_admin(chat_id: int, admin_id: int, added_by: int) -> bool:
    async def _a(conn):
        cur = await conn.execute("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
        if await cur.fetchone(): return False
        await conn.execute("INSERT INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?,?,?,?)", (chat_id, admin_id, added_by, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_a)

async def db_remove_hidden_admin(chat_id: int, admin_id: int) -> bool:
    await execute_db(lambda c: c.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id)) or c.commit())
    invalidate_auth_cache(chat_id, admin_id)
    return True

async def db_get_hidden_admins(chat_id: int):
    return await execute_db(lambda c: c.execute("SELECT admin_id, added_by, added_at FROM hidden_admins WHERE chat_id=?", (chat_id,)) or c.fetchall())

async def add_bot_admin(user_id: int) -> bool:
    await execute_db(lambda c: c.execute("INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)", (user_id, PRIMARY_OWNER_ID, utc_now_iso())) or c.commit())
    return True

async def remove_bot_admin(user_id: int) -> bool:
    await execute_db(lambda c: c.execute("DELETE FROM bot_admins WHERE user_id=?", (user_id,)) or c.commit())
    return True

async def translate_text(text: str, target_lang: str) -> str:
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except: return text

# ===================================================================
# 20. نظام الردود والكيبوردات
# ===================================================================
class CallbackData:
    MAIN_MENU = "main_menu"; BACK = "back"; CANCEL_SESSION = "cancel_session"
    CHANNELS_ADD = "channels:add"; CHANNELS_MY = "channels:my_channels"
    CHANNELS_DELETE_PREFIX = "channels:delete:"; CHANNELS_SELECT_PREFIX = "channels:select:"
    POSTS_ADD_15 = "posts:add_15"; POSTS_PUBLISH_ONE = "posts:publish_one"
    POSTS_MY = "posts:my_posts"; POSTS_RECYCLE = "posts:recycle"
    POSTS_DELETE_SINGLE_PREFIX = "posts:delete_single:"
    POSTS_CONFIRM_CLEAR_ALL_PREFIX = "posts:confirm_clear_all:"
    POSTS_CLEAR_ALL_PREFIX = "posts:clear_all:"
    PUBLISH_ALL_CHANNELS = "publish_all_channels"
    STATS_PENDING = "stats:pending"; STATS_FULL = "stats:full"
    GROUPS_MY = "groups:my_groups"; GROUPS_SETTINGS_PREFIX = "groups:settings:"
    SETTINGS_MENU = "settings:menu"
    SETTINGS_TOGGLE_AUTO_PUBLISH = "settings:toggle_auto_publish"
    SETTINGS_TOGGLE_AUTO_RECYCLE = "settings:toggle_auto_recycle"
    SCHEDULE_MENU_PREFIX = "schedule:menu:"
    SCHEDULE_SET_INTERVAL_MINUTES_PREFIX = "schedule:set_interval_minutes:"
    SCHEDULE_SET_INTERVAL_HOURS_PREFIX = "schedule:set_interval_hours:"
    SCHEDULE_SET_INTERVAL_DAYS_PREFIX = "schedule:set_interval_days:"
    SCHEDULE_SET_DAYS_PREFIX = "schedule:set_days:"; SCHEDULE_SET_DATES_PREFIX = "schedule:set_dates:"
    SCHEDULE_SET_PUBLISH_TIME_PREFIX = "schedule:set_publish_time:"
    SCHEDULE_DAY_SELECT_PREFIX = "schedule:day_select:"; SCHEDULE_SAVE_DAYS = "schedule:save_days"
    SCHEDULE_SET_CRON_PREFIX = "schedule:set_cron:"
    SECURITY_BANNED_WORDS_MENU_PREFIX = "security:banned_words_menu:"
    SECURITY_CLOSE = "security:close"; SECURITY_SELECT_GROUP = "security_select_group:"
    SECURITY_REFRESH_GROUPS = "security_refresh_groups"
    SECURITY_ENABLE_ALL_PREFIX = "security:enable_all:"
    SECURITY_DISABLE_ALL_PREFIX = "security:disable_all:"
    SECURITY_DELETE_PENALTY_PREFIX = "security:delete_penalty:"
    BANNED_WORDS_ADD_PREFIX = "banned_words:add:"; BANNED_WORDS_LIST_PREFIX = "banned_words:list:"
    BANNED_WORDS_REMOVE_PREFIX = "banned_words:remove:"
    PENALTY_MENU = "penalty_menu"; PENALTY_KICK = "penalty:kick"; PENALTY_BAN = "penalty:ban"
    PENALTY_MUTE = "penalty:mute"; PENALTY_WARN = "penalty:warn"
    PENALTY_RESTRICT = "penalty:restrict"; PENALTY_NONE = "penalty:none"
    ADVANCED_ACTIONS = "advanced_actions"
    GROUP_ACTION_BAN = "group_action:ban"; GROUP_ACTION_MUTE = "group_action:mute"
    GROUP_ACTION_WARN = "group_action:warn"; GROUP_ACTION_KICK = "group_action:kick"
    GROUP_ACTION_RESTRICT = "group_action:restrict"; GROUP_ACTION_PIN = "group_action:pin"
    GROUP_ACTION_LOG = "group_action:log"; GROUP_ACTION_UNBAN = "group_action:unban"
    ADV_MUTE_DURATION_PREFIX = "adv_mute_duration:"
    PANEL_LOCK_PREFIX = "panel:lock:"; PANEL_UNLOCK_PREFIX = "panel:unlock:"; PANEL_CLOSE = "panel:close"
    HELP = "help"; SUPPORT_MENU = "support:menu"; SUPPORT_HELP = "support:help"
    SUPPORT_TICKET = "support:ticket"
    TRIAL = "trial"; SUBSCRIBE_MENU = "subscribe:menu"
    BUY_SUBSCRIPTION_1 = "buy:subscription_1"; BUY_SUBSCRIPTION_2 = "buy:subscription_2"
    BUY_SUBSCRIPTION_30 = "buy:subscription_30"; BUY_SUBSCRIPTION_90 = "buy:subscription_90"
    DEVELOPER = "developer"; UPDATES = "updates"
    REFERRAL_MENU = "referral:menu"; REFERRAL_COPY_LINK_PREFIX = "referral:copy_link:"
    REFERRAL_CLAIM_REWARD = "referral:claim_reward"; REFERRAL_LIST = "referral:list"
    REMINDER_MENU = "reminder:menu"; REMINDER_TOGGLE_SUB = "reminder:toggle_sub"
    REMINDER_TOGGLE_DAILY = "reminder:toggle_daily"; REMINDER_TOGGLE_WEEKLY = "reminder:toggle_weekly"
    REMINDER_SET_DAYS = "reminder:set_days"; REMINDER_SET_LANG = "reminder:set_lang"
    REMINDER_LANG_PREFIX = "reminder:lang:"
    TRANSLATION_MENU = "translation:menu"; TRANSLATION_OFF = "translation:off"
    TRANSLATION_SET_PREFIX = "translation:set:"
    CONTESTS_MENU = "contests_menu"; CONTEST_JOIN_PREFIX = "contest_join:"
    CONTEST_WINNERS = "contest_winners"
    CHANNEL_STATS = "channel_stats"; MY_CHANNEL_STATS = "my_channel_stats"
    CHECK_SUBSCRIBE = "check_subscribe"
    ADMIN_PANEL = "admin:panel"; ADMIN_USERS = "admin:users"
    ADMIN_BANNED_USERS = "admin:banned_users"; ADMIN_UNBAN_ALL_USERS = "admin:unban_all_users"
    ADMIN_ALL_CHANNELS = "admin:all_channels"; ADMIN_BANNED_CHANNELS = "admin:banned_channels"
    ADMIN_ACTIVATE_ALL_CHANNELS = "admin:activate_all_channels"
    ADMIN_GROUPS = "admin:groups"; ADMIN_BANNED_GROUPS = "admin:banned_groups"
    ADMIN_UNBAN_ALL_GROUPS = "admin:unban_all_groups"
    ADMIN_BOT_CHANNELS = "admin:bot_channels"
    ADMIN_MONITOR_USERS = "admin:monitor_users"
    ADMIN_ADD_ADMIN = "admin:add_admin"; ADMIN_REMOVE_ADMIN = "admin:remove_admin"
    ADMIN_RAM = "admin:ram"; ADMIN_STATS = "admin:stats"; ADMIN_METRICS = "admin:metrics"
    ADMIN_BACKUP = "admin:backup"; ADMIN_RESTORE_BACKUP = "admin:restore_backup"
    ADMIN_RESTORE_BACKUP_SELECT_PREFIX = "admin:restore_backup_select:"
    ADMIN_BACKUP_SETTINGS = "admin:backup_settings"; ADMIN_TOGGLE_AUTO_BACKUP = "admin:toggle_auto_backup"
    ADMIN_CHANGE_INTERVAL = "admin:change_interval"
    ADMIN_SEND_UPDATE = "admin:send_update"; ADMIN_SET_UPDATE_CHANNEL = "admin:set_update_channel"
    ADMIN_SHOW_UPDATE_CHANNEL = "admin:show_update_channel"; ADMIN_UPDATES = "admin:updates"
    ADMIN_FORCE_SUBSCRIBE = "admin:force_subscribe"; ADMIN_SET_FORCE_CHANNEL = "admin:set_force_channel"
    ADMIN_BROADCAST = "admin:broadcast"; ADMIN_CONFIRM_BROADCAST = "admin:confirm_broadcast"
    ADMIN_SUPPORT_TICKETS = "admin:support_tickets"; ADMIN_DELETE_ALL_TICKETS = "admin:delete_all_tickets"
    ADMIN_CONFIRM_DELETE_TICKETS = "admin:confirm_delete_tickets"
    ADMIN_MANAGE_SENDCODE = "admin:manage_sendcode"; ADMIN_SET_SENDCODE_USER = "admin:set_sendcode_user"
    ADMIN_SHOW_LOG_CHANNEL = "admin:show_log_channel"; ADMIN_SET_LOG_CHANNEL = "admin:set_log_channel"
    ADMIN_REPLIES = "admin:replies"; ADMIN_ADD_REPLY = "admin:add_reply"
    ADMIN_LIST_REPLIES = "admin:list_replies"; ADMIN_DEL_REPLY = "admin:del_reply"
    ADMIN_BANNED_WORDS = "admin:banned_words"; ADMIN_ADD_BANNED_WORD = "admin:add_banned_word"
    ADMIN_LIST_BANNED_WORDS = "admin:list_banned_words"; ADMIN_REMOVE_BANNED_WORD = "admin:remove_banned_word"
    ADMIN_CREATE_CONTEST = "admin:create_contest"; ADMIN_DECLARE_WINNER = "admin:declare_winner"
    ADMIN_DEL_CONTEST_PREFIX = "admin:del_contest:"; ADMIN_AUTO_REPLY = "admin_auto_reply"
    AUTO_REPLY_MENU_PREFIX = "auto_reply_menu:"; AUTO_REPLY_TOGGLE_PREFIX = "auto_reply_toggle:"
    AUTO_REPLY_ADMINS_PREFIX = "auto_reply_admins:"; AUTO_REPLY_RESET_PREFIX = "auto_reply_reset:"
    AUTO_REPLY_CONFIRM_RESET_PREFIX = "auto_reply_confirm_reset:"
    AUTO_REPLY_STATS_PREFIX = "auto_reply_stats:"; USER_AUTO_REPLY_TOGGLE_PREFIX = "user_auto_reply_toggle:"
    NSFW_SETTINGS = "nsfw_settings"; NSFW_TOGGLE = "nsfw_toggle"; NSFW_THRESHOLD_SET = "nsfw_threshold_set"

class UserState(Enum):
    NONE = auto(); ADDING_POSTS = auto(); WAITING_CHANNEL_ID = auto()
    WAITING_INTERVAL_MINUTES = auto(); WAITING_INTERVAL_HOURS = auto(); WAITING_INTERVAL_DAYS = auto()
    WAITING_DATES = auto(); WAITING_PUBLISH_TIME = auto(); SELECTING_DAYS = auto()
    WAITING_ADMIN_ID_ADD = auto(); WAITING_ADMIN_ID_REMOVE = auto()
    WAITING_BROADCAST = auto(); WAITING_UPDATE_TEXT = auto(); WAITING_UPDATE_CHANNEL = auto()
    WAITING_FORCE_CHANNEL = auto(); WAITING_REMINDER_DAYS = auto()
    WAITING_SCHEDULE_POST = auto()
    WAITING_BAN_USER = auto(); WAITING_MUTE_USER = auto(); WAITING_WARN_USER = auto()
    WAITING_KICK_USER = auto(); WAITING_RESTRICT_USER = auto(); WAITING_UNBAN_USER = auto()
    WAITING_PIN_MESSAGE = auto()
    WAITING_GROUP_BANNED_WORD = auto(); WAITING_REMOVE_GROUP_BANNED_WORD = auto()
    WAITING_GLOBAL_BANNED_WORD = auto(); WAITING_REMOVE_GLOBAL_BANNED_WORD = auto()
    WAITING_KEYWORD = auto(); WAITING_REPLY = auto()
    WAITING_SENDCODE_USER = auto(); WAITING_LOG_CHANNEL = auto()
    SUPPORT_MODE = auto()
    WAITING_CONTEST_TITLE = auto(); WAITING_CONTEST_DESCRIPTION = auto()
    WAITING_CONTEST_PRIZE = auto(); WAITING_CONTEST_END_DATE = auto()
    WAITING_CONTEST_ANSWER = auto()
    WAITING_NSFW_THRESHOLD = auto(); WAITING_CRON = auto()
    WAITING_MAX_LENGTH = auto(); WAITING_WARN_COUNT = auto()

# ===================================================================
# 21. الكيبوردات
# ===================================================================
def security_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 روابط", callback_data=f"security:links:{chat_id}"),
         InlineKeyboardButton("@ معرفات", callback_data=f"security:mentions:{chat_id}"),
         InlineKeyboardButton("⏱️ بطيء", callback_data=f"security:slow_mode:{chat_id}")],
        [InlineKeyboardButton("🎯 ترحيب", callback_data=f"security:welcome_enabled:{chat_id}"),
         InlineKeyboardButton("👋 وداع", callback_data=f"security:goodbye_enabled:{chat_id}"),
         InlineKeyboardButton("🚫 كلمات", callback_data=f"security:banned_words_menu:{chat_id}")],
        [InlineKeyboardButton("🎬 فيديو", callback_data=f"security:delete_videos:{chat_id}"),
         InlineKeyboardButton("🎵 صوت", callback_data=f"security:delete_audio:{chat_id}"),
         InlineKeyboardButton("🎞️ متحرك", callback_data=f"security:delete_animation:{chat_id}")],
        [InlineKeyboardButton("🛠️ خدمة", callback_data=f"security:delete_service:{chat_id}"),
         InlineKeyboardButton("📄 ملفات", callback_data=f"security:delete_documents:{chat_id}"),
         InlineKeyboardButton("🖼️ ملصقات", callback_data=f"security:delete_stickers:{chat_id}")],
        [InlineKeyboardButton("📨 مُعاد", callback_data=f"security:delete_forwarded:{chat_id}"),
         InlineKeyboardButton("📊 استطلاع", callback_data=f"security:delete_polls:{chat_id}"),
         InlineKeyboardButton("🎮 ألعاب", callback_data=f"security:delete_games:{chat_id}")],
        [InlineKeyboardButton("🎤 صوتي", callback_data=f"security:delete_voice:{chat_id}"),
         InlineKeyboardButton("🎥 نوت", callback_data=f"security:delete_video_note:{chat_id}"),
         InlineKeyboardButton("🌊 فيضان", callback_data=f"security:antiflood:{chat_id}")],
        [InlineKeyboardButton("🌙 ليلي", callback_data=f"security:night_mode:{chat_id}"),
         InlineKeyboardButton("📏 طول", callback_data=f"security:max_length:{chat_id}"),
         InlineKeyboardButton("⚠️ تحذير", callback_data=f"security:warn_settings:{chat_id}")],
        [InlineKeyboardButton("⚖️ عقوبة", callback_data=f"security:delete_penalty:{chat_id}"),
         InlineKeyboardButton("⚡ تفعيل الكل", callback_data=f"security:enable_all:{chat_id}"),
         InlineKeyboardButton("⛔ تعطيل الكل", callback_data=f"security:disable_all:{chat_id}")],
        [InlineKeyboardButton("⚖️ العقوبة", callback_data=f"penalty_menu:{chat_id}"),
         InlineKeyboardButton("🛠️ متقدم", callback_data=f"advanced_actions:{chat_id}"),
         InlineKeyboardButton("📜 سجل", callback_data=f"group_action:log:{chat_id}")],
        [InlineKeyboardButton("🔙 إغلاق", callback_data=CallbackData.SECURITY_CLOSE)]
    ])

def get_admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 المستخدمين", callback_data=CallbackData.ADMIN_USERS),
         InlineKeyboardButton("⛔ المحظورين", callback_data=CallbackData.ADMIN_BANNED_USERS)],
        [InlineKeyboardButton("📡 قنوات", callback_data=CallbackData.ADMIN_ALL_CHANNELS),
         InlineKeyboardButton("👥 المجموعات", callback_data=CallbackData.ADMIN_GROUPS)],
        [InlineKeyboardButton("👑 + مشرف", callback_data=CallbackData.ADMIN_ADD_ADMIN),
         InlineKeyboardButton("🗑️ - مشرف", callback_data=CallbackData.ADMIN_REMOVE_ADMIN)],
        [InlineKeyboardButton("💬 ردود", callback_data=CallbackData.ADMIN_REPLIES),
         InlineKeyboardButton("🚫 كلمات", callback_data=CallbackData.ADMIN_BANNED_WORDS)],
        [InlineKeyboardButton("🖥️ الرام", callback_data=CallbackData.ADMIN_RAM),
         InlineKeyboardButton("📊 إحصائيات", callback_data=CallbackData.ADMIN_STATS)],
        [InlineKeyboardButton("💾 نسخ", callback_data=CallbackData.ADMIN_BACKUP),
         InlineKeyboardButton("🔄 استعادة", callback_data=CallbackData.ADMIN_RESTORE_BACKUP)],
        [InlineKeyboardButton("📢 تحديث", callback_data=CallbackData.ADMIN_SEND_UPDATE),
         InlineKeyboardButton("📨 بث", callback_data=CallbackData.ADMIN_BROADCAST)],
        [InlineKeyboardButton("📋 تذاكر", callback_data=CallbackData.ADMIN_SUPPORT_TICKETS),
         InlineKeyboardButton("📋 تقارير", callback_data=CallbackData.ADMIN_SHOW_LOG_CHANNEL)],
        [InlineKeyboardButton("🔒 اشتراك إجباري", callback_data=CallbackData.ADMIN_FORCE_SUBSCRIBE),
         InlineKeyboardButton("📊 مراقبة", callback_data=CallbackData.ADMIN_MONITOR_USERS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])

def get_group_banned_words_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كلمة", callback_data=f"banned_words:add:{chat_id}"),
         InlineKeyboardButton("📋 عرض الكلمات", callback_data=f"banned_words:list:{chat_id}")],
        [InlineKeyboardButton("🗑️ حذف كلمة", callback_data=f"banned_words:remove:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"groups:settings:{chat_id}")]
    ])

def get_replies_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة رد", callback_data=CallbackData.ADMIN_ADD_REPLY),
         InlineKeyboardButton("📋 عرض الردود", callback_data=CallbackData.ADMIN_LIST_REPLIES)],
        [InlineKeyboardButton("🗑️ حذف رد", callback_data=CallbackData.ADMIN_DEL_REPLY),
         InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])

def get_banned_words_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كلمة عامة", callback_data=CallbackData.ADMIN_ADD_BANNED_WORD),
         InlineKeyboardButton("📋 عرض الكلمات", callback_data=CallbackData.ADMIN_LIST_BANNED_WORDS)],
        [InlineKeyboardButton("🗑️ حذف كلمة", callback_data=CallbackData.ADMIN_REMOVE_BANNED_WORD),
         InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_BANNED_WORDS)]
    ])

def get_advanced_group_actions_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 حظر", callback_data=f"group_action:ban:{chat_id}"),
         InlineKeyboardButton("🔇 كتم", callback_data=f"group_action:mute:{chat_id}")],
        [InlineKeyboardButton("⚠️ تحذير", callback_data=f"group_action:warn:{chat_id}"),
         InlineKeyboardButton("👢 طرد", callback_data=f"group_action:kick:{chat_id}")],
        [InlineKeyboardButton("🔒 تقييد", callback_data=f"group_action:restrict:{chat_id}"),
         InlineKeyboardButton("📌 تثبيت", callback_data=f"group_action:pin:{chat_id}")],
        [InlineKeyboardButton("🔓 إلغاء حظر", callback_data=f"group_action:unban:{chat_id}"),
         InlineKeyboardButton("📜 سجل", callback_data=f"group_action:log:{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"groups:settings:{chat_id}")]
    ])

def get_advanced_mute_duration_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱️ 5 دقائق", callback_data=f"adv_mute_duration:5:{chat_id}"),
         InlineKeyboardButton("⏱️ 30 دقيقة", callback_data=f"adv_mute_duration:30:{chat_id}")],
        [InlineKeyboardButton("⏱️ 1 ساعة", callback_data=f"adv_mute_duration:60:{chat_id}"),
         InlineKeyboardButton("⏱️ 12 ساعة", callback_data=f"adv_mute_duration:720:{chat_id}")],
        [InlineKeyboardButton("📆 يوم", callback_data=f"adv_mute_duration:1440:{chat_id}"),
         InlineKeyboardButton("📆 أسبوع", callback_data=f"adv_mute_duration:10080:{chat_id}")],
        [InlineKeyboardButton("🔇 كتم دائم", callback_data=f"adv_mute_duration:0:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"advanced_actions:{chat_id}")]
    ])

def penalty_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👢 طرد", callback_data=f"penalty:kick:{chat_id}"),
         InlineKeyboardButton("🛑 حظر", callback_data=f"penalty:ban:{chat_id}")],
        [InlineKeyboardButton("🔇 كتم", callback_data=f"penalty:mute:{chat_id}"),
         InlineKeyboardButton("⚠️ تحذير", callback_data=f"penalty:warn:{chat_id}")],
        [InlineKeyboardButton("🔒 تقييد", callback_data=f"penalty:restrict:{chat_id}"),
         InlineKeyboardButton("❌ لا شيء", callback_data=f"penalty:none:{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"groups:settings:{chat_id}")]
    ])

def get_auto_reply_keyboard(chat_id: int, settings: dict) -> InlineKeyboardMarkup:
    st = "🟢 مفعل" if settings.get('enabled') else "🔴 معطل"
    at = "👑 مشرفين" if settings.get('only_admins') else "👥 الجميع"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📝 الردود: {st}", callback_data=f"auto_reply_toggle:{chat_id}")],
        [InlineKeyboardButton(f"👥 المستخدمون: {at}", callback_data=f"auto_reply_admins:{chat_id}")],
        [InlineKeyboardButton("🔄 إعادة تعيين", callback_data=f"auto_reply_reset:{chat_id}")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data=f"auto_reply_stats:{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"groups:settings:{chat_id}")]
    ])

async def get_main_keyboard(user_id: int):
    channels = await db_get_channels(user_id)
    active = await db_get_active_channel(user_id)
    cnt = 0; ch_display = "لا توجد قنوات"
    if active:
        try:
            cnt = await db_unpublished_count(active)
            ch_info = await db_get_channel_info(active)
            if ch_info: ch_display = f"{ch_info[1]} ({ch_info[0]})"
        except: pass
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
            keyboard.append([InlineKeyboardButton("⏰ الجدولة", callback_data=f"schedule:menu:{active}"),
                             InlineKeyboardButton("📊 القناة", callback_data=f"channel_stats:{active}")])
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
# 22. نظام تحليل المشاعر والتعلم
# ===================================================================
class SentimentAnalyzer:
    def __init__(self):
        self.positive_words = {"جميل","رائع","ممتاز","حلو","شكرا","شكراً","تسلم","فرح","سعيد","مبسوط","الحمد","تفاؤل","أمل","نجاح","مبدع","خير","بركة","نعمة"}
        self.negative_words = {"زعل","حزين","متعب","محبط","غضب","غاضب","مزعج","سيء","سخيف","غبي","ممل","كره","موت","ألم","جرح","نكد","فشل","خسر","ظلم","حرب","شر","لعنة"}
        self.neutral_words = {"تمام","حاضر","اوك","بخير","ماشي","طيب","جيد","عادي","موافق"}
    
    def analyze(self, text: str) -> Dict[str, Any]:
        if not text: return {'sentiment': 'neutral', 'score': 0.0}
        words = re.findall(r'\b\w+\b', text.lower())
        pc = sum(1 for w in words if w in self.positive_words)
        nc = sum(1 for w in words if w in self.negative_words)
        nuc = sum(1 for w in words if w in self.neutral_words)
        total = pc + nc + nuc
        if total == 0: return {'sentiment': 'neutral', 'score': 0.0}
        score = (pc - nc) / max(total, 1)
        if score > 0.2: sentiment = 'positive'
        elif score < -0.2: sentiment = 'negative'
        else: sentiment = 'neutral'
        return {'sentiment': sentiment, 'score': round(score, 3), 'details': {'positive': pc, 'negative': nc, 'neutral': nuc}}

sentiment_analyzer = SentimentAnalyzer()

ALL_REPLIES = {
    "السلام عليكم": "وعليكم السلام ورحمة الله وبركاته 🌸", "هلا": "هلا بك، نورت ✨",
    "اهلا": "أهلاً وسهلاً 🌹", "مرحبا": "مرحباً، نورت 🌟", "صباح الخير": "صباح النور ☀️",
    "مساء الخير": "مساء النور 🌙", "شكرا": "عفواً 😊", "شكراً": "العفو 🌹",
    "تسلم": "تسلم، الله يخليك", "يعطيك العافية": "الله يعافيك 🤍",
    "كيفك": "بخير الحمد لله، وأنت؟ 😊", "تمام": "الحمد لله 🌸",
    "بوت": "نعم، أنا بوت ريلاكس مانيجر 🌿\nكيف أقدر أساعدك؟",
    "احبك": "حبيبي والله 🤍", "الله": "لا إله إلا الله 🤲",
    "الحمد لله": "الحمد لله دائماً 🤲", "مبروك": "الله يبارك فيك 🎉",
    "هههه": "😂😂😂", "جميل": "الجمال جمالك 🌸", "رائع": "الروعة أنت 🌟",
    "ممتاز": "ممتاز مثلك 👌", "تعبان": "سلامتك، الله يشافيك 🤲",
    "حزين": "لا تحزن، الفرج قريب 🤲", "قمر": "قمر أنت والله 🌙",
    "باي": "باي، الله معاك 👋", "مع السلامة": "الله معك 🌸",
    "Hello": "Hello 👋", "Hi": "Hi there! 👋", "Thanks": "You're welcome 😊",
    "Good morning": "Good morning ☀️", "Good night": "Good night 🌙",
}

# ===================================================================
# 23. معالجات الأوامر
# ===================================================================
async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        await db_register_user(user_id)
        await db_update_user_cache(user_id, update.effective_user.username or "", update.effective_user.first_name or "")
        
        if context.args and context.args[0].startswith('ref_'):
            ref_code = context.args[0][4:]
            referrer_id = await db_get_user_by_referral_code(ref_code)
            if referrer_id and referrer_id != user_id:
                if await db_add_referral(referrer_id, user_id):
                    reward = await db_auto_reward_referral(referrer_id, user_id)
                    try: await context.bot.send_message(referrer_id, f"🎉 مستخدم جديد عبر رابطك!\n🎁 مكافأتك: {reward} يوم")
                    except: pass
        
        # اشتراك إجباري
        force_channel = await db_get_force_subscribe_channel()
        if force_channel:
            try:
                member = await context.bot.get_chat_member(f"@{force_channel}", user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("📢 اشترك", url=f"https://t.me/{force_channel}")],
                        [InlineKeyboardButton("✅ تحقق", callback_data=CallbackData.CHECK_SUBSCRIBE)]
                    ])
                    await safe_send_markdown(context.bot, user_id, f"⚠️ اشترك في @{force_channel} أولاً", reply_markup=kb)
                    return
            except: pass
        
        kb, title, active = await get_main_keyboard(user_id)
        if active: context.user_data['active_channel'] = active
        if update.callback_query: await safe_edit_markdown(update.callback_query, title, reply_markup=kb)
        else: await safe_send_markdown(context.bot, user_id, title, reply_markup=kb)
    except Exception as e:
        error_id = log_error(e)
        await safe_send_markdown(context.bot, update.effective_user.id, f"❌ خطأ: `{error_id}`")

async def language_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, update.effective_user.id, "اختر اللغة:", reply_markup=kb)

async def syncgroup_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, "🔒 للمجموعات فقط")
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    await db_register_group(chat_id, update.effective_chat.title or "بدون اسم", user_id, update.effective_chat.username)
    
    bp = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bp['can_act']:
        await safe_send_markdown(context.bot, user_id, "⚠️ البوت ليس مشرفاً\nاجعل البوت مشرفاً ثم أعد المحاولة")
        return
    
    real_id = user_id
    if user_id == ANONYMOUS_ADMIN_ID:
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            if admins:
                for a in admins:
                    if a.status == 'creator': real_id = a.user.id; break
                if real_id == user_id: real_id = admins[0].user.id
        except: pass
    
    is_admin = await is_currently_admin_in_group(context.bot, chat_id, real_id) if real_id != user_id else await is_currently_admin_in_group(context.bot, chat_id, user_id)
    
    if is_admin:
        await db_register_hidden_owner_group(chat_id, real_id)
        invalidate_auth_cache(chat_id, real_id)
        cnt = await db_sync_group_admins(chat_id, context.bot, real_id)
        await safe_send_markdown(context.bot, real_id, f"✅ تم تفعيل المجموعة!\n👥 {cnt} مشرف\nاستخدم /security للإعدادات")
    else:
        await safe_send_markdown(context.bot, user_id, "✅ تم تسجيل المجموعة!\nاستخدم /register_hidden_owner بعد جعلك مشرفاً")

async def register_hidden_owner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']: return
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    bp = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bp['can_act']: await safe_send_markdown(context.bot, user_id, "⚠️ البوت ليس مشرفاً"); return
    member = await context.bot.get_chat_member(chat_id, user_id)
    if member.status not in ['administrator', 'creator']: await safe_send_markdown(context.bot, user_id, "🔒 للمشرفين فقط"); return
    await db_register_hidden_owner_group(chat_id, user_id)
    await safe_send_markdown(context.bot, user_id, "✅ تم تسجيلك كمالك مخفي")

async def security_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']: return
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id): await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح"); return
    settings = await db_get_security_settings(chat_id)
    text = "🔐 **إعدادات الأمان**\n━━━━━━━━━━━━━━\n"
    def st(v): return "✅" if v else "❌"
    text += f"🔗 الروابط: {st(settings.get('delete_links',0))}\n@ المعرفات: {st(settings.get('mentions',0))}\n"
    text += f"⏱️ البطيء: {st(settings.get('slow_mode',0))}\n🎯 الترحيب: {st(settings.get('welcome_enabled',0))}\n"
    text += f"👋 الوداع: {st(settings.get('goodbye_enabled',0))}\n🎬 فيديو: {st(settings.get('delete_videos',0))}\n"
    text += f"🎵 صوت: {st(settings.get('delete_audio',0))}\n🎞️ متحرك: {st(settings.get('delete_animation',0))}\n"
    text += f"📏 الطول: {settings.get('max_message_length',0) or 'غير محدود'}\n⚖️ العقوبة: {settings.get('auto_penalty','none')}"
    await safe_send_markdown(context.bot, user_id, text, reply_markup=security_keyboard(chat_id))

async def panel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']: return
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id): return
    locked = await is_chat_locked(chat_id)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 قفل" if not locked else "🔓 فتح", callback_data=f"panel:lock:{chat_id}" if not locked else f"panel:unlock:{chat_id}"),
         InlineKeyboardButton("🛠️ متقدم", callback_data=f"advanced_actions:{chat_id}")],
        [InlineKeyboardButton("🔙 إغلاق", callback_data=CallbackData.PANEL_CLOSE)]
    ])
    await safe_send_markdown(context.bot, user_id, f"🔧 لوحة تحكم {update.effective_chat.title}", reply_markup=kb)

async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_send_markdown(context.bot, update.effective_user.id,
        "❓ **المساعدة**\n/start - الرئيسية\n/syncgroup - تفعيل مجموعة\n/security - الأمان\n/panel - لوحة تحكم\n/lock - قفل\n/unlock - فتح\n/ban - حظر\n/mute - كتم\n/warn - تحذير\n/schedule - جدولة\n/stats - إحصائيات\n/contests - مسابقات\n/support - دعم\n/language - لغة")

async def trial_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await db_has_used_trial(user_id): await safe_send_markdown(context.bot, user_id, "❌ استخدمت التجربة"); return
    if await db_has_active_subscription(user_id): await safe_send_markdown(context.bot, user_id, "✅ لديك اشتراك"); return
    await db_activate_trial(user_id)
    await safe_send_markdown(context.bot, user_id, "🎁 تم تفعيل 30 يوم مجاناً!")

async def subscribe_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await db_has_active_subscription(user_id):
        d = await db_get_subscription_days_left(user_id)
        await safe_send_markdown(context.bot, user_id, f"✅ متبقي {d} يوم"); return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ 1 يوم - 5⭐", callback_data=CallbackData.BUY_SUBSCRIPTION_1),
         InlineKeyboardButton("⭐ 2 يوم - 9⭐", callback_data=CallbackData.BUY_SUBSCRIPTION_2)],
        [InlineKeyboardButton("⭐ شهر - 50⭐", callback_data=CallbackData.BUY_SUBSCRIPTION_30),
         InlineKeyboardButton("⭐ 3 أشهر - 120⭐", callback_data=CallbackData.BUY_SUBSCRIPTION_90)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, user_id, "💎 **اختر الباقة**", reply_markup=kb)

async def support_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['support_mode'] = True
    await safe_send_markdown(context.bot, user_id, "📞 أرسل رسالتك وسنرد عليك")

async def rank_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async def _g(conn):
        cur = await conn.execute("SELECT points, level FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return (row[0] or 0, row[1] or 1) if row else (0, 1)
    pts, lvl = await execute_db(_g)
    await safe_send_markdown(context.bot, user_id, f"📊 **رتبتك**\n🎖️ المستوى: {lvl}\n⭐ النقاط: {pts}")

async def top_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async def _g(conn):
        cur = await conn.execute("SELECT user_id, points, level FROM users WHERE banned=0 ORDER BY points DESC LIMIT 10")
        return await cur.fetchall()
    users = await execute_db(_g)
    if not users: await safe_send_markdown(context.bot, update.effective_user.id, "📭 لا يوجد"); return
    text = "🏆 **أفضل 10**\n"
    for i, (uid, pts, lvl) in enumerate(users, 1):
        m = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
        text += f"{m} `{uid}` - Lv.{lvl} ({pts}ن)\n"
    await safe_send_markdown(context.bot, update.effective_user.id, text)

async def stats_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active: await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة"); return
    stats = await db_get_channel_stats(active)
    ch = await db_get_channel_info(active)
    await safe_send_markdown(context.bot, user_id, f"📊 {ch[1] if ch else 'قناة'}\n📝 {stats['total_posts']}\n✅ {stats['published_posts']}\n⏳ {stats['unpublished_posts']}")

async def developer_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_send_markdown(context.bot, update.effective_user.id, "👨‍💻 @RelaxMgr\n📌 v22.2.0")

async def updates_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ch = await db_get_updates_channel()
    if ch: await safe_send_markdown(context.bot, update.effective_user.id, f"📢 @{ch}")
    else: await safe_send_markdown(context.bot, update.effective_user.id, "📢 لا توجد قناة")

async def sendcode_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        allowed = await db_get_allowed_sendcode_user()
        if user_id != allowed: await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح"); return
    await safe_send_markdown(context.bot, user_id, f"📨 `/start {secrets.token_urlsafe(8)}`")

async def lock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']: return
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id): return
    await db_set_chat_lock(chat_id, True, user_id)
    await safe_send_markdown(context.bot, chat_id, "🔒 تم قفل المجموعة")

async def unlock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']: return
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id): return
    await db_set_chat_lock(chat_id, False)
    await safe_send_markdown(context.bot, chat_id, "🔓 تم فتح المجموعة")

async def schedule_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = UserState.WAITING_SCHEDULE_POST
    await safe_send_markdown(context.bot, update.effective_user.id, "📝 أرسل: YYYY-MM-DD HH:MM النص")

async def set_rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']: return
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id): return
    args = context.args
    if not args: await safe_send_markdown(context.bot, chat_id, "📝 أرسل: /set_rules النص"); return
    rules = " ".join(args)
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO group_rules (chat_id, rules_text, updated_by, updated_at) VALUES (?,?,?,?)", (chat_id, rules, user_id, utc_now_iso())) or c.commit())
    await safe_send_markdown(context.bot, chat_id, "✅ تم")

async def rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']: return
    chat_id = update.effective_chat.id
    async def _g(conn):
        cur = await conn.execute("SELECT rules_text FROM group_rules WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        return row[0] if row else None
    rules = await execute_db(_g)
    await safe_send_markdown(context.bot, chat_id, rules or "📋 لا توجد قوانين")

async def create_contest_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id): return
    context.user_data['state'] = UserState.WAITING_CONTEST_TITLE
    await safe_send_markdown(context.bot, user_id, "📝 أرسل عنوان المسابقة:")

async def declare_winner_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id): return
    args = context.args
    if len(args) < 2: await safe_send_markdown(context.bot, user_id, "/declare_winner id winner"); return
    try:
        cid = int(args[0]); wid = int(args[1])
        contest = await db_get_contest(cid)
        if not contest or contest['status'] != 'active': await safe_send_markdown(context.bot, user_id, "❌"); return
        await db_set_contest_winner(cid, wid)
        await safe_send_markdown(context.bot, user_id, f"✅ الفائز: {wid}")
        try: await context.bot.send_message(wid, f"🏆 فزت في {contest['title']}!")
        except: pass
    except: await safe_send_markdown(context.bot, user_id, "❌ خطأ")

async def contests_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    contests = await db_get_active_contests_with_participants(10)
    if not contests: await safe_send_markdown(context.bot, user_id, "📭 لا توجد"); return
    text = "🏆 **المسابقات**\n"
    kb = []
    for c in contests:
        cid, title, desc, prize, end_date, ctype, participants = c[0], c[1], c[2], c[3], c[4], c[5], c[6]
        try: dl = (datetime.fromisoformat(end_date) - utc_now()).days; tl = f"⏳ {dl} يوم" if dl > 0 else "🔴 انتهت"
        except: tl = "📅"; dl = 0
        p = await db_get_user_participation(user_id, cid)
        text += f"📌 {title}\n🎁 {prize}\n👥 {participants}\n{tl}\n\n"
        if not p and dl > 0: kb.append([InlineKeyboardButton(f"شارك في {title[:20]}", callback_data=f"contest_join:{cid}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await safe_send_markdown(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(kb))

async def set_log_channel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id): return
    context.user_data['state'] = UserState.WAITING_LOG_CHANNEL
    await safe_send_markdown(context.bot, user_id, "📋 أرسل معرف القناة:")

async def handle_moderation_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type not in ['group', 'supergroup']: return
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id): return
    cmd = update.message.text.split()[0][1:]; args = context.args
    target_id = None; reason = ""
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        if args: reason = " ".join(args)
    elif args:
        try: target_id = int(args[0]); reason = " ".join(args[1:]) if len(args) > 1 else ""
        except: await safe_send_markdown(context.bot, chat_id, "❌ معرف غير صالح"); return
    else: await safe_send_markdown(context.bot, chat_id, "❌ ارد على رسالة أو أرسل معرف"); return
    if target_id == context.bot.id: return
    dur = 60 if cmd == 'mute' else None
    success, msg = await apply_penalty_with_duration(context.bot, chat_id, target_id, cmd, dur, reason, user_id)
    await safe_send_markdown(context.bot, chat_id, msg)

# ===================================================================
# 24. معالجات الكولباك
# ===================================================================
async def _answer_query(query):
    try: await query.answer()
    except: pass

async def _safe_edit(query, text, reply_markup=None):
    try: await safe_edit_markdown(query, text, reply_markup=reply_markup)
    except: pass

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await _answer_query(query)
    user_id = update.effective_user.id
    kb, title, active = await get_main_keyboard(user_id)
    if active: context.user_data['active_channel'] = active
    await _safe_edit(query, title, reply_markup=kb)

async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu_callback(update, context)

async def cancel_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await _answer_query(query)
    context.user_data.clear()
    await safe_send_markdown(context.bot, update.effective_user.id, "❌ تم الإلغاء")
    await main_menu_callback(update, context)

async def add_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    context.user_data['state'] = UserState.WAITING_CHANNEL_ID
    await _safe_edit(query, "📡 أرسل معرف القناة (@username أو -100...)")

async def my_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels: await _safe_edit(query, "📭 لا توجد قنوات"); return
    kb = []
    for ch_id, ch_tele_id, ch_name, banned in channels:
        st = "🚫" if banned else "✅"
        kb.append([InlineKeyboardButton(f"{st} {ch_name}", callback_data=f"channels:select:{ch_id}"),
                   InlineKeyboardButton("🗑️", callback_data=f"channels:delete:{ch_id}")])
    kb.append([InlineKeyboardButton("➕ إضافة", callback_data=CallbackData.CHANNELS_ADD)])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await _safe_edit(query, "📡 **قنواتي**", reply_markup=InlineKeyboardMarkup(kb))

async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    await db_delete_channel_by_id(user_id, ch_db_id)
    await _safe_edit(query, "✅ تم الحذف")
    await my_channels_callback(update, context)

async def select_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    await db_set_active_channel(user_id, ch_db_id)
    context.user_data['active_channel'] = ch_db_id
    await _safe_edit(query, "✅ تم التحديد")
    await main_menu_callback(update, context)

async def add_15_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
        await _safe_edit(query, "⚠️ اشتراكك منتهٍ"); return
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active: await _safe_edit(query, "⚠️ اختر قناة"); return
    unpub = await db_unpublished_count(active)
    if unpub >= MAX_UNPUBLISHED_POSTS: await _safe_edit(query, "⚠️ الحد الأقصى"); return
    target = min(15, MAX_UNPUBLISHED_POSTS - unpub)
    context.user_data[f"session_{user_id}"] = []
    context.user_data[f"session_target_{user_id}"] = target
    context.user_data['state'] = UserState.ADDING_POSTS
    await _safe_edit(query, f"📥 أرسل {target} منشور")

async def publish_one_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
        await _safe_edit(query, "⚠️ اشتراك منتهٍ"); return
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active: await _safe_edit(query, "⚠️ اختر قناة"); return
    post = await db_get_next_post(active)
    if not post: await _safe_edit(query, "📭 لا توجد منشورات"); return
    ch_info = await db_get_channel_info(active)
    if not ch_info: return
    channel_id = ch_info[0]
    try:
        if post['media_type'] == 'photo' and post['media_file_id']:
            await context.bot.send_photo(channel_id, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
        elif post['media_type'] == 'video' and post['media_file_id']:
            await context.bot.send_video(channel_id, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
        elif post['media_type'] == 'document' and post['media_file_id']:
            await context.bot.send_document(channel_id, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
        else: await context.bot.send_message(channel_id, post['text'][:4096] if post['text'] else ".")
        await db_mark_published(post['id'])
        await db_set_last_publish(active, utc_now())
        await db_update_next_publish_date(active)
        await _safe_edit(query, "✅ تم النشر")
    except Exception as e:
        await db_increment_fail_count(post['id'])
        await _safe_edit(query, f"❌ فشل: {str(e)[:100]}")

async def my_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active: await _safe_edit(query, "⚠️ اختر قناة"); return
    posts = await db_get_user_posts_for_channel(active, 15)
    if not posts: await _safe_edit(query, "📭 لا توجد"); return
    text = "📋 **منشوراتي**\n"
    kb = []
    for pid, ptext, mtype in posts[:10]:
        short = (ptext or "بدون نص")[:50]
        text += f"🆔 {pid}: {short}...\n"
        kb.append([InlineKeyboardButton(f"🗑️ حذف #{pid}", callback_data=f"posts:delete_single:{pid}_{active}")])
    kb.append([InlineKeyboardButton("🗑️ حذف الكل", callback_data=f"posts:confirm_clear_all:{active}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await _safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))

async def delete_single_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")[-1].split("_")
    if len(parts) >= 2:
        pid, active = int(parts[0]), int(parts[1])
        await db_delete_single_post(pid, user_id, active)
        await my_posts_callback(update, context)

async def confirm_clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    active = int(query.data.split(":")[-1])
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم", callback_data=f"posts:clear_all:{active}"),
         InlineKeyboardButton("❌ لا", callback_data=CallbackData.BACK)]
    ])
    await _safe_edit(query, "⚠️ متأكد من حذف الكل؟", reply_markup=kb)

async def clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    active = int(query.data.split(":")[-1])
    await execute_db(lambda c: c.execute("DELETE FROM posts WHERE channel_db_id=?", (active,)) or c.commit())
    await _safe_edit(query, "✅ تم الحذف")

async def recycle_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if active:
        await db_reset_posts_to_unpublished(active)
        await _safe_edit(query, "♻️ تم")

async def publish_all_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels: return
    for ch_db_id, ch_tele_id, ch_name, banned in channels:
        if banned: continue
        post = await db_get_next_post(ch_db_id)
        if not post: continue
        try:
            if post['media_type'] == 'photo' and post['media_file_id']:
                await context.bot.send_photo(ch_tele_id, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
            else: await context.bot.send_message(ch_tele_id, post['text'][:4096] if post['text'] else ".")
            await db_mark_published(post['id'])
            await db_set_last_publish(ch_db_id, utc_now())
            await db_update_next_publish_date(ch_db_id)
        except: await db_increment_fail_count(post['id'])
        await asyncio.sleep(1)
    await safe_send_markdown(context.bot, user_id, "✅ تم النشر للكل")

async def pending_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    u = await db_get_user_unpublished_posts(user_id)
    t = await db_get_user_total_posts(user_id)
    await _safe_edit(query, f"📊 غير المنشورة: {u}\n📋 الإجمالي: {t}")

async def full_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    ch = await db_get_user_channels_count(user_id)
    t = await db_get_user_total_posts(user_id)
    u = await db_get_user_unpublished_posts(user_id)
    g = await db_get_user_groups_count(user_id)
    await _safe_edit(query, f"📈 قنوات: {ch}\n📝 منشورات: {t}\n⏳ غير منشورة: {u}\n👥 مجموعات: {g}")

async def my_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    uid = update.effective_user.id
    groups = await db_get_user_groups(uid)
    valid = [(cid, cn, un, b) for cid, cn, un, b in groups if await is_authorized_in_group(context.bot, cid, uid)]
    if not valid:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ أضف", url=f"https://t.me/{BOT_USERNAME}?startgroup")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        await _safe_edit(query, "📭 لا توجد", reply_markup=kb); return
    kb = []
    for chat_id, chat_name, _, banned in valid:
        st = "⛔" if banned else "✅"
        kb.append([InlineKeyboardButton(f"{st} {chat_name[:25]}", callback_data=f"groups:settings:{chat_id}")])
        kb.append([InlineKeyboardButton("🔐 أمان", callback_data=f"security_select_group:{chat_id}"),
                    InlineKeyboardButton("📜 سجل", callback_data=f"group_action:log:{chat_id}"),
                    InlineKeyboardButton("⚙️ متقدم", callback_data=f"advanced_actions:{chat_id}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await _safe_edit(query, "👥 **مجموعاتي**", reply_markup=InlineKeyboardMarkup(kb))

async def group_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, uid): return
    settings = await db_get_security_settings(chat_id)
    text = "🔐 **إعدادات الأمان**\n━━━━━━━━━━━━━━\n"
    def st(v): return "✅" if v else "❌"
    text += f"🔗 الروابط: {st(settings.get('delete_links',0))}\n@ المعرفات: {st(settings.get('mentions',0))}\n"
    text += f"⏱️ البطيء: {st(settings.get('slow_mode',0))}\n🎯 الترحيب: {st(settings.get('welcome_enabled',0))}\n"
    text += f"👋 الوداع: {st(settings.get('goodbye_enabled',0))}\n🎬 فيديو: {st(settings.get('delete_videos',0))}\n"
    text += f"🎵 صوت: {st(settings.get('delete_audio',0))}\n🎞️ متحرك: {st(settings.get('delete_animation',0))}\n"
    text += f"📄 ملفات: {st(settings.get('delete_documents',0))}\n🖼️ ملصقات: {st(settings.get('delete_stickers',0))}\n"
    text += f"📨 معاد: {st(settings.get('delete_forwarded',0))}\n🌊 فيضان: {st(settings.get('antiflood_enabled',0))}\n"
    text += f"🌙 ليلي: {st(settings.get('night_mode_enabled',0))}\n⚖️ العقوبة: {settings.get('auto_penalty','none')}"
    await _safe_edit(query, text, reply_markup=security_keyboard(chat_id))

async def settings_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    auto = "✅" if await db_auto_status(user_id) else "❌"
    rec = "✅" if await db_get_auto_recycle(user_id) else "❌"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⚙️ نشر تلقائي: {auto}", callback_data=CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH)],
        [InlineKeyboardButton(f"♻️ تدوير: {rec}", callback_data=CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    await _safe_edit(query, "⚙️ **الإعدادات**", reply_markup=kb)

async def toggle_auto_publish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    cur = await db_auto_status(user_id)
    await db_set_auto(user_id, not cur)
    await settings_menu_callback(update, context)

async def toggle_auto_recycle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    cur = await db_get_auto_recycle(user_id)
    await db_set_auto_recycle(user_id, not cur)
    await settings_menu_callback(update, context)

# ===================================================================
# 25. معالج الأمان - زر التبديل
# ===================================================================
async def security_toggle_setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 3: return
    action = parts[1]
    try: chat_id = int(parts[2])
    except: return
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True); return
    
    field_map = {
        "links": "delete_links", "mentions": "mentions", "slow_mode": "slow_mode",
        "delete_videos": "delete_videos", "delete_audio": "delete_audio",
        "delete_animation": "delete_animation", "delete_service": "delete_service",
        "delete_documents": "delete_documents", "delete_stickers": "delete_stickers",
        "delete_forwarded": "delete_forwarded", "delete_polls": "delete_polls",
        "delete_games": "delete_games", "delete_voice": "delete_voice",
        "delete_video_note": "delete_video_note",
        "welcome_enabled": "welcome_enabled", "goodbye_enabled": "goodbye_enabled",
        "antiflood": "antiflood_enabled", "night_mode": "night_mode_enabled",
    }
    
    if action in field_map:
        col = field_map[action]
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        current = settings.get(col, 0)
        new_value = 1 if current == 0 else 0
        await db_set_security_settings(chat_id, **{col: new_value})
        
        # تأكيد التغيير
        status_text = "✅ مفعل" if new_value else "❌ معطل"
        await query.answer(f"تم تغيير {action} إلى {status_text}", show_alert=True)
        
        # تحديث اللوحة
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        text = "🔐 **إعدادات الأمان**\n━━━━━━━━━━━━━━\n"
        def st(v): return "✅" if v else "❌"
        text += f"🔗 الروابط: {st(settings.get('delete_links',0))}\n@ المعرفات: {st(settings.get('mentions',0))}\n"
        text += f"⏱️ البطيء: {st(settings.get('slow_mode',0))}\n🎯 الترحيب: {st(settings.get('welcome_enabled',0))}\n"
        text += f"👋 الوداع: {st(settings.get('goodbye_enabled',0))}\n🎬 فيديو: {st(settings.get('delete_videos',0))}\n"
        text += f"🎵 صوت: {st(settings.get('delete_audio',0))}\n🎞️ متحرك: {st(settings.get('delete_animation',0))}\n"
        text += f"📄 ملفات: {st(settings.get('delete_documents',0))}\n🖼️ ملصقات: {st(settings.get('delete_stickers',0))}\n"
        text += f"📨 معاد: {st(settings.get('delete_forwarded',0))}\n🌊 فيضان: {st(settings.get('antiflood_enabled',0))}\n"
        text += f"🌙 ليلي: {st(settings.get('night_mode_enabled',0))}\n⚖️ العقوبة: {settings.get('auto_penalty','none')}"
        try: await query.edit_message_text(text=text, reply_markup=security_keyboard(chat_id))
        except: pass
    elif action == "max_length":
        context.user_data['state'] = UserState.WAITING_MAX_LENGTH
        context.user_data['security_chat_id'] = chat_id
        await query.edit_message_text(text="📏 أرسل الحد الأقصى لطول الرسالة (0 = غير محدود):")
    elif action == "banned_words_menu":
        await query.edit_message_text(text="🚫 **الكلمات المحظورة**", reply_markup=get_group_banned_words_keyboard(chat_id))
    elif action == "enable_all":
        await db_set_security_settings(chat_id, delete_videos=1, delete_audio=1, delete_animation=1, delete_service=1, delete_documents=1, delete_stickers=1, delete_forwarded=1, delete_polls=1, delete_games=1, delete_voice=1, delete_video_note=1)
        await group_settings_callback(update, context)
    elif action == "disable_all":
        await db_set_security_settings(chat_id, delete_videos=0, delete_audio=0, delete_animation=0, delete_service=0, delete_documents=0, delete_stickers=0, delete_forwarded=0, delete_polls=0, delete_games=0, delete_voice=0, delete_video_note=0)
        await group_settings_callback(update, context)
    elif action == "delete_penalty":
        await query.edit_message_text(text="⚖️ اختر العقوبة:", reply_markup=penalty_keyboard(chat_id))

# ===================================================================
# 26. معالجات إضافية
# ===================================================================
async def security_banned_words_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    await _safe_edit(query, "🚫 **الكلمات المحظورة**", reply_markup=get_group_banned_words_keyboard(chat_id))

async def banned_words_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_GROUP_BANNED_WORD
    context.user_data['banned_words_chat_id'] = chat_id
    await _safe_edit(query, "✏️ أرسل الكلمة:")

async def banned_words_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    words = await db_get_banned_words(chat_id)
    if not words: await _safe_edit(query, "📭 لا توجد"); return
    text = "🚫 **الكلمات المحظورة**\n"
    for w, _, _ in words: text += f"• `{w}`\n"
    await _safe_edit(query, text)

async def banned_words_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_REMOVE_GROUP_BANNED_WORD
    context.user_data['banned_words_chat_id'] = chat_id
    await _safe_edit(query, "✏️ أرسل الكلمة للحذف:")

async def security_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    try: await query.message.delete()
    except: pass

async def security_select_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    await my_groups_callback(update, context)

async def security_refresh_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await my_groups_callback(update, context)

async def penalty_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    await _safe_edit(query, "⚖️ اختر العقوبة:", reply_markup=penalty_keyboard(chat_id))

async def _set_penalty(update, context, penalty):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    await db_set_security_settings(chat_id, auto_penalty=penalty)
    await _safe_edit(query, f"✅ تم تعيين {penalty}")

async def penalty_kick_callback(update, context): await _set_penalty(update, context, 'kick')
async def penalty_ban_callback(update, context): await _set_penalty(update, context, 'ban')
async def penalty_mute_callback(update, context): await _set_penalty(update, context, 'mute')
async def penalty_warn_callback(update, context): await _set_penalty(update, context, 'warn')
async def penalty_restrict_callback(update, context): await _set_penalty(update, context, 'restrict')
async def penalty_none_callback(update, context): await _set_penalty(update, context, 'none')

async def advanced_actions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    await _safe_edit(query, "🛠️ إجراءات متقدمة:", reply_markup=get_advanced_group_actions_keyboard(chat_id))

async def group_action_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_BAN_USER
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "🚫 أرسل معرف المستخدم:")

async def group_action_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    await _safe_edit(query, "🔇 اختر المدة:", reply_markup=get_advanced_mute_duration_keyboard(chat_id))

async def advanced_mute_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    parts = query.data.split(":")
    minutes = int(parts[1]); chat_id = int(parts[2])
    context.user_data['mute_minutes'] = minutes if minutes > 0 else None
    context.user_data['state'] = UserState.WAITING_MUTE_USER
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, f"🔇 كتم {minutes} دقيقة\nأرسل معرف المستخدم:")

async def group_action_warn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_WARN_USER
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "⚠️ أرسل معرف المستخدم:")

async def group_action_kick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_KICK_USER
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "👢 أرسل معرف المستخدم:")

async def group_action_restrict_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_RESTRICT_USER
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "🔒 أرسل معرف المستخدم:")

async def group_action_pin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_PIN_MESSAGE
    await _safe_edit(query, "📌 ارد على الرسالة ثم أرسل /pin")

async def group_action_log_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    await _safe_edit(query, "📜 سجل الإجراءات\nقيد التطوير")

async def group_action_unban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await _answer_query(query)
    chat_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_UNBAN_USER
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "🔓 أرسل معرف المستخدم:")

# ===================================================================
# 27. معالج الأزرار العام
# ===================================================================
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الموزع الرئيسي لجميع ضغطات الأزرار"""
    query = update.callback_query
    data = query.data
    if not data:
        return

    if data == "noop":
        await _answer_query(query)
        return

    try:
        # ===== التنقل الأساسي =====
        if data == CallbackData.MAIN_MENU:
            return await main_menu_callback(update, context)
        if data == CallbackData.BACK:
            return await back_callback(update, context)
        if data == CallbackData.CANCEL_SESSION:
            return await cancel_session_callback(update, context)

        # ===== القنوات =====
        if data == CallbackData.CHANNELS_ADD:
            return await add_channel_callback(update, context)
        if data == CallbackData.CHANNELS_MY:
            return await my_channels_callback(update, context)
        if data.startswith("channels:delete:"):
            return await delete_channel_callback(update, context)
        if data.startswith("channels:select:"):
            return await select_channel_callback(update, context)

        # ===== المنشورات =====
        if data == CallbackData.POSTS_ADD_15:
            return await add_15_posts_callback(update, context)
        if data == CallbackData.POSTS_PUBLISH_ONE:
            return await publish_one_callback(update, context)
        if data == CallbackData.POSTS_MY:
            return await my_posts_callback(update, context)
        if data == CallbackData.POSTS_RECYCLE:
            return await recycle_posts_callback(update, context)
        if data.startswith("posts:delete_single:"):
            return await delete_single_post_callback(update, context)
        if data.startswith("posts:confirm_clear_all:"):
            return await confirm_clear_all_posts_callback(update, context)
        if data.startswith("posts:clear_all:"):
            return await clear_all_posts_callback(update, context)
        if data == CallbackData.PUBLISH_ALL_CHANNELS:
            return await publish_all_channels_callback(update, context)

        # ===== الإحصائيات =====
        if data == CallbackData.STATS_PENDING:
            return await pending_stats_callback(update, context)
        if data == CallbackData.STATS_FULL:
            return await full_stats_callback(update, context)
        if data.startswith("channel_stats:"):
            return await channel_stats_callback(update, context)
        if data == CallbackData.MY_CHANNEL_STATS:
            return await my_channel_stats_callback(update, context)

        # ===== المجموعات =====
        if data == CallbackData.GROUPS_MY:
            return await my_groups_callback(update, context)
        if data.startswith("groups:settings:"):
            return await group_settings_callback(update, context)
        if data.startswith("delete_group:"):
            return await delete_group_callback(update, context)

        # ===== الإعدادات =====
        if data == CallbackData.SETTINGS_MENU:
            return await settings_menu_callback(update, context)
        if data == CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH:
            return await toggle_auto_publish_callback(update, context)
        if data == CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE:
            return await toggle_auto_recycle_callback(update, context)

        # ===== الجدولة =====
        if data.startswith("schedule:menu:"):
            return await schedule_menu_callback(update, context)
        if data.startswith("schedule:set_interval_minutes:"):
            return await set_interval_minutes_callback(update, context)
        if data.startswith("schedule:set_interval_hours:"):
            return await set_interval_hours_callback(update, context)
        if data.startswith("schedule:set_interval_days:"):
            return await set_interval_days_callback(update, context)
        if data.startswith("schedule:set_days:"):
            return await set_days_callback(update, context)
        if data.startswith("schedule:set_dates:"):
            return await set_dates_callback(update, context)
        if data.startswith("schedule:set_publish_time:"):
            return await set_publish_time_callback(update, context)
        if data.startswith("schedule:set_cron:"):
            return await set_cron_callback(update, context)
        if data.startswith("schedule:day_select:"):
            return await day_select_callback(update, context)
        if data == CallbackData.SCHEDULE_SAVE_DAYS:
            return await save_days_callback(update, context)

        # ===== الأمان (التبديل) =====
        if data.startswith("security:") and len(data.split(":")) >= 3:
            # التأكد من أن المقطع الثاني هو إجراء معروف للتبديل
            action = data.split(":")[1]
            if action in [
                "links", "mentions", "slow_mode", "delete_videos", "delete_audio",
                "delete_animation", "delete_service", "delete_documents", "delete_stickers",
                "delete_forwarded", "delete_polls", "delete_games", "delete_voice",
                "delete_video_note", "welcome_enabled", "goodbye_enabled", "antiflood",
                "night_mode", "max_length", "warn_settings", "delete_penalty", "enable_all", "disable_all"
            ]:
                return await security_toggle_setting_callback(update, context)
        if data == CallbackData.SECURITY_CLOSE:
            return await security_close_callback(update, context)
        if data.startswith("security_select_group:"):
            return await security_select_group_callback(update, context)
        if data == CallbackData.SECURITY_REFRESH_GROUPS:
            return await security_refresh_groups_callback(update, context)
        if data.startswith("security:banned_words_menu:"):
            return await security_banned_words_menu_callback(update, context)

        # ===== الكلمات المحظورة =====
        if data.startswith("banned_words:add:"):
            return await banned_words_add_callback(update, context)
        if data.startswith("banned_words:list:"):
            return await banned_words_list_callback(update, context)
        if data.startswith("banned_words:remove:"):
            return await banned_words_remove_callback(update, context)

        # ===== العقوبات =====
        if data.startswith("penalty_menu:"):
            return await penalty_menu_callback(update, context)
        if data.startswith("penalty:kick:"):
            return await penalty_kick_callback(update, context)
        if data.startswith("penalty:ban:"):
            return await penalty_ban_callback(update, context)
        if data.startswith("penalty:mute:"):
            return await penalty_mute_callback(update, context)
        if data.startswith("penalty:warn:"):
            return await penalty_warn_callback(update, context)
        if data.startswith("penalty:restrict:"):
            return await penalty_restrict_callback(update, context)
        if data.startswith("penalty:none:"):
            return await penalty_none_callback(update, context)

        # ===== الإجراءات المتقدمة =====
        if data.startswith("advanced_actions:"):
            return await advanced_actions_callback(update, context)
        if data.startswith("group_action:ban:"):
            return await group_action_ban_callback(update, context)
        if data.startswith("group_action:mute:"):
            return await group_action_mute_callback(update, context)
        if data.startswith("adv_mute_duration:"):
            return await advanced_mute_duration_callback(update, context)
        if data.startswith("group_action:warn:"):
            return await group_action_warn_callback(update, context)
        if data.startswith("group_action:kick:"):
            return await group_action_kick_callback(update, context)
        if data.startswith("group_action:restrict:"):
            return await group_action_restrict_callback(update, context)
        if data.startswith("group_action:pin:"):
            return await group_action_pin_callback(update, context)
        if data.startswith("group_action:log:"):
            return await group_action_log_callback(update, context)
        if data.startswith("group_action:unban:"):
            return await group_action_unban_callback(update, context)

        # ===== لوحة التحكم (قفل/فتح) =====
        if data.startswith("panel:lock:"):
            chat_id = int(data.split(":")[-1])
            await db_set_chat_lock(chat_id, True, update.effective_user.id)
            await _answer_query(query)
            await group_settings_callback(update, context)
            return
        if data.startswith("panel:unlock:"):
            chat_id = int(data.split(":")[-1])
            await db_set_chat_lock(chat_id, False)
            await _answer_query(query)
            await group_settings_callback(update, context)
            return
        if data == CallbackData.PANEL_CLOSE:
            await _answer_query(query)
            try:
                await query.message.delete()
            except:
                pass
            return

        # ===== المساعدة والدعم =====
        if data == CallbackData.HELP:
            return await help_command_handler(update, context)
        if data == CallbackData.SUPPORT_MENU:
            return await support_command_handler(update, context)
        if data == CallbackData.SUPPORT_HELP:
            await _answer_query(query)
            await safe_send_markdown(context.bot, update.effective_user.id, "❓ الدعم")
            return
        if data == CallbackData.SUPPORT_TICKET:
            await _answer_query(query)
            context.user_data['support_mode'] = True
            await safe_send_markdown(context.bot, update.effective_user.id, "📝 أرسل رسالتك")
            return

        # ===== التجربة والاشتراك =====
        if data == CallbackData.TRIAL:
            return await trial_callback(update, context)
        if data == CallbackData.SUBSCRIBE_MENU:
            return await subscribe_menu_callback(update, context)
        if data == CallbackData.BUY_SUBSCRIPTION_1:
            return await buy_subscription_1_callback(update, context)
        if data == CallbackData.BUY_SUBSCRIPTION_2:
            return await buy_subscription_2_callback(update, context)
        if data == CallbackData.BUY_SUBSCRIPTION_30:
            return await buy_subscription_30_callback(update, context)
        if data == CallbackData.BUY_SUBSCRIPTION_90:
            return await buy_subscription_90_callback(update, context)

        # ===== المطور والتحديثات =====
        if data == CallbackData.DEVELOPER:
            return await developer_command_handler(update, context)
        if data == CallbackData.UPDATES:
            return await updates_command_handler(update, context)

        # ===== الإحالات =====
        if data == CallbackData.REFERRAL_MENU:
            return await referral_menu_callback(update, context)
        if data.startswith("referral:copy_link:"):
            return await referral_copy_link_callback(update, context)
        if data == CallbackData.REFERRAL_CLAIM_REWARD:
            return await referral_claim_reward_callback(update, context)
        if data == CallbackData.REFERRAL_LIST:
            return await referral_list_callback(update, context)

        # ===== التذكيرات =====
        if data == CallbackData.REMINDER_MENU:
            return await reminder_menu_callback(update, context)
        if data == CallbackData.REMINDER_TOGGLE_SUB:
            return await reminder_toggle_sub_callback(update, context)
        if data == CallbackData.REMINDER_TOGGLE_DAILY:
            return await reminder_toggle_daily_callback(update, context)
        if data == CallbackData.REMINDER_TOGGLE_WEEKLY:
            return await reminder_toggle_weekly_callback(update, context)
        if data == CallbackData.REMINDER_SET_DAYS:
            return await reminder_set_days_callback(update, context)
        if data == CallbackData.REMINDER_SET_LANG:
            return await reminder_set_lang_callback(update, context)
        if data.startswith("reminder:lang:"):
            return await reminder_lang_callback(update, context)

        # ===== الترجمة =====
        if data == CallbackData.TRANSLATION_MENU:
            return await translation_menu_callback(update, context)
        if data == CallbackData.TRANSLATION_OFF:
            return await translation_off_callback(update, context)
        if data.startswith("translation:set:"):
            return await translation_set_callback(update, context)

        # ===== المسابقات =====
        if data == CallbackData.CONTESTS_MENU:
            return await contests_command_handler(update, context)
        if data.startswith("contest_join:"):
            return await contest_join_callback(update, context)
        if data == CallbackData.CONTEST_WINNERS:
            return await contest_winners_callback(update, context)

        # ===== NSFW =====
        if data == CallbackData.NSFW_SETTINGS:
            return await nsfw_settings_callback(update, context)
        if data == CallbackData.NSFW_TOGGLE:
            return await nsfw_toggle_callback(update, context)
        if data == CallbackData.NSFW_THRESHOLD_SET:
            return await nsfw_threshold_set_callback(update, context)

        # ===== الردود التلقائية (المجموعة) =====
        if data.startswith("auto_reply_menu:"):
            return await auto_reply_menu_callback(update, context)
        if data.startswith("auto_reply_toggle:"):
            return await auto_reply_toggle_callback(update, context)
        if data.startswith("auto_reply_admins:"):
            return await auto_reply_admins_callback(update, context)
        if data.startswith("auto_reply_reset:"):
            return await auto_reply_reset_callback(update, context)
        if data.startswith("auto_reply_confirm_reset:"):
            return await auto_reply_confirm_reset_callback(update, context)
        if data.startswith("auto_reply_cancel:"):
            return await auto_reply_cancel_callback(update, context)
        if data.startswith("auto_reply_stats:"):
            return await auto_reply_stats_callback(update, context)
        if data.startswith("user_auto_reply_toggle:"):
            return await user_auto_reply_toggle_callback(update, context)

        # ===== التحقق من الاشتراك الإجباري =====
        if data == CallbackData.CHECK_SUBSCRIBE:
            return await check_subscribe_callback_handler(update, context)

        # ===== تغيير اللغة =====
        if data.startswith("lang_"):
            return await language_callback(update, context)

        # ===== أزرار نصية عامة =====
        if data in ["rank", "top", "schedule_post", "language"]:
            if data == "rank":
                return await rank_command_handler(update, context)
            if data == "top":
                return await top_command_handler(update, context)
            if data == "schedule_post":
                context.user_data['state'] = UserState.WAITING_SCHEDULE_POST
                await safe_send_markdown(context.bot, update.effective_user.id, "📝 أرسل: YYYY-MM-DD HH:MM النص")
                return
            if data == "language":
                return await language_command_handler(update, context)

        # ===== لوحة الأدمن =====
        if data == CallbackData.ADMIN_PANEL:
            user_id = update.effective_user.id
            if user_id == PRIMARY_OWNER_ID or await is_bot_admin(user_id):
                await _safe_edit(query, "👑 لوحة التحكم", reply_markup=get_admin_keyboard(user_id))
            return
        if data.startswith("admin:") or data.startswith("confirm_restore:"):
            return await admin_router_callback(update, context)

        # ===== غير معروف =====
        await _answer_query(query)
        logger.warning(f"بيانات كولباك غير معروفة: {data}")

    except Exception as e:
        error_id = log_error(e)
        try:
            await _answer_query(query)
            await safe_send_markdown(context.bot, update.effective_user.id, f"❌ خطأ: `{error_id}`")
        except:
            pass

# ===================================================================
# 28. دوال الأدمن المساعدة
# ===================================================================
async def admin_router_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; data = query.data
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id): return
    await query.answer()
    
    if data == CallbackData.ADMIN_USERS:
        total, banned, _, _, _ = await db_stats()
        await _safe_edit(query, f"👥 المستخدمين: {total}\n🚫 محظورين: {banned}")
    elif data == CallbackData.ADMIN_BANNED_USERS:
        await _safe_edit(query, "🚫 المحظورين\nقيد التطوير")
    elif data == CallbackData.ADMIN_UNBAN_ALL_USERS:
        await execute_db(lambda c: c.execute("UPDATE users SET banned=0") or c.commit())
        await _safe_edit(query, "✅ تم فك حظر الجميع")
    elif data == CallbackData.ADMIN_ALL_CHANNELS:
        cnt = await db_get_user_channels_count(0)
        await _safe_edit(query, f"📡 القنوات\nقيد التطوير")
    elif data == CallbackData.ADMIN_GROUPS:
        await _safe_edit(query, "👥 المجموعات\nقيد التطوير")
    elif data == CallbackData.ADMIN_ADD_ADMIN:
        context.user_data['state'] = UserState.WAITING_ADMIN_ID_ADD
        await _safe_edit(query, "👑 أرسل معرف المشرف:")
    elif data == CallbackData.ADMIN_REMOVE_ADMIN:
        context.user_data['state'] = UserState.WAITING_ADMIN_ID_REMOVE
        await _safe_edit(query, "🗑️ أرسل معرف المشرف:")
    elif data == CallbackData.ADMIN_RAM:
        ram = get_ram_usage()
        await _safe_edit(query, f"💾 {ram['used']:.1f}/{ram['total']:.1f} GB ({ram['percent']}%)")
    elif data == CallbackData.ADMIN_STATS:
        total, banned, posts, groups, channels = await db_stats()
        await _safe_edit(query, f"👥 {total} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}")
    elif data == CallbackData.ADMIN_METRICS:
        ram = get_ram_usage()
        await _safe_edit(query, f"💾 {ram['percent']}%\n🔄 {task_manager.get_task_count()} مهمة")
    elif data == CallbackData.ADMIN_BACKUP:
        try:
            backup_file = await create_backup()
            await safe_send_markdown(context.bot, user_id, f"✅ {backup_file.name}")
        except Exception as e:
            await safe_send_markdown(context.bot, user_id, f"❌ {str(e)[:100]}")
    elif data == CallbackData.ADMIN_RESTORE_BACKUP:
        backups = await list_backups()
        if not backups: await _safe_edit(query, "📭 لا توجد"); return
        text = "💾 اختر:\n"
        kb = []
        for i, b in enumerate(backups[:10], 1):
            text += f"{i}. {b.name}\n"
            kb.append([InlineKeyboardButton(f"{i}. {b.name[:30]}", callback_data=f"confirm_restore:{b.name}")])
        kb.append([InlineKeyboardButton("🔙", callback_data=CallbackData.ADMIN_PANEL)])
        await _safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("confirm_restore:"):
        backup_name = data.split(":")[-1]
        backup_path = BACKUP_DIR / backup_name
        try:
            await restore_backup(backup_path)
            await _safe_edit(query, "✅ تمت الاستعادة")
        except Exception as e:
            await _safe_edit(query, f"❌ {str(e)[:100]}")
    elif data == CallbackData.ADMIN_BACKUP_SETTINGS:
        auto = await db_get_auto_backup()
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("تبديل", callback_data=CallbackData.ADMIN_TOGGLE_AUTO_BACKUP)],
            [InlineKeyboardButton("🔙", callback_data=CallbackData.ADMIN_PANEL)]
        ])
        await _safe_edit(query, f"نسخ تلقائي: {'✅' if auto else '❌'}", reply_markup=kb)
    elif data == CallbackData.ADMIN_TOGGLE_AUTO_BACKUP:
        cur = await db_get_auto_backup()
        await db_set_setting('auto_backup', '0' if cur else '1')
        await admin_router_callback(update, context)
    elif data == CallbackData.ADMIN_SEND_UPDATE:
        context.user_data['state'] = UserState.WAITING_UPDATE_TEXT
        await _safe_edit(query, "📢 أرسل نص التحديث:")
    elif data == CallbackData.ADMIN_BROADCAST:
        context.user_data['state'] = UserState.WAITING_BROADCAST
        await _safe_edit(query, "📨 أرسل الرسالة:")
    elif data == CallbackData.ADMIN_CONFIRM_BROADCAST:
        broadcast_text = context.user_data.get('broadcast_text', '')
        if broadcast_text:
            users = await db_get_all_users()
            sent = 0
            for row in users:
                try: await context.bot.send_message(row[0], broadcast_text); sent += 1
                except: pass
                await asyncio.sleep(0.05)
            await _safe_edit(query, f"✅ تم: {sent}")
    elif data == CallbackData.ADMIN_SUPPORT_TICKETS:
        await _safe_edit(query, "📋 التذاكر\nقيد التطوير")
    elif data == CallbackData.ADMIN_DELETE_ALL_TICKETS:
        await execute_db(lambda c: c.execute("DELETE FROM support_tickets") or c.commit())
        await _safe_edit(query, "✅ تم")
    elif data == CallbackData.ADMIN_SHOW_LOG_CHANNEL:
        log_id = await db_get_log_channel_id()
        await _safe_edit(query, f"📋 {log_id}" if log_id else "📋 غير محدد")
    elif data == CallbackData.ADMIN_SET_LOG_CHANNEL:
        context.user_data['state'] = UserState.WAITING_LOG_CHANNEL
        await _safe_edit(query, "📋 أرسل معرف القناة:")
    elif data == CallbackData.ADMIN_REPLIES:
        await _safe_edit(query, "💬 الردود", reply_markup=get_replies_keyboard())
    elif data == CallbackData.ADMIN_ADD_REPLY:
        context.user_data['state'] = UserState.WAITING_KEYWORD
        await _safe_edit(query, "📝 أرسل الكلمة:")
    elif data == CallbackData.ADMIN_LIST_REPLIES:
        async def _g(conn):
            cur = await conn.execute("SELECT keyword, reply FROM auto_replies WHERE chat_id=0 LIMIT 50")
            return await cur.fetchall()
        replies = await execute_db(_g)
        if not replies: await _safe_edit(query, "📭 لا توجد"); return
        text = "💬 الردود:\n"
        for kw, rp in replies: text += f"• {kw} → {rp[:30]}...\n"
        await _safe_edit(query, text)
    elif data == CallbackData.ADMIN_DEL_REPLY:
        context.user_data['admin_del_reply'] = True
        context.user_data['state'] = UserState.WAITING_REPLY
        await _safe_edit(query, "🗑️ أرسل الكلمة:")
    elif data == CallbackData.ADMIN_BANNED_WORDS:
        await _safe_edit(query, "🚫 كلمات محظورة", reply_markup=get_banned_words_admin_keyboard())
    elif data == CallbackData.ADMIN_ADD_BANNED_WORD:
        context.user_data['state'] = UserState.WAITING_GLOBAL_BANNED_WORD
        await _safe_edit(query, "🚫 أرسل الكلمة:")
    elif data == CallbackData.ADMIN_LIST_BANNED_WORDS:
        words = await db_get_banned_words(-1)
        if not words: await _safe_edit(query, "📭 لا توجد"); return
        text = "🚫:\n"
        for w, _, _ in words[:50]: text += f"• {w}\n"
        await _safe_edit(query, text)
    elif data == CallbackData.ADMIN_REMOVE_BANNED_WORD:
        context.user_data['state'] = UserState.WAITING_REMOVE_GLOBAL_BANNED_WORD
        await _safe_edit(query, "🗑️ أرسل الكلمة:")
    elif data == CallbackData.ADMIN_FORCE_SUBSCRIBE:
        ch = await db_get_force_subscribe_channel()
        await _safe_edit(query, f"🔒 {'@'+ch if ch else 'غير محدد'}")
    elif data == CallbackData.ADMIN_SET_FORCE_CHANNEL:
        context.user_data['state'] = UserState.WAITING_FORCE_CHANNEL
        await _safe_edit(query, "🔒 أرسل معرف القناة:")
    elif data == CallbackData.ADMIN_MONITOR_USERS:
        total, banned, posts, groups, channels = await db_stats()
        await _safe_edit(query, f"👥 {total} | 🚫 {banned} | 📝 {posts} | 👥 {groups} | 📡 {channels}")
    elif data == CallbackData.ADMIN_UPDATES:
        ch = await db_get_updates_channel()
        await _safe_edit(query, f"📢 {'@'+ch if ch else 'غير محدد'}")
    elif data == CallbackData.ADMIN_SET_UPDATE_CHANNEL:
        context.user_data['state'] = UserState.WAITING_UPDATE_CHANNEL
        await _safe_edit(query, "📢 أرسل معرف القناة:")
    elif data == CallbackData.ADMIN_CREATE_CONTEST:
        context.user_data['state'] = UserState.WAITING_CONTEST_TITLE
        await _safe_edit(query, "📝 أرسل عنوان المسابقة:")
    elif data == CallbackData.ADMIN_DECLARE_WINNER:
        await _safe_edit(query, "🏆 /declare_winner id winner")
    else:
        await query.answer("⚠️ قيد التطوير", show_alert=True)

# ===================================================================
# 29. دوال إضافية للمفقودات
# ===================================================================
async def referral_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    stats = await db_get_referral_stats(user_id)
    code = await db_get_user_referral_code(user_id)
    text = f"🔗 رابطك: `https://t.me/{BOT_USERNAME}?start=ref_{code}`\n👥 {stats['total_referrals']} | 🎁 {stats['available_days']} يوم"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎁 صرف", callback_data=CallbackData.REFERRAL_CLAIM_REWARD)],
                               [InlineKeyboardButton("🔙", callback_data=CallbackData.BACK)]])
    await _safe_edit(query, text, reply_markup=kb)

async def referral_claim_reward_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    days = await db_claim_referral_reward(user_id)
    await _safe_edit(query, f"✅ {days} يوم" if days else "❌ لا يوجد")

async def reminder_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await _safe_edit(query, "⏰ التذكيرات\nقيد التطوير")

async def translation_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    lang = await get_user_translation_language(update.effective_user.id)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇸🇦 عربي", callback_data="translation:set:ar"),
         InlineKeyboardButton("🇬🇧 English", callback_data="translation:set:en")],
        [InlineKeyboardButton("🚫 إيقاف", callback_data=CallbackData.TRANSLATION_OFF)],
        [InlineKeyboardButton("🔙", callback_data=CallbackData.BACK)]
    ])
    await _safe_edit(query, f"🌐 الترجمة: {lang}", reply_markup=kb)

async def translation_off_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO user_translation VALUES (?, 'off')", (update.effective_user.id,)) or c.commit())
    await _safe_edit(query, "✅ تم الإيقاف")

async def translation_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    lang = query.data.split(":")[-1]
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO user_translation VALUES (?, ?)", (update.effective_user.id, lang)) or c.commit())
    await _safe_edit(query, f"✅ {lang}")

async def channel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    active = int(query.data.split(":")[-1])
    stats = await db_get_channel_stats(active)
    await _safe_edit(query, f"📊 {stats['total_posts']} | ✅ {stats['published_posts']} | ⏳ {stats['unpublished_posts']}")

async def my_channel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels: await _safe_edit(query, "📭"); return
    text = "📊 ملخص:\n"
    for ch_db_id, ch_tele_id, ch_name, banned in channels:
        unpub = await db_unpublished_count(ch_db_id)
        text += f"{'🚫' if banned else '✅'} {ch_name}: {unpub}\n"
    await _safe_edit(query, text)

async def nsfw_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await _safe_edit(query, "🔞 قيد التطوير")

async def nsfw_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await _safe_edit(query, "🔞 تم")

async def nsfw_threshold_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    context.user_data['state'] = UserState.WAITING_NSFW_THRESHOLD
    await _safe_edit(query, "📊 أرسل النسبة (0-100):")

async def auto_reply_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    chat_id = int(query.data.split(":")[-1])
    settings = await db_get_auto_reply_settings(chat_id)
    await _safe_edit(query, "📝 الردود التلقائية", reply_markup=get_auto_reply_keyboard(chat_id, settings))

async def auto_reply_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    chat_id = int(query.data.split(":")[-1])
    settings = await db_get_auto_reply_settings(chat_id)
    new_enabled = not settings.get('enabled', False)
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO auto_reply_settings (chat_id, enabled) VALUES (?, ?)", (chat_id, 1 if new_enabled else 0)) or c.commit())
    await _safe_edit(query, f"✅ {'مفعل' if new_enabled else 'معطل'}")

async def auto_reply_admins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    chat_id = int(query.data.split(":")[-1])
    settings = await db_get_auto_reply_settings(chat_id)
    new_admins = not settings.get('only_admins', False)
    await execute_db(lambda c: c.execute("INSERT OR REPLACE INTO auto_reply_settings (chat_id, only_admins) VALUES (?, ?)", (chat_id, 1 if new_admins else 0)) or c.commit())
    await _safe_edit(query, f"✅ {'مشرفين' if new_admins else 'الجميع'}")

async def auto_reply_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    chat_id = int(query.data.split(":")[-1])
    await execute_db(lambda c: c.execute("DELETE FROM auto_replies WHERE chat_id=?", (chat_id,)) or c.commit())
    await _safe_edit(query, "✅ تم التعيين")

async def auto_reply_confirm_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await _safe_edit(query, "✅ تم")

async def auto_reply_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await main_menu_callback(update, context)

async def auto_reply_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await _safe_edit(query, "📊 قيد التطوير")

async def user_auto_reply_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    async def _g(conn):
        cur = await conn.execute("SELECT auto_reply_enabled FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return bool(row[0]) if row else True
    cur = await execute_db(_g)
    await execute_db(lambda c: c.execute("UPDATE users SET auto_reply_enabled=? WHERE user_id=?", (0 if cur else 1, user_id)) or c.commit())
    await _safe_edit(query, f"✅ {'معطل' if cur else 'مفعل'}")

async def check_subscribe_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await main_menu_callback(update, context)

async def buy_subscription_1_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    try:
        await context.bot.send_invoice(update.effective_user.id, "يوم واحد", "اشتراك يوم", "sub_1", "", "XTR", [LabeledPrice("يوم", 5)])
    except: pass

async def buy_subscription_2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    try: await context.bot.send_invoice(update.effective_user.id, "يومين", "اشتراك يومين", "sub_2", "", "XTR", [LabeledPrice("يومين", 9)])
    except: pass

async def buy_subscription_30_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    try: await context.bot.send_invoice(update.effective_user.id, "شهر", "اشتراك شهر", "sub_30", "", "XTR", [LabeledPrice("شهر", 50)])
    except: pass

async def buy_subscription_90_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    try: await context.bot.send_invoice(update.effective_user.id, "3 أشهر", "اشتراك 3 أشهر", "sub_90", "", "XTR", [LabeledPrice("3 أشهر", 120)])
    except: pass

async def trial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await trial_command_handler(update, context)

async def subscribe_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await subscribe_command_handler(update, context)

async def contest_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    cid = int(query.data.split(":")[-1])
    context.user_data['contest_join_id'] = cid
    context.user_data['state'] = UserState.WAITING_CONTEST_ANSWER
    await safe_send_markdown(context.bot, update.effective_user.id, "📝 أرسل إجابتك:")

async def contest_winners_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await safe_send_markdown(context.bot, update.effective_user.id, "🏆 قيد التطوير")

# ===================================================================
# 30. دوال النسخ الاحتياطي
# ===================================================================
async def create_backup():
    try:
        temp_b = tempfile.NamedTemporaryFile(delete=False, suffix='.db'); temp_b.close()
        shutil.copy2(DB_PATH, temp_b.name)
        with open(temp_b.name, 'rb') as f: data = f.read()
        compressed = compress_backup(data)
        encrypted = BACKUP_CIPHER.encrypt(compressed)
        backup_file = BACKUP_DIR / f"backup_{mecca_now().strftime('%Y%m%d_%H%M%S')}.enc"
        backup_file.write_bytes(encrypted)
        os.unlink(temp_b.name)
        backups = sorted(BACKUP_DIR.glob("backup_*.enc"), key=lambda x: x.stat().st_mtime, reverse=True)
        for old in backups[MAX_BACKUPS:]: old.unlink()
        return backup_file
    except Exception as e: raise

async def incremental_backup():
    try:
        last = await db_get_last_backup_time()
        last_time = datetime.fromisoformat(last) if last else utc_now() - timedelta(days=7)
        backup_data = {}
        async def _gp(conn):
            cur = await conn.execute("SELECT * FROM posts WHERE created_at > ? LIMIT 1000", (last_time.isoformat(),))
            return [dict(row) for row in await cur.fetchall()]
        posts = await execute_db(_gp)
        if posts: backup_data['posts'] = posts
        if backup_data:
            data_json = json.dumps(backup_data, default=str)
            compressed = compress_backup(data_json.encode())
            encrypted = BACKUP_CIPHER.encrypt(compressed)
            f = BACKUP_DIR / f"incremental_{mecca_now().strftime('%Y%m%d_%H%M%S')}.inc"
            f.write_bytes(encrypted)
            return f
    except: return None

async def list_backups():
    return sorted(BACKUP_DIR.glob("backup_*.enc"), key=lambda x: x.stat().st_mtime, reverse=True) + sorted(BACKUP_DIR.glob("incremental_*.inc"), key=lambda x: x.stat().st_mtime, reverse=True)

async def restore_backup(backup_path: Path):
    if not backup_path.exists(): raise FileNotFoundError()
    encrypted = backup_path.read_bytes()
    decrypted = BACKUP_CIPHER.decrypt(encrypted)
    decompressed = decompress_backup(decrypted)
    if backup_path.suffix == '.inc':
        data = json.loads(decompressed.decode())
        async def _merge(conn):
            if 'posts' in data:
                for p in data['posts']:
                    await conn.execute("INSERT OR IGNORE INTO posts (id, channel_db_id, text, media_type, media_file_id, published, fail_count, created_at) VALUES (?,?,?,?,?,?,?,?)", (p['id'], p['channel_db_id'], p['text'], p['media_type'], p['media_file_id'], p['published'], p['fail_count'], p['created_at']))
            await conn.commit()
        await execute_db(_merge)
    else:
        temp_r = tempfile.NamedTemporaryFile(delete=False, suffix='.db'); temp_r.write(decompressed); temp_r.close()
        shutil.copy2(DB_PATH, BACKUP_DIR / f"pre_restore_{mecca_now().strftime('%Y%m%d_%H%M%S')}.db")
        shutil.copy2(temp_r.name, DB_PATH); os.unlink(temp_r.name)
        await db_pool.initialize()

# ===================================================================
# 31. معالج الرسائل
# ===================================================================
async def filter_messages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat: return
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    if update.effective_chat.type not in ['group', 'supergroup']: return
    if user_id == context.bot.id: return
    if await is_user_bot(context.bot, user_id): return
    
    bp = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bp.get('can_act'): return
    
    text = update.message.text or update.message.caption or ""
    
    if await is_chat_locked(chat_id) and not await is_authorized_in_group(context.bot, chat_id, user_id):
        try: await update.message.delete()
        except: pass; return
    
    if not await db_check_slow_mode(chat_id, user_id):
        try: await update.message.delete()
        except: pass; return
    
    settings = await db_get_security_settings(chat_id)
    
    if settings.get('delete_links') and text and contains_link(text):
        await delete_and_penalize(update, context, "🚫 روابط ممنوعة!"); return
    
    if settings.get('mentions') and text and contains_mention(text):
        await delete_and_penalize(update, context, "🚫 معرفات ممنوعة!"); return
    
    if settings.get('delete_banned_words') and text:
        word = await db_contains_banned_word(text, chat_id)
        if word: await delete_and_penalize(update, context, f"🚫 كلمة محظورة!"); return
    
    delete_media = False
    msg = update.message
    if settings.get('delete_videos') and msg.video: delete_media = True
    elif settings.get('delete_audio') and msg.audio: delete_media = True
    elif settings.get('delete_animation') and msg.animation: delete_media = True
    elif settings.get('delete_documents') and msg.document: delete_media = True
    elif settings.get('delete_stickers') and msg.sticker: delete_media = True
    elif settings.get('delete_forwarded') and msg.forward_date: delete_media = True
    elif settings.get('delete_polls') and msg.poll: delete_media = True
    elif settings.get('delete_voice') and msg.voice: delete_media = True
    elif settings.get('delete_video_note') and msg.video_note: delete_media = True
    
    if delete_media:
        try: await msg.delete()
        except: pass
        penalty = settings.get('delete_penalty', settings.get('auto_penalty', 'none'))
        if penalty != 'none': await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, settings.get('auto_mute_duration', 60))
        return
    
    max_len = settings.get('max_message_length', 0)
    if max_len > 0 and text and len(text) > max_len:
        try: await msg.delete()
        except: pass; return
    
    if settings.get('antiflood_enabled') and await db_check_antiflood(chat_id, user_id):
        try: await msg.delete()
        except: pass
        await apply_penalty_with_duration(context.bot, chat_id, user_id, settings.get('antiflood_penalty', 'mute'), 60); return
    
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
                    try: await msg.delete()
                    except: pass
                    await apply_penalty_with_duration(context.bot, chat_id, user_id, 'mute', 60); return
                elif action == 'delete':
                    try: await msg.delete()
                    except: pass; return
        except: pass
    
    # ردود تلقائية
    if text:
        ars = await db_get_auto_reply_settings(chat_id)
        if ars.get('enabled'):
            can_reply = True
            if ars.get('only_admins'): can_reply = await is_authorized_in_group(context.bot, chat_id, user_id)
            if ars.get('ignore_bots') and update.effective_user.is_bot: can_reply = False
            if can_reply:
                reply = await db_get_reply(text.lower())
                if not reply:
                    for key, value in ALL_REPLIES.items():
                        if re.search(r'\b' + re.escape(key) + r'\b', text, re.IGNORECASE):
                            reply = value if isinstance(value, str) else random.choice(value) if isinstance(value, list) else value
                            break
                if reply:
                    try: await msg.reply_text(reply)
                    except: pass
        
        # تعلم
        if len(text) > 3:
            sentiment = sentiment_analyzer.analyze(text)
            async def _save_sentiment(conn):
                await conn.execute("INSERT INTO sentiment_history (user_id, chat_id, text, sentiment, score, created_at) VALUES (?,?,?,?,?,?)", (user_id, chat_id, text[:200], sentiment['sentiment'], sentiment['score'], utc_now_iso()))
                await conn.commit()
            try: await execute_db(_save_sentiment)
            except: pass

async def message_handler_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user: return
    user_id = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""
    state = context.user_data.get('state')
    
    if state == UserState.WAITING_CHANNEL_ID:
        channel_id = text.strip()
        if not (channel_id.startswith('@') or channel_id.lstrip('-').isdigit()):
            await safe_send_markdown(context.bot, user_id, "❌ صيغة خاطئة"); return
        try:
            chat = await context.bot.get_chat(channel_id)
            if chat.type != 'channel': await safe_send_markdown(context.bot, user_id, "❌ ليس قناة"); return
            channel_name = chat.title or "بدون اسم"
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status not in ['administrator', 'creator'] or not bot_member.can_post_messages:
                    await safe_send_markdown(context.bot, user_id, "❌ البوت ليس مشرفاً أو لا يملك صلاحية النشر"); return
            except: await safe_send_markdown(context.bot, user_id, "❌ لا يمكن الوصول"); return
            result = await db_add_channel(user_id, str(chat.id), channel_name)
            await safe_send_markdown(context.bot, user_id, "✅ تمت الإضافة" if result else "⚠️ موجودة")
        except Exception as e: await safe_send_markdown(context.bot, user_id, f"❌ {str(e)[:100]}")
        context.user_data.pop('state', None)
    
    elif state == UserState.ADDING_POSTS:
        session_posts = context.user_data.get(f"session_{user_id}", [])
        target = context.user_data.get(f"session_target_{user_id}", 15)
        media_type = 'text'; media_file_id = None
        msg = update.message
        if msg.photo: media_type = 'photo'; media_file_id = msg.photo[-1].file_id
        elif msg.video: media_type = 'video'; media_file_id = msg.video.file_id
        elif msg.document: media_type = 'document'; media_file_id = msg.document.file_id
        elif msg.audio: media_type = 'audio'; media_file_id = msg.audio.file_id
        elif msg.voice: media_type = 'voice'; media_file_id = msg.voice.file_id
        elif msg.animation: media_type = 'animation'; media_file_id = msg.animation.file_id
        elif msg.text: media_type = 'text'
        else: await safe_send_markdown(context.bot, user_id, "⚠️ غير مدعوم"); return
        
        text_content = msg.caption or "" if media_type != 'text' else text
        session_posts.append((text_content, media_type, media_file_id))
        context.user_data[f"session_{user_id}"] = session_posts
        remaining = target - len(session_posts)
        await safe_send_markdown(context.bot, user_id, f"✅ {len(session_posts)}/{target} | متبقي {remaining}")
        
        if len(session_posts) >= target:
            active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
            if active: await db_save_posts(active, session_posts)
            context.user_data.pop(f"session_{user_id}", None)
            context.user_data.pop(f"session_target_{user_id}", None)
            context.user_data.pop('state', None)
            await safe_send_markdown(context.bot, user_id, "✅ تم الحفظ")
    
    elif state == UserState.WAITING_INTERVAL_MINUTES:
        try:
            minutes = int(text)
            if 1 <= minutes <= 1440:
                ch_id = context.user_data.get('schedule_ch_id')
                if ch_id: await db_save_schedule(ch_id, 'interval_minutes', interval_minutes=minutes)
                await safe_send_markdown(context.bot, user_id, "✅ تم")
        except: pass
        context.user_data.pop('state', None)
    
    elif state == UserState.WAITING_INTERVAL_HOURS:
        try:
            hours = int(text)
            if 1 <= hours <= 168:
                ch_id = context.user_data.get('schedule_ch_id')
                if ch_id: await db_save_schedule(ch_id, 'interval_hours', interval_hours=hours)
                await safe_send_markdown(context.bot, user_id, "✅ تم")
        except: pass
        context.user_data.pop('state', None)
    
    elif state == UserState.WAITING_INTERVAL_DAYS:
        try:
            days = int(text)
            if 1 <= days <= 365:
                ch_id = context.user_data.get('schedule_ch_id')
                if ch_id: await db_save_schedule(ch_id, 'interval_days', interval_days=days)
                await safe_send_markdown(context.bot, user_id, "✅ تم")
        except: pass
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
                else: await safe_send_markdown(context.bot, user_id, "❌ وقت في الماضي")
            except: await safe_send_markdown(context.bot, user_id, "❌ صيغة خاطئة")
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
    
    elif state == UserState.WAITING_KEYWORD:
        context.user_data['reply_keyword'] = text.lower()
        context.user_data['state'] = UserState.WAITING_REPLY
        await safe_send_markdown(context.bot, user_id, f"📝 الكلمة: {text}\nأرسل الرد:")
    
    elif state == UserState.WAITING_REPLY:
        if context.user_data.get('admin_del_reply'):
            await db_del_reply(text.lower())
            await safe_send_markdown(context.bot, user_id, f"✅ تم حذف '{text}'")
            context.user_data.pop('admin_del_reply', None)
        else:
            keyword = context.user_data.get('reply_keyword')
            if keyword:
                await db_add_reply(keyword, text)
                await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة رد لـ '{keyword}'")
        context.user_data.pop('state', None)
    
    elif state == UserState.WAITING_ADMIN_ID_ADD:
        try:
            target_id = int(text)
            await add_bot_admin(target_id)
            await safe_send_markdown(context.bot, user_id, f"✅ تمت إضافة {target_id}")
        except: await safe_send_markdown(context.bot, user_id, "❌ خطأ")
        context.user_data.pop('state', None)
    
    elif state == UserState.WAITING_ADMIN_ID_REMOVE:
        try:
            target_id = int(text)
            await remove_bot_admin(target_id)
            await safe_send_markdown(context.bot, user_id, f"✅ تمت إزالة {target_id}")
        except: await safe_send_markdown(context.bot, user_id, "❌ خطأ")
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
            try: await context.bot.send_message(f"@{ch}", f"📢 {text}"); await safe_send_markdown(context.bot, user_id, "✅ تم")
            except: await safe_send_markdown(context.bot, user_id, "❌ فشل")
        else: await safe_send_markdown(context.bot, user_id, "❌ لا توجد قناة")
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
        except: await safe_send_markdown(context.bot, user_id, "❌ خطأ")
        context.user_data.pop('state', None)
    
    elif state == UserState.WAITING_LOG_CHANNEL:
        try:
            chat = await context.bot.get_chat(text)
            if chat.type == 'channel':
                await db_set_setting('log_channel_id', str(chat.id))
                await safe_send_markdown(context.bot, user_id, f"✅ {chat.title}")
            else: await safe_send_markdown(context.bot, user_id, "❌ ليس قناة")
        except: await safe_send_markdown(context.bot, user_id, "❌ خطأ")
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
                cid = await db_create_contest(user_id, context.user_data.pop('contest_title',''), context.user_data.pop('contest_description',''), context.user_data.pop('contest_prize',''), mecca_to_utc(end_date))
                await safe_send_markdown(context.bot, user_id, f"✅ مسابقة #{cid}")
            else: await safe_send_markdown(context.bot, user_id, "❌ وقت في الماضي")
        except: await safe_send_markdown(context.bot, user_id, "❌ صيغة خاطئة")
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
                global NSFW_THRESHOLD; NSFW_THRESHOLD = val / 100
                await safe_send_markdown(context.bot, user_id, f"✅ {val}%")
        except: pass
        context.user_data.pop('state', None)
    
    elif state == UserState.WAITING_MAX_LENGTH:
        try:
            val = int(text)
            if val >= 0:
                chat_id = context.user_data.get('security_chat_id')
                if chat_id: await db_set_security_settings(chat_id, max_message_length=val)
                await safe_send_markdown(context.bot, user_id, f"✅ {val}")
        except: pass
        context.user_data.pop('state', None)
    
    elif state in [UserState.WAITING_BAN_USER, UserState.WAITING_MUTE_USER, UserState.WAITING_WARN_USER,
                   UserState.WAITING_KICK_USER, UserState.WAITING_RESTRICT_USER, UserState.WAITING_UNBAN_USER]:
        chat_id = context.user_data.get('advanced_chat_id')
        if chat_id:
            try:
                target_id = int(text.split()[0]) if text.split()[0].isdigit() else None
                if target_id:
                    action_map = {UserState.WAITING_BAN_USER: "ban", UserState.WAITING_MUTE_USER: "mute",
                                  UserState.WAITING_WARN_USER: "warn", UserState.WAITING_KICK_USER: "kick",
                                  UserState.WAITING_RESTRICT_USER: "restrict", UserState.WAITING_UNBAN_USER: "unban"}
                    action = action_map.get(state)
                    if action:
                        dur = context.user_data.get('mute_minutes', 60) if action == 'mute' else None
                        success, msg = await apply_penalty_with_duration(context.bot, chat_id, target_id, action, dur, "", user_id)
                        await safe_send_markdown(context.bot, user_id, msg)
            except: pass
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
            reply = await db_get_reply(text.lower())
            if reply:
                try: await update.message.reply_text(reply)
                except: pass; return
        await main_menu_callback(update, context)

# ===================================================================
# 32. المهام الخلفية
# ===================================================================
class TaskManager:
    def __init__(self): self.tasks = set(); self.semaphore = asyncio.Semaphore(10)
    def create_task(self, coro, name=None):
        async def w():
            async with self.semaphore:
                try: return await coro
                except asyncio.CancelledError: raise
                except Exception as e: logger.error(f"مهمة {name}: {e}"); raise
        task = asyncio.create_task(w())
        if name: task.set_name(name)
        self.tasks.add(task); task.add_done_callback(self.tasks.discard)
        return task
    async def cancel_all(self):
        for t in list(self.tasks):
            if not t.done(): t.cancel()
        if self.tasks: await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
    def get_task_count(self):
        self.tasks = {t for t in self.tasks if not t.done()}
        return len(self.tasks)

task_manager = TaskManager()

async def safe_loop(coro_func, name="loop"):
    while True:
        try:
            if asyncio.iscoroutinefunction(coro_func): await coro_func()
            else: await coro_func
            await asyncio.sleep(1)
        except asyncio.CancelledError: break
        except Exception as e:
            logger.error(f"حلقة {name}: {e}")
            await asyncio.sleep(60)

async def auto_publish_loop_improved(bot):
    await asyncio.sleep(5)
    while True:
        try:
            async def _g(conn):
                cur = await conn.execute("""
                    SELECT uc.id, uc.channel_id, u.user_id FROM user_channels uc
                    JOIN users u ON uc.user_id=u.user_id
                    LEFT JOIN schedule s ON uc.id=s.channel_db_id
                    WHERE u.auto_publish=1 AND u.banned=0 AND uc.banned=0
                    AND (s.next_publish_date IS NULL OR s.next_publish_date <= ?)
                    ORDER BY COALESCE(s.next_publish_date, '1970-01-01') ASC LIMIT ?
                """, (utc_now_iso(), MAX_CHANNELS_PER_CYCLE))
                return await cur.fetchall()
            rows = await execute_db(_g)
            for ch_db_id, ch_tele_id, user_id in rows:
                post = await db_get_next_post(ch_db_id)
                if not post:
                    if await db_get_auto_recycle(user_id):
                        await db_reset_all_posts_to_unpublished(ch_db_id)
                    continue
                try:
                    if post['media_type'] == 'photo' and post['media_file_id']:
                        await bot.send_photo(ch_tele_id, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
                    else: await bot.send_message(ch_tele_id, post['text'][:4096] if post['text'] else ".")
                    await db_mark_published(post['id'])
                    await db_set_last_publish(ch_db_id, utc_now())
                    await db_update_next_publish_date(ch_db_id)
                except Exception as e:
                    await db_increment_fail_count(post['id'])
                    await db_set_next_publish_date(ch_db_id, utc_now() + timedelta(seconds=PUBLISH_RETRY_DELAY))
                await asyncio.sleep(random.uniform(1, 3))
            await asyncio.sleep(await db_get_publish_interval_seconds())
        except Exception as e: logger.error(f"نشر: {e}"); await asyncio.sleep(60)

async def auto_backup():
    while True:
        await asyncio.sleep(AUTO_BACKUP_SLEEP)
        try:
            if await db_get_auto_backup():
                last = await db_get_last_backup_time()
                if not last or (utc_now() - datetime.fromisoformat(last)).days >= 7: await create_backup()
                else: await incremental_backup()
                await db_set_setting('last_backup', utc_now_iso())
        except: pass

async def run_scheduled_posts_loop_improved(bot):
    while True:
        await asyncio.sleep(SCHEDULED_POSTS_SLEEP)
        try:
            posts = await db_get_due_scheduled_posts(utc_now(), 50)
            for post_id, chat_id, text, fail_count in posts:
                try:
                    await bot.send_message(chat_id, text[:4096] if text else ".")
                    await db_delete_scheduled_post(post_id)
                except:
                    await db_update_scheduled_post_fail(post_id, fail_count+1)
                    if fail_count+1 >= 5: await db_delete_scheduled_post(post_id)
        except: pass

async def send_reminders_loop_improved(bot):
    while True:
        await asyncio.sleep(REMINDERS_SLEEP)
        try:
            for u in await db_get_users_needing_reminder():
                try: await bot.send_message(u['user_id'], f"⚠️ اشتراكك ينتهي خلال {u['days_left']} أيام")
                except: pass
                await db_update_last_reminder_sent(u['user_id'], "sub")
        except: pass

async def cleanup_expired_sessions_improved():
    while True:
        await asyncio.sleep(CLEANUP_SLEEP)
        try:
            await execute_db(lambda c: c.execute("DELETE FROM sentiment_history WHERE created_at < ?", ((utc_now() - timedelta(days=90)).isoformat(),)) or c.commit())
        except: pass

async def self_ping_loop():
    while True:
        await asyncio.sleep(300)
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"http://localhost:{WEB_PORT}/health", timeout=5) as r:
                    if r.status == 200: logger.debug("Ping OK")
        except: pass

async def broadcast_stats_periodically():
    while True:
        await asyncio.sleep(3600)
        try:
            total, banned, posts, groups, channels = await db_stats()
            logger.info(f"📊 مستخدمين={total} محظورين={banned} منشورات={posts} مجموعات={groups} قنوات={channels}")
        except: pass

async def cleanup_points_cache():
    while True: await asyncio.sleep(3600)

async def memory_monitor():
    while True:
        await asyncio.sleep(60)
        try:
            if get_ram_usage()['percent'] > 80: gc.collect()
        except: pass

async def auto_close_contests_loop(bot):
    while True:
        await asyncio.sleep(3600)
        try:
            now = utc_now_iso()
            async def _g(conn):
                cur = await conn.execute("SELECT id, title, prize FROM contests WHERE status='active' AND end_date <= ?", (now,))
                return await cur.fetchall()
            for cid, title, prize in await execute_db(_g):
                async def _winner(conn):
                    cur = await conn.execute("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,))
                    row = await cur.fetchone()
                    return row[0] if row else None
                wid = await execute_db(_winner)
                if wid:
                    await db_set_contest_winner(cid, wid)
                    try: await bot.send_message(wid, f"🏆 فزت في {title}!")
                    except: pass
        except: pass

async def refresh_group_admins_and_hidden_owners_loop(bot):
    while True:
        await asyncio.sleep(3600)
        try:
            async def _g(conn):
                cur = await conn.execute("SELECT chat_id FROM bot_groups WHERE banned=0")
                return [row[0] for row in await cur.fetchall()]
            for chat_id in await execute_db(_g):
                try:
                    await db_sync_group_admins(chat_id, bot)
                    async def _clean(conn):
                        for table, col in [("hidden_owner_groups","owner_id"), ("hidden_admins","admin_id")]:
                            cur = await conn.execute(f"SELECT {col} FROM {table} WHERE chat_id=?", (chat_id,))
                            for row in await cur.fetchall():
                                try:
                                    member = await bot.get_chat_member(chat_id, row[0])
                                    if member.status not in ['administrator', 'creator']:
                                        await conn.execute(f"DELETE FROM {table} WHERE chat_id=? AND {col}=?", (chat_id, row[0]))
                                except: pass
                        await conn.commit()
                    await execute_db(_clean)
                except: pass
        except: pass

async def memory_optimizer_loop():
    while True:
        await asyncio.sleep(300)
        try: gc.collect()
        except: pass

# ===================================================================
# 33. خادم الويب
# ===================================================================
async def setup_unified_web_server(application, port: int):
    from aiohttp import web
    from telegram import Update
    
    if not hasattr(application, 'web_app') or application.web_app is None:
        application.web_app = web.Application()
    
    async def health(request): return web.Response(text="OK")
    async def index(request):
        return web.Response(text="<h1>🌿 ريلاكس مانيجر</h1><p>✅ يعمل</p>", content_type="text/html", charset="utf-8")
    async def webhook(request):
        try:
            data = await request.json()
            await application.process_update(Update.de_json(data, application.bot))
            return web.Response(status=200, text="OK")
        except: return web.Response(status=500)
    
    application.web_app.router.add_get('/', index)
    application.web_app.router.add_get('/health', health)
    application.web_app.router.add_post(f"/{TOKEN}", webhook)
    
    runner = web.AppRunner(application.web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info(f"✅ خادم ويب على {port}")

async def global_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    error_id = secrets.token_hex(4)
    logger.error(f"[{error_id}] {type(error).__name__}: {str(error)[:200]}")
    try:
        if update and update.effective_user:
            await context.bot.send_message(update.effective_user.id, f"❌ خطأ: `{error_id}`")
    except: pass

async def run_polling_safe(application):
    while True:
        try: await application.run_polling(drop_pending_updates=True)
        except asyncio.CancelledError: break
        except Exception as e:
            logger.error(f"Polling: {e}")
            await asyncio.sleep(10)

# ===================================================================
# 34. معالجات الأحداث
# ===================================================================
async def chat_join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.chat_join_request.approve()
    except: pass

async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members: return
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']: return
    settings = await db_get_security_settings(chat.id)
    for member in update.message.new_chat_members:
        if member.id == context.bot.id: continue
        if settings.get('welcome_enabled'):
            try: await context.bot.send_message(chat.id, f"مرحباً {member.full_name or member.first_name} في {chat.title} 🤍")
            except: pass
        await db_update_user_cache(member.id, member.username or "", member.first_name or "")

async def left_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.left_chat_member: return
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']: return
    settings = await db_get_security_settings(chat.id)
    member = update.message.left_chat_member
    if settings.get('goodbye_enabled'):
        try: await context.bot.send_message(chat.id, f"وداعاً {member.full_name or member.first_name} 👋")
        except: pass

async def track_chat_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result: return
    if result.new_chat_member.status in ['member', 'administrator']:
        chat = result.chat
        if chat.type in ['group', 'supergroup']:
            await db_register_group(chat.id, chat.title or "", result.from_user.id, chat.username)
            await db_sync_group_admins(chat.id, context.bot)

async def pre_checkout_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    try:
        parts = update.message.successful_payment.invoice_payload.split('_')
        days = int(parts[1]) if len(parts) >= 2 else 30
        await db_activate_subscription(update.effective_user.id, days)
        await safe_send_markdown(context.bot, update.effective_user.id, f"✅ تم تفعيل {days} يوم!")
    except: pass

# ===================================================================
# 35. دالة main()
# ===================================================================
async def main():
    print("🚀 بدء تشغيل ريلاكس مانيجر...")
    
    await init_db()
    print("✅ قاعدة البيانات جاهزة")
    
    # تحميل الكلمات المحظورة
    words = load_banned_words_from_file(BANNED_WORDS_FILE)
    if words:
        for w in words:
            try: await db_add_banned_word(w, -1, PRIMARY_OWNER_ID)
            except: pass
        await rebuild_banned_patterns()
    
    await db_register_user(PRIMARY_OWNER_ID)
    await add_bot_admin(PRIMARY_OWNER_ID)
    
    # إنشاء التطبيق
    if USE_PROXY:
        request = HTTPXRequest(proxy_url=PROXY_URL, read_timeout=60, write_timeout=30, connect_timeout=30, connection_pool_size=MAX_CONNECTIONS)
    else:
        request = HTTPXRequest(read_timeout=60, write_timeout=30, connect_timeout=30, connection_pool_size=MAX_CONNECTIONS)
    
    application = Application.builder().token(TOKEN).request(request).build()
    application.add_error_handler(global_error_handler)
    
    # تسجيل الأوامر
    for cmd, handler in [
        ("start", start_command_handler), ("language", language_command_handler),
        ("syncgroup", syncgroup_command_handler), ("register_hidden_owner", register_hidden_owner_handler),
        ("security", security_command_handler), ("panel", panel_command_handler),
        ("help", help_command_handler), ("trial", trial_command_handler),
        ("subscribe", subscribe_command_handler), ("support", support_command_handler),
        ("rank", rank_command_handler), ("top", top_command_handler),
        ("stats", stats_command_handler), ("developer", developer_command_handler),
        ("updates", updates_command_handler), ("sendcode", sendcode_command_handler),
        ("lock", lock_chat_command_handler), ("unlock", unlock_chat_command_handler),
        ("schedule", schedule_command_handler), ("set_rules", set_rules_command_handler),
        ("rules", rules_command_handler), ("create_contest", create_contest_command_handler),
        ("declare_winner", declare_winner_command_handler), ("contests", contests_command_handler),
        ("set_log_channel", set_log_channel_command_handler),
    ]:
        application.add_handler(CommandHandler(cmd, handler))
    
    for cmd in ["ban", "mute", "warn", "kick", "restrict", "unban", "pin"]:
        application.add_handler(CommandHandler(cmd, handle_moderation_commands))
    
    # معالج الأزرار
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    
    # معالجات الرسائل
    application.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler), group=1)
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, message_handler_main))
    
    # معالجات الأحداث
    application.add_handler(ChatJoinRequestHandler(chat_join_request_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_chat_member_handler))
    application.add_handler(ChatMemberHandler(track_chat_add, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback_handler))
    
    # أوامر البوت
    try:
        await application.bot.set_my_commands([
            BotCommand("start", "الرئيسية"), BotCommand("help", "مساعدة"),
            BotCommand("syncgroup", "تفعيل مجموعة"), BotCommand("security", "الأمان"),
            BotCommand("panel", "لوحة تحكم"), BotCommand("lock", "قفل"), BotCommand("unlock", "فتح"),
            BotCommand("ban", "حظر"), BotCommand("mute", "كتم"), BotCommand("warn", "تحذير"),
            BotCommand("schedule", "جدولة"), BotCommand("stats", "إحصائيات"),
            BotCommand("contests", "مسابقات"), BotCommand("support", "دعم"),
        ])
    except: pass
    
    # المهام الخلفية
    task_manager.create_task(safe_loop(lambda: auto_publish_loop_improved(application.bot)), "نشر")
    task_manager.create_task(safe_loop(auto_backup), "نسخ")
    task_manager.create_task(safe_loop(lambda: run_scheduled_posts_loop_improved(application.bot)), "مجدولة")
    task_manager.create_task(safe_loop(lambda: send_reminders_loop_improved(application.bot)), "تذكير")
    task_manager.create_task(safe_loop(cleanup_expired_sessions_improved), "تنظيف")
    task_manager.create_task(safe_loop(self_ping_loop), "ping")
    task_manager.create_task(safe_loop(memory_monitor), "ذاكرة")
    task_manager.create_task(safe_loop(lambda: auto_close_contests_loop(application.bot)), "مسابقات")
    task_manager.create_task(safe_loop(lambda: refresh_group_admins_and_hidden_owners_loop(application.bot)), "صلاحيات")
    
    # خادم ويب
    port = int(os.getenv("PORT", "10000"))
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("HEROKU_APP_NAME")
    
    try: await setup_unified_web_server(application, port)
    except: pass
    
    if hostname:
        await application.initialize(); await application.start()
        try: await application.bot.set_webhook(url=f"https://{hostname}/{TOKEN}", drop_pending_updates=True)
        except: pass
        try: await application.bot.send_message(PRIMARY_OWNER_ID, f"✅ تم تشغيل {BOT_NAME}")
        except: pass
        try: await asyncio.Event().wait()
        except KeyboardInterrupt: pass
    else:
        try: await application.bot.delete_webhook()
        except: pass
        try: await application.bot.send_message(PRIMARY_OWNER_ID, f"✅ تم تشغيل {BOT_NAME}")
        except: pass
        await run_polling_safe(application)
    
    await task_manager.cancel_all()
    await db_pool.close()

if __name__ == "__main__":
    nest_asyncio.apply()
    print("🌿 ريلاكس مانيجر v22.2.0")
    print(f"🤖 {BOT_NAME} | @RelaxMgr")
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n👋 تم الإيقاف")
    except Exception as e:
        print(f"\n❌ {e}")
        traceback.print_exc()
        sys.exit(1)
