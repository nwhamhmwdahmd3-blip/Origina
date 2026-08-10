#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ريلاكس مانيجر - بوت متكامل لإدارة القنوات والمجموعات
الإصدار: 21.0.0 - النسخة العالمية الكاملة مع جميع الميزات (مصححة بالكامل)
المطور: @RelaxMgr
"""

import sys
import os
from pathlib import Path
import secrets
import string
import urllib.parse
import base64
import io
import tempfile
import json
import hashlib
import hmac
import time as time_module
import re
import shutil
import logging
import traceback
import random
import asyncio
import socket
import subprocess
import gc
import sqlite3
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque, OrderedDict
from typing import Optional, List, Dict, Tuple, Any, Union, Callable, Awaitable
from functools import lru_cache, wraps
from dataclasses import dataclass, asdict
from enum import Enum, auto
import gzip
import zipfile
import platform
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import queue
from concurrent.futures import ThreadPoolExecutor
import types
import signal
import html

# ===================================================================
# 1. check_python_version
# ===================================================================
def check_python_version():
    required_version = (3, 8)
    current_version = sys.version_info
    if current_version < required_version:
        print(f"❌ يحتاج البوت إلى بايثون {required_version[0]}.{required_version[1]} أو أحدث")
        print(f"📌 الإصدار الحالي: {current_version[0]}.{current_version[1]}")
        sys.exit(1)
check_python_version()

# ===================================================================
# 2. تثبيت الحزم الأساسية
# ===================================================================
def ensure_package(package_name: str, import_name: str = None) -> bool:
    if import_name is None:
        import_name = package_name
    try:
        __import__(import_name)
        return True
    except ImportError:
        try:
            print(f"📦 جاري تثبيت {package_name}...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package_name, "--quiet"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            __import__(import_name)
            print(f"✅ تم تثبيت {package_name}")
            return True
        except:
            print(f"⚠️ لا يمكن تثبيت {package_name}")
            return False

# تثبيت الحزم الأساسية
ensure_package("python-dotenv", "dotenv")
ensure_package("cachetools")
ensure_package("psutil")
ensure_package("nest-asyncio", "nest_asyncio")
ensure_package("aiosqlite")
ensure_package("cryptography")
ensure_package("deep-translator", "deep_translator")
ensure_package("bleach")
ensure_package("qrcode")
ensure_package("Pillow", "PIL")
ensure_package("plotly")
ensure_package("aiohttp")
ensure_package("aiofiles")
ensure_package("httpx")
ensure_package("reportlab")
ensure_package("jinja2")
ensure_package("markdown")
ensure_package("python-multipart", "multipart")
ensure_package("aioredis")
ensure_package("pandas")
ensure_package("openpyxl")

# ===================================================================
# 3. استيراد المكتبات
# ===================================================================
import nest_asyncio
nest_asyncio.apply()
import aiosqlite
from dotenv import load_dotenv
load_dotenv()
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember, BotCommand, LabeledPrice, ChatPermissions
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler, ChatMemberHandler, ChatJoinRequestHandler
from telegram.error import TimedOut, NetworkError, BadRequest, Forbidden, Conflict
from telegram.request import HTTPXRequest
import httpx
from deep_translator import GoogleTranslator
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from aiohttp import web, WSMsgType
import aiohttp
from PIL import Image
import numpy as np

# ===================================================================
# دوال مساعدة
# ===================================================================
async def is_user_bot(bot, user_id: int) -> bool:
    try:
        chat = await bot.get_chat(user_id)
        return chat.is_bot
    except Exception:
        return False

# ===================================================================
# 4. إعداد المسارات
# ===================================================================
def get_base_path() -> Path:
    return Path(__file__).parent.resolve()
BASE_PATH = get_base_path()

def get_writable_path(base_path: Path, subdir: str) -> Path:
    paths_to_try = [
        base_path / subdir,
        Path.home() / f".bot_{subdir}",
        Path(f"/tmp/bot_{subdir}"),
        Path(os.getenv('TEMP', '/tmp')) / f"bot_{subdir}",
    ]
    for path in paths_to_try:
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".write_test"
            test_file.touch()
            test_file.unlink()
            return path
        except:
            continue
    import tempfile
    temp_path = Path(tempfile.gettempdir()) / f"bot_{subdir}"
    temp_path.mkdir(parents=True, exist_ok=True)
    return temp_path

DATA_PATH = get_writable_path(BASE_PATH, "data")
DB_PATH = DATA_PATH / "bot_data.db"
BACKUP_DIR = get_writable_path(BASE_PATH, "backups")
LOG_PATH = get_writable_path(BASE_PATH, "logs") / "bot.log"
SECURITY_LOG = get_writable_path(BASE_PATH, "logs") / "security.log"
ERROR_LOG = get_writable_path(BASE_PATH, "logs") / "errors.log"
ACCESS_LOG = get_writable_path(BASE_PATH, "logs") / "access.log"
TEMP_PATH = get_writable_path(BASE_PATH, "temp")
STATIC_PATH = get_writable_path(BASE_PATH, "static")
TEMPLATES_PATH = get_writable_path(BASE_PATH, "templates")
LANG_PATH = BASE_PATH / "lang"
PLUGINS_PATH = BASE_PATH / "plugins"
BANNED_WORDS_FILE = BASE_PATH / "banned_words.txt"

# إنشاء المجلدات
for path in [DATA_PATH, BACKUP_DIR, LOG_PATH.parent, TEMP_PATH, STATIC_PATH, TEMPLATES_PATH, LANG_PATH, PLUGINS_PATH]:
    path.mkdir(parents=True, exist_ok=True)

# ===================================================================
# 5. تحميل متغيرات البيئة
# ===================================================================
def load_env_files():
    env_files = [
        ".env",
        ".env.local",
        str(BASE_PATH / ".env"),
        str(BASE_PATH / "config" / ".env"),
        str(Path.home() / ".bot" / ".env"),
    ]
    for env_file in env_files:
        if os.path.exists(env_file):
            load_dotenv(env_file)
            return True
    return False
load_env_files()

def get_env_or_default(key: str, default: any, env_type: type = str) -> any:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        if env_type == bool:
            return value.lower() in ['true', '1', 'yes', 'on']
        elif env_type == int:
            return int(value)
        elif env_type == float:
            return float(value)
        return env_type(value)
    except:
        return default

TOKEN = get_env_or_default("BOT_TOKEN", None, str)
if not TOKEN:
    raise ValueError("❌ لم يتم العثور على BOT_TOKEN في ملفات البيئة")

PRIMARY_OWNER_ID = get_env_or_default("MAIN_ADMIN_ID", 0, int)
if PRIMARY_OWNER_ID == 0:
    raise ValueError("❌ MAIN_ADMIN_ID غير محدد في ملفات البيئة")

BOT_NAME = get_env_or_default("BOT_NAME", "ريلاكس مانيجر", str)
BOT_USERNAME = get_env_or_default("BOT_USERNAME", "Reelaaaxbot", str)
USE_PROXY = get_env_or_default("USE_PROXY", False, bool)
PROXY_URL = get_env_or_default("PROXY_URL", "http://127.0.0.1:10809", str)
ENABLE_2FA = False
ADMIN_2FA_SECRET = ""
DB_ENCRYPTION = get_env_or_default("DB_ENCRYPTION", True, bool)
MAX_BACKUPS = get_env_or_default("MAX_BACKUPS", 10, int)
SECURITY_LOG_LEVEL = get_env_or_default("SECURITY_LOG_LEVEL", "CRITICAL", str)

RENDER_PORT = int(os.getenv("PORT", "10000"))
WEB_PORT = get_env_or_default("WEB_PORT", RENDER_PORT, int)
WEB_HOST = get_env_or_default("WEB_HOST", "0.0.0.0", str)
WEB_PASSWORD = get_env_or_default("WEB_PASSWORD", "", str)
if not WEB_PASSWORD and os.getenv('ENVIRONMENT', 'development') == 'production':
    WEB_PASSWORD = secrets.token_urlsafe(16)
    print(f"🔑 كلمة المرور المؤقتة: {WEB_PASSWORD}")
WEB_USERNAME = get_env_or_default("WEB_USERNAME", "admin", str)
WEB_SECRET_KEY = get_env_or_default("WEB_SECRET_KEY", secrets.token_urlsafe(32), str)

BATTERY_SAVER_MODE = get_env_or_default("BATTERY_SAVER_MODE", False, bool)

if BATTERY_SAVER_MODE:
    POLL_INTERVAL = 10.0
    SCHEDULED_POSTS_SLEEP = 120
    REMINDERS_SLEEP = 7200
    AUTO_BACKUP_SLEEP = 48 * 60 * 60
else:
    POLL_INTERVAL = 1.0
    SCHEDULED_POSTS_SLEEP = 10
    REMINDERS_SLEEP = 3600
    AUTO_BACKUP_SLEEP = 24 * 60 * 60

DEFAULT_PUBLISH_INTERVAL_SECONDS = 720
CLEANUP_SLEEP = 3600
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 20 * 1024 * 1024))
MAX_CHANNELS_PER_CYCLE = int(os.getenv('MAX_CHANNELS_PER_CYCLE', '20'))
PUBLISH_RETRY_DELAY = 300
MAX_POSTS_PER_SESSION = 50
MAX_UNPUBLISHED_POSTS = 1000
DB_TIMEOUT = 30
MAX_CONNECTIONS = 20
ANONYMOUS_ADMIN_ID = int(os.getenv("ANONYMOUS_ADMIN_ID", "1087968824"))

# ===================================================================
# متغيرات NSFW والنسخ الاحتياطي والمؤقتات (مضافة)
# ===================================================================
NSFW_ENABLED = get_env_or_default("NSFW_ENABLED", False, bool)
NSFW_THRESHOLD = get_env_or_default("NSFW_THRESHOLD", 0.7, float)
NSFW_MAX_FILE_SIZE = get_env_or_default("NSFW_MAX_FILE_SIZE", 5 * 1024 * 1024, int)
NSFW_MAX_VIDEO_SIZE = get_env_or_default("NSFW_MAX_VIDEO_SIZE", 50 * 1024 * 1024, int)
CLOUD_BACKUP_ENABLED = get_env_or_default("CLOUD_BACKUP_ENABLED", False, bool)
start_time = time_module.time()

# ===================================================================
# 6. ثوابت المجموعات المحسنة
# ===================================================================
_MAX_BANNED_WORDS_PER_CHAT = 500
_MAX_BANNED_WORDS_GLOBAL = 2000
_MAX_AUTH_CACHE_SIZE = 50000
_MAX_FAILED_ATTEMPTS = 10
_FAILED_ATTEMPTS_WINDOW = 300
_TOKEN_EXPIRY = 300
_AUTH_CACHE_TTL = 300
_FLOOD_CACHE_MAX_SIZE = 10000

# ===================================================================
# 7. قائمة الأعمدة المسموح بها (قائمة بيضاء للأمان)
# ===================================================================
_ALLOWED_SECURITY_COLUMNS = {
    'delete_links', 'mentions', 'warn_message', 'slow_mode', 'slow_mode_seconds',
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
# 8. نظام السجلات
# ===================================================================
class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if TOKEN and TOKEN in msg:
            msg = msg.replace(TOKEN, "[TOKEN_HIDDEN]")
        record.msg = msg
        return True

from logging.handlers import RotatingFileHandler
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        RotatingFileHandler(LOG_PATH, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

for handler in logger.handlers:
    handler.addFilter(SensitiveDataFilter())

class AdvancedLogger:
    def __init__(self):
        self.loggers = {}
        self._setup_loggers()

    def _setup_loggers(self):
        error_logger = logging.getLogger('error_logger')
        error_logger.setLevel(logging.ERROR)
        error_handler = RotatingFileHandler(ERROR_LOG, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        error_logger.addHandler(error_handler)
        self.loggers['error'] = error_logger

        access_logger = logging.getLogger('access_logger')
        access_logger.setLevel(logging.INFO)
        access_handler = RotatingFileHandler(ACCESS_LOG, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        access_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        access_logger.addHandler(access_handler)
        self.loggers['access'] = access_logger

        security_logger = logging.getLogger('security_logger')
        security_logger.setLevel(logging.WARNING)
        security_handler = RotatingFileHandler(SECURITY_LOG, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        security_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        security_logger.addHandler(security_handler)
        self.loggers['security'] = security_logger

    def log_error(self, message: str, error: Exception = None, context: dict = None):
        error_id = secrets.token_hex(4)
        log_msg = f"[{error_id}] {message}"
        if error:
            log_msg += f" - {error}"
        if context:
            safe_context = {k: v for k, v in context.items() if k not in ['token', 'password', 'key', 'secret']}
            log_msg += f" - السياق: {json.dumps(safe_context, default=str)[:200]}"
        self.loggers['error'].error(log_msg)
        traceback.print_exc()
        return error_id

    def log_access(self, user_id: int, action: str, details: dict = None):
        log_msg = f"User: {user_id} - Action: {action}"
        if details:
            safe_details = {k: v for k, v in details.items() if k not in ['token', 'password', 'key', 'secret']}
            log_msg += f" - {json.dumps(safe_details, default=str)[:100]}"
        self.loggers['access'].info(log_msg)

    def log_security(self, event: str, user_id: int, details: dict = None, severity: str = "INFO"):
        log_msg = f"[{severity}] {event} - User: {user_id}"
        if details:
            safe_details = {k: v for k, v in details.items() if k not in ['token', 'password', 'key', 'secret']}
            log_msg += f" - {json.dumps(safe_details, default=str)[:200]}"
        self.loggers['security'].warning(log_msg)

advanced_logger = AdvancedLogger()

def log_error(error: Exception, context: dict = None) -> str:
    return advanced_logger.log_error("حدث خطأ غير متوقع", error, context)

# ===================================================================
# 9. نظام التشفير
# ===================================================================
def derive_key_from_password(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key

def get_encryption_key() -> bytes:
    key_file = DATA_PATH / ".db_key"
    salt_file = DATA_PATH / ".db_salt"
    if key_file.exists() and salt_file.exists():
        try:
            with open(key_file, 'rb') as f:
                key = f.read()
            if len(key) == 44:
                return key
        except:
            pass
    password = os.getenv('DB_ENCRYPTION_PASSWORD')
    if password and len(password) >= 8:
        salt = os.urandom(16)
        key = derive_key_from_password(password, salt)
        with open(key_file, 'wb') as f:
            f.write(key)
        with open(salt_file, 'wb') as f:
            f.write(salt)
        print("✅ تم إنشاء مفتاح التشفير من متغير البيئة")
        return key
    if not sys.stdin.isatty():
        key = Fernet.generate_key()
        with open(key_file, 'wb') as f:
            f.write(key)
        return key
    try:
        import getpass
        print("🔐 لإعداد تشفير قاعدة البيانات، أدخل كلمة مرور قوية:")
        password = getpass.getpass("كلمة المرور: ")
        confirm = getpass.getpass("تأكيد كلمة المرور: ")
        if password != confirm:
            print("❌ كلمات المرور غير متطابقة!")
            sys.exit(1)
        if len(password) < 8:
            print("❌ كلمة المرور يجب أن تكون 8 أحرف على الأقل!")
            sys.exit(1)
        salt = os.urandom(16)
        key = derive_key_from_password(password, salt)
        with open(key_file, 'wb') as f:
            f.write(key)
        with open(salt_file, 'wb') as f:
            f.write(salt)
        print("✅ تم إنشاء مفتاح التشفير وحفظه بشكل آمن")
        return key
    except:
        key = Fernet.generate_key()
        with open(key_file, 'wb') as f:
            f.write(key)
        return key

ENCRYPTION_KEY = get_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

def get_backup_encryption_key() -> bytes:
    backup_key_file = DATA_PATH / ".backup_key"
    if backup_key_file.exists():
        try:
            with open(backup_key_file, 'rb') as f:
                return f.read()
        except:
            pass
    new_key = Fernet.generate_key()
    with open(backup_key_file, 'wb') as f:
        f.write(new_key)
    return new_key

BACKUP_ENCRYPTION_KEY = get_backup_encryption_key()
BACKUP_CIPHER = Fernet(BACKUP_ENCRYPTION_KEY)

def encrypt_file_stream(src: Path, dst: Path, cipher: Fernet, chunk_size: int = 64*1024):
    with open(src, 'rb') as f_in, open(dst, 'wb') as f_out:
        while True:
            chunk = f_in.read(chunk_size)
            if not chunk:
                break
            encrypted_chunk = cipher.encrypt(chunk)
            f_out.write(encrypted_chunk)

def decrypt_file_stream(src: Path, dst: Path, cipher: Fernet, chunk_size: int = 64*1024):
    with open(src, 'rb') as f_in, open(dst, 'wb') as f_out:
        while True:
            chunk = f_in.read(chunk_size)
            if not chunk:
                break
            decrypted_chunk = cipher.decrypt(chunk)
            f_out.write(decrypted_chunk)

def encrypt_db_backup() -> Path:
    if not DB_ENCRYPTION:
        return DB_PATH
    encrypted_path = DB_PATH.with_suffix('.enc')
    encrypt_file_stream(DB_PATH, encrypted_path, cipher_suite)
    return encrypted_path

def compress_backup(data: bytes) -> bytes:
    try:
        import zstandard
        compressor = zstandard.ZstdCompressor(level=3)
        return compressor.compress(data)
    except:
        return gzip.compress(data)

def decompress_backup(data: bytes) -> bytes:
    try:
        import zstandard
        decompressor = zstandard.ZstdDecompressor()
        return decompressor.decompress(data)
    except:
        return gzip.decompress(data)

# ===================================================================
# 10. نظام التخزين المؤقت
# ===================================================================
try:
    from cachetools import TTLCache, LRUCache
    CACHETOOLS_AVAILABLE = True
    _admin_cache = TTLCache(maxsize=1000, ttl=60)
    _security_cache = TTLCache(maxsize=500, ttl=30)
    _auth_cache = TTLCache(maxsize=1000, ttl=30)
except ImportError:
    CACHETOOLS_AVAILABLE = False
    _admin_cache = {}
    _security_cache = {}
    _auth_cache = {}

_flood_cache = OrderedDict()
_flood_cache_time = {'last_cleanup': 0}
_failed_attempts_cache = {}
_token_cache = {}

user_points_last_hour = defaultdict(lambda: (0, 0.0))
_translation_cache = {}
user_translation_settings_cache = {}
_user_translation_cache_lock = asyncio.Lock()
_BANNED_PATTERNS_LOCK = asyncio.Lock()
BANNED_PATTERNS = []

# ===================================================================
# 11. دوال مساعدة
# ===================================================================
def load_banned_words_from_file(file_path: Path) -> List[str]:
    words = []
    if not file_path.exists():
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("# قائمة الكلمات المحظورة - كل كلمة في سطر منفصل\n")
                f.write("# ابدأ السطر بـ # للتعليق\n\n")
                f.write("بورن\nسكس\nجنس\nعري\nخمر\nخمور\nمخدرات\nحشيش\nكحول\nدعارة\n")
        except Exception as e:
            print(f"❌ فشل إنشاء ملف الكلمات المحظورة: {e}")
        return words
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                word = line.lower()
                if len(word) >= 2:
                    words.append(word)
        print(f"✅ تم تحميل {len(words)} كلمة محظورة")
    except Exception as e:
        print(f"❌ فشل تحميل الكلمات المحظورة: {e}")
    return words

def clean_text_for_telegram(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[\u200b\u200c\u200d\u2060\uFEFF\u202a\u202b\u202c\u202d\u202e]', '', text)
    return text

def escape_markdown_v2(text: str) -> str:
    if not text:
        return ""
    special_chars = r'_*[]()~`>#+\-=|{}.!\\'
    def escape_char(match):
        char = match.group(0)
        start = match.start()
        if start > 0 and text[start-1] == '\\':
            return char
        return '\\' + char
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', escape_char, text)

def sanitize_text(text: str, max_length: int = 4096, allow_tags: list = None) -> str:
    if not text:
        return ""
    try:
        import bleach
        if allow_tags is None:
            allow_tags = ['b', 'i', 'u', 's', 'a', 'code', 'pre', 'strong', 'em']
        cleaned = bleach.clean(
            text,
            tags=allow_tags,
            attributes={'a': ['href', 'title']},
            styles=[],
            strip=True
        )
    except:
        cleaned = text
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned

def encode_callback_data(data: str) -> str:
    return urllib.parse.quote(data, safe='')

def decode_callback_data(data: str) -> str:
    return urllib.parse.unquote(data)

def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def mecca_now():
    return utc_now() + timedelta(hours=3)

def utc_now_iso():
    return utc_now().isoformat()

def mecca_now_iso():
    return mecca_now().isoformat()

def to_naive(dt):
    if dt is None:
        return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

def mecca_to_utc(mecca_dt):
    if mecca_dt is None:
        return None
    if hasattr(mecca_dt, 'tzinfo') and mecca_dt.tzinfo is not None:
        mecca_dt = mecca_dt.replace(tzinfo=None)
    return mecca_dt - timedelta(hours=3)

def utc_to_mecca(utc_dt):
    if utc_dt is None:
        return None
    if hasattr(utc_dt, 'tzinfo') and utc_dt.tzinfo is not None:
        utc_dt = utc_dt.replace(tzinfo=None)
    return utc_dt + timedelta(hours=3)

def parse_days_of_week_safe(days_str):
    if not days_str:
        return []
    try:
        return json.loads(days_str)
    except:
        return []

def parse_dates_safe(dates_str):
    if not dates_str:
        return []
    try:
        return json.loads(dates_str)
    except:
        return []

def contains_link(text):
    patterns = [
        r'https?://\S+',
        r'www\.\S+',
        r't\.me/\S+',
        r'telegram\.me/\S+',
        r'\b[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+\S*'
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)

def contains_mention(text):
    return bool(re.search(r'@\w+', text))

def get_ram_usage():
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {'total': round(mem.total / (1024**3), 1), 'used': round(mem.used / (1024**3), 1), 'percent': mem.percent}
    except:
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
            mem_total = 0
            mem_available = 0
            for line in lines:
                if 'MemTotal:' in line:
                    mem_total = int(line.split()[1]) / (1024 * 1024)
                if 'MemAvailable:' in line:
                    mem_available = int(line.split()[1]) / (1024 * 1024)
            if mem_total > 0:
                used = mem_total - mem_available
                percent = (used / mem_total) * 100
                return {'total': round(mem_total, 1), 'used': round(used, 1), 'percent': round(percent, 1)}
        except:
            pass
    return {'total': 0, 'used': 0, 'percent': 0}

def generate_operation_token() -> str:
    return secrets.token_urlsafe(32)

def validate_time_format(time_str: str) -> bool:
    if not time_str:
        return False
    pattern = r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$'
    return bool(re.match(pattern, str(time_str)))

def format_welcome_message(template: str, user_name: str, chat_name: str) -> str:
    safe_user = html.escape(str(user_name))
    safe_chat = html.escape(str(chat_name))
    try:
        return template.format(user=safe_user, chat=safe_chat)
    except:
        return f"مرحباً {safe_user} في {safe_chat}"

# ===================================================================
# 12. معالج الأخطاء
# ===================================================================
class ErrorHandler:
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.errors = defaultdict(int)

    async def handle_async(self, func: Callable, *args, **kwargs) -> Any:
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except (TimedOut, NetworkError) as e:
                last_error = e
                delay = self.base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(delay)
                continue
            except Exception as e:
                raise
        if last_error:
            raise last_error
        return None

error_handler = ErrorHandler()

# ===================================================================
# 13. دوال الإرسال الآمن
# ===================================================================
async def safe_send_markdown(bot, chat_id: int, text: str, reply_markup=None, **kwargs):
    if not text:
        return None
    clean_text = sanitize_text(text)
    MAX_LEN = 4096
    try:
        escaped = escape_markdown_v2(clean_text)
        if len(escaped) > MAX_LEN:
            cut_point = MAX_LEN - 3
            while cut_point > 0 and escaped[cut_point - 1] in ('\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!', '@'):
                cut_point -= 1
            escaped = escaped[:cut_point] + "..."
        return await bot.send_message(
            chat_id=chat_id,
            text=escaped,
            parse_mode='MarkdownV2',
            reply_markup=reply_markup,
            **kwargs
        )
    except BadRequest as e:
        if "User_bot_to_bot_disabled" in str(e):
            return None
        try:
            html_text = clean_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if len(html_text) > MAX_LEN:
                html_text = html_text[:MAX_LEN-3] + "..."
            return await bot.send_message(
                chat_id=chat_id,
                text=html_text,
                parse_mode='HTML',
                reply_markup=reply_markup,
                **kwargs
            )
        except:
            try:
                plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', clean_text)
                if len(plain) > MAX_LEN:
                    plain = plain[:MAX_LEN-3] + "..."
                return await bot.send_message(
                    chat_id=chat_id,
                    text=plain,
                    reply_markup=reply_markup,
                    **kwargs
                )
            except:
                raise
    except:
        raise

async def safe_edit_markdown(query, text: str, reply_markup=None, **kwargs):
    if not query or not query.message:
        return None
    if not text:
        return None
    clean_text = sanitize_text(text)
    MAX_LEN = 4096
    try:
        escaped = escape_markdown_v2(clean_text)
        if len(escaped) > MAX_LEN:
            cut_point = MAX_LEN - 3
            while cut_point > 0 and escaped[cut_point - 1] in ('\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!', '@'):
                cut_point -= 1
            escaped = escaped[:cut_point] + "..."
        return await query.edit_message_text(
            text=escaped,
            parse_mode='MarkdownV2',
            reply_markup=reply_markup,
            **kwargs
        )
    except:
        try:
            html_text = clean_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if len(html_text) > MAX_LEN:
                html_text = html_text[:MAX_LEN-3] + "..."
            return await query.edit_message_text(
                text=html_text,
                parse_mode='HTML',
                reply_markup=reply_markup,
                **kwargs
            )
        except:
            try:
                plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', clean_text)
                if len(plain) > MAX_LEN:
                    plain = plain[:MAX_LEN-3] + "..."
                return await query.edit_message_text(
                    text=plain,
                    reply_markup=reply_markup,
                    **kwargs
                )
            except:
                raise

# ===================================================================
# 14. نظام اللغة
# ===================================================================
SUPPORTED_LANGUAGES = {
    'ar': 'العربية 🇸🇦', 'en': 'English 🇬🇧', 'fr': 'Français 🇫🇷',
    'tr': 'Türkçe 🇹🇷', 'zh': '中文 🇨🇳', 'ru': 'Русский 🇷🇺',
    'de': 'Deutsch 🇩🇪', 'es': 'Español 🇪🇸', 'it': 'Italiano 🇮🇹',
    'pt': 'Português 🇵🇹', 'ja': '日本語 🇯🇵', 'ko': '한국어 🇰🇷'
}

_lang_data = {}
_lang_cache_time = {}
LANG_CACHE_TTL = 300
_lang_lock = asyncio.Lock()
user_language = {}

def create_default_lang_files():
    default_langs = {
        'ar': {
            "welcome": "🌿 **مرحباً بك في ريلاكس مانيجر**\nاختر اللغة المناسبة",
            "main_title": "🌿 **{0}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 المعرف: `{1}`\n👥 مجموعاتي: {2}\n💎 الاشتراك: {3}\n📡 القناة النشطة: {4}\n📝 المنشورات غير المنشورة: {5}\n⚙️ النشر التلقائي: {6}",
            "no_channels": "لا توجد قنوات",
            "add_channel": "➕ إضافة قناة",
            "my_channels": "📡 قنواتي",
            "add_15_posts": "📥 إضافة 15 منشور",
            "publish_one": "📤 نشر واحد",
            "my_posts_btn": "📋 منشوراتي",
            "recycle": "♻️ إعادة تدوير",
            "stats_btn": "📊 إحصائياتي",
            "my_stats_btn": "📈 إحصائيات كاملة",
            "my_groups_btn": "👥 مجموعاتي",
            "settings_btn": "⚙️ الإعدادات",
            "schedule_btn": "⏰ الجدولة",
            "help_btn": "❓ المساعدة",
            "trial_btn": "🎁 تجربة مجانية",
            "subscribe_btn": "💎 اشتراك",
            "developer_btn": "👨‍💻 المطور",
            "language_btn": "🌐 اللغة",
            "support_btn": "📞 الدعم",
            "referral": "🔗 الإحالات",
            "reminder_settings": "⏰ التذكيرات",
            "translation_settings": "🌐 الترجمة",
            "publish_all": "📤 نشر الكل",
            "updates_btn": "📢 التحديثات",
            "add_to_group": "➕ إضافة إلى مجموعة",
            "admin_panel": "👑 لوحة الأدمن",
            "my_rank_btn": "📊 رتبتي",
            "top_10_btn": "🏆 أفضل 10",
            "schedule_post_btn": "📝 جدولة منشور",
            "channel_stats": "📊 إحصائيات القناة",
            "my_channels_summary": "📊 ملخص قنواتي",
            "auto_on": "مفعل",
            "auto_off": "معطل",
            "subscribed": "✅ مفعل",
            "not_subscribed": "❌ غير مفعل",
            "send_channel_id": "📡 أرسل معرف القناة (مثال: @RelaxMgrr أو -100123456)",
            "channel_added": "✅ تم إضافة القناة {0}",
            "channel_exists": "⚠️ القناة موجودة مسبقاً",
            "no_channels_list": "📭 لا توجد قنوات مسجلة",
            "channels_list": "📡 **قنواتي**\nاختر قناة للتحكم بها:",
            "delete_channel": "🗑️ حذف",
            "channel_deleted": "✅ تم حذف القناة",
            "delete_failed": "❌ فشل الحذف",
            "no_posts": "📭 لا توجد منشورات",
            "my_posts_title": "📋 **منشوراتي غير المنشورة**",
            "confirm_delete": "⚠️ هل أنت متأكد من حذف جميع المنشورات؟",
            "deleted_all": "✅ تم حذف جميع المنشورات",
            "recycled": "♻️ تم إعادة تدوير جميع المنشورات",
            "pending_stats": "📊 **إحصائيات المنشورات**\n━━━━━━━━━━━━━━━━━━━━━━\n📝 غير المنشورة: {0}\n📋 الإجمالي: {1}",
            "stats": "📈 **إحصائياتي الكاملة**\n━━━━━━━━━━━━━━━━━━━━━━\n📡 القنوات: {0}\n📝 إجمالي المنشورات: {1}\n⏳ غير المنشورة: {2}\n👥 المجموعات: {3}\n⚙️ النشر التلقائي: {4}",
            "settings": "⚙️ **الإعدادات**\nاختر الإعداد المطلوب:",
            "disabled": "❌ تعطيل",
            "enabled": "✅ تفعيل",
            "auto_toggled": "✅ تم تغيير حالة النشر التلقائي إلى: {0}",
            "schedule_settings": "⏰ **إعدادات الجدولة**\n━━━━━━━━━━━━━━━━━━━━━━\n{0}\n━━━━━━━━━━━━━━━━━━━━━━\nاختر نوع الجدولة:",
            "interval_minutes": "دقائق: {0}",
            "interval_hours": "ساعات: {0}",
            "interval_days": "أيام: {0}",
            "days_week": "أيام الأسبوع: {0}",
            "specific_dates": "تواريخ محددة: {0}",
            "nothing": "لا شيء",
            "send_minutes": "⏱️ أرسل عدد الدقائق (مثال: 30)",
            "send_hours": "⏱️ أرسل عدد الساعات (مثال: 2)",
            "send_days": "⏱️ أرسل عدد الأيام (مثال: 1)",
            "send_dates": "📅 أرسل التواريخ مفصولة بفواصل (مثال: 2024-12-25,2025-01-01)",
            "send_time": "🕐 أرسل وقت النشر (مثال: 14:30)",
            "interval_set": "✅ تم حفظ الإعدادات",
            "invalid_number": "❌ رقم غير صالح",
            "invalid_date": "❌ تاريخ غير صالح",
            "invalid_time": "❌ وقت غير صالح",
            "days_saved": "✅ تم حفظ أيام النشر",
            "monday": "الإثنين",
            "tuesday": "الثلاثاء",
            "wednesday": "الأربعاء",
            "thursday": "الخميس",
            "friday": "الجمعة",
            "saturday": "السبت",
            "sunday": "الأحد",
            "admin_only": "🔒 هذا الأمر للمشرفين فقط!",
            "group_only": "🔒 هذا الأمر يعمل فقط في المجموعات!",
            "locked": "🔒 تم قفل المجموعة",
            "unlocked": "🔓 تم فتح المجموعة",
            "cancelled": "❌ تم الإلغاء",
            "error": "⚠️ حدث خطأ، حاول مرة أخرى",
            "help": "❓ **المساعدة**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 **الأوامر المتاحة:**\n/start - القائمة الرئيسية\n/trial - تجربة مجانية\n/subscribe - الاشتراك\n/syncgroup - تفعيل المجموعة\n/security - إعدادات الأمان\n/register_hidden_owner - تسجيل مالك مخفي\n/add_hidden_admin - إضافة مشرف مخفي\n/remove_hidden_admin - إزالة مشرف مخفي\n/list_hidden_admins - عرض المشرفين المخفيين\n/rank - رتبتك\n/top - أفضل 10\n/stats - إحصائيات القناة\n/lock - قفل المجموعة\n/unlock - فتح المجموعة\n/schedule - جدولة منشور\n/panel - لوحة التحكم\n/language - تغيير اللغة\n/support - مركز الدعم\n/help - هذه المساعدة\n/developer - المطور\n/updates - التحديثات\n/contests - المسابقات\n/create_contest - إنشاء مسابقة\n/declare_winner - إعلان فائز\n/set_rules - تعيين قوانين المجموعة\n/rules - عرض قوانين المجموعة",
            "support_welcome": "📞 **مركز الدعم**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الخدمة المطلوبة:",
            "support_help": "❓ **المساعدة**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 للتواصل مع الدعم:\n• استخدم /support\n• اكتب رسالتك\n• ستصلك تذكرة برقم\n• سنرد عليك بأسرع وقت",
            "trial_used": "❌ لقد استخدمت التجربة المجانية مسبقاً",
            "already_subscribed": "✅ لديك اشتراك فعال بالفعل",
            "trial": "🎁 **تم تفعيل التجربة المجانية!**\n━━━━━━━━━━━━━━━━━━━━━━\n✅ لديك 30 يوماً مجاناً\n📌 استمتع بجميع الميزات",
            "subscribe": "💎 **الاشتراك**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الباقة المناسبة لك:\n\n⭐ 1 يوم - 5 نجوم\n⭐ 2 يوم - 9 نجوم\n⭐ شهر (30 يوم) - 50 نجمة\n⭐ 3 أشهر (90 يوم) - 120 نجمة",
            "updates_text": "📢 **آخر التحديثات**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 تابع قناة التحديثات لمعرفة كل جديد:",
            "referral_title": "🔗 **الإحالات**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 رابط الإحالة الخاص بك:\n`https://t.me/{1}?start=ref_{0}`\n\n👥 عدد المحالين: {3}\n🎁 المكافآت المتاحة: {4} يوم\n⭐ المكافأة لكل إحالة: {5} يوم\n🎁 نقاط الترحيب: {6}",
            "copy_link": "📋 نسخ الرابط",
            "claim_reward": "🎁 صرف المكافآت",
            "referral_list": "📋 قائمة المحالين",
            "no_referrals": "📭 لا توجد إحالات بعد",
            "no_reward_available": "❌ لا توجد مكافآت متاحة للصرف",
            "reward_claimed": "✅ تم صرف {0} يوم اشتراك!",
            "reminder_title": "⏰ **إعدادات التذكيرات**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 تذكير انتهاء الاشتراك: {0}\n📊 تقرير يومي: {1}\n📈 تقرير أسبوعي: {2}\n⏰ التذكير قبل: {3} أيام",
            "reminder_sub": "🔔 تذكير الاشتراك",
            "reminder_daily": "📊 تقرير يومي",
            "reminder_weekly": "📈 تقرير أسبوعي",
            "reminder_days_btn": "⏰ عدد الأيام",
            "reminder_lang_btn": "🌐 لغة الإشعارات",
            "subscription_warning": "⚠️ **تنبيه!**\nاشتراكك ينتهي خلال {0} أيام\nقم بتجديده الآن لتستمر الميزات 💎",
            "daily_stats": "📊 **تقريرك اليومي**\n━━━━━━━━━━━━━━━━━━━━━━\n📡 القنوات: {0}\n📝 إجمالي المنشورات: {1}\n⏳ غير المنشورة: {2}\n👥 المجموعات: {3}",
            "weekly_report": "📈 **تقريرك الأسبوعي**\n━━━━━━━━━━━━━━━━━━━━━━\n📡 القنوات: {0}\n📝 إجمالي المنشورات: {1}\n⏳ غير المنشورة: {2}\n👥 المجموعات: {3}\n🔗 الإحالات: {4}",
            "translation_status_off": "معطلة ❌",
            "translation_status_on": "مفعلة ✅ إلى {0}",
            "translation_settings": "إعدادات الترجمة",
            "translation_how_it_works": "📌 كيفية العمل:\nسيتم ترجمة المنشورات تلقائياً عند النشر إلى اللغة التي تختارها",
            "translation_choose": "اختر لغة الترجمة:",
            "translation_off": "🚫 إيقاف الترجمة",
            "translation_disabled": "✅ تم إيقاف الترجمة",
            "translation_enabled": "✅ تم تفعيل الترجمة إلى {0}",
            "contests_menu": "🏆 المسابقات",
            "contest_participants_count": "👥 عدد المشاركين: {0}",
            "contest_time_left": "⏳ متبقي {0} يوم",
            "contest_expired_label": "🔴 انتهت",
            "hidden_admin_added": "✅ تم إضافة المشرف المخفي `{0}` بنجاح",
            "hidden_admin_removed": "✅ تم إزالة المشرف المخفي `{0}` بنجاح",
            "hidden_admin_list": "🔒 **قائمة المشرفين المخفيين**\n━━━━━━━━━━━━━━━━━━━━━━\n{0}",
            "no_hidden_admins": "📭 لا يوجد مشرفين مخفيين في هذه المجموعة",
            "hidden_owner_registered": "✅ تم تسجيل المالك المخفي بنجاح",
            "hidden_owner_already": "⚠️ أنت مسجل بالفعل كمالك مخفي",
            "promo_message": "👋 **مرحباً بك في مجموعتنا!**\n\nللاستفادة من جميع خدمات البوت، يرجى التوجه إلى الخاص:\n👉 @{0}\n\nهناك يمكنك إدارة القنوات، ضبط الإعدادات، والمزيد! 🚀",
            "back": "🔙 رجوع",
            "group_registered": "✅ **تم تسجيل المجموعة!**\n\n🔹 **لتفعيل الميزات المتقدمة:**\n• تأكد من أن البوت مشرف\n• استخدم `/syncgroup` مرة أخرى\n\n📌 **إذا كنت مشرفاً:**\n• استخدم `/register_hidden_owner` لتسجيل نفسك كمالك مخفي\n• استخدم `/security` لإعدادات الأمان",
            "activation_requested": "✅ **تم تسجيل المجموعة وإشعار المشرفين!**\n\n📌 سيتم إشعار المشرفين لتفعيل البوت.\n⏳ انتظر حتى يقوم أحد المشرفين بتفعيل البوت.",
            "activation_notification": "📢 **طلب تفعيل البوت!**\n\n👤 المستخدم: {0}\n📌 المجموعة: {1}\n🆔 المعرف: `{2}`\n\nلتفعيل البوت، استخدم:\n`/syncgroup`\nفي المجموعة.",
            "no_admins_found": "⚠️ لا يمكن العثور على مشرفين في المجموعة.\nتأكد من أن البوت مشرف."
        },
        'en': {
            "welcome": "🌿 **Welcome to Relax Manager**\nChoose your language",
            "main_title": "🌿 **{0}**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 ID: `{1}`\n👥 My Groups: {2}\n💎 Subscription: {3}\n📡 Active Channel: {4}\n📝 Unpublished Posts: {5}\n⚙️ Auto Publish: {6}",
            "no_channels": "No channels",
            "add_channel": "➕ Add Channel",
            "my_channels": "📡 My Channels",
            "add_15_posts": "📥 Add 15 Posts",
            "publish_one": "📤 Publish One",
            "my_posts_btn": "📋 My Posts",
            "recycle": "♻️ Recycle",
            "stats_btn": "📊 My Stats",
            "my_stats_btn": "📈 Full Stats",
            "my_groups_btn": "👥 My Groups",
            "settings_btn": "⚙️ Settings",
            "schedule_btn": "⏰ Schedule",
            "help_btn": "❓ Help",
            "trial_btn": "🎁 Free Trial",
            "subscribe_btn": "💎 Subscribe",
            "developer_btn": "👨‍💻 Developer",
            "language_btn": "🌐 Language",
            "support_btn": "📞 Support",
            "referral": "🔗 Referrals",
            "reminder_settings": "⏰ Reminders",
            "translation_settings": "🌐 Translation",
            "publish_all": "📤 Publish All",
            "updates_btn": "📢 Updates",
            "add_to_group": "➕ Add to Group",
            "admin_panel": "👑 Admin Panel",
            "my_rank_btn": "📊 My Rank",
            "top_10_btn": "🏆 Top 10",
            "schedule_post_btn": "📝 Schedule Post",
            "channel_stats": "📊 Channel Stats",
            "my_channels_summary": "📊 My Channels Summary",
            "auto_on": "Enabled",
            "auto_off": "Disabled",
            "subscribed": "✅ Active",
            "not_subscribed": "❌ Inactive",
            "send_channel_id": "📡 Send channel ID (e.g., @channel or -100123456)",
            "channel_added": "✅ Channel {0} added",
            "channel_exists": "⚠️ Channel already exists",
            "no_channels_list": "📭 No channels registered",
            "channels_list": "📡 **My Channels**\nSelect a channel to control:",
            "delete_channel": "🗑️ Delete",
            "channel_deleted": "✅ Channel deleted",
            "delete_failed": "❌ Delete failed",
            "no_posts": "📭 No posts",
            "my_posts_title": "📋 **My Unpublished Posts**",
            "confirm_delete": "⚠️ Are you sure you want to delete all posts?",
            "deleted_all": "✅ All posts deleted",
            "recycled": "♻️ All posts recycled",
            "pending_stats": "📊 **Post Statistics**\n━━━━━━━━━━━━━━━━━━━━━━\n📝 Unpublished: {0}\n📋 Total: {1}",
            "stats": "📈 **My Full Stats**\n━━━━━━━━━━━━━━━━━━━━━━\n📡 Channels: {0}\n📝 Total Posts: {1}\n⏳ Unpublished: {2}\n👥 Groups: {3}\n⚙️ Auto Publish: {4}",
            "settings": "⚙️ **Settings**\nSelect the setting:",
            "disabled": "❌ Disable",
            "enabled": "✅ Enable",
            "auto_toggled": "✅ Auto publish status changed to: {0}",
            "schedule_settings": "⏰ **Schedule Settings**\n━━━━━━━━━━━━━━━━━━━━━━\n{0}\n━━━━━━━━━━━━━━━━━━━━━━\nSelect schedule type:",
            "interval_minutes": "Minutes: {0}",
            "interval_hours": "Hours: {0}",
            "interval_days": "Days: {0}",
            "days_week": "Days of week: {0}",
            "specific_dates": "Specific dates: {0}",
            "nothing": "Nothing",
            "send_minutes": "⏱️ Send number of minutes (e.g., 30)",
            "send_hours": "⏱️ Send number of hours (e.g., 2)",
            "send_days": "⏱️ Send number of days (e.g., 1)",
            "send_dates": "📅 Send dates separated by commas (e.g., 2024-12-25,2025-01-01)",
            "send_time": "🕐 Send publish time (e.g., 14:30)",
            "interval_set": "✅ Settings saved",
            "invalid_number": "❌ Invalid number",
            "invalid_date": "❌ Invalid date",
            "invalid_time": "❌ Invalid time",
            "days_saved": "✅ Days saved",
            "monday": "Monday",
            "tuesday": "Tuesday",
            "wednesday": "Wednesday",
            "thursday": "Thursday",
            "friday": "Friday",
            "saturday": "Saturday",
            "sunday": "Sunday",
            "admin_only": "🔒 This command is for admins only!",
            "group_only": "🔒 This command works only in groups!",
            "locked": "🔒 Group locked",
            "unlocked": "🔓 Group unlocked",
            "cancelled": "❌ Cancelled",
            "error": "⚠️ An error occurred, try again",
            "help": "❓ **Help**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 **Available Commands:**\n/start - Main Menu\n/trial - Free Trial\n/subscribe - Subscribe\n/syncgroup - Activate Group\n/security - Security Settings\n/register_hidden_owner - Register Hidden Owner\n/add_hidden_admin - Add Hidden Admin\n/remove_hidden_admin - Remove Hidden Admin\n/list_hidden_admins - List Hidden Admins\n/rank - Your Rank\n/top - Top 10\n/stats - Channel Stats\n/lock - Lock Group\n/unlock - Unlock Group\n/schedule - Schedule Post\n/panel - Control Panel\n/language - Change Language\n/support - Support Center\n/help - This Help\n/developer - Developer\n/updates - Updates\n/contests - Contests\n/create_contest - Create Contest\n/declare_winner - Declare Winner\n/set_rules - Set Group Rules\n/rules - View Group Rules",
            "support_welcome": "📞 **Support Center**\n━━━━━━━━━━━━━━━━━━━━━━\nSelect the required service:",
            "support_help": "❓ **Help**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 To contact support:\n• Use /support\n• Write your message\n• You'll get a ticket number\n• We'll reply ASAP",
            "trial_used": "❌ You have already used the free trial",
            "already_subscribed": "✅ You already have an active subscription",
            "trial": "🎁 **Free Trial Activated!**\n━━━━━━━━━━━━━━━━━━━━━━\n✅ You have 30 days free\n📌 Enjoy all features",
            "subscribe": "💎 **Subscription**\n━━━━━━━━━━━━━━━━━━━━━━\nChoose your plan:\n\n⭐ 1 Day - 5 Stars\n⭐ 2 Days - 9 Stars\n⭐ 30 Days (Month) - 50 Stars\n⭐ 90 Days (3 Months) - 120 Stars",
            "updates_text": "📢 **Latest Updates**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 Follow updates channel for news:",
            "referral_title": "🔗 **Referrals**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 Your referral link:\n`https://t.me/{1}?start=ref_{0}`\n\n👥 Total Referrals: {3}\n🎁 Available Rewards: {4} days\n⭐ Reward per Referral: {5} days\n🎁 Welcome Bonus: {6}",
            "copy_link": "📋 Copy Link",
            "claim_reward": "🎁 Claim Rewards",
            "referral_list": "📋 Referral List",
            "no_referrals": "📭 No referrals yet",
            "no_reward_available": "❌ No rewards available to claim",
            "reward_claimed": "✅ Claimed {0} days subscription!",
            "reminder_title": "⏰ **Reminder Settings**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 Subscription Reminder: {0}\n📊 Daily Report: {1}\n📈 Weekly Report: {2}\n⏰ Remind Before: {3} days",
            "reminder_sub": "🔔 Subscription Reminder",
            "reminder_daily": "📊 Daily Report",
            "reminder_weekly": "📈 Weekly Report",
            "reminder_days_btn": "⏰ Days Before",
            "reminder_lang_btn": "🌐 Notification Language",
            "subscription_warning": "⚠️ **Warning!**\nYour subscription expires in {0} days\nRenew now to keep features 💎",
            "daily_stats": "📊 **Your Daily Report**\n━━━━━━━━━━━━━━━━━━━━━━\n📡 Channels: {0}\n📝 Total Posts: {1}\n⏳ Unpublished: {2}\n👥 Groups: {3}",
            "weekly_report": "📈 **Your Weekly Report**\n━━━━━━━━━━━━━━━━━━━━━━\n📡 Channels: {0}\n📝 Total Posts: {1}\n⏳ Unpublished: {2}\n👥 Groups: {3}\n🔗 Referrals: {4}",
            "translation_status_off": "Disabled ❌",
            "translation_status_on": "Enabled ✅ to {0}",
            "translation_settings": "Translation Settings",
            "translation_how_it_works": "📌 How it works:\nPosts will be automatically translated to your chosen language when published",
            "translation_choose": "Choose translation language:",
            "translation_off": "🚫 Disable Translation",
            "translation_disabled": "✅ Translation disabled",
            "translation_enabled": "✅ Translation enabled to {0}",
            "contests_menu": "🏆 Contests",
            "contest_participants_count": "👥 Participants: {0}",
            "contest_time_left": "⏳ {0} days left",
            "contest_expired_label": "🔴 Expired",
            "hidden_admin_added": "✅ Hidden admin `{0}` added successfully",
            "hidden_admin_removed": "✅ Hidden admin `{0}` removed successfully",
            "hidden_admin_list": "🔒 **Hidden Admins List**\n━━━━━━━━━━━━━━━━━━━━━━\n{0}",
            "no_hidden_admins": "📭 No hidden admins in this group",
            "hidden_owner_registered": "✅ Hidden owner registered successfully",
            "hidden_owner_already": "⚠️ You are already registered as hidden owner",
            "promo_message": "👋 **Welcome to our group!**\n\nTo use all bot features, please go to private chat:\n👉 @{0}\n\nThere you can manage channels, adjust settings, and more! 🚀",
            "back": "🔙 Back",
            "group_registered": "✅ **Group registered!**\n\n🔹 **To activate advanced features:**\n• Make sure the bot is admin\n• Use `/syncgroup` again\n\n📌 **If you are an admin:**\n• Use `/register_hidden_owner` to register as hidden owner\n• Use `/security` for security settings",
            "activation_requested": "✅ **Group registered and admins notified!**\n\n📌 Admins will be notified to activate the bot.\n⏳ Wait for an admin to activate the bot.",
            "activation_notification": "📢 **Bot activation request!**\n\n👤 User: {0}\n📌 Group: {1}\n🆔 ID: `{2}`\n\nTo activate the bot, use:\n`/syncgroup`\nin the group.",
            "no_admins_found": "⚠️ No admins found in the group.\nMake sure the bot is admin."
        }
    }
    for lang, texts in default_langs.items():
        lang_file = LANG_PATH / f"{lang}.json"
        if not lang_file.exists():
            with open(lang_file, 'w', encoding='utf-8') as f:
                json.dump(texts, f, ensure_ascii=False, indent=2)

def load_all_languages():
    global _lang_data
    for lang_file in LANG_PATH.glob("*.json"):
        lang = lang_file.stem
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                _lang_data[lang] = json.load(f)
        except Exception as e:
            print(f"⚠️ فشل تحميل {lang_file}: {e}")
    if not _lang_data:
        create_default_lang_files()
        load_all_languages()

load_all_languages()

def get_text(user_id: int, key: str) -> str:
    lang = user_language.get(user_id, 'ar')
    texts = _lang_data.get(lang, {})
    if key not in texts:
        en_texts = _lang_data.get('en', {})
        if key in en_texts:
            return en_texts[key]
    return texts.get(key, key)

async def set_user_language(user_id: int, lang: str):
    user_language[user_id] = lang

# ===================================================================
# 15. الردود التلقائية المدمجة (200+ رد)
# ===================================================================
WELCOME_REPLIES = {
    "مرحباً": ["أهلاً وسهلاً بك في مجموعتنا 🤍", "أهلاً بك، نورت المجموعة 🌸", "مرحباً، تشرفنا بوجودك 🙏"],
    "السلام عليكم": ["وعليكم السلام ورحمة الله وبركاته 🌹", "وعليكم السلام، نورت المجموعة 🌸", "الله يبارك فيك 🙏"],
    "اهلاً": ["أهلاً بك، تشرفنا 🙏", "أهلاً وسهلاً 🌹", "نورتنا يا غالي 🌸"],
    "هلا": ["هلا والله، نورت المجموعة ✨", "هلا بك مليون 🌹", "هلا هلا، تشرفنا 🙏"],
    "مرحبا بكم": ["أهلاً بكم جميعاً، تشرفنا بتواجدكم 🌸", "نورتونا جميعاً 🌹", "أهلاً وسهلاً بالجميع 🙏"],
    "هلا والله": ["هلا بك، نورت الدنيا 🌹", "هلا والله، تشرفنا 🌸", "نورت يا غالي ✨"],
    "مرحبا مليون": ["مليون مرحبة، نورت ✨", "مرحبا مليون، تشرفنا 🌹", "نورت الدنيا يا حلو 🌸"],
    "اهلا وسهلا": ["أهلاً وسهلاً، حياك الله 🙏", "أهلاً وسهلاً، نورتنا 🌹", "حياك الله وبياك 🌸"],
    "نورت": ["نورت المجموعة بوجودك 🌸", "نورت الدنيا ياحلو 🌹", "نورتنا جميعاً ✨"],
    "شرفت": ["شرفتنا يا غالي 🌹", "شرفت الدنيا بوجودك 🌸", "تشرفنا بمعرفتك 🙏"],
    "تشرفنا": ["تشرفنا بمعرفتك 🙏", "الشرف لنا 🌹", "نورتنا بوجودك 🌸"],
    "منور": ["منور الدنيا يا حلو 🌸", "منور أنت ياغالي 🌹", "نورت المجموعة ✨"],
    "ياهلا": ["ياهلا بك مليون 🌹", "ياهلا وسهلا 🌸", "نورت يا غالي 🙏"],
    "اهلين": ["أهلين وسهلين ✨", "أهلين بك 🌹", "حياك الله 🌸"],
    "مسا الخير": ["مسا النور 🌙", "مسا الخير، نورتنا 🌹", "مسا العسل 🌸"],
    "صباح الخير": ["صباح النور 🌞", "صباح الخير، نورت اليوم 🌹", "صباح الورد 🌸"],
    "تصبح على خير": ["وأنت من أهله 🌙", "تصبح على خير ورضا 🌹", "الله يسلمك 🌸"],
    "مساء النور": ["أهلين وسهلين 🌸", "مساء النور والسرور 🌹", "حياك الله 🙏"],
    "نورت الدنيا": ["أنت النور 🌹", "نورت العالم بوجودك 🌸", "الدنيا بنورك ✨"],
    "فرحتنا": ["فرحتنا بوجودك 🤍", "نورت فرحتنا 🌹", "فرحة بمعرفتك 🌸"]
}
FAQ_REPLIES = {
    "كيف حالك": ["الحمد لله، بخير وأنت؟ ❤️", "بخير، تسلم 🌹", "الحمد لله، كيفك أنت؟ 🌸"],
    "شو اخبارك": ["كل الخير، كيفك أنت؟ 🌹", "بخير الحمد لله ❤️", "الخبر كله خير 🌸"],
    "اخبارك": ["بخير، الحمد لله 🙏", "تمام، الحمد لله 🌹", "بخير، تسلم 🌸"],
    "شنو اخبارك": ["الحمد لله، كيفك أنت؟ ❤️", "كل تمام، كيفك؟ 🌹", "بخير الحمد لله 🌸"],
    "شخبارك": ["شخبارك أنت؟ 🌸", "بخير، تسلم 🌹", "الحمد لله، وأنت؟ 🙏"],
    "وينكم": ["هني موجودين، شنو المطلوب؟ 👋", "أنا هنا، تحت أمرك 🌹", "هني ننتظرك 🌸"],
    "وينك": ["أنا هنا، شنو تحتاج؟ 🤖", "هني موجود، تفضل 🌹", "تحت أمرك 🙏"],
    "شنو اسمك": ["أنا البوت، تحت أمرك 🙏", "اسمي البوت، تشرفنا 🤖", "أنا مساعد المجموعة 🌸"],
    "وش اسمك": ["أنا البوت، تشرفنا 🤖", "اسمي البوت، سعيد بمعرفتك 🌹", "أنا ريلاكس مانيجر 🙏"],
    "منو انت": ["أنا البوت، مساعد المجموعة 🛡️", "أنا مدير المجموعة 🤖", "أنا خادمكم 🙏"],
    "ايش اسمك": ["اسمي البوت، سعيد بمعرفتك 🌹", "أنا البوت، تحت أمرك 🙏", "ريلآكس مانيجر 🤖"],
    "كيفك انت": ["بخير الحمد لله 🌸", "تمام، كيفك أنت؟ 🌹", "الحمد لله، تسلم 🙏"],
    "وشلونك": ["الحمد لله، كيفك أنت؟ ❤️", "تمام، الحمد لله 🌹", "بخير، تسلم 🌸"],
    "كيف الأحوال": ["كل تمام، الحمد لله 🙏", "الأحوال بخير 🌹", "الحمد لله على كل حال 🌸"],
    "شو وضعك": ["تمام، الحمد لله 🌹", "بخير، تسلم 🙏", "الحمد لله، كيفك؟ 🌸"],
    "كيف الحال": ["الحال دوماً بخير 🌸", "بخير، الحمد لله 🌹", "الحال كله تمام 🙏"],
    "ايش اخبارك": ["الخبر كله خير ❤️", "كل الخير، تسلم 🌹", "أخبار طيبة 🌸"],
    "اخبار الدنيا": ["الدنيا بخير 🌹", "الحمد لله، الدنيا تمام 🌸", "كل شيء بخير 🙏"],
    "شو جديد": ["الجديد هو وجودك معنا ✨", "كل يوم جديد معكم 🌹", "الجديد فرحتنا بكم 🌸"],
    "ايش جديدك": ["جديدك يفرحنا 🌸", "أخبارك تسعدنا 🌹", "كل جديدك حلو ✨"],
    "كيف اليوم": ["اليوم جميل بحضورك 🌹", "يومك يبدأ بالخير 🌸", "اليوم ممتع معكم 🙏"],
    "شو تسوي": ["أساعد الناس، وهني بانتظارك 🤖", "أخدمكم وأدير المجموعة 🌹", "بخدمتكم 🙏"],
    "اين انت": ["أنا هنا، تحت أمرك 🙏", "هني موجود، تفضل 🌹", "أنا معكم دائماً 🌸"],
    "شنو تسوي": ["أخدم المجموعة وأديرها 📡", "أساعد في الإدارة 🌹", "أنا هنا لخدمتكم 🙏"],
    "ماذا تفعل": ["أساعد في إدارة المجموعة 🛡️", "أنشر وأحمي 🌹", "أخدم المجموعة 🙏"]
}
POSITIVE_REPLIES = {
    "شكراً": ["العفو، تحت أمرك دائماً ❤️", "العفو، أهلين 🙏", "الشكر لله 🌹"],
    "شكرا": ["العفو، أهلين 🙏", "العفو، نورت 🌸", "تسلم يا غالي 🌹"],
    "تسلم": ["تسلم يا غالي 🌸", "تسلم يدك 🌹", "الله يسلمك 🙏"],
    "تسلمي": ["تسلمي يا غالية 🌹", "تسلم يدك 🌸", "الله يسلمك 🙏"],
    "يسلمو": ["يسلم قلبك ❤️", "يسلمو على الذوق 🌹", "الله يسلمك 🌸"],
    "يعطيك العافية": ["يعافيك ربي ❤️", "الله يعافيك 🌹", "تسلم، يعافيك 🌸"],
    "يعطيك الف عافية": ["الله يعافيك 🌹", "يعافيك ربي 🙏", "تسلم يا غالي 🌸"],
    "ربي يوفقك": ["وإياك يا رب 🌸", "الله يوفق الجميع 🌹", "آمين يا رب 🙏"],
    "جزاك الله خير": ["وإياكم، الله يبارك فيك 🌹", "آمين، الله يجزاك خير 🌸", "الله يبارك فيك 🙏"],
    "الف شكر": ["ألف شكر لك 🙏", "الشكر لله 🌹", "تسلم على الذوق 🌸"],
    "مشكور": ["مشكور يا غالي 🌸", "العفو 🌹", "تسلم 🙏"],
    "مشكورة": ["مشكورة يا غالية 🌹", "العفو 🌸", "تسلمي 🙏"],
    "شكراً جزيلاً": ["الشكر لله ثم لك ❤️", "العفو، أهلين 🌹", "تسلم على كلامك 🌸"],
    "يعطيك الصحة": ["الله يعافيك 🙏", "يعطيك الصحة والعافية 🌹", "تسلم 🌸"],
    "ربي يعطيك العافية": ["يعافيك ربي 🌹", "الله يعافيك 🙏", "تسلم 🌸"],
    "ممتاز": ["شكراً لك 🌟", "أشكرك 🌹", "ممتاز أنت 🌸"],
    "رائع": ["يعجبني هذا 🌸", "روعة 🌹", "شكراً 🙏"],
    "جميل": ["روعة 🌹", "جميل جداً 🌸", "أشكرك 🙏"],
    "الله يبارك فيك": ["وفيك بارك الله 🙏", "آمين، وبارك فيك 🌹", "الله يبارك في الجميع 🌸"],
    "تقبل مروري": ["نورتنا بمرورك 🌸", "شكراً لمرورك 🌹", "تشرفنا بوجودك 🙏"]
}
RELIGIOUS_REPLIES = {
    "ما شاء الله": ["تبارك الرحمن 🤍", "ما شاء الله تبارك الله 🌹", "الله يبارك 🙏"],
    "ماشاءالله": ["تبارك الله 🌹", "الله يبارك فيك 🙏", "ما شاء الله 🌸"],
    "ما شاء الله تبارك الله": ["الله يبارك فيك 🙏", "تبارك الرحمن 🌹", "ما شاء الله 🌸"],
    "الحمد لله": ["الحمد لله دائماً وأبداً 🙏", "الحمد لله على كل حال 🌹", "الحمد لله رب العالمين 🌸"],
    "سبحان الله": ["سبحان الله وبحمده 🌹", "سبحان الله العظيم 🙏", "سبحان الله وبحمده 🌸"],
    "سبحان الله وبحمده": ["سبحان الله العظيم 🌸", "سبحان الله وبحمده 🙏", "سبحان الله 🌹"],
    "اللهم صل على محمد": ["اللهم صل وسلم وبارك على نبينا محمد 🌸", "اللهم صل على محمد وآل محمد 🌹", "اللهم صل على سيدنا محمد 🙏"],
    "صل على النبي": ["اللهم صل على محمد 🌹", "اللهم صل وسلم وبارك عليه 🌸", "اللهم صل على سيدنا محمد 🙏"],
    "استغفر الله": ["ربي اغفر لي ولوالديّ 🙏", "أستغفر الله العظيم 🌹", "اللهم اغفر لي 🌸"],
    "استغفر الله العظيم": ["الله أكبر، أستغفرك وأتوب إليك 🤍", "أستغفر الله العظيم الذي لا إله إلا هو 🌹", "ربي اغفر لي 🙏"],
    "لا اله الا الله": ["لا إله إلا الله محمد رسول الله 🙏", "لا إله إلا الله وحده لا شريك له 🌹", "شهادة الحق 🌸"],
    "الله اكبر": ["الله أكبر كبيراً 🌹", "الله أكبر، الحمد لله 🙏", "الله أكبر وأعلى 🌸"],
    "الحمدلله": ["الحمد لله رب العالمين 🙏", "الحمد لله على كل حال 🌹", "الحمد لله دائماً 🌸"],
    "ربي": ["لبيك يا رب 🌸", "ربي معي 🌹", "ربي كريم 🙏"],
    "اللهم": ["آمين يا رب العالمين 🤍", "اللهم استجب 🙏", "اللهم لك الحمد 🌹"],
    "سبحانه": ["سبحانه وتعالى 🙏", "سبحان الله العظيم 🌹", "سبحانه وتقدس 🌸"],
    "تعالى الله": ["الله أعلى وأعلم 🌹", "تعالى الله عما يشركون 🙏", "الله أعلى 🌸"],
    "بسم الله": ["بسم الله الرحمن الرحيم 🤍", "بسم الله توكلت على الله 🙏", "بسم الله ما شاء الله 🌹"],
    "توكلت على الله": ["حسبي الله ونعم الوكيل 🙏", "توكلت على الله الحي القيوم 🌹", "الله كافي 🌸"],
    "رب العالمين": ["رب السماوات والأرض 🌹", "رب العالمين أجمعين 🙏", "الله رب العالمين 🌸"],
    "الرحمن": ["بسم الله الرحمن الرحيم 🤍", "الرحمن الرحيم 🙏", "الله الرحمن 🌹"],
    "الرحيم": ["الرحيم بعباده 🙏", "الرحمن الرحيم 🌹", "الله الرحيم 🌸"],
    "الملك": ["الملك القدوس 🌹", "الملك الحق المبين 🙏", "الله الملك 🌸"],
    "القدوس": ["سبحان القدوس 🤍", "القدوس السلام 🙏", "سبحان الله القدوس 🌹"],
    "السلام": ["السلام عليكم ورحمة الله 🌸", "السلام عليكم 🙏", "السلام عليكم ورحمة الله وبركاته 🌹"]
}
JOKE_REPLIES = {
    "ضحك": ["😂😂", "ههههه 🤣", "ضحكتني 😂"],
    "نكتة": ["مرة واحد قال للبوت: وينك؟ قال البوت: هني 👻", "مرة واحد سأل البوت: أيش تسوي؟ قال: أنشر وأحمي 🤖", "نكتة جديدة: البوت يقول للمستخدم: أنت نورت 🌟"],
    "مزح": ["😅😅", "ههههه 🤣", "مزح مزح 😂"],
    "فكة": ["😂🤣", "هههههه 🤣", "فكة عسل 😂"],
    "وناسة": ["🤩🤩", "وناسة يا جماعة 🌸", "جو وناسة 😊"],
    "طقطقة": ["😂😂", "طق طق 🤣", "ههههه طقطقة حلوة 😂"],
    "خبلت": ["هههههه 🤣", "خبلتني 😂", "ههههه خبل 🤣"],
    "هههه": ["😂🤣", "هههههه 🤣", "ضحكتني 😂"],
    "ضحكتني": ["أنا مبسوط إنك ضحكت 😊", "😊😊", "أنا سعيد بإضحاكك 🌹"],
    "ههههههه": ["ههههههههه 🤣😂", "هههههه 🤣", "موتني ضحك 😂"],
    "ضحكك": ["يضحكني حضورك 😂", "ضحكك حلو 🌸", "أضحكني 😊"],
    "نكتة جديدة": ["مرة وحدة سألت البوت: أيش تسوي؟ قال: أنشر وأحمي 🤖", "نكتة: البوت مشغول بالنشر 😂", "مرة البوت قال للمستخدم: أنت الغالي 🌹"],
    "طشة": ["😂😂", "طشة عسل 😂", "ههههه 🤣"],
    "مموت": ["ههههه، ضحكتني 🤣", "موتني ضحك 😂", "ههههه 🤣"],
    "قهقهة": ["ههههههههه 😂", "قهقهة حلوة 🤣", "هههههه 😊"],
    "ضحك عالي": ["ههههههههههه 🤣", "ضحك عالي جداً 😂", "ههههههه 🤣"],
    "نكتة حلوة": ["أحلى نكتة هي وجودك معنا 😊", "نكتة حلوة منك 🌸", "أحلى نكتة 🌹"],
    "وناسة": ["جو وناسة 🤩", "وناسة يا جماعة 😊", "جو جميل 🌸"],
    "اخبارك": ["تضحك وتبسط 😂", "أخبارك طيبة 🌹", "كل الخير 🙏"],
    "طقطقة حلوة": ["هههه، طق طق 🤣", "طقطقة عسل 😂", "ههههه طقطقة حلوة 🌸"],
    "فكه": ["فكة عسل 😂", "فكة وناسة 🤣", "ههههه فكه 🌸"],
    "خوش واحد": ["ههههه 🤣", "خوش واحد أنت 🌹", "ضحكتني 😂"],
    "موتني": ["موتني ضحك 😂", "ههههه موتني 🤣", "ما رح أموت ضحك 😊"],
    "نكتة اليوم": ["اليوم يومك 😊", "نكتة اليوم من عندك 🌹", "اليوم يوم سعيد 🌸"],
    "حلوة": ["حلوتك 🤩", "حلوة منك 🌹", "أجمل نكتة 🌸"],
    "ايش هالضحك": ["ضحكك يفرحني 😂", "ضحك حلو 🌸", "أنا مبسوط 🌹"],
    "يهبل": ["ههههه 🤣", "يهبل ضحك 😂", "ههههه يهبل 🌸"],
    "يكسر": ["ههههههه 🤣😂", "يكسر القلب 😂", "ههههه يكسّر 🌹"],
    "مزة": ["ههههه 🤣", "مزة منك 🌸", "ههههه مزة 😂"],
    "جو": ["جو حلو 😊", "جو رائع 🌹", "جو ممتع 🌸"]
}
MOTIVATIONAL_REPLIES = {
    "تعبت": ["إرتاح شوي، تستاهل الراحة 😊", "خذ قسط من الراحة 🌸", "تستاهل كل خير 🙏"],
    "زعلان": ["لا تزعل، كل شيء بيصير خير ❤️", "الدنيا جميلة، ابتسم 🌹", "كل شيء سيكون بخير 🌸"],
    "فرحان": ["الله يفرح قلبك 😊", "فرحتنا بفرحك 🌹", "تبقى مبسوط دائماً 🌸"],
    "ناجح": ["ألف مبروك، تستاهل كل خير 🎉", "مبروك النجاح 🌹", "أنت ناجح دائماً 🙏"],
    "فائز": ["مبروك الفوز، أنت تستاهل 🏆", "ألف مبروك 🌹", "أنت فائز دائماً 🌸"],
    "متعب": ["خذ قسط من الراحة 🌸", "إرتاح شوي، راح ترتاح 🌹", "تستاهل الراحة 🙏"],
    "محبط": ["لا تحبط، النجاح قريب 💪", "الدنيا بخير، ابتسم 🌹", "أنت أقوى من ذلك 🌸"],
    "متفائل": ["تفاؤلك خير 🌹", "التفاؤل طريق النجاح 🌸", "أنت متفائل دائماً 🙏"],
    "حزين": ["كل شيء سيكون بخير ❤️", "لا تحزن، الله معك 🌹", "الحياة جميلة 🌸"],
    "مبسوط": ["أجمل شعور هو السعادة 😊", "سعادتك تسعدني 🌹", "تبقى مبسوط دائماً 🌸"],
    "متحمس": ["حماسك جميل 🔥", "استمر بالحماس 🌹", "أنت متحمس دائماً 🙏"],
    "مبدع": ["إبداعك رائع 🌟", "أنت مبدع دائماً 🌹", "إبداعك يفرحنا 🌸"],
    "متطور": ["أنت تتطور باستمرار 🚀", "التطور طريق النجاح 🌹", "أنت في تطور مستمر 🙏"],
    "طموح": ["طموحك يوصلك للنجاح 💫", "الطموح طريق القمة 🌹", "أنت طموح دائماً 🌸"],
    "ناجح": ["أنت ناجح دائماً 🎉", "النجاح حليفك 🌹", "مبروك النجاح 🙏"]
}
SOCIAL_REPLIES = {
    "كيفك": ["بخير الحمد لله، وأنت؟ 🌹", "بخير، تسلم ❤️", "الحمد لله، كيفك أنت؟ 🌸"],
    "كيفك انت": ["بخير، تسلم ❤️", "بخير، الحمد لله 🌹", "أنا بخير، شكراً 🙏"],
    "اخبار العائلة": ["كلهم بخير، الحمد لله 🙏", "العائلة بخير 🌹", "الحمد لله على كل حال 🌸"],
    "والديك": ["بخير، الحمد لله 🌸", "والديك في أفضل حال 🌹", "الله يحفظهم 🙏"],
    "الاهل": ["الحمد لله، كلهم بخير 🌹", "الأهل في خير 🌸", "الله يحفظ العائلة 🙏"],
    "الصحة": ["الحمد لله على كل حال 🙏", "الصحة نعمة 🌹", "الحمد لله، بخير 🌸"],
    "العمل": ["الحمد لله، أموره طيبة 🌸", "العمل بخير 🌹", "الحمد لله على كل حال 🙏"],
    "الدراسة": ["بالتوفيق إن شاء الله 📚", "الله يوفقك 🌹", "النجاح حليفك 🌸"],
    "الجامعة": ["الله يوفقك يارب 🌹", "الجامعة تنتظر نجاحك 🌸", "بالتوفيق 🙏"],
    "المدرسة": ["بالتوفيق والنجاح 🌸", "المدرسة تنتظرك 🌹", "الله يوفقك 🙏"],
    "البيت": ["الحمد لله، بيتنا بخير 🙏", "البيت جميل 🌹", "الحمد لله 🌸"],
    "السفر": ["الله يسهل لك 🌹", "سفر مبارك 🌸", "الله يحفظك 🙏"],
    "السيارة": ["سلامتك يا رب 🚗", "السيارة بخير 🌹", "الحمد لله 🌸"],
    "السكن": ["الحمد لله، مستقرين 🌸", "السكن بخير 🌹", "الحمد لله 🙏"],
    "المال": ["الحمد لله، رزق حلال 🙏", "المال يزيد بالبركة 🌹", "الحمد لله 🌸"],
    "الزواج": ["الله يبارك لك 🌹", "ألف مبروك 🌸", "الله يتمم بخير 🙏"],
    "العزوبية": ["الله يرزقك الزوجة الصالحة 🙏", "الزواج نصيب 🌹", "الله يكتب الخير 🌸"],
    "الأولاد": ["الله يبارك لك فيهم 🌸", "الأولاد زينة الحياة 🌹", "الله يحفظهم 🙏"],
    "البنات": ["الله يحفظهم لك 🌹", "البنات نعمة 🌸", "الله يرعاهم 🙏"],
    "العائلة": ["الله يجمع شملكم 🤍", "العائلة أغلى ما نملك 🌹", "الله يحمي العائلة 🌸"]
}
ADMIN_REPLIES = {
    "ممنوع": ["تم التنبيه، يرجى احترام قوانين المجموعة 🚫", "ممنوع، يرجى الالتزام 🌹", "تنبيه: ممنوع 🙏"],
    "انتبه": ["رجاءً انتبه للقوانين ⚠️", "انتبه يا غالي 🌹", "تنبيه مهم 🌸"],
    "قوانين": ["قوانين المجموعة موجودة في الوصف 📋", "اقرأ القوانين في الوصف 🌹", "القوانين واضحة 🙏"],
    "مخالفة": ["تنبيه: هذا مخالف للقوانين 🚫", "مخالفة، يرجى الانتباه 🌹", "تنبيه مهم 🌸"],
    "تحذير": ["تحذير أول، يرجى الالتزام بالقوانين ⚠️", "تحذير، انتبه 🌹", "هذا تحذير 🙏"],
    "طرد": ["سيتم تطبيق العقوبات 🚫", "طرد، انتبه 🌹", "عقوبات رادعة 🌸"],
    "حظر": ["تم حظر المخالف 🚫", "حظر، انتبه 🌹", "تم تطبيق الحظر 🙏"],
    "كتم": ["تم كتم المخالف 🔇", "كتم لمدة محددة 🌹", "تم تطبيق الكتم 🌸"],
    "سجل": ["تم تسجيل المخالفة 📝", "سجل المخالفات 🌹", "تم التوثيق 🙏"],
    "تنبيه": ["تنبيه هام يرجى قراءة القوانين 📋", "تنبيه للمخالفين 🌹", "انتبه للقوانين 🌸"]
}
REQUEST_REPLIES = {
    "بليز": ["حاضر، بس أرسل طلبك بالتفصيل 📝", "تفضل، أنا هنا 🌹", "أرسل طلبك 🙏"],
    "من فضلك": ["تفضل، أنا هنا للمساعدة 🤖", "تفضل، بكامل الخدمة 🌹", "أنا في خدمتك 🌸"],
    "تكرم": ["أمرك يا غالي 🌹", "تفضل، أنا هنا 🙏", "بكامل الخدمة 🌸"],
    "لو سمحت": ["تفضل، أنا جاهز 🙏", "تفضل، بكامل الخدمة 🌹", "أنا في انتظارك 🌸"],
    "عندي طلب": ["أرسل طلبك وسأساعدك 💡", "تفضل بطلبك 🌹", "أنا في الخدمة 🙏"],
    "طلب": ["تفضل بطلبك 📝", "أرسل طلبك 🌹", "أنا هنا لمساعدتك 🌸"],
    "سؤال": ["اسأل، وأنا هنا للإجابة ❓", "تفضل بسؤالك 🌹", "أنا هنا للإجابة 🙏"],
    "استفسار": ["تفضل بالاستفسار 📋", "أنا هنا للإجابة 🌹", "تفضل 🌸"],
    "مساعدة": ["كيف أقدر أساعدك؟ 🤖", "أنا هنا لمساعدتك 🌹", "تفضل، أنا في الخدمة 🙏"],
    "دعم": ["أنا هنا لدعمك 💪", "الدعم متوفر 🌹", "نحن معك 🙏"],
    "شكوى": ["اشرح شكوتك وسنحلها 📞", "تفضل بشكوتك 🌹", "نحن هنا لحلها 🌸"],
    "مشكلة": ["اشرح مشكلتك، سأحاول مساعدتك 💡", "تفضل بمشكلتك 🌹", "نحن هنا لحلها 🙏"],
    "اقتراح": ["تفضل باقتراحك، نرحب بكل فكرة 💡", "اقتراحك يهمنا 🌹", "تفضل بفكرتك 🌸"],
    "فكرة": ["شاركنا فكرتك الجميلة 🌟", "فكرتك تهمنا 🌹", "تفضل بفكرتك 🙏"],
    "رأي": ["نرحب برأيك القيم 📝", "رأيك يهمنا 🌹", "تفضل برأيك 🌸"]
}
ABOUT_BOT_REPLIES = {
    "مين انت": ["أنا البوت، مساعد لإدارة المجموعات 🤖", "أنا ريلاكس مانيجر 🌹", "أنا خادم المجموعة 🙏"],
    "ايش تسوي": ["أساعد في إدارة المجموعات، النشر، الأمان، والكثير 📋", "أدير القنوات والمجموعات 🌹", "أنا مساعد شامل 🌸"],
    "مهمتك": ["تنظيم المجموعات وحمايتها من المزعجين 🛡️", "الأمان أولاً 🌹", "حماية المجموعة 🙏"],
    "شغلك": ["أنشر المنشورات، أحافظ على الأمان، وأدير القنوات 📡", "إدارة متكاملة 🌹", "خدمة المجموعة 🌸"],
    "ايش تقدر": ["أقدر أساعدك في إدارة القناة والمجموعة 💪", "كل شيء تقريباً 🌹", "أنا متعدد المهام 🙏"],
    "مهاراتك": ["النشر التلقائي، الأمان، الردود، والإحصائيات 📊", "مهارات متعددة 🌹", "أنا شامل 🌸"],
    "شو اختصاصك": ["إدارة القنوات والمجموعات بكل احترافية 🎯", "اختصاصي الإدارة 🌹", "الخدمة المتكاملة 🙏"],
    "ليش انت هنا": ["لأخدمكم وأساعد في تنظيم المجموعة 🌸", "أنا هنا لخدمتكم 🌹", "لأدير المجموعة 🙏"],
    "عرف نفسك": ["أنا بوت مساعد، تحت أمركم 🙏", "أنا ريلاكس مانيجر 🌹", "أنا خادمكم 🌸"],
    "شنو فائدتك": ["أسهل عليك إدارة القناة والمجموعة 🚀", "فائدتي في الخدمة 🌹", "أنا هنا لمساعدتك 🙏"]
}
EXTRA_REPLIES = {
    "تمام": ["تمام يا غالي 🌸", "تمام، تسلم 🌹", "أوكي 🙏"],
    "اوك": ["أوكي، تحت أمرك 🙏", "أوكي، تمام 🌹", "ممتاز 🌸"],
    "حاضر": ["حاضر، أنا جاهز 💪", "حاضر، تفضل 🌹", "تحت أمرك 🙏"],
    "ان شاء الله": ["إن شاء الله خير 🌹", "إن شاء الله 🌸", "بإذن الله 🙏"],
    "باذن الله": ["بإذن الله 🙏", "بإذن الله خير 🌹", "إن شاء الله 🌸"],
    "مع السلامة": ["مع السلامة، تشرفنا بك 🌸", "مع السلامة 🌹", "أهلاً وسهلاً بك 🙏"],
    "باي": ["باي، نورت 🌹", "مع السلامة 🌸", "تشرفنا بك 🙏"],
    "سلام": ["سلام، الله يحفظك 🙏", "سلام عليكم 🌹", "مع السلامة 🌸"],
    "ياعيني": ["ياعيني عليك 🌹", "ياعيني، أنت الغالي 🌸", "ياعيني يا حلو 🙏"],
    "ياحلو": ["حلوك الله 🌸", "أنت الحلو 🌹", "حلو كلامك 🙏"]
}

ALL_REPLIES = {}
ALL_REPLIES.update(WELCOME_REPLIES)
ALL_REPLIES.update(FAQ_REPLIES)
ALL_REPLIES.update(POSITIVE_REPLIES)
ALL_REPLIES.update(RELIGIOUS_REPLIES)
ALL_REPLIES.update(JOKE_REPLIES)
ALL_REPLIES.update(MOTIVATIONAL_REPLIES)
ALL_REPLIES.update(SOCIAL_REPLIES)
ALL_REPLIES.update(ADMIN_REPLIES)
ALL_REPLIES.update(REQUEST_REPLIES)
ALL_REPLIES.update(ABOUT_BOT_REPLIES)
ALL_REPLIES.update(EXTRA_REPLIES)

# ===================================================================
# 16. نظام قاعدة البيانات
# ===================================================================
class DatabasePool:
    def __init__(self, max_connections: int = 10):
        self._pool = None
        self._max_connections = max_connections
        self._lock = asyncio.Lock()

    async def initialize(self):
        async with self._lock:
            if self._pool is None:
                self._pool = await aiosqlite.connect(str(DB_PATH), timeout=DB_TIMEOUT)
                await self._pool.execute("PRAGMA journal_mode=WAL")
                await self._pool.execute("PRAGMA synchronous=NORMAL")
                await self._pool.execute("PRAGMA foreign_keys=ON")
                await self._pool.execute("PRAGMA cache_size=-64000")
                await self._pool.execute("PRAGMA temp_store=MEMORY")
                await self._pool.execute("PRAGMA wal_autocheckpoint=1000")
                await self._pool.execute("PRAGMA optimize")
                await self._pool.execute("PRAGMA max_page_count=1000000")
                await self._pool.execute("PRAGMA secure_delete=ON")
                self._pool.row_factory = aiosqlite.Row

    async def get_connection(self):
        if self._pool is None:
            await self.initialize()
        return self._pool

    async def execute(self, query: str, params: tuple = None):
        conn = await self.get_connection()
        async with conn.execute(query, params or ()) as cursor:
            return await cursor.fetchall()

    async def execute_many(self, queries: List[Tuple[str, tuple]]):
        conn = await self.get_connection()
        async with conn:
            for query, params in queries:
                await conn.execute(query, params)
            await conn.commit()

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

db_pool = DatabasePool(max_connections=MAX_CONNECTIONS)

async def execute_db(func: Callable):
    conn = await db_pool.get_connection()
    try:
        return await func(conn)
    except Exception as e:
        logger.error(f"خطأ في قاعدة البيانات: {e}")
        raise
    finally:
        pass

# ===================================================================
# 17. دوال المستخدمين
# ===================================================================
async def db_register_user(user_id: int) -> bool:
    async def _register(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if await cur.fetchone():
            return False
        await conn.execute(
            """INSERT INTO users 
               (user_id, auto_publish, banned, trial_used, auto_reply_enabled, auto_recycle) 
               VALUES (?, 1, 0, 0, 1, 1)""",
            (user_id,)
        )
        await conn.commit()
        return True
    return await execute_db(_register)

async def db_get_all_users():
    async def _get(conn):
        cur = await conn.execute("SELECT user_id, banned FROM users ORDER BY user_id")
        return await cur.fetchall()
    return await execute_db(_get)

async def db_update_user_cache(user_id: int, username: str, first_name: str):
    async def _update(conn):
        await conn.execute(
            """INSERT OR REPLACE INTO users_cache 
               (user_id, username, first_name, last_updated) 
               VALUES (?, ?, ?, ?)""",
            (user_id, username or "", first_name or "", utc_now_iso())
        )
        await conn.commit()
    return await execute_db(_update)

async def db_is_banned(user_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_check)

async def db_set_ban(user_id: int, banned: bool):
    async def _set(conn):
        await conn.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, user_id))
        await conn.commit()
    return await execute_db(_set)

async def db_has_used_trial(user_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_check)

async def db_activate_trial(user_id: int) -> int:
    async def _activate(conn):
        cur = await conn.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0] == 1:
            return 0
        end_date = (utc_now() + timedelta(days=30)).isoformat()
        await conn.execute("UPDATE users SET trial_used=1, subscription_end=? WHERE user_id=?", (end_date, user_id))
        await conn.commit()
        return 30
    return await execute_db(_activate)

async def db_activate_subscription(user_id: int, days: int):
    async def _activate(conn):
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try:
                current_end = datetime.fromisoformat(row[0])
                if current_end > utc_now():
                    new_end = current_end + timedelta(days=days)
                else:
                    new_end = utc_now() + timedelta(days=days)
            except:
                new_end = utc_now() + timedelta(days=days)
        else:
            new_end = utc_now() + timedelta(days=days)
        await conn.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (new_end.isoformat(), user_id))
        await conn.commit()
    return await execute_db(_activate)

async def db_has_active_subscription(user_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try:
                end_date = datetime.fromisoformat(row[0])
                return end_date > utc_now()
            except:
                return False
        return False
    return await execute_db(_check)

async def db_get_subscription_days_left(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try:
                end_date = datetime.fromisoformat(row[0])
                days = (end_date - utc_now()).days
                return max(0, days)
            except:
                return 0
        return 0
    return await execute_db(_get)

async def db_auto_status(user_id: int) -> bool:
    async def _get(conn):
        cur = await conn.execute("SELECT auto_publish FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_get)

async def db_set_auto(user_id: int, enabled: bool):
    async def _set(conn):
        await conn.execute("UPDATE users SET auto_publish=? WHERE user_id=?", (1 if enabled else 0, user_id))
        await conn.commit()
    return await execute_db(_set)

async def db_get_auto_recycle(user_id: int) -> bool:
    async def _get(conn):
        cur = await conn.execute("SELECT auto_recycle FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_get)

async def db_set_auto_recycle(user_id: int, enabled: bool):
    async def _set(conn):
        await conn.execute("UPDATE users SET auto_recycle=? WHERE user_id=?", (1 if enabled else 0, user_id))
        await conn.commit()
    return await execute_db(_set)

async def db_get_user_auto_reply_status(user_id: int) -> bool:
    async def _get(conn):
        cur = await conn.execute("SELECT auto_reply_enabled FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_get)

async def db_set_user_auto_reply_status(user_id: int, enabled: bool):
    async def _set(conn):
        await conn.execute("UPDATE users SET auto_reply_enabled=? WHERE user_id=?", (1 if enabled else 0, user_id))
        await conn.commit()
    return await execute_db(_set)

async def db_get_active_channel(user_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT active_channel FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0] is not None:
            cur2 = await conn.execute("SELECT banned FROM user_channels WHERE id=?", (row[0],))
            row2 = await cur2.fetchone()
            if row2 and row2[0] == 0:
                return row[0]
        cur = await conn.execute("SELECT id FROM user_channels WHERE user_id=? AND banned=0 ORDER BY id LIMIT 1", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_set_active_channel(user_id: int, channel_db_id: int):
    async def _set(conn):
        await conn.execute("UPDATE users SET active_channel=? WHERE user_id=?", (channel_db_id, user_id))
        await conn.commit()
    return await execute_db(_set)

async def db_get_user_channels_count(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM user_channels WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_get_user_unpublished_posts(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute(
            """SELECT COUNT(*) FROM posts p 
               JOIN user_channels uc ON p.channel_db_id=uc.id 
               WHERE uc.user_id=? AND p.published=0 AND uc.banned=0""",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_get_user_total_posts(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute(
            """SELECT COUNT(*) FROM posts p 
               JOIN user_channels uc ON p.channel_db_id=uc.id 
               WHERE uc.user_id=? AND uc.banned=0""",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)
# ===================================================================
# 18. دوال القنوات
# ===================================================================
async def db_add_channel(user_id: int, channel_id: str, channel_name: str) -> int:
    """إضافة قناة للمستخدم"""
    async def _add(conn):
        # التحقق من عدم التكرار
        cur = await conn.execute(
            "SELECT id FROM user_channels WHERE user_id=? AND channel_id=?", 
            (user_id, channel_id)
        )
        if await cur.fetchone():
            return None

        # إضافة القناة
        cur = await conn.execute(
            """INSERT INTO user_channels 
               (user_id, channel_id, channel_name, created_at) 
               VALUES (?, ?, ?, ?) RETURNING id""",
            (user_id, channel_id, channel_name, utc_now_iso())
        )
        row = await cur.fetchone()
        await conn.commit()
        return row[0] if row else None
    return await execute_db(_add)

async def db_get_channels(user_id: int):

    async def _get(conn):
        try:
            cur = await conn.execute(
                "SELECT id, channel_id, channel_name, banned FROM user_channels WHERE user_id=? ORDER BY id",
                (user_id,)
            )
            rows = await cur.fetchall()
            safe_rows = []
            for row in rows:
                try:
                    if len(row) >= 4:
                        ch_id = row[0] if row[0] is not None else 0
                        ch_tele_id = row[1] if row[1] is not None else "unknown"
                        ch_name = row[2] if row[2] is not None else ch_tele_id
                        banned = row[3] if row[3] is not None else 0
                        safe_rows.append((ch_id, ch_tele_id, ch_name, banned))
                except:
                    continue
            return safe_rows
        except Exception as e:
            logger.error(f"خطأ في جلب قنوات المستخدم {user_id}: {e}")
            return []
    return await execute_db(_get)

async def db_get_channel_info(channel_db_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT channel_id, channel_name FROM user_channels WHERE id=?", (channel_db_id,))
        return await cur.fetchone()
    return await execute_db(_get)

async def db_delete_channel_by_id(user_id: int, channel_db_id: int) -> bool:
    async def _delete(conn):
        # جلب channel_id قبل الحذف لحذفه من bot_channels أيضاً
        cur = await conn.execute("SELECT channel_id FROM user_channels WHERE id=? AND user_id=?", (channel_db_id, user_id))
        row = await cur.fetchone()
        if row:
            channel_tele_id = row[0]
            await conn.execute("DELETE FROM bot_channels WHERE channel_id=?", (channel_tele_id,))
        await conn.execute("DELETE FROM user_channels WHERE id=? AND user_id=?", (channel_db_id, user_id))
        await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (channel_db_id,))
        await conn.execute("DELETE FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        await conn.execute("DELETE FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
        return True
    return await execute_db(_delete)

async def db_all_users_channels(only_banned: bool = False, limit: int = 500):
    async def _get(conn):
        if only_banned:
            cur = await conn.execute("SELECT user_id, id, channel_id, channel_name, banned FROM user_channels WHERE banned=1 LIMIT ?", (limit,))
        else:
            cur = await conn.execute("SELECT user_id, id, channel_id, channel_name, banned FROM user_channels LIMIT ?", (limit,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_register_channel(channel_id: int, channel_name: str, added_by: int):
    async def _register(conn):
        cur = await conn.execute("SELECT channel_id FROM bot_channels WHERE channel_id=?", (channel_id,))
        if await cur.fetchone():
            await conn.execute("UPDATE bot_channels SET channel_name=?, added_by=? WHERE channel_id=?", (channel_name, added_by, channel_id))
            await conn.commit()
            return False
        await conn.execute("INSERT INTO bot_channels (channel_id, channel_name, added_by, added_at) VALUES (?, ?, ?, ?)", (channel_id, channel_name, added_by, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_register)

async def db_get_all_bot_channels(only_banned: bool = False):
    async def _get(conn):
        if only_banned:
            cur = await conn.execute("SELECT channel_id, channel_name, added_by, added_at, banned FROM bot_channels WHERE banned=1 ORDER BY added_at DESC")
        else:
            cur = await conn.execute("SELECT channel_id, channel_name, added_by, added_at, banned FROM bot_channels ORDER BY added_at DESC")
        return await cur.fetchall()
    return await execute_db(_get)

async def db_toggle_channel_ban(channel_db_id: int):
    async def _toggle(conn):
        cur = await conn.execute("SELECT banned FROM user_channels WHERE id=?", (channel_db_id,))
        row = await cur.fetchone()
        if row:
            new_status = 1 if row[0] == 0 else 0
            await conn.execute("UPDATE user_channels SET banned=? WHERE id=?", (new_status, channel_db_id))
            await conn.commit()
            return new_status == 1
        return False
    return await execute_db(_toggle)

async def db_toggle_bot_channel_ban(channel_id: int):
    async def _toggle(conn):
        cur = await conn.execute("SELECT banned FROM bot_channels WHERE channel_id=?", (channel_id,))
        row = await cur.fetchone()
        if row:
            new_status = 1 if row[0] == 0 else 0
            await conn.execute("UPDATE bot_channels SET banned=? WHERE channel_id=?", (new_status, channel_id))
            await conn.commit()
            return new_status == 1
        return False
    return await execute_db(_toggle)

# ===================================================================
# 19. دوال المنشورات
# ===================================================================
async def db_save_posts(channel_db_id: int, posts: list) -> int:
    async def _save(conn):
        values = []
        for text_content, media_type, media_file_id in posts:
            values.append((channel_db_id, sanitize_text(text_content), media_type, media_file_id, utc_now_iso()))
        await conn.executemany(
            """INSERT INTO posts 
               (channel_db_id, text, media_type, media_file_id, created_at) 
               VALUES (?, ?, ?, ?, ?)""",
            values
        )
        await conn.commit()
        return len(values)
    return await execute_db(_save)

async def db_get_next_post(channel_db_id: int):
    async def _get(conn):
        cur = await conn.execute(
            """SELECT id, text, media_type, media_file_id 
               FROM posts 
               WHERE channel_db_id=? AND published=0 AND (fail_count IS NULL OR fail_count < 3) 
               ORDER BY id LIMIT 1""",
            (channel_db_id,)
        )
        row = await cur.fetchone()
        if row:
            return {'id': row[0], 'text': row[1], 'media_type': row[2], 'media_file_id': row[3]}
        return None
    return await execute_db(_get)

async def db_mark_published(post_id: int):
    async def _mark(conn):
        await conn.execute("UPDATE posts SET published=1 WHERE id=?", (post_id,))
        await conn.commit()
    return await execute_db(_mark)

async def db_increment_fail_count(post_id: int):
    async def _inc(conn):
        await conn.execute("UPDATE posts SET fail_count = fail_count + 1 WHERE id=?", (post_id,))
        await conn.commit()
    return await execute_db(_inc)

async def db_get_posts_count(channel_db_id: int) -> int:
    async def _count(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_count)

async def db_get_published_count(channel_db_id: int) -> int:
    async def _count(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=1", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_count)

async def db_reset_all_posts_to_unpublished(channel_db_id: int) -> int:
    async def _reset(conn):
        # ترتيب عشوائي لتجنب تكرار نفس التسلسل
        await conn.execute("UPDATE posts SET published=0, fail_count=0 WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_reset)

async def db_reset_posts_to_unpublished(channel_db_id: int, user_id: int = None):
    async def _reset(conn):
        await conn.execute("UPDATE posts SET published=0, fail_count=0 WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
    return await execute_db(_reset)

async def db_get_user_posts_for_channel(channel_db_id: int, limit=15):
    async def _get(conn):
        cur = await conn.execute(
            "SELECT id, text, media_type FROM posts WHERE channel_db_id=? AND published=0 ORDER BY id LIMIT ?",
            (channel_db_id, limit)
        )
        return await cur.fetchall()
    return await execute_db(_get)

async def db_delete_single_post(post_id: int, user_id: int, channel_db_id: int) -> bool:
    async def _delete(conn):
        cur = await conn.execute("SELECT 1 FROM user_channels WHERE id=? AND user_id=? AND banned=0", (channel_db_id, user_id))
        if not await cur.fetchone():
            return False
        cur = await conn.execute("SELECT 1 FROM posts WHERE id=? AND channel_db_id=?", (post_id, channel_db_id))
        if not await cur.fetchone():
            return False
        await conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
        await conn.commit()
        return True
    return await execute_db(_delete)

async def db_unpublished_count(channel_db_id: int) -> int:
    async def _count(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=0", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_count)

async def db_update_post_views(post_id: int, views_count: int = None):
    async def _update_views(conn):
        if views_count is not None:
            await conn.execute("UPDATE posts SET views_count = ?, last_view_time = ? WHERE id = ?", (views_count, utc_now_iso(), post_id))
        else:
            await conn.execute("UPDATE posts SET views_count = views_count + 1, last_view_time = ? WHERE id = ?", (utc_now_iso(), post_id))
        await conn.commit()
    return await execute_db(_update_views)

# ===================================================================
# 20. دوال الجدولة والنشر التلقائي
# ===================================================================
async def db_save_schedule(channel_db_id: int, schedule_type: str, 
                           interval_minutes: int = None, interval_hours: int = None,
                           interval_days: int = None, days_of_week: str = None,
                           specific_dates: str = None, publish_time: str = None,
                           cron_expression: str = None):
    async def _save(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO schedule 
            (channel_db_id, schedule_type, interval_minutes, interval_hours, interval_days, 
             days_of_week, specific_dates, publish_time, cron_expression, next_publish_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """, (channel_db_id, schedule_type, interval_minutes, interval_hours, interval_days,
              days_of_week or '[]', specific_dates or '[]', publish_time or '00:00', cron_expression))
        await conn.commit()
    return await execute_db(_save)

async def db_get_schedule(channel_db_id: int):
    async def _get(conn):
        cur = await conn.execute("""
            SELECT schedule_type, interval_minutes, interval_hours, interval_days, 
                   days_of_week, specific_dates, publish_time, cron_expression, next_publish_date 
            FROM schedule WHERE channel_db_id=?
        """, (channel_db_id,))
        row = await cur.fetchone()
        if row:
            return {
                'type': row[0] or 'interval_minutes',
                'interval_minutes': row[1] or 12,
                'interval_hours': row[2] or 0,
                'interval_days': row[3] or 0,
                'days_of_week': row[4] or '[]',
                'specific_dates': row[5] or '[]',
                'publish_time': row[6] or '00:00',
                'cron_expression': row[7],
                'next_publish_date': row[8]
            }
        return {'type': 'interval_minutes', 'interval_minutes': 12, 'interval_hours': 0,
                'interval_days': 0, 'days_of_week': '[]', 'specific_dates': '[]',
                'publish_time': '00:00', 'cron_expression': None, 'next_publish_date': None}
    return await execute_db(_get)

async def db_set_next_publish_date(channel_db_id: int, next_date: datetime):
    async def _set(conn):
        if next_date:
            await conn.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?", (next_date.isoformat(), channel_db_id))
        else:
            await conn.execute("UPDATE schedule SET next_publish_date=NULL WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
    return await execute_db(_set)

async def db_set_last_publish(channel_db_id: int, publish_time: datetime):
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO last_publish (channel_db_id, last_publish_time) VALUES (?, ?)", (channel_db_id, publish_time.isoformat()))
        await conn.commit()
    return await execute_db(_set)

async def db_update_next_publish_date(channel_db_id: int):
    async def _update(conn):
        schedule = await db_get_schedule(channel_db_id)
        last_publish_cur = await conn.execute("SELECT last_publish_time FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
        last_row = await last_publish_cur.fetchone()
        # إذا كانت الجدولة من نوع days أو dates، نبدأ من الوقت الحالي لتجنب التواريخ الماضية
        if schedule['type'] in ['days', 'dates']:
            last_time = utc_now()
        else:
            last_time = datetime.fromisoformat(last_row[0]) if last_row else utc_now()
        schedule_type = schedule['type']
        publish_time_str = schedule.get('publish_time', '00:00')
        if ':' not in publish_time_str:
            publish_time_str = '00:00'
        try:
            hour, minute = map(int, publish_time_str.split(':'))
        except:
            hour, minute = 0, 0
        next_date = None
        now = utc_now()
        if schedule_type == 'interval_minutes':
            minutes = schedule.get('interval_minutes', 12)
            next_date = last_time + timedelta(minutes=minutes)
        elif schedule_type == 'interval_hours':
            hours = schedule.get('interval_hours', 1)
            next_date = last_time + timedelta(hours=hours)
        elif schedule_type == 'interval_days':
            days = schedule.get('interval_days', 1)
            next_date = last_time + timedelta(days=days)
        elif schedule_type == 'days':
            days_of_week = parse_days_of_week_safe(schedule.get('days_of_week', '[]'))
            if days_of_week:
                target_date = last_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
                found = False
                for i in range(1, 8):
                    check_date = target_date + timedelta(days=i)
                    if check_date.weekday() in days_of_week:
                        next_date = check_date
                        found = True
                        break
                if not found:
                    next_date = target_date + timedelta(days=7)
                    while next_date.weekday() not in days_of_week:
                        next_date += timedelta(days=1)
            else:
                next_date = last_time + timedelta(days=1)
        elif schedule_type == 'dates':
            specific_dates = parse_dates_safe(schedule.get('specific_dates', '[]'))
            if specific_dates:
                target_date = last_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
                for date_str in sorted(specific_dates):
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d').replace(hour=hour, minute=minute, second=0, microsecond=0)
                        if date_obj > last_time:
                            next_date = date_obj
                            break
                    except:
                        continue
                if not next_date:
                    try:
                        next_date = datetime.strptime(specific_dates[0], '%Y-%m-%d').replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=365)
                    except:
                        next_date = utc_now() + timedelta(days=1)
            else:
                next_date = utc_now() + timedelta(days=1)
        elif schedule_type == 'cron':
            cron_expr = schedule.get('cron_expression', '0 0 * * *')
            try:
                parts = cron_expr.split()
                if len(parts) >= 5:
                    next_date = last_time + timedelta(days=1)
                    for i in range(1, 31):
                        check_date = last_time + timedelta(days=i)
                        if check_date.hour == hour and check_date.minute == minute:
                            if parts[2] == '*' or check_date.day == int(parts[2]):
                                if parts[3] == '*' or check_date.month == int(parts[3]):
                                    if parts[4] == '*' or check_date.weekday() == int(parts[4]):
                                        next_date = check_date
                                        break
            except:
                next_date = utc_now() + timedelta(days=1)
        else:
            next_date = utc_now() + timedelta(minutes=schedule.get('interval_minutes', 12))
        if next_date:
            if next_date <= now:
                if schedule_type == 'interval_minutes':
                    minutes = schedule.get('interval_minutes', 12)
                    while next_date <= now:
                        next_date += timedelta(minutes=minutes)
                elif schedule_type == 'interval_hours':
                    hours = schedule.get('interval_hours', 1)
                    while next_date <= now:
                        next_date += timedelta(hours=hours)
                elif schedule_type == 'interval_days':
                    days = schedule.get('interval_days', 1)
                    while next_date <= now:
                        next_date += timedelta(days=days)
                else:
                    while next_date <= now:
                        next_date += timedelta(days=1)
            await conn.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?", (next_date.isoformat(), channel_db_id))
            await conn.commit()
    return await execute_db(_update)

async def db_set_publish_time(channel_db_id: int, time_str: str):
    async def _set(conn):
        await conn.execute("UPDATE schedule SET publish_time=? WHERE channel_db_id=?", (time_str, channel_db_id))
        await conn.commit()
    return await execute_db(_set)

async def db_add_scheduled_post(chat_id: int, text: str, publish_time: datetime):
    async def _add(conn):
        await conn.execute("INSERT INTO scheduled_posts (chat_id, text, publish_time, fail_count) VALUES (?, ?, ?, 0)", (chat_id, sanitize_text(text), publish_time.isoformat()))
        await conn.commit()
    return await execute_db(_add)

async def db_get_due_scheduled_posts(now: datetime, limit: int = 50):
    async def _get(conn):
        cur = await conn.execute("SELECT id, chat_id, text, fail_count FROM scheduled_posts WHERE publish_time <= ? LIMIT ?", (now.isoformat(), limit))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_update_scheduled_post_fail(post_id: int, fail_count: int):
    async def _update(conn):
        await conn.execute("UPDATE scheduled_posts SET fail_count = ? WHERE id = ?", (fail_count, post_id))
        await conn.commit()
    return await execute_db(_update)

async def db_delete_scheduled_post(post_id: int):
    async def _delete(conn):
        await conn.execute("DELETE FROM scheduled_posts WHERE id = ?", (post_id,))
        await conn.commit()
    return await execute_db(_delete)

async def db_stats():
    async def _stats(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM users")
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE banned=1")
        banned = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE published=0")
        posts = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM bot_groups")
        groups = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM user_channels")
        channels = (await cur.fetchone())[0]
        return total, banned, posts, groups, channels
    return await execute_db(_stats)

async def db_get_publish_interval_seconds() -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='publish_interval'")
        row = await cur.fetchone()
        return int(row[0]) if row else DEFAULT_PUBLISH_INTERVAL_SECONDS
    return await execute_db(_get)

async def db_set_publish_interval_seconds(seconds: int, admin_id: int, is_admin: bool = False):
    if not is_admin and admin_id != PRIMARY_OWNER_ID:
        return False
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('publish_interval', ?)", (str(seconds),))
        await conn.commit()
    return await execute_db(_set)

async def db_get_updates_channel():
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='updates_channel'")
        row = await cur.fetchone()
        if row and row[0]:
            channel = row[0].strip()
            if channel.startswith('@'):
                channel = channel[1:]
            return channel if channel else None
        return None
    return await execute_db(_get)

async def db_set_updates_channel(channel: str):
    if not channel:
        return False
    channel = channel.strip()
    if channel.startswith('@'):
        channel = channel[1:]
    if not channel:
        return False
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('updates_channel', ?)", (channel,))
        await conn.commit()
    return await execute_db(_set)

async def db_get_force_subscribe_status() -> bool:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='force_subscribe_enabled'")
        row = await cur.fetchone()
        return row and row[0] == '1'
    return await execute_db(_get)

async def db_set_force_subscribe_status(enabled: bool):
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('force_subscribe_enabled', ?)", ('1' if enabled else '0',))
        await conn.commit()
    return await execute_db(_set)

async def db_get_force_subscribe_channel():
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='force_subscribe_channel'")
        row = await cur.fetchone()
        return row[0] if row and row[0] else None
    return await execute_db(_get)

async def db_set_force_subscribe_channel(channel: str):
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('force_subscribe_channel', ?)", (channel,))
        await conn.commit()
    return await execute_db(_set)

async def db_get_log_channel_id():
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='log_channel_id'")
        row = await cur.fetchone()
        return row[0] if row and row[0] else None
    return await execute_db(_get)

async def db_set_log_channel_id(channel_id: str):
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('log_channel_id', ?)", (channel_id,))
        await conn.commit()
    return await execute_db(_set)

async def db_get_auto_backup() -> bool:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='auto_backup'")
        row = await cur.fetchone()
        return row and row[0] == '1'
    return await execute_db(_get)

async def db_set_auto_backup(enabled: bool) -> None:
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_backup', ?)", ('1' if enabled else '0',))
        await conn.commit()
    return await execute_db(_set)

async def db_get_last_backup_time():
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='last_backup'")
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_get_allowed_sendcode_user() -> int | None:
    async def _get(conn):
        cur = await conn.execute("SELECT user_id FROM allowed_sendcode_user WHERE id=1")
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_set_allowed_sendcode_user(user_id: int) -> None:
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO allowed_sendcode_user (id, user_id) VALUES (1, ?)", (user_id,))
        await conn.commit()
    return await execute_db(_set)

# ===================================================================
# 21. دوال المجموعات
# ===================================================================
async def db_register_group(chat_id: int, chat_name: str, added_by: int, username: str = None) -> bool:
    chat_name = chat_name.strip()[:255]
    username = username.strip()[:100] if username and isinstance(username, str) else None
    async def _register(conn):
        try:
            cur = await conn.execute("SELECT chat_id, banned FROM bot_groups WHERE chat_id=?", (chat_id,))
            existing = await cur.fetchone()
            if existing:
                await conn.execute(
                    "UPDATE bot_groups SET chat_name=?, username=?, added_by=?, updated_at=? WHERE chat_id=?",
                    (chat_name, username, added_by, utc_now_iso(), chat_id)
                )
                await conn.commit()
                return not existing[1]
            await conn.execute(
                "INSERT INTO bot_groups (chat_id, chat_name, username, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, chat_name, username, added_by, utc_now_iso())
            )
            await conn.execute("INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?, ?)", (added_by, chat_id))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في تسجيل المجموعة {chat_id}: {e}")
            await conn.rollback()
            return False
    return await execute_db(_register)

async def db_get_user_groups(user_id: int):
    async def _get(conn):
        try:
            result = []
            seen = set()
            cur = await conn.execute("""
                SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned
                FROM bot_groups bg
                INNER JOIN hidden_owner_groups hog ON bg.chat_id = hog.chat_id
                WHERE hog.owner_id = ? AND hog.is_hidden = 1
                ORDER BY bg.chat_name
            """, (user_id,))
            for row in await cur.fetchall():
                if row[0] not in seen:
                    seen.add(row[0])
                    result.append(row)
            cur = await conn.execute("""
                SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned
                FROM bot_groups bg
                INNER JOIN hidden_admins ha ON bg.chat_id = ha.chat_id
                WHERE ha.admin_id = ?
                ORDER BY bg.chat_name
            """, (user_id,))
            for row in await cur.fetchall():
                if row[0] not in seen:
                    seen.add(row[0])
                    result.append(row)
            cur = await conn.execute("""
                SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned
                FROM bot_groups bg
                INNER JOIN group_admins ga ON bg.chat_id = ga.chat_id
                WHERE ga.user_id = ?
                ORDER BY bg.chat_name
            """, (user_id,))
            for row in await cur.fetchall():
                if row[0] not in seen:
                    seen.add(row[0])
                    result.append(row)
            return result
        except Exception as e:
            logger.error(f"خطأ في جلب مجموعات المستخدم {user_id}: {e}")
            return []
    return await execute_db(_get)

async def db_get_user_groups_count(user_id: int) -> int:
    async def _get(conn):
        try:
            groups = await db_get_user_groups(user_id)
            return len(groups)
        except:
            return 0
    return await execute_db(_get)

async def db_get_all_groups(only_banned: bool = False):
    async def _get(conn):
        if only_banned:
            cur = await conn.execute("SELECT chat_id, chat_name, username, added_by, added_at, banned FROM bot_groups WHERE banned=1 ORDER BY added_at DESC")
        else:
            cur = await conn.execute("SELECT chat_id, chat_name, username, added_by, added_at, banned FROM bot_groups ORDER BY added_at DESC")
        return await cur.fetchall()
    return await execute_db(_get)

async def db_toggle_group_ban(chat_id: int):
    async def _toggle(conn):
        cur = await conn.execute("SELECT banned FROM bot_groups WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        if row:
            new_status = 1 if row[0] == 0 else 0
            await conn.execute("UPDATE bot_groups SET banned=? WHERE chat_id=?", (new_status, chat_id))
            await conn.commit()
            return new_status == 1
        return False
    return await execute_db(_toggle)

async def db_is_real_admin(chat_id: int, user_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM group_admins WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_check)

async def db_is_hidden_owner(chat_id: int, user_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=? AND is_hidden=1", (chat_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_check)

async def db_is_hidden_admin(chat_id: int, user_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_check)

async def db_register_hidden_owner_group(chat_id: int, owner_id: int) -> bool:
    async def _register(conn):
        try:
            await conn.execute("INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?, ?, 1)", (chat_id, owner_id))
            await conn.execute("INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?, ?)", (owner_id, chat_id))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في تسجيل المالك المخفي {owner_id}: {e}")
            await conn.rollback()
            return False
    return await execute_db(_register)

async def db_add_hidden_admin(chat_id: int, admin_id: int, added_by: int) -> bool:
    async def _add(conn):
        try:
            cur = await conn.execute("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
            if await cur.fetchone():
                return False
            await conn.execute("INSERT INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?, ?, ?, ?)", (chat_id, admin_id, added_by, utc_now_iso()))
            await conn.execute("INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?, ?)", (admin_id, chat_id))
            await conn.commit()
            # تسجيل الحدث الأمني
            await log_security_event("HIDDEN_ADMIN_ADDED", chat_id, admin_id, {"added_by": added_by}, "high")
            return True
        except Exception as e:
            logger.error(f"خطأ في إضافة مشرف مخفي {admin_id}: {e}")
            await conn.rollback()
            return False
    return await execute_db(_add)

async def db_remove_hidden_admin(chat_id: int, admin_id: int) -> bool:
    async def _remove(conn):
        try:
            await conn.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
            await conn.execute("DELETE FROM user_groups_link WHERE user_id=? AND chat_id=?", (admin_id, chat_id))
            await conn.commit()
            invalidate_auth_cache(chat_id, admin_id)
            # تسجيل الحدث الأمني
            await log_security_event("HIDDEN_ADMIN_REMOVED", chat_id, admin_id, {}, "high")
            return True
        except Exception as e:
            logger.error(f"خطأ في إزالة المشرف المخفي {admin_id}: {e}")
            await conn.rollback()
            return False
    return await execute_db(_remove)

async def db_get_hidden_admins(chat_id: int) -> List[Dict]:
    async def _get(conn):
        cur = await conn.execute("SELECT admin_id, added_by, added_at FROM hidden_admins WHERE chat_id=? ORDER BY added_at DESC", (chat_id,))
        rows = await cur.fetchall()
        return [{'admin_id': row[0], 'added_by': row[1], 'added_at': row[2]} for row in rows]
    return await execute_db(_get)

async def db_sync_group_admins(chat_id: int, bot, owner_id: int = None) -> int:
    try:
        admins = await bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        if not admin_ids:
            logger.warning(f"لا يوجد مشرفين في المجموعة {chat_id}")
            return 0
        async def _update(conn):
            try:
                await conn.execute("DELETE FROM group_admins WHERE chat_id=?", (chat_id,))
                if admin_ids:
                    values = [(chat_id, uid) for uid in admin_ids]
                    await conn.executemany("INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?, ?)", values)
                await conn.execute("DELETE FROM hidden_admins WHERE chat_id = ? AND admin_id NOT IN (SELECT user_id FROM group_admins WHERE chat_id = ?) AND admin_id NOT IN (SELECT owner_id FROM hidden_owner_groups WHERE chat_id = ?)", (chat_id, chat_id, chat_id))
                await conn.execute("DELETE FROM hidden_owner_groups WHERE chat_id = ? AND owner_id NOT IN (SELECT user_id FROM group_admins WHERE chat_id = ?)", (chat_id, chat_id))
                await conn.commit()
                return len(admin_ids)
            except Exception as e:
                logger.error(f"خطأ في تحديث مشرفي المجموعة {chat_id}: {e}")
                await conn.rollback()
                return 0
        count = await execute_db(_update)
        for admin_id in admin_ids:
            invalidate_auth_cache(chat_id, admin_id)
        return count
    except Exception as e:
        logger.error(f"خطأ في مزامنة مشرفي المجموعة {chat_id}: {e}")
        return 0

# ===================================================================
# 22. دوال الأمان والحماية
# ===================================================================
async def ensure_security_columns(conn):
    try:
        cur = await conn.execute("PRAGMA table_info(group_security)")
        existing_columns = [row[1] for row in await cur.fetchall()]

        required_columns = {
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
            'night_mode_action': 'TEXT DEFAULT "mute"'
        }

        for col_name, col_type in required_columns.items():
            if col_name not in existing_columns:
                await conn.execute(f"ALTER TABLE group_security ADD COLUMN {col_name} {col_type}")
                logger.info(f"تم إضافة العمود {col_name}")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                chat_id INTEGER,
                user_id INTEGER,
                details TEXT,
                severity TEXT DEFAULT 'info',
                created_at TEXT NOT NULL
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_type ON security_events(event_type)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_severity ON security_events(severity)")
        await conn.commit()
    except Exception as e:
        logger.error(f"خطأ في تحديث أعمدة الأمان: {e}")

async def check_failed_attempts(chat_id: int, user_id: int) -> bool:
    cache_key = f"failed_{chat_id}_{user_id}"
    now = time_module.time()
    if cache_key not in _failed_attempts_cache:
        _failed_attempts_cache[cache_key] = []
    _failed_attempts_cache[cache_key] = [t for t in _failed_attempts_cache[cache_key] if now - t < _FAILED_ATTEMPTS_WINDOW]
    if len(_failed_attempts_cache[cache_key]) >= _MAX_FAILED_ATTEMPTS:
        await log_security_event("brute_force_blocked", chat_id, user_id, {"attempts": len(_failed_attempts_cache[cache_key])}, "high")
        return False
    _failed_attempts_cache[cache_key].append(now)
    return True

async def db_check_antiflood(chat_id: int, user_id: int) -> bool:
    settings = await db_get_security_settings(chat_id)
    if not settings.get('antiflood_enabled', False):
        return False
    max_messages = settings.get('antiflood_messages', 5)
    time_window = settings.get('antiflood_seconds', 10)
    cache_key = f"flood_{chat_id}_{user_id}"
    now = time_module.time()
    if cache_key in _flood_cache:
        messages = _flood_cache.pop(cache_key)
        messages = [t for t in messages if now - t < time_window]
        messages.append(now)
        _flood_cache[cache_key] = messages
        if len(messages) > max_messages:
            return True
    else:
        _flood_cache[cache_key] = [now]
    while len(_flood_cache) > _FLOOD_CACHE_MAX_SIZE:
        _flood_cache.popitem(last=False)
    if now - _flood_cache_time.get('last_cleanup', 0) > 300:
        _flood_cache_time['last_cleanup'] = now
        keys_to_remove = []
        for key, messages in _flood_cache.items():
            if isinstance(messages, list):
                messages = [t for t in messages if now - t < time_window]
                if not messages:
                    keys_to_remove.append(key)
                else:
                    _flood_cache[key] = messages
        for key in keys_to_remove:
            _flood_cache.pop(key, None)
    return False

def _get_column_name(setting_key: str) -> str:
    mapping = {
        'links': 'delete_links', 'mentions': 'mentions', 'warn': 'warn_message',
        'slow_mode': 'slow_mode', 'slow_mode_seconds': 'slow_mode_seconds',
        'welcome_enabled': 'welcome_enabled', 'welcome_text': 'welcome_text',
        'goodbye_enabled': 'goodbye_enabled', 'goodbye_text': 'goodbye_text',
        'delete_banned_words': 'delete_banned_words', 'auto_penalty': 'auto_penalty',
        'auto_mute_duration': 'auto_mute_duration', 'delete_videos': 'delete_videos',
        'delete_audio': 'delete_audio', 'delete_animation': 'delete_animation',
        'delete_service': 'delete_service', 'delete_documents': 'delete_documents',
        'delete_stickers': 'delete_stickers', 'delete_forwarded': 'delete_forwarded',
        'delete_polls': 'delete_polls', 'delete_games': 'delete_games',
        'delete_voice': 'delete_voice', 'delete_video_note': 'delete_video_note',
        'delete_penalty': 'delete_penalty', 'delete_penalty_duration': 'delete_penalty_duration',
        'antiflood_enabled': 'antiflood_enabled', 'antiflood_messages': 'antiflood_messages',
        'antiflood_seconds': 'antiflood_seconds', 'antiflood_penalty': 'antiflood_penalty',
        'max_warnings': 'max_warnings', 'warn_penalty': 'warn_penalty',
        'max_message_length': 'max_message_length', 'night_mode_enabled': 'night_mode_enabled',
        'night_mode_start': 'night_mode_start', 'night_mode_end': 'night_mode_end',
        'night_mode_action': 'night_mode_action'
    }
    return mapping.get(setting_key)

# ===================================================================
# 23. دوال الكلمات المحظورة
# ===================================================================
async def db_add_banned_word(word: str, chat_id: int, added_by: int) -> bool:
    if not word or not isinstance(word, str):
        return False
    if not isinstance(chat_id, int) or chat_id <= 0:
        return False
    word = word.strip().lower()[:100]
    if len(word) < 2:
        return False
    async def _add(conn):
        try:
            cur = await conn.execute("SELECT COUNT(*) FROM banned_words WHERE chat_id=?", (chat_id,))
            count = (await cur.fetchone())[0]
            if count >= _MAX_BANNED_WORDS_PER_CHAT:
                logger.warning(f"تم الوصول للحد الأقصى للكلمات المحظورة في {chat_id}")
                return False
            if chat_id == -1:
                cur = await conn.execute("SELECT COUNT(*) FROM banned_words WHERE chat_id=-1")
                global_count = (await cur.fetchone())[0]
                if global_count >= _MAX_BANNED_WORDS_GLOBAL:
                    logger.warning("تم الوصول للحد الأقصى للكلمات المحظورة العامة")
                    return False
            await conn.execute("INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?, ?, ?, ?)", (word, chat_id, added_by, utc_now_iso()))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في إضافة كلمة محظورة: {e}")
            return False
    return await execute_db(_add)

async def db_remove_banned_word(word: str, chat_id: int) -> bool:
    if not word or not isinstance(word, str):
        return False
    word = word.strip().lower()
    async def _remove(conn):
        try:
            await conn.execute("DELETE FROM banned_words WHERE word=? AND chat_id=?", (word, chat_id))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في حذف كلمة محظورة: {e}")
            return False
    return await execute_db(_remove)

async def db_get_banned_words(chat_id: int):
    async def _get(conn):
        try:
            cur = await conn.execute("SELECT word, added_by, added_at FROM banned_words WHERE chat_id=? OR chat_id=-1", (chat_id,))
            return await cur.fetchall()
        except Exception as e:
            logger.error(f"خطأ في جلب الكلمات المحظورة: {e}")
            return []
    return await execute_db(_get)

async def db_contains_banned_word(text: str, chat_id: int) -> Optional[str]:
    if not text:
        return None
    words = await db_get_banned_words(chat_id)
    text_lower = text.lower()
    for word, _, _ in words:
        if word in text_lower:
            return word
    return None

# ===================================================================
# 24. دوال الصلاحيات المتقدمة
# ===================================================================
async def check_bot_admin_permissions_group(bot, chat_id: int) -> dict:
    try:
        me = await bot.get_chat_member(chat_id, bot.id)
        if me.status not in ['administrator', 'creator']:
            return {'can_act': False, 'reason': 'البوت ليس مشرفاً'}
        perms = {
            'can_delete': getattr(me, 'can_delete_messages', False),
            'can_ban': getattr(me, 'can_restrict_members', False),
            'can_pin': getattr(me, 'can_pin_messages', False),
            'can_invite': getattr(me, 'can_invite_users', False)
        }
        missing = [k for k, v in perms.items() if not v]
        if missing:
            return {'can_act': False, 'reason': f'ينقص البوت صلاحيات: {", ".join(missing)}', 'permissions': perms}
        return {'can_act': True, 'reason': '', 'permissions': perms}
    except Exception as e:
        return {'can_act': False, 'reason': str(e)}

async def is_currently_admin_in_group(bot, chat_id: int, user_id: int) -> bool:
    if user_id == ANONYMOUS_ADMIN_ID:
        try:
            admins = await bot.get_chat_administrators(chat_id)
            return len(admins) > 0
        except Exception:
            return False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"خطأ في التحقق من مشرف {user_id} في {chat_id}: {e}")
        return False

def invalidate_auth_cache(chat_id: int = None, user_id: int = None):
    try:
        if chat_id and user_id:
            key = f"auth_{chat_id}_{user_id}"
            _auth_cache.pop(key, None)
        elif chat_id:
            keys = [k for k in _auth_cache if k.startswith(f"auth_{chat_id}_")]
            for k in keys:
                _auth_cache.pop(k, None)
        else:
            _auth_cache.clear()
    except Exception as e:
        logger.error(f"خطأ في مسح الكاش: {e}")

async def is_authorized_in_group(bot, chat_id: int, user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID:
        return True
    bot_perms = await check_bot_admin_permissions_group(bot, chat_id)
    if not bot_perms.get('can_act', False):
        return False
    cache_key = f"auth_{chat_id}_{user_id}"
    if cache_key in _auth_cache:
        cached_time, value = _auth_cache[cache_key]
        if time_module.time() - cached_time < 60:
            return value
    authorized = False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            authorized = True
        else:
            if await db_is_hidden_owner(chat_id, user_id):
                authorized = True
            elif await db_is_hidden_admin(chat_id, user_id):
                authorized = True
            else:
                authorized = False
    except Exception as e:
        logger.warning(f"فشل التحقق من {user_id} في {chat_id}: {e}")
        authorized = await db_is_hidden_owner(chat_id, user_id) or await db_is_hidden_admin(chat_id, user_id) or await db_is_real_admin(chat_id, user_id)
    _auth_cache[cache_key] = (time_module.time(), authorized)
    return authorized

async def is_bot_admin(user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID:
        return True
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM bot_admins WHERE user_id=?", (user_id,))
        return await cur.fetchone() is not None
    return await execute_db(_check)

async def add_bot_admin(user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID:
        return True
    async def _add(conn):
        await conn.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (user_id,))
        await conn.commit()
        return True
    return await execute_db(_add)

async def remove_bot_admin(user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID:
        return False
    async def _remove(conn):
        await conn.execute("DELETE FROM bot_admins WHERE user_id=?", (user_id,))
        await conn.commit()
        return True
    return await execute_db(_remove)

# ===================================================================
# 25. دوال العقوبات والإجراءات الإشرافية
# ===================================================================
async def apply_penalty_with_duration(bot, chat_id: int, user_id: int, 
                                     penalty: str, duration_minutes: int = 0, 
                                     reason: str = "") -> Tuple[bool, str]:
    if user_id == PRIMARY_OWNER_ID:
        return False, "لا يمكن تطبيق عقوبة على المطور الأساسي"
    if await db_is_hidden_owner(chat_id, user_id):
        return False, "لا يمكن تطبيق عقوبة على المالك المخفي"
    result = False, "عقوبة غير معروفة"
    if penalty == 'kick':
        result = await execute_kick(bot, chat_id, user_id, reason)
    elif penalty == 'ban':
        result = await execute_ban(bot, chat_id, user_id, reason)
    elif penalty == 'mute':
        result = await execute_mute(bot, chat_id, user_id, duration_minutes, reason)
    elif penalty == 'warn':
        result = await execute_warn(bot, chat_id, user_id, bot.id, reason)
    return result

async def execute_ban(bot, chat_id: int, user_id: int, reason: str = "", moderator_id: int = None) -> Tuple[bool, str]:
    try:
        await bot.ban_chat_member(chat_id, user_id)
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, reason, created_at) VALUES (?, ?, 'ban', ?, ?, ?)", (chat_id, user_id, moderator_id, reason[:200] if reason else "", utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        return True, f"✅ تم حظر المستخدم {user_id}"
    except Exception as e:
        logger.error(f"خطأ في حظر المستخدم {user_id}: {e}")
        return False, "❌ حدث خطأ أثناء تنفيذ العملية"

async def execute_mute(bot, chat_id: int, user_id: int, duration_minutes: int = None, reason: str = "", moderator_id: int = None) -> Tuple[bool, str]:
    try:
        until_date = None
        if duration_minutes and duration_minutes > 0:
            until_date = datetime.utcnow() + timedelta(minutes=duration_minutes)
        permissions = ChatPermissions(can_send_messages=False)
        await bot.restrict_chat_member(chat_id, user_id, permissions, until_date=until_date)
        duration_text = f" لمدة {duration_minutes} دقيقة" if duration_minutes else " بشكل دائم"
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'mute', ?, ?, ?, ?)", (chat_id, user_id, duration_minutes or -1, moderator_id, reason[:200] if reason else "", utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        return True, f"✅ تم كتم المستخدم {user_id}{duration_text}"
    except Exception as e:
        logger.error(f"خطأ في كتم المستخدم {user_id}: {e}")
        return False, "❌ حدث خطأ أثناء تنفيذ العملية"

async def execute_kick(bot, chat_id: int, user_id: int, reason: str = "", moderator_id: int = None) -> Tuple[bool, str]:
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id)
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, reason, created_at) VALUES (?, ?, 'kick', ?, ?, ?)", (chat_id, user_id, moderator_id, reason[:200] if reason else "", utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        return True, f"✅ تم طرد المستخدم {user_id}"
    except Exception as e:
        logger.error(f"خطأ في طرد المستخدم {user_id}: {e}")
        return False, "❌ حدث خطأ أثناء تنفيذ العملية"

async def execute_warn(bot, chat_id: int, user_id: int, moderator_id: int, reason: str = "") -> Tuple[bool, str]:
    settings = await db_get_security_settings(chat_id)
    max_warnings = settings.get('max_warnings', 3)
    warn_penalty = settings.get('warn_penalty', 'ban')
    async def _add_warning(conn):
        cur = await conn.execute("SELECT warnings FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        row = await cur.fetchone()
        warnings = (row[0] if row else 0) + 1
        await conn.execute("INSERT OR REPLACE INTO user_warnings (user_id, chat_id, warnings) VALUES (?, ?, ?)", (user_id, chat_id, warnings))
        await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'warn', ?, ?, ?, ?)", (chat_id, user_id, warnings, moderator_id, reason[:200] if reason else "", utc_now_iso()))
        await conn.commit()
        return warnings
    warnings = await execute_db(_add_warning)
    if warnings >= max_warnings:
        penalty_reason = f"تلقائي بعد {warnings} تحذيرات"
        if warn_penalty == 'ban':
            await execute_ban(bot, chat_id, user_id, penalty_reason, moderator_id)
        elif warn_penalty == 'kick':
            await execute_kick(bot, chat_id, user_id, penalty_reason, moderator_id)
        elif warn_penalty == 'mute':
            await execute_mute(bot, chat_id, user_id, 1440, penalty_reason, moderator_id)
        async def _clear(conn):
            await conn.execute("DELETE FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            await conn.commit()
        await execute_db(_clear)
        return True, f"⚠️ تحذير {warnings}/{max_warnings} - تم تطبيق {warn_penalty}"
    return True, f"⚠️ تحذير {warnings}/{max_warnings}"

async def execute_restrict(bot, chat_id: int, user_id: int, reason: str = "", moderator_id: int = None) -> Tuple[bool, str]:
    try:
        permissions = ChatPermissions(can_send_messages=True, can_send_media_messages=False, can_send_other_messages=False, can_add_web_page_previews=False)
        await bot.restrict_chat_member(chat_id, user_id, permissions)
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, reason, created_at) VALUES (?, ?, 'restrict', ?, ?, ?)", (chat_id, user_id, moderator_id, reason[:200] if reason else "", utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        return True, f"✅ تم تقييد المستخدم {user_id}"
    except Exception as e:
        logger.error(f"خطأ في تقييد المستخدم {user_id}: {e}")
        return False, "❌ حدث خطأ أثناء تنفيذ العملية"

async def execute_unban(bot, chat_id: int, user_id: int, moderator_id: int = None) -> Tuple[bool, str]:
    try:
        await bot.unban_chat_member(chat_id, user_id)
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, created_at) VALUES (?, ?, 'unban', ?, ?)", (chat_id, user_id, moderator_id, utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        return True, f"✅ تم إلغاء حظر المستخدم {user_id}"
    except Exception as e:
        logger.error(f"خطأ في إلغاء حظر المستخدم {user_id}: {e}")
        return False, "❌ حدث خطأ أثناء تنفيذ العملية"

async def execute_pin(bot, chat_id: int, message_id: int, disable_notification: bool = False) -> Tuple[bool, str]:
    try:
        await bot.pin_chat_message(chat_id, message_id, disable_notification=disable_notification)
        return True, "✅ تم تثبيت الرسالة"
    except Exception as e:
        return False, f"❌ فشل التثبيت: {str(e)[:100]}"

async def execute_moderation_action(bot, chat_id: int, user_id: int, action: str, reason: str = "", duration: int = None, moderator_id: int = None):
    if action == 'ban':
        return await execute_ban(bot, chat_id, user_id, reason=reason, moderator_id=moderator_id)
    elif action == 'mute':
        return await execute_mute(bot, chat_id, user_id, duration_minutes=duration, reason=reason, moderator_id=moderator_id)
    elif action == 'warn':
        return await execute_warn(bot, chat_id, user_id, moderator_id, reason=reason)
    elif action == 'kick':
        return await execute_kick(bot, chat_id, user_id, reason=reason, moderator_id=moderator_id)
    elif action == 'restrict':
        return await execute_restrict(bot, chat_id, user_id, reason=reason, moderator_id=moderator_id)
    elif action == 'unban':
        return await execute_unban(bot, chat_id, user_id, moderator_id=moderator_id)
    elif action == 'pin':
        return None, "استخدم زر التثبيت مع الرد على الرسالة"
    else:
        return False, f"إجراء غير معروف: {action}"
# ===================================================================
# دوال المستخدمين - المفقودة
# ===================================================================

async def db_get_user_language(user_id: int) -> str:
    """جلب لغة المستخدم من قاعدة البيانات"""
    async def _get(conn):
        cur = await conn.execute("SELECT lang FROM user_translation WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_set_user_language(user_id: int, lang: str) -> None:
    """حفظ لغة المستخدم في قاعدة البيانات"""
    async def _set(conn):
        await conn.execute(
            "INSERT OR REPLACE INTO user_translation (user_id, lang) VALUES (?, ?)",
            (user_id, lang)
        )
        await conn.commit()
    return await execute_db(_set)

# ===================================================================
# دوال الإحالات - المفقودة
# ===================================================================

async def db_get_referral_code(user_id: int) -> str:
    """الحصول على كود الإحالة للمستخدم"""
    async def _get(conn):
        cur = await conn.execute("SELECT referral_code FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row and row[0] else None
    return await execute_db(_get)

async def db_generate_referral_code(user_id: int) -> str:
    """إنشاء كود إحالة للمستخدم"""
    async def _generate(conn):
        code_hash = hashlib.md5(f"{user_id}{time_module.time()}".encode()).hexdigest()[:8]
        referral_code = f"REF{code_hash.upper()}"
        await conn.execute("UPDATE users SET referral_code=? WHERE user_id=?", (referral_code, user_id))
        await conn.commit()
        return referral_code
    return await execute_db(_generate)

async def db_get_user_by_referral_code(referral_code: str) -> int | None:
    """الحصول على المستخدم بواسطة كود الإحالة"""
    async def _get(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE referral_code=?", (referral_code,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_add_referral(referrer_id: int, referred_id: int) -> bool:
    """إضافة إحالة جديدة"""
    async def _add(conn):
        if referrer_id == referred_id:
            return False
        cur = await conn.execute("SELECT 1 FROM referrals WHERE referred_id=?", (referred_id,))
        if await cur.fetchone():
            return False
        today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        cur = await conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND referred_at >= ?",
                                (referrer_id, today_start))
        count_today = (await cur.fetchone())[0]
        settings = await db_get_referral_settings()
        max_per_day = int(settings.get('max_referrals_per_day', '5'))
        if count_today >= max_per_day:
            return False
        await conn.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)", (referrer_id, referred_id))
        await conn.execute(
            "INSERT INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days) VALUES (?, 1, 0, 0) ON CONFLICT(user_id) DO UPDATE SET referral_count = referral_count + 1",
            (referrer_id,)
        )
        await conn.commit()
        return True
    return await execute_db(_add)

async def db_auto_reward_referral(referrer_id: int, referred_id: int) -> int:
    """مكافأة تلقائية للإحالة"""
    async def _reward(conn):
        settings = await db_get_referral_settings()
        reward_days = int(settings.get('reward_days_per_referral', '3'))
        await conn.execute("""
            INSERT INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days)
            VALUES (?, 0, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                referral_count = referral_count + 1,
                total_reward_days = total_reward_days + ?
        """, (referrer_id, reward_days, reward_days))
        await conn.execute("UPDATE referrals SET is_rewarded=1 WHERE referrer_id=? AND referred_id=?",
                          (referrer_id, referred_id))
        await conn.commit()
        return reward_days
    return await execute_db(_reward)

async def db_get_referral_stats(user_id: int) -> dict:
    """الحصول على إحصائيات الإحالات للمستخدم"""
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,))
        total_referrals = (await cur.fetchone())[0]
        cur = await conn.execute(
            "SELECT referral_count, total_reward_days, claimed_reward_days FROM referral_rewards WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        return {
            'total_referrals': total_referrals,
            'referral_count': row[0] if row else 0,
            'total_reward_days': row[1] if row else 0,
            'claimed_reward_days': row[2] if row else 0,
            'available_days': (row[1] if row else 0) - (row[2] if row else 0)
        }
    return await execute_db(_get)

async def db_claim_referral_reward(user_id: int) -> int:
    """صرف مكافآت الإحالات"""
    async def _claim(conn):
        cur = await conn.execute("SELECT total_reward_days, claimed_reward_days FROM referral_rewards WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return 0
        total = row[0]
        claimed = row[1]
        available = total - claimed
        if available <= 0:
            return 0
        current_sub = await db_get_subscription_days_left(user_id)
        new_sub_days = current_sub + available
        end_date = (utc_now() + timedelta(days=new_sub_days)).isoformat()
        await conn.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (end_date, user_id))
        await conn.execute("UPDATE referral_rewards SET claimed_reward_days = claimed_reward_days + ? WHERE user_id=?",
                          (available, user_id))
        await conn.commit()
        return available
    return await execute_db(_claim)

# ===================================================================
# دوال التذكيرات - المفقودة
# ===================================================================

async def db_get_user_reminder_settings(user_id: int) -> dict:
    """الحصول على إعدادات التذكيرات للمستخدم"""
    async def _get(conn):
        cur = await conn.execute(
            """SELECT subscription_reminder, daily_stats_reminder, weekly_report,
                      reminder_days_before, last_reminder_sent, notification_lang
               FROM user_reminder_settings WHERE user_id=?""",
            (user_id,)
        )
        row = await cur.fetchone()
        if row:
            return {
                'subscription_reminder': row[0] == 1,
                'daily_stats_reminder': row[1] == 1,
                'weekly_report': row[2] == 1,
                'reminder_days_before': row[3] if row[3] is not None else 3,
                'last_reminder_sent': row[4] if row[4] else 0,
                'notification_lang': row[5] if row[5] else 'ar'
            }
        else:
            await conn.execute(
                "INSERT INTO user_reminder_settings (user_id, subscription_reminder, daily_stats_reminder, weekly_report, reminder_days_before, last_reminder_sent, notification_lang) VALUES (?, 1, 0, 1, 3, 0, 'ar')",
                (user_id,)
            )
            await conn.commit()
            return {
                'subscription_reminder': True, 'daily_stats_reminder': False,
                'weekly_report': True, 'reminder_days_before': 3,
                'last_reminder_sent': 0, 'notification_lang': 'ar'
            }
    return await execute_db(_get)

async def db_update_reminder_settings(user_id: int, **kwargs):
    """تحديث إعدادات التذكيرات للمستخدم"""
    async def _update(conn):
        fields, values = [], []
        for key, value in kwargs.items():
            if key == 'subscription_reminder':
                fields.append("subscription_reminder=?")
                values.append(1 if value else 0)
            elif key == 'daily_stats_reminder':
                fields.append("daily_stats_reminder=?")
                values.append(1 if value else 0)
            elif key == 'weekly_report':
                fields.append("weekly_report=?")
                values.append(1 if value else 0)
            elif key == 'reminder_days_before':
                fields.append("reminder_days_before=?")
                values.append(value)
            elif key == 'notification_lang':
                fields.append("notification_lang=?")
                values.append(value)
        if fields:
            query = f"UPDATE user_reminder_settings SET {', '.join(fields)} WHERE user_id=?"
            values.append(user_id)
            await conn.execute(query, values)
            await conn.commit()
    return await execute_db(_update)

async def db_update_last_reminder_sent(user_id: int, reminder_type: str):
    """تحديث وقت آخر تذكير تم إرساله"""
    async def _update(conn):
        now_timestamp = int(time_module.time())
        await conn.execute("UPDATE user_reminder_settings SET last_reminder_sent=? WHERE user_id=?",
                          (now_timestamp, user_id))
        await conn.commit()
    return await execute_db(_update)

async def db_get_users_needing_reminder() -> list:
    """الحصول على المستخدمين الذين يحتاجون تذكير"""
    async def _get(conn):
        now = utc_now()
        users = []
        cutoff_date = (now + timedelta(days=10)).isoformat()
        cur = await conn.execute(
            "SELECT user_id, subscription_end FROM users WHERE subscription_end IS NOT NULL AND subscription_end <= ? AND banned=0",
            (cutoff_date,)
        )
        rows = await cur.fetchall()
        for user_id, subscription_end_str in rows:
            try:
                end_date = datetime.fromisoformat(subscription_end_str)
                days_left = (end_date - now).days
                if days_left < 0:
                    continue
                settings = await db_get_user_reminder_settings(user_id)
                if settings['subscription_reminder']:
                    reminder_days = settings['reminder_days_before']
                    last_sent = settings['last_reminder_sent']
                    now_timestamp = int(time_module.time())
                    need_reminder = False
                    if 0 < days_left <= reminder_days:
                        if last_sent == 0:
                            need_reminder = True
                        elif (now_timestamp - last_sent) > (3 * 24 * 60 * 60):
                            need_reminder = True
                    if need_reminder:
                        users.append({
                            'user_id': user_id,
                            'days_left': days_left,
                            'notification_lang': settings['notification_lang']
                        })
            except:
                continue
        return users
    return await execute_db(_get)

# ===================================================================
# دوال الترجمة - المفقودة
# ===================================================================

async def get_user_translation_language(user_id: int) -> str:
    """الحصول على لغة الترجمة للمستخدم"""
    async def _get(conn):
        cur = await conn.execute("SELECT lang FROM user_translation WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 'off'
    lang = await execute_db(_get)
    return lang

async def set_user_translation_language(user_id: int, lang: str):
    """تعيين لغة الترجمة للمستخدم"""
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO user_translation (user_id, lang) VALUES (?, ?)", (user_id, lang))
        await conn.commit()
    await execute_db(_set)

async def translate_text(text: str, target_lang: str) -> str:
    """ترجمة نص إلى اللغة المستهدفة"""
    if not text or target_lang == 'off' or target_lang == 'ar':
        return text
    cache_key = f"{hashlib.md5(text.encode()).hexdigest()}_{target_lang}"
    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        translated = translator.translate(text)
        if translated:
            return translated
    except Exception as e:
        logger.error(f"فشل الترجمة: {e}")
    return text

# ===================================================================
# دوال المستويات والنقاط - المفقودة
# ===================================================================

LEVEL_REQUIREMENTS = {
    1: 0,
    2: 100,
    3: 250,
    4: 500,
    5: 1000,
    6: 2000,
    7: 5000,
    8: 10000,
    9: 20000,
    10: 50000
}

async def db_get_user_level(user_id: int) -> dict:
    """الحصول على مستوى المستخدم ونقاطه"""
    async def _get(conn):
        cur = await conn.execute("SELECT points, level FROM user_levels WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row:
            return {'points': row[0], 'level': row[1]}
        await conn.execute("INSERT INTO user_levels (user_id, points, level) VALUES (?, 0, 1)", (user_id,))
        await conn.commit()
        return {'points': 0, 'level': 1}
    return await execute_db(_get)

async def db_update_user_level(user_id: int, points: int, level: int):
    """تحديث مستوى المستخدم ونقاطه"""
    async def _update(conn):
        await conn.execute(
            "INSERT OR REPLACE INTO user_levels (user_id, points, level) VALUES (?, ?, ?)",
            (user_id, points, level)
        )
        await conn.commit()
    return await execute_db(_update)

async def get_rank(user_id: int) -> dict:
    """الحصول على رتبة المستخدم"""
    return await db_get_user_level(user_id)

async def get_top_users(limit: int = 10) -> List[tuple]:
    """الحصول على أفضل المستخدمين حسب النقاط"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT user_id, points, level FROM user_levels ORDER BY points DESC LIMIT ?",
            (limit,)
        )
        return await cur.fetchall()
    return await execute_db(_get)

# ===================================================================
# دوال المسابقات - المفقودة
# ===================================================================

async def db_create_contest(creator_id: int, title: str, description: str, prize: str,
                            end_date: datetime, contest_type: str = 'raffle') -> int:
    """إنشاء مسابقة جديدة"""
    try:
        if end_date <= utc_now():
            raise ValueError("end_date must be in future")
        async def _create(conn):
            if not isinstance(end_date, datetime):
                raise ValueError("end_date must be datetime object")
            end_date_str = end_date.isoformat()
            created_at_str = utc_now_iso()
            cur = await conn.execute("""
                INSERT INTO contests (creator_id, title, description, prize, end_date, status, created_at, contest_type)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
            """, (creator_id, title, description, prize, end_date_str, created_at_str, contest_type))
            await conn.commit()
            return cur.lastrowid
        contest_id = await execute_db(_create)
        if contest_id:
            logger.info(f"✅ تم إنشاء مسابقة جديدة (ID: {contest_id}) بواسطة المستخدم {creator_id}")
        return contest_id
    except Exception as e:
        logger.error(f"❌ خطأ في db_create_contest: {e}")
        return None

async def db_participate_in_contest(user_id: int, contest_id: int, answer: str = "") -> bool:
    """المشاركة في مسابقة"""
    async def _participate(conn):
        try:
            await conn.execute(
                "INSERT INTO contest_participants (user_id, contest_id, answer, joined_at) VALUES (?, ?, ?, ?)",
                (user_id, contest_id, answer, utc_now_iso())
            )
            await conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    return await execute_db(_participate)

async def db_set_contest_winner(contest_id: int, winner_id: int) -> bool:
    """تعيين فائز في المسابقة"""
    async def _set(conn):
        await conn.execute(
            "UPDATE contests SET status = 'finished', winner_id = ? WHERE id = ?",
            (winner_id, contest_id)
        )
        await conn.execute(
            "INSERT INTO contest_winners (contest_id, winner_id, announced_at) VALUES (?, ?, ?)",
            (contest_id, winner_id, utc_now_iso())
        )
        await conn.commit()
        return True
    return await execute_db(_set)

async def db_get_contest_winners(limit: int = 10) -> list:
    """الحصول على الفائزين السابقين"""
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT c.id, c.title, c.prize, cw.winner_id, cw.announced_at
            FROM contest_winners cw
            JOIN contests c ON cw.contest_id = c.id
            ORDER BY cw.announced_at DESC LIMIT ?
        """, (limit,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_delete_contest(contest_id: int, user_id: int) -> bool:
    """حذف مسابقة"""
    async def _delete(conn):
        cur = await conn.execute("SELECT creator_id FROM contests WHERE id = ?", (contest_id,))
        row = await cur.fetchone()
        if row and (row[0] == user_id or await is_bot_admin(user_id)):
            await conn.execute("DELETE FROM contest_participants WHERE contest_id = ?", (contest_id,))
            await conn.execute("DELETE FROM contests WHERE id = ?", (contest_id,))
            await conn.commit()
            return True
        return False
    return await execute_db(_delete)

async def db_get_random_participant(contest_id: int) -> int | None:
    """الحصول على مشارك عشوائي في المسابقة"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT user_id FROM contest_participants WHERE contest_id = ? ORDER BY RANDOM() LIMIT 1",
            (contest_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

# ===================================================================
# دوال التذاكر (Support Tickets) - المفقودة
# ===================================================================

async def db_save_ticket(user_id: int, username: str, message: str, ticket_number: int) -> int:
    """حفظ تذكرة دعم جديدة"""
    async def _save(conn):
        cur = await conn.execute(
            "INSERT INTO support_tickets (user_id, username, message, ticket_number, created_at) VALUES (?, ?, ?, ?, ?) RETURNING id",
            (user_id, username, message, ticket_number, utc_now_iso())
        )
        row = await cur.fetchone()
        await conn.commit()
        return row[0] if row else None
    return await execute_db(_save)

async def db_get_all_tickets(limit: int = 20):
    """الحصول على جميع التذاكر"""
    async def _get(conn):
        cur = await conn.execute("SELECT id, user_id, username, message, ticket_number, status, created_at FROM support_tickets ORDER BY created_at DESC LIMIT ?", (limit,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_mark_ticket_replied(ticket_id: int):
    """تحديث تذكرة بأنه تم الرد عليها"""
    async def _mark(conn):
        await conn.execute("UPDATE support_tickets SET status='replied', replied=1 WHERE id=?", (ticket_id,))
        await conn.commit()
    return await execute_db(_mark)

async def db_get_next_ticket_number() -> int:
    """الحصول على رقم التذكرة التالي"""
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='last_ticket_number'")
        row = await cur.fetchone()
        return int(row[0]) if row and row[0] else 0
    return await execute_db(_get)

async def db_delete_all_tickets():
    """حذف جميع التذاكر"""
    async def _delete(conn):
        await conn.execute("DELETE FROM support_tickets")
        await conn.commit()
    return await execute_db(_delete)

# ===================================================================
# دوال الردود التلقائية - المفقودة
# ===================================================================

async def db_get_auto_reply_settings(chat_id: int) -> dict:
    """الحصول على إعدادات الردود التلقائية"""
    async def _get(conn):
        cur = await conn.execute("SELECT enabled, only_admins, ignore_bots FROM auto_reply_settings WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        if row:
            return {'enabled': row[0] == 1, 'only_admins': row[1] == 1, 'ignore_bots': row[2] == 1}
        return {'enabled': True, 'only_admins': False, 'ignore_bots': True}
    return await execute_db(_get)

async def db_set_auto_reply_enabled(chat_id: int, enabled: bool) -> None:
    """تفعيل/تعطيل الردود التلقائية"""
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO auto_reply_settings (chat_id, enabled, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (chat_id, 1 if enabled else 0))
        await conn.commit()
    return await execute_db(_set)

async def db_set_auto_reply_only_admins(chat_id: int, only_admins: bool) -> None:
    """تعيين الردود للمشرفين فقط"""
    async def _set(conn):
        await conn.execute("UPDATE auto_reply_settings SET only_admins=?, updated_at=CURRENT_TIMESTAMP WHERE chat_id=?", (1 if only_admins else 0, chat_id))
        await conn.commit()
    return await execute_db(_set)

async def db_toggle_auto_reply(chat_id: int) -> bool:
    """تبديل حالة الردود التلقائية"""
    settings = await db_get_auto_reply_settings(chat_id)
    new_status = not settings['enabled']
    await db_set_auto_reply_enabled(chat_id, new_status)
    return new_status

# ===================================================================
# دوال الردود المخصصة - المفقودة
# ===================================================================

async def db_add_reply(keyword: str, reply: str) -> None:
    """إضافة رد مخصص"""
    async def _add(conn):
        await conn.execute("INSERT OR REPLACE INTO group_replies (keyword, reply) VALUES (?, ?)", (keyword.lower(), reply))
        await conn.commit()
    return await execute_db(_add)

async def db_del_reply(keyword: str) -> bool:
    """حذف رد مخصص"""
    async def _del(conn):
        cur = await conn.execute("DELETE FROM group_replies WHERE keyword=?", (keyword.lower(),))
        await conn.commit()
        return cur.rowcount > 0
    return await execute_db(_del)

async def db_get_reply(keyword: str) -> str | None:
    """الحصول على رد مخصص"""
    async def _get(conn):
        cur = await conn.execute("SELECT reply FROM group_replies WHERE keyword=?", (keyword.lower(),))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_get_all_replies() -> list:
    """الحصول على جميع الردود المخصصة"""
    async def _get(conn):
        cur = await conn.execute("SELECT keyword, reply FROM group_replies ORDER BY keyword")
        return await cur.fetchall()
    return await execute_db(_get)

# ===================================================================
# 26. معرفات الأزرار
# ===================================================================
class CallbackData:
    MAIN_MENU = "main_menu"
    CHANNELS_MY = "channels:my_channels"
    CHANNELS_ADD = "channels:add"
    CHANNELS_DELETE_PREFIX = "channels:delete:"
    CHANNELS_SELECT_PREFIX = "channels:select:"
    POSTS_ADD_15 = "posts:add_15"
    POSTS_PUBLISH_ONE = "posts:publish_one"
    POSTS_MY = "posts:my_posts"
    POSTS_RECYCLE = "posts:recycle"
    POSTS_DELETE_SINGLE_PREFIX = "posts:delete_single:"
    POSTS_CONFIRM_CLEAR_ALL_PREFIX = "posts:confirm_clear_all:"
    POSTS_CLEAR_ALL_PREFIX = "posts:clear_all:"
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
    SCHEDULE_SET_DAYS_PREFIX = "schedule:set_days:"
    SCHEDULE_SET_DATES_PREFIX = "schedule:set_dates:"
    SCHEDULE_SET_PUBLISH_TIME_PREFIX = "schedule:set_publish_time:"
    SCHEDULE_DAY_SELECT_PREFIX = "schedule:day_select:"
    SCHEDULE_SAVE_DAYS = "schedule:save_days"
    SECURITY_LINKS_PREFIX = "security:links:"
    SECURITY_MENTIONS_PREFIX = "security:mentions:"
    SECURITY_SLOWMODE_PREFIX = "security:slow_mode:"
    SECURITY_BANNED_WORDS_MENU_PREFIX = "security:banned_words_menu:"
    SECURITY_WELCOME_PREFIX = "security:welcome_enabled:"
    SECURITY_GOODBYE_PREFIX = "security:goodbye_enabled:"
    SECURITY_CLOSE = "security:close"
    BANNED_WORDS_ADD_PREFIX = "banned_words:add:"
    BANNED_WORDS_LIST_PREFIX = "banned_words:list:"
    BANNED_WORDS_REMOVE_PREFIX = "banned_words:remove:"
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
    REFERRAL_COPY_LINK_PREFIX = "referral:copy_link:"
    REFERRAL_CLAIM_REWARD = "referral:claim_reward"
    REFERRAL_LIST = "referral:list"
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
    BACK = "back"
    CANCEL_SESSION = "cancel_session"
    ADVANCED_ACTIONS = "advanced_actions"
    GROUP_ACTION_BAN = "group_action:ban"
    GROUP_ACTION_MUTE = "group_action:mute"
    GROUP_ACTION_WARN = "group_action:warn"
    GROUP_ACTION_KICK = "group_action:kick"
    GROUP_ACTION_RESTRICT = "group_action:restrict"
    GROUP_ACTION_PIN = "group_action:pin"
    GROUP_ACTION_LOG = "group_action:log"
    GROUP_ACTION_UNBAN = "group_action:unban"
    GROUP_MUTE_DURATION_5 = "group_mute_duration:5"
    GROUP_MUTE_DURATION_30 = "group_mute_duration:30"
    GROUP_MUTE_DURATION_60 = "group_mute_duration:60"
    GROUP_MUTE_DURATION_720 = "group_mute_duration:720"
    GROUP_MUTE_DURATION_1440 = "group_mute_duration:1440"
    GROUP_MUTE_DURATION_10080 = "group_mute_duration:10080"
    GROUP_MUTE_DURATION_PERMANENT = "group_mute_duration:permanent"
    SECURITY_SELECT_GROUP = "security_select_group:"
    SECURITY_REFRESH_GROUPS = "security_refresh_groups"
    PENALTY_MENU = "penalty_menu"
    PENALTY_KICK = "penalty:kick"
    PENALTY_BAN = "penalty:ban"
    PENALTY_MUTE = "penalty:mute"
    PENALTY_WARN = "penalty:warn"
    PENALTY_RESTRICT = "penalty:restrict"
    PENALTY_NONE = "penalty:none"
    PUBLISH_ALL_CHANNELS = "publish_all_channels"
    CHANNEL_STATS = "channel_stats"
    CHANNEL_GROWTH = "channel_growth"
    CHANNEL_STATS_REFRESH = "channel_stats_refresh"
    MY_CHANNEL_STATS = "my_channel_stats"
    ADMIN_TOGGLE_CHANNEL_BAN_PREFIX = "admin:toggle_channel_ban:"
    ADMIN_TOGGLE_GROUP_BAN_PREFIX = "admin:toggle_group_ban:"
    CONTESTS_MENU = "contests_menu"
    CONTEST_JOIN_PREFIX = "contest_join:"
    CONTEST_WINNERS = "contest_winners"
    CONTESTS_BACK = "contests_back"
    HIDDEN_ADMIN_ADD = "hidden_admin:add"
    HIDDEN_ADMIN_REMOVE_PREFIX = "hidden_admin:remove:"
    HIDDEN_ADMIN_LIST = "hidden_admin:list"
    ADMIN_AUTO_REPLY = "admin_auto_reply"
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
    SECURITY_DELETE_VIDEOS_PREFIX = "security:delete_videos:"
    SECURITY_DELETE_SERVICE_PREFIX = "security:delete_service:"
    SECURITY_DELETE_DOCUMENTS_PREFIX = "security:delete_documents:"
    SECURITY_DELETE_STICKERS_PREFIX = "security:delete_stickers:"
    SECURITY_DELETE_AUDIO_PREFIX = "security:delete_audio:"
    SECURITY_DELETE_ANIMATION_PREFIX = "security:delete_animation:"
    SECURITY_DELETE_FORWARDED_PREFIX = "security:delete_forwarded:"
    SECURITY_DELETE_POLLS_PREFIX = "security:delete_polls:"
    SECURITY_DELETE_GAMES_PREFIX = "security:delete_games:"
    SECURITY_DELETE_VOICE_PREFIX = "security:delete_voice:"
    SECURITY_DELETE_VIDEO_NOTE_PREFIX = "security:delete_video_note:"
    SECURITY_ENABLE_ALL_PREFIX = "security:enable_all:"
    SECURITY_DISABLE_ALL_PREFIX = "security:disable_all:"
    SECURITY_DELETE_PENALTY_PREFIX = "security:delete_penalty:"
    SECURITY_ANTIFLOOD_PREFIX = "security:antiflood:"
    SECURITY_MAX_LENGTH_PREFIX = "security:max_length:"
    SECURITY_WARN_SETTINGS_PREFIX = "security:warn_settings:"
    SECURITY_NIGHT_MODE_PREFIX = "security:night_mode:"
    PANEL_LOCK_PREFIX = "panel:lock:"
    PANEL_UNLOCK_PREFIX = "panel:unlock:"
    PANEL_CLOSE = "panel:close"
    CHECK_SUBSCRIBE = "check_subscribe"

# ===================================================================
# 27. حالات المستخدم
# ===================================================================
class UserState(Enum):
    NONE = auto()
    ADDING_POSTS = auto()
    WAITING_CHANNEL_ID = auto()
    WAITING_INTERVAL_MINUTES = auto()
    WAITING_INTERVAL_HOURS = auto()
    WAITING_INTERVAL_DAYS = auto()
    WAITING_DATES = auto()
    WAITING_PUBLISH_TIME = auto()
    SELECTING_DAYS = auto()
    WAITING_ADMIN_ID_ADD = auto()
    WAITING_ADMIN_ID_REMOVE = auto()
    WAITING_BROADCAST = auto()
    WAITING_UPDATE_TEXT = auto()
    WAITING_UPDATE_CHANNEL = auto()
    WAITING_FORCE_CHANNEL = auto()
    WAITING_SENDCODE_CONFIRM = auto()
    WAITING_SENDCODE_PASSWORD = auto()
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
    WAITING_2FA = auto()
    SUPPORT_MODE = auto()
    WAITING_CONTEST_TITLE = auto()
    WAITING_CONTEST_DESCRIPTION = auto()
    WAITING_CONTEST_PRIZE = auto()
    WAITING_CONTEST_END_DATE = auto()
    WAITING_CONTEST_ANSWER = auto()
    WAITING_DELETE_CONTEST = auto()
    WAITING_GROUP_SECURITY = auto()
    WAITING_HIDDEN_ADMIN_ADD = auto()
    WAITING_HIDDEN_ADMIN_REMOVE = auto()
    WAITING_AUTO_REPLY_MENU = auto()
    WAITING_NSFW_THRESHOLD = auto()
    WAITING_EXPORT_DATA = auto()
    WAITING_CRON = auto()
    WAITING_MAX_LENGTH = auto()
    WAITING_WARN_COUNT = auto()
    WAITING_SCHEDULE = auto()
    WAITING_CONFIRM = auto()

# ===================================================================
# 28. دوال الكيبوردات
# ===================================================================
def get_advanced_group_actions_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛑 حظر", callback_data=f"{CallbackData.GROUP_ACTION_BAN}:{chat_id}"),
            InlineKeyboardButton("🔇 كتم", callback_data=f"{CallbackData.GROUP_ACTION_MUTE}:{chat_id}")
        ],
        [
            InlineKeyboardButton("⚠️ تحذير", callback_data=f"{CallbackData.GROUP_ACTION_WARN}:{chat_id}"),
            InlineKeyboardButton("👢 طرد", callback_data=f"{CallbackData.GROUP_ACTION_KICK}:{chat_id}")
        ],
        [
            InlineKeyboardButton("🔒 تقييد", callback_data=f"{CallbackData.GROUP_ACTION_RESTRICT}:{chat_id}"),
            InlineKeyboardButton("📌 تثبيت", callback_data=f"{CallbackData.GROUP_ACTION_PIN}:{chat_id}")
        ],
        [
            InlineKeyboardButton("🔓 إلغاء حظر", callback_data=f"{CallbackData.GROUP_ACTION_UNBAN}:{chat_id}"),
            InlineKeyboardButton("📜 سجل الإجراءات", callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

def get_advanced_mute_duration_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱️ 5 دقائق", callback_data=f"adv_mute_duration:5:{chat_id}"),
            InlineKeyboardButton("⏱️ 30 دقيقة", callback_data=f"adv_mute_duration:30:{chat_id}")
        ],
        [
            InlineKeyboardButton("⏱️ 1 ساعة", callback_data=f"adv_mute_duration:60:{chat_id}"),
            InlineKeyboardButton("⏱️ 12 ساعة", callback_data=f"adv_mute_duration:720:{chat_id}")
        ],
        [
            InlineKeyboardButton("📆 يوم", callback_data=f"adv_mute_duration:1440:{chat_id}"),
            InlineKeyboardButton("📆 أسبوع", callback_data=f"adv_mute_duration:10080:{chat_id}")
        ],
        [
            InlineKeyboardButton("🔇 كتم دائم", callback_data=f"adv_mute_duration:0:{chat_id}"),
            InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")
        ]
    ])

def security_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 روابط", callback_data=f"security:links:{chat_id}"),
            InlineKeyboardButton("@ معرفات", callback_data=f"security:mentions:{chat_id}"),
            InlineKeyboardButton("⏱️ بطيء", callback_data=f"security:slow_mode:{chat_id}")
        ],
        [
            InlineKeyboardButton("🎯 ترحيب", callback_data=f"security:welcome_enabled:{chat_id}"),
            InlineKeyboardButton("👋 وداع", callback_data=f"security:goodbye_enabled:{chat_id}"),
            InlineKeyboardButton("🚫 كلمات", callback_data=f"{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}{chat_id}")
        ],
        [
            InlineKeyboardButton("🎬 فيديو", callback_data=f"security:delete_videos:{chat_id}"),
            InlineKeyboardButton("🎵 صوت", callback_data=f"security:delete_audio:{chat_id}"),
            InlineKeyboardButton("🎞️ متحرك", callback_data=f"security:delete_animation:{chat_id}")
        ],
        [
            InlineKeyboardButton("🛠️ خدمة", callback_data=f"security:delete_service:{chat_id}"),
            InlineKeyboardButton("📄 ملفات", callback_data=f"security:delete_documents:{chat_id}"),
            InlineKeyboardButton("🖼️ ملصقات", callback_data=f"security:delete_stickers:{chat_id}")
        ],
        [
            InlineKeyboardButton("📨 مُعاد", callback_data=f"security:delete_forwarded:{chat_id}"),
            InlineKeyboardButton("📊 استطلاع", callback_data=f"security:delete_polls:{chat_id}"),
            InlineKeyboardButton("🎮 ألعاب", callback_data=f"security:delete_games:{chat_id}")
        ],
        [
            InlineKeyboardButton("🎤 صوتي", callback_data=f"security:delete_voice:{chat_id}"),
            InlineKeyboardButton("🎥 نوت", callback_data=f"security:delete_video_note:{chat_id}"),
            InlineKeyboardButton("🌊 فيضان", callback_data=f"security:antiflood:{chat_id}")
        ],
        [
            InlineKeyboardButton("🌙 ليلي", callback_data=f"security:night_mode:{chat_id}"),
            InlineKeyboardButton("📏 طول", callback_data=f"security:max_length:{chat_id}"),
            InlineKeyboardButton("⚠️ تحذير", callback_data=f"security:warn_settings:{chat_id}")
        ],
        [
            InlineKeyboardButton("⚖️ عقوبة", callback_data=f"{CallbackData.SECURITY_DELETE_PENALTY_PREFIX}{chat_id}"),
            InlineKeyboardButton("⚡ تفعيل الكل", callback_data=f"{CallbackData.SECURITY_ENABLE_ALL_PREFIX}{chat_id}"),
            InlineKeyboardButton("⛔ تعطيل الكل", callback_data=f"{CallbackData.SECURITY_DISABLE_ALL_PREFIX}{chat_id}")
        ],
        [
            InlineKeyboardButton("⚖️ العقوبة", callback_data=f"{CallbackData.PENALTY_MENU}:{chat_id}"),
            InlineKeyboardButton("🛠️ متقدم", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}"),
            InlineKeyboardButton("📜 سجل", callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}")
        ],
        [
            InlineKeyboardButton("🔙 إغلاق", callback_data=CallbackData.SECURITY_CLOSE)
        ]
    ])

def penalty_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👢 طرد", callback_data=f"{CallbackData.PENALTY_KICK}:{chat_id}"),
            InlineKeyboardButton("🛑 حظر", callback_data=f"{CallbackData.PENALTY_BAN}:{chat_id}")
        ],
        [
            InlineKeyboardButton("🔇 كتم", callback_data=f"{CallbackData.PENALTY_MUTE}:{chat_id}"),
            InlineKeyboardButton("⚠️ تحذير", callback_data=f"penalty:warn:{chat_id}")
        ],
        [
            InlineKeyboardButton("🔒 تقييد", callback_data=f"penalty:restrict:{chat_id}"),
            InlineKeyboardButton("❌ لا شيء", callback_data=f"penalty:none:{chat_id}")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

def mute_duration_keyboard(chat_id: int, source: str = "penalty") -> InlineKeyboardMarkup:
    """لوحة اختيار مدة الكتم (موحدة)"""
    back_callback = f"{CallbackData.PENALTY_MENU}:{chat_id}" if source == "penalty" else f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱️ 5 دقائق", callback_data=f"mute_duration:5:{chat_id}"),
         InlineKeyboardButton("⏱️ 30 دقيقة", callback_data=f"mute_duration:30:{chat_id}")],
        [InlineKeyboardButton("⏱️ 1 ساعة", callback_data=f"mute_duration:60:{chat_id}"),
         InlineKeyboardButton("⏱️ 12 ساعة", callback_data=f"mute_duration:720:{chat_id}")],
        [InlineKeyboardButton("📆 يوم", callback_data=f"mute_duration:1440:{chat_id}"),
         InlineKeyboardButton("📆 أسبوع", callback_data=f"mute_duration:10080:{chat_id}")],
        [InlineKeyboardButton("🔇 كتم دائم", callback_data=f"mute_duration:-1:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=back_callback)]
    ])

def get_group_banned_words_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ إضافة كلمة", callback_data=f"{CallbackData.BANNED_WORDS_ADD_PREFIX}{chat_id}"),
            InlineKeyboardButton("📋 عرض الكلمات", callback_data=f"{CallbackData.BANNED_WORDS_LIST_PREFIX}{chat_id}")
        ],
        [
            InlineKeyboardButton("🗑️ حذف كلمة", callback_data=f"{CallbackData.BANNED_WORDS_REMOVE_PREFIX}{chat_id}"),
            InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")
        ]
    ])

def get_admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 المستخدمين", callback_data=CallbackData.ADMIN_USERS),
            InlineKeyboardButton("⛔ المحظورين", callback_data=CallbackData.ADMIN_BANNED_USERS)
        ],
        [
            InlineKeyboardButton("📡 قنوات المستخدمين", callback_data=CallbackData.ADMIN_ALL_CHANNELS),
            InlineKeyboardButton("🚫 قنوات محظورة", callback_data=CallbackData.ADMIN_BANNED_CHANNELS)
        ],
        [
            InlineKeyboardButton("👥 المجموعات", callback_data=CallbackData.ADMIN_GROUPS),
            InlineKeyboardButton("🚷 مجموعات محظورة", callback_data=CallbackData.ADMIN_BANNED_GROUPS)
        ],
        [
            InlineKeyboardButton("📢 قنوات البوت", callback_data=CallbackData.ADMIN_BOT_CHANNELS),
            InlineKeyboardButton("🚫 قنوات بوت محظورة", callback_data=CallbackData.ADMIN_BANNED_BOT_CHANNELS)
        ],
        [
            InlineKeyboardButton("❤️ تنشيط الكل", callback_data=CallbackData.ADMIN_ACTIVATE_ALL_CHANNELS),
            InlineKeyboardButton("📊 مراقبة", callback_data=CallbackData.ADMIN_MONITOR_USERS)
        ],
        [
            InlineKeyboardButton("👑 + مشرف", callback_data=CallbackData.ADMIN_ADD_ADMIN),
            InlineKeyboardButton("🗑️ - مشرف", callback_data=CallbackData.ADMIN_REMOVE_ADMIN)
        ],
        [
            InlineKeyboardButton("💬 ردود", callback_data=CallbackData.ADMIN_REPLIES),
            InlineKeyboardButton("🚫 كلمات محظورة", callback_data=CallbackData.ADMIN_BANNED_WORDS)
        ],
        [
            InlineKeyboardButton("📝 ردود تلقائية", callback_data=CallbackData.ADMIN_AUTO_REPLY)
        ],
        [
            InlineKeyboardButton("🖥️ حالة الرام", callback_data=CallbackData.ADMIN_RAM),
            InlineKeyboardButton("📊 إحصائيات", callback_data=CallbackData.ADMIN_STATS)
        ],
        [
            InlineKeyboardButton("📈 مقاييس", callback_data=CallbackData.ADMIN_METRICS)
        ],
        [
            InlineKeyboardButton("💾 نسخ احتياطي", callback_data=CallbackData.ADMIN_BACKUP),
            InlineKeyboardButton("🔄 استعادة", callback_data=CallbackData.ADMIN_RESTORE_BACKUP)
        ],
        [
            InlineKeyboardButton("⚙️ إعدادات النسخ", callback_data=CallbackData.ADMIN_BACKUP_SETTINGS),
            InlineKeyboardButton("⏱️ وقت النشر", callback_data=CallbackData.ADMIN_CHANGE_INTERVAL)
        ],
        [
            InlineKeyboardButton("📢 نشر تحديث", callback_data=CallbackData.ADMIN_SEND_UPDATE),
            InlineKeyboardButton("⚙️ قناة التحديثات", callback_data=CallbackData.ADMIN_SET_UPDATE_CHANNEL)
        ],
        [
            InlineKeyboardButton("📢 عرض القناة", callback_data=CallbackData.ADMIN_SHOW_UPDATE_CHANNEL)
        ],
        [
            InlineKeyboardButton("🔄 التحديثات", callback_data=CallbackData.ADMIN_UPDATES),
            InlineKeyboardButton("🔒 اشتراك إجباري", callback_data=CallbackData.ADMIN_FORCE_SUBSCRIBE)
        ],
        [
            InlineKeyboardButton("⚙️ تعيين القناة", callback_data=CallbackData.ADMIN_SET_FORCE_CHANNEL),
            InlineKeyboardButton("📨 إرسال رسالة", callback_data=CallbackData.ADMIN_BROADCAST)
        ],
        [
            InlineKeyboardButton("📋 تذاكر", callback_data=CallbackData.ADMIN_SUPPORT_TICKETS),
            InlineKeyboardButton("🗑️ حذف التذاكر", callback_data=CallbackData.ADMIN_DELETE_ALL_TICKETS)
        ],
        [
            InlineKeyboardButton("📁 صلاحية /sendcode", callback_data=CallbackData.ADMIN_MANAGE_SENDCODE),
            InlineKeyboardButton("📋 قناة التقارير", callback_data=CallbackData.ADMIN_SHOW_LOG_CHANNEL)
        ],
        [
            InlineKeyboardButton("📋 تعيين التقارير", callback_data=CallbackData.ADMIN_SET_LOG_CHANNEL)
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])

def get_replies_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ إضافة رد", callback_data=CallbackData.ADMIN_ADD_REPLY),
            InlineKeyboardButton("📋 عرض الردود", callback_data=CallbackData.ADMIN_LIST_REPLIES)
        ],
        [
            InlineKeyboardButton("🗑️ حذف رد", callback_data=CallbackData.ADMIN_DEL_REPLY),
            InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)
        ]
    ])

def get_banned_words_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ إضافة كلمة عامة", callback_data=CallbackData.ADMIN_ADD_BANNED_WORD),
            InlineKeyboardButton("📋 عرض الكلمات", callback_data=CallbackData.ADMIN_LIST_BANNED_WORDS)
        ],
        [
            InlineKeyboardButton("🗑️ حذف كلمة", callback_data=CallbackData.ADMIN_REMOVE_BANNED_WORD),
            InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_BANNED_WORDS)
        ]
    ])

def get_auto_reply_keyboard(chat_id: int, settings: dict) -> InlineKeyboardMarkup:
    status_text = "🟢 مفعل" if settings['enabled'] else "🔴 معطل"
    admin_text = "👑 مشرفين فقط" if settings['only_admins'] else "👥 الجميع"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"📝 الردود: {status_text}", callback_data=f"{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}{chat_id}")
        ],
        [
            InlineKeyboardButton(f"👥 المستخدمون: {admin_text}", callback_data=f"{CallbackData.AUTO_REPLY_ADMINS_PREFIX}{chat_id}")
        ],
        [
            InlineKeyboardButton("🔄 إعادة تعيين الردود", callback_data=f"{CallbackData.AUTO_REPLY_RESET_PREFIX}{chat_id}")
        ],
        [
            InlineKeyboardButton("📊 إحصائيات الردود", callback_data=f"{CallbackData.AUTO_REPLY_STATS_PREFIX}{chat_id}")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

def get_user_auto_reply_keyboard(user_id: int, enabled: bool) -> InlineKeyboardMarkup:
    status_text = "🟢 مفعل" if enabled else "🔴 معطل"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"📝 الردود التلقائية: {status_text}", callback_data=f"{CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX}{user_id}")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])

# ===================================================================
# 29. دوال إعدادات مدة العقوبة (المفقودة)
# ===================================================================

async def db_get_penalty_settings(chat_id: int) -> dict:
    """جلب إعدادات العقوبات للمجموعة"""
    async def _get(conn):
        cur = await conn.execute("""
            SELECT auto_penalty, auto_mute_duration, delete_penalty, delete_penalty_duration,
                   max_warnings, warn_penalty, antiflood_penalty, night_mode_action
            FROM group_security WHERE chat_id=?
        """, (chat_id,))
        row = await cur.fetchone()
        if row:
            return {
                'auto_penalty': row[0] or 'none',
                'auto_mute_duration': row[1] or 60,
                'delete_penalty': row[2] or 'none',
                'delete_penalty_duration': row[3] or 0,
                'max_warnings': row[4] or 3,
                'warn_penalty': row[5] or 'ban',
                'antiflood_penalty': row[6] or 'mute',
                'night_mode_action': row[7] or 'mute'
            }
        return {
            'auto_penalty': 'none',
            'auto_mute_duration': 60,
            'delete_penalty': 'none',
            'delete_penalty_duration': 0,
            'max_warnings': 3,
            'warn_penalty': 'ban',
            'antiflood_penalty': 'mute',
            'night_mode_action': 'mute'
        }
    return await execute_db(_get)

# ===================================================================
# 30. دوال إعدادات الأمان الأساسية (Security Functions)
# ===================================================================

async def db_get_security_settings(chat_id: int, force_refresh: bool = False) -> dict:
    """جلب إعدادات الأمان لمجموعة معينة"""
    async def _get(conn):
        cur = await conn.execute("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        if row:
            columns = [description[0] for description in cur.description]
            settings = dict(zip(columns, row))
            return settings
        defaults = {
            'chat_id': chat_id,
            'links': 0,
            'mentions': 0,
            'slow_mode': 0,
            'slow_mode_seconds': 5,
            'welcome_enabled': 0,
            'goodbye_enabled': 0,
            'delete_videos': 0,
            'delete_audio': 0,
            'delete_animation': 0,
            'delete_service': 0,
            'delete_documents': 0,
            'delete_stickers': 0,
            'delete_forwarded': 0,
            'delete_polls': 0,
            'delete_games': 0,
            'delete_voice': 0,
            'delete_video_note': 0,
            'antiflood_enabled': 0,
            'night_mode_enabled': 0,
            'max_message_length': 0,
            'delete_penalty': 'none',
            'delete_penalty_duration': 0,
            'antiflood_messages': 5,
            'antiflood_seconds': 10,
            'antiflood_penalty': 'mute',
            'max_warnings': 3,
            'warn_penalty': 'ban',
            'night_mode_start': '23:00',
            'night_mode_end': '06:00',
            'night_mode_action': 'mute',
            'welcome_text': 'مرحباً {user} في {chat} 🤍',
            'goodbye_text': 'وداعاً {user} 👋',
            'delete_banned_words': 0,
            'auto_penalty': 'none',
            'auto_mute_duration': 60,
        }
        columns = ', '.join(defaults.keys())
        placeholders = ', '.join(['?' for _ in defaults])
        await conn.execute(
            f"INSERT OR IGNORE INTO group_security ({columns}) VALUES ({placeholders})",
            tuple(defaults.values())
        )
        await conn.commit()
        return defaults
    return await execute_db(_get)

async def db_set_security_settings(chat_id: int, **kwargs):
    """تحديث إعدادات أمان محددة فقط للمجموعة"""
    async def _update(conn):
        await conn.execute(
            "INSERT OR IGNORE INTO group_security (chat_id) VALUES (?)",
            (chat_id,)
        )
        if kwargs:
            set_parts = [f"{key} = ?" for key in kwargs.keys()]
            set_clause = ", ".join(set_parts)
            values = list(kwargs.values()) + [chat_id]
            await conn.execute(
                f"UPDATE group_security SET {set_clause} WHERE chat_id = ?",
                tuple(values)
            )
            await conn.commit()
            logger.info(f"✅ تم تحديث: {kwargs} للمجموعة {chat_id}")
    await execute_db(_update)

def _build_security_text(settings: dict) -> str:
    """بناء نص لوحة الأمان"""
    def st(val):
        return "✅" if val else "❌"
    text = f"""🔐 إعدادات الأمان للمجموعة
━━━━━━━━━━━━━━━━━━━━━━
🔗 الروابط: {st(settings.get('links', 0))}
@ المعرفات: {st(settings.get('mentions', 0))}
⏱️ البطيء: {st(settings.get('slow_mode', 0))} ({settings.get('slow_mode_seconds', 5)}ث)
🎯 الترحيب: {st(settings.get('welcome_enabled', 0))}
👋 الوداع: {st(settings.get('goodbye_enabled', 0))}
🎬 فيديوهات: {st(settings.get('delete_videos', 0))}
🎵 صوتيات: {st(settings.get('delete_audio', 0))}
🎞️ متحركات: {st(settings.get('delete_animation', 0))}
🛠️ الخدمة: {st(settings.get('delete_service', 0))}
📄 ملفات: {st(settings.get('delete_documents', 0))}
🖼️ ملصقات: {st(settings.get('delete_stickers', 0))}
📨 المُعاد: {st(settings.get('delete_forwarded', 0))}
📊 استطلاعات: {st(settings.get('delete_polls', 0))}
🎮 ألعاب: {st(settings.get('delete_games', 0))}
🎤 صوتيات: {st(settings.get('delete_voice', 0))}
🎥 فيديو نوت: {st(settings.get('delete_video_note', 0))}
🌊 مضاد الفيضان: {st(settings.get('antiflood_enabled', 0))}
🌙 ليلي: {st(settings.get('night_mode_enabled', 0))}
📏 الطول: {settings.get('max_message_length', 0) or 'غير محدود'}
⚖️ العقوبة: {settings.get('delete_penalty', 'لا شيء')}
━━━━━━━━━━━━━━━━━━━━━━
📌 اختر الإعداد:"""
    return text

def _build_security_keyboard(chat_id: int) -> list:
    """بناء أزرار لوحة الأمان"""
    return [
        [
            InlineKeyboardButton("🔗 روابط", callback_data=f"security:links:{chat_id}"),
            InlineKeyboardButton("@ معرفات", callback_data=f"security:mentions:{chat_id}"),
            InlineKeyboardButton("⏱️ بطيء", callback_data=f"security:slow_mode:{chat_id}")
        ],
        [
            InlineKeyboardButton("🎯 ترحيب", callback_data=f"security:welcome_enabled:{chat_id}"),
            InlineKeyboardButton("👋 وداع", callback_data=f"security:goodbye_enabled:{chat_id}"),
            InlineKeyboardButton("🚫 كلمات", callback_data=f"{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}{chat_id}")
        ],
        [
            InlineKeyboardButton("🎬 فيديو", callback_data=f"security:delete_videos:{chat_id}"),
            InlineKeyboardButton("🎵 صوت", callback_data=f"security:delete_audio:{chat_id}"),
            InlineKeyboardButton("🎞️ متحرك", callback_data=f"security:delete_animation:{chat_id}")
        ],
        [
            InlineKeyboardButton("🛠️ خدمة", callback_data=f"security:delete_service:{chat_id}"),
            InlineKeyboardButton("📄 ملفات", callback_data=f"security:delete_documents:{chat_id}"),
            InlineKeyboardButton("🖼️ ملصقات", callback_data=f"security:delete_stickers:{chat_id}")
        ],
        [
            InlineKeyboardButton("📨 مُعاد", callback_data=f"security:delete_forwarded:{chat_id}"),
            InlineKeyboardButton("📊 استطلاع", callback_data=f"security:delete_polls:{chat_id}"),
            InlineKeyboardButton("🎮 ألعاب", callback_data=f"security:delete_games:{chat_id}")
        ],
        [
            InlineKeyboardButton("🎤 صوتي", callback_data=f"security:delete_voice:{chat_id}"),
            InlineKeyboardButton("🎥 نوت", callback_data=f"security:delete_video_note:{chat_id}"),
            InlineKeyboardButton("🌊 فيضان", callback_data=f"security:antiflood:{chat_id}")
        ],
        [
            InlineKeyboardButton("🌙 ليلي", callback_data=f"security:night_mode:{chat_id}"),
            InlineKeyboardButton("📏 طول", callback_data=f"security:max_length:{chat_id}"),
            InlineKeyboardButton("⚠️ تحذير", callback_data=f"security:warn_settings:{chat_id}")
        ],
        [
            InlineKeyboardButton("⚖️ عقوبة", callback_data=f"{CallbackData.SECURITY_DELETE_PENALTY_PREFIX}{chat_id}"),
            InlineKeyboardButton("⚡ تفعيل الكل", callback_data=f"{CallbackData.SECURITY_ENABLE_ALL_PREFIX}{chat_id}"),
            InlineKeyboardButton("⛔ تعطيل الكل", callback_data=f"{CallbackData.SECURITY_DISABLE_ALL_PREFIX}{chat_id}")
        ],
        [
            InlineKeyboardButton("⚖️ العقوبة", callback_data=f"{CallbackData.PENALTY_MENU}:{chat_id}"),
            InlineKeyboardButton("🛠️ متقدم", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}"),
            InlineKeyboardButton("📜 سجل", callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}")
        ],
        [
            InlineKeyboardButton("🔙 إغلاق", callback_data=CallbackData.SECURITY_CLOSE)
        ]
    ]

async def _update_security_panel(query, chat_id: int, user_id: int):
    """تحديث لوحة الأمان - حذف القديمة وإرسال جديدة"""
    try:
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        text = _build_security_text(settings)
        keyboard = _build_security_keyboard(chat_id)
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.message.delete()
        except Exception as e:
            logger.debug(f"لم نتمكن من حذف الرسالة القديمة: {e}")

        await query.message.chat.send_message(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

        logger.info(f"✅ تم تحديث لوحة الأمان للمجموعة {chat_id}")

    except Exception as e:
        logger.error(f"خطأ في _update_security_panel: {e}", exc_info=True)
        try:
            await query.answer("❌ حدث خطأ، حاول مرة أخرى", show_alert=True)
        except:
            pass
# ===================================================================
# 31. معالج المدة الموحد (mute_duration_callback) - جديد
# ===================================================================

async def mute_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج موحد لاختيار مدة الكتم"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer("❌ بيانات غير صالحة", show_alert=True)
        return
    try:
        minutes = int(parts[1])
        chat_id = int(parts[2])
    except ValueError:
        await query.answer("❌ مدة أو معرف غير صالح", show_alert=True)
        return

    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return

    # التحقق من صلاحية البوت
    bot_perms = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bot_perms.get('can_restrict', False):
        await query.answer("❌ البوت لا يملك صلاحية تقييد الأعضاء!", show_alert=True)
        return

    # حفظ المدة
    if minutes == -1:
        duration = -1
        duration_text = "دائم"
    else:
        duration = minutes
        if minutes < 60:
            duration_text = f"{minutes} دقيقة"
        elif minutes < 1440:
            duration_text = f"{minutes // 60} ساعة"
        else:
            duration_text = f"{minutes // 1440} يوم"

    await db_set_security_settings(chat_id, auto_penalty='mute', auto_mute_duration=duration if duration > 0 else 60)
    await query.answer(f"✅ تم تعيين مدة الكتم إلى: {duration_text}")

    # تحديث لوحة الأمان
    await _update_security_panel(query, chat_id, user_id)

# ===================================================================
# 32. دوال عقوبات الحذف (مع إضافة زر مدة العقوبة)
# ===================================================================

async def security_delete_penalty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('security_chat_id')
    if not chat_id or not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 طرد", callback_data=f"set_delete_penalty:kick:{chat_id}"),
         InlineKeyboardButton("🛑 حظر", callback_data=f"set_delete_penalty:ban:{chat_id}")],
        [InlineKeyboardButton("🔇 كتم", callback_data=f"set_delete_penalty:mute:{chat_id}"),
         InlineKeyboardButton("⚠️ تحذير", callback_data=f"set_delete_penalty:warn:{chat_id}")],
        [InlineKeyboardButton("⏱️ مدة العقوبة", callback_data=f"set_delete_penalty_duration:{chat_id}"),
         InlineKeyboardButton("❌ لا شيء", callback_data=f"set_delete_penalty:none:{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])
    msg = "⚖️ **اختر عقوبة الحذف التلقائي**\n\nسيتم تطبيق هذه العقوبة عند حذف رسالة مخالفة:"
    await query.edit_message_text(msg, reply_markup=keyboard)

async def set_delete_penalty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    parts = query.data.split(":") if query else context.user_data.get('delete_penalty_data', '').split(":")
    if len(parts) == 3:
        penalty = parts[1]
        chat_id = int(parts[2])
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("🔒 غير مصرح", show_alert=True)
            return
        await db_set_security_settings(chat_id, delete_penalty=penalty, delete_penalty_duration=60)
        await query.answer(f"✅ تم تعيين عقوبة الحذف إلى: {penalty}")
        await _update_security_panel(query, chat_id, user_id)

async def set_delete_penalty_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب إدخال مدة عقوبة الحذف"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    context.user_data['state'] = "WAITING_DELETE_PENALTY_DURATION"
    context.user_data['security_chat_id'] = chat_id
    await query.edit_message_text("⏱️ **أرسل مدة عقوبة الحذف بالدقائق** (مثال: 60)\nأو أرسل 0 للكتم الدائم.")

# ===================================================================
# 33. دوال إضافية: دالة إصلاح الأعمدة المفقودة
# ===================================================================

async def fix_missing_columns():
    """إصلاح الأعمدة المفقودة في قاعدة البيانات"""
    async def _fix(conn):
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1")
        except:
            pass
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN subscription_end TEXT")
        except:
            pass
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN referral_code TEXT")
        except:
            pass
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
        except:
            pass
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN last_daily_reward TEXT")
        except:
            pass
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN last_weekly_reward TEXT")
        except:
            pass
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN achievements TEXT DEFAULT '[]'")
        except:
            pass
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_levels (
                user_id INTEGER PRIMARY KEY,
                points INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1
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
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                text TEXT,
                created_by INTEGER,
                created_at TEXT,
                scheduled_for TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        await conn.commit()
        logger.info("✅ تم إصلاح الأعمدة المفقودة")
    await execute_db(_fix)

# ===================================================================
# 34. دالة إعدادات الإحالات (المفقودة)
# ===================================================================

async def db_get_referral_settings() -> dict:
    """جلب إعدادات الإحالات من قاعدة البيانات"""
    async def _get(conn):
        cur = await conn.execute("SELECT key, value FROM referral_settings")
        rows = await cur.fetchall()
        return {row[0]: row[1] for row in rows}
    return await execute_db(_get)

# ===================================================================
# 35. دوال إضافية مطلوبة لبعض الميزات
# ===================================================================

async def rebuild_banned_patterns():
    """إعادة بناء الأنماط المحظورة من الكلمات المحظورة العامة"""
    global BANNED_PATTERNS
    async with _BANNED_PATTERNS_LOCK:
        BANNED_PATTERNS = []
        try:
            async def _get_patterns(conn):
                cur = await conn.execute("SELECT word FROM banned_words WHERE chat_id = -1")
                rows = await cur.fetchall()
                return [row[0] for row in rows]
            words = await execute_db(_get_patterns)
            for word in words:
                if '*' in word or '?' in word or '+' in word:
                    try:
                        BANNED_PATTERNS.append(re.compile(word))
                    except:
                        pass
            logger.info(f"✅ تم إعادة بناء {len(BANNED_PATTERNS)} نمط محظور")
        except Exception as e:
            logger.error(f"❌ فشل إعادة بناء الأنماط المحظورة: {e}")

async def log_security_event(event_type: str, chat_id: int, user_id: int, details: dict = None, severity: str = "info"):
    """تسجيل حدث أمني في قاعدة البيانات وسجلات النص"""
    async def _log(conn):
        await conn.execute(
            "INSERT INTO security_events (event_type, chat_id, user_id, details, severity, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (event_type, chat_id, user_id, json.dumps(details) if details else None, severity, utc_now_iso())
        )
        await conn.commit()
    await execute_db(_log)
    advanced_logger.log_security(event_type, user_id, details, severity.upper())

async def achievement_system(user_id: int, achievement: str):
    """منح إنجاز للمستخدم (تطبيق بسيط)"""
    async def _update(conn):
        cur = await conn.execute("SELECT achievements FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        achievements = json.loads(row[0]) if row and row[0] else []
        if achievement not in achievements:
            achievements.append(achievement)
            await conn.execute("UPDATE users SET achievements=? WHERE user_id=?", (json.dumps(achievements), user_id))
            await conn.commit()
    await execute_db(_update)

async def db_get_active_contests_with_participants(limit: int = 10) -> list:
    """جلب المسابقات النشطة مع عدد المشاركين لكل منها"""
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        now = utc_now().isoformat()
        cur = await conn.execute("""
            SELECT c.id, c.title, c.description, c.prize, c.end_date, c.contest_type,
                   COALESCE((SELECT COUNT(*) FROM contest_participants cp WHERE cp.contest_id = c.id), 0) as participants
            FROM contests c
            WHERE c.status = 'active' AND c.end_date > ?
            ORDER BY c.end_date ASC LIMIT ?
        """, (now, limit))
        rows = await cur.fetchall()
        result = []
        for row in rows:
            result.append((
                row['id'],
                row['title'],
                row['description'],
                row['prize'],
                row['end_date'],
                row['participants'],
                row['contest_type'] if 'contest_type' in row.keys() else 'raffle'
            ))
        return result
    return await execute_db(_get)

async def db_get_user_participation(user_id: int, contest_id: int) -> dict | None:
    """جلب بيانات مشاركة المستخدم في مسابقة معينة"""
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT id, answer, joined_at FROM contest_participants WHERE user_id = ? AND contest_id = ?",
            (user_id, contest_id)
        )
        row = await cur.fetchone()
        if row:
            return {'id': row['id'], 'answer': row['answer'], 'joined_at': row['joined_at']}
        return None
    return await execute_db(_get)

# ===================================================================
# 36. معالج الكولباك للأوامر النصية
# ===================================================================

async def handle_text_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج للكولباك التي تأتي من أزرار نصية (بدون بيانات إضافية)"""
    query = update.callback_query
    if query:
        await query.answer()
    data = query.data
    if data == "rank":
        await rank_command_handler(update, context)
    elif data == "top":
        await top_command_handler(update, context)
    elif data == "schedule_post":
        await schedule_command_handler(update, context)
    elif data == "language":
        await language_command_handler(update, context)
    else:
        await query.edit_message_text("❌ إجراء غير معروف")

# ===================================================================
# 37. دوال إضافية - معالجات الأحداث والفلترة
# ===================================================================

async def global_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        error = context.error
        error_id = advanced_logger.log_error("خطأ في تحديث", error, {
            'user_id': update.effective_user.id if update and update.effective_user else None,
            'chat_id': update.effective_chat.id if update and update.effective_chat else None,
            'message': update.effective_message.text if update and update.effective_message else None
        })
        if isinstance(error, Conflict):
            logger.warning(f"⚠️ تعارض في التحديثات (Conflict): {error}")
            return
        if isinstance(error, Forbidden):
            logger.warning(f"⚠️ البوت محظور أو ليس لديه صلاحيات: {error}")
            if update and update.effective_chat:
                try:
                    await safe_send_markdown(context.bot, PRIMARY_OWNER_ID, f"⚠️ **البوت محظور أو ليس لديه صلاحيات في:**\n{update.effective_chat.title}\nID: `{update.effective_chat.id}`")
                except:
                    pass
            return
        if isinstance(error, TimedOut):
            logger.warning(f"⏱️ انتهت المهلة: {error}")
            return
        if update and update.effective_user and context and context.bot:
            if not await is_user_bot(context.bot, update.effective_user.id):
                await safe_send_markdown(context.bot, update.effective_user.id, f"❌ حدث خطأ:\n`{str(error)[:300]}`\n(الرمز: `{error_id}`)")
        if PRIMARY_OWNER_ID and context and context.bot:
            try:
                error_text = f"🚨 **خطأ في البوت** (الرمز: {error_id})\n\n📌 المستخدم: {update.effective_user.id if update and update.effective_user else 'غير معروف'}\n⚠️ الخطأ: `{str(error)[:300]}`\n"
                if update and update.effective_message and update.effective_message.text:
                    error_text += f"📝 الرسالة: `{update.effective_message.text[:100]}`\n"
                await safe_send_markdown(context.bot, PRIMARY_OWNER_ID, error_text)
            except Exception as e:
                logger.error(f"فشل إرسال إشعار الخطأ للمطور: {e}")
    except Exception as e:
        logger.error(f"فشل معالج الأخطاء نفسه: {e}")

async def is_chat_locked(chat_id: int) -> bool:
    async def _check(conn):
        try:
            cur = await conn.execute("SELECT 1 FROM chat_locks WHERE chat_id=? AND locked=1", (chat_id,))
            return await cur.fetchone() is not None
        except Exception as e:
            logger.error(f"خطأ في التحقق من قفل المجموعة {chat_id}: {e}")
            return False
    return await execute_db(_check)

async def db_set_chat_lock(chat_id: int, locked: bool, locked_by: int = None) -> bool:
    if not isinstance(chat_id, int) or chat_id <= 0:
        return False
    async def _set(conn):
        try:
            if locked:
                await conn.execute(
                    "INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?, 1, ?, ?)",
                    (chat_id, utc_now_iso(), locked_by)
                )
            else:
                await conn.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في قفل المجموعة {chat_id}: {e}")
            return False
    return await execute_db(_set)

async def get_moderation_log(chat_id: int, limit: int = 20) -> str:
    async def _get_log(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT user_id, action, duration_minutes, reason, created_at FROM moderation_log WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?", (chat_id, limit))
        return await cur.fetchall()
    logs = await execute_db(_get_log)
    if not logs:
        return "📭 لا توجد سجلات إجراءات"
    text = "📜 **سجل إجراءات المجموعة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for log in logs:
        user_id = log['user_id']
        action = log['action']
        duration = log['duration_minutes']
        reason = log['reason']
        created_at = log['created_at']
        try:
            dt = datetime.fromisoformat(created_at)
            dt_mecca = utc_to_mecca(dt)
            time_str = dt_mecca.strftime("%Y-%m-%d %H:%M")
        except:
            time_str = created_at[:16] if created_at else "?"
        duration_text = ""
        if action == 'mute' and duration:
            if duration == -1:
                duration_text = " (دائم)"
            elif duration < 60:
                duration_text = f" ({duration} دقيقة)"
            elif duration < 1440:
                duration_text = f" ({duration//60} ساعة)"
            else:
                duration_text = f" ({duration//1440} يوم)"
        elif action == 'warn' and duration:
            duration_text = f" (تحذير #{duration})"
        reason_text = f"\n   📝 السبب: {reason[:50]}" if reason else ""
        text += f"• `{user_id}` → {action}{duration_text}{reason_text}\n   🕐 {time_str}\n\n"
    return text

async def delete_and_penalize(update: Update, context: ContextTypes.DEFAULT_TYPE, warning_message: str):
    if not update.message:
        return
    message = update.message
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"فشل حذف الرسالة: {e}")
    try:
        await safe_send_markdown(context.bot, chat_id, warning_message)
    except:
        pass
    settings = await db_get_security_settings(chat_id)
    penalty = settings.get('auto_penalty', 'none')
    if penalty != 'none':
        duration = settings.get('auto_mute_duration', 60)
        await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, duration, reason="مخالفة قواعد المجموعة")

# ===================================================================
# 38. دوال القائمة الرئيسية والكيبوردات
# ===================================================================

async def get_main_keyboard(user_id: int):
    channels = await db_get_channels(user_id)
    active = await db_get_active_channel(user_id)
    cnt = 0
    ch_display = get_text(user_id, 'no_channels')
    if active is not None:
        try:
            cnt = await db_unpublished_count(active)
            ch_info = await db_get_channel_info(active)
            if ch_info and len(ch_info) >= 2:
                ch_tele_id = ch_info[0] if ch_info[0] is not None else "unknown"
                ch_name = ch_info[1] if ch_info[1] is not None else ch_tele_id
                ch_display = f"{ch_name} ({ch_tele_id})"
        except:
            ch_display = get_text(user_id, 'no_channels')
    my_groups = 0
    try:
        my_groups = await db_get_user_groups_count(user_id)
    except:
        my_groups = 0
    has_sub = False
    try:
        has_sub = await db_has_active_subscription(user_id)
    except:
        has_sub = False
    sub_text = get_text(user_id, 'subscribed') if has_sub else get_text(user_id, 'not_subscribed')
    auto_status = False
    try:
        auto_status = await db_auto_status(user_id)
    except:
        auto_status = False
    auto_text = get_text(user_id, 'auto_on') if auto_status else get_text(user_id, 'auto_off')
    title = get_text(user_id, 'main_title').format(BOT_NAME, user_id, my_groups, sub_text, ch_display, cnt, auto_status)

    updates_channel = None
    try:
        updates_channel = await db_get_updates_channel()
    except:
        updates_channel = None
    updates_url = f"https://t.me/{updates_channel}" if updates_channel else None

    keyboard = []

    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'my_groups_btn'), callback_data=CallbackData.GROUPS_MY),
        InlineKeyboardButton(get_text(user_id, 'add_channel'), callback_data=CallbackData.CHANNELS_ADD)
    ])

    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'my_channels'), callback_data=CallbackData.CHANNELS_MY),
        InlineKeyboardButton(get_text(user_id, 'settings_btn'), callback_data=CallbackData.SETTINGS_MENU)
    ])

    if channels:
        keyboard.append([
            InlineKeyboardButton(get_text(user_id, 'add_15_posts'), callback_data=CallbackData.POSTS_ADD_15),
            InlineKeyboardButton(get_text(user_id, 'publish_one'), callback_data=CallbackData.POSTS_PUBLISH_ONE)
        ])
        keyboard.append([
            InlineKeyboardButton(get_text(user_id, 'my_posts_btn'), callback_data=CallbackData.POSTS_MY),
            InlineKeyboardButton(get_text(user_id, 'recycle'), callback_data=CallbackData.POSTS_RECYCLE)
        ])
        keyboard.append([
            InlineKeyboardButton(f"{get_text(user_id, 'stats_btn')} ({cnt})", callback_data=CallbackData.STATS_PENDING),
            InlineKeyboardButton(get_text(user_id, 'my_stats_btn'), callback_data=CallbackData.STATS_FULL)
        ])
        if active is not None:
            keyboard.append([
                InlineKeyboardButton(get_text(user_id, 'schedule_btn'), callback_data=f"{CallbackData.SCHEDULE_MENU_PREFIX}{active}"),
                InlineKeyboardButton(get_text(user_id, 'channel_stats'), callback_data=f"{CallbackData.CHANNEL_STATS}:{active}")
            ])
        keyboard.append([
            InlineKeyboardButton(get_text(user_id, 'my_channels_summary'), callback_data=CallbackData.MY_CHANNEL_STATS),
            InlineKeyboardButton(get_text(user_id, 'my_rank_btn'), callback_data="rank")
        ])
        keyboard.append([
            InlineKeyboardButton(get_text(user_id, 'top_10_btn'), callback_data="top"),
            InlineKeyboardButton(get_text(user_id, 'schedule_post_btn'), callback_data="schedule_post")
        ])
        keyboard.append([
            InlineKeyboardButton(get_text(user_id, 'publish_all'), callback_data=CallbackData.PUBLISH_ALL_CHANNELS)
        ])

    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'help_btn'), callback_data=CallbackData.HELP),
        InlineKeyboardButton(get_text(user_id, 'trial_btn'), callback_data=CallbackData.TRIAL)
    ])
    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'subscribe_btn'), callback_data=CallbackData.SUBSCRIBE_MENU),
        InlineKeyboardButton(get_text(user_id, 'developer_btn'), callback_data=CallbackData.DEVELOPER)
    ])

    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'language_btn'), callback_data="language"),
        InlineKeyboardButton(get_text(user_id, 'support_btn'), callback_data=CallbackData.SUPPORT_MENU)
    ])
    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'referral'), callback_data=CallbackData.REFERRAL_MENU),
        InlineKeyboardButton(get_text(user_id, 'reminder_settings'), callback_data=CallbackData.REMINDER_MENU)
    ])
    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'translation_settings'), callback_data=CallbackData.TRANSLATION_MENU),
        InlineKeyboardButton(get_text(user_id, 'contests_menu'), callback_data=CallbackData.CONTESTS_MENU)
    ])

    if updates_url:
        keyboard.append([
            InlineKeyboardButton(get_text(user_id, 'updates_btn'), callback_data=CallbackData.UPDATES)
        ])

    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'add_to_group'), url=f"https://t.me/{BOT_USERNAME}?startgroup")
    ])

    is_admin = False
    try:
        is_admin = (user_id == PRIMARY_OWNER_ID) or (await is_bot_admin(user_id))
    except:
        is_admin = False
    if is_admin:
        keyboard.append([
            InlineKeyboardButton(get_text(user_id, 'admin_panel'), callback_data=CallbackData.ADMIN_PANEL)
        ])

    valid_keyboard = []
    for row in keyboard:
        if row and all(isinstance(btn, InlineKeyboardButton) for btn in row):
            valid_keyboard.append(row)
    if not valid_keyboard:
        valid_keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])

    return InlineKeyboardMarkup(valid_keyboard), title, active

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    kb, title, active = await get_main_keyboard(user_id)
    if active:
        context.user_data['active_channel'] = active
    if query:
        await safe_edit_markdown(query, title, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, title, reply_markup=kb)

async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu_callback(update, context)

# ===================================================================
# 39. دوال القنوات والإحصائيات
# ===================================================================

async def db_get_channel_stats(channel_db_id: int) -> dict:
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT COUNT(*) as total_posts,
                   SUM(CASE WHEN published = 1 THEN 1 ELSE 0 END) as published_posts,
                   SUM(CASE WHEN published = 0 THEN 1 ELSE 0 END) as unpublished_posts,
                   SUM(COALESCE(views_count, 0)) as total_views,
                   AVG(COALESCE(views_count, 0)) as avg_views,
                   MAX(created_at) as last_post_time,
                   MIN(created_at) as first_post_time
            FROM posts
            WHERE channel_db_id = ?
        """, (channel_db_id,))
        row = await cur.fetchone()
        if not row or row['total_posts'] == 0:
            return {
                'total_posts': 0, 'published_posts': 0, 'unpublished_posts': 0,
                'total_views': 0, 'avg_views': 0, 'last_post_time': None, 'first_post_time': None,
                'avg_time_between_posts': 0, 'best_publish_hour': 0
            }
        avg_time = 0
        best_hour = 0
        try:
            cur2 = await conn.execute("""
                SELECT created_at FROM posts WHERE channel_db_id = ? AND published = 1 ORDER BY created_at
            """, (channel_db_id,))
            times = await cur2.fetchall()
            if len(times) >= 2:
                total_seconds = 0
                for i in range(1, len(times)):
                    prev = datetime.fromisoformat(times[i-1]['created_at'])
                    curr = datetime.fromisoformat(times[i]['created_at'])
                    total_seconds += (curr - prev).total_seconds()
                avg_seconds = total_seconds / (len(times) - 1)
                avg_time = round(avg_seconds / 3600, 2)
            cur3 = await conn.execute("""
                SELECT strftime('%H', created_at) as hour, COUNT(*) as count
                FROM posts WHERE channel_db_id = ? AND published = 1
                GROUP BY hour ORDER BY count DESC LIMIT 1
            """, (channel_db_id,))
            hour_row = await cur3.fetchone()
            best_hour = int(hour_row['hour']) if hour_row else 0
        except:
            pass
        return {
            'total_posts': row['total_posts'] or 0,
            'published_posts': row['published_posts'] or 0,
            'unpublished_posts': row['unpublished_posts'] or 0,
            'total_views': row['total_views'] or 0,
            'avg_views': round(row['avg_views'] or 0, 2),
            'last_post_time': row['last_post_time'],
            'first_post_time': row['first_post_time'],
            'avg_time_between_posts': avg_time,
            'best_publish_hour': best_hour
        }
    return await execute_db(_get)

async def db_get_channel_growth(channel_db_id: int, days: int = 30) -> dict:
    async def _get_growth(conn):
        conn.row_factory = aiosqlite.Row
        start_date = (utc_now() - timedelta(days=days)).isoformat()
        cur = await conn.execute("""
            SELECT date(created_at) as post_date,
                   COUNT(*) as count,
                   SUM(COALESCE(views_count, 0)) as views
            FROM posts
            WHERE channel_db_id = ? AND created_at >= ?
            GROUP BY date(created_at)
            ORDER BY post_date
        """, (channel_db_id, start_date))
        rows = await cur.fetchall()
        dates = []
        counts = []
        views = []
        for row in rows:
            dates.append(row['post_date'])
            counts.append(row['count'] or 0)
            views.append(row['views'] or 0)
        return {
            'dates': dates,
            'counts': counts,
            'views': views,
            'total_days': len(dates),
            'total_posts': sum(counts),
            'total_views': sum(views)
        }
    return await execute_db(_get_growth)

async def db_get_channel_stats_summary(user_id: int) -> dict:
    async def _get_summary(conn):
        channels = await db_get_channels(user_id)
        if not channels:
            return None
        total_posts = 0
        total_published = 0
        total_views = 0
        total_channels = len(channels)
        best_channel = None
        best_channel_views = 0
        active_channels = 0
        for ch_db_id, ch_tele_id, ch_name, banned in channels:
            if not banned:
                active_channels += 1
            stats = await db_get_user_channel_stats(user_id, ch_db_id)
            if stats and stats['total_posts'] > 0:
                total_posts += stats['total_posts']
                total_published += stats['published_posts']
                total_views += stats['total_views']
                if stats['total_views'] > best_channel_views:
                    best_channel_views = stats['total_views']
                    best_channel = {
                        'name': ch_name,
                        'views': stats['total_views'],
                        'posts': stats['published_posts'],
                        'avg_views': stats['avg_views']
                    }
        return {
            'total_channels': total_channels,
            'active_channels': active_channels,
            'total_posts': total_posts,
            'total_published': total_published,
            'total_views': total_views,
            'avg_views_per_channel': round(total_views / total_channels, 2) if total_channels > 0 else 0,
            'best_channel': best_channel
        }
    return await execute_db(_get_summary)

async def db_get_user_channel_stats(user_id: int, channel_db_id: int) -> dict:
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT COUNT(*) as total_posts,
                   SUM(CASE WHEN published = 1 THEN 1 ELSE 0 END) as published_posts,
                   SUM(CASE WHEN published = 0 THEN 1 ELSE 0 END) as unpublished_posts,
                   SUM(COALESCE(views_count, 0)) as total_views,
                   AVG(COALESCE(views_count, 0)) as avg_views,
                   MAX(created_at) as last_post_time,
                   MIN(created_at) as first_post_time
            FROM posts
            WHERE channel_db_id = ?
        """, (channel_db_id,))
        row = await cur.fetchone()
        if not row or row['total_posts'] == 0:
            return {
                'total_posts': 0, 'published_posts': 0, 'unpublished_posts': 0,
                'total_views': 0, 'avg_views': 0, 'last_post_time': None, 'first_post_time': None
            }
        return {
            'total_posts': row['total_posts'] or 0,
            'published_posts': row['published_posts'] or 0,
            'unpublished_posts': row['unpublished_posts'] or 0,
            'total_views': row['total_views'] or 0,
            'avg_views': round(row['avg_views'] or 0, 2),
            'last_post_time': row['last_post_time'],
            'first_post_time': row['first_post_time']
        }
    return await execute_db(_get)

# ===================================================================
# 40. دوال الاشتراك الإجباري والتأكد
# ===================================================================

async def ensure_force_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id=None) -> bool:
    if user_id is None:
        if update.effective_user is None:
            return True
        user_id = update.effective_user.id
    if user_id == PRIMARY_OWNER_ID or await is_bot_admin(user_id):
        return True
    if not await db_get_force_subscribe_status():
        return True
    channel = await db_get_force_subscribe_channel()
    if not channel:
        return True
    if await is_user_subscribed(context.bot, user_id, channel):
        return True
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{channel.lstrip('@')}"),
         InlineKeyboardButton("🔄 تأكد من الاشتراك", callback_data=CallbackData.CHECK_SUBSCRIBE)],
        [InlineKeyboardButton("❌ إلغاء", callback_data=CallbackData.BACK)]
    ])
    msg = f"🔒 **اشتراك إجباري**\n\nيجب عليك الاشتراك في قناتنا أولاً:\n👉 @{channel.lstrip('@')}\n\nبعد الاشتراك، اضغط على زر التحقق."
    try:
        if update.callback_query:
            if update.callback_query.message.text == msg:
                return False
            await safe_edit_markdown(update.callback_query, msg, reply_markup=keyboard)
        elif update.message:
            await safe_send_markdown(context.bot, user_id, msg, reply_markup=keyboard)
    except Exception:
        pass
    return False

async def is_user_subscribed(bot, user_id, channel):
    if not channel:
        return True
    channel = channel.lstrip('@')
    try:
        member = await bot.get_chat_member(f"@{channel}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

async def check_subscribe_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    enabled = await db_get_force_subscribe_status()
    channel = await db_get_force_subscribe_channel()
    if enabled and channel:
        if await is_user_subscribed(context.bot, uid, channel):
            if query:
                await safe_edit_markdown(query, "✅ تم التحقق! أنت مشترك الآن.")
            else:
                await safe_send_markdown(context.bot, uid, "✅ تم التحقق! أنت مشترك الآن.")
            await main_menu_callback(update, context)
        else:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 اشترك", url=f"https://t.me/{channel.lstrip('@')}"),
                 InlineKeyboardButton("🔄 تأكد", callback_data=CallbackData.CHECK_SUBSCRIBE),
                 InlineKeyboardButton(get_text(uid, 'back'), callback_data=CallbackData.BACK)]
            ])
            if query:
                await safe_edit_markdown(query, f"❌ لم تشترك في @{channel.lstrip('@')}", reply_markup=kb)
            else:
                await safe_send_markdown(context.bot, uid, f"❌ لم تشترك في @{channel.lstrip('@')}", reply_markup=kb)
    else:
        if query:
            await safe_edit_markdown(query, "⚠️ الاشتراك الإجباري غير مفعل")
        else:
            await safe_send_markdown(context.bot, uid, "⚠️ الاشتراك الإجباري غير مفعل")

# ===================================================================
# 41. دوال اللوحة الرئيسية ومعالجات الكولباك الأساسية
# ===================================================================

async def channel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":") if query else context.user_data.get('channel_stats_data', '').split(":")
    ch_db_id = int(parts[1]) if len(parts) >= 2 else context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not ch_db_id:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    stats = await db_get_channel_stats(ch_db_id)
    ch_info = await db_get_channel_info(ch_db_id)
    channel_name = ch_info[1] if ch_info and len(ch_info) >= 2 else "القناة"
    text = f"📊 **إحصائيات {channel_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📝 إجمالي المنشورات: {stats['total_posts']}\n"
    text += f"✅ المنشورة: {stats['published_posts']}\n"
    text += f"⏳ غير المنشورة: {stats['unpublished_posts']}\n"
    text += f"👁️ إجمالي المشاهدات: {stats['total_views']}\n"
    text += f"📊 متوسط المشاهدات: {stats['avg_views']}\n"
    text += f"🕐 آخر منشور: {stats['last_post_time'][:16] if stats['last_post_time'] else 'لا يوجد'}\n"
    text += f"📅 أول منشور: {stats['first_post_time'][:16] if stats['first_post_time'] else 'لا يوجد'}\n"
    text += f"⏱️ متوسط الوقت بين المنشورات: {stats['avg_time_between_posts']} ساعة\n"
    text += f"🕐 أفضل وقت للنشر: {stats['best_publish_hour']}:00\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 النمو", callback_data=f"{CallbackData.CHANNEL_GROWTH}:{ch_db_id}"),
         InlineKeyboardButton("🔄 تحديث", callback_data=f"{CallbackData.CHANNEL_STATS_REFRESH}:{ch_db_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def channel_growth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":") if query else context.user_data.get('channel_growth_data', '').split(":")
    ch_db_id = int(parts[1]) if len(parts) >= 2 else context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not ch_db_id:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    growth = await db_get_channel_growth(ch_db_id, days=30)
    ch_info = await db_get_channel_info(ch_db_id)
    channel_name = ch_info[1] if ch_info and len(ch_info) >= 2 else "القناة"
    text = f"📈 **نمو {channel_name} (آخر 30 يوم)**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📝 إجمالي المنشورات: {growth['total_posts']}\n"
    text += f"👁️ إجمالي المشاهدات: {growth['total_views']}\n"
    text += f"📅 عدد الأيام النشطة: {growth['total_days']}\n"
    text += f"📊 المتوسط اليومي: {growth['total_posts'] // max(1, growth['total_days'])} منشور\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات", callback_data=f"{CallbackData.CHANNEL_STATS}:{ch_db_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def channel_stats_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await channel_stats_callback(update, context)

async def my_channel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    summary = await db_get_channel_stats_summary(user_id)
    if not summary:
        if query:
            await query.edit_message_text("📭 لا توجد قنوات مسجلة.")
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد قنوات مسجلة.")
        return
    text = f"📊 **ملخص قنواتي**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📡 إجمالي القنوات: {summary['total_channels']}\n"
    text += f"🟢 النشطة: {summary['active_channels']}\n"
    text += f"📝 إجمالي المنشورات: {summary['total_posts']}\n"
    text += f"✅ المنشورة: {summary['total_published']}\n"
    text += f"👁️ إجمالي المشاهدات: {summary['total_views']}\n"
    text += f"📊 متوسط المشاهدات لكل قناة: {summary['avg_views_per_channel']}\n"
    if summary['best_channel']:
        text += f"\n🏆 **أفضل قناة:**\n"
        text += f"📌 {summary['best_channel']['name']}\n"
        text += f"👁️ مشاهدات: {summary['best_channel']['views']}\n"
        text += f"📝 منشورات: {summary['best_channel']['posts']}\n"
        text += f"📊 متوسط المشاهدات: {summary['best_channel']['avg_views']}\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def add_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_CHANNEL_ID
    msg = get_text(user_id, 'send_channel_id')
    if query:
        await query.edit_message_text(msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

async def my_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels:
        msg = get_text(user_id, 'no_channels_list')
        if query:
            await query.edit_message_text(msg)
        else:
            await safe_send_markdown(context.bot, user_id, msg)
        return
    kb = []
    for ch in channels:
        ch_db_id, ch_tele_id, ch_name, banned = ch
        display = ch_name if ch_name != ch_tele_id else ch_tele_id
        kb.append([
            InlineKeyboardButton(f"📢 {display}", callback_data=f"{CallbackData.CHANNELS_SELECT_PREFIX}{ch_db_id}"),
            InlineKeyboardButton(get_text(user_id, 'channel_stats'), callback_data=f"{CallbackData.CHANNEL_STATS}:{ch_db_id}"),
            InlineKeyboardButton(get_text(user_id, 'delete_channel'), callback_data=f"{CallbackData.CHANNELS_DELETE_PREFIX}{ch_db_id}")
        ])
    kb.append([InlineKeyboardButton(get_text(user_id, 'add_channel'), callback_data=CallbackData.CHANNELS_ADD)])
    kb.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)])
    if query:
        await query.edit_message_text(get_text(user_id, 'channels_list'), reply_markup=InlineKeyboardMarkup(kb))
    else:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'channels_list'), reply_markup=InlineKeyboardMarkup(kb))

async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1]) if query else context.user_data.get('delete_channel_id')
    if not ch_db_id:
        return
    if await db_delete_channel_by_id(user_id, ch_db_id):
        if query:
            await query.edit_message_text(get_text(user_id, 'channel_deleted'))
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'channel_deleted'))
        await my_channels_callback(update, context)
    else:
        if query:
            await query.answer(get_text(user_id, 'delete_failed'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'delete_failed'))

async def select_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    await db_set_active_channel(user_id, ch_db_id)
    context.user_data['active_channel'] = ch_db_id
    await main_menu_callback(update, context)

async def add_15_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
        await query.edit_message_text("⚠️ اشتراكك منتهٍ، استخدم /trial أو /subscribe")
        return
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    unpublished_count = await db_unpublished_count(active)
    if unpublished_count >= MAX_UNPUBLISHED_POSTS:
        if query:
            await query.edit_message_text(f"⚠️ لقد تجاوزت الحد الأقصى للمنشورات غير المنشورة ({MAX_UNPUBLISHED_POSTS}).\nقم بنشر بعض المنشورات أولاً.")
        else:
            await safe_send_markdown(context.bot, user_id, f"⚠️ لقد تجاوزت الحد الأقصى للمنشورات غير المنشورة ({MAX_UNPUBLISHED_POSTS}).\nقم بنشر بعض المنشورات أولاً.")
        return
    context.user_data[f"session_{user_id}"] = []
    context.user_data[f"session_target_{user_id}"] = min(15, MAX_UNPUBLISHED_POSTS - unpublished_count)
    context.user_data['state'] = UserState.ADDING_POSTS
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=CallbackData.CANCEL_SESSION)]])
    msg = f"📥 أرسل المنشورات (نصوص أو صور أو فيديوهات أو مستندات)\nالحد الأقصى المسموح: {MAX_UNPUBLISHED_POSTS - unpublished_count} منشور"
    if query:
        await query.edit_message_text(msg, reply_markup=cancel_kb)
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=cancel_kb)

async def publish_one_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
        await query.edit_message_text("⚠️ اشتراكك منتهٍ، استخدم /trial أو /subscribe")
        return
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    post = await db_get_next_post(active)
    if not post:
        if query:
            await query.edit_message_text(get_text(user_id, 'no_posts'))
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'no_posts'))
        return
    ch_info = await db_get_channel_info(active)
    translation_lang = await get_user_translation_language(user_id)
    final_text = post['text']
    if translation_lang != 'off' and final_text:
        try:
            translated = await translate_text(final_text, translation_lang)
            if translated and translated != final_text:
                final_text = f"{final_text}\n\n🌐 {translated}"
        except:
            pass
    try:
        if post['media_type'] == 'photo' and post['media_file_id']:
            await context.bot.send_photo(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'video' and post['media_file_id']:
            await context.bot.send_video(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'document' and post['media_file_id']:
            await context.bot.send_document(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'audio' and post['media_file_id']:
            await context.bot.send_audio(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'voice' and post['media_file_id']:
            await context.bot.send_voice(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'animation' and post['media_file_id']:
            await context.bot.send_animation(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        else:
            await context.bot.send_message(ch_info[0], final_text, parse_mode=None)
        await db_mark_published(post['id'])
        await db_set_last_publish(active, utc_now())
        await db_update_next_publish_date(active)
        if query:
            await query.edit_message_text("✅ تم نشر المنشور بنجاح!")
        else:
            await safe_send_markdown(context.bot, user_id, "✅ تم نشر المنشور بنجاح!")
    except Exception as e:
        error_id = log_error(e, {'user_id': user_id, 'action': 'publish_one'})
        if query:
            await query.edit_message_text(f"❌ فشل النشر (الرمز: `{error_id}`)")
        else:
            await safe_send_markdown(context.bot, user_id, f"❌ فشل النشر (الرمز: `{error_id}`)")
    await main_menu_callback(update, context)

async def my_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    posts = await db_get_user_posts_for_channel(active, limit=15)
    if not posts:
        if query:
            await query.edit_message_text(get_text(user_id, 'no_posts'))
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'no_posts'))
        return
    msg = get_text(user_id, 'my_posts_title') + "\n"
    kb_buttons = []
    for idx, (pid, ptext, media_type) in enumerate(posts[:10], 1):
        short = re.sub('<[^>]+>', '', ptext)[:80]
        media_icon = "🖼️" if media_type == 'photo' else "🎬" if media_type == 'video' else "📝" if media_type == 'text' else "📄"
        msg += f"{idx}. {media_icon} {short}...\n🆔 {pid}\n\n"
        kb_buttons.append([InlineKeyboardButton(f"🗑️ حذف #{pid}", callback_data=f"{CallbackData.POSTS_DELETE_SINGLE_PREFIX}{pid}_{active}")])
    kb_buttons.append([InlineKeyboardButton("🗑️ حذف الكل", callback_data=f"{CallbackData.POSTS_CONFIRM_CLEAR_ALL_PREFIX}{active}")])
    kb_buttons.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)])
    if query:
        await safe_edit_markdown(query, msg, reply_markup=InlineKeyboardMarkup(kb_buttons))
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=InlineKeyboardMarkup(kb_buttons))

async def delete_single_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")[-1].split("_") if query else context.user_data.get('delete_post_data', '').split("_")
    if len(parts) >= 2:
        post_id = int(parts[0])
        active = int(parts[1])
        if await db_delete_single_post(post_id, user_id, active):
            if query:
                await query.answer("✅ تم حذف المنشور", show_alert=True)
            else:
                await safe_send_markdown(context.bot, user_id, "✅ تم حذف المنشور")
            await my_posts_callback(update, context)
        else:
            if query:
                await query.answer("❌ فشل الحذف", show_alert=True)
            else:
                await safe_send_markdown(context.bot, user_id, "❌ فشل الحذف")

async def confirm_clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = int(query.data.split(":")[-1]) if query else context.user_data.get('clear_all_posts_id')
    if not active:
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم", callback_data=f"{CallbackData.POSTS_CLEAR_ALL_PREFIX}{active}"),
         InlineKeyboardButton("❌ لا", callback_data=CallbackData.BACK)]
    ])
    if query:
        await query.edit_message_text(get_text(user_id, 'confirm_delete'), reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'confirm_delete'), reply_markup=kb)

async def clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = int(query.data.split(":")[-1]) if query else context.user_data.get('clear_all_posts_id')
    if not active:
        return
    async def _clear_posts(conn):
        await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (active,))
        await conn.commit()
    await execute_db(_clear_posts)
    if query:
        await query.answer(get_text(user_id, 'deleted_all'), show_alert=True)
    else:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'deleted_all'))
    await main_menu_callback(update, context)

async def recycle_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if active:
        await db_reset_posts_to_unpublished(active, user_id)
        if query:
            await query.edit_message_text(get_text(user_id, 'recycled'))
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'recycled'))
    else:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
    await main_menu_callback(update, context)

async def pending_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    unpublished = await db_get_user_unpublished_posts(user_id)
    total = await db_get_user_total_posts(user_id)
    text = get_text(user_id, 'pending_stats').format(unpublished, total)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def full_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    channels = await db_get_user_channels_count(user_id)
    total = await db_get_user_total_posts(user_id)
    unpublished = await db_get_user_unpublished_posts(user_id)
    groups = await db_get_user_groups_count(user_id)
    auto = get_text(user_id, 'auto_on') if await db_auto_status(user_id) else get_text(user_id, 'auto_off')
    text = get_text(user_id, 'stats').format(channels, total, unpublished, groups, auto)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

# ===================================================================
# 42. دوال المهام الخلفية (Background Tasks) - كاملة
# ===================================================================

async def auto_publish_loop_improved(bot):
    await asyncio.sleep(5)
    consecutive_errors = 0
    backoff = 10
    max_backoff = 60
    semaphore = asyncio.Semaphore(5)

    async def publish_one(row):
        async with semaphore:
            ch_db_id, ch_tele_id, user_id = row
            if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
                return
            has_permission, permission_msg = await check_bot_permissions(bot, ch_tele_id)
            if not has_permission:
                return
            auto_recycle = await db_get_auto_recycle(user_id)
            total = await db_get_posts_count(ch_db_id)
            published = await db_get_published_count(ch_db_id)
            if total > 0 and published >= total:
                if auto_recycle:
                    logger.info(f"♻️ إعادة تدوير تلقائي للقناة {ch_tele_id} (مفعلة للمستخدم {user_id})")
                    await db_reset_all_posts_to_unpublished(ch_db_id)
                    try:
                        await bot.send_message(chat_id=user_id, text=f"♻️ **تم إعادة تدوير المنشورات تلقائياً!**\n\n📡 القناة: {ch_tele_id}\n📝 تم إعادة تعيين {total} منشور للنشر من جديد.", parse_mode="MarkdownV2")
                    except:
                        pass
                    return
                else:
                    logger.warning(f"⛔ توقف النشر للقناة {ch_tele_id} (auto_recycle معطل للمستخدم {user_id})")
                    try:
                        await bot.send_message(chat_id=user_id, text=f"⚠️ **توقف النشر التلقائي**\n\n📡 القناة: {ch_tele_id}\n📝 تم نشر جميع المنشورات ({published}/{total}).\n\n♻️ إعادة التدوير التلقائي معطل.\n📌 قم بتفعيله من الإعدادات أو أضف منشورات جديدة.", parse_mode="MarkdownV2")
                    except:
                        pass
                    await db_set_next_publish_date(ch_db_id, utc_now() + timedelta(days=365))
                    return
            post = await db_get_next_post(ch_db_id)
            if not post:
                if auto_recycle:
                    total = await db_get_posts_count(ch_db_id)
                    if total > 0:
                        await db_reset_all_posts_to_unpublished(ch_db_id)
                        logger.info(f"♻️ إعادة تدوير تلقائي للقناة {ch_tele_id} (لا توجد منشورات غير منشورة)")
                        try:
                            await bot.send_message(chat_id=user_id, text=f"♻️ **تم إعادة تدوير المنشورات تلقائياً!**\n\n📡 القناة: {ch_tele_id}\n📝 تم إعادة تعيين {total} منشور للنشر من جديد.", parse_mode="MarkdownV2")
                        except:
                            pass
                        return
                    else:
                        logger.info(f"📭 لا توجد منشورات في القناة {ch_tele_id}")
                        return
                else:
                    logger.info(f"📭 لا توجد منشورات للقناة {ch_tele_id} (auto_recycle معطل)")
                    return
            translation_lang = await get_user_translation_language(user_id)
            final_text = post['text']
            if translation_lang != 'off' and final_text:
                try:
                    translated = await translate_text(final_text, translation_lang)
                    if translated and translated != final_text:
                        final_text = f"{final_text}\n\n🌐 {translated}"
                except:
                    pass
            success = False
            for attempt in range(3):
                try:
                    if post['media_type'] == 'photo' and post['media_file_id']:
                        await bot.send_photo(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
                    elif post['media_type'] == 'video' and post['media_file_id']:
                        await bot.send_video(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
                    elif post['media_type'] == 'document' and post['media_file_id']:
                        await bot.send_document(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
                    elif post['media_type'] == 'audio' and post['media_file_id']:
                        await bot.send_audio(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
                    elif post['media_type'] == 'voice' and post['media_file_id']:
                        await bot.send_voice(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
                    elif post['media_type'] == 'animation' and post['media_file_id']:
                        await bot.send_animation(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
                    else:
                        await bot.send_message(ch_tele_id, final_text, parse_mode=None)
                    success = True
                    break
                except Exception as e:
                    logger.warning(f"محاولة {attempt+1} فشلت في النشر للقناة {ch_tele_id}: {e}")
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
            if success:
                await db_mark_published(post['id'])
                await db_set_last_publish(ch_db_id, utc_now())
                await db_update_next_publish_date(ch_db_id)
            else:
                await db_increment_fail_count(post['id'])
                logger.error(f"فشل دائم في نشر المنشور {post['id']} في القناة {ch_tele_id}")
                next_retry = utc_now() + timedelta(seconds=PUBLISH_RETRY_DELAY)
                await db_set_next_publish_date(ch_db_id, next_retry)
            await asyncio.sleep(random.uniform(2, 5))
    while True:
        try:
            publish_interval = await db_get_publish_interval_seconds()
            async def _get_due_channels(conn, limit=MAX_CHANNELS_PER_CYCLE):
                now_utc_iso = utc_now().isoformat()
                cur = await conn.execute("""
                    SELECT uc.id, uc.channel_id, u.user_id
                    FROM user_channels uc
                    JOIN users u ON uc.user_id = u.user_id
                    LEFT JOIN schedule s ON uc.id = s.channel_db_id
                    WHERE u.auto_publish = 1
                      AND u.banned = 0
                      AND uc.banned = 0
                      AND (s.next_publish_date IS NULL OR s.next_publish_date <= ?)
                    ORDER BY COALESCE(s.next_publish_date, '1970-01-01') ASC
                    LIMIT ?
                """, (now_utc_iso, limit))
                return await cur.fetchall()
            rows = await execute_db(_get_due_channels)
            tasks = [publish_one(row) for row in rows]
            await asyncio.gather(*tasks, return_exceptions=True)
            consecutive_errors = 0
            backoff = publish_interval
            await asyncio.sleep(publish_interval)
        except Exception as e:
            logger.error(f"خطأ في حلقة النشر: {e}")
            consecutive_errors += 1
            backoff = min(backoff * 1.5, max_backoff)
            await asyncio.sleep(backoff)

async def auto_backup():
    consecutive_errors = 0
    backoff = AUTO_BACKUP_SLEEP
    max_backoff = 7 * 24 * 60 * 60
    while True:
        try:
            await asyncio.sleep(AUTO_BACKUP_SLEEP)
            auto_enabled = await db_get_auto_backup()
            if auto_enabled:
                last_backup = await db_get_last_backup_time()
                if not last_backup:
                    await create_backup()
                else:
                    last_time = datetime.fromisoformat(last_backup)
                    if (utc_now() - last_time).days >= 7:
                        await create_backup()
                    else:
                        await incremental_backup()
                async def _update_backup_time(conn):
                    await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_backup', ?)", (utc_now_iso(),))
                    await conn.commit()
                await execute_db(_update_backup_time)
            consecutive_errors = 0
            backoff = AUTO_BACKUP_SLEEP
        except Exception as e:
            logger.error(f"⚠️ خطأ في النسخ الاحتياطي التلقائي: {e}")
            backoff = min(backoff * 1.5, max_backoff)
            await asyncio.sleep(backoff)

async def run_scheduled_posts_loop_improved(bot):
    while True:
        await asyncio.sleep(SCHEDULED_POSTS_SLEEP)
        try:
            now_utc = utc_now()
            posts = await db_get_due_scheduled_posts(now_utc, limit=50)
            for post_id, chat_id, text, fail_count in posts:
                try:
                    await bot.send_message(chat_id, text)
                    await db_delete_scheduled_post(post_id)
                except Exception as e:
                    new_fail = fail_count + 1
                    await db_update_scheduled_post_fail(post_id, new_fail)
                    if new_fail >= 5:
                        await db_delete_scheduled_post(post_id)
        except:
            pass

async def send_reminders_loop_improved(bot):
    while True:
        await asyncio.sleep(REMINDERS_SLEEP)
        try:
            users_to_remind = await db_get_users_needing_reminder()
            for user_data in users_to_remind:
                user_id = user_data['user_id']
                days_left = user_data['days_left']
                lang = user_data['notification_lang']
                original_lang = user_language.get(user_id, 'ar')
                user_language[user_id] = lang
                text = get_text(user_id, 'subscription_warning').format(days_left)
                try:
                    await safe_send_markdown(bot, user_id, text)
                    await db_update_last_reminder_sent(user_id, "subscription_expiry")
                except:
                    pass
                user_language[user_id] = original_lang
        except:
            pass

async def cleanup_expired_sessions_improved():
    while True:
        await asyncio.sleep(CLEANUP_SLEEP)
        try:
            now = time_module.time()
            async def _cleanup_sessions(conn):
                await conn.execute("DELETE FROM web_sessions WHERE expires < ?", (now,))
                await conn.commit()
            await execute_db(_cleanup_sessions)
            async def _cleanup_tickets(conn):
                cutoff = (utc_now() - timedelta(days=30)).isoformat()
                await conn.execute("DELETE FROM support_tickets WHERE created_at < ? AND status='closed'", (cutoff,))
                await conn.commit()
            await execute_db(_cleanup_tickets)
        except:
            pass

async def broadcast_stats_periodically():
    while True:
        await asyncio.sleep(60)
        try:
            total, banned, posts, groups, channels = await db_stats()
            logger.info(f"📊 إحصائيات: مستخدمين={total}, محظورين={banned}, منشورات={posts}, مجموعات={groups}, قنوات={channels}")
        except:
            pass

async def auto_close_contests_loop(bot):
    while True:
        await asyncio.sleep(3600)
        try:
            now = utc_now().isoformat()
            async def _get_expired(conn):
                cur = await conn.execute("SELECT id FROM contests WHERE status = 'active' AND end_date <= ?", (now,))
                return [row[0] for row in await cur.fetchall()]
            expired = await execute_db(_get_expired)
            for contest_id in expired:
                contest = await db_get_contest(contest_id)
                if not contest:
                    continue
                participants_count = 0
                async def _count_participants(conn):
                    cur = await conn.execute("SELECT COUNT(*) FROM contest_participants WHERE contest_id=?", (contest_id,))
                    return (await cur.fetchone())[0]
                participants_count = await execute_db(_count_participants)
                if participants_count > 0:
                    winner_id = await db_get_random_participant(contest_id)
                    if winner_id:
                        await db_set_contest_winner(contest_id, winner_id)
                        try:
                            await bot.send_message(winner_id, f"🏆 **تهانينا!**\nلقد فزت في مسابقة **{contest['title']}**!\n🎁 جائزتك: {contest['prize']}")
                        except:
                            pass
                    else:
                        async def _close(conn):
                            await conn.execute("UPDATE contests SET status = 'finished' WHERE id = ?", (contest_id,))
                            await conn.commit()
                        await execute_db(_close)
                else:
                    async def _close(conn):
                        await conn.execute("UPDATE contests SET status = 'finished' WHERE id = ?", (contest_id,))
                        await conn.commit()
                    await execute_db(_close)
        except:
            pass

async def memory_monitor():
    while True:
        try:
            ram = get_ram_usage()
            if ram['percent'] > 80:
                await memory_optimizer()
            await asyncio.sleep(60)
        except:
            await asyncio.sleep(60)

async def refresh_group_admins_and_hidden_owners_loop(bot):
    while True:
        try:
            async def _get_all_groups(conn):
                cur = await conn.execute("SELECT chat_id FROM bot_groups WHERE banned=0")
                return [row[0] for row in await cur.fetchall()]
            groups = await execute_db(_get_all_groups)
            for chat_id in groups:
                try:
                    await db_sync_group_admins(chat_id, bot)
                    async def _remove_non_admin_hidden_owners(conn):
                        cur = await conn.execute("SELECT owner_id FROM hidden_owner_groups WHERE chat_id=?", (chat_id,))
                        owners = [row[0] for row in await cur.fetchall()]
                        for owner_id in owners:
                            try:
                                member = await bot.get_chat_member(chat_id, owner_id)
                                if member.status not in ['administrator', 'creator']:
                                    await conn.execute("DELETE FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, owner_id))
                                    invalidate_auth_cache(chat_id, owner_id)
                                    logger.info(f"🗑️ تم إزالة المالك المخفي {owner_id} من المجموعة {chat_id} (لم يعد مشرفاً)")
                            except Exception as e:
                                logger.error(f"فشل التحقق من المالك المخفي {owner_id} في {chat_id}: {e}")
                        cur = await conn.execute("SELECT admin_id FROM hidden_admins WHERE chat_id=?", (chat_id,))
                        admins = [row[0] for row in await cur.fetchall()]
                        for admin_id in admins:
                            try:
                                member = await bot.get_chat_member(chat_id, admin_id)
                                if member.status not in ['administrator', 'creator']:
                                    await conn.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
                                    invalidate_auth_cache(chat_id, admin_id)
                                    logger.info(f"🗑️ تم إزالة المشرف المخفي {admin_id} من المجموعة {chat_id} (لم يعد مشرفاً)")
                            except Exception as e:
                                logger.error(f"فشل التحقق من المشرف المخفي {admin_id} في {chat_id}: {e}")
                        await conn.commit()
                    await execute_db(_remove_non_admin_hidden_owners)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"فشل تحديث صلاحيات المجموعة {chat_id}: {e}")
            logger.info(f"✅ تم تحديث صلاحيات {len(groups)} مجموعة")
        except Exception as e:
            logger.error(f"خطأ في حلقة تحديث الصلاحيات: {e}")
        await asyncio.sleep(3600)

async def self_ping_loop():
    import aiohttp
    while True:
        try:
            await asyncio.sleep(300)
            port = int(os.getenv("PORT", "10000"))
            async with aiohttp.ClientSession() as session:
                url = f"http://localhost:{port}/health"
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        logger.debug("✅ Ping ناجح")
        except Exception as e:
            logger.debug(f"⚠️ فشل Ping: {e}")

async def cleanup_points_cache():
    while True:
        await asyncio.sleep(3600)
        user_points_last_hour.clear()

async def memory_optimizer():
    try:
        if CACHETOOLS_AVAILABLE:
            _admin_cache.clear()
            _security_cache.clear()
            _auth_cache.clear()
        else:
            _admin_cache.clear()
            _security_cache.clear()
            _auth_cache.clear()
        _translation_cache.clear()
        gc.collect()
        return True
    except Exception as e:
        advanced_logger.log_error("فشل تحسين الذاكرة", e)
        return False

async def memory_optimizer_loop():
    while True:
        await asyncio.sleep(300)
        try:
            await memory_optimizer()
        except Exception as e:
            advanced_logger.log_error("فشل حلقة تحسين الذاكرة", e)

async def check_bot_permissions(bot, chat_id: int) -> tuple:
    try:
        me = await bot.get_chat_member(chat_id, bot.id)
        if me.status not in ['administrator', 'creator']:
            return False, "البوت ليس مشرفاً"
        if not me.can_post_messages:
            return False, "البوت ليس لديه صلاحية النشر"
        return True, ""
    except Exception as e:
        return False, str(e)

async def create_backup():
    try:
        encrypted_path = encrypt_db_backup()
        temp_backup = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_backup.close()
        shutil.copy2(DB_PATH, temp_backup.name)
        with open(temp_backup.name, 'rb') as f:
            backup_data = f.read()
        compressed = compress_backup(backup_data)
        encrypted = BACKUP_CIPHER.encrypt(compressed)
        backup_file = BACKUP_DIR / f"backup_{mecca_now().strftime('%Y%m%d_%H%M%S')}.enc"
        with open(backup_file, 'wb') as f:
            f.write(encrypted)
        os.unlink(temp_backup.name)
        backups = sorted(BACKUP_DIR.glob("backup_*.enc"), key=lambda x: x.stat().st_mtime, reverse=True)
        for old_backup in backups[MAX_BACKUPS:]:
            old_backup.unlink()
        logger.info(f"✅ تم إنشاء نسخة احتياطية مشفرة: {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"❌ فشل إنشاء النسخة الاحتياطية: {e}")
        raise

async def incremental_backup():
    try:
        last_backup = await db_get_last_backup_time()
        if last_backup:
            last_time = datetime.fromisoformat(last_backup)
        else:
            last_time = utc_now() - timedelta(days=7)
        backup_data = {}
        async def _get_new_posts(conn):
            cur = await conn.execute("SELECT * FROM posts WHERE created_at > ? LIMIT 1000", (last_time.isoformat(),))
            return await cur.fetchall()
        new_posts = await execute_db(_get_new_posts)
        if new_posts:
            backup_data['posts'] = [dict(post) for post in new_posts]
        async def _get_new_users(conn):
            cur = await conn.execute("SELECT * FROM users WHERE user_id IN (SELECT user_id FROM users_cache WHERE last_updated > ?)", (last_time.isoformat(),))
            return await cur.fetchall()
        new_users = await execute_db(_get_new_users)
        if new_users:
            backup_data['users'] = [dict(user) for user in new_users]
        if backup_data:
            data_json = json.dumps(backup_data, default=str)
            compressed = compress_backup(data_json.encode('utf-8'))
            encrypted = BACKUP_CIPHER.encrypt(compressed)
            backup_file = BACKUP_DIR / f"incremental_{mecca_now().strftime('%Y%m%d_%H%M%S')}.inc"
            with open(backup_file, 'wb') as f:
                f.write(encrypted)
            logger.info(f"✅ تم إنشاء نسخة احتياطية متزايدة: {backup_file}")
            return backup_file
        logger.info("📭 لا توجد بيانات جديدة للنسخ الاحتياطي المتزايد")
        return None
    except Exception as e:
        logger.error(f"❌ فشل إنشاء النسخة الاحتياطية المتزايدة: {e}")
        return None

async def list_backups():
    backups = sorted(BACKUP_DIR.glob("backup_*.enc"), key=lambda x: x.stat().st_mtime, reverse=True)
    incremental = sorted(BACKUP_DIR.glob("incremental_*.inc"), key=lambda x: x.stat().st_mtime, reverse=True)
    return backups + incremental

async def restore_backup(backup_path: Path):
    if not backup_path.exists():
        raise FileNotFoundError(f"الملف {backup_path} غير موجود")
    with open(backup_path, 'rb') as f:
        encrypted = f.read()
    try:
        decrypted = BACKUP_CIPHER.decrypt(encrypted)
    except Exception as e:
        raise ValueError(f"فشل فك التشفير: {e}")
    try:
        decompressed = decompress_backup(decrypted)
    except Exception as e:
        raise ValueError(f"فشل فك الضغط: {e}")
    if backup_path.suffix == '.inc':
        data = json.loads(decompressed.decode('utf-8'))
        async def _merge_data(conn):
            if 'posts' in data:
                for post in data['posts']:
                    await conn.execute(
                        "INSERT OR IGNORE INTO posts (id, channel_db_id, text, media_type, media_file_id, published, fail_count, views_count, last_view_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (post['id'], post['channel_db_id'], post['text'], post['media_type'], post['media_file_id'], post['published'], post['fail_count'], post['views_count'], post['last_view_time'], post['created_at'])
                    )
            if 'users' in data:
                for user in data['users']:
                    await conn.execute(
                        "INSERT OR IGNORE INTO users (user_id, auto_publish, banned, trial_used, subscription_end, referral_code, referred_by, active_channel, auto_reply_enabled, auto_recycle) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (user['user_id'], user['auto_publish'], user['banned'], user['trial_used'], user['subscription_end'], user['referral_code'], user['referred_by'], user['active_channel'], user['auto_reply_enabled'], user['auto_recycle'])
                    )
            await conn.commit()
        await execute_db(_merge_data)
        logger.info(f"✅ تم دمج النسخة المتزايدة: {backup_path}")
    else:
        temp_restore = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_restore.write(decompressed)
        temp_restore.close()
        current_backup = BACKUP_DIR / f"pre_restore_{mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, current_backup)
        shutil.copy2(temp_restore.name, DB_PATH)
        os.unlink(temp_restore.name)
        await db_pool.initialize()
        logger.info(f"✅ تم استعادة النسخة الكاملة: {backup_path}")

# ===================================================================
# 43. وظائف تهيئة قاعدة البيانات وخادم الويب
# ===================================================================

async def init_security_table():
    async def _create(conn):
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_security (
                chat_id INTEGER PRIMARY KEY,
                links INTEGER DEFAULT 0,
                mentions INTEGER DEFAULT 0,
                slow_mode INTEGER DEFAULT 0,
                slow_mode_seconds INTEGER DEFAULT 5,
                welcome_enabled INTEGER DEFAULT 0,
                goodbye_enabled INTEGER DEFAULT 0,
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
                antiflood_enabled INTEGER DEFAULT 0,
                night_mode_enabled INTEGER DEFAULT 0,
                max_message_length INTEGER DEFAULT 0,
                delete_penalty TEXT DEFAULT 'none',
                delete_penalty_duration INTEGER DEFAULT 0,
                antiflood_messages INTEGER DEFAULT 5,
                antiflood_seconds INTEGER DEFAULT 10,
                antiflood_penalty TEXT DEFAULT 'mute',
                max_warnings INTEGER DEFAULT 3,
                warn_penalty TEXT DEFAULT 'ban',
                night_mode_start TEXT DEFAULT '23:00',
                night_mode_end TEXT DEFAULT '06:00',
                night_mode_action TEXT DEFAULT 'mute',
                welcome_text TEXT DEFAULT 'مرحباً {user} في {chat} 🤍',
                goodbye_text TEXT DEFAULT 'وداعاً {user} 👋',
                delete_banned_words INTEGER DEFAULT 0,
                auto_penalty TEXT DEFAULT 'none',
                auto_mute_duration INTEGER DEFAULT 60
            )
        """)
        await conn.commit()
        logger.info("✅ جدول group_security جاهز")
    await execute_db(_create)

async def init_db_improved():
    async with aiosqlite.connect(str(DB_PATH), timeout=DB_TIMEOUT) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA cache_size=-64000")
        await conn.execute("PRAGMA temp_store=MEMORY")
        await conn.execute("PRAGMA wal_autocheckpoint=1000")
        await conn.execute("PRAGMA optimize")
        await conn.execute("PRAGMA max_page_count=1000000")
        await conn.execute("PRAGMA secure_delete=ON")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                auto_publish INTEGER DEFAULT 1,
                banned INTEGER DEFAULT 0,
                trial_used INTEGER DEFAULT 0,
                subscription_end TEXT,
                referral_code TEXT,
                referred_by INTEGER,
                active_channel INTEGER,
                auto_reply_enabled INTEGER DEFAULT 1,
                auto_recycle INTEGER DEFAULT 1,
                last_daily_reward TEXT,
                last_weekly_reward TEXT,
                achievements TEXT DEFAULT '[]'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users_cache (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_updated TEXT
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
                FOREIGN KEY(user_id) REFERENCES users(user_id)
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
                views_count INTEGER DEFAULT 0,
                last_view_time TEXT,
                created_at TEXT,
                FOREIGN KEY(channel_db_id) REFERENCES user_channels(id)
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
                next_publish_date TEXT,
                FOREIGN KEY(channel_db_id) REFERENCES user_channels(id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS last_publish (
                channel_db_id INTEGER PRIMARY KEY,
                last_publish_time TEXT,
                FOREIGN KEY(channel_db_id) REFERENCES user_channels(id)
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
                PRIMARY KEY(chat_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_owner_groups (
                chat_id INTEGER,
                owner_id INTEGER,
                is_hidden INTEGER DEFAULT 1,
                PRIMARY KEY(chat_id, owner_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_admins (
                chat_id INTEGER,
                admin_id INTEGER,
                added_by INTEGER,
                added_at TEXT,
                PRIMARY KEY(chat_id, admin_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_groups_link (
                user_id INTEGER,
                chat_id INTEGER,
                PRIMARY KEY(user_id, chat_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_security (
                chat_id INTEGER PRIMARY KEY,
                delete_links INTEGER DEFAULT 0,
                mentions INTEGER DEFAULT 0,
                warn_message INTEGER DEFAULT 1,
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
                night_mode_action TEXT DEFAULT 'mute'
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
                PRIMARY KEY(user_id, chat_id)
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
            CREATE TABLE IF NOT EXISTS group_replies (
                keyword TEXT PRIMARY KEY,
                reply TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_reply_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
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
                user_id INTEGER PRIMARY KEY
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_channels (
                channel_id INTEGER PRIMARY KEY,
                channel_name TEXT,
                added_by INTEGER,
                added_at TEXT,
                banned INTEGER DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.execute("""
            INSERT OR IGNORE INTO settings (key, value) VALUES ('publish_interval', ?)
        """, (str(DEFAULT_PUBLISH_INTERVAL_SECONDS),))
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.execute("""
            INSERT OR IGNORE INTO referral_settings (key, value) VALUES 
                ('reward_days_per_referral', '3'),
                ('max_referrals_per_day', '5'),
                ('welcome_bonus_points', '10')
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                referred_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_rewarded INTEGER DEFAULT 0,
                UNIQUE(referred_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_rewards (
                user_id INTEGER PRIMARY KEY,
                referral_count INTEGER DEFAULT 0,
                total_reward_days INTEGER DEFAULT 0,
                claimed_reward_days INTEGER DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_reminder_settings (
                user_id INTEGER PRIMARY KEY,
                subscription_reminder INTEGER DEFAULT 1,
                daily_stats_reminder INTEGER DEFAULT 0,
                weekly_report INTEGER DEFAULT 1,
                reminder_days_before INTEGER DEFAULT 3,
                last_reminder_sent INTEGER DEFAULT 0,
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
            CREATE TABLE IF NOT EXISTS user_levels (
                user_id INTEGER PRIMARY KEY,
                points INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1
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
            CREATE TABLE IF NOT EXISTS moderation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                action TEXT,
                duration_minutes INTEGER,
                moderator_id INTEGER,
                reason TEXT,
                created_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_warnings (
                user_id INTEGER,
                chat_id INTEGER,
                warnings INTEGER DEFAULT 0,
                PRIMARY KEY(user_id, chat_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS allowed_sendcode_user (
                id INTEGER PRIMARY KEY,
                user_id INTEGER
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS web_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                user_id INTEGER,
                created_at REAL,
                expires REAL
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
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                text TEXT,
                created_by INTEGER,
                created_at TEXT,
                scheduled_for TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                chat_id INTEGER,
                user_id INTEGER,
                details TEXT,
                severity TEXT DEFAULT 'info',
                created_at TEXT NOT NULL
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_type ON security_events(event_type)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_severity ON security_events(severity)")
        await conn.commit()
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")

async def setup_unified_web_server(application, port: int):
    from aiohttp import web
    from telegram import Update
    import json

    if not hasattr(application, 'web_app') or application.web_app is None:
        application.web_app = web.Application()

    async def health_check(request):
        try:
            db_healthy = await check_database_health()
            tg_healthy = await check_telegram_health()
            ram = get_ram_usage()
            checks = {
                'database': db_healthy,
                'telegram_api': tg_healthy,
                'memory': ram,
                'uptime': time_module.time() - start_time
            }
            status = 200 if all([checks['database'], checks['telegram_api']]) else 503
            return web.json_response({
                'status': 'healthy' if status == 200 else 'unhealthy',
                'checks': checks
            }, status=status)
        except Exception as e:
            return web.json_response({
                'status': 'unhealthy',
                'error': str(e)
            }, status=503)

    async def index_handler(request):
        html = """
        <html>
            <head><title>ريلاكس مانيجر</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px; direction: rtl;">
                <h1>🌿 ريلاكس مانيجر</h1>
                <p>✅ البوت يعمل بكفاءة</p>
                <p>📊 <a href="/health">التحقق من الصحة</a></p>
                <p>🤖 <a href="https://t.me/Reelaaaxbot">البوت على تيليجرام</a></p>
                <p style="color: #666; font-size: 12px;">الإصدار 21.0.0</p>
            </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html", charset="utf-8")

    async def webhook_handler(request):
        try:
            data = await request.json()
            update_id = data.get('update_id', 'unknown')
            logger.info(f"📩 استقبال تحديث: {update_id}")
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
            return web.Response(status=200, text="OK")
        except Exception as e:
            logger.error(f"❌ خطأ في Webhook: {e}")
            return web.Response(status=500, text="Error")

    application.web_app.router.add_get('/', index_handler)
    application.web_app.router.add_get('/health', health_check)
    application.web_app.router.add_post(f"/{TOKEN}", webhook_handler)

    runner = web.AppRunner(application.web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"✅ خادم الويب الموحد يعمل على المنفذ {port}")
    return site

async def check_database_health() -> bool:
    try:
        async def _check(conn):
            cur = await conn.execute("SELECT 1")
            return await cur.fetchone() is not None
        return await execute_db(_check)
    except:
        return False

async def check_telegram_health() -> bool:
    try:
        from telegram.ext import Application
        app = Application.builder().token(TOKEN).build()
        me = await app.bot.get_me()
        return me is not None
    except:
        return False

class TaskManager:
    def __init__(self, max_tasks=50, max_concurrent=10):
        self.tasks = set()
        self._lock = asyncio.Lock()
        self.max_tasks = max_tasks
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def create_task(self, coro: Awaitable) -> asyncio.Task:
        async def _wrapped():
            async with self.semaphore:
                return await coro
        if len(self.tasks) >= self.max_tasks:
            try:
                oldest = next(iter(self.tasks))
                oldest.cancel()
            except StopIteration:
                pass
        task = asyncio.create_task(_wrapped())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def cancel_all(self):
        for task in list(self.tasks):
            if not task.done():
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

task_manager = TaskManager(max_concurrent=10)

async def safe_loop(coro, name="background_loop"):
    while True:
        try:
            await coro()
        except asyncio.CancelledError:
            logger.info(f"🛑 تم إلغاء الحلقة: {name}")
            break
        except Exception as e:
            logger.error(f"❌ تعطلت الحلقة {name}: {e}. إعادة التشغيل بعد 10 ثوانٍ...")
            await asyncio.sleep(10)

async def run_polling_safe(application):
    while True:
        try:
            await application.run_polling(
                drop_pending_updates=True,
                poll_interval=POLL_INTERVAL
            )
        except asyncio.CancelledError:
            logger.info("🛑 تم إلغاء polling")
            break
        except RuntimeError as e:
            if "Cannot close a running event loop" in str(e):
                logger.warning("⚠️ مشكلة في إغلاق الحلقة، جاري إعادة المحاولة...")
                await asyncio.sleep(3)
                continue
            logger.error(f"❌ خطأ Runtime: {e}. إعادة التشغيل بعد 10 ثوانٍ...")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"❌ توقف polling: {e}. إعادة التشغيل بعد 10 ثوانٍ...")
            await asyncio.sleep(10)
# ===================================================================
# ========== دوال معالجات الأوامر (Command Handlers) - كاملة ==========
# ===================================================================

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        username = update.effective_user.username or ""
        first_name = update.effective_user.first_name or ""
        await db_register_user(user_id)
        await db_update_user_cache(user_id, username, first_name)
        lang = await db_get_user_language(user_id)
        if not lang:
            lang = 'ar'
        await set_user_language(user_id, lang)
        if context.args and context.args[0].startswith('ref_'):
            ref_code = context.args[0][4:]
            referrer_id = await db_get_user_by_referral_code(ref_code)
            if referrer_id and referrer_id != user_id:
                if await db_add_referral(referrer_id, user_id):
                    reward_days = await db_auto_reward_referral(referrer_id, user_id)
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id, 
                            text=f"🎉 قام مستخدم جديد بالتسجيل عبر رابطك!\n👤 المعرف: {user_id}\n🎁 مكافأتك: {reward_days} يوم اشتراك إضافي"
                        )
                    except:
                        pass
        if not await ensure_force_subscribe(update, context):
            return
        kb, title, active = await get_main_keyboard(user_id)
        if active:
            context.user_data['active_channel'] = active
        if update.callback_query:
            await safe_edit_markdown(update.callback_query, title, reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, title, reply_markup=kb)
    except Exception as e:
        logger.error(f"خطأ في start_command_handler: {e}")
        try:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="❌ حدث خطأ، يرجى المحاولة مرة أخرى."
            )
        except:
            pass

async def language_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr"), InlineKeyboardButton("🇹🇷 Türkçe", callback_data="lang_tr")],
        [InlineKeyboardButton("🇨🇳 中文", callback_data="lang_zh"), InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de"), InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
        [InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it"), InlineKeyboardButton("🇵🇹 Português", callback_data="lang_pt")],
        [InlineKeyboardButton("🇯🇵 日本語", callback_data="lang_ja"), InlineKeyboardButton("🇰🇷 한국어", callback_data="lang_ko")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'welcome'), reply_markup=keyboard)

async def syncgroup_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    chat_id = update.effective_chat.id
    chat_name = update.effective_chat.title or "بدون اسم"
    user_id = update.effective_user.id
    await db_register_group(chat_id, chat_name, user_id, update.effective_chat.username)
    bot_perms = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bot_perms['can_act']:
        await safe_send_markdown(
            context.bot,
            user_id,
            f"⚠️ **البوت ليس مشرفاً في المجموعة!**\n\n📌 تم تسجيل المجموعة `{chat_name}`.\n\n🔹 **لتفعيل الميزات المتقدمة:**\n• اجعل البوت مشرفاً في المجموعة\n• ثم استخدم `/syncgroup` مرة أخرى\n\n🔹 إذا كنت مالكاً أو مشرفاً، يمكنك استخدام:\n`/register_hidden_owner`\nبعد جعل البوت مشرفاً."
        )
        return
    is_admin = False
    real_user_id = user_id
    if user_id == ANONYMOUS_ADMIN_ID:
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            if admins:
                for admin in admins:
                    if admin.status == 'creator':
                        real_user_id = admin.user.id
                        is_admin = True
                        break
                if not is_admin and admins:
                    real_user_id = admins[0].user.id
                    is_admin = True
        except Exception as e:
            logger.error(f"فشل في الحصول على مشرفين من المجموعة {chat_id}: {e}")
            is_admin = False
    else:
        is_admin = await is_currently_admin_in_group(context.bot, chat_id, user_id)
        real_user_id = user_id
    if is_admin:
        await db_register_hidden_owner_group(chat_id, real_user_id)
        invalidate_auth_cache(chat_id, real_user_id)
        admin_count = await db_sync_group_admins(chat_id, context.bot, real_user_id)
        await safe_send_markdown(
            context.bot,
            real_user_id,
            f"✅ **تم تفعيل المجموعة بنجاح!**\n\n📌 اسم المجموعة: {chat_name}\n🆔 المعرف: {chat_id}\n👤 تم تسجيلك كمالك مخفي (المعرف: `{real_user_id}`)\n👥 تم مزامنة {admin_count} مشرف\n\n🔐 استخدم /security لإعدادات الأمان\n🛠️ استخدم /panel للوحة التحكم"
        )
        if user_id == ANONYMOUS_ADMIN_ID and user_id != real_user_id:
            await safe_send_markdown(
                context.bot,
                user_id,
                f"🔍 تم تسجيلك كمالك مخفي باستخدام معرفك الحقيقي: `{real_user_id}`"
            )
    else:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'group_registered'))
        await notify_group_admins(context.bot, chat_id, user_id, chat_name)

async def register_hidden_owner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    bot_perms = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bot_perms['can_act']:
        await safe_send_markdown(context.bot, user_id, "⚠️ **البوت ليس مشرفاً في المجموعة!**\n\nلتسجيل نفسك كمالك مخفي، يجب أن يكون البوت مشرفاً أولاً.")
        return
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        is_creator = member.status == 'creator'
        is_admin = member.status == 'administrator'
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ لا يمكن التحقق من صلاحياتك: {str(e)[:100]}")
        return
    if await db_is_banned(user_id):
        await safe_send_markdown(context.bot, user_id, "❌ **أنت محظور عالمياً!**\nلا يمكنك تسجيل نفسك كمالك مخفي.")
        return
    if is_creator or is_admin:
        if await db_is_hidden_owner(chat_id, user_id):
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'hidden_owner_already'))
            return
        await db_register_hidden_owner_group(chat_id, user_id)
        async def _add_real_admin(conn):
            await conn.execute("INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))
            await conn.commit()
        await execute_db(_add_real_admin)
        invalidate_auth_cache(chat_id, user_id)
        await safe_send_markdown(context.bot, user_id, f"✅ **تم تسجيلك كمالك مخفي بنجاح!**\n\n🔐 يمكنك الآن استخدام جميع أوامر الإدارة:\n• `/security` - إعدادات الأمان\n• `/panel` - لوحة التحكم\n• `/lock` / `/unlock` - قفل وفتح المجموعة\n• أوامر الحظر والكتم والتحذير")
        return
    await safe_send_markdown(context.bot, user_id, "❌ **غير مصرح!**\n\nلتسجيل نفسك كمالك مخفي، يجب أن تكون:\n• مالك المجموعة (creator)\n• أو مشرفاً في المجموعة (administrator)\n\n📌 إذا كنت تعتقد أنك مالك:\n• تأكد من أن البوت مشرف\n• تأكد من أنك المالك في تيليجرام")

async def add_hidden_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['administrator', 'creator']:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
            return
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ لا يمكن التحقق من صلاحياتك: {str(e)[:100]}")
        return
    args = context.args
    if len(args) < 1:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n/add_hidden_admin معرف_المستخدم\n\nمثال: `/add_hidden_admin 123456789`")
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await safe_send_markdown(context.bot, user_id, "❌ معرف مستخدم غير صالح!")
        return
    if target_id == PRIMARY_OWNER_ID:
        await safe_send_markdown(context.bot, user_id, "❌ لا يمكن إضافة المطور الأساسي كمشرف مخفي!")
        return
    if target_id == user_id:
        await safe_send_markdown(context.bot, user_id, "❌ لا يمكن إضافة نفسك كمشرف مخفي!")
        return
    try:
        member = await context.bot.get_chat_member(chat_id, target_id)
        if member.status in ['left', 'kicked']:
            await safe_send_markdown(context.bot, user_id, "❌ المستخدم ليس في المجموعة!")
            return
        if member.status not in ['administrator', 'creator', 'member']:
            await safe_send_markdown(context.bot, user_id, "❌ المستخدم ليس عضواً في المجموعة!")
            return
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ لا يمكن العثور على المستخدم: {e}")
        return
    try:
        user = await context.bot.get_chat(target_id)
        if user.is_bot:
            await safe_send_markdown(context.bot, user_id, "❌ لا يمكن إضافة بوت كمشرف مخفي!")
            return
    except:
        pass
    if await db_is_banned(target_id):
        await safe_send_markdown(context.bot, user_id, "❌ المستخدم محظور عالمياً!")
        return
    if await db_is_hidden_admin(chat_id, target_id):
        await safe_send_markdown(context.bot, user_id, f"⚠️ المستخدم `{target_id}` مشرف مخفي بالفعل!")
        return
    success = await db_add_hidden_admin(chat_id, target_id, user_id)
    if success:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'hidden_admin_added').format(target_id))
        invalidate_auth_cache(chat_id, target_id)
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل إضافة المشرف المخفي!")

async def remove_hidden_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['administrator', 'creator']:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
            return
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ لا يمكن التحقق من صلاحياتك: {str(e)[:100]}")
        return
    args = context.args
    if len(args) < 1:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n/remove_hidden_admin معرف_المستخدم\n\nمثال: `/remove_hidden_admin 123456789`")
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await safe_send_markdown(context.bot, user_id, "❌ معرف مستخدم غير صالح!")
        return
    if target_id == PRIMARY_OWNER_ID:
        await safe_send_markdown(context.bot, user_id, "❌ لا يمكن إزالة المطور الأساسي!")
        return
    if not await db_is_hidden_admin(chat_id, target_id):
        await safe_send_markdown(context.bot, user_id, f"⚠️ المستخدم `{target_id}` ليس مشرفاً مخفياً!")
        return
    success = await db_remove_hidden_admin(chat_id, target_id)
    if success:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'hidden_admin_removed').format(target_id))
        invalidate_auth_cache(chat_id, target_id)
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل إزالة المشرف المخفي!")

async def list_hidden_admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['administrator', 'creator']:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
            return
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ لا يمكن التحقق من صلاحياتك: {str(e)[:100]}")
        return
    admins = await db_get_hidden_admins(chat_id)
    if not admins:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'no_hidden_admins'))
        return
    text = get_text(user_id, 'hidden_admin_list').format("")
    for admin in admins:
        text += f"👤 المستخدم: `{admin['admin_id']}`\n"
        text += f"➕ أضيف بواسطة: `{admin['added_by']}`\n"
        text += f"🕐 التاريخ: {admin['added_at'][:16]}\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"
    await safe_send_markdown(context.bot, user_id, text)

async def trial_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await db_has_used_trial(user_id):
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'trial_used'))
        return
    if await db_has_active_subscription(user_id):
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'already_subscribed'))
        return
    await db_activate_trial(user_id)
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'trial'))
    await start_command_handler(update, context)

async def subscribe_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await db_has_active_subscription(user_id):
        days = await db_get_subscription_days_left(user_id)
        await safe_send_markdown(context.bot, user_id, f"✅ اشتراكك مفعل، متبقي {days} يوم\nشكراً لدعمك ❤️")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ 1 يوم - 5 نجوم", callback_data=CallbackData.BUY_SUBSCRIPTION_1),
         InlineKeyboardButton("⭐ 2 يوم - 9 نجوم", callback_data=CallbackData.BUY_SUBSCRIPTION_2)],
        [InlineKeyboardButton("⭐ شهر (30 يوم) - 50 نجمة", callback_data=CallbackData.BUY_SUBSCRIPTION_30),
         InlineKeyboardButton("⭐ 3 أشهر (90 يوم) - 120 نجمة", callback_data=CallbackData.BUY_SUBSCRIPTION_90)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'subscribe'), reply_markup=kb)

async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'help'))

async def support_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['support_mode'] = True
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 كتابة تذكرة", callback_data=CallbackData.SUPPORT_TICKET)],
        [InlineKeyboardButton("❓ المساعدة", callback_data=CallbackData.SUPPORT_HELP)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'support_welcome'), reply_markup=keyboard)

async def rank_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = await get_rank(user_id)
    await safe_send_markdown(context.bot, user_id, f"📊 **رتبتك**\n━━━━━━━━━━━━━━━━━━━━━━\n🎖️ المستوى: {data['level']}\n⭐ النقاط: {data['points']}\n🎯 النقاط المطلوبة للمستوى التالي: {LEVEL_REQUIREMENTS.get(data['level'] + 1, 'ماكس')}")

async def top_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    top_users = await get_top_users(10)
    if not top_users:
        await safe_send_markdown(context.bot, user_id, "📭 لا يوجد مستخدمين بعد.")
        return
    text = "🏆 **أفضل 10 مستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for idx, (uid, points, level) in enumerate(top_users, 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        try:
            user = await context.bot.get_chat(uid)
            name = user.first_name or str(uid)
        except:
            name = str(uid)
        text += f"{medal} {name} - المستوى {level} ({points} نقطة)\n"
    await safe_send_markdown(context.bot, user_id, text)

async def stats_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    stats = await db_get_channel_stats(active)
    ch_info = await db_get_channel_info(active)
    channel_name = ch_info[1] if ch_info else "القناة"
    text = f"📊 **إحصائيات {channel_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📝 إجمالي المنشورات: {stats['total_posts']}\n"
    text += f"✅ المنشورة: {stats['published_posts']}\n"
    text += f"⏳ غير المنشورة: {stats['unpublished_posts']}\n"
    text += f"👁️ إجمالي المشاهدات: {stats['total_views']}\n"
    text += f"📊 متوسط المشاهدات: {stats['avg_views']}\n"
    await safe_send_markdown(context.bot, user_id, text)

async def developer_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = "👨‍💻 **المطور**\n\nريلاكس مانيجر\nالإصدار 21.0.0\n\n📌 المطور: @RelaxMgr\n📌 القناة: @RelaxMgrr"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]])
    await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def updates_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    channel = await db_get_updates_channel()
    if channel:
        text = get_text(user_id, 'updates_text')
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 القناة", url=f"https://t.me/{channel}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
    else:
        text = "📢 لا توجد قناة تحديثات محددة."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]])
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def lock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'admin_only'))
        return
    await db_set_chat_lock(chat_id, True, user_id)
    await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'locked'))

async def unlock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'admin_only'))
        return
    await db_set_chat_lock(chat_id, False)
    await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'unlocked'))

async def schedule_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_SCHEDULE_POST
    await safe_send_markdown(context.bot, user_id, "📝 **جدولة منشور**\n\nأرسل المنشور بهذه الصيغة:\n`YYYY-MM-DD HH:MM نص المنشور`\n\nمثال: `2024-12-25 14:30 مرحباً بالجميع!`\n\n🕐 الوقت بتوقيت مكة المكرمة")

async def panel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    current_lock_status = await is_chat_locked(chat_id)
    lock_status_text = "🔒 مقفلة" if current_lock_status else "🔓 مفتوحة"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 قفل المجموعة", callback_data=f"{CallbackData.PANEL_LOCK_PREFIX}{chat_id}"),
         InlineKeyboardButton("🔓 فتح المجموعة", callback_data=f"{CallbackData.PANEL_UNLOCK_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🛠️ إجراءات متقدمة", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}"),
         InlineKeyboardButton("🔙 إغلاق اللوحة", callback_data=CallbackData.PANEL_CLOSE)]
    ])
    await safe_send_markdown(context.bot, user_id, f"🔧 **لوحة تحكم المجموعة**\n━━━━━━━━━━━━━━\n📌 **المجموعة:** {update.effective_chat.title}\n🔐 **الحالة:** {lock_status_text}\n━━━━━━━━━━━━━━\n\nاستخدم الأزرار للتحكم في قفل وفتح المجموعة والإجراءات المتقدمة", reply_markup=kb)

async def set_rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'admin_only'))
        return
    args = context.args
    if not args:
        await safe_send_markdown(context.bot, chat_id, "📝 **الاستخدام:**\n`/set_rules نص القوانين`")
        return
    rules_text = " ".join(args)
    async def _set_rules(conn):
        await conn.execute("INSERT OR REPLACE INTO group_rules (chat_id, rules_text, updated_by, updated_at) VALUES (?, ?, ?, ?)", (chat_id, rules_text, user_id, utc_now_iso()))
        await conn.commit()
    await execute_db(_set_rules)
    await safe_send_markdown(context.bot, chat_id, "✅ تم تعيين قوانين المجموعة بنجاح!")

async def rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    chat_id = update.effective_chat.id
    async def _get_rules(conn):
        cur = await conn.execute("SELECT rules_text, updated_at FROM group_rules WHERE chat_id=?", (chat_id,))
        return await cur.fetchone()
    rules = await execute_db(_get_rules)
    if not rules:
        await safe_send_markdown(context.bot, chat_id, "📋 لا توجد قوانين مسجلة لهذه المجموعة.")
        return
    rules_text, updated_at = rules
    await safe_send_markdown(context.bot, chat_id, f"📋 **قوانين المجموعة**\n━━━━━━━━━━━━━━━━━━━━━━\n{rules_text}\n\n🕐 آخر تحديث: {updated_at}")

# ===================================================================
# ========== دوال اختيار مجموعة الأمان ==========
# ===================================================================

async def security_select_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار مجموعة لإعدادات الأمان"""
    query = update.callback_query
    user_id = update.effective_user.id
    if query:
        await query.answer()

    if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
        groups = await db_get_user_groups(user_id)
        if not groups:
            if query:
                await query.edit_message_text("📭 لا توجد مجموعات مسجلة لديك.")
            else:
                await safe_send_markdown(context.bot, user_id, "📭 لا توجد مجموعات مسجلة لديك.")
            return
    else:
        async def _get_all_groups(conn):
            cur = await conn.execute("SELECT chat_id, chat_name, username, banned FROM bot_groups ORDER BY chat_name")
            return await cur.fetchall()
        groups = await execute_db(_get_all_groups)

    if not groups:
        if query:
            await query.edit_message_text("📭 لا توجد مجموعات مسجلة.")
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد مجموعات مسجلة.")
        return

    keyboard = []
    for chat_id, chat_name, username, banned in groups:
        if not await is_authorized_in_group(context.bot, chat_id, user_id) and user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
            continue
        status_icon = "⛔" if banned else "✅"
        display_name = chat_name[:28] + "..." if len(chat_name) > 31 else chat_name
        keyboard.append([InlineKeyboardButton(f"{status_icon} {display_name}", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")])

    if not keyboard:
        if query:
            await query.edit_message_text("🔒 لا توجد مجموعات لديك صلاحية عليها.")
        else:
            await safe_send_markdown(context.bot, user_id, "🔒 لا توجد مجموعات لديك صلاحية عليها.")
        return

    keyboard.append([
        InlineKeyboardButton("🔄 تحديث", callback_data=CallbackData.SECURITY_REFRESH_GROUPS),
        InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)
    ])

    if query:
        await query.edit_message_text("🔐 **اختر مجموعة لإعدادات الأمان:**", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_send_markdown(context.bot, user_id, "🔐 **اختر مجموعة لإعدادات الأمان:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def security_refresh_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحديث قائمة المجموعات للأمان"""
    await security_select_group_callback(update, context)

# ===================================================================
# ========== معالج الرسائل الكامل (غير مختصر) ==========
# ===================================================================

async def message_handler_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل في الخاص"""
    if update.message is None or update.effective_user is None:
        return

    user_id = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""
    state = context.user_data.get('state')

    # ===== حالة إضافة قناة =====
    if state == UserState.WAITING_CHANNEL_ID:
        channel_id = text.strip()
        if not (channel_id.startswith('@') or channel_id.lstrip('-').isdigit()):
            await safe_send_markdown(
                context.bot,
                user_id,
                "❌ صيغة المعرف غير صحيحة! استخدم @username أو المعرف الرقمي.\nمثال: @my_channel أو -1001234567890"
            )
            return
        try:
            chat = await context.bot.get_chat(channel_id)
            channel_name = chat.title or "بدون اسم"
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status not in ['administrator', 'creator']:
                    await safe_send_markdown(
                        context.bot,
                        user_id,
                        f"❌ **البوت ليس مشرفاً في القناة `{channel_name}`!**\n\nيرجى إضافة البوت كمشرف في القناة ثم المحاولة مرة أخرى."
                    )
                    context.user_data.pop('state', None)
                    return
                if not bot_member.can_post_messages:
                    await safe_send_markdown(
                        context.bot,
                        user_id,
                        f"❌ **البوت لا يملك صلاحية النشر في القناة `{channel_name}`!**\n\nيرجى منح البوت صلاحية 'نشر الرسائل' في القناة."
                    )
                    context.user_data.pop('state', None)
                    return
            except Exception as e:
                await safe_send_markdown(
                    context.bot,
                    user_id,
                    f"❌ **لا يمكن الوصول إلى القناة:** {str(e)[:100]}\n\nتأكد من أن المعرف صحيح وأن القناة عامة أو البوت عضو فيها."
                )
                context.user_data.pop('state', None)
                return
            result = await db_add_channel(user_id, channel_id, channel_name)
            if result:
                await safe_send_markdown(
                    context.bot,
                    user_id,
                    get_text(user_id, 'channel_added').format(channel_name)
                )
                await db_register_channel(chat.id, channel_name, user_id)
                await my_channels_callback(update, context)
            else:
                await safe_send_markdown(
                    context.bot,
                    user_id,
                    get_text(user_id, 'channel_exists')
                )
        except Exception as e:
            await safe_send_markdown(
                context.bot,
                user_id,
                f"❌ خطأ: {str(e)[:100]}\nتأكد من صحة المعرف."
            )
        context.user_data.pop('state', None)
        return

    # ===== حالة إضافة منشورات =====
    elif state == UserState.ADDING_POSTS:
        session_posts = context.user_data.get(f"session_{user_id}", [])
        target_count = context.user_data.get(f"session_target_{user_id}", 15)
        if len(session_posts) >= target_count:
            await safe_send_markdown(context.bot, user_id, f"✅ تم استلام {len(session_posts)} منشور.\nسيتم حفظهم الآن...")
            active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
            if active:
                await db_save_posts(active, session_posts)
                await safe_send_markdown(context.bot, user_id, f"✅ تم حفظ {len(session_posts)} منشور!")
            else:
                await safe_send_markdown(context.bot, user_id, "⚠️ لم يتم تحديد قناة نشطة.")
            context.user_data.pop(f"session_{user_id}", None)
            context.user_data.pop(f"session_target_{user_id}", None)
            context.user_data.pop('state', None)
            await main_menu_callback(update, context)
            return
        media_type = 'text'
        media_file_id = None
        if update.message.photo:
            media_type = 'photo'
            media_file_id = update.message.photo[-1].file_id
        elif update.message.video:
            media_type = 'video'
            media_file_id = update.message.video.file_id
        elif update.message.document:
            media_type = 'document'
            media_file_id = update.message.document.file_id
        elif update.message.audio:
            media_type = 'audio'
            media_file_id = update.message.audio.file_id
        elif update.message.voice:
            media_type = 'voice'
            media_file_id = update.message.voice.file_id
        elif update.message.animation:
            media_type = 'animation'
            media_file_id = update.message.animation.file_id
        elif update.message.text:
            media_type = 'text'
            text_content = text
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ نوع الميديا غير مدعوم. أرسل نص، صورة، فيديو، مستند، صوت، أو متحرك.")
            return
        if media_type != 'text':
            text_content = update.message.caption or ""
        session_posts.append((text_content, media_type, media_file_id))
        context.user_data[f"session_{user_id}"] = session_posts
        remaining = target_count - len(session_posts)
        await safe_send_markdown(context.bot, user_id, f"✅ تم استلام منشور. متبقي {remaining} منشور.")
        if len(session_posts) >= target_count:
            active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
            if active:
                await db_save_posts(active, session_posts)
                await safe_send_markdown(context.bot, user_id, f"✅ تم حفظ {len(session_posts)} منشور!")
            else:
                await safe_send_markdown(context.bot, user_id, "⚠️ لم يتم تحديد قناة نشطة.")
            context.user_data.pop(f"session_{user_id}", None)
            context.user_data.pop(f"session_target_{user_id}", None)
            context.user_data.pop('state', None)
            await main_menu_callback(update, context)
        return

    # ===== حالة انتظار الفترات الزمنية =====
    elif state == UserState.WAITING_INTERVAL_MINUTES:
        try:
            minutes = int(text)
            if minutes < 1 or minutes > 1440:
                await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال عدد بين 1 و 1440 دقيقة.")
                return
            ch_id = context.user_data.get('schedule_ch_id')
            if context.user_data.get('admin_interval'):
                await db_set_publish_interval_seconds(minutes * 60, user_id, True)
                await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين وقت النشر العام إلى {minutes} دقيقة.")
                context.user_data.pop('admin_interval', None)
            else:
                if ch_id:
                    await db_save_schedule(ch_id, 'interval_minutes', interval_minutes=minutes)
                    await db_set_next_publish_date(ch_id, None)
                    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'interval_set'))
                else:
                    await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد القناة.")
            context.user_data.pop('schedule_ch_id', None)
            context.user_data.pop('state', None)
            await main_menu_callback(update, context)
        except ValueError:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'invalid_number'))
        return

    elif state == UserState.WAITING_INTERVAL_HOURS:
        try:
            hours = int(text)
            if hours < 1 or hours > 168:
                await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال عدد بين 1 و 168 ساعة.")
                return
            ch_id = context.user_data.get('schedule_ch_id')
            if ch_id:
                await db_save_schedule(ch_id, 'interval_hours', interval_hours=hours)
                await db_set_next_publish_date(ch_id, None)
                await safe_send_markdown(context.bot, user_id, get_text(user_id, 'interval_set'))
            else:
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد القناة.")
            context.user_data.pop('schedule_ch_id', None)
            context.user_data.pop('state', None)
            await main_menu_callback(update, context)
        except ValueError:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'invalid_number'))
        return

    elif state == UserState.WAITING_INTERVAL_DAYS:
        try:
            days = int(text)
            if days < 1 or days > 365:
                await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال عدد بين 1 و 365 يوم.")
                return
            ch_id = context.user_data.get('schedule_ch_id')
            if ch_id:
                await db_save_schedule(ch_id, 'interval_days', interval_days=days)
                await db_set_next_publish_date(ch_id, None)
                await safe_send_markdown(context.bot, user_id, get_text(user_id, 'interval_set'))
            else:
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد القناة.")
            context.user_data.pop('schedule_ch_id', None)
            context.user_data.pop('state', None)
            await main_menu_callback(update, context)
        except ValueError:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'invalid_number'))
        return

    elif state == UserState.WAITING_DATES:
        dates = [d.strip() for d in text.split(',') if d.strip()]
        valid_dates = []
        for d in dates:
            try:
                datetime.strptime(d, '%Y-%m-%d')
                valid_dates.append(d)
            except:
                await safe_send_markdown(context.bot, user_id, f"❌ التاريخ {d} غير صالح (الصيغة: YYYY-MM-DD)")
                return
        if valid_dates:
            ch_id = context.user_data.get('schedule_ch_id')
            if ch_id:
                await db_save_schedule(ch_id, 'dates', specific_dates=json.dumps(valid_dates))
                await db_set_next_publish_date(ch_id, None)
                await safe_send_markdown(context.bot, user_id, get_text(user_id, 'interval_set'))
            else:
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد القناة.")
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'invalid_date'))
        context.user_data.pop('schedule_ch_id', None)
        context.user_data.pop('state', None)
        await main_menu_callback(update, context)
        return

    elif state == UserState.WAITING_PUBLISH_TIME:
        if re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', text):
            ch_id = context.user_data.get('schedule_ch_id')
            if ch_id:
                await db_set_publish_time(ch_id, text)
                await db_set_next_publish_date(ch_id, None)
                await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين وقت النشر إلى {text} (بتوقيت مكة).")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد القناة.")
            context.user_data.pop('schedule_ch_id', None)
            context.user_data.pop('state', None)
            await main_menu_callback(update, context)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'invalid_time'))
        return

    elif state == UserState.WAITING_CRON:
        cron_expr = text.strip()
        if cron_expr:
            ch_id = context.user_data.get('schedule_ch_id')
            if ch_id:
                await db_save_schedule(ch_id, 'cron', cron_expression=cron_expr)
                await db_set_next_publish_date(ch_id, None)
                await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين تعبير CRON: `{cron_expr}`")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد القناة.")
            context.user_data.pop('schedule_ch_id', None)
            context.user_data.pop('state', None)
            await main_menu_callback(update, context)
        else:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال تعبير CRON صالح.")
        return

    elif state == UserState.WAITING_MAX_LENGTH:
        try:
            max_len = int(text.strip())
            if max_len < 0:
                await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال رقم موجب أو 0.")
                return
            chat_id = context.user_data.get('security_chat_id')
            if chat_id:
                await db_set_security_settings(chat_id, max_message_length=max_len)
                await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين الحد الأقصى لطول الرسالة إلى {max_len} حرف.")
                if update.callback_query:
                    await _update_security_panel(update.callback_query, chat_id, user_id)
                else:
                    await safe_send_markdown(context.bot, user_id, "يمكنك العودة إلى اللوحة من خلال /security")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المجموعة.")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال رقم صحيح.")
        context.user_data.pop('state', None)
        context.user_data.pop('security_chat_id', None)
        return

    elif state == UserState.WAITING_WARN_COUNT:
        try:
            count = int(text.strip())
            if count < 1 or count > 10:
                await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال عدد بين 1 و 10.")
                return
            chat_id = context.user_data.get('security_chat_id')
            if chat_id:
                await db_set_security_settings(chat_id, max_warnings=count)
                await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين عدد التحذيرات إلى {count}.")
                await security_warn_settings_callback(update, context)
            else:
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المجموعة.")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال رقم صحيح.")
        context.user_data.pop('state', None)
        context.user_data.pop('security_chat_id', None)
        return

    elif state == UserState.WAITING_ADMIN_ID_ADD:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        try:
            target_id = int(text.strip())
            if target_id == PRIMARY_OWNER_ID:
                await safe_send_markdown(context.bot, user_id, "✅ المطور الأساسي مشرف بالفعل.")
            else:
                if await add_bot_admin(target_id):
                    await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة المستخدم `{target_id}` كمشرف.")
                else:
                    await safe_send_markdown(context.bot, user_id, f"❌ فشل إضافة المشرف.")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ معرف غير صالح.")
        context.user_data.pop('state', None)
        await admin_panel_callback(update, context)
        return

    elif state == UserState.WAITING_ADMIN_ID_REMOVE:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        try:
            target_id = int(text.strip())
            if target_id == PRIMARY_OWNER_ID:
                await safe_send_markdown(context.bot, user_id, "❌ لا يمكن إزالة المطور الأساسي.")
            else:
                if await remove_bot_admin(target_id):
                    await safe_send_markdown(context.bot, user_id, f"✅ تم إزالة المستخدم `{target_id}` من المشرفين.")
                else:
                    await safe_send_markdown(context.bot, user_id, f"❌ فشل إزالة المشرف.")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ معرف غير صالح.")
        context.user_data.pop('state', None)
        await admin_panel_callback(update, context)
        return

    elif state == UserState.WAITING_BROADCAST:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        broadcast_text = text.strip()
        if not broadcast_text:
            await safe_send_markdown(context.bot, user_id, "❌ النص لا يمكن أن يكون فارغاً.")
            return
        context.user_data['broadcast_text'] = broadcast_text
        context.user_data.pop('state', None)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تأكيد الإرسال", callback_data=CallbackData.ADMIN_CONFIRM_BROADCAST),
             InlineKeyboardButton("❌ إلغاء", callback_data=CallbackData.ADMIN_PANEL)]
        ])
        await safe_send_markdown(context.bot, user_id, f"📨 **مراجعة الرسالة:**\n\n{broadcast_text[:500]}\n\nهل أنت متأكد من إرسالها لجميع المستخدمين؟", reply_markup=keyboard)
        return

    elif state == UserState.WAITING_UPDATE_TEXT:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        text_update = text.strip()
        if not text_update:
            await safe_send_markdown(context.bot, user_id, "❌ النص لا يمكن أن يكون فارغاً.")
            return
        channel = await db_get_updates_channel()
        if not channel:
            await safe_send_markdown(context.bot, user_id, "❌ لم يتم تعيين قناة التحديثات.")
            context.user_data.pop('state', None)
            return
        try:
            await context.bot.send_message(f"@{channel}", f"📢 **تحديث جديد**\n\n{text_update}")
            await safe_send_markdown(context.bot, user_id, f"✅ تم نشر التحديث في قناة @{channel}")
        except Exception as e:
            await safe_send_markdown(context.bot, user_id, f"❌ فشل النشر: {str(e)[:100]}")
        context.user_data.pop('state', None)
        await admin_updates_callback(update, context)
        return

    elif state == UserState.WAITING_UPDATE_CHANNEL:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        channel = text.strip()
        if channel.startswith('@'):
            channel = channel[1:]
        if await db_set_updates_channel(channel):
            await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين قناة التحديثات: @{channel}")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ فشل تعيين القناة.")
        context.user_data.pop('state', None)
        await admin_updates_callback(update, context)
        return

    elif state == UserState.WAITING_FORCE_CHANNEL:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        channel = text.strip()
        if channel.startswith('@'):
            channel = channel[1:]
        await db_set_force_subscribe_channel(channel)
        await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين قناة الاشتراك الإجباري: @{channel}")
        context.user_data.pop('state', None)
        await admin_force_subscribe_callback(update, context)
        return

    elif state == UserState.WAITING_SENDCODE_USER:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        try:
            target_id = int(text.strip())
            await db_set_allowed_sendcode_user(target_id)
            await safe_send_markdown(context.bot, user_id, f"✅ تم منح صلاحية /sendcode للمستخدم `{target_id}`")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ معرف غير صالح.")
        context.user_data.pop('state', None)
        await admin_panel_callback(update, context)
        return

    elif state == UserState.WAITING_LOG_CHANNEL:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        identifier = text.strip()
        try:
            chat = await context.bot.get_chat(identifier)
            if chat.type != 'channel':
                await safe_send_markdown(context.bot, user_id, "❌ المعرف ليس لقناة!")
                return
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if bot_member.status not in ['administrator', 'creator']:
                await safe_send_markdown(context.bot, user_id, "❌ البوت ليس مشرفاً في هذه القناة!")
                context.user_data.pop('state', None)
                context.user_data.pop('temp_log_channel_identifier', None)
                return
            if not bot_member.can_post_messages:
                await safe_send_markdown(context.bot, user_id, "❌ البوت لا يملك صلاحية الإرسال في هذه القناة!")
                context.user_data.pop('state', None)
                context.user_data.pop('temp_log_channel_identifier', None)
                return
            await db_set_log_channel_id(str(chat.id))
            try:
                await context.bot.send_message(chat.id, "✅ تم تعيين هذه القناة كقناة للتقارير الأمنية!")
            except:
                pass
            await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين قناة التقارير: {chat.title}")
        except Exception as e:
            await safe_send_markdown(context.bot, user_id, f"❌ فشل تعيين القناة: {str(e)[:100]}")
        context.user_data.pop('state', None)
        context.user_data.pop('temp_log_channel_identifier', None)
        await admin_panel_callback(update, context)
        return

    elif state == UserState.WAITING_GROUP_BANNED_WORD:
        chat_id = context.user_data.get('banned_words_chat_id')
        if not chat_id:
            await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المجموعة.")
            context.user_data.pop('state', None)
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        word = text.lower().strip()
        if len(word) < 2:
            await safe_send_markdown(context.bot, user_id, "❌ الكلمة يجب أن تكون حرفين على الأقل.")
            return
        if await db_add_banned_word(word, chat_id, user_id):
            await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة كلمة `{word}` إلى الكلمات المحظورة.")
        else:
            await safe_send_markdown(context.bot, user_id, f"⚠️ الكلمة `{word}` موجودة بالفعل.")
        context.user_data.pop('state', None)
        await security_banned_words_menu_callback(update, context)
        return

    elif state == UserState.WAITING_REMOVE_GROUP_BANNED_WORD:
        chat_id = context.user_data.get('banned_words_chat_id')
        if not chat_id:
            await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المجموعة.")
            context.user_data.pop('state', None)
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        word = text.lower().strip()
        await db_remove_banned_word(word, chat_id)
        await safe_send_markdown(context.bot, user_id, f"✅ تم حذف كلمة `{word}` من الكلمات المحظورة.")
        context.user_data.pop('state', None)
        await security_banned_words_menu_callback(update, context)
        return

    elif state == UserState.WAITING_GLOBAL_BANNED_WORD:
        if not await is_bot_admin(user_id):
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        word = text.lower().strip()
        if len(word) < 2:
            await safe_send_markdown(context.bot, user_id, "❌ الكلمة يجب أن تكون حرفين على الأقل.")
            return
        if await db_add_banned_word(word, -1, user_id):
            await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة كلمة `{word}` إلى الكلمات المحظورة العامة.")
        else:
            await safe_send_markdown(context.bot, user_id, f"⚠️ الكلمة `{word}` موجودة بالفعل.")
        context.user_data.pop('state', None)
        await admin_banned_words_callback(update, context)
        return

    elif state == UserState.WAITING_REMOVE_GLOBAL_BANNED_WORD:
        if not await is_bot_admin(user_id):
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        word = text.lower().strip()
        await db_remove_banned_word(word, -1)
        await safe_send_markdown(context.bot, user_id, f"✅ تم حذف كلمة `{word}` من الكلمات المحظورة العامة.")
        context.user_data.pop('state', None)
        await admin_banned_words_callback(update, context)
        return

    elif state == UserState.WAITING_KEYWORD:
        if not await is_bot_admin(user_id):
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        keyword = text.lower().strip()
        context.user_data['reply_keyword'] = keyword
        context.user_data['state'] = UserState.WAITING_REPLY
        await safe_send_markdown(context.bot, user_id, f"📝 الكلمة المفتاحية: {keyword}\nالآن أرسل الرد المطلوب:")
        return

    elif state == UserState.WAITING_REPLY:
        if context.user_data.get('admin_del_reply'):
            keyword = text.lower().strip()
            if await db_del_reply(keyword):
                await safe_send_markdown(context.bot, user_id, f"✅ تم حذف رد الكلمة `{keyword}`")
            else:
                await safe_send_markdown(context.bot, user_id, f"❌ الكلمة `{keyword}` غير موجودة")
            context.user_data.pop('admin_del_reply', None)
            context.user_data.pop('state', None)
            await admin_replies_callback(update, context)
            return
        keyword = context.user_data.get('reply_keyword')
        if not keyword:
            await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد الكلمة المفتاحية.")
            context.user_data.pop('state', None)
            return
        reply = text.strip()
        if not reply:
            await safe_send_markdown(context.bot, user_id, "❌ الرد لا يمكن أن يكون فارغاً.")
            return
        await db_add_reply(keyword, reply)
        await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة رد للكلمة `{keyword}`")
        context.user_data.pop('reply_keyword', None)
        context.user_data.pop('state', None)
        await admin_replies_callback(update, context)
        return

    elif state == UserState.WAITING_REMINDER_DAYS:
        try:
            days = int(text)
            if days < 1 or days > 10:
                await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال عدد بين 1 و 10 أيام.")
                return
            await db_update_reminder_settings(user_id, reminder_days_before=days)
            await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين التذكير قبل {days} أيام من انتهاء الاشتراك.")
            context.user_data.pop('state', None)
            await reminder_menu_callback(update, context)
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال رقم صحيح.")
        return

    elif state == UserState.WAITING_SCHEDULE_POST:
        parts = text.split(' ', 2)
        if len(parts) >= 3:
            try:
                date_str = parts[0]
                time_str = parts[1]
                post_text = parts[2]
                mecca_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                if mecca_dt <= mecca_now():
                    await safe_send_markdown(context.bot, user_id, "❌ الوقت يجب أن يكون في المستقبل!")
                    return
                utc_dt = mecca_to_utc(mecca_dt)
                chat_id = update.effective_chat.id if update.effective_chat.type in ['group', 'supergroup'] else user_id
                await db_add_scheduled_post(chat_id, post_text, utc_dt)
                await safe_send_markdown(context.bot, user_id, f"✅ تم جدولة المنشور! 📅 {date_str} 🕐 {time_str} (بتوقيت مكة)")
                context.user_data.pop('state', None)
                await main_menu_callback(update, context)
            except ValueError:
                await safe_send_markdown(context.bot, user_id, "❌ صيغة التاريخ/الوقت غير صحيحة! استخدم YYYY-MM-DD HH:MM")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ الصيغة غير صحيحة! استخدم: YYYY-MM-DD HH:MM نص المنشور")
        return

    elif state in [UserState.WAITING_BAN_USER, UserState.WAITING_MUTE_USER, UserState.WAITING_WARN_USER,
                   UserState.WAITING_KICK_USER, UserState.WAITING_RESTRICT_USER, UserState.WAITING_UNBAN_USER]:
        chat_id = context.user_data.get('advanced_chat_id')
        if not chat_id:
            await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المجموعة.")
            context.user_data.pop('state', None)
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        args = text.split(maxsplit=1)
        reason = args[1] if len(args) > 1 else ""
        try:
            target_id = int(args[0]) if args[0].isdigit() else None
            if target_id is None and update.message.reply_to_message:
                target_id = update.message.reply_to_message.from_user.id
            if not target_id:
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المستخدم. أرسل المعرف أو قم بالرد على رسالة المستخدم.")
                return
            action_map = {
                "WAITING_BAN_USER": "ban",
                "WAITING_MUTE_USER": "mute",
                "WAITING_WARN_USER": "warn",
                "WAITING_KICK_USER": "kick",
                "WAITING_RESTRICT_USER": "restrict",
                "WAITING_UNBAN_USER": "unban"
            }
            action = action_map.get(state)
            if not action:
                await safe_send_markdown(context.bot, user_id, "❌ إجراء غير معروف.")
                context.user_data.pop('state', None)
                return
            duration = context.user_data.get('mute_minutes', 60) if action == 'mute' else None
            success, msg = await execute_moderation_action(context.bot, chat_id, target_id, action, reason, duration, user_id)
            await safe_send_markdown(context.bot, user_id, msg)
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ معرف المستخدم غير صالح.")
        context.user_data.pop('state', None)
        context.user_data.pop('mute_minutes', None)
        return

    elif state == UserState.WAITING_PIN_MESSAGE:
        chat_id = context.user_data.get('advanced_chat_id')
        if not chat_id:
            await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المجموعة.")
            context.user_data.pop('state', None)
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        if update.message.reply_to_message:
            success, msg = await execute_pin(context.bot, chat_id, update.message.reply_to_message.message_id)
            await safe_send_markdown(context.bot, user_id, msg)
        else:
            await safe_send_markdown(context.bot, user_id, "❌ قم بالرد على الرسالة التي تريد تثبيتها.")
        context.user_data.pop('state', None)
        return

    elif state == UserState.WAITING_CONTEST_TITLE:
        if not text:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال عنوان صحيح.")
            return
        context.user_data['contest_title'] = text
        context.user_data['state'] = UserState.WAITING_CONTEST_DESCRIPTION
        await safe_send_markdown(context.bot, user_id, "📝 أرسل وصف المسابقة:")
        return

    elif state == UserState.WAITING_CONTEST_DESCRIPTION:
        if not text:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال وصف صحيح.")
            return
        context.user_data['contest_description'] = text
        context.user_data['state'] = UserState.WAITING_CONTEST_PRIZE
        await safe_send_markdown(context.bot, user_id, "🎁 أرسل جائزة المسابقة:")
        return

    elif state == UserState.WAITING_CONTEST_PRIZE:
        if not text:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال جائزة صحيحة.")
            return
        context.user_data['contest_prize'] = text
        context.user_data['state'] = UserState.WAITING_CONTEST_END_DATE
        await safe_send_markdown(context.bot, user_id, "📅 أرسل تاريخ انتهاء المسابقة (صيغة: YYYY-MM-DD HH:MM) بتوقيت مكة:")
        return

    elif state == UserState.WAITING_CONTEST_END_DATE:
        try:
            end_date = datetime.strptime(text, "%Y-%m-%d %H:%M")
            now_mecca = mecca_now()
            if end_date <= now_mecca:
                await safe_send_markdown(context.bot, user_id, "❌ التاريخ يجب أن يكون في المستقبل!")
                return
            end_date_utc = mecca_to_utc(end_date)
            title = context.user_data.pop('contest_title', 'بدون عنوان')
            description = context.user_data.pop('contest_description', '')
            prize = context.user_data.pop('contest_prize', '')
            contest_id = await db_create_contest(user_id, title, description, prize, end_date_utc, 'raffle')
            if contest_id:
                await safe_send_markdown(context.bot, user_id, f"✅ **تم إنشاء المسابقة بنجاح!**\n\n📌 العنوان: {title}\n🎁 الجائزة: {prize}\n📅 تنتهي: {end_date.strftime('%Y-%m-%d %H:%M')} (بتوقيت مكة)\n🆔 معرف المسابقة: `{contest_id}`")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ فشل إنشاء المسابقة، حاول مرة أخرى.")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ صيغة تاريخ غير صحيحة!\nاستخدم: YYYY-MM-DD HH:MM")
            return
        except Exception as e:
            error_id = log_error(e, {'user_id': user_id, 'action': 'create_contest'})
            await safe_send_markdown(context.bot, user_id, f"❌ حدث خطأ أثناء إنشاء المسابقة (الرمز: `{error_id}`).")
            return
        context.user_data.pop('state', None)
        await main_menu_callback(update, context)
        return

    elif state == UserState.WAITING_CONTEST_ANSWER:
        contest_id = context.user_data.get('contest_join_id')
        if not contest_id:
            await safe_send_markdown(context.bot, user_id, "❌ لم يتم العثور على المسابقة.")
            context.user_data.pop('state', None)
            return
        answer = text if text else ""
        if answer.lower() == '/skip':
            answer = ""
        success = await db_participate_in_contest(user_id, contest_id, answer)
        if success:
            await safe_send_markdown(context.bot, user_id, "✅ تم تسجيل مشاركتك في المسابقة بنجاح!")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ أنت مشترك بالفعل في هذه المسابقة!")
        context.user_data.pop('contest_join_id', None)
        context.user_data.pop('state', None)
        await contests_command_handler(update, context)
        return

    elif state == UserState.WAITING_NSFW_THRESHOLD:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        try:
            threshold = float(text)
            if threshold < 0 or threshold > 100:
                await safe_send_markdown(context.bot, user_id, "❌ النسبة يجب أن تكون بين 0 و 100.")
                return
            global NSFW_THRESHOLD
            NSFW_THRESHOLD = threshold / 100.0
            os.environ["NSFW_THRESHOLD"] = str(NSFW_THRESHOLD)
            await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين نسبة الحساسية إلى {threshold}%")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال رقم صحيح.")
        context.user_data.pop('state', None)
        await nsfw_settings_callback(update, context)
        return

    elif state == UserState.WAITING_DELETE_PENALTY_DURATION:
        chat_id = context.user_data.get('security_chat_id')
        if not chat_id:
            await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المجموعة.")
            context.user_data.pop('state', None)
            return
        try:
            duration = int(text.strip())
            if duration < 0:
                await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال عدد موجب أو 0.")
                return
            await db_set_security_settings(chat_id, delete_penalty_duration=duration)
            await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين مدة عقوبة الحذف إلى {duration} دقيقة.")
            if update.callback_query:
                await _update_security_panel(update.callback_query, chat_id, user_id)
            else:
                await safe_send_markdown(context.bot, user_id, "يمكنك العودة إلى اللوحة من خلال /security")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال رقم صحيح.")
        context.user_data.pop('state', None)
        context.user_data.pop('security_chat_id', None)
        return

    elif context.user_data.get('support_mode'):
        if text:
            ticket_num = await db_get_next_ticket_number() + 1
            async def _update_ticket_num(conn):
                await conn.execute("UPDATE settings SET value=? WHERE key='last_ticket_number'", (str(ticket_num),))
                await conn.commit()
            await execute_db(_update_ticket_num)
            username = update.effective_user.username or "بدون يوزر"
            await db_save_ticket(user_id, username, text, ticket_num)
            await safe_send_markdown(context.bot, user_id, f"✅ تم إرسال تذكرتك رقم #{ticket_num}\nسيتم الرد عليك بأسرع وقت.")
            context.user_data.pop('support_mode', None)
            await log_security_event("SUPPORT_TICKET_CREATED", 0, user_id, {"ticket": ticket_num}, "info")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال نص الرسالة.")
        return

    else:
        if update.message.text:
            reply = await db_get_reply(text.lower())
            if reply:
                try:
                    await update.message.reply_text(reply)
                except:
                    pass
        await main_menu_callback(update, context)

# ===================================================================
# ========== دوال إضافية أخرى ==========
# ===================================================================

async def confirm_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    backup_name = query.data.split(":")[-1]
    backup_path = BACKUP_DIR / backup_name
    if not backup_path.exists():
        await query.edit_message_text("❌ الملف غير موجود.")
        return
    try:
        await restore_backup(backup_path)
        await query.edit_message_text("✅ تم استعادة النسخة الاحتياطية بنجاح!")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل الاستعادة: {str(e)[:200]}")
    await admin_panel_callback(update, context)

async def send_addition_report_to_all_admins(bot, chat, adder, chat_type_name):
    try:
        if not chat or not adder:
            return
        admins = await bot.get_chat_administrators(chat.id)
        for admin in admins:
            user = admin.user
            if user.id == adder.id:
                try:
                    await bot.send_message(
                        chat_id=user.id,
                        text=(
                            f"✅ **تم إضافة البوت إلى {chat_type_name}**\n\n"
                            f"📌 الاسم: {chat.title}\n"
                            f"🆔 المعرف: {chat.id}\n"
                            f"👤 أضيف بواسطة: {adder.full_name or adder.first_name or adder.id}\n\n"
                            f"🔒 **تم تسجيلك كمالك مخفي تلقائياً**\n"
                            f"🔐 استخدم /security لإعدادات الأمان\n"
                            f"🛠️ استخدم /panel للوحة التحكم\n\n"
                            f"📌 **ملاحظة:** إذا لم تظهر لك المجموعة، استخدم /syncgroup في المجموعة"
                        ),
                        parse_mode="MarkdownV2"
                    )
                except:
                    pass
            else:
                try:
                    await bot.send_message(
                        chat_id=user.id,
                        text=(
                            f"📢 **تم إضافة البوت إلى {chat_type_name}**\n\n"
                            f"📌 الاسم: {chat.title}\n"
                            f"🆔 المعرف: {chat.id}\n"
                            f"👤 أضيف بواسطة: {adder.full_name or adder.first_name or adder.id}\n\n"
                            f"🔹 **لتفعيل البوت:** استخدم `/syncgroup` في المجموعة.\n"
                            f"🔹 **لتسجيل نفسك كمالك مخفي:** استخدم `/register_hidden_owner`.\n"
                            f"🔹 **لإعدادات الأمان:** استخدم `/security`.\n\n"
                            f"🔹 **ملاحظة:** إذا كنت تريد إدارة البوت، تأكد من أنك مشرف في المجموعة."
                        ),
                        parse_mode="MarkdownV2"
                    )
                except:
                    pass
            await asyncio.sleep(0.3)
    except Exception as e:
        logger.error(f"❌ فشل إرسال الإشعارات للمشرفين في {chat.id}: {e}")

async def detect_owner_type(bot, chat_id: int) -> dict:
    try:
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.status == 'creator':
                return {'is_hidden': False, 'user_id': admin.user.id}
        return {'is_hidden': True, 'user_id': None}
    except Exception as e:
        logger.error(f"فشل كشف المالك في {chat_id}: {e}")
        return {'is_hidden': True, 'user_id': None}

async def add_points(user_id: int, update: Update = None, context: ContextTypes.DEFAULT_TYPE = None):
    now = utc_now()
    count, last_timestamp = user_points_last_hour.get(user_id, (0, 0.0))
    if last_timestamp > 0:
        last_time = datetime.fromtimestamp(last_timestamp)
        last_time = to_naive(last_time)
        if (now - last_time).total_seconds() < 3600:
            if count >= 20:
                return
            new_count = count + 1
        else:
            new_count = 1
    else:
        new_count = 1
    user_points_last_hour[user_id] = (new_count, now.timestamp())
    data = await db_get_user_level(user_id)
    old_level = data['level']
    points = data['points'] + 1
    level = old_level
    new_levels = []
    for lvl, pts in LEVEL_REQUIREMENTS.items():
        if points >= pts and lvl > level:
            new_levels.append(lvl)
            level = lvl
    if new_levels and update and update.effective_user and context:
        try:
            if len(new_levels) == 1:
                msg = f"🎉 **تهانينا!**\nلقد وصلت إلى المستوى {new_levels[0]}! 🎉"
            else:
                msg = f"🎉 **تهانينا!**\nلقد تقدمت {len(new_levels)} مستويات إلى المستوى {new_levels[-1]}! 🎉"
            await safe_send_to_user_or_group(update, context, msg)
        except:
            pass
    await db_update_user_level(user_id, points, level)

async def safe_send_to_user_or_group(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        if update.callback_query:
            await safe_edit_markdown(update.callback_query, text)
        elif update.message:
            await safe_send_markdown(context.bot, update.message.chat_id, text)
        else:
            await safe_send_markdown(context.bot, update.effective_user.id, text)
    except Exception as e:
        logger.error(f"فشل إرسال رسالة في safe_send_to_user_or_group: {e}")

# ===================================================================
# 44. الوظيفة الرئيسية (main)
# ===================================================================

# ===================================================================
# 44. الوظيفة الرئيسية (main) - النسخة الكاملة
# ===================================================================

async def main():
    # تهيئة قاعدة البيانات
    await init_db_improved()
    await init_security_table()
    await fix_missing_columns()

    # تحميل الكلمات المحظورة
    try:
        words = load_banned_words_from_file(BANNED_WORDS_FILE)
        if words:
            async def _import(conn):
                imported = 0
                for word in words:
                    try:
                        await conn.execute(
                            "INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?, ?, ?, ?)",
                            (word, -1, PRIMARY_OWNER_ID, utc_now_iso())
                        )
                        imported += 1
                    except Exception:
                        continue
                await conn.commit()
                return imported
            imported_count = await execute_db(_import)
            logger.info(f"✅ تم استيراد {imported_count} كلمة محظورة من {BANNED_WORDS_FILE}")
            await rebuild_banned_patterns()
    except Exception as e:
        logger.error(f"❌ فشل استيراد الكلمات المحظورة: {e}")

    # تحميل اللغات
    load_all_languages()

    # إعداد Application
    if USE_PROXY:
        request_kwargs = {
            'proxy_url': PROXY_URL,
            'read_timeout': 60.0,
            'write_timeout': 30.0,
            'connect_timeout': 30.0,
            'pool_timeout': 10.0,
            'connection_pool_size': MAX_CONNECTIONS
        }
        request = HTTPXRequest(**request_kwargs)
        application = Application.builder().token(TOKEN).request(request).build()
    else:
        request_kwargs = {
            'read_timeout': 60.0,
            'write_timeout': 30.0,
            'connect_timeout': 30.0,
            'pool_timeout': 10.0,
            'connection_pool_size': MAX_CONNECTIONS
        }
        request = HTTPXRequest(**request_kwargs)
        application = Application.builder().token(TOKEN).request(request).build()

    application.add_error_handler(global_error_handler)

    # ===================================================================
    # تسجيل معالجات الأوامر (Command Handlers)
    # ===================================================================
    application.add_handler(CommandHandler("start", start_command_handler))
    application.add_handler(CommandHandler("language", language_command_handler))
    application.add_handler(CommandHandler("syncgroup", syncgroup_command_handler))
    application.add_handler(CommandHandler("security", security_select_group_callback))
    application.add_handler(CommandHandler("register_hidden_owner", register_hidden_owner_handler))
    application.add_handler(CommandHandler("add_hidden_admin", add_hidden_admin_command))
    application.add_handler(CommandHandler("remove_hidden_admin", remove_hidden_admin_command))
    application.add_handler(CommandHandler("list_hidden_admins", list_hidden_admins_command))
    application.add_handler(CommandHandler("trial", trial_command_handler))
    application.add_handler(CommandHandler("subscribe", subscribe_command_handler))
    application.add_handler(CommandHandler("help", help_command_handler))
    application.add_handler(CommandHandler("support", support_command_handler))
    application.add_handler(CommandHandler("rank", rank_command_handler))
    application.add_handler(CommandHandler("top", top_command_handler))
    application.add_handler(CommandHandler("developer", developer_command_handler))
    application.add_handler(CommandHandler("updates", updates_command_handler))
    application.add_handler(CommandHandler("stats", stats_command_handler))
    application.add_handler(CommandHandler("lock", lock_chat_command_handler))
    application.add_handler(CommandHandler("unlock", unlock_chat_command_handler))
    application.add_handler(CommandHandler("schedule", schedule_command_handler))
    application.add_handler(CommandHandler("panel", panel_command_handler))
    application.add_handler(CommandHandler("set_rules", set_rules_command_handler))
    application.add_handler(CommandHandler("rules", rules_command_handler))

    # ===================================================================
    # تسجيل معالجات الكولباك (CallbackQuery Handlers) - كاملة
    # ===================================================================

    # القائمة الرئيسية والتنقل
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern=f"^{CallbackData.MAIN_MENU}$"))
    application.add_handler(CallbackQueryHandler(back_callback, pattern=f"^{CallbackData.BACK}$"))
    application.add_handler(CallbackQueryHandler(cancel_session_callback, pattern=f"^{CallbackData.CANCEL_SESSION}$"))

    # القنوات
    application.add_handler(CallbackQueryHandler(add_channel_callback, pattern=f"^{CallbackData.CHANNELS_ADD}$"))
    application.add_handler(CallbackQueryHandler(my_channels_callback, pattern=f"^{CallbackData.CHANNELS_MY}$"))
    application.add_handler(CallbackQueryHandler(delete_channel_callback, pattern=f"^{CallbackData.CHANNELS_DELETE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(select_channel_callback, pattern=f"^{CallbackData.CHANNELS_SELECT_PREFIX}"))

    # المنشورات
    application.add_handler(CallbackQueryHandler(add_15_posts_callback, pattern=f"^{CallbackData.POSTS_ADD_15}$"))
    application.add_handler(CallbackQueryHandler(publish_one_callback, pattern=f"^{CallbackData.POSTS_PUBLISH_ONE}$"))
    application.add_handler(CallbackQueryHandler(my_posts_callback, pattern=f"^{CallbackData.POSTS_MY}$"))
    application.add_handler(CallbackQueryHandler(recycle_posts_callback, pattern=f"^{CallbackData.POSTS_RECYCLE}$"))
    application.add_handler(CallbackQueryHandler(delete_single_post_callback, pattern=f"^{CallbackData.POSTS_DELETE_SINGLE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(confirm_clear_all_posts_callback, pattern=f"^{CallbackData.POSTS_CONFIRM_CLEAR_ALL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(clear_all_posts_callback, pattern=f"^{CallbackData.POSTS_CLEAR_ALL_PREFIX}"))

    # الإحصائيات
    application.add_handler(CallbackQueryHandler(pending_stats_callback, pattern=f"^{CallbackData.STATS_PENDING}$"))
    application.add_handler(CallbackQueryHandler(full_stats_callback, pattern=f"^{CallbackData.STATS_FULL}$"))

    # المجموعات
    application.add_handler(CallbackQueryHandler(my_groups_callback, pattern=f"^{CallbackData.GROUPS_MY}$"))
    application.add_handler(CallbackQueryHandler(group_settings_callback, pattern=f"^{CallbackData.GROUPS_SETTINGS_PREFIX}"))

    # الإعدادات العامة
    application.add_handler(CallbackQueryHandler(settings_menu_callback, pattern=f"^{CallbackData.SETTINGS_MENU}$"))
    application.add_handler(CallbackQueryHandler(toggle_auto_publish_callback, pattern=f"^{CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH}$"))
    application.add_handler(CallbackQueryHandler(toggle_auto_recycle_callback, pattern=f"^{CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE}$"))

    # الجدولة
    application.add_handler(CallbackQueryHandler(schedule_menu_callback, pattern=f"^{CallbackData.SCHEDULE_MENU_PREFIX}"))
    application.add_handler(CallbackQueryHandler(set_interval_minutes_callback, pattern=f"^{CallbackData.SCHEDULE_SET_INTERVAL_MINUTES_PREFIX}"))
    application.add_handler(CallbackQueryHandler(set_interval_hours_callback, pattern=f"^{CallbackData.SCHEDULE_SET_INTERVAL_HOURS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(set_interval_days_callback, pattern=f"^{CallbackData.SCHEDULE_SET_INTERVAL_DAYS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(set_cron_callback, pattern="^schedule:set_cron:"))
    application.add_handler(CallbackQueryHandler(set_days_callback, pattern=f"^{CallbackData.SCHEDULE_SET_DAYS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(set_dates_callback, pattern=f"^{CallbackData.SCHEDULE_SET_DATES_PREFIX}"))
    application.add_handler(CallbackQueryHandler(set_publish_time_callback, pattern=f"^{CallbackData.SCHEDULE_SET_PUBLISH_TIME_PREFIX}"))
    application.add_handler(CallbackQueryHandler(day_select_callback, pattern=f"^{CallbackData.SCHEDULE_DAY_SELECT_PREFIX}"))
    application.add_handler(CallbackQueryHandler(save_days_callback, pattern=f"^{CallbackData.SCHEDULE_SAVE_DAYS}$"))

    # الأمان - تبديل الإعدادات
    application.add_handler(CallbackQueryHandler(
        security_toggle_setting_callback,
        pattern=r"^security:(links|mentions|slow_mode|delete_videos|delete_service|delete_documents|delete_stickers|delete_audio|delete_animation|delete_forwarded|delete_polls|delete_games|delete_voice|delete_video_note|welcome_enabled|goodbye_enabled|antiflood|night_mode|max_length|warn_settings):[0-9-]+$"
    ))

    # الأمان - الكلمات المحظورة
    application.add_handler(CallbackQueryHandler(security_banned_words_menu_callback, pattern=f"^{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}"))
    application.add_handler(CallbackQueryHandler(banned_words_add_callback, pattern=f"^{CallbackData.BANNED_WORDS_ADD_PREFIX}"))
    application.add_handler(CallbackQueryHandler(banned_words_list_callback, pattern=f"^{CallbackData.BANNED_WORDS_LIST_PREFIX}"))
    application.add_handler(CallbackQueryHandler(banned_words_remove_callback, pattern=f"^{CallbackData.BANNED_WORDS_REMOVE_PREFIX}"))

    # الأمان - عقوبات الحذف والتحذير
    application.add_handler(CallbackQueryHandler(security_delete_penalty_callback, pattern=f"^{CallbackData.SECURITY_DELETE_PENALTY_PREFIX}"))
    application.add_handler(CallbackQueryHandler(set_delete_penalty_callback, pattern="^set_delete_penalty:"))
    application.add_handler(CallbackQueryHandler(set_delete_penalty_duration_callback, pattern="^set_delete_penalty_duration:"))
    application.add_handler(CallbackQueryHandler(security_warn_settings_callback, pattern="^security:warn_settings:"))
    application.add_handler(CallbackQueryHandler(security_warn_count_callback, pattern="^warn_count:"))
    application.add_handler(CallbackQueryHandler(set_warn_penalty_callback, pattern="^warn_penalty:"))

    # الأمان - تفعيل/تعطيل الكل
    application.add_handler(CallbackQueryHandler(security_enable_all_callback, pattern=f"^{CallbackData.SECURITY_ENABLE_ALL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(confirm_enable_all_callback, pattern="^confirm_enable_all:"))
    application.add_handler(CallbackQueryHandler(security_disable_all_callback, pattern=f"^{CallbackData.SECURITY_DISABLE_ALL_PREFIX}"))

    # الأمان - إغلاق اللوحة
    application.add_handler(CallbackQueryHandler(security_close_callback, pattern=f"^{CallbackData.SECURITY_CLOSE}$"))

    # اختيار مجموعة للأمان
    application.add_handler(CallbackQueryHandler(security_select_group_callback, pattern=f"^{CallbackData.SECURITY_SELECT_GROUP}"))
    application.add_handler(CallbackQueryHandler(security_refresh_groups_callback, pattern=f"^{CallbackData.SECURITY_REFRESH_GROUPS}$"))

    # العقوبات (Penalty Menu)
    application.add_handler(CallbackQueryHandler(penalty_menu_callback, pattern=f"^{CallbackData.PENALTY_MENU}:"))
    application.add_handler(CallbackQueryHandler(penalty_kick_callback, pattern=f"^{CallbackData.PENALTY_KICK}:"))
    application.add_handler(CallbackQueryHandler(penalty_ban_callback, pattern=f"^{CallbackData.PENALTY_BAN}:"))
    application.add_handler(CallbackQueryHandler(penalty_mute_callback, pattern=f"^{CallbackData.PENALTY_MUTE}:"))
    application.add_handler(CallbackQueryHandler(penalty_warn_callback, pattern="^penalty:warn:"))
    application.add_handler(CallbackQueryHandler(penalty_restrict_callback, pattern="^penalty:restrict:"))
    application.add_handler(CallbackQueryHandler(penalty_none_callback, pattern="^penalty:none:"))
    application.add_handler(CallbackQueryHandler(mute_duration_callback, pattern="^mute_duration:"))

    # الإجراءات المتقدمة للمجموعة
    application.add_handler(CallbackQueryHandler(advanced_actions_callback, pattern=f"^{CallbackData.ADVANCED_ACTIONS}"))
    application.add_handler(CallbackQueryHandler(group_action_ban_callback, pattern=f"^{CallbackData.GROUP_ACTION_BAN}"))
    application.add_handler(CallbackQueryHandler(group_action_mute_callback, pattern=f"^{CallbackData.GROUP_ACTION_MUTE}"))
    application.add_handler(CallbackQueryHandler(group_action_warn_callback, pattern=f"^{CallbackData.GROUP_ACTION_WARN}"))
    application.add_handler(CallbackQueryHandler(group_action_kick_callback, pattern=f"^{CallbackData.GROUP_ACTION_KICK}"))
    application.add_handler(CallbackQueryHandler(group_action_restrict_callback, pattern=f"^{CallbackData.GROUP_ACTION_RESTRICT}"))
    application.add_handler(CallbackQueryHandler(group_action_pin_callback, pattern=f"^{CallbackData.GROUP_ACTION_PIN}"))
    application.add_handler(CallbackQueryHandler(group_action_log_callback, pattern=f"^{CallbackData.GROUP_ACTION_LOG}"))
    application.add_handler(CallbackQueryHandler(group_action_unban_callback, pattern=f"^{CallbackData.GROUP_ACTION_UNBAN}"))

    # لوحة التحكم (قفل/فتح)
    application.add_handler(CallbackQueryHandler(panel_lock_callback_handler, pattern=f"^{CallbackData.PANEL_LOCK_PREFIX}"))
    application.add_handler(CallbackQueryHandler(panel_unlock_callback_handler, pattern=f"^{CallbackData.PANEL_UNLOCK_PREFIX}"))
    application.add_handler(CallbackQueryHandler(panel_close_callback_handler, pattern=f"^{CallbackData.PANEL_CLOSE}$"))

    # المساعدة والدعم
    application.add_handler(CallbackQueryHandler(help_callback, pattern=f"^{CallbackData.HELP}$"))
    application.add_handler(CallbackQueryHandler(support_menu_callback, pattern=f"^{CallbackData.SUPPORT_MENU}$"))
    application.add_handler(CallbackQueryHandler(support_help_callback, pattern=f"^{CallbackData.SUPPORT_HELP}$"))
    application.add_handler(CallbackQueryHandler(support_ticket_callback, pattern=f"^{CallbackData.SUPPORT_TICKET}$"))
    application.add_handler(CallbackQueryHandler(support_back_callback, pattern=f"^{CallbackData.SUPPORT_BACK}$"))

    # التجربة والاشتراك
    application.add_handler(CallbackQueryHandler(trial_callback, pattern=f"^{CallbackData.TRIAL}$"))
    application.add_handler(CallbackQueryHandler(subscribe_menu_callback, pattern=f"^{CallbackData.SUBSCRIBE_MENU}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_1_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_1}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_2_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_2}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_30_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_30}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_90_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_90}$"))

    # المطور والتحديثات
    application.add_handler(CallbackQueryHandler(developer_callback, pattern=f"^{CallbackData.DEVELOPER}$"))
    application.add_handler(CallbackQueryHandler(updates_callback, pattern=f"^{CallbackData.UPDATES}$"))

    # الإحالات
    application.add_handler(CallbackQueryHandler(referral_menu_callback, pattern=f"^{CallbackData.REFERRAL_MENU}$"))
    application.add_handler(CallbackQueryHandler(referral_copy_link_callback, pattern=f"^{CallbackData.REFERRAL_COPY_LINK_PREFIX}"))
    application.add_handler(CallbackQueryHandler(referral_claim_reward_callback, pattern=f"^{CallbackData.REFERRAL_CLAIM_REWARD}$"))
    application.add_handler(CallbackQueryHandler(referral_list_callback, pattern=f"^{CallbackData.REFERRAL_LIST}$"))

    # التذكيرات
    application.add_handler(CallbackQueryHandler(reminder_menu_callback, pattern=f"^{CallbackData.REMINDER_MENU}$"))
    application.add_handler(CallbackQueryHandler(reminder_toggle_sub_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_SUB}$"))
    application.add_handler(CallbackQueryHandler(reminder_toggle_daily_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_DAILY}$"))
    application.add_handler(CallbackQueryHandler(reminder_toggle_weekly_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_WEEKLY}$"))
    application.add_handler(CallbackQueryHandler(reminder_set_days_callback, pattern=f"^{CallbackData.REMINDER_SET_DAYS}$"))
    application.add_handler(CallbackQueryHandler(reminder_set_lang_callback, pattern=f"^{CallbackData.REMINDER_SET_LANG}$"))
    application.add_handler(CallbackQueryHandler(reminder_lang_callback, pattern=f"^{CallbackData.REMINDER_LANG_PREFIX}"))

    # الترجمة
    application.add_handler(CallbackQueryHandler(translation_menu_callback, pattern=f"^{CallbackData.TRANSLATION_MENU}$"))
    application.add_handler(CallbackQueryHandler(translation_off_callback, pattern=f"^{CallbackData.TRANSLATION_OFF}$"))
    application.add_handler(CallbackQueryHandler(translation_set_callback, pattern=f"^{CallbackData.TRANSLATION_SET_PREFIX}"))

    # المسابقات
    application.add_handler(CallbackQueryHandler(contests_menu_callback, pattern=f"^{CallbackData.CONTESTS_MENU}$"))
    application.add_handler(CallbackQueryHandler(contest_join_callback, pattern=f"^{CallbackData.CONTEST_JOIN_PREFIX}"))
    application.add_handler(CallbackQueryHandler(contest_winners_callback, pattern=f"^{CallbackData.CONTEST_WINNERS}$"))
    application.add_handler(CallbackQueryHandler(contests_back_callback, pattern=f"^{CallbackData.CONTESTS_BACK}$"))

    # إحصائيات القنوات والنشر الشامل
    application.add_handler(CallbackQueryHandler(channel_stats_callback, pattern=f"^{CallbackData.CHANNEL_STATS}:"))
    application.add_handler(CallbackQueryHandler(channel_growth_callback, pattern=f"^{CallbackData.CHANNEL_GROWTH}:"))
    application.add_handler(CallbackQueryHandler(channel_stats_refresh_callback, pattern=f"^{CallbackData.CHANNEL_STATS_REFRESH}:"))
    application.add_handler(CallbackQueryHandler(my_channel_stats_callback, pattern=f"^{CallbackData.MY_CHANNEL_STATS}$"))
    application.add_handler(CallbackQueryHandler(publish_all_channels_callback_handler, pattern=f"^{CallbackData.PUBLISH_ALL_CHANNELS}$"))

    # NSFW
    application.add_handler(CallbackQueryHandler(nsfw_settings_callback, pattern=f"^{CallbackData.NSFW_SETTINGS}$"))
    application.add_handler(CallbackQueryHandler(nsfw_toggle_callback, pattern=f"^{CallbackData.NSFW_TOGGLE}$"))
    application.add_handler(CallbackQueryHandler(nsfw_threshold_set_callback, pattern=f"^{CallbackData.NSFW_THRESHOLD_SET}$"))

    # اشتراك إجباري
    application.add_handler(CallbackQueryHandler(check_subscribe_callback_handler, pattern=f"^{CallbackData.CHECK_SUBSCRIBE}$"))

    # اللغة والأوامر النصية
    application.add_handler(CallbackQueryHandler(language_callback, pattern=r"^lang_"))
    application.add_handler(CallbackQueryHandler(handle_text_callbacks, pattern="^(rank|top|schedule_post|language)$"))

    # ===================================================================
    # لوحة الأدمن (Admin Panel Callbacks)
    # ===================================================================
    application.add_handler(CallbackQueryHandler(admin_panel_callback, pattern=f"^{CallbackData.ADMIN_PANEL}$"))
    application.add_handler(CallbackQueryHandler(admin_users_callback, pattern=f"^{CallbackData.ADMIN_USERS}$"))
    application.add_handler(CallbackQueryHandler(admin_banned_users_callback, pattern=f"^{CallbackData.ADMIN_BANNED_USERS}$"))
    application.add_handler(CallbackQueryHandler(admin_unban_all_users_callback, pattern=f"^{CallbackData.ADMIN_UNBAN_ALL_USERS}$"))
    application.add_handler(CallbackQueryHandler(admin_all_channels_callback, pattern=f"^{CallbackData.ADMIN_ALL_CHANNELS}$"))
    application.add_handler(CallbackQueryHandler(admin_banned_channels_callback, pattern=f"^{CallbackData.ADMIN_BANNED_CHANNELS}$"))
    application.add_handler(CallbackQueryHandler(admin_activate_all_channels_callback, pattern=f"^{CallbackData.ADMIN_ACTIVATE_ALL_CHANNELS}$"))
    application.add_handler(CallbackQueryHandler(admin_groups_callback, pattern=f"^{CallbackData.ADMIN_GROUPS}$"))
    application.add_handler(CallbackQueryHandler(admin_banned_groups_callback, pattern=f"^{CallbackData.ADMIN_BANNED_GROUPS}$"))
    application.add_handler(CallbackQueryHandler(admin_unban_all_groups_callback, pattern=f"^{CallbackData.ADMIN_UNBAN_ALL_GROUPS}$"))
    application.add_handler(CallbackQueryHandler(admin_bot_channels_callback, pattern=f"^{CallbackData.ADMIN_BOT_CHANNELS}$"))
    application.add_handler(CallbackQueryHandler(admin_banned_bot_channels_callback, pattern=f"^{CallbackData.ADMIN_BANNED_BOT_CHANNELS}$"))
    application.add_handler(CallbackQueryHandler(admin_unban_all_bot_channels_callback, pattern=f"^{CallbackData.ADMIN_UNBAN_ALL_BOT_CHANNELS}$"))
    application.add_handler(CallbackQueryHandler(admin_monitor_users_callback, pattern=f"^{CallbackData.ADMIN_MONITOR_USERS}$"))
    application.add_handler(CallbackQueryHandler(admin_add_admin_callback, pattern=f"^{CallbackData.ADMIN_ADD_ADMIN}$"))
    application.add_handler(CallbackQueryHandler(admin_remove_admin_callback, pattern=f"^{CallbackData.ADMIN_REMOVE_ADMIN}$"))
    application.add_handler(CallbackQueryHandler(admin_ram_callback, pattern=f"^{CallbackData.ADMIN_RAM}$"))
    application.add_handler(CallbackQueryHandler(admin_stats_callback, pattern=f"^{CallbackData.ADMIN_STATS}$"))
    application.add_handler(CallbackQueryHandler(admin_metrics_callback, pattern=f"^{CallbackData.ADMIN_METRICS}$"))
    application.add_handler(CallbackQueryHandler(admin_backup_callback, pattern=f"^{CallbackData.ADMIN_BACKUP}$"))
    application.add_handler(CallbackQueryHandler(admin_restore_backup_callback, pattern=f"^{CallbackData.ADMIN_RESTORE_BACKUP}$"))
    application.add_handler(CallbackQueryHandler(admin_restore_backup_select_callback, pattern=f"^{CallbackData.ADMIN_RESTORE_BACKUP_SELECT_PREFIX}"))
    application.add_handler(CallbackQueryHandler(confirm_restore_callback, pattern="^confirm_restore:"))
    application.add_handler(CallbackQueryHandler(admin_backup_settings_callback, pattern=f"^{CallbackData.ADMIN_BACKUP_SETTINGS}$"))
    application.add_handler(CallbackQueryHandler(admin_toggle_auto_backup_callback, pattern=f"^{CallbackData.ADMIN_TOGGLE_AUTO_BACKUP}$"))
    application.add_handler(CallbackQueryHandler(admin_change_interval_callback, pattern=f"^{CallbackData.ADMIN_CHANGE_INTERVAL}$"))
    application.add_handler(CallbackQueryHandler(admin_send_update_callback, pattern=f"^{CallbackData.ADMIN_SEND_UPDATE}$"))
    application.add_handler(CallbackQueryHandler(admin_set_update_channel_callback, pattern=f"^{CallbackData.ADMIN_SET_UPDATE_CHANNEL}$"))
    application.add_handler(CallbackQueryHandler(admin_show_update_channel_callback, pattern=f"^{CallbackData.ADMIN_SHOW_UPDATE_CHANNEL}$"))
    application.add_handler(CallbackQueryHandler(admin_updates_callback, pattern=f"^{CallbackData.ADMIN_UPDATES}$"))
    application.add_handler(CallbackQueryHandler(admin_force_subscribe_callback, pattern=f"^{CallbackData.ADMIN_FORCE_SUBSCRIBE}$"))
    application.add_handler(CallbackQueryHandler(admin_set_force_channel_callback, pattern=f"^{CallbackData.ADMIN_SET_FORCE_CHANNEL}$"))
    application.add_handler(CallbackQueryHandler(admin_broadcast_callback, pattern=f"^{CallbackData.ADMIN_BROADCAST}$"))
    application.add_handler(CallbackQueryHandler(admin_confirm_broadcast_callback, pattern=f"^{CallbackData.ADMIN_CONFIRM_BROADCAST}$"))
    application.add_handler(CallbackQueryHandler(admin_support_tickets_callback, pattern=f"^{CallbackData.ADMIN_SUPPORT_TICKETS}$"))
    application.add_handler(CallbackQueryHandler(admin_delete_all_tickets_callback, pattern=f"^{CallbackData.ADMIN_DELETE_ALL_TICKETS}$"))
    application.add_handler(CallbackQueryHandler(admin_confirm_delete_tickets_callback, pattern=f"^{CallbackData.ADMIN_CONFIRM_DELETE_TICKETS}$"))
    application.add_handler(CallbackQueryHandler(admin_manage_sendcode_callback, pattern=f"^{CallbackData.ADMIN_MANAGE_SENDCODE}$"))
    application.add_handler(CallbackQueryHandler(admin_set_sendcode_user_callback, pattern=f"^{CallbackData.ADMIN_SET_SENDCODE_USER}$"))
    application.add_handler(CallbackQueryHandler(admin_show_log_channel_callback, pattern=f"^{CallbackData.ADMIN_SHOW_LOG_CHANNEL}$"))
    application.add_handler(CallbackQueryHandler(admin_set_log_channel_callback, pattern=f"^{CallbackData.ADMIN_SET_LOG_CHANNEL}$"))

    # إدارة الردود والكلمات المحظورة
    application.add_handler(CallbackQueryHandler(admin_replies_callback, pattern=f"^{CallbackData.ADMIN_REPLIES}$"))
    application.add_handler(CallbackQueryHandler(admin_add_reply_callback, pattern=f"^{CallbackData.ADMIN_ADD_REPLY}$"))
    application.add_handler(CallbackQueryHandler(admin_list_replies_callback, pattern=f"^{CallbackData.ADMIN_LIST_REPLIES}$"))
    application.add_handler(CallbackQueryHandler(admin_del_reply_callback, pattern=f"^{CallbackData.ADMIN_DEL_REPLY}$"))
    application.add_handler(CallbackQueryHandler(admin_banned_words_callback, pattern=f"^{CallbackData.ADMIN_BANNED_WORDS}$"))
    application.add_handler(CallbackQueryHandler(admin_add_banned_word_callback, pattern=f"^{CallbackData.ADMIN_ADD_BANNED_WORD}$"))
    application.add_handler(CallbackQueryHandler(admin_list_banned_words_callback, pattern=f"^{CallbackData.ADMIN_LIST_BANNED_WORDS}$"))
    application.add_handler(CallbackQueryHandler(admin_remove_banned_word_callback, pattern=f"^{CallbackData.ADMIN_REMOVE_BANNED_WORD}$"))

    # المسابقات (أدمن)
    application.add_handler(CallbackQueryHandler(admin_create_contest_callback, pattern=f"^{CallbackData.ADMIN_CREATE_CONTEST}$"))
    application.add_handler(CallbackQueryHandler(admin_declare_winner_callback, pattern=f"^{CallbackData.ADMIN_DECLARE_WINNER}$"))
    application.add_handler(CallbackQueryHandler(admin_del_contest_callback, pattern=f"^{CallbackData.ADMIN_DEL_CONTEST_PREFIX}"))

    # الردود التلقائية
    application.add_handler(CallbackQueryHandler(admin_auto_reply_callback, pattern=f"^{CallbackData.ADMIN_AUTO_REPLY}$"))
    application.add_handler(CallbackQueryHandler(auto_reply_menu_callback, pattern=f"^{CallbackData.AUTO_REPLY_MENU_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_toggle_callback, pattern=f"^{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_admins_callback, pattern=f"^{CallbackData.AUTO_REPLY_ADMINS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_reset_callback, pattern=f"^{CallbackData.AUTO_REPLY_RESET_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_confirm_reset_callback, pattern=f"^{CallbackData.AUTO_REPLY_CONFIRM_RESET_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_cancel_callback, pattern=f"^{CallbackData.AUTO_REPLY_CANCEL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_stats_callback, pattern=f"^{CallbackData.AUTO_REPLY_STATS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(user_auto_reply_toggle_callback, pattern=f"^{CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX}"))

    # ===================================================================
    # تسجيل معالجات الرسائل (Message Handlers)
    # ===================================================================
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler))
    application.add_handler(MessageHandler(filters.CAPTION & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, message_handler_main))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.AUDIO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.VOICE & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.ANIMATION & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, message_handler_main))

    # ===================================================================
    # تسجيل معالجات الأحداث الإضافية
    # ===================================================================
    application.add_handler(ChatJoinRequestHandler(chat_join_request_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_chat_member_handler))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback_handler))
    application.add_handler(ChatMemberHandler(track_chat_add, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER, delete_service_messages))

    # ===================================================================
    # تعيين أوامر البوت
    # ===================================================================
    commands = [
        BotCommand("start", "بدء البوت"),
        BotCommand("trial", "تجربة مجانية"),
        BotCommand("subscribe", "الاشتراك"),
        BotCommand("syncgroup", "تفعيل المجموعة"),
        BotCommand("security", "إعدادات الأمان"),
        BotCommand("register_hidden_owner", "تسجيل مالك مخفي"),
        BotCommand("add_hidden_admin", "إضافة مشرف مخفي"),
        BotCommand("remove_hidden_admin", "إزالة مشرف مخفي"),
        BotCommand("list_hidden_admins", "عرض المشرفين المخفيين"),
        BotCommand("rank", "رتبتك"),
        BotCommand("top", "أفضل 10"),
        BotCommand("stats", "إحصائيات القناة"),
        BotCommand("lock", "قفل المجموعة"),
        BotCommand("unlock", "فتح المجموعة"),
        BotCommand("schedule", "جدولة منشور"),
        BotCommand("panel", "لوحة التحكم"),
        BotCommand("language", "تغيير اللغة"),
        BotCommand("support", "مركز الدعم"),
        BotCommand("help", "المساعدة"),
        BotCommand("developer", "المطور"),
        BotCommand("updates", "آخر التحديثات"),
        BotCommand("set_rules", "تعيين قوانين المجموعة"),
        BotCommand("rules", "عرض قوانين المجموعة"),
    ]
    await application.bot.set_my_commands(commands)

    # ===================================================================
    # تشغيل المهام الخلفية
    # ===================================================================
    task_manager.create_task(safe_loop(lambda: auto_publish_loop_improved(application.bot), "auto_publish"))
    task_manager.create_task(safe_loop(auto_backup, "auto_backup"))
    task_manager.create_task(safe_loop(lambda: run_scheduled_posts_loop_improved(application.bot), "scheduled_posts"))
    task_manager.create_task(safe_loop(lambda: send_reminders_loop_improved(application.bot), "reminders"))
    task_manager.create_task(safe_loop(cleanup_expired_sessions_improved, "cleanup_sessions"))
    task_manager.create_task(safe_loop(self_ping_loop, "self_ping"))
    task_manager.create_task(safe_loop(broadcast_stats_periodically, "broadcast_stats"))
    task_manager.create_task(safe_loop(cleanup_points_cache, "cleanup_points"))
    task_manager.create_task(safe_loop(memory_monitor, "memory_monitor"))
    task_manager.create_task(safe_loop(lambda: auto_close_contests_loop(application.bot), "auto_close_contests"))
    task_manager.create_task(safe_loop(lambda: refresh_group_admins_and_hidden_owners_loop(application.bot), "refresh_admins"))
    task_manager.create_task(safe_loop(memory_optimizer_loop, "memory_optimizer"))

    # ===================================================================
    # تشغيل خادم الويب
    # ===================================================================
    port = int(os.getenv("PORT", "10000"))
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("HEROKU_APP_NAME")

    try:
        await setup_unified_web_server(application, port)
        logger.info(f"✅ خادم الويب يعمل على المنفذ {port}")
    except Exception as e:
        logger.error(f"❌ فشل بدء خادم الويب: {e}")
        raise

    # ===================================================================
    # تشغيل البوت (Webhook أو Polling)
    # ===================================================================
    if hostname:
        await application.initialize()
        await application.start()
        webhook_url = f"https://{hostname}/{TOKEN}"
        try:
            await application.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "chat_member", "chat_join_request", "pre_checkout_query"]
            )
            logger.info(f"✅ تم تعيين Webhook إلى: {webhook_url}")
        except Exception as e:
            logger.error(f"❌ فشل تعيين Webhook: {e}")
            raise

        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("🛑 تم إيقاف البوت")
    else:
        logger.info("🔄 استخدام Polling (بدون Webhook)")
        await application.bot.delete_webhook()
        await run_polling_safe(application)

# ===================================================================
# 45. تشغيل البوت
# ===================================================================
if __name__ == "__main__":
    try:
        os.environ["WEB_CONCURRENCY"] = "1"
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 تم إيقاف البوت")
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {e}")
        traceback.print_exc()
        sys.exit(1)

