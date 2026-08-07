
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ريلاكس مانيجر - بوت متكامل لإدارة القنوات والمجموعات
الإصدار: 21.0.0 - النسخة العالمية الكاملة مع جميع الميزات
المطور: @RelaxMgr
"""

# ===================================================================
# ===== 1. استيراد المكتبات والتحقق من الإصدار =====
# ===================================================================

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
from collections import defaultdict, deque
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


def check_python_version():
    """التحقق من إصدار بايثون المطلوب (3.8+)"""
    required_version = (3, 8)
    current_version = sys.version_info
    if current_version < required_version:
        print(f"❌ يحتاج البوت إلى بايثون {required_version[0]}.{required_version[1]} أو أحدث")
        print(f"📌 الإصدار الحالي: {current_version[0]}.{current_version[1]}")
        sys.exit(1)


check_python_version()

# ===================================================================
# ===== 2. التحقق من توفر Jinja2 =====
# ===================================================================

JINJA2_AVAILABLE = False
try:
    import jinja2
    JINJA2_AVAILABLE = True
except ImportError:
    print("⚠️ Jinja2 غير متاح - سيتم استخدام HTML النقي")

# ===================================================================
# ===== 3. إعداد المسارات (Paths) =====
# ===================================================================

def get_base_path() -> Path:
    """الحصول على المسار الأساسي للبوت"""
    return Path(__file__).parent.resolve()


BASE_PATH = get_base_path()


def get_writable_path(base_path: Path, subdir: str) -> Path:
    """الحصول على مسار قابل للكتابة مع محاولة عدة مواقع"""
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


def get_temp_path() -> Path:
    """الحصول على المسار المؤقت"""
    return get_writable_path(BASE_PATH, "temp")


# ===================================================================
# ===== 4. تعريف المسارات الرئيسية =====
# ===================================================================

DATA_PATH = get_writable_path(BASE_PATH, "data")
DB_PATH = DATA_PATH / "bot_data.db"
BACKUP_DIR = get_writable_path(BASE_PATH, "backups")
LOG_PATH = get_writable_path(BASE_PATH, "logs") / "bot.log"
SECURITY_LOG = get_writable_path(BASE_PATH, "logs") / "security.log"
ERROR_LOG = get_writable_path(BASE_PATH, "logs") / "errors.log"
ACCESS_LOG = get_writable_path(BASE_PATH, "logs") / "access.log"
TEMP_PATH = get_temp_path()
STATIC_PATH = get_writable_path(BASE_PATH, "static")
TEMPLATES_PATH = get_writable_path(BASE_PATH, "templates")
LANG_PATH = BASE_PATH / "lang"
PLUGINS_PATH = BASE_PATH / "plugins"

# إنشاء المجلدات
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
DATA_PATH.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
TEMP_PATH.mkdir(parents=True, exist_ok=True)
STATIC_PATH.mkdir(parents=True, exist_ok=True)
TEMPLATES_PATH.mkdir(parents=True, exist_ok=True)
LANG_PATH.mkdir(parents=True, exist_ok=True)
PLUGINS_PATH.mkdir(parents=True, exist_ok=True)

# ===================================================================
# ===== 5. تثبيت الحزم المطلوبة تلقائياً =====
# ===================================================================

def ensure_package(package_name: str, import_name: str = None) -> bool:
    """
    تثبيت حزمة بايثون إذا لم تكن موجودة
    Args:
        package_name: اسم الحزمة للتثبيت
        import_name: اسم الاستيراد (إذا كان مختلفاً عن package_name)
    Returns:
        bool: نجاح التثبيت
    """
    if import_name is None:
        import_name = package_name
    try:
        __import__(import_name)
        return True
    except ImportError:
        try:
            import subprocess
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

# حزم اختيارية
PYOTP_AVAILABLE = ensure_package("pyotp")
ZSTD_AVAILABLE = ensure_package("zstandard")
CV2_AVAILABLE = ensure_package("opencv-python-headless", "cv2")
GOOGLE_AUTH_AVAILABLE = False
try:
    ensure_package("google-auth", "google.auth")
    ensure_package("google-auth-oauthlib", "google_auth_oauthlib")
    ensure_package("google-api-python-client", "googleapiclient")
    GOOGLE_AUTH_AVAILABLE = True
except:
    GOOGLE_AUTH_AVAILABLE = False

# استيراد الحزم الاختيارية
if PYOTP_AVAILABLE:
    import pyotp
if ZSTD_AVAILABLE:
    import zstandard
    ZSTD_COMPRESSOR = zstandard.ZstdCompressor(level=3)
    ZSTD_DECOMPRESSOR = zstandard.ZstdDecompressor()
if CV2_AVAILABLE:
    import cv2
    import numpy as np
if GOOGLE_AUTH_AVAILABLE:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

# ===================================================================
# ===== 6. استيراد المكتبات الإضافية =====
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
# ===== 7. فلتر البيانات الحساسة للتسجيل =====
# ===================================================================

class SensitiveDataFilter(logging.Filter):
    """فلتر لإخفاء البيانات الحساسة في السجلات"""
    def filter(self, record):
        msg = record.getMessage()
        if TOKEN and TOKEN in msg:
            msg = msg.replace(TOKEN, "[TOKEN_HIDDEN]")
        if ENCRYPTION_KEY and isinstance(ENCRYPTION_KEY, bytes):
            try:
                key_str = ENCRYPTION_KEY.decode()
                if key_str in msg:
                    msg = msg.replace(key_str, "[ENCRYPTION_KEY_HIDDEN]")
            except:
                pass
        if BACKUP_ENCRYPTION_KEY and isinstance(BACKUP_ENCRYPTION_KEY, bytes):
            try:
                key_str = BACKUP_ENCRYPTION_KEY.decode()
                if key_str in msg:
                    msg = msg.replace(key_str, "[BACKUP_KEY_HIDDEN]")
            except:
                pass
        record.msg = msg
        return True

# ===================================================================
# ===== 8. إعداد نظام التسجيل (Logging) =====
# ===================================================================

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

# إضافة فلتر البيانات الحساسة لجميع المعالجات
for handler in logger.handlers:
    handler.addFilter(SensitiveDataFilter())

# ===================================================================
# ===== 9. تحميل متغيرات البيئة =====
# ===================================================================

def load_env_files():
    """تحميل ملفات البيئة المتعددة"""
    from dotenv import load_dotenv
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
    """الحصول على متغير بيئي مع قيمة افتراضية"""
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


# ===================================================================
# ===== 10. متغيرات البيئة الأساسية =====
# ===================================================================

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

# إعدادات Google Drive
GOOGLE_DRIVE_FOLDER_ID = get_env_or_default("GOOGLE_DRIVE_FOLDER_ID", "", str)
CLOUD_BACKUP_ENABLED = get_env_or_default("CLOUD_BACKUP_ENABLED", False, bool) and GOOGLE_AUTH_AVAILABLE
GOOGLE_CREDENTIALS_FILE = get_env_or_default("GOOGLE_CREDENTIALS_FILE", "credentials.json", str)
TOKEN_FILE = get_env_or_default("TOKEN_FILE", "token.json", str)

# إعدادات خادم الويب
RENDER_PORT = int(os.getenv("PORT", "10000"))
WEB_PORT = get_env_or_default("WEB_PORT", RENDER_PORT, int)
if WEB_PORT == 8080 and RENDER_PORT != 8080:
    WEB_PORT = RENDER_PORT

WEB_HOST = get_env_or_default("WEB_HOST", "0.0.0.0", str)
WEB_PASSWORD = get_env_or_default("WEB_PASSWORD", "", str)
if not WEB_PASSWORD and os.getenv('ENVIRONMENT', 'development') == 'production':
    print("⚠️ تحذير أمني: WEB_PASSWORD غير معيّنة في بيئة الإنتاج! سيتم طلب كلمة مرور عشوائية.")
    WEB_PASSWORD = secrets.token_urlsafe(16)
    print(f"🔑 كلمة المرور المؤقتة: {WEB_PASSWORD}")
WEB_USERNAME = get_env_or_default("WEB_USERNAME", "admin", str)
WEB_SECRET_KEY = get_env_or_default("WEB_SECRET_KEY", secrets.token_urlsafe(32), str)
WEB_SESSION_TIMEOUT = get_env_or_default("WEB_SESSION_TIMEOUT", 3600, int)
WEB_RATE_LIMIT = get_env_or_default("WEB_RATE_LIMIT", 100, int)
WEB_RATE_WINDOW = get_env_or_default("WEB_RATE_WINDOW", 60, int)

# إعدادات الأداء
BATTERY_SAVER_MODE = get_env_or_default("BATTERY_SAVER_MODE", False, bool)

DEFAULT_PUBLISH_INTERVAL_SECONDS = 720
CLEANUP_SLEEP = 3600

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

WEB_PORT_USED = WEB_PORT

# ===================================================================
# ===== 11. نظام التشفير =====
# ===================================================================

def derive_key_from_password(password: str, salt: bytes) -> bytes:
    """اشتقاق مفتاح تشفير من كلمة مرور باستخدام PBKDF2"""
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key


def get_encryption_key() -> bytes:
    """
    الحصول على مفتاح التشفير من عدة مصادر:
    1. keyring
    2. ملفات .db_key و .db_salt
    3. متغير البيئة DB_ENCRYPTION_PASSWORD
    4. إنشاء مفتاح عشوائي
    """
    try:
        import keyring
        key = keyring.get_password("relax_bot", "db_key")
        if key:
            return base64.urlsafe_b64decode(key)
    except ImportError:
        pass

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
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
            with open(salt_file, 'wb') as f:
                f.write(salt)
            try:
                import keyring
                keyring.set_password("relax_bot", "db_key", base64.urlsafe_b64encode(key).decode())
            except:
                pass
        except:
            pass
        print("✅ تم إنشاء مفتاح التشفير من متغير البيئة")
        return key

    if not sys.stdin.isatty():
        print("🔐 بيئة غير تفاعلية - إنشاء مفتاح عشوائي")
        key = Fernet.generate_key()
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
        except:
            pass
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
        print("⚠️ فشل في الحصول على كلمة المرور - استخدام مفتاح عشوائي")
        key = Fernet.generate_key()
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
        except:
            pass
        return key


ENCRYPTION_KEY = get_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)


def get_backup_encryption_key() -> bytes:
    """الحصول على مفتاح تشفير النسخ الاحتياطية"""
    backup_key_file = DATA_PATH / ".backup_key"
    if backup_key_file.exists():
        try:
            with open(backup_key_file, 'rb') as f:
                return f.read()
        except:
            pass
    new_key = Fernet.generate_key()
    try:
        with open(backup_key_file, 'wb') as f:
            f.write(new_key)
    except:
        pass
    print("✅ تم توليد مفتاح جديد لتشفير النسخ الاحتياطية")
    return new_key


BACKUP_ENCRYPTION_KEY = get_backup_encryption_key()
BACKUP_CIPHER = Fernet(BACKUP_ENCRYPTION_KEY)

# ===================================================================
# ===== 12. نظام التخزين المؤقت =====
# ===================================================================

_background_tasks_started = False

try:
    from cachetools import TTLCache, LRUCache
    CACHETOOLS_AVAILABLE = True
    _admin_cache = TTLCache(maxsize=1000, ttl=60)
    _security_cache = TTLCache(maxsize=500, ttl=30)
    _translation_cache = LRUCache(maxsize=200)
    _auth_cache = TTLCache(maxsize=1000, ttl=30)
except ImportError:
    CACHETOOLS_AVAILABLE = False
    _admin_cache = {}
    _security_cache = {}
    _translation_cache = {}
    _auth_cache = {}
    _auth_cache_time = {}
    _ADMIN_CACHE_TTL = 30
    _SECURITY_CACHE_TTL = 30
    _TRANSLATION_CACHE_SIZE = 500
    _AUTH_CACHE_TTL = 30

_security_cache_time = {}
_security_cache_ttl = 30

_translation_cache_lock = asyncio.Lock()
user_translation_settings_cache = {}
_user_translation_cache_lock = asyncio.Lock()


class TimedLRUCache:
    """تخزين مؤقت مع انتهاء صلاحية LRU"""
    def __init__(self, maxsize=200, ttl=3600):
        self.cache = {}
        self.maxsize = maxsize
        self.ttl = ttl
        self._lock = asyncio.Lock()

    async def get(self, key):
        """الحصول على قيمة من التخزين المؤقت"""
        async with self._lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if time_module.time() - timestamp < self.ttl:
                    return value
                else:
                    del self.cache[key]
            return None

    async def set(self, key, value):
        """تخزين قيمة في التخزين المؤقت"""
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
            self.cache[key] = (value, time_module.time())
            if len(self.cache) > self.maxsize:
                oldest = min(self.cache.keys(), key=lambda k: self.cache[k][1])
                del self.cache[oldest]

    async def clear(self):
        """مسح التخزين المؤقت"""
        async with self._lock:
            self.cache.clear()


_translation_cache = TimedLRUCache(maxsize=500, ttl=3600)

# ===================================================================
# ===== 13. إعدادات NSFW =====
# ===================================================================

SIGHTENGINE_API_USER = os.getenv("SIGHTENGINE_API_USER", "")
SIGHTENGINE_API_SECRET = os.getenv("SIGHTENGINE_API_SECRET", "")
NSFW_ENABLED = get_env_or_default("NSFW_ENABLED", True, bool)
NSFW_THRESHOLD = get_env_or_default("NSFW_THRESHOLD", 0.7, float)
NSFW_MAX_FILE_SIZE = get_env_or_default("NSFW_MAX_FILE_SIZE", 5 * 1024 * 1024, int)
NSFW_MAX_VIDEO_SIZE = get_env_or_default("NSFW_MAX_VIDEO_SIZE", 10 * 1024 * 1024, int)
NSFW_FRAMES = get_env_or_default("NSFW_FRAMES", 5, int)
NSFW_CACHE = {}
NSFW_CACHE_TTL = 60
_NSFW_CACHE_LOCK = asyncio.Lock()

MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 20 * 1024 * 1024))
MAX_CHANNELS_PER_CYCLE = int(os.getenv('MAX_CHANNELS_PER_CYCLE', '20'))
PUBLISH_RETRY_DELAY = 300
MAX_POSTS_PER_SESSION = 50
MAX_UNPUBLISHED_POSTS = 1000
DB_TIMEOUT = 30
MAX_CONNECTIONS = 20
SESSION_TIMEOUT_SECONDS = 300

ANONYMOUS_ADMIN_ID = int(os.getenv("ANONYMOUS_ADMIN_ID", "1087968824"))

# ===================================================================
# ===== 14. اللغات المدعومة =====
# ===================================================================

SUPPORTED_LANGUAGES = {
    'ar': 'العربية 🇸🇦',
    'en': 'English 🇬🇧',
    'fr': 'Français 🇫🇷',
    'tr': 'Türkçe 🇹🇷',
    'zh': '中文 🇨🇳',
    'ru': 'Русский 🇷🇺',
    'de': 'Deutsch 🇩🇪',
    'es': 'Español 🇪🇸',
    'it': 'Italiano 🇮🇹',
    'pt': 'Português 🇵🇹',
    'ja': '日本語 🇯🇵',
    'ko': '한국어 🇰🇷'
}

# ===================================================================
# ===== 15. نظام الكلمات المحظورة =====
# ===================================================================

BANNED_WORDS_FILE = BASE_PATH / "banned_words.txt"
BANNED_PATTERNS = []
_BANNED_PATTERNS_LOCK = asyncio.Lock()


def load_banned_words_from_file(file_path: Path) -> List[str]:
    """
    تحميل الكلمات المحظورة من ملف نصي
    - كل كلمة في سطر منفصل
    - # للتعليق
    - * للتعبيرات النمطية
    """
    words = []
    if not file_path.exists():
        print(f"⚠️ ملف {file_path} غير موجود، سيتم إنشاؤه فارغاً")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("# قائمة الكلمات المحظورة - كل كلمة في سطر منفصل\n")
                f.write("# ابدأ السطر بـ # للتعليق\n")
                f.write("# استخدم * للتعبيرات النمطية (مثل: سكس.*\n")
                f.write("\n")
                f.write("بورن\nسكس\nجنس\nعري\nخمر\nخمور\nمخدرات\nحشيش\nكحول\nدعارة\n")
            print(f"✅ تم إنشاء ملف {file_path} مع كلمات افتراضية")
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
        print(f"✅ تم تحميل {len(words)} كلمة محظورة من {file_path}")
    except Exception as e:
        print(f"❌ فشل تحميل الكلمات المحظورة: {e}")
    return words


async def rebuild_banned_patterns():
    """إعادة بناء الأنماط المحظورة من قاعدة البيانات"""
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

# ===================================================================
# ===== 16. نظام Redis للتخزين المؤقت =====
# ===================================================================

try:
    import aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️ مكتبة aioredis غير مثبتة، سيتم استخدام التخزين المؤقت في الذاكرة")


class CacheManager:
    """مدير التخزين المؤقت (Redis + Memory)"""
    def __init__(self):
        self.redis = None
        self.use_redis = REDIS_AVAILABLE and os.getenv("REDIS_URL")
        self.local_cache = {}

    async def init(self):
        """تهيئة اتصال Redis"""
        if self.use_redis:
            try:
                self.redis = await aioredis.from_url(os.getenv("REDIS_URL"))
                await self.redis.ping()
                logger.info("✅ تم الاتصال بـ Redis")
            except Exception as e:
                logger.warning(f"⚠️ فشل الاتصال بـ Redis: {e}")
                self.use_redis = False

    async def get(self, key: str):
        """الحصول على قيمة من التخزين المؤقت"""
        if self.use_redis:
            try:
                value = await self.redis.get(key)
                if value:
                    return json.loads(value)
            except:
                pass
        return self.local_cache.get(key)

    async def set(self, key: str, value: Any, ttl: int = 300):
        """تخزين قيمة في التخزين المؤقت"""
        if self.use_redis:
            try:
                await self.redis.setex(key, ttl, json.dumps(value))
                return
            except:
                pass
        self.local_cache[key] = value

    async def delete(self, key: str):
        """حذف قيمة من التخزين المؤقت"""
        if self.use_redis:
            try:
                await self.redis.delete(key)
            except:
                pass
        self.local_cache.pop(key, None)


cache_manager = CacheManager()

# ===================================================================
# ===== 17. دوال الوقت =====
# ===================================================================

def utc_now():
    """الحصول على الوقت الحالي بتوقيت UTC"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def mecca_now():
    """الحصول على الوقت الحالي بتوقيت مكة المكرمة (UTC+3)"""
    return utc_now() + timedelta(hours=3)


def utc_now_iso():
    """الحصول على الوقت الحالي بتوقيت UTC بصيغة ISO"""
    return utc_now().isoformat()


def mecca_now_iso():
    """الحصول على الوقت الحالي بتوقيت مكة بصيغة ISO"""
    return mecca_now().isoformat()


def to_naive(dt):
    """تحويل وقت مع منطقة زمنية إلى وقت بدون منطقة زمنية"""
    if dt is None:
        return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def mecca_to_utc(mecca_dt):
    """تحويل وقت من توقيت مكة إلى UTC"""
    if mecca_dt is None:
        return None
    if hasattr(mecca_dt, 'tzinfo') and mecca_dt.tzinfo is not None:
        mecca_dt = mecca_dt.replace(tzinfo=None)
    return mecca_dt - timedelta(hours=3)


def utc_to_mecca(utc_dt):
    """تحويل وقت من UTC إلى توقيت مكة"""
    if utc_dt is None:
        return None
    if hasattr(utc_dt, 'tzinfo') and utc_dt.tzinfo is not None:
        utc_dt = utc_dt.replace(tzinfo=None)
    return utc_dt + timedelta(hours=3)

# ===================================================================
# ===== 18. دوال كشف NSFW =====
# ===================================================================

async def check_nsfw_cached(image_bytes: bytes, cache_key: str = None) -> dict:
    """كشف NSFW مع تخزين مؤقت"""
    if cache_key is None:
        cache_key = hashlib.md5(image_bytes).hexdigest()
    async with _NSFW_CACHE_LOCK:
        if cache_key in NSFW_CACHE:
            cached_data, cached_time = NSFW_CACHE[cache_key]
            if time_module.time() - cached_time < NSFW_CACHE_TTL:
                return cached_data
    result = await check_nsfw_image(image_bytes)
    async with _NSFW_CACHE_LOCK:
        NSFW_CACHE[cache_key] = (result, time_module.time())
        if len(NSFW_CACHE) > 100:
            expired_keys = [k for k, (_, t) in NSFW_CACHE.items() if time_module.time() - t > NSFW_CACHE_TTL]
            for k in expired_keys:
                del NSFW_CACHE[k]
    return result


async def check_nsfw_image(image_bytes: bytes) -> dict:
    """كشف NSFW في الصورة باستخدام SightEngine API"""
    try:
        if not SIGHTENGINE_API_USER or not SIGHTENGINE_API_SECRET:
            return {"nsfw": False, "score": 0, "error": "API غير مفعل"}

        # ضغط الصورة لتحسين الأداء
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((800, 800))
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=80)
        compressed = buffer.getvalue()
        image_b64 = base64.b64encode(compressed).decode('utf-8')

        async with aiohttp.ClientSession() as session:
            url = "https://api.sightengine.com/1.0/check.json"
            params = {
                "models": "nudity-2.0,wad",
                "api_user": SIGHTENGINE_API_USER,
                "api_secret": SIGHTENGINE_API_SECRET,
                "image": image_b64
            }
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status != 200:
                    return {"nsfw": False, "score": 0, "error": f"فشل الاتصال ({resp.status})"}
                data = await resp.json()
                nsfw_score = data.get("nudity", {}).get("safe", 1)
                nsfw_score = 1 - nsfw_score
                wad = max(
                    data.get("weapon", 0) or 0,
                    data.get("drugs", 0) or 0,
                    data.get("alcohol", 0) or 0
                )
                faces = data.get("faces", 0) or 0
                return {
                    "nsfw": nsfw_score > NSFW_THRESHOLD or wad > NSFW_THRESHOLD,
                    "nsfw_score": round(nsfw_score, 2),
                    "wad_score": round(wad, 2),
                    "faces": faces,
                    "safe_score": round(1 - nsfw_score, 2),
                    "raw": data
                }
    except Exception as e:
        logger.error(f"خطأ في كشف NSFW للصورة: {e}")
        return {"nsfw": False, "score": 0, "error": str(e)}


async def check_nsfw_video(video_bytes: bytes, frames: int = NSFW_FRAMES) -> dict:
    """كشف NSFW في الفيديو باستخدام OpenCV"""
    if not CV2_AVAILABLE:
        return {"nsfw": False, "score": 0, "error": "cv2 غير مثبت"}
    try:
        if not video_bytes:
            return {"nsfw": False, "score": 0, "error": "فيديو فارغ"}

        # حفظ الفيديو مؤقتاً
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name

        cap = cv2.VideoCapture(tmp_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0:
            cap.release()
            os.unlink(tmp_path)
            return {"nsfw": False, "score": 0, "error": "لا يمكن قراءة الفيديو"}

        frame_indices = np.linspace(0, total_frames - 1, min(frames, total_frames), dtype=int)
        nsfw_scores = []
        wad_scores = []
        faces_count = 0

        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            img_bytes = buffer.tobytes()
            result = await check_nsfw_image(img_bytes)
            if not result.get("error"):
                nsfw_scores.append(result.get("nsfw_score", 0))
                wad_scores.append(result.get("wad_score", 0))
                faces_count += result.get("faces", 0)
            await asyncio.sleep(0.1)

        cap.release()
        os.unlink(tmp_path)

        if not nsfw_scores:
            return {"nsfw": False, "score": 0, "error": "لا يمكن تحليل الإطارات"}

        avg_nsfw = sum(nsfw_scores) / len(nsfw_scores)
        avg_wad = sum(wad_scores) / len(wad_scores)

        return {
            "nsfw": avg_nsfw > NSFW_THRESHOLD or avg_wad > NSFW_THRESHOLD,
            "nsfw_score": round(avg_nsfw, 2),
            "wad_score": round(avg_wad, 2),
            "faces": faces_count // len(frame_indices) if frame_indices else 0,
            "frames_analyzed": len(nsfw_scores),
            "max_nsfw_score": round(max(nsfw_scores), 2) if nsfw_scores else 0,
            "max_wad_score": round(max(wad_scores), 2) if wad_scores else 0
        }
    except Exception as e:
        logger.error(f"خطأ في كشف NSFW للفيديو: {e}")
        return {"nsfw": False, "score": 0, "error": str(e)}

# ===================================================================
# ===== 19. نظام اللغة =====
# ===================================================================

_lang_data = {}
_lang_cache_time = {}
LANG_CACHE_TTL = 300
_lang_lock = asyncio.Lock()
user_language = {}


def load_all_languages():
    """تحميل جميع ملفات اللغة من مجلد lang/"""
    global _lang_data
    for lang_file in LANG_PATH.glob("*.json"):
        lang = lang_file.stem
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                _lang_data[lang] = json.load(f)
            print(f"✅ تم تحميل اللغة: {lang}")
        except Exception as e:
            print(f"⚠️ فشل تحميل {lang_file}: {e}")
    if not _lang_data:
        create_default_lang_files()
        load_all_languages()


def create_default_lang_files():
    """إنشاء ملفات اللغة الافتراضية (العربية والإنجليزية)"""
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
            "help": "❓ **المساعدة**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 **الأوامر المتاحة:**\n/start - القائمة الرئيسية\n/trial - تجربة مجانية\n/subscribe - الاشتراك\n/syncgroup - تفعيل المجموعة\n/security - إعدادات الأمان\n/register_hidden_owner - تسجيل مالك مخفي\n/add_hidden_admin - إضافة مشرف مخفي\n/remove_hidden_admin - إزالة مشرف مخفي\n/list_hidden_admins - عرض المشرفين المخفيين\n/rank - رتبتك\n/top - أفضل 10\n/stats - إحصائيات القناة\n/lock - قفل المجموعة\n/unlock - فتح المجموعة\n/schedule - جدولة منشور\n/panel - لوحة التحكم\n/language - تغيير اللغة\n/support - مركز الدعم\n/help - هذه المساعدة\n/developer - المطور\n/updates - التحديثات\n/contests - المسابقات\n/create_contest - إنشاء مسابقة\n/declare_winner - إعلان فائز\n/set_rules - تعيين قوانين المجموعة\n/rules - عرض قوانين المجموعة\n/coupon - استخدام كوبون خصم\n/poll - إنشاء استطلاع\n/vote - التصويت في استطلاع",
            "support_welcome": "📞 **مركز الدعم**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الخدمة المطلوبة:",
            "support_help": "❓ **المساعدة**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 للتواصل مع الدعم:\n• استخدم /support\n• اكتب رسالتك\n• ستصلك تذكرة برقم\n• سنرد عليك بأسرع وقت\n\n📌 للمشاكل التقنية:\n• تأكد من أن البوت مشرف\n• تأكد من صلاحيات البوت\n• راجع إعدادات الأمان",
            "trial_used": "❌ لقد استخدمت التجربة المجانية مسبقاً",
            "already_subscribed": "✅ لديك اشتراك فعال بالفعل",
            "trial": "🎁 **تم تفعيل التجربة المجانية!**\n━━━━━━━━━━━━━━━━━━━━━━\n✅ لديك 30 يوماً مجاناً\n📌 استمتع بجميع الميزات\n💎 يمكنك الاشتراك بعد انتهاء التجربة",
            "subscribe": "💎 **الاشتراك**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الباقة المناسبة لك:\n\n⭐ 1 يوم - 5 نجوم\n⭐ 2 يوم - 9 نجوم\n⭐ شهر (30 يوم) - 50 نجمة\n⭐ 3 أشهر (90 يوم) - 120 نجمة\n\n📌 الدفع عبر نجوم تيليجرام",
            "updates_text": "📢 **آخر التحديثات**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 تابع قناة التحديثات لمعرفة كل جديد:\n• إضافات جديدة\n• تحسينات الأداء\n• إصلاحات الأخطاء\n• ميزات حصرية",
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
            "help": "❓ **Help**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 **Available Commands:**\n/start - Main Menu\n/trial - Free Trial\n/subscribe - Subscribe\n/syncgroup - Activate Group\n/security - Security Settings\n/register_hidden_owner - Register Hidden Owner\n/add_hidden_admin - Add Hidden Admin\n/remove_hidden_admin - Remove Hidden Admin\n/list_hidden_admins - List Hidden Admins\n/rank - Your Rank\n/top - Top 10\n/stats - Channel Stats\n/lock - Lock Group\n/unlock - Unlock Group\n/schedule - Schedule Post\n/panel - Control Panel\n/language - Change Language\n/support - Support Center\n/help - This Help\n/developer - Developer\n/updates - Updates\n/contests - Contests\n/create_contest - Create Contest\n/declare_winner - Declare Winner\n/set_rules - Set Group Rules\n/rules - View Group Rules\n/coupon - Use Coupon\n/poll - Create Poll\n/vote - Vote in Poll",
            "support_welcome": "📞 **Support Center**\n━━━━━━━━━━━━━━━━━━━━━━\nSelect the required service:",
            "support_help": "❓ **Help**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 To contact support:\n• Use /support\n• Write your message\n• You'll get a ticket number\n• We'll reply ASAP\n\n📌 For technical issues:\n• Make sure bot is admin\n• Check bot permissions\n• Review security settings",
            "trial_used": "❌ You have already used the free trial",
            "already_subscribed": "✅ You already have an active subscription",
            "trial": "🎁 **Free Trial Activated!**\n━━━━━━━━━━━━━━━━━━━━━━\n✅ You have 30 days free\n📌 Enjoy all features\n💎 You can subscribe after trial ends",
            "subscribe": "💎 **Subscription**\n━━━━━━━━━━━━━━━━━━━━━━\nChoose your plan:\n\n⭐ 1 Day - 5 Stars\n⭐ 2 Days - 9 Stars\n⭐ 30 Days (Month) - 50 Stars\n⭐ 90 Days (3 Months) - 120 Stars\n\n📌 Payment via Telegram Stars",
            "updates_text": "📢 **Latest Updates**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 Follow updates channel for news:\n• New features\n• Performance improvements\n• Bug fixes\n• Exclusive features",
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
            print(f"✅ تم إنشاء ملف {lang_file}")


load_all_languages()


def get_text(user_id: int, key: str) -> str:
    """الحصول على نص مترجم حسب لغة المستخدم"""
    lang = user_language.get(user_id, 'ar')
    texts = _lang_data.get(lang, {})
    if key not in texts:
        en_texts = _lang_data.get('en', {})
        if key in en_texts:
            return en_texts[key]
    return texts.get(key, key)


async def set_user_language(user_id: int, lang: str):
    """تعيين لغة المستخدم"""
    user_language[user_id] = lang

# ===================================================================
# ===== 20. الردود التلقائية المدمجة (200+ رد) =====
# ===================================================================

# تعريف جميع الردود التلقائية
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

# دمج جميع الردود
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
# ===== 21. دوال معالجة النصوص =====
# ===================================================================

def clean_text_for_telegram(text: str) -> str:
    """تنظيف النص من الأحرف الخاصة"""
    if not text:
        return ""
    text = re.sub(r'[\u200b\u200c\u200d\u2060\uFEFF\u202a\u202b\u202c\u202d\u202e]', '', text)
    return text


def escape_markdown_v2(text: str) -> str:
    """هروب الأحرف الخاصة بـ Markdown V2"""
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
    """تنقية النص من HTML وعلامات الترقيم"""
    if not text:
        return ""
    try:
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
    """تشفير بيانات الكولباك"""
    return urllib.parse.quote(data, safe='')


def decode_callback_data(data: str) -> str:
    """فك تشفير بيانات الكولباك"""
    return urllib.parse.unquote(data)


ERROR_MESSAGES = {
    "Forbidden": "🔒 البوت ليس لديه صلاحية للقيام بهذا الإجراء",
    "BadRequest": "⚠️ طلب غير صحيح، تأكد من البيانات المدخلة",
    "TimedOut": "⏱️ انتهت المهلة، حاول مرة أخرى",
    "NetworkError": "🌐 مشكلة في الشبكة، تحقق من اتصالك",
    "InvalidQuery": "❌ بيانات غير صالحة، حاول مرة أخرى",
    "ChatNotFound": "❌ المجموعة غير موجودة أو البوت ليس فيها",
    "UserNotFound": "❌ المستخدم غير موجود",
    "MessageNotModified": "✅ تم التحديث",
}

# ===================================================================
# ===== 22. نظام التسجيل المتقدم =====
# ===================================================================

class AdvancedLogger:
    """نظام تسجيل متقدم متعدد المستويات"""
    def __init__(self):
        self.loggers = {}
        self._setup_loggers()

    def _setup_loggers(self):
        """إعداد معالجات التسجيل"""
        # سجل الأخطاء
        error_logger = logging.getLogger('error_logger')
        error_logger.setLevel(logging.ERROR)
        error_handler = logging.FileHandler(ERROR_LOG, encoding='utf-8')
        error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        error_logger.addHandler(error_handler)
        self.loggers['error'] = error_logger

        # سجل الوصول
        access_logger = logging.getLogger('access_logger')
        access_logger.setLevel(logging.INFO)
        access_handler = logging.FileHandler(ACCESS_LOG, encoding='utf-8')
        access_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        access_logger.addHandler(access_handler)
        self.loggers['access'] = access_logger

        # سجل الأمان
        security_logger = logging.getLogger('security_logger')
        security_logger.setLevel(logging.WARNING)
        security_handler = logging.FileHandler(SECURITY_LOG, encoding='utf-8')
        security_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        security_logger.addHandler(security_handler)
        self.loggers['security'] = security_logger

    def log_error(self, message: str, error: Exception = None, context: dict = None) -> str:
        """تسجيل خطأ مع معرف فريد"""
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
        """تسجيل حدث وصول"""
        log_msg = f"User: {user_id} - Action: {action}"
        if details:
            safe_details = {k: v for k, v in details.items() if k not in ['token', 'password', 'key', 'secret']}
            log_msg += f" - {json.dumps(safe_details, default=str)[:100]}"
        self.loggers['access'].info(log_msg)

    def log_security(self, event: str, user_id: int, details: dict = None, severity: str = "INFO"):
        """تسجيل حدث أمني"""
        log_msg = f"[{severity}] {event} - User: {user_id}"
        if details:
            safe_details = {k: v for k, v in details.items() if k not in ['token', 'password', 'key', 'secret']}
            log_msg += f" - {json.dumps(safe_details, default=str)[:200]}"
        self.loggers['security'].warning(log_msg)


advanced_logger = AdvancedLogger()


def log_error(error: Exception, context: dict = None) -> str:
    """دالة مساعدة لتسجيل الأخطاء"""
    return advanced_logger.log_error("حدث خطأ غير متوقع", error, context)

# ===================================================================
# ===== 23. معالج الأخطاء مع إعادة المحاولة =====
# ===================================================================

class ErrorHandler:
    """معالج الأخطاء مع إعادة المحاولة التلقائية"""
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.errors = defaultdict(int)
        self._lock = asyncio.Lock()

    async def handle_async(self, func: Callable, *args, **kwargs) -> Any:
        """تنفيذ دالة غير متزامنة مع إعادة المحاولة"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except (TimedOut, NetworkError) as e:
                last_error = e
                delay = self.base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                advanced_logger.log_error(f"محاولة {attempt+1} فشلت", e, {'args': str(args)[:100]})
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(delay)
                continue
            except Conflict as e:
                advanced_logger.log_error("تعارض في التحديثات", e)
                return None
            except Forbidden as e:
                advanced_logger.log_security("FORBIDDEN_ACTION", 0, {'error': str(e)}, "CRITICAL")
                raise
            except Exception as e:
                advanced_logger.log_error("خطأ غير متوقع", e, {'args': str(args)[:100]})
                raise
        if last_error:
            raise last_error
        return None

    def handle_sync(self, func: Callable, *args, **kwargs) -> Any:
        """تنفيذ دالة متزامنة مع إعادة المحاولة"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                delay = self.base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                advanced_logger.log_error(f"محاولة {attempt+1} فشلت (متزامنة)", e)
                if attempt < self.max_retries - 1:
                    time_module.sleep(delay)
                continue
        if last_error:
            raise last_error
        return None


error_handler = ErrorHandler()

# ===================================================================
# ===== 24. محسن الذاكرة =====
# ===================================================================

async def memory_optimizer():
    """تنظيف الذاكرة والتخزين المؤقت"""
    try:
        if CACHETOOLS_AVAILABLE:
            _admin_cache.clear()
            _security_cache.clear()
            _auth_cache.clear()
        else:
            _admin_cache.clear()
            _security_cache.clear()
            _auth_cache.clear()
            _security_cache_time.clear()
        await _translation_cache.clear()
        NSFW_CACHE.clear()
        gc.collect()
        return True
    except Exception as e:
        advanced_logger.log_error("فشل تحسين الذاكرة", e)
        return False


async def memory_optimizer_loop():
    """حلقة تحسين الذاكرة الدورية"""
    while True:
        await asyncio.sleep(300)
        try:
            await memory_optimizer()
            advanced_logger.log_access(0, "MEMORY_OPTIMIZED", {"timestamp": utc_now_iso()})
        except Exception as e:
            advanced_logger.log_error("فشل حلقة تحسين الذاكرة", e)

# ===================================================================
# ===== 25. نظام الإشعارات =====
# ===================================================================

class NotificationSystem:
    """نظام إرسال الإشعارات"""
    def __init__(self):
        self.pending_notifications = []
        self._lock = asyncio.Lock()
        self._scheduled_tasks = []

    async def send_notification(self, bot, user_id: int, text: str, parse_mode: str = "MarkdownV2", reply_markup=None):
        """إرسال إشعار لمستخدم"""
        try:
            await safe_send_markdown(bot, user_id, text, reply_markup)
            advanced_logger.log_access(user_id, "NOTIFICATION_SENT", {"text": text[:50]})
            return True
        except Exception as e:
            advanced_logger.log_error("فشل إرسال الإشعار", e, {"user_id": user_id})
            return False

    async def send_bulk_notification(self, bot, user_ids: List[int], text: str, parse_mode: str = "MarkdownV2", delay: float = 0.5):
        """إرسال إشعارات جماعية"""
        results = []
        semaphore = asyncio.Semaphore(10)

        async def send_one(user_id):
            async with semaphore:
                try:
                    await safe_send_markdown(bot, user_id, text)
                    return (user_id, True)
                except:
                    await asyncio.sleep(delay)
                    return (user_id, False)

        tasks = [send_one(uid) for uid in user_ids]
        results = await asyncio.gather(*tasks)
        success = sum(1 for _, ok in results if ok)
        failed = len(results) - success
        advanced_logger.log_access(0, "BULK_NOTIFICATION", {
            "total": len(user_ids),
            "success": success,
            "failed": failed
        })
        return success, failed

    async def schedule_notification(self, bot, user_id: int, text: str, delay_seconds: int):
        """جدولة إشعار مؤجل"""
        async def delayed():
            await asyncio.sleep(delay_seconds)
            await self.send_notification(bot, user_id, text)

        task = asyncio.create_task(delayed())
        self._scheduled_tasks.append(task)
        task.add_done_callback(lambda t: self._scheduled_tasks.remove(t) if t in self._scheduled_tasks else None)
        return task


notification_system = NotificationSystem()

# ===================================================================
# ===== 26. دوال الإرسال الآمنة =====
# ===================================================================

async def safe_send_markdown(bot, chat_id: int, text: str, reply_markup=None, **kwargs):
    """إرسال رسالة بأمان مع Markdown V2"""
    if not text:
        return None

    clean_text = sanitize_text(text)
    MAX_LEN = 4096

    try:
        escaped = escape_markdown_v2(clean_text)
        escaped = re.sub(r'\\{2,}', '\\\\', escaped)
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
            logger.debug(f"محاولة إرسال رسالة إلى بوت (chat_id={chat_id}) تم تجاهلها.")
            return None
        raise
    except Exception:
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
        except Exception:
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
            except Exception as final_e:
                raise final_e


async def safe_edit_markdown(query, text: str, reply_markup=None, **kwargs):
    """تعديل رسالة بأمان مع Markdown V2"""
    if not query or not query.message:
        return None

    current_text = query.message.text or ""
    current_reply_markup = query.message.reply_markup

    if current_text == text:
        if reply_markup is None and current_reply_markup is None:
            try:
                await query.answer("✅ تم التحديث")
            except:
                pass
            return None
        elif reply_markup is not None and current_reply_markup is not None:
            if str(reply_markup) == str(current_reply_markup):
                try:
                    await query.answer("✅ تم التحديث")
                except:
                    pass
                return None

    if not text:
        return None

    clean_text = sanitize_text(text)
    MAX_LEN = 4096

    try:
        escaped = escape_markdown_v2(clean_text)
        escaped = re.sub(r'\\{2,}', '\\\\', escaped)
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
    except Exception:
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
        except Exception:
            try:
                plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', clean_text)
                if len(plain) > MAX_LEN:
                    plain = plain[:MAX_LEN-3] + "..."
                return await query.edit_message_text(
                    text=plain,
                    reply_markup=reply_markup,
                    **kwargs
                )
            except Exception as final_e:
                try:
                    return await query.message.reply_text(
                        text=plain,
                        reply_markup=reply_markup,
                        **kwargs
                    )
                except:
                    raise final_e

# ===================================================================
# ===== 27. التحقق من التشغيل الواحد =====
# ===================================================================

def check_single_instance():
    """التحقق من أن البوت يعمل في نسخة واحدة"""
    try:
        sock_path = TEMP_PATH / "bot.sock"
        if sock_path.exists():
            sock_path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(sock_path))
        return sock
    except Exception as e:
        print(f"⚠️ لا يمكن التحقق من التشغيل الواحد: {e}")
        return None


lock_socket = check_single_instance()

# ===================================================================
# ===== 28. نظام الأمان والتدقيق =====
# ===================================================================

class SecurityAudit:
    """نظام تدقيق الأمان"""
    async def log(self, event_type: str, user_id: int, details: dict, severity: str = "INFO"):
        """تسجيل حدث أمني"""
        log_entry = {
            "event": event_type,
            "user_id": user_id,
            "details": details,
            "severity": severity,
            "timestamp": mecca_now_iso()
        }
        logger.warning(f"[SECURITY] {event_type} | User: {user_id} | {details} | Severity: {severity}")
        advanced_logger.log_security(event_type, user_id, details, severity)

        try:
            with open(SECURITY_LOG, "a", encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + "\n")
        except:
            pass

        try:
            log_channel = await db_get_log_channel_id()
            if log_channel:
                try:
                    from telegram import Bot
                    bot = Bot(token=TOKEN)
                    await bot.send_message(
                        chat_id=log_channel,
                        text=f"🔐 **تقرير أمني**\n\n📌 الحدث: {event_type}\n👤 المستخدم: `{user_id}`\n📊 التفاصيل: {json.dumps(details, default=str)[:200]}\n⚠️ الخطورة: {severity}\n🕐 الوقت: {mecca_now().strftime('%Y-%m-%d %H:%M:%S')}",
                        parse_mode="MarkdownV2"
                    )
                except Exception as e:
                    logger.warning(f"فشل إرسال التقرير إلى القناة: {e}")
        except:
            pass
        return True


security_audit = SecurityAudit()


class AnomalyDetector:
    """كشف السلوكيات الشاذة"""
    def __init__(self):
        self.user_activity = defaultdict(list)
        self.lock = asyncio.Lock()

    async def detect_anomaly(self, user_id: int, action: str) -> bool:
        """كشف السلوك الشاذ"""
        async with self.lock:
            now = time_module.time()
            self.user_activity[user_id].append((now, action))
            self.user_activity[user_id] = [
                (t, a) for t, a in self.user_activity[user_id]
                if now - t < 60
            ]
            if len(self.user_activity[user_id]) > 10:
                await security_audit.log(
                    "SUSPICIOUS_ACTIVITY",
                    user_id,
                    {"actions": self.user_activity[user_id], "count": len(self.user_activity[user_id])},
                    "CRITICAL"
                )
                return True
            return False


anomaly_detector = AnomalyDetector()

# ===================================================================
# ===== 29. Pool اتصالات قاعدة البيانات =====
# ===================================================================

class DatabasePool:
    """Pool اتصالات قاعدة البيانات"""
    def __init__(self, max_connections: int = 10):
        self._pool = None
        self._max_connections = max_connections
        self._lock = asyncio.Lock()
        self._connections = []

    async def initialize(self):
        """تهيئة Pool الاتصالات"""
        async with self._lock:
            if self._pool is None:
                self._pool = await aiosqlite.connect(str(DB_PATH), timeout=DB_TIMEOUT)
                await self._pool.execute("PRAGMA journal_mode=WAL")
                await self._pool.execute("PRAGMA synchronous=NORMAL")
                await self._pool.execute("PRAGMA foreign_keys=ON")
                await self._pool.execute("PRAGMA cache_size=-64000")
                await self._pool.execute("PRAGMA max_page_count=1000000")
                await self._pool.execute("PRAGMA secure_delete=ON")
                self._pool.row_factory = aiosqlite.Row

    async def get_connection(self):
        """الحصول على اتصال من Pool"""
        if self._pool is None:
            await self.initialize()
        return self._pool

    async def execute(self, query: str, params: tuple = None):
        """تنفيذ استعلام في قاعدة البيانات"""
        conn = await self.get_connection()
        async with conn.execute(query, params or ()) as cursor:
            return await cursor.fetchall()

    async def execute_many(self, queries: List[Tuple[str, tuple]]):
        """تنفيذ عدة استعلامات في صفقة واحدة"""
        conn = await self.get_connection()
        async with conn:
            for query, params in queries:
                await conn.execute(query, params)
            await conn.commit()

    async def close(self):
        """إغلاق Pool الاتصالات"""
        if self._pool:
            await self._pool.close()
            self._pool = None


db_pool = DatabasePool(max_connections=MAX_CONNECTIONS)


async def execute_db(func: Callable):
    """تنفيذ دالة قاعدة بيانات مع اتصال من Pool"""
    conn = await db_pool.get_connection()
    try:
        return await func(conn)
    except Exception as e:
        logger.error(f"خطأ في قاعدة البيانات: {e}")
        raise
    finally:
        pass

# ===================================================================
# ===== 30. دوال التشفير والضغط =====
# ===================================================================

def encrypt_file_stream(src: Path, dst: Path, cipher: Fernet, chunk_size: int = 64*1024):
    """تشفير ملف بشكل تدفقي"""
    with open(src, 'rb') as f_in, open(dst, 'wb') as f_out:
        while True:
            chunk = f_in.read(chunk_size)
            if not chunk:
                break
            encrypted_chunk = cipher.encrypt(chunk)
            f_out.write(encrypted_chunk)


def decrypt_file_stream(src: Path, dst: Path, cipher: Fernet, chunk_size: int = 64*1024):
    """فك تشفير ملف بشكل تدفقي"""
    with open(src, 'rb') as f_in, open(dst, 'wb') as f_out:
        while True:
            chunk = f_in.read(chunk_size)
            if not chunk:
                break
            decrypted_chunk = cipher.decrypt(chunk)
            f_out.write(decrypted_chunk)


def encrypt_db_backup() -> Path:
    """تشفير قاعدة البيانات للنسخ الاحتياطي"""
    if not DB_ENCRYPTION:
        return DB_PATH
    cipher = Fernet(ENCRYPTION_KEY)
    encrypted_path = DB_PATH.with_suffix('.enc')
    encrypt_file_stream(DB_PATH, encrypted_path, cipher)
    return encrypted_path


def decrypt_db_backup(encrypted_path: Path) -> bytes:
    """فك تشفير قاعدة البيانات من النسخ الاحتياطي"""
    if not DB_ENCRYPTION:
        with open(encrypted_path, 'rb') as f:
            return f.read()
    cipher = Fernet(ENCRYPTION_KEY)
    temp_decrypted = encrypted_path.with_suffix('.db.tmp')
    decrypt_file_stream(encrypted_path, temp_decrypted, cipher)
    with open(temp_decrypted, 'rb') as f:
        data = f.read()
    temp_decrypted.unlink()
    return data


def compress_backup(data: bytes) -> bytes:
    """ضغط بيانات النسخ الاحتياطي"""
    if ZSTD_AVAILABLE:
        try:
            return ZSTD_COMPRESSOR.compress(data)
        except:
            pass
    return gzip.compress(data)


def decompress_backup(data: bytes) -> bytes:
    """فك ضغط بيانات النسخ الاحتياطي"""
    if ZSTD_AVAILABLE:
        try:
            return ZSTD_DECOMPRESSOR.decompress(data)
        except:
            pass
    return gzip.decompress(data)


async def retry_with_jitter(func: Callable, max_retries: int = 5, base_delay: float = 1) -> Any:
    """تنفيذ دالة مع إعادة المحاولة وتأخير عشوائي"""
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            jitter = random.uniform(0, 0.5)
            delay = (base_delay * (2 ** attempt)) + jitter
            logger.warning(f"⚠️ إعادة محاولة {attempt+1}/{max_retries} بعد {delay:.2f}s: {e}")
            await asyncio.sleep(delay)

# ===================================================================
# ===== 31. محدد السرعة العام =====
# ===================================================================

class GlobalRateLimiter:
    """محدد السرعة العالمي"""
    def __init__(self):
        self.limits = {
            'command': (5, 10),
            'callback': (10, 30),
            'message': (20, 60),
            'api': (30, 60),
        }
        self.records = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, user_id: int, action_type: str = 'command') -> bool:
        """التحقق من السماح بتنفيذ الإجراء"""
        async with self._lock:
            max_req, window = self.limits.get(action_type, (10, 60))
            now = time_module.time()
            key = f"{user_id}:{action_type}"
            user_requests = self.records[key]
            user_requests = [t for t in user_requests if now - t < window]
            self.records[key] = user_requests
            if len(user_requests) >= max_req:
                return False
            user_requests.append(now)
            return True


global_rate_limiter = GlobalRateLimiter()

# ===================================================================
# ===== 32. تعريفات CallbackData و UserState =====
# ===================================================================

class CallbackData:
    """تعريفات بيانات الكولباك"""
    # القائمة الرئيسية
    MAIN_MENU = "main_menu"
    BACK = "back"
    CANCEL_SESSION = "cancel_session"

    # القنوات
    CHANNELS_MY = "channels:my_channels"
    CHANNELS_ADD = "channels:add"
    CHANNELS_DELETE_PREFIX = "channels:delete:"
    CHANNELS_SELECT_PREFIX = "channels:select:"

    # المنشورات
    POSTS_ADD_15 = "posts:add_15"
    POSTS_PUBLISH_ONE = "posts:publish_one"
    POSTS_MY = "posts:my_posts"
    POSTS_RECYCLE = "posts:recycle"
    POSTS_DELETE_SINGLE_PREFIX = "posts:delete_single:"
    POSTS_CONFIRM_CLEAR_ALL_PREFIX = "posts:confirm_clear_all:"
    POSTS_CLEAR_ALL_PREFIX = "posts:clear_all:"

    # الإحصائيات
    STATS_PENDING = "stats:pending"
    STATS_FULL = "stats:full"

    # المجموعات
    GROUPS_MY = "groups:my_groups"
    GROUPS_SETTINGS_PREFIX = "groups:settings:"

    # الإعدادات
    SETTINGS_MENU = "settings:menu"
    SETTINGS_TOGGLE_AUTO_PUBLISH = "settings:toggle_auto_publish"
    SETTINGS_TOGGLE_AUTO_RECYCLE = "settings:toggle_auto_recycle"

    # الجدولة
    SCHEDULE_MENU_PREFIX = "schedule:menu:"
    SCHEDULE_SET_INTERVAL_MINUTES_PREFIX = "schedule:set_interval_minutes:"
    SCHEDULE_SET_INTERVAL_HOURS_PREFIX = "schedule:set_interval_hours:"
    SCHEDULE_SET_INTERVAL_DAYS_PREFIX = "schedule:set_interval_days:"
    SCHEDULE_SET_DAYS_PREFIX = "schedule:set_days:"
    SCHEDULE_SET_DATES_PREFIX = "schedule:set_dates:"
    SCHEDULE_SET_PUBLISH_TIME_PREFIX = "schedule:set_publish_time:"
    SCHEDULE_DAY_SELECT_PREFIX = "schedule:day_select:"
    SCHEDULE_SAVE_DAYS = "schedule:save_days"

    # الأمان
    SECURITY_LINKS_PREFIX = "security:links:"
    SECURITY_MENTIONS_PREFIX = "security:mentions:"
    SECURITY_WARN_PREFIX = "security:warn:"
    SECURITY_SLOWMODE_PREFIX = "security:slow_mode:"
    SECURITY_BANNED_WORDS_MENU_PREFIX = "security:banned_words_menu:"
    SECURITY_WELCOME_PREFIX = "security:welcome_enabled:"
    SECURITY_GOODBYE_PREFIX = "security:goodbye_enabled:"
    SECURITY_MAIN = "security:main"
    SECURITY_CLOSE = "security:close"
    SECURITY_SELECT_GROUP = "security_select_group:"
    SECURITY_REFRESH_GROUPS = "security_refresh_groups"
    SECURITY_DELETE_VIDEOS_PREFIX = "security:delete_videos:"
    SECURITY_DELETE_SERVICE_PREFIX = "security:delete_service:"
    SECURITY_DELETE_DOCUMENTS_PREFIX = "security:delete_documents:"
    SECURITY_DELETE_STICKERS_PREFIX = "security:delete_stickers:"
    SECURITY_DELETE_AUDIO_PREFIX = "security:delete_audio:"
    SECURITY_DELETE_ANIMATION_PREFIX = "security:delete_animation:"
    SECURITY_ENABLE_ALL_PREFIX = "security:enable_all:"
    SECURITY_DISABLE_ALL_PREFIX = "security:disable_all:"
    SECURITY_DELETE_PENALTY_PREFIX = "security:delete_penalty:"

    # الكلمات المحظورة
    BANNED_WORDS_ADD_PREFIX = "banned_words:add:"
    BANNED_WORDS_LIST_PREFIX = "banned_words:list:"
    BANNED_WORDS_REMOVE_PREFIX = "banned_words:remove:"

    # المساعدة والدعم
    HELP = "help"
    SUPPORT_MENU = "support:menu"
    SUPPORT_HELP = "support:help"
    SUPPORT_TICKET = "support:ticket"
    SUPPORT_BACK = "support:back"

    # الاشتراك والتجربة
    TRIAL = "trial"
    SUBSCRIBE_MENU = "subscribe:menu"
    BUY_SUBSCRIPTION_1 = "buy:subscription_1"
    BUY_SUBSCRIPTION_2 = "buy:subscription_2"
    BUY_SUBSCRIPTION_30 = "buy:subscription_30"
    BUY_SUBSCRIPTION_90 = "buy:subscription_90"

    # المطور والتحديثات
    DEVELOPER = "developer"
    UPDATES = "updates"

    # الإحالات
    REFERRAL_MENU = "referral:menu"
    REFERRAL_COPY_LINK_PREFIX = "referral:copy_link:"
    REFERRAL_CLAIM_REWARD = "referral:claim_reward"
    REFERRAL_LIST = "referral:list"

    # التذكيرات
    REMINDER_MENU = "reminder:menu"
    REMINDER_TOGGLE_SUB = "reminder:toggle_sub"
    REMINDER_TOGGLE_DAILY = "reminder:toggle_daily"
    REMINDER_TOGGLE_WEEKLY = "reminder:toggle_weekly"
    REMINDER_SET_DAYS = "reminder:set_days"
    REMINDER_SET_LANG = "reminder:set_lang"
    REMINDER_LANG_PREFIX = "reminder:lang:"

    # الترجمة
    TRANSLATION_MENU = "translation:menu"
    TRANSLATION_OFF = "translation:off"
    TRANSLATION_SET_PREFIX = "translation:set:"

    # لوحة الأدمن
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
    ADMIN_TOGGLE_CHANNEL_BAN_PREFIX = "admin:toggle_channel_ban:"
    ADMIN_TOGGLE_GROUP_BAN_PREFIX = "admin:toggle_group_ban:"
    ADMIN_AUTO_REPLY = "admin_auto_reply"
    ADMIN_AUTO_REPLY_SELECT_PREFIX = "admin_auto_reply_select:"
    ADMIN_COUPONS = "admin:coupons"
    ADMIN_CREATE_COUPON = "admin:create_coupon"
    ADMIN_LIST_COUPONS = "admin:list_coupons"
    ADMIN_DELETE_COUPON = "admin:delete_coupon"
    ADMIN_POLLS = "admin:polls"
    ADMIN_CREATE_POLL = "admin:create_poll"
    ADMIN_LIST_POLLS = "admin:list_polls"
    ADMIN_DELETE_POLL = "admin:delete_poll"
    ADMIN_ADS = "admin:ads"
    ADMIN_CREATE_AD = "admin:create_ad"
    ADMIN_LIST_ADS = "admin:list_ads"
    ADMIN_DELETE_AD = "admin:delete_ad"
    ADMIN_FAQ = "admin:faq"
    ADMIN_ADD_FAQ = "admin:add_faq"
    ADMIN_LIST_FAQ = "admin:list_faq"
    ADMIN_DELETE_FAQ = "admin:delete_faq"

    # الإجراءات المتقدمة
    ADVANCED_ACTIONS = "advanced_actions"
    GROUP_ACTION_BAN = "group_action:ban"
    GROUP_ACTION_MUTE = "group_action:mute"
    GROUP_ACTION_WARN = "group_action:warn"
    GROUP_ACTION_KICK = "group_action:kick"
    GROUP_ACTION_RESTRICT = "group_action:restrict"
    GROUP_ACTION_PIN = "group_action:pin"
    GROUP_ACTION_LOG = "group_action:log"
    GROUP_ACTION_UNBAN = "group_action:unban"

    # مدة الكتم
    GROUP_MUTE_DURATION_5 = "group_mute_duration:5"
    GROUP_MUTE_DURATION_30 = "group_mute_duration:30"
    GROUP_MUTE_DURATION_60 = "group_mute_duration:60"
    GROUP_MUTE_DURATION_720 = "group_mute_duration:720"
    GROUP_MUTE_DURATION_1440 = "group_mute_duration:1440"
    GROUP_MUTE_DURATION_10080 = "group_mute_duration:10080"
    GROUP_MUTE_DURATION_PERMANENT = "group_mute_duration:permanent"

    # العقوبات
    PENALTY_MENU = "penalty_menu"
    PENALTY_KICK = "penalty:kick"
    PENALTY_BAN = "penalty:ban"
    PENALTY_MUTE = "penalty:mute"

    # النشر
    PUBLISH_ALL_CHANNELS = "publish_all_channels"
    CHANNEL_STATS = "channel_stats"
    CHANNEL_GROWTH = "channel_growth"
    CHANNEL_STATS_REFRESH = "channel_stats_refresh"
    MY_CHANNEL_STATS = "my_channel_stats"

    # المسابقات
    CONTESTS_MENU = "contests_menu"
    CONTEST_JOIN_PREFIX = "contest_join:"
    CONTEST_WINNERS = "contest_winners"
    CONTESTS_BACK = "contests_back"

    # المشرفين المخفيين
    HIDDEN_ADMIN_ADD = "hidden_admin:add"
    HIDDEN_ADMIN_REMOVE_PREFIX = "hidden_admin:remove:"
    HIDDEN_ADMIN_LIST = "hidden_admin:list"

    # الردود التلقائية
    AUTO_REPLY_MENU_PREFIX = "auto_reply_menu:"
    AUTO_REPLY_TOGGLE_PREFIX = "auto_reply_toggle:"
    AUTO_REPLY_ADMINS_PREFIX = "auto_reply_admins:"
    AUTO_REPLY_RESET_PREFIX = "auto_reply_reset:"
    AUTO_REPLY_CONFIRM_RESET_PREFIX = "auto_reply_confirm_reset:"
    AUTO_REPLY_CANCEL_PREFIX = "auto_reply_cancel:"
    AUTO_REPLY_STATS_PREFIX = "auto_reply_stats:"
    USER_AUTO_REPLY_TOGGLE_PREFIX = "user_auto_reply_toggle:"

    # NSFW
    NSFW_SETTINGS = "nsfw_settings"
    NSFW_TOGGLE = "nsfw_toggle"
    NSFW_THRESHOLD_SET = "nsfw_threshold_set"

    # القفل والفتح
    PANEL_LOCK_PREFIX = "panel:lock:"
    PANEL_UNLOCK_PREFIX = "panel:unlock:"
    PANEL_CLOSE = "panel:close"

    # كوبونات
    COUPON_USE = "coupon:use"

    # استطلاعات
    POLL_VOTE_PREFIX = "poll:vote:"
    POLL_RESULTS_PREFIX = "poll:results:"

    # FAQ
    FAQ_SEARCH = "faq:search"

    # التحقق من الاشتراك
    CHECK_SUBSCRIBE = "check_subscribe"


class UserState(Enum):
    """حالات المستخدم أثناء التفاعل"""
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
    WAITING_COUPON_CODE = auto()
    WAITING_POLL_QUESTION = auto()
    WAITING_POLL_OPTIONS = auto()
    WAITING_POLL_DURATION = auto()
    WAITING_AD_TITLE = auto()
    WAITING_AD_TEXT = auto()
    WAITING_AD_DURATION = auto()
    WAITING_AD_PRICE = auto()
    WAITING_FAQ_QUESTION = auto()
    WAITING_FAQ_ANSWER = auto()

# ===================================================================
# ===== 33. دوال قاعدة البيانات الأساسية (db_*) =====
# ===================================================================

# ===== دوال المستخدمين =====

async def db_register_user(user_id: int) -> bool:
    """تسجيل مستخدم جديد في قاعدة البيانات"""
    async def _register(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if await cur.fetchone():
            return False
        await conn.execute(
            "INSERT INTO users (user_id, auto_publish, banned, trial_used, auto_reply_enabled, auto_recycle) VALUES (?, 1, 0, 0, 1, 1)",
            (user_id,)
        )
        await conn.commit()
        return True
    return await execute_db(_register)


async def db_get_all_users():
    """الحصول على جميع المستخدمين"""
    async def _get(conn):
        cur = await conn.execute("SELECT user_id, banned FROM users ORDER BY user_id")
        return await cur.fetchall()
    return await execute_db(_get)


async def db_update_user_cache(user_id: int, username: str, first_name: str):
    """تحديث بيانات المستخدم في التخزين المؤقت"""
    async def _update(conn):
        await conn.execute(
            "INSERT OR REPLACE INTO users_cache (user_id, username, first_name, last_updated) VALUES (?, ?, ?, ?)",
            (user_id, username or "", first_name or "", utc_now_iso())
        )
        await conn.commit()
    return await execute_db(_update)


async def db_is_banned(user_id: int) -> bool:
    """التحقق من حظر المستخدم"""
    async def _check(conn):
        cur = await conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_check)


async def db_set_ban(user_id: int, banned: bool):
    """تعيين حالة حظر المستخدم"""
    async def _set(conn):
        await conn.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, user_id))
        await conn.commit()
    return await execute_db(_set)


async def db_has_used_trial(user_id: int) -> bool:
    """التحقق من استخدام التجربة المجانية"""
    async def _check(conn):
        cur = await conn.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_check)


async def db_activate_trial(user_id: int) -> int:
    """تفعيل التجربة المجانية لمدة 30 يوم"""
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
    """تفعيل اشتراك مدفوع لمدة أيام"""
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
    """التحقق من وجود اشتراك فعال"""
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
    """الحصول على عدد الأيام المتبقية في الاشتراك"""
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
    """الحصول على حالة النشر التلقائي"""
    async def _get(conn):
        cur = await conn.execute("SELECT auto_publish FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_get)


async def db_set_auto(user_id: int, enabled: bool):
    """تعيين حالة النشر التلقائي"""
    async def _set(conn):
        await conn.execute("UPDATE users SET auto_publish=? WHERE user_id=?", (1 if enabled else 0, user_id))
        await conn.commit()
    return await execute_db(_set)


async def db_get_auto_recycle(user_id: int) -> bool:
    """الحصول على حالة إعادة التدوير التلقائي"""
    async def _get(conn):
        cur = await conn.execute("SELECT auto_recycle FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_get)


async def db_set_auto_recycle(user_id: int, enabled: bool):
    """تعيين حالة إعادة التدوير التلقائي"""
    async def _set(conn):
        await conn.execute("UPDATE users SET auto_recycle=? WHERE user_id=?", (1 if enabled else 0, user_id))
        await conn.commit()
    return await execute_db(_set)

# ===== دوال إدارة القنوات =====

async def db_add_channel(user_id: int, channel_id: str, channel_name: str) -> int:
    """إضافة قناة لمستخدم"""
    async def _add(conn):
        cur = await conn.execute("SELECT id FROM user_channels WHERE user_id=? AND channel_id=?", (user_id, channel_id))
        if await cur.fetchone():
            return None
        cur = await conn.execute(
            "INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) VALUES (?, ?, ?, ?) RETURNING id",
            (user_id, channel_id, channel_name, utc_now_iso())
        )
        row = await cur.fetchone()
        await conn.commit()
        return row[0] if row else None
    return await execute_db(_add)


async def db_get_channels(user_id: int):
    """الحصول على قنوات المستخدم"""
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
    """الحصول على معلومات قناة"""
    async def _get(conn):
        cur = await conn.execute("SELECT channel_id, channel_name FROM user_channels WHERE id=?", (channel_db_id,))
        return await cur.fetchone()
    return await execute_db(_get)


async def db_delete_channel_by_id(user_id: int, channel_db_id: int) -> bool:
    """حذف قناة بواسطة المعرف"""
    async def _delete(conn):
        await conn.execute("DELETE FROM user_channels WHERE id=? AND user_id=?", (channel_db_id, user_id))
        await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (channel_db_id,))
        await conn.execute("DELETE FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
        return True
    return await execute_db(_delete)


async def db_get_active_channel(user_id: int):
    """الحصول على القناة النشطة للمستخدم"""
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
    """تعيين القناة النشطة للمستخدم"""
    async def _set(conn):
        await conn.execute("UPDATE users SET active_channel=? WHERE user_id=?", (channel_db_id, user_id))
        await conn.commit()
    return await execute_db(_set)


async def db_get_user_channels_count(user_id: int) -> int:
    """الحصول على عدد قنوات المستخدم"""
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM user_channels WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)


async def db_get_all_user_channels_no_limit():
    """الحصول على جميع قنوات المستخدمين بدون حد"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT uc.user_id, uc.id, uc.channel_id, uc.channel_name, uc.banned FROM user_channels uc ORDER BY uc.id"
        )
        return await cur.fetchall()
    return await execute_db(_get)


async def db_all_users_channels(only_banned: bool = False, limit: int = 500):
    """الحصول على قنوات المستخدمين مع خيار المحظورة"""
    async def _get(conn):
        if only_banned:
            cur = await conn.execute(
                "SELECT user_id, id, channel_id, channel_name, banned FROM user_channels WHERE banned=1 LIMIT ?",
                (limit,)
            )
        else:
            cur = await conn.execute(
                "SELECT user_id, id, channel_id, channel_name, banned FROM user_channels LIMIT ?",
                (limit,)
            )
        return await cur.fetchall()
    return await execute_db(_get)


async def db_register_channel(channel_id: int, channel_name: str, added_by: int):
    """تسجيل قناة في قنوات البوت"""
    async def _register(conn):
        cur = await conn.execute("SELECT channel_id FROM bot_channels WHERE channel_id=?", (channel_id,))
        if await cur.fetchone():
            await conn.execute(
                "UPDATE bot_channels SET channel_name=?, added_by=? WHERE channel_id=?",
                (channel_name, added_by, channel_id)
            )
            await conn.commit()
            return False
        await conn.execute(
            "INSERT INTO bot_channels (channel_id, channel_name, added_by, added_at) VALUES (?, ?, ?, ?)",
            (channel_id, channel_name, added_by, utc_now_iso())
        )
        await conn.commit()
        return True
    return await execute_db(_register)


async def db_get_all_bot_channels(only_banned: bool = False):
    """الحصول على جميع قنوات البوت"""
    async def _get(conn):
        if only_banned:
            cur = await conn.execute(
                "SELECT channel_id, channel_name, added_by, added_at, banned FROM bot_channels WHERE banned=1 ORDER BY added_at DESC"
            )
        else:
            cur = await conn.execute(
                "SELECT channel_id, channel_name, added_by, added_at, banned FROM bot_channels ORDER BY added_at DESC"
            )
        return await cur.fetchall()
    return await execute_db(_get)

# ===== دوال إدارة المنشورات =====

async def db_save_posts(channel_db_id: int, posts: list) -> int:
    """حفظ منشورات في قاعدة البيانات"""
    async def _save(conn):
        values = []
        for text_content, media_type, media_file_id in posts:
            values.append((channel_db_id, sanitize_text(text_content), media_type, media_file_id, utc_now_iso()))
        await conn.executemany(
            "INSERT INTO posts (channel_db_id, text, media_type, media_file_id, created_at) VALUES (?, ?, ?, ?, ?)",
            values
        )
        await conn.commit()
        return len(values)
    return await execute_db(_save)


async def db_get_next_post(channel_db_id: int):
    """الحصول على المنشور التالي للنشر"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT id, text, media_type, media_file_id FROM posts WHERE channel_db_id=? AND published=0 AND (fail_count IS NULL OR fail_count < 3) ORDER BY id LIMIT 1",
            (channel_db_id,)
        )
        row = await cur.fetchone()
        if row:
            return {'id': row[0], 'text': row[1], 'media_type': row[2], 'media_file_id': row[3]}
        return None
    return await execute_db(_get)


async def db_mark_published(post_id: int):
    """تحديث المنشور على أنه منشور"""
    async def _mark(conn):
        await conn.execute("UPDATE posts SET published=1 WHERE id=?", (post_id,))
        await conn.commit()
    return await execute_db(_mark)


async def db_increment_fail_count(post_id: int):
    """زيادة عدد محاولات الفشل للمنشور"""
    async def _inc(conn):
        await conn.execute("UPDATE posts SET fail_count = fail_count + 1 WHERE id=?", (post_id,))
        await conn.commit()
    return await execute_db(_inc)


async def db_get_posts_count(channel_db_id: int) -> int:
    """الحصول على عدد المنشورات في قناة"""
    async def _count(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_count)


async def db_get_published_count(channel_db_id: int) -> int:
    """الحصول على عدد المنشورات المنشورة"""
    async def _count(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=1", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_count)


async def db_reset_all_posts_to_unpublished(channel_db_id: int) -> int:
    """إعادة تعيين جميع المنشورات إلى غير منشورة"""
    async def _reset(conn):
        await conn.execute("UPDATE posts SET published=0, fail_count=0 WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_reset)


async def db_reset_posts_to_unpublished(channel_db_id: int, user_id: int = None):
    """إعادة تعيين المنشورات إلى غير منشورة (مع التحقق من الصلاحية)"""
    async def _reset(conn):
        await conn.execute("UPDATE posts SET published=0, fail_count=0 WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
    return await execute_db(_reset)


async def db_get_user_posts_for_channel(channel_db_id: int, limit=15):
    """الحصول على منشورات المستخدم لقناة محددة"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT id, text, media_type FROM posts WHERE channel_db_id=? AND published=0 ORDER BY id LIMIT ?",
            (channel_db_id, limit)
        )
        return await cur.fetchall()
    return await execute_db(_get)


async def db_delete_single_post(post_id: int, user_id: int, channel_db_id: int) -> bool:
    """حذف منشور واحد"""
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


async def db_get_user_unpublished_posts(user_id: int) -> int:
    """الحصول على عدد المنشورات غير المنشورة للمستخدم"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=? AND p.published=0 AND uc.banned=0",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)


async def db_get_user_total_posts(user_id: int) -> int:
    """الحصول على عدد المنشورات الكلي للمستخدم"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=? AND uc.banned=0",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)


async def db_unpublished_count(channel_db_id: int) -> int:
    """الحصول على عدد المنشورات غير المنشورة لقناة"""
    async def _count(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=0", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_count)


async def db_update_post_views(post_id: int, views_count: int = None):
    """تحديث عدد مشاهدات المنشور"""
    async def _update_views(conn):
        if views_count is not None:
            await conn.execute(
                "UPDATE posts SET views_count = ?, last_view_time = ? WHERE id = ?",
                (views_count, utc_now_iso(), post_id)
            )
        else:
            await conn.execute(
                "UPDATE posts SET views_count = views_count + 1, last_view_time = ? WHERE id = ?",
                (utc_now_iso(), post_id)
            )
        await conn.commit()
    return await execute_db(_update_views)


async def db_stats():
    """الحصول على إحصائيات البوت العامة"""
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

# ===== دوال إدارة المجموعات =====

async def db_register_group(chat_id: int, chat_name: str, added_by: int, username: str = None) -> bool:
    """تسجيل مجموعة في قاعدة البيانات"""
    async def _register(conn):
        cur = await conn.execute("SELECT chat_id FROM bot_groups WHERE chat_id=?", (chat_id,))
        if await cur.fetchone():
            await conn.execute(
                "UPDATE bot_groups SET chat_name=?, username=?, added_by=? WHERE chat_id=?",
                (chat_name, username, added_by, chat_id)
            )
            await conn.commit()
            return False
        await conn.execute(
            "INSERT INTO bot_groups (chat_id, chat_name, username, added_by, added_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, chat_name, username, added_by, utc_now_iso())
        )
        await conn.execute("INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?, ?)", (added_by, chat_id))
        await conn.commit()
        return True
    return await execute_db(_register)


async def db_get_user_groups(user_id: int):
    """الحصول على مجموعات المستخدم (بما فيها المخفية)"""
    async def _get(conn):
        try:
            # المشرفين الحقيقيين
            cur = await conn.execute("""
                SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned
                FROM bot_groups bg
                WHERE bg.chat_id IN (SELECT chat_id FROM group_admins WHERE user_id = ?)
                ORDER BY bg.chat_name
            """, (user_id,))
            admin_groups = await cur.fetchall()

            # المالكين المخفيين
            cur = await conn.execute("""
                SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned
                FROM bot_groups bg
                INNER JOIN hidden_owner_groups hog ON bg.chat_id = hog.chat_id
                WHERE hog.owner_id = ?
                ORDER BY bg.chat_name
            """, (user_id,))
            owner_groups = await cur.fetchall()

            # المشرفين المخفيين
            cur = await conn.execute("""
                SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned
                FROM bot_groups bg
                INNER JOIN hidden_admins ha ON bg.chat_id = ha.chat_id
                WHERE ha.admin_id = ?
                ORDER BY bg.chat_name
            """, (user_id,))
            hidden_groups = await cur.fetchall()

            # دمج النتائج مع إزالة التكرار
            result = []
            seen = set()
            for group in admin_groups:
                chat_id = group[0]
                if chat_id not in seen:
                    seen.add(chat_id)
                    result.append(group)
            for group in owner_groups:
                chat_id = group[0]
                if chat_id not in seen:
                    seen.add(chat_id)
                    result.append(group)
            for group in hidden_groups:
                chat_id = group[0]
                if chat_id not in seen:
                    seen.add(chat_id)
                    result.append(group)
            return result
        except Exception as e:
            logger.error(f"خطأ في جلب مجموعات المستخدم {user_id}: {e}")
            return []
    return await execute_db(_get)


async def db_get_user_groups_count(user_id: int) -> int:
    """الحصول على عدد مجموعات المستخدم"""
    async def _get(conn):
        try:
            groups = await db_get_user_groups(user_id)
            return len(groups)
        except Exception as e:
            logger.error(f"خطأ في حساب عدد مجموعات المستخدم: {e}")
            return 0
    return await execute_db(_get)


async def db_get_all_groups(only_banned: bool = False):
    """الحصول على جميع المجموعات المسجلة"""
    async def _get(conn):
        if only_banned:
            cur = await conn.execute(
                "SELECT chat_id, chat_name, username, added_by, added_at, banned FROM bot_groups WHERE banned=1 ORDER BY added_at DESC"
            )
        else:
            cur = await conn.execute(
                "SELECT chat_id, chat_name, username, added_by, added_at, banned FROM bot_groups ORDER BY added_at DESC"
            )
        return await cur.fetchall()
    return await execute_db(_get)


async def db_set_chat_lock(chat_id: int, locked: bool, locked_by: int = None):
    """قفل أو فتح المجموعة"""
    async def _set(conn):
        if locked:
            await conn.execute(
                "INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?, 1, ?, ?)",
                (chat_id, utc_now_iso(), locked_by)
            )
        else:
            await conn.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await conn.commit()
    return await execute_db(_set)


async def is_chat_locked(chat_id: int) -> bool:
    """التحقق من حالة قفل المجموعة"""
    async def _check(conn):
        cur = await conn.execute("SELECT locked FROM chat_locks WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_check)

# ===================================================================
# ===== 34. دوال الصلاحيات (permission_*) =====
# ===================================================================

async def db_is_real_admin(chat_id: int, user_id: int) -> bool:
    """التحقق من كون المستخدم مشرفاً حقيقياً"""
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM group_admins WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_check)


async def db_is_hidden_owner(chat_id: int, user_id: int) -> bool:
    """التحقق من كون المستخدم مالكاً مخفياً"""
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_check)


async def db_is_hidden_admin(chat_id: int, user_id: int) -> bool:
    """التحقق من كون المستخدم مشرفاً مخفياً"""
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_check)


async def db_register_hidden_owner_group(chat_id: int, owner_id: int):
    """تسجيل مالك مخفي لمجموعة"""
    async def _register(conn):
        await conn.execute(
            "INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?, ?, 1)",
            (chat_id, owner_id)
        )
        await conn.execute("INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?, ?)", (owner_id, chat_id))
        await conn.commit()
    return await execute_db(_register)


async def db_add_hidden_admin(chat_id: int, admin_id: int, added_by: int) -> bool:
    """إضافة مشرف مخفي لمجموعة"""
    async def _add(conn):
        try:
            await conn.execute(
                "INSERT OR IGNORE INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?, ?, ?, ?)",
                (chat_id, admin_id, added_by, utc_now_iso())
            )
            await conn.execute("INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?, ?)", (admin_id, chat_id))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في إضافة مشرف مخفي: {e}")
            return False
    return await execute_db(_add)


async def db_remove_hidden_admin(chat_id: int, admin_id: int) -> bool:
    """إزالة مشرف مخفي من مجموعة"""
    async def _remove(conn):
        await conn.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
        await conn.execute("DELETE FROM user_groups_link WHERE user_id=? AND chat_id=?", (admin_id, chat_id))
        await conn.commit()
        return True
    return await execute_db(_remove)


async def db_sync_group_admins(chat_id: int, bot, owner_id: int = None) -> int:
    """مزامنة مشرفي المجموعة مع قاعدة البيانات"""
    try:
        admins = await bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        if not admin_ids:
            logger.warning(f"⚠️ لا يوجد مشرفين في المجموعة {chat_id}")
            return 0

        async def _update(conn):
            await conn.execute("DELETE FROM group_admins WHERE chat_id=?", (chat_id,))
            if admin_ids:
                values = [(chat_id, uid) for uid in admin_ids]
                await conn.executemany("INSERT INTO group_admins (chat_id, user_id) VALUES (?, ?)", values)
                await conn.commit()
            return len(admin_ids)

        count = await execute_db(_update)
        for admin_id in admin_ids:
            invalidate_auth_cache(chat_id, admin_id)
        return count
    except Exception as e:
        logger.error(f"خطأ في مزامنة مشرفي المجموعة {chat_id}: {e}")
        return 0


async def is_authorized_in_group(bot, chat_id: int, user_id: int) -> bool:
    """التحقق المتكامل من صلاحية المستخدم في المجموعة"""
    if user_id == PRIMARY_OWNER_ID:
        return True

    bot_perms = await check_bot_admin_permissions_group(bot, chat_id)
    if not bot_perms['can_act']:
        logger.warning(f"⚠️ البوت ليس مشرفاً في {chat_id}")
        return False

    cache_key = f"auth_{chat_id}_{user_id}"
    if CACHETOOLS_AVAILABLE:
        if cache_key in _auth_cache:
            return _auth_cache[cache_key]
    else:
        if cache_key in _auth_cache:
            cached_time, value = _auth_cache[cache_key]
            if time_module.time() - cached_time < _AUTH_CACHE_TTL:
                return value

    authorized = False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            async def _update_real_admin(conn):
                await conn.execute("INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))
                await conn.commit()
            await execute_db(_update_real_admin)
            authorized = True
        else:
            if await db_is_hidden_owner(chat_id, user_id):
                if not await is_currently_admin_in_group(bot, chat_id, user_id):
                    async def _remove_hidden_owner(conn):
                        await conn.execute("DELETE FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
                        await conn.commit()
                    await execute_db(_remove_hidden_owner)
                    authorized = False
                else:
                    authorized = True
            elif await db_is_hidden_admin(chat_id, user_id):
                if not await is_currently_admin_in_group(bot, chat_id, user_id):
                    async def _remove_hidden_admin(conn):
                        await conn.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, user_id))
                        await conn.commit()
                    await execute_db(_remove_hidden_admin)
                    authorized = False
                else:
                    authorized = True
            elif await db_is_real_admin(chat_id, user_id):
                if not await is_currently_admin_in_group(bot, chat_id, user_id):
                    async def _remove_real_admin(conn):
                        await conn.execute("DELETE FROM group_admins WHERE chat_id=? AND user_id=?", (chat_id, user_id))
                        await conn.commit()
                    await execute_db(_remove_real_admin)
                    authorized = False
                else:
                    authorized = True
            else:
                authorized = False
    except Exception as e:
        logger.warning(f"⚠️ فشل التحقق المباشر من مشرف {user_id} في {chat_id}: {e}")
        if await db_is_hidden_owner(chat_id, user_id) or await db_is_hidden_admin(chat_id, user_id) or await db_is_real_admin(chat_id, user_id):
            authorized = True
        else:
            authorized = False

    if CACHETOOLS_AVAILABLE:
        _auth_cache[cache_key] = authorized
    else:
        _auth_cache[cache_key] = (time_module.time(), authorized)
    return authorized


def invalidate_auth_cache(chat_id: int = None, user_id: int = None):
    """إبطال التخزين المؤقت للصلاحيات"""
    try:
        if chat_id is not None and user_id is not None:
            key = f"auth_{chat_id}_{user_id}"
            _auth_cache.pop(key, None)
            if not CACHETOOLS_AVAILABLE:
                _auth_cache_time.pop(key, None)
        elif chat_id is not None:
            keys_to_remove = [k for k in list(_auth_cache.keys()) if k.startswith(f"auth_{chat_id}_")]
            for k in keys_to_remove:
                _auth_cache.pop(k, None)
                if not CACHETOOLS_AVAILABLE:
                    _auth_cache_time.pop(k, None)
        else:
            _auth_cache.clear()
            if not CACHETOOLS_AVAILABLE:
                _auth_cache_time.clear()
    except Exception as e:
        logger.error(f"خطأ في invalidate_auth_cache: {e}")


async def check_bot_admin_permissions_group(bot, chat_id: int) -> dict:
    """التحقق من صلاحيات البوت في المجموعة"""
    try:
        me = await bot.get_chat_member(chat_id, bot.id)
        if me.status not in ['administrator', 'creator']:
            return {'can_act': False, 'reason': 'البوت ليس مشرفاً في المجموعة'}

        permissions = {
            'can_ban': getattr(me, 'can_restrict_members', False),
            'can_pin': getattr(me, 'can_pin_messages', False),
            'can_delete': getattr(me, 'can_delete_messages', False),
            'can_invite': getattr(me, 'can_invite_users', False)
        }
        missing = [k for k, v in permissions.items() if not v]
        if missing:
            return {'can_act': False, 'reason': f'البوت يحتاج صلاحيات: {", ".join(missing)}'}
        return {'can_act': True, 'reason': ''}
    except Exception as e:
        return {'can_act': False, 'reason': str(e)}


async def refresh_group_admins_and_hidden_owners_loop(bot):
    """حلقة تحديث صلاحيات المجموعات والمشرفين المخفيين"""
    while True:
        try:
            async def _get_all_groups(conn):
                cur = await conn.execute("SELECT chat_id FROM bot_groups WHERE banned=0")
                return [row[0] for row in await cur.fetchall()]

            groups = await execute_db(_get_all_groups)
            for chat_id in groups:
                try:
                    await db_sync_group_admins(chat_id, bot)

                    async def _check_hidden_owners(conn):
                        cur = await conn.execute("SELECT owner_id FROM hidden_owner_groups WHERE chat_id=?", (chat_id,))
                        owners = [row[0] for row in await cur.fetchall()]
                        for owner_id in owners:
                            try:
                                member = await bot.get_chat_member(chat_id, owner_id)
                                if member.status not in ['administrator', 'creator']:
                                    await conn.execute("DELETE FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, owner_id))
                                    invalidate_auth_cache(chat_id, owner_id)
                                    logger.info(f"🗑️ تم إزالة المالك المخفي {owner_id} من المجموعة {chat_id}")
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
                                    logger.info(f"🗑️ تم إزالة المشرف المخفي {admin_id} من المجموعة {chat_id}")
                            except Exception as e:
                                logger.error(f"فشل التحقق من المشرف المخفي {admin_id} في {chat_id}: {e}")
                        await conn.commit()

                    await execute_db(_check_hidden_owners)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"فشل تحديث صلاحيات المجموعة {chat_id}: {e}")

            logger.info(f"✅ تم تحديث صلاحيات {len(groups)} مجموعة")
        except Exception as e:
            logger.error(f"خطأ في حلقة تحديث الصلاحيات: {e}")
        await asyncio.sleep(3600)


async def is_currently_admin_in_group(bot, chat_id: int, user_id: int) -> bool:
    """التحقق المباشر من كون المستخدم مشرفاً في تيليجرام"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        logger.error(f"خطأ في التحقق من مشرف {user_id} في {chat_id}: {e}")
        return False


async def detect_owner_type(bot, chat_id: int) -> dict:
    """كشف نوع المالك في المجموعة"""
    try:
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.status == 'creator':
                return {'is_hidden': False, 'user_id': admin.user.id}
        return {'is_hidden': True, 'user_id': None}
    except Exception as e:
        logger.error(f"فشل كشف المالك في {chat_id}: {e}")
        return {'is_hidden': True, 'user_id': None}

# ===================================================================
# ===== 35. دوال إعدادات الأمان (security_*) =====
# ===================================================================

async def ensure_security_columns(conn):
    """ضمان وجود أعمدة الأمان في جدول group_security"""
    cur = await conn.execute("PRAGMA table_info(group_security)")
    existing = [row[1] for row in await cur.fetchall()]

    needed = ['mentions', 'delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
              'delete_documents', 'delete_stickers', 'delete_penalty', 'delete_penalty_duration']
    for col in needed:
        if col not in existing:
            await conn.execute(f"ALTER TABLE group_security ADD COLUMN {col} DEFAULT 0")

    old_columns = ['delete_links', 'delete_mentions', 'warn_message', 'slow_mode', 'slow_mode_seconds',
                   'welcome_enabled', 'welcome_text', 'goodbye_enabled', 'goodbye_text',
                   'delete_banned_words', 'auto_penalty', 'auto_mute_duration']
    for col in old_columns:
        if col not in existing:
            await conn.execute(f"ALTER TABLE group_security ADD COLUMN {col} DEFAULT 0")
    await conn.commit()


async def db_get_security_settings(chat_id: int, force_refresh: bool = False):
    """الحصول على إعدادات الأمان لمجموعة"""
    default_settings = {
        'links': False, 'mentions': False, 'warn': True, 'slow_mode': False,
        'slow_mode_seconds': 5, 'welcome_enabled': False,
        'welcome_text': "مرحباً {user} في {chat} 🤍",
        'goodbye_enabled': False, 'goodbye_text': "وداعاً {user} 👋",
        'delete_banned_words': False, 'auto_penalty': 'none', 'auto_mute_duration': 60,
        'delete_videos': False, 'delete_audio': False, 'delete_animation': False,
        'delete_service': False, 'delete_documents': False, 'delete_stickers': False,
        'delete_penalty': 'none', 'delete_penalty_duration': 0
    }

    if not force_refresh:
        if CACHETOOLS_AVAILABLE:
            if chat_id in _security_cache:
                return _security_cache[chat_id]
        else:
            if chat_id in _security_cache:
                cached_time, value = _security_cache[chat_id]
                if time_module.time() - cached_time < _SECURITY_CACHE_TTL:
                    return value

    try:
        async def _get(conn):
            original_factory = conn.row_factory
            conn.row_factory = aiosqlite.Row
            try:
                cur_check = await conn.execute("PRAGMA table_info(group_security)")
                columns = [row[1] for row in await cur_check.fetchall()]
                if 'mentions' not in columns:
                    await ensure_security_columns(conn)

                cur = await conn.execute(
                    """SELECT delete_links, mentions, warn_message, slow_mode,
                              slow_mode_seconds, welcome_enabled, welcome_text,
                              goodbye_enabled, goodbye_text, delete_banned_words,
                              auto_penalty, auto_mute_duration,
                              delete_videos, delete_audio, delete_animation,
                              delete_service, delete_documents, delete_stickers,
                              delete_penalty, delete_penalty_duration
                       FROM group_security WHERE chat_id=?""",
                    (chat_id,)
                )
                row = await cur.fetchone()
                if row:
                    settings = {
                        'links': row['delete_links'] == 1,
                        'mentions': row['mentions'] == 1,
                        'warn': row['warn_message'] == 1,
                        'slow_mode': row['slow_mode'] == 1,
                        'slow_mode_seconds': row['slow_mode_seconds'] if row['slow_mode_seconds'] is not None else 5,
                        'welcome_enabled': row['welcome_enabled'] == 1,
                        'welcome_text': row['welcome_text'] if row['welcome_text'] else default_settings['welcome_text'],
                        'goodbye_enabled': row['goodbye_enabled'] == 1,
                        'goodbye_text': row['goodbye_text'] if row['goodbye_text'] else default_settings['goodbye_text'],
                        'delete_banned_words': row['delete_banned_words'] == 1,
                        'auto_penalty': row['auto_penalty'] if row['auto_penalty'] else 'none',
                        'auto_mute_duration': row['auto_mute_duration'] if row['auto_mute_duration'] is not None else 60,
                        'delete_videos': row['delete_videos'] == 1,
                        'delete_audio': row['delete_audio'] == 1,
                        'delete_animation': row['delete_animation'] == 1,
                        'delete_service': row['delete_service'] == 1,
                        'delete_documents': row['delete_documents'] == 1,
                        'delete_stickers': row['delete_stickers'] == 1,
                        'delete_penalty': row['delete_penalty'] if 'delete_penalty' in row else 'none',
                        'delete_penalty_duration': row['delete_penalty_duration'] if 'delete_penalty_duration' in row else 0
                    }
                    if CACHETOOLS_AVAILABLE:
                        _security_cache[chat_id] = settings
                    else:
                        _security_cache[chat_id] = (time_module.time(), settings)
                    return settings

                await ensure_security_columns(conn)
                await conn.execute(
                    """INSERT INTO group_security
                       (chat_id, delete_links, mentions, warn_message, slow_mode,
                        slow_mode_seconds, welcome_enabled, welcome_text, goodbye_enabled,
                        goodbye_text, delete_banned_words, auto_penalty, auto_mute_duration,
                        delete_videos, delete_audio, delete_animation,
                        delete_service, delete_documents, delete_stickers,
                        delete_penalty, delete_penalty_duration)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (chat_id, 0, 0, 1, 0, 5, 0, default_settings['welcome_text'],
                     0, default_settings['goodbye_text'], 0, 'none', 60,
                     0, 0, 0, 0, 0, 0, 'none', 0)
                )
                await conn.commit()
                if CACHETOOLS_AVAILABLE:
                    _security_cache[chat_id] = default_settings
                else:
                    _security_cache[chat_id] = (time_module.time(), default_settings)
                return default_settings
            finally:
                conn.row_factory = original_factory

        return await execute_db(_get)
    except Exception as e:
        advanced_logger.log_error("خطأ في db_get_security_settings", e, {"chat_id": chat_id})
        return default_settings


async def db_set_security_settings(chat_id: int, **kwargs):
    """تعيين إعدادات الأمان لمجموعة"""
    try:
        async def _set(conn):
            await ensure_security_columns(conn)
            cur = await conn.execute("SELECT 1 FROM group_security WHERE chat_id=?", (chat_id,))
            exists = await cur.fetchone()

            if not exists:
                default_settings = {
                    'links': False, 'mentions': False, 'warn': True,
                    'slow_mode': False, 'slow_mode_seconds': 5,
                    'welcome_enabled': False, 'welcome_text': "مرحباً {user} في {chat} 🤍",
                    'goodbye_enabled': False, 'goodbye_text': "وداعاً {user} 👋",
                    'delete_banned_words': False, 'auto_penalty': 'none',
                    'auto_mute_duration': 60,
                    'delete_videos': False, 'delete_audio': False,
                    'delete_animation': False, 'delete_service': False,
                    'delete_documents': False, 'delete_stickers': False,
                    'delete_penalty': 'none', 'delete_penalty_duration': 0
                }
                final_settings = default_settings.copy()
                final_settings.update(kwargs)
                await conn.execute(
                    """INSERT INTO group_security
                       (chat_id, delete_links, mentions, warn_message, slow_mode,
                        slow_mode_seconds, welcome_enabled, welcome_text, goodbye_enabled,
                        goodbye_text, delete_banned_words, auto_penalty, auto_mute_duration,
                        delete_videos, delete_audio, delete_animation,
                        delete_service, delete_documents, delete_stickers,
                        delete_penalty, delete_penalty_duration)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (chat_id,
                     1 if final_settings.get('links', False) else 0,
                     1 if final_settings.get('mentions', False) else 0,
                     1 if final_settings.get('warn', True) else 0,
                     1 if final_settings.get('slow_mode', False) else 0,
                     final_settings.get('slow_mode_seconds', 5),
                     1 if final_settings.get('welcome_enabled', False) else 0,
                     final_settings.get('welcome_text', default_settings['welcome_text']),
                     1 if final_settings.get('goodbye_enabled', False) else 0,
                     final_settings.get('goodbye_text', default_settings['goodbye_text']),
                     1 if final_settings.get('delete_banned_words', False) else 0,
                     final_settings.get('auto_penalty', 'none'),
                     final_settings.get('auto_mute_duration', 60),
                     1 if final_settings.get('delete_videos', False) else 0,
                     1 if final_settings.get('delete_audio', False) else 0,
                     1 if final_settings.get('delete_animation', False) else 0,
                     1 if final_settings.get('delete_service', False) else 0,
                     1 if final_settings.get('delete_documents', False) else 0,
                     1 if final_settings.get('delete_stickers', False) else 0,
                     final_settings.get('delete_penalty', 'none'),
                     final_settings.get('delete_penalty_duration', 0)
                    )
                )
                await conn.commit()
                _security_cache.pop(chat_id, None)
                await cache_manager.delete(f"security_{chat_id}")
                return

            updates = []
            values = []
            for key, value in kwargs.items():
                if key == 'links':
                    updates.append("delete_links=?")
                    values.append(1 if value else 0)
                elif key == 'mentions':
                    updates.append("mentions=?")
                    values.append(1 if value else 0)
                elif key == 'warn':
                    updates.append("warn_message=?")
                    values.append(1 if value else 0)
                elif key == 'slow_mode':
                    updates.append("slow_mode=?")
                    values.append(1 if value else 0)
                elif key == 'slow_mode_seconds':
                    updates.append("slow_mode_seconds=?")
                    values.append(value)
                elif key == 'welcome_enabled':
                    updates.append("welcome_enabled=?")
                    values.append(1 if value else 0)
                elif key == 'welcome_text':
                    updates.append("welcome_text=?")
                    values.append(value)
                elif key == 'goodbye_enabled':
                    updates.append("goodbye_enabled=?")
                    values.append(1 if value else 0)
                elif key == 'goodbye_text':
                    updates.append("goodbye_text=?")
                    values.append(value)
                elif key == 'delete_banned_words':
                    updates.append("delete_banned_words=?")
                    values.append(1 if value else 0)
                elif key == 'auto_penalty':
                    updates.append("auto_penalty=?")
                    values.append(value)
                elif key == 'auto_mute_duration':
                    updates.append("auto_mute_duration=?")
                    values.append(value)
                elif key == 'delete_videos':
                    updates.append("delete_videos=?")
                    values.append(1 if value else 0)
                elif key == 'delete_audio':
                    updates.append("delete_audio=?")
                    values.append(1 if value else 0)
                elif key == 'delete_animation':
                    updates.append("delete_animation=?")
                    values.append(1 if value else 0)
                elif key == 'delete_service':
                    updates.append("delete_service=?")
                    values.append(1 if value else 0)
                elif key == 'delete_documents':
                    updates.append("delete_documents=?")
                    values.append(1 if value else 0)
                elif key == 'delete_stickers':
                    updates.append("delete_stickers=?")
                    values.append(1 if value else 0)
                elif key == 'delete_penalty':
                    updates.append("delete_penalty=?")
                    values.append(value)
                elif key == 'delete_penalty_duration':
                    updates.append("delete_penalty_duration=?")
                    values.append(value)

            if updates:
                query = f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id=?"
                values.append(chat_id)
                await conn.execute(query, values)
                await conn.commit()

        await execute_db(_set)
        _security_cache.pop(chat_id, None)
        await cache_manager.delete(f"security_{chat_id}")
    except sqlite3.OperationalError as e:
        if "no such column" in str(e):
            async def _add_cols(conn):
                await ensure_security_columns(conn)
            await execute_db(_add_cols)
            return await db_set_security_settings(chat_id, **kwargs)
        else:
            raise


async def db_get_delete_settings(chat_id: int) -> dict:
    """الحصول على إعدادات الحذف لمجموعة"""
    settings = await db_get_security_settings(chat_id)
    return {k: v for k, v in settings.items() if k.startswith('delete_')}


async def db_check_slow_mode(chat_id: int, user_id: int) -> bool:
    """التحقق من الوضع البطيء لمستخدم"""
    settings = await db_get_security_settings(chat_id)
    if not settings['slow_mode']:
        return True

    seconds = settings.get('slow_mode_seconds', 5)

    async def _check(conn):
        cur = await conn.execute("SELECT message_time FROM user_messages WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        row = await cur.fetchone()
        now = utc_now()
        if row:
            last_time = datetime.fromisoformat(row[0])
            if (now - last_time).total_seconds() < seconds:
                return False
        await conn.execute("INSERT OR REPLACE INTO user_messages (user_id, chat_id, message_time) VALUES (?, ?, ?)",
                          (user_id, chat_id, now.isoformat()))
        await conn.commit()
        return True
    return await execute_db(_check)


async def db_add_banned_word(word: str, chat_id: int, added_by: int) -> bool:
    """إضافة كلمة محظورة"""
    async def _add(conn):
        try:
            await conn.execute(
                "INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?, ?, ?, ?)",
                (word, chat_id, added_by, utc_now_iso())
            )
            await conn.commit()
            if '*' in word or '?' in word or '+' in word:
                await rebuild_banned_patterns()
            return True
        except:
            return False
    return await execute_db(_add)


async def db_remove_banned_word(word: str, chat_id: int) -> bool:
    """إزالة كلمة محظورة"""
    async def _remove(conn):
        await conn.execute("DELETE FROM banned_words WHERE word=? AND chat_id=?", (word, chat_id))
        await conn.commit()
        if '*' in word or '?' in word or '+' in word:
            await rebuild_banned_patterns()
        return True
    return await execute_db(_remove)


async def db_get_banned_words(chat_id: int):
    """الحصول على الكلمات المحظورة لمجموعة"""
    async def _get(conn):
        cur = await conn.execute("SELECT word, added_by, added_at FROM banned_words WHERE chat_id=? OR chat_id=-1 ORDER BY word", (chat_id,))
        return await cur.fetchall()
    return await execute_db(_get)


async def db_contains_banned_word(text: str, chat_id: int) -> str:
    """التحقق من وجود كلمة محظورة في النص"""
    words = await db_get_banned_words(chat_id)
    text_lower = text.lower()
    for word, _, _ in words:
        if word in text_lower:
            return word
    for pattern in BANNED_PATTERNS:
        if pattern.search(text_lower):
            return pattern.pattern
    return None


async def add_banned_pattern(pattern: str) -> bool:
    """إضافة نمط محظور"""
    try:
        compiled = re.compile(pattern.lower())
        BANNED_PATTERNS.append(compiled)
        return True
    except:
        return False


async def check_banned_patterns(text: str) -> bool:
    """التحقق من الأنماط المحظورة"""
    text_lower = text.lower()
    for pattern in BANNED_PATTERNS:
        if pattern.search(text_lower):
            return True
    return False


async def db_get_hidden_admins(chat_id: int) -> List[Dict]:
    """الحصول على المشرفين المخفيين لمجموعة"""
    async def _get(conn):
        cur = await conn.execute("""
            SELECT admin_id, added_by, added_at
            FROM hidden_admins
            WHERE chat_id=?
            ORDER BY added_at DESC
        """, (chat_id,))
        rows = await cur.fetchall()
        return [{'admin_id': row[0], 'added_by': row[1], 'added_at': row[2]} for row in rows]
    return await execute_db(_get)


async def db_get_all_hidden_admins(user_id: int) -> List[Dict]:
    """الحصول على جميع المجموعات التي يكون فيها المستخدم مشرفاً مخفياً"""
    async def _get(conn):
        cur = await conn.execute("""
            SELECT chat_id, added_at
            FROM hidden_admins
            WHERE admin_id=?
        """, (user_id,))
        rows = await cur.fetchall()
        return [{'chat_id': row[0], 'added_at': row[1]} for row in rows]
    return await execute_db(_get)


async def db_should_hide_group_from_user(chat_id: int, user_id: int) -> bool:
    """التحقق من إخفاء المجموعة عن المستخدم"""
    async def _check(conn):
        if await db_is_hidden_owner(chat_id, user_id):
            return False
        if await db_is_hidden_admin(chat_id, user_id):
            return True
        return False
    return await execute_db(_check)


async def db_get_hidden_owner_groups(user_id: int):
    """الحصول على مجموعات المالك المخفي"""
    async def _get(conn):
        cur = await conn.execute("""
            SELECT chat_id FROM hidden_owner_groups
            WHERE owner_id=?
        """, (user_id,))
        return [row[0] for row in await cur.fetchall()]
    return await execute_db(_get)


async def db_get_hidden_admins_for_user(user_id: int):
    """الحصول على المجموعات التي يكون فيها المستخدم مشرفاً مخفياً"""
    async def _get(conn):
        cur = await conn.execute("""
            SELECT chat_id, added_by, added_at
            FROM hidden_admins
            WHERE admin_id=?
        """, (user_id,))
        return await cur.fetchall()
    return await execute_db(_get)

# ===================================================================
# ===== 36. دوال الجدولة (schedule_*) =====
# ===================================================================

class ScheduleType(Enum):
    """أنواع الجدولة"""
    INTERVAL = "interval"
    CRON = "cron"
    RECURRING = "recurring"


async def db_save_schedule(channel_db_id: int, schedule_type: str, interval_minutes: int = None,
                           interval_hours: int = None, interval_days: int = None,
                           days_of_week: str = None, specific_dates: str = None,
                           publish_time: str = None, cron_expression: str = None):
    """حفظ إعدادات الجدولة لقناة"""
    async def _save(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO schedule (channel_db_id, schedule_type, interval_minutes,
                interval_hours, interval_days, days_of_week, specific_dates, publish_time,
                cron_expression, next_publish_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """, (channel_db_id, schedule_type, interval_minutes, interval_hours, interval_days,
              days_of_week, specific_dates, publish_time or "00:00", cron_expression))
        await conn.commit()
    return await execute_db(_save)


async def db_get_schedule(channel_db_id: int):
    """الحصول على إعدادات الجدولة لقناة"""
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
    """تعيين تاريخ النشر التالي"""
    async def _set(conn):
        if next_date:
            await conn.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?",
                              (next_date.isoformat(), channel_db_id))
        else:
            await conn.execute("UPDATE schedule SET next_publish_date=NULL WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
    return await execute_db(_set)


async def db_set_last_publish(channel_db_id: int, publish_time: datetime):
    """تعيين تاريخ النشر الأخير"""
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO last_publish (channel_db_id, last_publish_time) VALUES (?, ?)",
                          (channel_db_id, publish_time.isoformat()))
        await conn.commit()
    return await execute_db(_set)


async def schedule_cron(channel_db_id: int, cron_expression: str):
    """تعيين جدولة بنمط Cron"""
    async def _save(conn):
        await conn.execute("""
            UPDATE schedule SET schedule_type='cron', cron_expression=?, next_publish_date=NULL
            WHERE channel_db_id=?
        """, (cron_expression, channel_db_id))
        await conn.commit()
    return await execute_db(_save)


async def db_update_next_publish_date(channel_db_id: int):
    """تحديث تاريخ النشر التالي بناءً على الجدولة"""
    async def _update(conn):
        schedule = await db_get_schedule(channel_db_id)
        last_publish_cur = await conn.execute("SELECT last_publish_time FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
        last_row = await last_publish_cur.fetchone()
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
                    minute_cron, hour_cron, day_cron, month_cron, weekday_cron = parts[:5]
                    next_date = last_time + timedelta(days=1)
                    for i in range(1, 31):
                        check_date = last_time + timedelta(days=i)
                        if check_date.hour == hour and check_date.minute == minute:
                            if day_cron == '*' or check_date.day == int(day_cron):
                                if month_cron == '*' or check_date.month == int(month_cron):
                                    if weekday_cron == '*' or check_date.weekday() == int(weekday_cron):
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

            await conn.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?",
                              (next_date.isoformat(), channel_db_id))
            await conn.commit()
    return await execute_db(_update)


async def db_set_publish_time(channel_db_id: int, time_str: str):
    """تعيين وقت النشر"""
    async def _set(conn):
        await conn.execute("UPDATE schedule SET publish_time=? WHERE channel_db_id=?", (time_str, channel_db_id))
        await conn.commit()
    return await execute_db(_set)


async def db_add_scheduled_post(chat_id: int, text: str, publish_time: datetime):
    """إضافة منشور مجدول"""
    async def _add(conn):
        await conn.execute(
            "INSERT INTO scheduled_posts (chat_id, text, publish_time, fail_count) VALUES (?, ?, ?, 0)",
            (chat_id, sanitize_text(text), publish_time.isoformat())
        )
        await conn.commit()
    return await execute_db(_add)


async def db_get_due_scheduled_posts(now: datetime, limit: int = 50):
    """الحصول على المنشورات المجدولة المستحقة"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT id, chat_id, text, fail_count FROM scheduled_posts WHERE publish_time <= ? LIMIT ?",
            (now.isoformat(), limit)
        )
        return await cur.fetchall()
    return await execute_db(_get)


async def db_update_scheduled_post_fail(post_id: int, fail_count: int):
    """تحديث عدد محاولات الفشل لمنشور مجدول"""
    async def _update(conn):
        await conn.execute("UPDATE scheduled_posts SET fail_count = ? WHERE id = ?", (fail_count, post_id))
        await conn.commit()
    return await execute_db(_update)


async def db_delete_scheduled_post(post_id: int):
    """حذف منشور مجدول"""
    async def _delete(conn):
        await conn.execute("DELETE FROM scheduled_posts WHERE id = ?", (post_id,))
        await conn.commit()
    return await execute_db(_delete)

# ===================================================================
# ===== 37. دوال الردود (reply_*) =====
# ===================================================================

async def db_add_reply(keyword, reply):
    """إضافة رد آلي"""
    async def _add(conn):
        await conn.execute("INSERT OR REPLACE INTO group_replies (keyword, reply) VALUES (?,?)", (keyword.lower(), reply))
        await conn.commit()
    return await execute_db(_add)


async def db_del_reply(keyword):
    """حذف رد آلي"""
    async def _del(conn):
        await conn.execute("DELETE FROM group_replies WHERE keyword=?", (keyword.lower(),))
        await conn.commit()
    return await execute_db(_del)


async def db_get_reply(keyword):
    """الحصول على رد آلي"""
    async def _get(conn):
        cur = await conn.execute("SELECT reply FROM group_replies WHERE keyword=?", (keyword.lower(),))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)


async def db_get_all_replies():
    """الحصول على جميع الردود الآلية"""
    async def _get(conn):
        cur = await conn.execute("SELECT keyword, reply FROM group_replies ORDER BY keyword")
        return await cur.fetchall()
    return await execute_db(_get)

# ===================================================================
# ===== 38. دوال الردود التلقائية المتقدمة (auto_reply_*) =====
# ===================================================================

async def db_get_auto_reply_settings(chat_id: int) -> dict:
    """الحصول على إعدادات الردود التلقائية لمجموعة"""
    async def _get(conn):
        cur = await conn.execute("SELECT enabled, only_admins, ignore_bots FROM auto_reply_settings WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        if row:
            return {'enabled': row[0] == 1, 'only_admins': row[1] == 1, 'ignore_bots': row[2] == 1}
        return {'enabled': True, 'only_admins': False, 'ignore_bots': True}
    return await execute_db(_get)


async def db_set_auto_reply_enabled(chat_id: int, enabled: bool) -> None:
    """تعيين حالة الردود التلقائية لمجموعة"""
    async def _set(conn):
        await conn.execute(
            "INSERT OR REPLACE INTO auto_reply_settings (chat_id, enabled, updated_at) VALUES (?, 1, CURRENT_TIMESTAMP)" if enabled else "INSERT OR REPLACE INTO auto_reply_settings (chat_id, enabled, updated_at) VALUES (?, 0, CURRENT_TIMESTAMP)",
            (chat_id,)
        )
        await conn.commit()
    return await execute_db(_set)


async def db_set_auto_reply_only_admins(chat_id: int, only_admins: bool) -> None:
    """تعيين حالة الردود للمشرفين فقط"""
    async def _set(conn):
        await conn.execute(
            "UPDATE auto_reply_settings SET only_admins=?, updated_at=CURRENT_TIMESTAMP WHERE chat_id=?",
            (1 if only_admins else 0, chat_id)
        )
        await conn.commit()
    return await execute_db(_set)


async def db_toggle_auto_reply(chat_id: int) -> bool:
    """تبديل حالة الردود التلقائية"""
    settings = await db_get_auto_reply_settings(chat_id)
    new_status = not settings['enabled']
    await db_set_auto_reply_enabled(chat_id, new_status)
    return new_status


async def db_get_user_auto_reply_status(user_id: int) -> bool:
    """الحصول على حالة الردود التلقائية للمستخدم"""
    async def _get(conn):
        cur = await conn.execute("SELECT auto_reply_enabled FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] == 1 if row else True
    return await execute_db(_get)


async def db_set_user_auto_reply_status(user_id: int, enabled: bool) -> None:
    """تعيين حالة الردود التلقائية للمستخدم"""
    async def _set(conn):
        await conn.execute("UPDATE users SET auto_reply_enabled=? WHERE user_id=?", (1 if enabled else 0, user_id))
        await conn.commit()
    return await execute_db(_set)

# ===================================================================
# ===== 39. دوال التذاكر (ticket_*) =====
# ===================================================================

async def db_get_next_ticket_number():
    """الحصول على رقم التذكرة التالي"""
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='last_ticket_number'")
        row = await cur.fetchone()
        return int(row[0]) if row else 0
    return await execute_db(_get)


async def db_save_ticket(user_id, username, message, ticket_num):
    """حفظ تذكرة دعم جديدة"""
    async def _save(conn):
        created_at = utc_now_iso()
        await conn.execute(
            "INSERT INTO support_tickets (user_id, username, message, ticket_number, status, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, username, sanitize_text(message), ticket_num, 'pending', created_at)
        )
        await conn.commit()
        return True
    return await execute_db(_save)


async def db_get_user_ticket(user_id):
    """الحصول على آخر تذكرة للمستخدم"""
    async def _get(conn):
        cur = await conn.execute("SELECT ticket_number, status, created_at FROM support_tickets WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
        return await cur.fetchone()
    return await execute_db(_get)


async def db_get_all_tickets(limit=20):
    """الحصول على جميع التذاكر"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT id, user_id, username, message, ticket_number, status, created_at FROM support_tickets ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return await cur.fetchall()
    return await execute_db(_get)


async def db_get_last_ticket_id_for_user(user_id):
    """الحصول على آخر معرف تذكرة للمستخدم"""
    async def _get(conn):
        cur = await conn.execute("SELECT id FROM support_tickets WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)


async def db_mark_ticket_replied(ticket_id):
    """تحديث التذكرة على أنها تم الرد عليها"""
    async def _mark(conn):
        await conn.execute("UPDATE support_tickets SET status='replied', replied=1 WHERE id=?", (ticket_id,))
        await conn.commit()
    return await execute_db(_mark)


async def db_delete_all_tickets() -> int:
    """حذف جميع التذاكر"""
    async def _delete(conn):
        await conn.execute("DELETE FROM support_tickets")
        count = cur.rowcount
        await conn.execute("UPDATE settings SET value='0' WHERE key='last_ticket_number'")
        await conn.commit()
        return count
    return await execute_db(_delete)

# ===================================================================
# ===== 40. دوال الإحالات (referral_*) =====
# ===================================================================

async def db_get_referral_settings() -> dict:
    """الحصول على إعدادات الإحالات"""
    async def _get(conn):
        settings = {}
        cur = await conn.execute("SELECT key, value FROM referral_settings")
        rows = await cur.fetchall()
        for key, value in rows:
            settings[key] = value
        return settings
    return await execute_db(_get)


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


async def db_get_welcome_bonus_points() -> int:
    """الحصول على نقاط الترحيب"""
    settings = await db_get_referral_settings()
    return int(settings.get('welcome_bonus_points', '10'))

# ===================================================================
# ===== 41. دوال التذكيرات (reminder_*) =====
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


async def db_get_all_active_users_for_report() -> list:
    """الحصول على جميع المستخدمين النشطين للتقرير"""
    async def _get(conn):
        thirty_days_ago = (utc_now() - timedelta(days=30)).isoformat()
        cur = await conn.execute("SELECT user_id FROM users_cache WHERE last_updated >= ?", (thirty_days_ago,))
        return [row[0] for row in await cur.fetchall()]
    return await execute_db(_get)

# ===================================================================
# ===== 42. دوال المستويات (level_*) =====
# ===================================================================

LEVEL_REQUIREMENTS = {1: 0, 2: 100, 3: 250, 4: 500, 5: 1000, 6: 2000, 7: 3500, 8: 5000, 9: 7500, 10: 10000}


async def db_get_user_level(user_id: int):
    """الحصول على مستوى المستخدم"""
    async def _get(conn):
        cur = await conn.execute("SELECT points, level FROM user_levels WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row:
            return {'points': row[0], 'level': row[1]}
        return {'points': 0, 'level': 1}
    return await execute_db(_get)


async def db_update_user_level(user_id: int, points: int, level: int):
    """تحديث مستوى المستخدم"""
    async def _update(conn):
        await conn.execute("INSERT OR REPLACE INTO user_levels (user_id, points, level) VALUES (?,?,?)",
                          (user_id, points, level))
        await conn.commit()
    return await execute_db(_update)


user_points_last_hour = defaultdict(lambda: (0, 0.0))


async def add_points(user_id: int, update: Update = None, context: ContextTypes.DEFAULT_TYPE = None):
    """إضافة نقطة للمستخدم"""
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


async def get_rank(user_id: int) -> dict:
    """الحصول على رتبة المستخدم"""
    return await db_get_user_level(user_id)


async def get_top_users(limit: int = 10):
    """الحصول على أفضل المستخدمين"""
    async def _get(conn):
        cur = await conn.execute("SELECT user_id, points, level FROM user_levels ORDER BY points DESC LIMIT ?", (limit,))
        return await cur.fetchall()
    return await execute_db(_get)


async def daily_reward(user_id: int) -> int:
    """مكافأة يومية"""
    today = utc_now().date()

    async def _check(conn):
        cur = await conn.execute("SELECT last_daily_reward FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try:
                last_date = datetime.fromisoformat(row[0]).date()
                if last_date == today:
                    return 0
            except:
                pass
        await conn.execute("UPDATE users SET last_daily_reward=? WHERE user_id=?", (utc_now_iso(), user_id))
        await conn.commit()
        return 10

    reward = await execute_db(_check)
    if reward > 0:
        data = await db_get_user_level(user_id)
        await db_update_user_level(user_id, data['points'] + reward, data['level'])
    return reward


async def weekly_reward(user_id: int) -> int:
    """مكافأة أسبوعية"""
    week_start = (utc_now() - timedelta(days=utc_now().weekday())).date()

    async def _check(conn):
        cur = await conn.execute("SELECT last_weekly_reward FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try:
                last_date = datetime.fromisoformat(row[0]).date()
                if last_date >= week_start:
                    return 0
            except:
                pass
        await conn.execute("UPDATE users SET last_weekly_reward=? WHERE user_id=?", (utc_now_iso(), user_id))
        await conn.commit()
        return 50

    reward = await execute_db(_check)
    if reward > 0:
        data = await db_get_user_level(user_id)
        await db_update_user_level(user_id, data['points'] + reward, data['level'])
    return reward


ACHIEVEMENTS = {
    'first_post': {'name': 'أول منشور', 'points': 10, 'icon': '📝'},
    'first_week': {'name': 'أسبوع نشاط', 'points': 50, 'icon': '📅'},
    'first_month': {'name': 'شهر نشاط', 'points': 200, 'icon': '🎉'},
    'first_referral': {'name': 'أول إحالة', 'points': 25, 'icon': '🔗'},
    'ten_referrals': {'name': '10 إحالات', 'points': 100, 'icon': '🌟'},
    'first_contest': {'name': 'أول مسابقة', 'points': 30, 'icon': '🏆'},
    'contest_winner': {'name': 'فائز بمسابقة', 'points': 100, 'icon': '🥇'},
}


async def achievement_system(user_id: int, action: str) -> str:
    """نظام الإنجازات"""
    async def _get_achievements(conn):
        cur = await conn.execute("SELECT achievements FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else '[]'

    achievements = json.loads(await execute_db(_get_achievements) or '[]')

    if action == 'first_post' and 'first_post' not in achievements:
        achievements.append('first_post')
        await db_update_user_level(
            user_id,
            (await db_get_user_level(user_id))['points'] + ACHIEVEMENTS['first_post']['points'],
            1
        )
        return f"{ACHIEVEMENTS['first_post']['icon']} {ACHIEVEMENTS['first_post']['name']} (+{ACHIEVEMENTS['first_post']['points']} نقطة)"

    if action == 'first_referral' and 'first_referral' not in achievements:
        achievements.append('first_referral')
        await db_update_user_level(
            user_id,
            (await db_get_user_level(user_id))['points'] + ACHIEVEMENTS['first_referral']['points'],
            1
        )
        return f"{ACHIEVEMENTS['first_referral']['icon']} {ACHIEVEMENTS['first_referral']['name']} (+{ACHIEVEMENTS['first_referral']['points']} نقطة)"

    return ""

# ===================================================================
# ===== 43. دوال الترجمة (translation_*) =====
# ===================================================================

user_translation_settings_cache = {}
_user_translation_cache_lock = asyncio.Lock()


async def get_user_translation_language(user_id: int) -> str:
    """الحصول على لغة الترجمة للمستخدم"""
    async with _user_translation_cache_lock:
        if user_id in user_translation_settings_cache:
            return user_translation_settings_cache[user_id]

    async def _get(conn):
        cur = await conn.execute("SELECT lang FROM user_translation WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 'off'

    lang = await execute_db(_get)
    async with _user_translation_cache_lock:
        user_translation_settings_cache[user_id] = lang
    return lang


async def set_user_translation_language(user_id: int, lang: str):
    """تعيين لغة الترجمة للمستخدم"""
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO user_translation (user_id, lang) VALUES (?, ?)", (user_id, lang))
        await conn.commit()
    await execute_db(_set)
    async with _user_translation_cache_lock:
        user_translation_settings_cache[user_id] = lang


async def translate_text(text: str, target_lang: str) -> str:
    """ترجمة نص إلى اللغة المستهدفة"""
    if not text or target_lang == 'off' or target_lang == 'ar':
        return text

    cache_key = f"{hashlib.md5(text.encode()).hexdigest()}_{target_lang}"
    cached = await _translation_cache.get(cache_key)
    if cached:
        return cached

    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        translated = translator.translate(text)
        if translated:
            await _translation_cache.set(cache_key, translated)
            return translated
    except Exception as e:
        logger.error(f"فشل الترجمة: {e}")
    return text

# ===================================================================
# ===== 44. دوال المسابقات (contest_*) =====
# ===================================================================

class ContestTypes(Enum):
    """أنواع المسابقات"""
    QUIZ = "quiz"
    RAFFLE = "raffle"
    VOTE = "vote"
    SUBMISSION = "submission"


async def db_get_active_contests_with_participants(limit: int = 10) -> list:
    """الحصول على المسابقات النشطة مع عدد المشاركين"""
    try:
        async def _get(conn):
            conn.row_factory = aiosqlite.Row
            now = utc_now().isoformat()
            try:
                cur = await conn.execute(
                    """SELECT c.id, c.title, c.description, c.prize, c.end_date, c.contest_type,
                              COALESCE((SELECT COUNT(*) FROM contest_participants cp WHERE cp.contest_id = c.id), 0) as participants
                       FROM contests c
                       WHERE c.status = 'active' AND c.end_date > ?
                       ORDER BY c.end_date ASC LIMIT ?""",
                    (now, limit)
                )
                rows = await cur.fetchall()
                result = []
                for row in rows:
                    try:
                        result.append((
                            row['id'],
                            row['title'],
                            row['description'],
                            row['prize'],
                            row['end_date'],
                            row['participants'],
                            row['contest_type'] if 'contest_type' in row else 'raffle'
                        ))
                    except:
                        continue
                return result
            except Exception as e:
                logger.error(f"خطأ في تنفيذ الاستعلام: {e}")
                return []
        return await execute_db(_get)
    except Exception as e:
        logger.error(f"خطأ في db_get_active_contests_with_participants: {e}")
        return []


async def db_create_contest(creator_id: int, title: str, description: str, prize: str,
                            end_date: datetime, contest_type: str = 'raffle') -> int:
    """إنشاء مسابقة جديدة"""
    try:
        async def _create(conn):
            if not isinstance(end_date, datetime):
                raise ValueError("end_date must be datetime object")
            end_date_str = end_date.isoformat()
            created_at_str = utc_now_iso()
            cur = await conn.execute(
                """INSERT INTO contests (creator_id, title, description, prize, end_date, status, created_at, contest_type)
                   VALUES (?, ?, ?, ?, ?, 'active', ?, ?)""",
                (creator_id, title, description, prize, end_date_str, created_at_str, contest_type)
            )
            await conn.commit()
            return cur.lastrowid

        contest_id = await execute_db(_create)
        if contest_id:
            logger.info(f"✅ تم إنشاء مسابقة جديدة (ID: {contest_id}) بواسطة المستخدم {creator_id}")
        else:
            logger.warning(f"⚠️ فشل إنشاء المسابقة، لم يتم إرجاع ID للمستخدم {creator_id}")
        return contest_id
    except Exception as e:
        logger.error(f"❌ خطأ في db_create_contest: {e}")
        raise


async def db_get_contest(contest_id: int) -> dict | None:
    """الحصول على معلومات مسابقة"""
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT id, title, description, prize, end_date, status, winner_id, creator_id, created_at, contest_type
               FROM contests WHERE id = ?""",
            (contest_id,)
        )
        row = await cur.fetchone()
        if row:
            return {
                'id': row['id'], 'title': row['title'], 'description': row['description'],
                'prize': row['prize'], 'end_date': row['end_date'], 'status': row['status'],
                'winner_id': row['winner_id'], 'creator_id': row['creator_id'],
                'created_at': row['created_at'],
                'contest_type': row['contest_type'] if 'contest_type' in row else 'raffle'
            }
        return None
    return await execute_db(_get)


async def db_participate_in_contest(user_id: int, contest_id: int, answer: str = "") -> bool:
    """مشاركة مستخدم في مسابقة"""
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


async def db_get_user_participation(user_id: int, contest_id: int) -> dict | None:
    """الحصول على مشاركة مستخدم في مسابقة"""
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


async def db_set_contest_winner(contest_id: int, winner_id: int) -> bool:
    """تعيين فائز في مسابقة"""
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
    """الحصول على الفائزين في المسابقات"""
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT c.id, c.title, c.prize, cw.winner_id, cw.announced_at
               FROM contest_winners cw
               JOIN contests c ON cw.contest_id = c.id
               ORDER BY cw.announced_at DESC LIMIT ?""",
            (limit,)
        )
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
    """الحصول على مشارك عشوائي في مسابقة"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT user_id FROM contest_participants WHERE contest_id = ? ORDER BY RANDOM() LIMIT 1",
            (contest_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

# ===================================================================
# ===== 45. دوال إحصائيات القنوات (channel_stats_*) =====
# ===================================================================

async def db_get_channel_stats(channel_db_id: int) -> dict:
    """الحصول على إحصائيات قناة"""
    async def _get_stats(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """
            SELECT
                COUNT(*) as total_posts,
                SUM(CASE WHEN published = 1 THEN 1 ELSE 0 END) as published_posts,
                SUM(CASE WHEN published = 0 THEN 1 ELSE 0 END) as unpublished_posts,
                SUM(views_count) as total_views,
                AVG(views_count) as avg_views,
                MAX(created_at) as last_post_time,
                MIN(created_at) as first_post_time
            FROM posts
            WHERE channel_db_id = ?
            """,
            (channel_db_id,)
        )
        row = await cur.fetchone()

        if not row or row['total_posts'] == 0:
            return {
                'total_posts': 0, 'published_posts': 0, 'unpublished_posts': 0,
                'total_views': 0, 'avg_views': 0, 'last_post_time': None,
                'first_post_time': None, 'avg_time_between_posts': 0,
                'best_publish_hour': 0, 'best_publish_day': 0,
                'published_today': 0, 'published_this_week': 0,
                'published_this_month': 0, 'most_viewed_post': None,
                'least_viewed_post': None,
            }

        total_posts = row['total_posts'] or 0
        published_posts = row['published_posts'] or 0
        unpublished_posts = row['unpublished_posts'] or 0
        total_views = row['total_views'] or 0
        avg_views = row['avg_views'] or 0
        last_post_time = row['last_post_time']
        first_post_time = row['first_post_time']

        avg_time_between = 0
        if published_posts > 1 and last_post_time and first_post_time:
            try:
                last_dt = datetime.fromisoformat(last_post_time)
                first_dt = datetime.fromisoformat(first_post_time)
                time_diff = (last_dt - first_dt).total_seconds()
                avg_time_between = time_diff / (published_posts - 1) if published_posts > 1 else 0
            except:
                avg_time_between = 0

        best_hour = 0
        best_day = 0
        if published_posts > 0:
            cur = await conn.execute(
                """
                SELECT strftime('%H', created_at) as hour, COUNT(*) as count
                FROM posts
                WHERE channel_db_id = ? AND published = 1
                GROUP BY hour
                ORDER BY count DESC
                LIMIT 1
                """,
                (channel_db_id,)
            )
            hour_row = await cur.fetchone()
            if hour_row:
                best_hour = int(hour_row['hour'])

            cur = await conn.execute(
                """
                SELECT strftime('%w', created_at) as day, COUNT(*) as count
                FROM posts
                WHERE channel_db_id = ? AND published = 1
                GROUP BY day
                ORDER BY count DESC
                LIMIT 1
                """,
                (channel_db_id,)
            )
            day_row = await cur.fetchone()
            if day_row:
                best_day = int(day_row['day'])

        today = utc_now().date().isoformat()
        week_start = (utc_now() - timedelta(days=7)).isoformat()
        month_start = (utc_now() - timedelta(days=30)).isoformat()

        cur = await conn.execute(
            """
            SELECT
                SUM(CASE WHEN date(created_at) = ? THEN 1 ELSE 0 END) as today_count,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) as week_count,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) as month_count
            FROM posts
            WHERE channel_db_id = ? AND published = 1
            """,
            (today, week_start, month_start, channel_db_id)
        )
        extra_row = await cur.fetchone()
        published_today = extra_row['today_count'] or 0 if extra_row else 0
        published_this_week = extra_row['week_count'] or 0 if extra_row else 0
        published_this_month = extra_row['month_count'] or 0 if extra_row else 0

        most_viewed = None
        least_viewed = None
        cur = await conn.execute(
            """
            SELECT id, text, views_count
            FROM posts
            WHERE channel_db_id = ? AND published = 1
            ORDER BY views_count DESC
            LIMIT 1
            """,
            (channel_db_id,)
        )
        most_row = await cur.fetchone()
        if most_row:
            most_viewed = {
                'id': most_row['id'],
                'text': most_row['text'][:50] + '...' if most_row['text'] and len(most_row['text']) > 50 else most_row['text'],
                'views': most_row['views_count']
            }

        cur = await conn.execute(
            """
            SELECT id, text, views_count
            FROM posts
            WHERE channel_db_id = ? AND published = 1 AND views_count > 0
            ORDER BY views_count ASC
            LIMIT 1
            """,
            (channel_db_id,)
        )
        least_row = await cur.fetchone()
        if least_row:
            least_viewed = {
                'id': least_row['id'],
                'text': least_row['text'][:50] + '...' if least_row['text'] and len(least_row['text']) > 50 else least_row['text'],
                'views': least_row['views_count']
            }

        return {
            'total_posts': total_posts,
            'published_posts': published_posts,
            'unpublished_posts': unpublished_posts,
            'total_views': total_views,
            'avg_views': round(avg_views, 2) if avg_views else 0,
            'last_post_time': last_post_time,
            'first_post_time': first_post_time,
            'avg_time_between_posts': round(avg_time_between / 3600, 2) if avg_time_between else 0,
            'best_publish_hour': best_hour,
            'best_publish_day': best_day,
            'published_today': published_today,
            'published_this_week': published_this_week,
            'published_this_month': published_this_month,
            'most_viewed_post': most_viewed,
            'least_viewed_post': least_viewed,
        }
    return await execute_db(_get_stats)


async def db_get_channel_stats_summary(user_id: int) -> dict:
    """الحصول على ملخص إحصائيات قنوات المستخدم"""
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
            stats = await db_get_channel_stats(ch_db_id)
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


async def db_get_channel_growth(channel_db_id: int, days: int = 30) -> dict:
    """الحصول على نمو القناة خلال فترة"""
    async def _get_growth(conn):
        conn.row_factory = aiosqlite.Row
        start_date = (utc_now() - timedelta(days=days)).isoformat()
        cur = await conn.execute(
            """
            SELECT
                date(created_at) as post_date,
                COUNT(*) as count,
                SUM(views_count) as views
            FROM posts
            WHERE channel_db_id = ? AND created_at >= ?
            GROUP BY date(created_at)
            ORDER BY post_date
            """,
            (channel_db_id, start_date)
        )
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


# ===================================================================
# ===== 46. دوال الصحة والنظام (health_*) =====
# ===================================================================

async def check_database_health() -> bool:
    """التحقق من صحة قاعدة البيانات"""
    try:
        async def _check(conn):
            cur = await conn.execute("SELECT 1")
            row = await cur.fetchone()
            return row is not None
        return await execute_db(_check)
    except:
        return False


async def check_telegram_health() -> bool:
    """التحقق من صحة اتصال تيليجرام"""
    try:
        from telegram.ext import Application
        app = Application.builder().token(TOKEN).build()
        me = await app.bot.get_me()
        return me is not None
    except:
        return False


def get_ram_usage():
    """الحصول على استخدام الذاكرة"""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            'total': round(mem.total / (1024**3), 1),
            'used': round(mem.used / (1024**3), 1),
            'percent': mem.percent
        }
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


# ===================================================================
# ===== 47. دوال النسخ الاحتياطي (backup_*) =====
# ===================================================================

async def create_backup():
    """إنشاء نسخة احتياطية كاملة"""
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

        if CLOUD_BACKUP_ENABLED and GOOGLE_AUTH_AVAILABLE:
            await upload_backup_to_drive(backup_file)

        logger.info(f"✅ تم إنشاء نسخة احتياطية مشفرة: {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"❌ فشل إنشاء النسخة الاحتياطية: {e}")
        raise


async def incremental_backup():
    """إنشاء نسخة احتياطية متزايدة"""
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
            cur = await conn.execute(
                "SELECT * FROM users WHERE user_id IN (SELECT user_id FROM users_cache WHERE last_updated > ?)",
                (last_time.isoformat(),)
            )
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
    """الحصول على قائمة النسخ الاحتياطية"""
    backups = sorted(BACKUP_DIR.glob("backup_*.enc"), key=lambda x: x.stat().st_mtime, reverse=True)
    incremental = sorted(BACKUP_DIR.glob("incremental_*.inc"), key=lambda x: x.stat().st_mtime, reverse=True)
    return backups + incremental


async def restore_backup(backup_path: Path):
    """استعادة نسخة احتياطية"""
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
                        (post['id'], post['channel_db_id'], post['text'], post['media_type'], post['media_file_id'],
                         post['published'], post['fail_count'], post['views_count'], post['last_view_time'],
                         post['created_at'])
                    )
            if 'users' in data:
                for user in data['users']:
                    await conn.execute(
                        "INSERT OR IGNORE INTO users (user_id, auto_publish, banned, trial_used, subscription_end, referral_code, referred_by, active_channel, auto_reply_enabled, auto_recycle) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (user['user_id'], user['auto_publish'], user['banned'], user['trial_used'],
                         user['subscription_end'], user['referral_code'], user['referred_by'],
                         user['active_channel'], user['auto_reply_enabled'], user['auto_recycle'])
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


async def auto_backup():
    """حلقة النسخ الاحتياطي التلقائي"""
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
                    await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_backup', ?)",
                                      (utc_now_iso(),))
                    await conn.commit()
                await execute_db(_update_backup_time)

            consecutive_errors = 0
            backoff = AUTO_BACKUP_SLEEP
        except Exception as e:
            logger.error(f"⚠️ خطأ في النسخ الاحتياطي التلقائي: {e}")
            backoff = min(backoff * 1.5, max_backoff)
            await asyncio.sleep(backoff)


# ===================================================================
# ===== 48. دوال جوجل درايف (drive_*) =====
# ===================================================================

_DRIVE_SERVICE_CACHE = None
_DRIVE_SERVICE_CACHE_TIME = 0
_DRIVE_SERVICE_CACHE_TTL = 3600


async def get_google_drive_service(force_refresh: bool = False):
    """الحصول على خدمة Google Drive"""
    global _DRIVE_SERVICE_CACHE, _DRIVE_SERVICE_CACHE_TIME

    if not CLOUD_BACKUP_ENABLED or not GOOGLE_AUTH_AVAILABLE:
        logger.warning("☁️ Google Drive Backup معطل أو غير مدعوم")
        return None

    now = time_module.time()
    if not force_refresh and _DRIVE_SERVICE_CACHE and (now - _DRIVE_SERVICE_CACHE_TIME) < _DRIVE_SERVICE_CACHE_TTL:
        return _DRIVE_SERVICE_CACHE

    try:
        creds = None
        token_path = Path(TOKEN_FILE)

        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_path),
                                                              ['https://www.googleapis.com/auth/drive.file'])
            except Exception as e:
                logger.warning(f"⚠️ فشل تحميل التوكن المخزن: {e}")

        if creds and creds.valid:
            _DRIVE_SERVICE_CACHE = build('drive', 'v3', credentials=creds)
            _DRIVE_SERVICE_CACHE_TIME = now
            logger.info("✅ تم استعادة خدمة Google Drive من التوكن المخزن")
            return _DRIVE_SERVICE_CACHE

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
                _DRIVE_SERVICE_CACHE = build('drive', 'v3', credentials=creds)
                _DRIVE_SERVICE_CACHE_TIME = now
                logger.info("✅ تم تجديد توكن Google Drive")
                return _DRIVE_SERVICE_CACHE
            except Exception as e:
                logger.warning(f"⚠️ فشل تجديد التوكن: {e}")
                if token_path.exists():
                    token_path.unlink()

        if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
            logger.error(f"❌ ملف الاعتمادات غير موجود: {GOOGLE_CREDENTIALS_FILE}")
            return None

        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_FILE,
                                                         ['https://www.googleapis.com/auth/drive.file'])
        creds = flow.run_local_server(port=0)

        with open(token_path, 'w') as token:
            token.write(creds.to_json())

        _DRIVE_SERVICE_CACHE = build('drive', 'v3', credentials=creds)
        _DRIVE_SERVICE_CACHE_TIME = now
        logger.info("✅ تم الحصول على توكن Google Drive جديد")
        return _DRIVE_SERVICE_CACHE
    except Exception as e:
        logger.error(f"❌ خطأ في خدمة Google Drive: {e}")
        return None


async def upload_backup_to_drive(backup_path: Path, max_retries: int = 3) -> str:
    """رفع نسخة احتياطية إلى Google Drive"""
    if not CLOUD_BACKUP_ENABLED or not GOOGLE_AUTH_AVAILABLE or not GOOGLE_DRIVE_FOLDER_ID:
        return None

    if not backup_path.exists():
        logger.error(f"❌ ملف النسخ غير موجود: {backup_path}")
        return None

    for attempt in range(max_retries):
        try:
            service = await get_google_drive_service(force_refresh=(attempt > 0))
            if not service:
                if attempt == max_retries - 1:
                    logger.error("❌ فشل الحصول على خدمة Google Drive بعد عدة محاولات")
                    return None
                await asyncio.sleep(2 ** attempt)
                continue

            file_name = f"backup_{mecca_now().strftime('%Y%m%d_%H%M%S')}.enc"

            try:
                results = service.files().list(
                    q=f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents",
                    orderBy="createdTime desc",
                    pageSize=15,
                    fields="files(id, name)"
                ).execute()
                files = results.get('files', [])
                for old_file in files[10:]:
                    try:
                        service.files().delete(fileId=old_file['id']).execute()
                        logger.info(f"🗑️ تم حذف ملف قديم من Drive: {old_file['name']}")
                    except Exception as e:
                        logger.warning(f"⚠️ فشل حذف الملف القديم: {e}")
            except Exception as e:
                logger.warning(f"⚠️ فشل تنظيف الملفات القديمة: {e}")

            media = MediaFileUpload(
                str(backup_path),
                mimetype='application/octet-stream',
                resumable=True,
                chunksize=1024*1024
            )

            file_metadata = {
                'name': file_name,
                'parents': [GOOGLE_DRIVE_FOLDER_ID]
            }

            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            )
            response = file.execute()
            file_id = response.get('id')

            logger.info(f"✅ تم رفع النسخة إلى Google Drive: {file_id} (المحاولة {attempt+1})")
            return file_id
        except Exception as e:
            logger.error(f"❌ خطأ في رفع النسخة: {e}")
            if attempt == max_retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
    return None


# ===================================================================
# ===== 49. دوال العقوبات والإجراءات (moderation_*) =====
# ===================================================================

async def apply_penalty_with_duration(bot, chat_id: int, user_id: int, penalty: str,
                                      duration_minutes: int = 0, reason: str = ""):
    """تطبيق عقوبة مع مدة محددة"""
    if penalty == 'kick':
        return await execute_kick(bot, chat_id, user_id, reason=reason, moderator_id=bot.id)
    elif penalty == 'ban':
        return await execute_ban(bot, chat_id, user_id, reason=reason, moderator_id=bot.id)
    elif penalty == 'mute':
        return await execute_mute(bot, chat_id, user_id, duration_minutes=duration_minutes,
                                 reason=reason, moderator_id=bot.id)
    elif penalty == 'warn':
        return await execute_warn(bot, chat_id, user_id, bot.id, reason=reason)
    else:
        return False, "عقوبة غير معروفة"


async def delete_and_penalize(update: Update, context: ContextTypes.DEFAULT_TYPE, warning_message: str):
    """حذف رسالة وتطبيق عقوبة"""
    if not update.message:
        return

    message = update.message
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        await message.delete()
    except Exception as e:
        logger.error(f"فشل حذف الرسالة المخالفة: {e}")

    try:
        await safe_send_markdown(context.bot, chat_id, warning_message)
    except Exception as e:
        logger.error(f"فشل إرسال رسالة التحذير: {e}")

    settings = await db_get_security_settings(chat_id)
    penalty = settings.get('auto_penalty', 'none')
    if penalty != 'none':
        duration = settings.get('auto_mute_duration', 60)
        success, msg = await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty,
                                                        duration, reason="مخالفة قواعد المجموعة")
        if success:
            await safe_send_markdown(context.bot, chat_id, msg)


async def execute_moderation_action(bot, chat_id: int, user_id: int, action: str,
                                    reason: str = "", duration: int = None, moderator_id: int = None):
    """تنفيذ إجراء رقابي"""
    if action == 'ban':
        return await execute_ban(bot, chat_id, user_id, reason=reason, moderator_id=moderator_id)
    elif action == 'mute':
        return await execute_mute(bot, chat_id, user_id, duration_minutes=duration,
                                 reason=reason, moderator_id=moderator_id)
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


async def execute_ban(bot, chat_id: int, user_id: int, until_date=None, reason: str = "", moderator_id: int = None):
    """تنفيذ حظر مستخدم"""
    try:
        await bot.ban_chat_member(chat_id, user_id, until_date=until_date)

        async def _log(conn):
            await conn.execute(
                "INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'ban', 0, ?, ?, ?)",
                (chat_id, user_id, moderator_id or PRIMARY_OWNER_ID, reason[:200] if reason else "", utc_now_iso())
            )
            await conn.commit()
        await execute_db(_log)

        return True, f"✅ تم حظر المستخدم `{user_id}` بنجاح"
    except Exception as e:
        return False, f"❌ فشل الحظر: {str(e)[:100]}"


async def execute_mute(bot, chat_id: int, user_id: int, duration_minutes: int = None,
                       reason: str = "", moderator_id: int = None):
    """تنفيذ كتم مستخدم"""
    try:
        until_date = None
        duration_text = ""
        if duration_minutes and duration_minutes > 0:
            until_date = utc_now() + timedelta(minutes=duration_minutes)
            if duration_minutes < 60:
                duration_text = f" لمدة {duration_minutes} دقيقة"
            elif duration_minutes < 1440:
                duration_text = f" لمدة {duration_minutes // 60} ساعة"
            else:
                duration_text = f" لمدة {duration_minutes // 1440} يوم"
        else:
            duration_text = " بشكل دائم"
            duration_minutes = -1

        permissions = ChatPermissions(can_send_messages=False)
        await bot.restrict_chat_member(chat_id, user_id, permissions, until_date=until_date)

        async def _log(conn):
            await conn.execute(
                "INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'mute', ?, ?, ?, ?)",
                (chat_id, user_id, duration_minutes, moderator_id or PRIMARY_OWNER_ID,
                 reason[:200] if reason else "", utc_now_iso())
            )
            await conn.commit()
        await execute_db(_log)

        return True, f"✅ تم كتم المستخدم `{user_id}`{duration_text}"
    except Exception as e:
        return False, f"❌ فشل الكتم: {str(e)[:100]}"


async def execute_kick(bot, chat_id: int, user_id: int, reason: str = "", moderator_id: int = None):
    """تنفيذ طرد مستخدم"""
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id)

        async def _log(conn):
            await conn.execute(
                "INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'kick', 0, ?, ?, ?)",
                (chat_id, user_id, moderator_id or PRIMARY_OWNER_ID, reason[:200] if reason else "", utc_now_iso())
            )
            await conn.commit()
        await execute_db(_log)

        return True, f"✅ تم طرد المستخدم `{user_id}`"
    except Exception as e:
        return False, f"❌ فشل الطرد: {str(e)[:100]}"


async def execute_warn(bot, chat_id: int, user_id: int, moderator_id: int, reason: str = "", auto_ban_limit: int = 3):
    """تنفيذ تحذير مستخدم"""
    async def _add_warning(conn):
        cur = await conn.execute("SELECT warnings FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        row = await cur.fetchone()
        warnings = row[0] + 1 if row else 1
        await conn.execute("INSERT OR REPLACE INTO user_warnings (user_id, chat_id, warnings) VALUES (?,?,?)",
                          (user_id, chat_id, warnings))
        await conn.execute(
            "INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'warn', ?, ?, ?, ?)",
            (chat_id, user_id, warnings, moderator_id, reason[:200] if reason else "", utc_now_iso())
        )
        await conn.commit()
        return warnings

    warnings = await execute_db(_add_warning)

    if warnings >= auto_ban_limit:
        await execute_ban(bot, chat_id, user_id, reason=f"تلقائي بعد {warnings} تحذيرات", moderator_id=moderator_id)

        async def _clear_warnings(conn):
            await conn.execute("DELETE FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            await conn.commit()
        await execute_db(_clear_warnings)

        return True, f"⚠️ تم تحذير المستخدم `{user_id}` ({warnings}/{auto_ban_limit}) وتم حظره تلقائياً"

    return True, f"⚠️ تم تحذير المستخدم `{user_id}` ({warnings}/{auto_ban_limit})"


async def execute_restrict(bot, chat_id: int, user_id: int, reason: str = "", moderator_id: int = None):
    """تنفيذ تقييد مستخدم"""
    try:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )
        await bot.restrict_chat_member(chat_id, user_id, permissions)

        async def _log(conn):
            await conn.execute(
                "INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'restrict', 0, ?, ?, ?)",
                (chat_id, user_id, moderator_id or PRIMARY_OWNER_ID, reason[:200] if reason else "", utc_now_iso())
            )
            await conn.commit()
        await execute_db(_log)

        return True, f"✅ تم تقييد المستخدم `{user_id}` (لا يمكنه إرسال وسائط)"
    except Exception as e:
        return False, f"❌ فشل التقييد: {str(e)[:100]}"


async def execute_pin(bot, chat_id: int, message_id: int, disable_notification: bool = False):
    """تنفيذ تثبيت رسالة"""
    try:
        await bot.pin_chat_message(chat_id, message_id, disable_notification=disable_notification)
        return True, "✅ تم تثبيت الرسالة"
    except Exception as e:
        return False, f"❌ فشل التثبيت: {str(e)[:100]}"


async def execute_unban(bot, chat_id: int, user_id: int, moderator_id: int = None):
    """تنفيذ إلغاء حظر مستخدم"""
    try:
        await bot.unban_chat_member(chat_id, user_id)

        async def _log(conn):
            await conn.execute(
                "INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'unban', 0, ?, ?, ?)",
                (chat_id, user_id, moderator_id or PRIMARY_OWNER_ID, "", utc_now_iso())
            )
            await conn.commit()
        await execute_db(_log)

        return True, f"✅ تم إلغاء حظر المستخدم `{user_id}`"
    except Exception as e:
        return False, f"❌ فشل إلغاء الحظر: {str(e)[:100]}"


async def get_moderation_log(chat_id: int, limit: int = 20) -> str:
    """الحصول على سجل الإجراءات الرقابية"""
    async def _get_log(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT user_id, action, duration_minutes, reason, created_at
            FROM moderation_log
            WHERE chat_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (chat_id, limit))
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
        elif action == 'unban':
            duration_text = ""

        reason_text = f"\n   📝 السبب: {reason[:50]}" if reason else ""
        text += f"• `{user_id}` → {action}{duration_text}{reason_text}\n   🕐 {time_str}\n\n"

    return text


# ===================================================================
# ===== 50. نظام جمع المقاييس (Metrics) =====
# ===================================================================

class MetricsCollector:
    """نظام جمع مقاييس الأداء"""
    def __init__(self):
        self.commands_count = defaultdict(int)
        self.errors_count = defaultdict(int)
        self.response_times = []
        self.start_time = time_module.time()

    def record_command(self, command: str):
        """تسجيل أمر"""
        self.commands_count[command] += 1

    def record_error(self, error_type: str):
        """تسجيل خطأ"""
        self.errors_count[error_type] += 1

    def record_response_time(self, seconds: float):
        """تسجيل وقت الاستجابة"""
        self.response_times.append(seconds)
        if len(self.response_times) > 1000:
            self.response_times.pop(0)

    def get_stats(self) -> dict:
        """الحصول على الإحصائيات"""
        avg_response = sum(self.response_times) / len(self.response_times) if self.response_times else 0
        return {
            'uptime': time_module.time() - self.start_time,
            'total_commands': sum(self.commands_count.values()),
            'commands': dict(self.commands_count),
            'errors': dict(self.errors_count),
            'avg_response_time': avg_response
        }


metrics = MetricsCollector()


# ===================================================================
# ===== 51. دوال الصلاحيات الإضافية =====
# ===================================================================

async def is_bot_admin(user_id: int) -> bool:
    """التحقق من كون المستخدم مشرف بوت"""
    if user_id == PRIMARY_OWNER_ID:
        return True

    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM bot_admins WHERE user_id=?", (user_id,))
        return await cur.fetchone() is not None
    return await execute_db(_check)


async def add_bot_admin(user_id: int) -> bool:
    """إضافة مشرف بوت"""
    if user_id == PRIMARY_OWNER_ID:
        return True

    async def _add(conn):
        await conn.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (user_id,))
        await conn.commit()
        return True
    return await execute_db(_add)


async def remove_bot_admin(user_id: int) -> bool:
    """إزالة مشرف بوت"""
    if user_id == PRIMARY_OWNER_ID:
        return False

    async def _remove(conn):
        await conn.execute("DELETE FROM bot_admins WHERE user_id=?", (user_id,))
        await conn.commit()
        return True
    return await execute_db(_remove)


async def get_all_bot_admins() -> List[int]:
    """الحصول على جميع مشرفي البوت"""
    async def _get(conn):
        cur = await conn.execute("SELECT user_id FROM bot_admins")
        return [row[0] for row in await cur.fetchall()]
    return await execute_db(_get)


# ===================================================================
# ===== 52. دوال مساعدة أساسية (helpers) =====
# ===================================================================

async def is_user_bot(bot, user_id: int) -> bool:
    """التحقق من كون المستخدم بوتاً"""
    try:
        chat = await bot.get_chat(user_id)
        return chat.is_bot
    except Exception:
        return False


async def safe_send_to_user_or_group(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """إرسال رسالة بأمان إلى مستخدم أو مجموعة"""
    try:
        if update.callback_query:
            await safe_edit_markdown(update.callback_query, text)
        elif update.message:
            await safe_send_markdown(context.bot, update.message.chat_id, text)
        else:
            await safe_send_markdown(context.bot, update.effective_user.id, text)
    except Exception as e:
        logger.error(f"فشل إرسال رسالة في safe_send_to_user_or_group: {e}")


async def check_bot_permissions(bot, chat_id: int) -> tuple:
    """التحقق من صلاحيات البوت في الدردشة"""
    try:
        me = await bot.get_chat_member(chat_id, bot.id)
        if me.status not in ['administrator', 'creator', 'member']:
            return False, "البوت ليس لديه صلاحية"
        if me.status in ['administrator', 'creator']:
            can_send = getattr(me, 'can_send_messages', True)
            can_post = getattr(me, 'can_post_messages', True)
            if can_send or can_post:
                return True, ""
            return False, "البوت لا يملك صلاحية الإرسال"
        return True, ""
    except Exception as e:
        return False, str(e)


async def ensure_db_connection():
    """ضمان اتصال قاعدة البيانات"""
    try:
        async def _ping(conn):
            await conn.execute("SELECT 1")
        await execute_db(_ping)
        return True
    except Exception as e:
        logger.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}. جاري إعادة الاتصال...")
        await db_pool.close()
        await db_pool.initialize()
        return False


# ===================================================================
# ===== 53. دوال القوائم والأزرار (keyboard_*) =====
# ===================================================================

def get_auto_reply_keyboard(chat_id: int, settings: dict) -> InlineKeyboardMarkup:
    """الحصول على لوحة مفاتيح إعدادات الردود التلقائية"""
    status_text = "🟢 مفعل" if settings['enabled'] else "🔴 معطل"
    admin_text = "👑 مشرفين فقط" if settings['only_admins'] else "👥 الجميع"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📝 الردود التلقائية: {status_text}",
                              callback_data=f"{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}{chat_id}")],
        [InlineKeyboardButton(f"👥 المستخدمون: {admin_text}",
                              callback_data=f"{CallbackData.AUTO_REPLY_ADMINS_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🔄 إعادة تعيين الردود",
                              callback_data=f"{CallbackData.AUTO_REPLY_RESET_PREFIX}{chat_id}")],
        [InlineKeyboardButton("📊 إحصائيات الردود",
                              callback_data=f"{CallbackData.AUTO_REPLY_STATS_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع",
                              callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])


def get_user_auto_reply_keyboard(user_id: int, enabled: bool) -> InlineKeyboardMarkup:
    """الحصول على لوحة مفاتيح إعدادات الردود التلقائية للمستخدم"""
    status_text = "🟢 مفعل" if enabled else "🔴 معطل"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📝 الردود التلقائية: {status_text}",
                              callback_data=f"{CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX}{user_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])


def get_replies_keyboard():
    """الحصول على لوحة مفاتيح إدارة الردود"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة رد", callback_data=CallbackData.ADMIN_ADD_REPLY),
         InlineKeyboardButton("📋 عرض الردود", callback_data=CallbackData.ADMIN_LIST_REPLIES)],
        [InlineKeyboardButton("🗑️ حذف رد", callback_data=CallbackData.ADMIN_DEL_REPLY),
         InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])


def get_group_banned_words_keyboard(chat_id):
    """الحصول على لوحة مفاتيح إدارة الكلمات المحظورة للمجموعة"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كلمة", callback_data=f"{CallbackData.BANNED_WORDS_ADD_PREFIX}{chat_id}"),
         InlineKeyboardButton("📋 عرض الكلمات", callback_data=f"{CallbackData.BANNED_WORDS_LIST_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🗑️ حذف كلمة", callback_data=f"{CallbackData.BANNED_WORDS_REMOVE_PREFIX}{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])


def get_banned_words_admin_keyboard():
    """الحصول على لوحة مفاتيح إدارة الكلمات المحظورة العامة"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كلمة عامة", callback_data=CallbackData.ADMIN_ADD_BANNED_WORD),
         InlineKeyboardButton("📋 عرض الكلمات", callback_data=CallbackData.ADMIN_LIST_BANNED_WORDS)],
        [InlineKeyboardButton("🗑️ حذف كلمة", callback_data=CallbackData.ADMIN_REMOVE_BANNED_WORD),
         InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_BANNED_WORDS)]
    ])


def get_advanced_group_actions_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """الحصول على لوحة مفاتيح الإجراءات المتقدمة للمجموعة"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 حظر", callback_data=f"{CallbackData.GROUP_ACTION_BAN}:{chat_id}"),
         InlineKeyboardButton("🔇 كتم", callback_data=f"{CallbackData.GROUP_ACTION_MUTE}:{chat_id}")],
        [InlineKeyboardButton("⚠️ تحذير", callback_data=f"{CallbackData.GROUP_ACTION_WARN}:{chat_id}"),
         InlineKeyboardButton("👢 طرد", callback_data=f"{CallbackData.GROUP_ACTION_KICK}:{chat_id}")],
        [InlineKeyboardButton("🔒 تقييد", callback_data=f"{CallbackData.GROUP_ACTION_RESTRICT}:{chat_id}"),
         InlineKeyboardButton("📌 تثبيت", callback_data=f"{CallbackData.GROUP_ACTION_PIN}:{chat_id}")],
        [InlineKeyboardButton("🔓 إلغاء حظر", callback_data=f"{CallbackData.GROUP_ACTION_UNBAN}:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])


def get_advanced_mute_duration_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """الحصول على لوحة مفاتيح مدة الكتم المتقدمة"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱️ 5 دقائق", callback_data=f"adv_mute_duration:5:{chat_id}"),
         InlineKeyboardButton("⏱️ 30 دقيقة", callback_data=f"adv_mute_duration:30:{chat_id}")],
        [InlineKeyboardButton("⏱️ 1 ساعة", callback_data=f"adv_mute_duration:60:{chat_id}"),
         InlineKeyboardButton("⏱️ 12 ساعة", callback_data=f"adv_mute_duration:720:{chat_id}")],
        [InlineKeyboardButton("📆 يوم", callback_data=f"adv_mute_duration:1440:{chat_id}"),
         InlineKeyboardButton("📆 أسبوع", callback_data=f"adv_mute_duration:10080:{chat_id}")],
        [InlineKeyboardButton("🔇 كتم دائم", callback_data=f"adv_mute_duration:0:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")]
    ])


def get_admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """الحصول على لوحة مفاتيح لوحة التحكم للمشرفين"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'admin_users'), callback_data=CallbackData.ADMIN_USERS),
         InlineKeyboardButton(get_text(user_id, 'admin_banned'), callback_data=CallbackData.ADMIN_BANNED_USERS)],
        [InlineKeyboardButton(get_text(user_id, 'admin_channels'), callback_data=CallbackData.ADMIN_ALL_CHANNELS),
         InlineKeyboardButton("⛔ قنوات محظورة", callback_data=CallbackData.ADMIN_BANNED_CHANNELS)],
        [InlineKeyboardButton("📊 المجموعات", callback_data=CallbackData.ADMIN_GROUPS),
         InlineKeyboardButton("🚷 مجموعات محظورة", callback_data=CallbackData.ADMIN_BANNED_GROUPS)],
        [InlineKeyboardButton("📢 قنوات البوت", callback_data=CallbackData.ADMIN_BOT_CHANNELS),
         InlineKeyboardButton("🚫 قنوات بوت محظورة", callback_data=CallbackData.ADMIN_BANNED_BOT_CHANNELS)],
        [InlineKeyboardButton("❤️ تنشيط الكل", callback_data=CallbackData.ADMIN_ACTIVATE_ALL_CHANNELS),
         InlineKeyboardButton("📂 مراقبة المستخدمين", callback_data=CallbackData.ADMIN_MONITOR_USERS)],
        [InlineKeyboardButton("👑 + مشرف", callback_data=CallbackData.ADMIN_ADD_ADMIN),
         InlineKeyboardButton("🗑️ - مشرف", callback_data=CallbackData.ADMIN_REMOVE_ADMIN)],
        [InlineKeyboardButton("💬 ردود المجموعة", callback_data=CallbackData.ADMIN_REPLIES),
         InlineKeyboardButton("🚫 كلمات محظورة (عامة)", callback_data=CallbackData.ADMIN_BANNED_WORDS)],
        [InlineKeyboardButton("📝 إعدادات الردود", callback_data=CallbackData.ADMIN_AUTO_REPLY)],
        [InlineKeyboardButton("🔒 إعدادات NSFW", callback_data=CallbackData.NSFW_SETTINGS)],
        [InlineKeyboardButton("🏆 إنشاء مسابقة", callback_data=CallbackData.ADMIN_CREATE_CONTEST),
         InlineKeyboardButton("🏅 إعلان فائز", callback_data=CallbackData.ADMIN_DECLARE_WINNER)],
        [InlineKeyboardButton("🎫 كوبونات خصم", callback_data=CallbackData.ADMIN_COUPONS)],
        [InlineKeyboardButton("📊 استطلاعات رأي", callback_data=CallbackData.ADMIN_POLLS)],
        [InlineKeyboardButton("📢 إعلانات مدفوعة", callback_data=CallbackData.ADMIN_ADS)],
        [InlineKeyboardButton("❓ أسئلة شائعة (FAQ)", callback_data=CallbackData.ADMIN_FAQ)],
        [InlineKeyboardButton("🛠️ إجراءات متقدمة", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:0")],
        [InlineKeyboardButton("🖥️ حالة الرام", callback_data=CallbackData.ADMIN_RAM),
         InlineKeyboardButton("📊 إحصائيات عامة", callback_data=CallbackData.ADMIN_STATS)],
        [InlineKeyboardButton("📈 مقاييس الأداء", callback_data=CallbackData.ADMIN_METRICS)],
        [InlineKeyboardButton("💾 نسخة احتياطية", callback_data=CallbackData.ADMIN_BACKUP),
         InlineKeyboardButton("🔄 استعادة نسخة", callback_data=CallbackData.ADMIN_RESTORE_BACKUP)],
        [InlineKeyboardButton("⏱️ وقت النشر (عام)", callback_data=CallbackData.ADMIN_CHANGE_INTERVAL),
         InlineKeyboardButton("⚙️ إعدادات النسخ", callback_data=CallbackData.ADMIN_BACKUP_SETTINGS)],
        [InlineKeyboardButton("📢 نشر تحديث", callback_data=CallbackData.ADMIN_SEND_UPDATE),
         InlineKeyboardButton("⚙️ قناة التحديثات", callback_data=CallbackData.ADMIN_SET_UPDATE_CHANNEL)],
        [InlineKeyboardButton("📢 عرض القناة الحالية", callback_data=CallbackData.ADMIN_SHOW_UPDATE_CHANNEL)],
        [InlineKeyboardButton("🔄 التحديثات", callback_data=CallbackData.ADMIN_UPDATES),
         InlineKeyboardButton("🔒 الاشتراك الإجباري", callback_data=CallbackData.ADMIN_FORCE_SUBSCRIBE)],
        [InlineKeyboardButton("⚙️ تعيين القناة", callback_data=CallbackData.ADMIN_SET_FORCE_CHANNEL),
         InlineKeyboardButton("📨 إرسال رسالة", callback_data=CallbackData.ADMIN_BROADCAST)],
        [InlineKeyboardButton("📋 تذاكر الدعم", callback_data=CallbackData.ADMIN_SUPPORT_TICKETS),
         InlineKeyboardButton("🗑️ حذف جميع التذاكر", callback_data=CallbackData.ADMIN_DELETE_ALL_TICKETS)],
        [InlineKeyboardButton("📁 صلاحية /sendcode", callback_data=CallbackData.ADMIN_MANAGE_SENDCODE),
         InlineKeyboardButton("📋 قناة التقارير", callback_data=CallbackData.ADMIN_SHOW_LOG_CHANNEL)],
        [InlineKeyboardButton("📋 تعيين قناة التقارير", callback_data=CallbackData.ADMIN_SET_LOG_CHANNEL)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])


def security_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """الحصول على لوحة مفاتيح إعدادات الأمان"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 حذف الروابط", callback_data=f"security:links:{chat_id}"),
         InlineKeyboardButton("@ حذف المعرفات", callback_data=f"security:mentions:{chat_id}")],
        [InlineKeyboardButton("🚫 كلمات محظورة", callback_data=f"{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}{chat_id}"),
         InlineKeyboardButton("⏱️ الوضع البطيء", callback_data=f"security:slow_mode:{chat_id}")],
        [InlineKeyboardButton("🎬 حذف الفيديوهات", callback_data=f"security:delete_videos:{chat_id}"),
         InlineKeyboardButton("🛠️ حذف رسائل الخدمة", callback_data=f"security:delete_service:{chat_id}")],
        [InlineKeyboardButton("📄 حذف الملفات", callback_data=f"security:delete_documents:{chat_id}"),
         InlineKeyboardButton("🖼️ حذف الملصقات", callback_data=f"security:delete_stickers:{chat_id}")],
        [InlineKeyboardButton("🎵 حذف الصوتيات", callback_data=f"security:delete_audio:{chat_id}"),
         InlineKeyboardButton("🎞️ حذف المتحركات", callback_data=f"security:delete_animation:{chat_id}")],
        [InlineKeyboardButton("⚡ تفعيل الكل", callback_data=f"{CallbackData.SECURITY_ENABLE_ALL_PREFIX}{chat_id}"),
         InlineKeyboardButton("⛔ تعطيل الكل", callback_data=f"{CallbackData.SECURITY_DISABLE_ALL_PREFIX}{chat_id}")],
        [InlineKeyboardButton("⚖️ عقوبة الحذف", callback_data=f"{CallbackData.SECURITY_DELETE_PENALTY_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🎯 الترحيب", callback_data=f"security:welcome_enabled:{chat_id}"),
         InlineKeyboardButton("👋 الوداع", callback_data=f"security:goodbye_enabled:{chat_id}")],
        [InlineKeyboardButton("⚖️ تحديد العقوبة", callback_data=f"{CallbackData.PENALTY_MENU}:{chat_id}"),
         InlineKeyboardButton("📝 إعدادات الردود", callback_data=CallbackData.ADMIN_AUTO_REPLY)],
        [InlineKeyboardButton("🛠️ إجراءات متقدمة", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")],
        [InlineKeyboardButton("📜 سجل الإجراءات", callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}")],
        [InlineKeyboardButton("🔙 إغلاق", callback_data=CallbackData.SECURITY_CLOSE)]
    ])


def penalty_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """الحصول على لوحة مفاتيح اختيار العقوبة"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 طرد", callback_data=f"{CallbackData.PENALTY_KICK}:{chat_id}"),
         InlineKeyboardButton("🛑 حظر", callback_data=f"{CallbackData.PENALTY_BAN}:{chat_id}")],
        [InlineKeyboardButton("🔇 كتم", callback_data=f"{CallbackData.PENALTY_MUTE}:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])


def mute_duration_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """الحصول على لوحة مفاتيح اختيار مدة الكتم"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱️ 5 دقائق", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_5}:{chat_id}"),
         InlineKeyboardButton("⏱️ 30 دقيقة", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_30}:{chat_id}")],
        [InlineKeyboardButton("⏱️ 1 ساعة", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_60}:{chat_id}"),
         InlineKeyboardButton("⏱️ 12 ساعة", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_720}:{chat_id}")],
        [InlineKeyboardButton("📆 يوم", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_1440}:{chat_id}"),
         InlineKeyboardButton("📆 أسبوع", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_10080}:{chat_id}")],
        [InlineKeyboardButton("🔇 كتم دائم", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_PERMANENT}:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.PENALTY_MENU}:{chat_id}")]
    ])


async def build_days_keyboard(uid, context):
    """بناء لوحة مفاتيح اختيار أيام الأسبوع"""
    selected = context.user_data.get('selected_days', [])
    day_names = [
        get_text(uid, 'monday'), get_text(uid, 'tuesday'), get_text(uid, 'wednesday'),
        get_text(uid, 'thursday'), get_text(uid, 'friday'), get_text(uid, 'saturday'),
        get_text(uid, 'sunday')
    ]

    kb_buttons = []
    for i in range(0, 7, 3):
        row = []
        for j in range(3):
            if i + j < 7:
                day_index = i + j
                name = day_names[day_index]
                mark = "✅ " if day_index in selected else ""
                row.append(InlineKeyboardButton(f"{mark}{name}",
                                               callback_data=f"{CallbackData.SCHEDULE_DAY_SELECT_PREFIX}{day_index}"))
        if row:
            kb_buttons.append(row)

    kb_buttons.append([
        InlineKeyboardButton("✔️ حفظ", callback_data=CallbackData.SCHEDULE_SAVE_DAYS),
        InlineKeyboardButton(get_text(uid, 'back'), callback_data=CallbackData.BACK)
    ])
    return InlineKeyboardMarkup(kb_buttons)


async def get_main_keyboard(user_id: int):
    """الحصول على لوحة المفاتيح الرئيسية للمستخدم"""
    channels = await db_get_channels(user_id)

    active = None
    if channels:
        try:
            active = await db_get_active_channel(user_id)
            if active is not None:
                channel_exists = False
                for ch in channels:
                    if ch[0] == active:
                        channel_exists = True
                        break
                if not channel_exists:
                    active = channels[0][0]
                    await db_set_active_channel(user_id, active)
            else:
                active = channels[0][0]
                await db_set_active_channel(user_id, active)
        except:
            active = channels[0][0] if channels else None

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

    title = get_text(user_id, 'main_title').format(BOT_NAME, user_id, my_groups, sub_text,
                                                   ch_display, cnt, auto_status)

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
            InlineKeyboardButton(f"{get_text(user_id, 'stats_btn')} ({cnt})",
                                callback_data=CallbackData.STATS_PENDING),
            InlineKeyboardButton(get_text(user_id, 'my_stats_btn'), callback_data=CallbackData.STATS_FULL)
        ])

        if active is not None:
            keyboard.append([
                InlineKeyboardButton(get_text(user_id, 'schedule_btn'),
                                    callback_data=f"{CallbackData.SCHEDULE_MENU_PREFIX}{active}"),
                InlineKeyboardButton(get_text(user_id, 'channel_stats'),
                                    callback_data=f"{CallbackData.CHANNEL_STATS}:{active}")
            ])

        keyboard.append([
            InlineKeyboardButton(get_text(user_id, 'my_channels_summary'),
                                callback_data=CallbackData.MY_CHANNEL_STATS),
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
        InlineKeyboardButton(get_text(user_id, 'translation_settings'), callback_data=CallbackData.TRANSLATION_MENU)
    ])

    keyboard.append([
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


# ===================================================================
# ===== 54. خادم الويب الموحد =====
# ===================================================================

async def index_handler(request):
    """معالج الصفحة الرئيسية"""
    html_content = """
    <html>
        <head>
            <title>ريلاكس مانيجر</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {
                    font-family: 'Arial', sans-serif;
                    text-align: center;
                    padding: 50px;
                    direction: rtl;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    min-height: 100vh;
                    margin: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                }
                .container {
                    background: rgba(255,255,255,0.1);
                    padding: 40px;
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                    max-width: 600px;
                    width: 100%;
                }
                h1 { font-size: 2.5em; margin-bottom: 20px; }
                .status { font-size: 1.2em; margin: 20px 0; }
                .links { margin: 30px 0; }
                .links a {
                    color: white;
                    text-decoration: none;
                    background: rgba(255,255,255,0.2);
                    padding: 12px 24px;
                    border-radius: 10px;
                    margin: 10px;
                    display: inline-block;
                    transition: all 0.3s;
                }
                .links a:hover {
                    background: rgba(255,255,255,0.4);
                    transform: scale(1.05);
                }
                .version {
                    margin-top: 30px;
                    opacity: 0.7;
                    font-size: 0.9em;
                }
                .bot-info {
                    background: rgba(255,255,255,0.1);
                    padding: 15px;
                    border-radius: 10px;
                    margin: 20px 0;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🌿 ريلاكس مانيجر</h1>
                <div class="status">
                    <span style="font-size: 3em;">✅</span>
                    <p>البوت يعمل بكفاءة</p>
                </div>
                <div class="bot-info">
                    <p>🤖 البوت: <strong>@Reelaaaxbot</strong></p>
                    <p>👑 المطور: <strong>@RelaxMgr</strong></p>
                </div>
                <div class="links">
                    <a href="/health">📊 التحقق من الصحة</a>
                    <a href="https://t.me/Reelaaaxbot">🤖 البوت على تيليجرام</a>
                </div>
                <div class="version">
                    <p>📌 الإصدار 21.0.0 - النسخة العالمية الكاملة</p>
                    <p style="font-size: 0.8em;">© 2026 ريلاكس مانيجر - جميع الحقوق محفوظة</p>
                </div>
            </div>
        </body>
    </html>
    """
    return web.Response(text=html_content, content_type="text/html", charset="utf-8")


async def health_check_handler(request):
    """معالج التحقق من الصحة"""
    try:
        db_healthy = await check_database_health()
        tg_healthy = await check_telegram_health()
        ram = get_ram_usage()

        checks = {
            'database': db_healthy,
            'telegram_api': tg_healthy,
            'memory': ram,
            'uptime': time_module.time() - getattr(health_check_handler, 'start_time', time_module.time())
        }

        status = 200 if all([checks['database'], checks['telegram_api']]) else 503
        return web.json_response({
            'status': 'healthy' if status == 200 else 'unhealthy',
            'checks': checks,
            'version': '21.0.0',
            'bot_name': BOT_NAME
        }, status=status)
    except Exception as e:
        return web.json_response({
            'status': 'unhealthy',
            'error': str(e)
        }, status=503)


async def setup_unified_web_server(application, port: int):
    """إعداد خادم الويب الموحد"""
    application.web_app.router.add_get('/', index_handler)
    application.web_app.router.add_get('/health', health_check_handler)
    application.web_app.router.add_get('/index.html', index_handler)

    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if hostname:
        application.web_app.router.add_post(f"/{TOKEN}", application.process_update)
        logger.info(f"✅ تم إضافة مسار Webhook على /{TOKEN}")

    runner = web.AppRunner(application.web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"✅ خادم الويب الموحد يعمل على المنفذ {port}")
    return site


# ===================================================================
# ===== 55. نظام إدارة المهام (Task Manager) =====
# ===================================================================

class TaskManager:
    """مدير المهام الخلفية"""
    def __init__(self, max_tasks=50, max_concurrent=10):
        self.tasks = set()
        self._lock = asyncio.Lock()
        self.max_tasks = max_tasks
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def create_task(self, coro: Awaitable) -> asyncio.Task:
        """إنشاء مهمة خلفية جديدة"""
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
        """إلغاء جميع المهام"""
        for task in list(self.tasks):
            if not task.done():
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)


task_manager = TaskManager(max_concurrent=10)


# ===================================================================
# ===== 56. دوال إعادة التشغيل التلقائي =====
# ===================================================================

async def safe_loop(coro, name="background_loop"):
    """حلقة آمنة مع إعادة تشغيل تلقائي"""
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
    """تشغيل polling مع إعادة تشغيل تلقائي"""
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


async def self_ping_loop():
    """حلقة النبض الداخلي"""
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


# ===================================================================
# ===== 57. دوال الخلفية (الحلقات) =====
# ===================================================================

async def auto_publish_loop_improved(bot):
    """حلقة النشر التلقائي المحسنة"""
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
                        await bot.send_message(
                            chat_id=user_id,
                            text=f"♻️ **تم إعادة تدوير المنشورات تلقائياً!**\n\n📡 القناة: {ch_tele_id}\n📝 تم إعادة تعيين {total} منشور للنشر من جديد.",
                            parse_mode="MarkdownV2"
                        )
                    except:
                        pass
                    return
                else:
                    logger.warning(f"⛔ توقف النشر للقناة {ch_tele_id} (auto_recycle معطل للمستخدم {user_id})")
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text=f"⚠️ **توقف النشر التلقائي**\n\n📡 القناة: {ch_tele_id}\n📝 تم نشر جميع المنشورات ({published}/{total}).\n\n♻️ إعادة التدوير التلقائي معطل.\n📌 قم بتفعيله من الإعدادات أو أضف منشورات جديدة.",
                            parse_mode="MarkdownV2"
                        )
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
                            await bot.send_message(
                                chat_id=user_id,
                                text=f"♻️ **تم إعادة تدوير المنشورات تلقائياً!**\n\n📡 القناة: {ch_tele_id}\n📝 تم إعادة تعيين {total} منشور للنشر من جديد.",
                                parse_mode="MarkdownV2"
                            )
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
                    media_handlers = {
                        'photo': bot.send_photo,
                        'video': bot.send_video,
                        'document': bot.send_document,
                        'audio': bot.send_audio,
                        'voice': bot.send_voice,
                        'animation': bot.send_animation
                    }

                    if post['media_type'] in media_handlers and post['media_file_id']:
                        await media_handlers[post['media_type']](ch_tele_id, post['media_file_id'],
                                                                 caption=final_text if final_text else None)
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


async def run_scheduled_posts_loop_improved(bot):
    """حلقة تشغيل المنشورات المجدولة"""
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
    """حلقة إرسال التذكيرات"""
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
    """تنظيف الجلسات المنتهية"""
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
    """نشر الإحصائيات بشكل دوري"""
    while True:
        await asyncio.sleep(60)
        try:
            total, banned, posts, groups, channels = await db_stats()
            logger.info(f"📊 إحصائيات: مستخدمين={total}, محظورين={banned}, منشورات={posts}, مجموعات={groups}, قنوات={channels}")
        except:
            pass


async def auto_close_contests_loop(bot):
    """إغلاق المسابقات المنتهية تلقائياً"""
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
                            await bot.send_message(
                                winner_id,
                                f"🏆 **تهانينا!**\nلقد فزت في مسابقة **{contest['title']}**!\n🎁 جائزتك: {contest['prize']}"
                            )
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
    """مراقبة الذاكرة وتنظيفها"""
    while True:
        try:
            ram = get_ram_usage()
            if ram['percent'] > 80:
                await memory_optimizer()
            await asyncio.sleep(60)
        except:
            await asyncio.sleep(60)


async def notify_group_admins(bot, chat_id: int, requester_id: int, chat_name: str):
    """إشعار مشرفي المجموعة بطلب التفعيل"""
    try:
        admins = await bot.get_chat_administrators(chat_id)
        if not admins:
            try:
                await bot.send_message(
                    chat_id,
                    f"📢 **طلب تفعيل البوت!**\n\n👤 المستخدم: {requester_id}\n📌 المجموعة: {chat_name}\n\nلتفعيل البوت، استخدم:\n`/syncgroup`"
                )
            except:
                pass
            return

        for admin in admins:
            if admin.user.id != requester_id:
                try:
                    await bot.send_message(
                        admin.user.id,
                        f"📢 **طلب تفعيل البوت!**\n\n👤 المستخدم: {requester_id}\n📌 المجموعة: {chat_name}\n🆔 المعرف: `{chat_id}`\n\nلتفعيل البوت، استخدم:\n`/syncgroup` في المجموعة."
                    )
                    await asyncio.sleep(0.5)
                except:
                    pass
    except Exception as e:
        logger.error(f"فشل إشعار المشرفين: {e}")


# ===================================================================
# ===== 58. معالج الأخطاء العالمي =====
# ===================================================================

async def global_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء العالمي"""
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
                    await safe_send_markdown(
                        context.bot,
                        PRIMARY_OWNER_ID,
                        f"⚠️ **البوت محظور أو ليس لديه صلاحيات في:**\n{update.effective_chat.title}\nID: `{update.effective_chat.id}`"
                    )
                except:
                    pass
            return

        if isinstance(error, TimedOut):
            logger.warning(f"⏱️ انتهت المهلة: {error}")
            return

        if update and update.effective_user and context and context.bot:
            if not await is_user_bot(context.bot, update.effective_user.id):
                await safe_send_markdown(
                    context.bot,
                    update.effective_user.id,
                    f"❌ حدث خطأ:\n`{str(error)[:300]}`\n(الرمز: `{error_id}`)"
                )

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


# ===================================================================
# ===== 59. تهيئة قاعدة البيانات =====
# ===================================================================

async def init_db_improved():
    """تهيئة قاعدة البيانات مع جميع الجداول"""
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

        # ===== جدول المستخدمين =====
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

        # ===== جدول تخزين المستخدمين المؤقت =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users_cache (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_updated TEXT
            )
        """)

        # ===== جدول قنوات المستخدم =====
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

        # ===== جدول المنشورات =====
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

        # ===== جدول الجدولة =====
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

        # ===== جدول وقت النشر الأخير =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS last_publish (
                channel_db_id INTEGER PRIMARY KEY,
                last_publish_time TEXT,
                FOREIGN KEY(channel_db_id) REFERENCES user_channels(id)
            )
        """)

        # ===== جدول المنشورات المجدولة =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                text TEXT,
                publish_time TEXT,
                fail_count INTEGER DEFAULT 0
            )
        """)

        # ===== جدول المجموعات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_groups (
                chat_id INTEGER PRIMARY KEY,
                chat_name TEXT,
                username TEXT,
                added_by INTEGER,
                added_at TEXT,
                banned INTEGER DEFAULT 0
            )
        """)

        # ===== جدول مشرفي المجموعات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_admins (
                chat_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY(chat_id, user_id)
            )
        """)

        # ===== جدول المالكين المخفيين =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_owner_groups (
                chat_id INTEGER,
                owner_id INTEGER,
                is_hidden INTEGER DEFAULT 1,
                PRIMARY KEY(chat_id, owner_id)
            )
        """)

        # ===== جدول المشرفين المخفيين =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_admins (
                chat_id INTEGER,
                admin_id INTEGER,
                added_by INTEGER,
                added_at TEXT,
                PRIMARY KEY(chat_id, admin_id)
            )
        """)

        # ===== جدول روابط المستخدمين والمجموعات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_groups_link (
                user_id INTEGER,
                chat_id INTEGER,
                PRIMARY KEY(user_id, chat_id)
            )
        """)

        # ===== جدول إعدادات الأمان =====
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
                delete_penalty TEXT DEFAULT 'none',
                delete_penalty_duration INTEGER DEFAULT 0
            )
        """)

        # ===== جدول قفل المجموعات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_locks (
                chat_id INTEGER PRIMARY KEY,
                locked INTEGER DEFAULT 0,
                locked_at TEXT,
                locked_by INTEGER
            )
        """)

        # ===== جدول رسائل المستخدمين (للحالة البطيئة) =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_messages (
                user_id INTEGER,
                chat_id INTEGER,
                message_time TEXT,
                PRIMARY KEY(user_id, chat_id)
            )
        """)

        # ===== جدول الكلمات المحظورة =====
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

        # ===== جدول الردود الآلية =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_replies (
                keyword TEXT PRIMARY KEY,
                reply TEXT
            )
        """)

        # ===== جدول إعدادات الردود التلقائية =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_reply_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                only_admins INTEGER DEFAULT 0,
                ignore_bots INTEGER DEFAULT 1,
                updated_at TEXT
            )
        """)

        # ===== جدول تذاكر الدعم =====
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

        # ===== جدول مشرفي البوت =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY
            )
        """)

        # ===== جدول قنوات البوت =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_channels (
                channel_id INTEGER PRIMARY KEY,
                channel_name TEXT,
                added_by INTEGER,
                added_at TEXT,
                banned INTEGER DEFAULT 0
            )
        """)

        # ===== جدول الإعدادات العامة =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # ===== جدول إعدادات الإحالات =====
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

        # ===== جدول الإحالات =====
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

        # ===== جدول مكافآت الإحالات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_rewards (
                user_id INTEGER PRIMARY KEY,
                referral_count INTEGER DEFAULT 0,
                total_reward_days INTEGER DEFAULT 0,
                claimed_reward_days INTEGER DEFAULT 0
            )
        """)

        # ===== جدول إعدادات التذكيرات =====
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

        # ===== جدول إعدادات الترجمة =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_translation (
                user_id INTEGER PRIMARY KEY,
                lang TEXT DEFAULT 'off'
            )
        """)

        # ===== جدول مستويات المستخدمين =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_levels (
                user_id INTEGER PRIMARY KEY,
                points INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1
            )
        """)

        # ===== جدول المسابقات =====
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

        # ===== جدول المشاركين في المسابقات =====
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

        # ===== جدول الفائزين في المسابقات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contest_winners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER,
                winner_id INTEGER,
                announced_at TEXT
            )
        """)

        # ===== جدول سجل الإجراءات الرقابية =====
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

        # ===== جدول تحذيرات المستخدمين =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_warnings (
                user_id INTEGER,
                chat_id INTEGER,
                warnings INTEGER DEFAULT 0,
                PRIMARY KEY(user_id, chat_id)
            )
        """)

        # ===== جدول المستخدم المسموح له بـ /sendcode =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS allowed_sendcode_user (
                id INTEGER PRIMARY KEY,
                user_id INTEGER
            )
        """)

        # ===== جدول جلسات الويب =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS web_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                user_id INTEGER,
                created_at REAL,
                expires REAL
            )
        """)

        # ===== جداول الميزات الجديدة =====

        # ===== جدول الكوبونات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS coupons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                discount_days INTEGER,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                created_by INTEGER,
                created_at TEXT,
                expires_at TEXT
            )
        """)

        # ===== جدول استخدام الكوبونات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS coupon_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coupon_id INTEGER,
                user_id INTEGER,
                used_at TEXT
            )
        """)

        # ===== جدول الاستطلاعات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                question TEXT,
                options TEXT,
                is_anonymous INTEGER DEFAULT 1,
                created_by INTEGER,
                created_at TEXT,
                expires_at TEXT,
                status TEXT DEFAULT 'active'
            )
        """)

        # ===== جدول تصويتات الاستطلاعات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER,
                user_id INTEGER,
                option_index INTEGER,
                voted_at TEXT,
                UNIQUE(poll_id, user_id)
            )
        """)

        # ===== جدول الإعلانات المدفوعة =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER,
                title TEXT,
                text TEXT,
                duration_days INTEGER,
                price INTEGER,
                created_by INTEGER,
                created_at TEXT,
                status TEXT DEFAULT 'active',
                views INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0
            )
        """)

        # ===== جدول الأسئلة الشائعة =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS faq (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT,
                answer TEXT,
                category TEXT DEFAULT 'general',
                created_by INTEGER,
                created_at TEXT
            )
        """)

        # ===== جدول قوانين المجموعات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_rules (
                chat_id INTEGER PRIMARY KEY,
                rules_text TEXT,
                updated_by INTEGER,
                updated_at TEXT
            )
        """)

        # ===== جدول الإعلانات العامة =====
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

        # ===== جدول أسئلة الاختبارات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT,
                options TEXT,
                correct_answer INTEGER,
                category TEXT DEFAULT 'general',
                created_by INTEGER,
                created_at TEXT
            )
        """)

        # ===== جدول نتائج الاختبارات =====
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                quiz_id INTEGER,
                score INTEGER,
                total_questions INTEGER,
                completed_at TEXT
            )
        """)

        await conn.commit()
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")


# ===================================================================
# ===== 60. إغلاق الموارد =====
# ===================================================================

async def cleanup_resources():
    """تنظيف الموارد قبل الإغلاق"""
    logger.info("🧹 جاري تنظيف الموارد...")
    await db_pool.close()
    logger.info("✅ تم تنظيف الموارد بنجاح")

# ===================================================================
# ===== جميع الدوال الأساسية المفقودة =====
# ===================================================================

# ===================================================================
# 1. معالج أمر /start
# ===================================================================

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /start - القائمة الرئيسية"""
    user_id = update.effective_user.id
    username = update.effective_user.username or ""
    first_name = update.effective_user.first_name or ""

    await db_register_user(user_id)
    await db_update_user_cache(user_id, username, first_name)
    await set_user_language(user_id, 'ar')

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
                await achievement_system(referrer_id, 'first_referral')

    if not await ensure_force_subscribe(update, context):
        return

    kb, title, active = await get_main_keyboard(user_id)
    await safe_send_markdown(context.bot, user_id, title, reply_markup=kb)


# ===================================================================
# 2. معالج أمر /syncgroup
# ===================================================================

async def syncgroup_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /syncgroup - تفعيل المجموعة"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return

    chat_id = update.effective_chat.id
    chat_name = update.effective_chat.title or "بدون اسم"
    user_id = update.effective_user.id
    chat_username = update.effective_chat.username

    await db_register_group(chat_id, chat_name, user_id, chat_username)

    bot_perms = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bot_perms['can_act']:
        await safe_send_markdown(context.bot, chat_id, f"⚠️ البوت ليس لديه الصلاحيات الكافية.\n{bot_perms['reason']}")
        return

    is_admin = await is_currently_admin_in_group(context.bot, chat_id, user_id)

    if is_admin:
        await db_register_hidden_owner_group(chat_id, user_id)
        await db_sync_group_admins(chat_id, context.bot, user_id)
        invalidate_auth_cache(chat_id, user_id)
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'group_registered'))
        await notify_group_admins(context.bot, chat_id, user_id, chat_name)
    else:
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'activation_requested'))
        await notify_group_admins(context.bot, chat_id, user_id, chat_name)

    try:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'promo_message').format(BOT_USERNAME))
    except:
        pass


# ===================================================================
# 3. معالج أمر /language
# ===================================================================

async def language_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /language - تغيير اللغة"""
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


# ===================================================================
# 4. معالج أمر /register_hidden_owner
# ===================================================================

async def register_hidden_owner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /register_hidden_owner - تسجيل مالك مخفي"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    bot_perms = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bot_perms['can_act']:
        await safe_send_markdown(context.bot, chat_id, f"⚠️ البوت ليس لديه الصلاحيات الكافية.\n{bot_perms['reason']}")
        return

    if not await is_currently_admin_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, chat_id, "❌ يجب أن تكون مشرفاً في المجموعة لتسجيل نفسك كمالك مخفي.")
        return

    if await db_is_hidden_owner(chat_id, user_id):
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'hidden_owner_already'))
        return

    await db_register_hidden_owner_group(chat_id, user_id)
    await db_sync_group_admins(chat_id, context.bot, user_id)
    invalidate_auth_cache(chat_id, user_id)
    await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'hidden_owner_registered'))


# ===================================================================
# 5. معالج أمر /add_hidden_admin
# ===================================================================

async def add_hidden_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /add_hidden_admin - إضافة مشرف مخفي"""
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
        await safe_send_markdown(context.bot, chat_id, "📝 **الاستخدام:**\n`/add_hidden_admin معرف_المستخدم`\n\nمثال: `/add_hidden_admin 123456789`")
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await safe_send_markdown(context.bot, chat_id, "❌ معرف غير صحيح!")
        return

    if not await is_currently_admin_in_group(context.bot, chat_id, target_id):
        await safe_send_markdown(context.bot, chat_id, "❌ المستخدم ليس مشرفاً في المجموعة.")
        return

    if await db_add_hidden_admin(chat_id, target_id, user_id):
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'hidden_admin_added').format(target_id))
        invalidate_auth_cache(chat_id, target_id)
    else:
        await safe_send_markdown(context.bot, chat_id, "❌ فشل إضافة المشرف المخفي.")


# ===================================================================
# 6. معالج أمر /remove_hidden_admin
# ===================================================================

async def remove_hidden_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /remove_hidden_admin - إزالة مشرف مخفي"""
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
        await safe_send_markdown(context.bot, chat_id, "📝 **الاستخدام:**\n`/remove_hidden_admin معرف_المستخدم`\n\nمثال: `/remove_hidden_admin 123456789`")
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await safe_send_markdown(context.bot, chat_id, "❌ معرف غير صحيح!")
        return

    if await db_remove_hidden_admin(chat_id, target_id):
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'hidden_admin_removed').format(target_id))
        invalidate_auth_cache(chat_id, target_id)
    else:
        await safe_send_markdown(context.bot, chat_id, "❌ فشل إزالة المشرف المخفي.")


# ===================================================================
# 7. معالج أمر /list_hidden_admins
# ===================================================================

async def list_hidden_admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /list_hidden_admins - عرض المشرفين المخفيين"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'admin_only'))
        return

    admins = await db_get_hidden_admins(chat_id)
    if not admins:
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'no_hidden_admins'))
        return

    text = get_text(user_id, 'hidden_admin_list').format("")
    for admin in admins:
        text += f"• `{admin['admin_id']}` (أضيف بواسطة {admin['added_by']})\n"

    await safe_send_markdown(context.bot, chat_id, text)


# ===================================================================
# 8. معالج أمر /trial
# ===================================================================

async def trial_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /trial - تفعيل التجربة المجانية"""
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


# ===================================================================
# 9. معالج أمر /subscribe
# ===================================================================

async def subscribe_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /subscribe - عرض خيارات الاشتراك"""
    user_id = update.effective_user.id

    if await db_has_active_subscription(user_id):
        days = await db_get_subscription_days_left(user_id)
        await safe_send_markdown(context.bot, user_id, f"✅ اشتراكك مفعل، متبقي {days} يوم\nشكراً لدعمك ❤️")
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ 1 يوم - 5 نجوم", callback_data=CallbackData.BUY_SUBSCRIPTION_1), InlineKeyboardButton("⭐ 2 يوم - 9 نجوم", callback_data=CallbackData.BUY_SUBSCRIPTION_2)],
        [InlineKeyboardButton("⭐ شهر (30 يوم) - 50 نجمة", callback_data=CallbackData.BUY_SUBSCRIPTION_30), InlineKeyboardButton("⭐ 3 أشهر (90 يوم) - 120 نجمة", callback_data=CallbackData.BUY_SUBSCRIPTION_90)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'subscribe'), reply_markup=kb)


# ===================================================================
# 10. معالج أمر /help
# ===================================================================

async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /help - عرض المساعدة"""
    user_id = update.effective_user.id
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'help'))


# ===================================================================
# 11. معالج أمر /support
# ===================================================================

async def support_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /support - مركز الدعم"""
    user_id = update.effective_user.id
    context.user_data['support_mode'] = True

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 كتابة تذكرة", callback_data=CallbackData.SUPPORT_TICKET)],
        [InlineKeyboardButton("❓ المساعدة", callback_data=CallbackData.SUPPORT_HELP)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'support_welcome'), reply_markup=keyboard)


# ===================================================================
# 12. معالج أمر /support_reply
# ===================================================================

async def support_reply_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /support_reply - الرد على تذكرة"""
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return

    args = context.args
    if len(args) < 2:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/support_reply معرف_التذكرة الرد`\n\nمثال: `/support_reply 5 تم حل مشكلتك`")
        return

    try:
        ticket_id = int(args[0])
        reply_text = " ".join(args[1:])
    except ValueError:
        await safe_send_markdown(context.bot, user_id, "❌ معرف التذكرة غير صحيح!")
        return

    async def _get_ticket(conn):
        cur = await conn.execute("SELECT user_id FROM support_tickets WHERE id=? AND status='pending'", (ticket_id,))
        return await cur.fetchone()

    ticket = await execute_db(_get_ticket)
    if not ticket:
        await safe_send_markdown(context.bot, user_id, "❌ التذكرة غير موجودة أو تم الرد عليها مسبقاً.")
        return

    target_user = ticket[0]
    await db_mark_ticket_replied(ticket_id)

    try:
        await context.bot.send_message(chat_id=target_user, text=f"📩 **رد على تذكرتك #{ticket_id}**\n\n{reply_text}")
        await safe_send_markdown(context.bot, user_id, f"✅ تم إرسال الرد إلى المستخدم `{target_user}`")
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ فشل إرسال الرد: {str(e)[:100]}")


# ===================================================================
# 13. معالج أمر /rank
# ===================================================================

async def rank_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /rank - عرض رتبة المستخدم"""
    user_id = update.effective_user.id
    data = await get_rank(user_id)
    await safe_send_markdown(context.bot, user_id, f"📊 **رتبتك**\n━━━━━━━━━━━━━━━━━━━━━━\n🎖️ المستوى: {data['level']}\n⭐ النقاط: {data['points']}\n🎯 النقاط المطلوبة للمستوى التالي: {LEVEL_REQUIREMENTS.get(data['level'] + 1, 'ماكس')}")


# ===================================================================
# 14. معالج أمر /top
# ===================================================================

async def top_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /top - عرض أفضل 10 مستخدمين"""
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


# ===================================================================
# 15. معالج أمر /stats
# ===================================================================

async def stats_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /stats - عرض إحصائيات القناة"""
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


# ===================================================================
# 16. معالج أمر /sendcode
# ===================================================================

async def sendcode_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /sendcode - إرسال كود البوت"""
    user_id = update.effective_user.id

    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        allowed_user = await db_get_allowed_sendcode_user()
        if user_id != allowed_user:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح لك باستخدام هذا الأمر.")
            return

    code = f"/start {secrets.token_urlsafe(8)}"
    await safe_send_markdown(context.bot, user_id, f"📨 **كود البوت:**\n`{code}`\n\nاستخدم هذا الكود لإضافة البوت.")


# ===================================================================
# 17. معالج أمر /lock
# ===================================================================

async def lock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /lock - قفل المجموعة"""
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


# ===================================================================
# 18. معالج أمر /unlock
# ===================================================================

async def unlock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /unlock - فتح المجموعة"""
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


# ===================================================================
# 19. معالج أمر /schedule
# ===================================================================

async def schedule_post_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /schedule - جدولة منشور"""
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_SCHEDULE_POST
    await safe_send_markdown(context.bot, user_id, "📝 **جدولة منشور**\n\nأرسل المنشور بهذه الصيغة:\n`YYYY-MM-DD HH:MM نص المنشور`\n\nمثال: `2024-12-25 14:30 مرحباً بالجميع!`\n\n🕐 الوقت بتوقيت مكة المكرمة")


# ===================================================================
# 20. معالج أمر /panel
# ===================================================================

async def panel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /panel - لوحة التحكم"""
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return

    await safe_send_markdown(context.bot, user_id, "👑 **لوحة التحكم**", reply_markup=get_admin_keyboard(user_id))


# ===================================================================
# 21. معالج أمر /set_log_channel
# ===================================================================

async def set_log_channel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /set_log_channel - تعيين قناة التقارير"""
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return

    args = context.args
    if not args:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/set_log_channel معرف_القناة`")
        return

    try:
        channel_id = args[0]
        chat = await context.bot.get_chat(channel_id)
        if chat.type != 'channel':
            await safe_send_markdown(context.bot, user_id, "❌ المعرف ليس لقناة!")
            return

        await db_set_log_channel_id(str(chat.id))
        await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين قناة التقارير: {chat.title}")
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ فشل تعيين القناة: {str(e)[:100]}")


# ===================================================================
# 22. معالج أمر /set_rules
# ===================================================================

async def set_rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /set_rules - تعيين قوانين المجموعة"""
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
        await safe_send_markdown(context.bot, chat_id, "📝 **الاستخدام:**\n`/set_rules نص القوانين`\n\nيمكنك استخدام عدة أسطر.")
        return

    rules_text = " ".join(args)

    async def _set_rules(conn):
        await conn.execute("INSERT OR REPLACE INTO group_rules (chat_id, rules_text, updated_by, updated_at) VALUES (?, ?, ?, ?)", (chat_id, rules_text, user_id, utc_now_iso()))
        await conn.commit()

    await execute_db(_set_rules)
    await safe_send_markdown(context.bot, chat_id, "✅ تم تعيين قوانين المجموعة بنجاح!")


# ===================================================================
# 23. معالج أمر /rules
# ===================================================================

async def rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /rules - عرض قوانين المجموعة"""
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
# 24. معالج أمر /developer
# ===================================================================

async def developer_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /developer - عرض معلومات المطور"""
    user_id = update.effective_user.id
    text = f"""👨‍💻 **المطور**
━━━━━━━━━━━━━━━━━━━━━━
📌 الاسم: RelaxMgr
📌 البوت: @{BOT_USERNAME}
📌 الإصدار: 21.0.0

📞 للتواصل: @RelaxMgr
📢 قناة التحديثات: @Reelaaaxbot

💎 **ميزات البوت:**
• إدارة القنوات والمجموعات
• جدولة النشر التلقائي
• نظام أمان متقدم
• مسابقات واستطلاعات
• كوبونات خصم
• وأكثر...
"""
    await safe_send_markdown(context.bot, user_id, text)


# ===================================================================
# 25. معالج أمر /updates
# ===================================================================

async def updates_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /updates - عرض آخر التحديثات"""
    user_id = update.effective_user.id
    updates_channel = await db_get_updates_channel()
    if updates_channel:
        text = f"📢 **آخر التحديثات**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 تابع قناة التحديثات:\n👉 @{updates_channel}"
    else:
        text = "📢 **آخر التحديثات**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 لا توجد قناة تحديثات حالياً."
    await safe_send_markdown(context.bot, user_id, text)


# ===================================================================
# 26. معالج أمر /coupon
# ===================================================================

async def coupon_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /coupon - استخدام كوبون خصم"""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/coupon كود_الكوبون`\n\nمثال: `/coupon SUMMER2024`")
        return

    coupon_code = args[0].upper()

    async def _validate_coupon(conn):
        cur = await conn.execute("SELECT id, discount_days, max_uses, used_count, expires_at FROM coupons WHERE code=?", (coupon_code,))
        return await cur.fetchone()

    coupon = await execute_db(_validate_coupon)

    if not coupon:
        await safe_send_markdown(context.bot, user_id, "❌ كوبون غير صحيح!")
        return

    coupon_id, discount_days, max_uses, used_count, expires_at = coupon

    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
            if expiry < utc_now():
                await safe_send_markdown(context.bot, user_id, "❌ هذا الكوبون منتهي الصلاحية!")
                return
        except:
            pass

    if max_uses > 0 and used_count >= max_uses:
        await safe_send_markdown(context.bot, user_id, "❌ هذا الكوبون استُنفد!")
        return

    async def _check_user_used(conn):
        cur = await conn.execute("SELECT 1 FROM coupon_usage WHERE coupon_id=? AND user_id=?", (coupon_id, user_id))
        return await cur.fetchone()

    if await execute_db(_check_user_used):
        await safe_send_markdown(context.bot, user_id, "❌ لقد استخدمت هذا الكوبون مسبقاً!")
        return

    await db_activate_subscription(user_id, discount_days)

    async def _mark_used(conn):
        await conn.execute("UPDATE coupons SET used_count = used_count + 1 WHERE id=?", (coupon_id,))
        await conn.execute("INSERT INTO coupon_usage (coupon_id, user_id, used_at) VALUES (?, ?, ?)", (coupon_id, user_id, utc_now_iso()))
        await conn.commit()

    await execute_db(_mark_used)
    await safe_send_markdown(context.bot, user_id, f"✅ تم تطبيق الكوبون بنجاح!\n🎁 حصلت على {discount_days} يوم اشتراك إضافي!")


# ===================================================================
# 27. معالج أمر /poll
# ===================================================================

async def poll_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /poll - إنشاء استطلاع رأي"""
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return

    context.user_data['state'] = UserState.WAITING_POLL_QUESTION
    await safe_send_markdown(context.bot, user_id, "📊 **إنشاء استطلاع رأي**\n\nأرسل سؤال الاستطلاع:")


# ===================================================================
# 28. معالج أمر /vote
# ===================================================================

async def vote_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /vote - التصويت في استطلاع"""
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/vote معرف_الاستطلاع رقم_الخيار`\n\nمثال: `/vote 5 2`")
        return

    try:
        poll_id = int(args[0])
        option_index = int(args[1]) - 1
    except ValueError:
        await safe_send_markdown(context.bot, user_id, "❌ أرقام غير صحيحة!")
        return

    async def _get_poll(conn):
        cur = await conn.execute("SELECT question, options, status, expires_at FROM polls WHERE id=?", (poll_id,))
        return await cur.fetchone()

    poll = await execute_db(_get_poll)
    if not poll:
        await safe_send_markdown(context.bot, user_id, "❌ الاستطلاع غير موجود!")
        return

    question, options_json, status, expires_at = poll

    if status != 'active':
        await safe_send_markdown(context.bot, user_id, "❌ هذا الاستطلاع غير نشط!")
        return

    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
            if expiry < utc_now():
                await safe_send_markdown(context.bot, user_id, "❌ هذا الاستطلاع انتهى!")
                return
        except:
            pass

    options = json.loads(options_json)
    if option_index < 0 or option_index >= len(options):
        await safe_send_markdown(context.bot, user_id, "❌ خيار غير صحيح!")
        return

    async def _vote(conn):
        try:
            await conn.execute("INSERT INTO poll_votes (poll_id, user_id, option_index, voted_at) VALUES (?, ?, ?, ?)", (poll_id, user_id, option_index, utc_now_iso()))
            await conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    if await execute_db(_vote):
        await safe_send_markdown(context.bot, user_id, f"✅ تم تسجيل تصويتك في الاستطلاع **{question}**")
    else:
        await safe_send_markdown(context.bot, user_id, "❌ لقد صوّت مسبقاً في هذا الاستطلاع!")


# ===================================================================
# 29. معالج أمر /faq
# ===================================================================

async def faq_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /faq - عرض الأسئلة الشائعة"""
    user_id = update.effective_user.id

    async def _get_faq(conn):
        cur = await conn.execute("SELECT id, question, answer, category FROM faq ORDER BY category, id LIMIT 20")
        return await cur.fetchall()

    faqs = await execute_db(_get_faq)

    if not faqs:
        await safe_send_markdown(context.bot, user_id, "📭 لا توجد أسئلة شائعة حالياً.")
        return

    text = "❓ **الأسئلة الشائعة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    current_category = ""
    for faq_id, question, answer, category in faqs:
        if category != current_category:
            current_category = category
            text += f"\n📌 **{category.upper()}**\n"
        text += f"\n**س: {question}**\nج: {answer}\n"

    await safe_send_markdown(context.bot, user_id, text)


# ===================================================================
# 30. معالج أمر /announce
# ===================================================================

async def announce_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /announce - إعلان جديد"""
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return

    args = context.args
    if not args:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/announce عنوان الإعلان | نص الإعلان`")
        return

    try:
        parts = " ".join(args).split("|")
        title = parts[0].strip()
        text = parts[1].strip() if len(parts) > 1 else ""
    except:
        await safe_send_markdown(context.bot, user_id, "❌ صيغة غير صحيحة!")
        return

    async def _save_announce(conn):
        await conn.execute("INSERT INTO announcements (title, text, created_by, created_at, status) VALUES (?, ?, ?, ?, 'active')", (title, text, user_id, utc_now_iso()))
        await conn.commit()

    await execute_db(_save_announce)

    users = await db_get_all_users()
    sent = 0
    failed = 0

    for user in users:
        try:
            await context.bot.send_message(chat_id=user[0], text=f"📢 **{title}**\n\n{text}")
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.1)

    await safe_send_markdown(context.bot, user_id, f"✅ تم إرسال الإعلان!\n📤 تم الإرسال: {sent}\n❌ فشل: {failed}")


# ===================================================================
# 31. معالج أوامر الرقابة
# ===================================================================

async def handle_moderation_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أوامر الرقابة (ban, mute, kick, warn, restrict, unban)"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    command = update.message.text.split()[0][1:]
    args = context.args

    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'admin_only'))
        return

    if not args:
        await safe_send_markdown(context.bot, chat_id, f"📝 **الاستخدام:**\n`/{command} معرف_المستخدم [السبب]`")
        return

    try:
        target_id = int(args[0])
        reason = " ".join(args[1:]) if len(args) > 1 else ""
    except ValueError:
        await safe_send_markdown(context.bot, chat_id, "❌ معرف غير صحيح!")
        return

    action_map = {'ban': 'ban', 'mute': 'mute', 'warn': 'warn', 'kick': 'kick', 'restrict': 'restrict', 'unban': 'unban'}
    action = action_map.get(command)

    if not action:
        await safe_send_markdown(context.bot, chat_id, f"❌ أمر غير معروف: /{command}")
        return

    if action == 'pin':
        if update.message.reply_to_message:
            success, msg = await execute_pin(context.bot, chat_id, update.message.reply_to_message.message_id)
            await safe_send_markdown(context.bot, chat_id, msg)
        else:
            await safe_send_markdown(context.bot, chat_id, "📌 رد على الرسالة التي تريد تثبيتها مع الأمر /pin")
        return

    success, msg = await execute_moderation_action(context.bot, chat_id, target_id, action, reason=reason, moderator_id=user_id)
    await safe_send_markdown(context.bot, chat_id, msg)


# ===================================================================
# 32. معالج أمر /contests
# ===================================================================

async def contests_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /contests - عرض المسابقات النشطة"""
    user_id = update.effective_user.id
    contests = await db_get_active_contests_with_participants(limit=10)

    if not contests:
        await safe_send_markdown(context.bot, user_id, "📭 لا توجد مسابقات نشطة حالياً.")
        return

    text = "🏆 **المسابقات النشطة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for contest_id, title, description, prize, end_date, participants, contest_type in contests:
        try:
            end_dt = datetime.fromisoformat(end_date)
            days_left = (end_dt - utc_now()).days
            time_left = f"{days_left} يوم" if days_left > 0 else "تنتهي اليوم"
        except:
            time_left = "?"

        text += f"\n📌 **{title}**\n📝 {description[:100]}...\n🎁 الجائزة: {prize}\n👥 المشاركون: {participants}\n⏳ متبقي: {time_left}\n🆔 المعرف: `{contest_id}`\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 المشاركة", callback_data=f"{CallbackData.CONTEST_JOIN_PREFIX}0")],
        [InlineKeyboardButton("🏆 الفائزون", callback_data=CallbackData.CONTEST_WINNERS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.CONTESTS_BACK)]
    ])
    await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)


# ===================================================================
# 33. معالج أمر /create_contest
# ===================================================================

async def create_contest_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /create_contest - إنشاء مسابقة جديدة"""
    user_id = update.effective_user.id

    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return

    context.user_data['state'] = UserState.WAITING_CONTEST_TITLE
    await safe_send_markdown(context.bot, user_id, "🏆 **إنشاء مسابقة جديدة**\n\n📝 أرسل عنوان المسابقة:")


# ===================================================================
# 34. معالج أمر /declare_winner
# ===================================================================

async def declare_winner_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /declare_winner - إعلان فائز في مسابقة"""
    user_id = update.effective_user.id

    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return

    args = context.args
    if not args:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/declare_winner معرف_المسابقة`")
        return

    try:
        contest_id = int(args[0])
    except ValueError:
        await safe_send_markdown(context.bot, user_id, "❌ معرف غير صحيح!")
        return

    contest = await db_get_contest(contest_id)
    if not contest:
        await safe_send_markdown(context.bot, user_id, "❌ المسابقة غير موجودة!")
        return

    if contest['status'] == 'finished':
        await safe_send_markdown(context.bot, user_id, "❌ هذه المسابقة منتهية!")
        return

    winner_id = await db_get_random_participant(contest_id)
    if not winner_id:
        await safe_send_markdown(context.bot, user_id, "❌ لا يوجد مشاركين في هذه المسابقة!")
        return

    await db_set_contest_winner(contest_id, winner_id)

    try:
        await context.bot.send_message(chat_id=winner_id, text=f"🏆 **تهانينا!**\nلقد فزت في مسابقة **{contest['title']}**!\n🎁 جائزتك: {contest['prize']}")
    except:
        pass

    await safe_send_markdown(context.bot, user_id, f"✅ تم إعلان المستخدم `{winner_id}` فائزاً في المسابقة!")


# ===================================================================
# ===== نهاية جميع الدوال الأساسية =====
# ===================================================================
# ===================================================================
# ===== كولباك الأمان المفقودة =====
# ===================================================================

async def security_select_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كولباك اختيار مجموعة لإعدادات الأمان"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    groups = await db_get_user_groups(user_id)
    if not groups:
        await query.edit_message_text("📭 لا توجد مجموعات مسجلة. أضف البوت إلى مجموعة أولاً.")
        return

    keyboard = []
    for chat_id, chat_name, username, banned in groups:
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            continue
        display_name = chat_name[:28] + "..." if len(chat_name) > 31 else chat_name
        status_icon = "⛔" if banned else "✅"
        keyboard.append([InlineKeyboardButton(f"{status_icon} {display_name}", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")])

    if not keyboard:
        await query.edit_message_text("🔒 لا تملك صلاحية على أي مجموعة.")
        return

    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await query.edit_message_text("🔐 **اختر مجموعة لإعدادات الأمان:**", reply_markup=InlineKeyboardMarkup(keyboard))


# ===================================================================
# ===== كولباك المجموعات =====
# ===================================================================

async def group_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كولباك إعدادات المجموعة"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass

    user_id = update.effective_user.id
    chat_id = None

    try:
        if query and query.data:
            try:
                chat_id = int(query.data.split(":")[-1])
            except (ValueError, IndexError) as e:
                error_id = advanced_logger.log_error("فشل استخراج chat_id من الكولباك", e, {"data": query.data})
                await query.edit_message_text(f"❌ بيانات الكولباك غير صالحة (الرمز: `{error_id}`)")
                return
        else:
            chat_id = context.user_data.get('group_chat_id')

        if not chat_id:
            if query:
                await query.edit_message_text("❌ لم يتم تحديد المجموعة")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            return

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            if query:
                await query.edit_message_text(get_text(user_id, 'admin_only'))
            else:
                await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
            return

        try:
            settings = await db_get_security_settings(chat_id, force_refresh=True)
        except Exception as e:
            error_id = advanced_logger.log_error("فشل جلب إعدادات الأمان", e, {"chat_id": chat_id})
            if query:
                await query.edit_message_text(f"❌ فشل جلب إعدادات الأمان (الرمز: `{error_id}`)")
            else:
                await safe_send_markdown(context.bot, user_id, f"❌ فشل جلب إعدادات الأمان (الرمز: `{error_id}`)")
            return

        await _update_security_panel(query, chat_id, user_id)
    except Exception as e:
        error_id = advanced_logger.log_error("خطأ غير متوقع في group_settings_callback", e, {"chat_id": chat_id, "user_id": user_id})
        try:
            if query:
                await query.edit_message_text(f"❌ حدث خطأ:\n`{str(e)[:300]}`\n(الرمز: `{error_id}`)")
            else:
                await safe_send_markdown(context.bot, user_id, f"❌ حدث خطأ:\n`{str(e)[:300]}`\n(الرمز: `{error_id}`)")
        except Exception as e2:
            logger.error(f"فشل إرسال رسالة الخطأ للمستخدم: {e2}")


# ===================================================================
# ===== تحديث لوحة الأمان =====
# ===================================================================

async def _update_security_panel(query, chat_id: int, user_id: int):
    """تحديث لوحة إعدادات الأمان"""
    settings = await db_get_security_settings(chat_id)

    status_text = lambda v: "✅ مفعل" if v else "❌ معطل"

    text = f"""🔐 **إعدادات الأمان للمجموعة**
━━━━━━━━━━━━━━━━━━━━━━
🔗 **حذف الروابط:** {status_text(settings['links'])}
@ **حذف المعرفات:** {status_text(settings['mentions'])}
⏱️ **الوضع البطيء:** {status_text(settings['slow_mode'])} ({settings['slow_mode_seconds']} ثانية)
🎯 **الترحيب:** {status_text(settings['welcome_enabled'])}
👋 **الوداع:** {status_text(settings['goodbye_enabled'])}
🎬 **حذف الفيديوهات:** {status_text(settings['delete_videos'])}
🎵 **حذف الصوتيات:** {status_text(settings['delete_audio'])}
🎞️ **حذف المتحركات:** {status_text(settings['delete_animation'])}
🛠️ **حذف رسائل الخدمة:** {status_text(settings['delete_service'])}
📄 **حذف الملفات:** {status_text(settings['delete_documents'])}
🖼️ **حذف الملصقات:** {status_text(settings['delete_stickers'])}
⚖️ **عقوبة الحذف:** {settings.get('delete_penalty', 'none')}
━━━━━━━━━━━━━━━━━━━━━━
اختر الإعدادات المطلوبة:"""

    await safe_edit_markdown(query, text, reply_markup=security_keyboard(chat_id))


# ===================================================================
# ===== كولباك تبديل إعدادات الأمان =====
# ===================================================================

async def security_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كولباك تبديل إعدادات الأمان"""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user_id = update.effective_user.id
    data_parts = query.data.split(":")

    if len(data_parts) < 3:
        return

    action = data_parts[1]
    chat_id = int(data_parts[2])

    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return

    settings = await db_get_security_settings(chat_id, force_refresh=True)

    toggles = {
        "links": ("links", "SECURITY_TOGGLE_LINKS"),
        "mentions": ("mentions", "SECURITY_TOGGLE_MENTIONS"),
        "slow_mode": ("slow_mode", "SECURITY_TOGGLE_SLOW_MODE"),
        "welcome_enabled": ("welcome_enabled", "SECURITY_TOGGLE_WELCOME"),
        "goodbye_enabled": ("goodbye_enabled", "SECURITY_TOGGLE_GOODBYE"),
        "delete_videos": ("delete_videos", "SECURITY_TOGGLE_DELETE_VIDEOS"),
        "delete_audio": ("delete_audio", "SECURITY_TOGGLE_DELETE_AUDIO"),
        "delete_animation": ("delete_animation", "SECURITY_TOGGLE_DELETE_ANIMATION"),
        "delete_service": ("delete_service", "SECURITY_TOGGLE_DELETE_SERVICE"),
        "delete_documents": ("delete_documents", "SECURITY_TOGGLE_DELETE_DOCUMENTS"),
        "delete_stickers": ("delete_stickers", "SECURITY_TOGGLE_DELETE_STICKERS"),
        "enable_all": ("enable_all", "SECURITY_ENABLE_ALL"),
        "disable_all": ("disable_all", "SECURITY_DISABLE_ALL")
    }

    if action in toggles:
        setting_key, event_name = toggles[action]
        
        if action == "enable_all":
            # تفعيل جميع الإعدادات
            for key in ['links', 'mentions', 'slow_mode', 'welcome_enabled', 'goodbye_enabled',
                        'delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
                        'delete_documents', 'delete_stickers']:
                settings[key] = True
            await db_set_security_settings(chat_id, **{k: True for k in ['links', 'mentions', 'slow_mode', 'welcome_enabled', 'goodbye_enabled',
                                                                          'delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
                                                                          'delete_documents', 'delete_stickers']})
            await security_audit.log("SECURITY_ENABLE_ALL", user_id, {"chat_id": chat_id}, "INFO")
            
        elif action == "disable_all":
            # تعطيل جميع الإعدادات
            for key in ['links', 'mentions', 'slow_mode', 'welcome_enabled', 'goodbye_enabled',
                        'delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
                        'delete_documents', 'delete_stickers']:
                settings[key] = False
            await db_set_security_settings(chat_id, **{k: False for k in ['links', 'mentions', 'slow_mode', 'welcome_enabled', 'goodbye_enabled',
                                                                            'delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
                                                                            'delete_documents', 'delete_stickers']})
            await security_audit.log("SECURITY_DISABLE_ALL", user_id, {"chat_id": chat_id}, "INFO")
            
        else:
            settings[setting_key] = not settings[setting_key]
            await db_set_security_settings(chat_id, **{setting_key: settings[setting_key]})
            await security_audit.log(event_name, user_id, {"chat_id": chat_id, "enabled": settings[setting_key]}, "INFO")
    else:
        await query.edit_message_text("❌ إجراء غير معروف")
        return

    _security_cache.pop(chat_id, None)
    await cache_manager.delete(f"security_{chat_id}")

    await _update_security_panel(query, chat_id, user_id)


# ===================================================================
# ===== كولباك إغلاق الأمان =====
# ===================================================================

async def security_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كولباك إغلاق إعدادات الأمان"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.delete()


# ===================================================================
# ===== كولباك تحديث المجموعات =====
# ===================================================================

async def security_refresh_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كولباك تحديث قائمة المجموعات"""
    query = update.callback_query
    if query:
        await query.answer()
    await my_groups_callback(update, context)


# ===================================================================
# ===== كولباك حذف مجموعة =====
# ===================================================================

async def delete_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كولباك حذف مجموعة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('delete_group_id')

    if not chat_id:
        return

    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        if query:
            await query.answer("❌ غير مصرح", show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, "❌ غير مصرح")
        return

    async def _delete_group(conn):
        await conn.execute("DELETE FROM bot_groups WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM user_groups_link WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM group_security WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM chat_locks WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM moderation_log WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM group_admins WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM group_rules WHERE chat_id = ?", (chat_id,))
        await conn.commit()

    await execute_db(_delete_group)
    invalidate_auth_cache(chat_id)

    if query:
        await query.edit_message_text("✅ تم حذف المجموعة من قاعدة البيانات.")
    else:
        await safe_send_markdown(context.bot, user_id, "✅ تم حذف المجموعة من قاعدة البيانات.")

    await my_groups_callback(update, context)


# ===================================================================
# ===== كولباك مجموعاتي =====
# ===================================================================

async def my_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كولباك عرض مجموعاتي"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except:
            pass
    user_id = update.effective_user.id

    groups = await db_get_user_groups(user_id)
    valid_groups = []

    for chat_id, chat_name, username, banned in groups:
        is_admin = await is_currently_admin_in_group(context.bot, chat_id, user_id)
        if is_admin:
            valid_groups.append((chat_id, chat_name, username, banned))

    if not valid_groups:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ أضف البوت", url=f"https://t.me/{BOT_USERNAME}?startgroup")],
            [InlineKeyboardButton("🔄 تحديث القائمة", callback_data=CallbackData.SECURITY_REFRESH_GROUPS)],
            [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
        ])
        msg = "📭 لا توجد مجموعات مسجلة\n\nأضف البوت إلى مجموعة وستظهر هنا."

        if query:
            try:
                await safe_edit_markdown(query, msg, reply_markup=kb)
            except:
                await query.edit_message_text(msg, reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, msg, reply_markup=kb)
        return

    keyboard = []
    for chat_id, chat_name, username, banned in valid_groups:
        display_name = chat_name[:28] + "..." if len(chat_name) > 31 else chat_name
        status_icon = "⛔" if banned else "✅"
        keyboard.append([InlineKeyboardButton(f"{status_icon} {display_name}", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")])
        keyboard.append([InlineKeyboardButton("🔐 الأمان", callback_data=f"{CallbackData.SECURITY_SELECT_GROUP}{chat_id}"),
                        InlineKeyboardButton("📜 السجل", callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}"),
                        InlineKeyboardButton("⚙️ متقدم", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")])

        is_locked = await is_chat_locked(chat_id)
        lock_label = "🔒 قفل" if not is_locked else "🔓 فتح"
        lock_callback = f"{CallbackData.PANEL_LOCK_PREFIX}{chat_id}" if not is_locked else f"{CallbackData.PANEL_UNLOCK_PREFIX}{chat_id}"
        keyboard.append([InlineKeyboardButton(lock_label, callback_data=lock_callback),
                        InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_group:{chat_id}")])
        keyboard.append([InlineKeyboardButton("─" * 20, callback_data="noop")])

    keyboard.append([InlineKeyboardButton("🔄 تحديث القائمة", callback_data=CallbackData.SECURITY_REFRESH_GROUPS),
                    InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "👥 **مجموعاتي**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر مجموعة للتحكم بها:\n\n✅ = نشطة  |  ⛔ = محظورة"

    if query:
        try:
            await safe_edit_markdown(query, text, reply_markup=reply_markup)
        except Exception as e:
            try:
                await query.edit_message_text(text, reply_markup=reply_markup)
            except:
                pass
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=reply_markup)

# ===================================================================
# ===== 61. الوظيفة الرئيسية (main) =====
# ===================================================================

async def main():
    """الوظيفة الرئيسية لتشغيل البوت"""
    # تهيئة قاعدة البيانات
    await init_db_improved()

    # استيراد الكلمات المحظورة من الملف
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
                    except:
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

    # تهيئة التخزين المؤقت
    await cache_manager.init()

    # إنشاء التطبيق
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

    # إضافة معالج الأخطاء
    application.add_error_handler(global_error_handler)

    # ===== إضافة الأوامر =====
    # الأوامر الأساسية
    application.add_handler(CommandHandler("start", start_command_handler))
    application.add_handler(CommandHandler("language", language_command_handler))
    application.add_handler(CommandHandler("syncgroup", syncgroup_command_handler))
    application.add_handler(CommandHandler("security", security_select_group_callback))
    application.add_handler(CommandHandler("register_hidden_owner", register_hidden_owner_handler))
    application.add_handler(CommandHandler("add_hidden_admin", add_hidden_admin_command))
    application.add_handler(CommandHandler("remove_hidden_admin", remove_hidden_admin_command))
    application.add_handler(CommandHandler("list_hidden_admins", list_hidden_admins_command))

    # الاشتراك والتجربة
    application.add_handler(CommandHandler("trial", trial_command_handler))
    application.add_handler(CommandHandler("subscribe", subscribe_command_handler))

    # المساعدة والدعم
    application.add_handler(CommandHandler("help", help_command_handler))
    application.add_handler(CommandHandler("support", support_command_handler))
    application.add_handler(CommandHandler("support_reply", support_reply_command_handler))

    # المستويات والإحصائيات
    application.add_handler(CommandHandler("rank", rank_command_handler))
    application.add_handler(CommandHandler("top", top_command_handler))
    application.add_handler(CommandHandler("stats", stats_command_handler))

    # المطور والتحديثات
    application.add_handler(CommandHandler("developer", developer_command_handler))
    application.add_handler(CommandHandler("updates", updates_command_handler))

    # الأوامر الإدارية
    application.add_handler(CommandHandler("sendcode", sendcode_command_handler))
    application.add_handler(CommandHandler("lock", lock_chat_command_handler))
    application.add_handler(CommandHandler("unlock", unlock_chat_command_handler))
    application.add_handler(CommandHandler("schedule", schedule_post_command_handler))
    application.add_handler(CommandHandler("panel", panel_command_handler))
    application.add_handler(CommandHandler("set_log_channel", set_log_channel_command_handler))

    # أوامر الرقابة
    application.add_handler(CommandHandler("ban", handle_moderation_commands))
    application.add_handler(CommandHandler("mute", handle_moderation_commands))
    application.add_handler(CommandHandler("warn", handle_moderation_commands))
    application.add_handler(CommandHandler("kick", handle_moderation_commands))
    application.add_handler(CommandHandler("restrict", handle_moderation_commands))
    application.add_handler(CommandHandler("pin", handle_moderation_commands))
    application.add_handler(CommandHandler("unban", handle_moderation_commands))

    # المسابقات
    application.add_handler(CommandHandler("contests", contests_command_handler))
    application.add_handler(CommandHandler("create_contest", create_contest_command_handler))
    application.add_handler(CommandHandler("declare_winner", declare_winner_command_handler))

    # القوانين
    application.add_handler(CommandHandler("set_rules", set_rules_command_handler))
    application.add_handler(CommandHandler("rules", rules_command_handler))

    # الميزات الجديدة
    application.add_handler(CommandHandler("coupon", coupon_command_handler))
    application.add_handler(CommandHandler("poll", poll_command_handler))
    application.add_handler(CommandHandler("vote", vote_command_handler))
    application.add_handler(CommandHandler("faq", faq_command_handler))
    application.add_handler(CommandHandler("announce", announce_command_handler))

    # ===== إضافة معالجات الكولباك =====
    # الكولباك الرئيسية
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern=f"^{CallbackData.MAIN_MENU}$"))
    application.add_handler(CallbackQueryHandler(back_callback, pattern=f"^{CallbackData.BACK}$"))
    application.add_handler(CallbackQueryHandler(cancel_session_callback, pattern=f"^{CallbackData.CANCEL_SESSION}$"))

    # كولباك القنوات
    application.add_handler(CallbackQueryHandler(add_channel_callback, pattern=f"^{CallbackData.CHANNELS_ADD}$"))
    application.add_handler(CallbackQueryHandler(my_channels_callback, pattern=f"^{CallbackData.CHANNELS_MY}$"))
    application.add_handler(CallbackQueryHandler(delete_channel_callback, pattern=f"^{CallbackData.CHANNELS_DELETE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(select_channel_callback, pattern=f"^{CallbackData.CHANNELS_SELECT_PREFIX}"))

    # كولباك المنشورات
    application.add_handler(CallbackQueryHandler(add_15_posts_callback, pattern=f"^{CallbackData.POSTS_ADD_15}$"))
    application.add_handler(CallbackQueryHandler(publish_one_callback, pattern=f"^{CallbackData.POSTS_PUBLISH_ONE}$"))
    application.add_handler(CallbackQueryHandler(my_posts_callback, pattern=f"^{CallbackData.POSTS_MY}$"))
    application.add_handler(CallbackQueryHandler(recycle_posts_callback, pattern=f"^{CallbackData.POSTS_RECYCLE}$"))
    application.add_handler(CallbackQueryHandler(delete_single_post_callback, pattern=f"^{CallbackData.POSTS_DELETE_SINGLE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(confirm_clear_all_posts_callback, pattern=f"^{CallbackData.POSTS_CONFIRM_CLEAR_ALL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(clear_all_posts_callback, pattern=f"^{CallbackData.POSTS_CLEAR_ALL_PREFIX}"))

    # كولباك الإحصائيات
    application.add_handler(CallbackQueryHandler(my_pending_stats_callback, pattern=f"^{CallbackData.STATS_PENDING}$"))
    application.add_handler(CallbackQueryHandler(my_full_stats_callback, pattern=f"^{CallbackData.STATS_FULL}$"))

    # كولباك المجموعات
    application.add_handler(CallbackQueryHandler(my_groups_callback, pattern=f"^{CallbackData.GROUPS_MY}$"))
    application.add_handler(CallbackQueryHandler(group_settings_callback, pattern=f"^{CallbackData.GROUPS_SETTINGS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(delete_group_callback, pattern=r"^delete_group:"))

    # كولباك الأمان
    application.add_handler(CallbackQueryHandler(security_select_group_callback, pattern=f"^{CallbackData.SECURITY_SELECT_GROUP}"))
    application.add_handler(CallbackQueryHandler(security_toggle_callback, pattern=r"^security:"))
    application.add_handler(CallbackQueryHandler(security_close_callback, pattern=f"^{CallbackData.SECURITY_CLOSE}$"))
    application.add_handler(CallbackQueryHandler(security_toggle_callback, pattern=f"^{CallbackData.SECURITY_ENABLE_ALL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(security_toggle_callback, pattern=f"^{CallbackData.SECURITY_DISABLE_ALL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(security_toggle_callback, pattern=f"^{CallbackData.SECURITY_DELETE_PENALTY_PREFIX}"))

    # كولباك الكلمات المحظورة
    application.add_handler(CallbackQueryHandler(handle_banned_words_menu, pattern=f"^{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}"))
    application.add_handler(CallbackQueryHandler(handle_banned_words_add, pattern=f"^{CallbackData.BANNED_WORDS_ADD_PREFIX}"))
    application.add_handler(CallbackQueryHandler(handle_banned_words_list, pattern=f"^{CallbackData.BANNED_WORDS_LIST_PREFIX}"))
    application.add_handler(CallbackQueryHandler(handle_banned_words_remove, pattern=f"^{CallbackData.BANNED_WORDS_REMOVE_PREFIX}"))

    # كولباك المساعدة والدعم
    application.add_handler(CallbackQueryHandler(support_menu_callback, pattern=f"^{CallbackData.SUPPORT_MENU}$"))
    application.add_handler(CallbackQueryHandler(help_callback, pattern=f"^{CallbackData.HELP}$"))
    application.add_handler(CallbackQueryHandler(ticket_callback, pattern=f"^{CallbackData.SUPPORT_TICKET}$"))

    # كولباك الاشتراك
    application.add_handler(CallbackQueryHandler(trial_callback, pattern=f"^{CallbackData.TRIAL}$"))
    application.add_handler(CallbackQueryHandler(subscribe_menu_callback, pattern=f"^{CallbackData.SUBSCRIBE_MENU}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_1}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_2}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_30}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_90}$"))

    # كولباك المطور والتحديثات
    application.add_handler(CallbackQueryHandler(developer_callback, pattern=f"^{CallbackData.DEVELOPER}$"))
    application.add_handler(CallbackQueryHandler(updates_callback, pattern=f"^{CallbackData.UPDATES}$"))

    # كولباك الإحالات
    application.add_handler(CallbackQueryHandler(referral_menu_callback, pattern=f"^{CallbackData.REFERRAL_MENU}$"))
    application.add_handler(CallbackQueryHandler(referral_copy_link_callback, pattern=f"^{CallbackData.REFERRAL_COPY_LINK_PREFIX}"))
    application.add_handler(CallbackQueryHandler(referral_claim_reward_callback, pattern=f"^{CallbackData.REFERRAL_CLAIM_REWARD}$"))
    application.add_handler(CallbackQueryHandler(referral_list_callback, pattern=f"^{CallbackData.REFERRAL_LIST}$"))

    # كولباك التذكيرات
    application.add_handler(CallbackQueryHandler(reminder_menu_callback, pattern=f"^{CallbackData.REMINDER_MENU}$"))
    application.add_handler(CallbackQueryHandler(reminder_toggle_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_SUB}$"))
    application.add_handler(CallbackQueryHandler(reminder_toggle_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_DAILY}$"))
    application.add_handler(CallbackQueryHandler(reminder_toggle_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_WEEKLY}$"))
    application.add_handler(CallbackQueryHandler(reminder_set_days_callback, pattern=f"^{CallbackData.REMINDER_SET_DAYS}$"))
    application.add_handler(CallbackQueryHandler(reminder_set_lang_callback, pattern=f"^{CallbackData.REMINDER_SET_LANG}$"))

    # كولباك الترجمة
    application.add_handler(CallbackQueryHandler(translation_menu_callback, pattern=f"^{CallbackData.TRANSLATION_MENU}$"))
    application.add_handler(CallbackQueryHandler(translation_off_callback, pattern=f"^{CallbackData.TRANSLATION_OFF}$"))
    application.add_handler(CallbackQueryHandler(translation_set_callback, pattern=f"^{CallbackData.TRANSLATION_SET_PREFIX}"))

    # كولباك لوحة الأدمن
    application.add_handler(CallbackQueryHandler(admin_panel_callback, pattern=f"^{CallbackData.ADMIN_PANEL}$"))
    application.add_handler(CallbackQueryHandler(admin_users_callback, pattern=f"^{CallbackData.ADMIN_USERS}$"))
    application.add_handler(CallbackQueryHandler(admin_banned_users_callback, pattern=f"^{CallbackData.ADMIN_BANNED_USERS}$"))
    application.add_handler(CallbackQueryHandler(admin_unban_all_users_callback, pattern=f"^{CallbackData.ADMIN_UNBAN_ALL_USERS}$"))
    application.add_handler(CallbackQueryHandler(admin_channels_callback, pattern=f"^{CallbackData.ADMIN_ALL_CHANNELS}$"))
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
    application.add_handler(CallbackQueryHandler(admin_replies_callback, pattern=f"^{CallbackData.ADMIN_REPLIES}$"))
    application.add_handler(CallbackQueryHandler(admin_add_reply_callback, pattern=f"^{CallbackData.ADMIN_ADD_REPLY}$"))
    application.add_handler(CallbackQueryHandler(admin_list_replies_callback, pattern=f"^{CallbackData.ADMIN_LIST_REPLIES}$"))
    application.add_handler(CallbackQueryHandler(admin_del_reply_callback, pattern=f"^{CallbackData.ADMIN_DEL_REPLY}$"))
    application.add_handler(CallbackQueryHandler(admin_banned_words_callback, pattern=f"^{CallbackData.ADMIN_BANNED_WORDS}$"))
    application.add_handler(CallbackQueryHandler(admin_add_banned_word_callback, pattern=f"^{CallbackData.ADMIN_ADD_BANNED_WORD}$"))
    application.add_handler(CallbackQueryHandler(admin_list_banned_words_callback, pattern=f"^{CallbackData.ADMIN_LIST_BANNED_WORDS}$"))
    application.add_handler(CallbackQueryHandler(admin_remove_banned_word_callback, pattern=f"^{CallbackData.ADMIN_REMOVE_BANNED_WORD}$"))
    application.add_handler(CallbackQueryHandler(admin_create_contest_callback, pattern=f"^{CallbackData.ADMIN_CREATE_CONTEST}$"))
    application.add_handler(CallbackQueryHandler(admin_declare_winner_callback, pattern=f"^{CallbackData.ADMIN_DECLARE_WINNER}$"))
    application.add_handler(CallbackQueryHandler(admin_del_contest_callback, pattern=f"^{CallbackData.ADMIN_DEL_CONTEST_PREFIX}"))

    # كولباك الميزات الجديدة
    application.add_handler(CallbackQueryHandler(admin_coupons_callback, pattern=f"^{CallbackData.ADMIN_COUPONS}$"))
    application.add_handler(CallbackQueryHandler(admin_create_coupon_callback, pattern=f"^{CallbackData.ADMIN_CREATE_COUPON}$"))
    application.add_handler(CallbackQueryHandler(admin_list_coupons_callback, pattern=f"^{CallbackData.ADMIN_LIST_COUPONS}$"))
    application.add_handler(CallbackQueryHandler(admin_delete_coupon_callback, pattern=f"^{CallbackData.ADMIN_DELETE_COUPON}$"))
    application.add_handler(CallbackQueryHandler(admin_polls_callback, pattern=f"^{CallbackData.ADMIN_POLLS}$"))
    application.add_handler(CallbackQueryHandler(admin_create_poll_callback, pattern=f"^{CallbackData.ADMIN_CREATE_POLL}$"))
    application.add_handler(CallbackQueryHandler(admin_list_polls_callback, pattern=f"^{CallbackData.ADMIN_LIST_POLLS}$"))
    application.add_handler(CallbackQueryHandler(admin_delete_poll_callback, pattern=f"^{CallbackData.ADMIN_DELETE_POLL}$"))
    application.add_handler(CallbackQueryHandler(admin_ads_callback, pattern=f"^{CallbackData.ADMIN_ADS}$"))
    application.add_handler(CallbackQueryHandler(admin_create_ad_callback, pattern=f"^{CallbackData.ADMIN_CREATE_AD}$"))
    application.add_handler(CallbackQueryHandler(admin_list_ads_callback, pattern=f"^{CallbackData.ADMIN_LIST_ADS}$"))
    application.add_handler(CallbackQueryHandler(admin_delete_ad_callback, pattern=f"^{CallbackData.ADMIN_DELETE_AD}$"))
    application.add_handler(CallbackQueryHandler(admin_faq_callback, pattern=f"^{CallbackData.ADMIN_FAQ}$"))
    application.add_handler(CallbackQueryHandler(admin_add_faq_callback, pattern=f"^{CallbackData.ADMIN_ADD_FAQ}$"))
    application.add_handler(CallbackQueryHandler(admin_list_faq_callback, pattern=f"^{CallbackData.ADMIN_LIST_FAQ}$"))
    application.add_handler(CallbackQueryHandler(admin_delete_faq_callback, pattern=f"^{CallbackData.ADMIN_DELETE_FAQ}$"))

    # كولباك كوبونات المستخدم
    application.add_handler(CallbackQueryHandler(coupon_use_callback, pattern=f"^{CallbackData.COUPON_USE}$"))

    # كولباك الاستطلاعات
    application.add_handler(CallbackQueryHandler(poll_vote_callback, pattern=f"^{CallbackData.POLL_VOTE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(poll_results_callback, pattern=f"^{CallbackData.POLL_RESULTS_PREFIX}"))

    # كولباك المسابقات
    application.add_handler(CallbackQueryHandler(contests_menu_callback, pattern=f"^{CallbackData.CONTESTS_MENU}$"))
    application.add_handler(CallbackQueryHandler(contest_join_callback, pattern=f"^{CallbackData.CONTEST_JOIN_PREFIX}"))
    application.add_handler(CallbackQueryHandler(contest_winners_callback, pattern=f"^{CallbackData.CONTEST_WINNERS}$"))
    application.add_handler(CallbackQueryHandler(contests_back_callback, pattern=f"^{CallbackData.CONTESTS_BACK}$"))

    # كولباك المشرفين المخفيين
    application.add_handler(CallbackQueryHandler(hidden_admin_add_callback, pattern=f"^{CallbackData.HIDDEN_ADMIN_ADD}$"))
    application.add_handler(CallbackQueryHandler(hidden_admin_remove_callback, pattern=f"^{CallbackData.HIDDEN_ADMIN_REMOVE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(hidden_admin_list_callback, pattern=f"^{CallbackData.HIDDEN_ADMIN_LIST}$"))

    # كولباك الردود التلقائية
    application.add_handler(CallbackQueryHandler(auto_reply_menu_callback, pattern=f"^{CallbackData.AUTO_REPLY_MENU_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_toggle_callback, pattern=f"^{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_admins_callback, pattern=f"^{CallbackData.AUTO_REPLY_ADMINS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_reset_callback, pattern=f"^{CallbackData.AUTO_REPLY_RESET_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_stats_callback, pattern=f"^{CallbackData.AUTO_REPLY_STATS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(user_auto_reply_toggle_callback, pattern=f"^{CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX}"))

    # كولباك NSFW
    application.add_handler(CallbackQueryHandler(nsfw_settings_callback, pattern=f"^{CallbackData.NSFW_SETTINGS}$"))
    application.add_handler(CallbackQueryHandler(nsfw_toggle_callback, pattern=f"^{CallbackData.NSFW_TOGGLE}$"))
    application.add_handler(CallbackQueryHandler(nsfw_threshold_set_callback, pattern=f"^{CallbackData.NSFW_THRESHOLD_SET}$"))

    # كولباك الإجراءات المتقدمة
    application.add_handler(CallbackQueryHandler(advanced_actions_callback, pattern=f"^{CallbackData.ADVANCED_ACTIONS}"))
    application.add_handler(CallbackQueryHandler(group_action_callback, pattern=f"^{CallbackData.GROUP_ACTION_BAN}"))
    application.add_handler(CallbackQueryHandler(group_action_callback, pattern=f"^{CallbackData.GROUP_ACTION_MUTE}"))
    application.add_handler(CallbackQueryHandler(group_action_callback, pattern=f"^{CallbackData.GROUP_ACTION_WARN}"))
    application.add_handler(CallbackQueryHandler(group_action_callback, pattern=f"^{CallbackData.GROUP_ACTION_KICK}"))
    application.add_handler(CallbackQueryHandler(group_action_callback, pattern=f"^{CallbackData.GROUP_ACTION_RESTRICT}"))
    application.add_handler(CallbackQueryHandler(group_action_callback, pattern=f"^{CallbackData.GROUP_ACTION_PIN}"))
    application.add_handler(CallbackQueryHandler(group_action_callback, pattern=f"^{CallbackData.GROUP_ACTION_UNBAN}"))
    application.add_handler(CallbackQueryHandler(group_action_log_callback, pattern=f"^{CallbackData.GROUP_ACTION_LOG}"))
    application.add_handler(CallbackQueryHandler(mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_5}"))
    application.add_handler(CallbackQueryHandler(mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_30}"))
    application.add_handler(CallbackQueryHandler(mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_60}"))
    application.add_handler(CallbackQueryHandler(mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_720}"))
    application.add_handler(CallbackQueryHandler(mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_1440}"))
    application.add_handler(CallbackQueryHandler(mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_10080}"))
    application.add_handler(CallbackQueryHandler(mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_PERMANENT}"))

    # كولباك العقوبات
    application.add_handler(CallbackQueryHandler(penalty_menu_callback, pattern=f"^{CallbackData.PENALTY_MENU}"))
    application.add_handler(CallbackQueryHandler(penalty_kick_callback, pattern=f"^{CallbackData.PENALTY_KICK}"))
    application.add_handler(CallbackQueryHandler(penalty_ban_callback, pattern=f"^{CallbackData.PENALTY_BAN}"))
    application.add_handler(CallbackQueryHandler(penalty_mute_callback, pattern=f"^{CallbackData.PENALTY_MUTE}"))

    # كولباك النشر
    application.add_handler(CallbackQueryHandler(publish_all_channels_callback, pattern=f"^{CallbackData.PUBLISH_ALL_CHANNELS}$"))
    application.add_handler(CallbackQueryHandler(channel_stats_callback, pattern=f"^{CallbackData.CHANNEL_STATS}"))
    application.add_handler(CallbackQueryHandler(channel_growth_callback, pattern=f"^{CallbackData.CHANNEL_GROWTH}"))
    application.add_handler(CallbackQueryHandler(my_channel_stats_callback, pattern=f"^{CallbackData.MY_CHANNEL_STATS}$"))

    # كولباك الجدولة
    application.add_handler(CallbackQueryHandler(schedule_menu_callback, pattern=f"^{CallbackData.SCHEDULE_MENU_PREFIX}"))
    application.add_handler(CallbackQueryHandler(schedule_set_interval_callback, pattern=f"^{CallbackData.SCHEDULE_SET_INTERVAL_MINUTES_PREFIX}"))
    application.add_handler(CallbackQueryHandler(schedule_set_interval_callback, pattern=f"^{CallbackData.SCHEDULE_SET_INTERVAL_HOURS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(schedule_set_interval_callback, pattern=f"^{CallbackData.SCHEDULE_SET_INTERVAL_DAYS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(schedule_set_days_callback, pattern=f"^{CallbackData.SCHEDULE_SET_DAYS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(schedule_set_dates_callback, pattern=f"^{CallbackData.SCHEDULE_SET_DATES_PREFIX}"))
    application.add_handler(CallbackQueryHandler(schedule_set_publish_time_callback, pattern=f"^{CallbackData.SCHEDULE_SET_PUBLISH_TIME_PREFIX}"))
    application.add_handler(CallbackQueryHandler(schedule_day_select_callback, pattern=f"^{CallbackData.SCHEDULE_DAY_SELECT_PREFIX}"))
    application.add_handler(CallbackQueryHandler(schedule_save_days_callback, pattern=f"^{CallbackData.SCHEDULE_SAVE_DAYS}$"))

    # كولباك القفل والفتح
    application.add_handler(CallbackQueryHandler(panel_lock_callback, pattern=f"^{CallbackData.PANEL_LOCK_PREFIX}"))
    application.add_handler(CallbackQueryHandler(panel_unlock_callback, pattern=f"^{CallbackData.PANEL_UNLOCK_PREFIX}"))
    application.add_handler(CallbackQueryHandler(panel_close_callback, pattern=f"^{CallbackData.PANEL_CLOSE}$"))

    # كولباك اللغة
    application.add_handler(CallbackQueryHandler(language_callback, pattern=r"^lang_"))

    # كولباك الإعدادات
    application.add_handler(CallbackQueryHandler(settings_menu_callback, pattern=f"^{CallbackData.SETTINGS_MENU}$"))
    application.add_handler(CallbackQueryHandler(settings_toggle_auto_publish_callback, pattern=f"^{CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH}$"))
    application.add_handler(CallbackQueryHandler(settings_toggle_auto_recycle_callback, pattern=f"^{CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE}$"))

    # كولباك التحقق من الاشتراك
    application.add_handler(CallbackQueryHandler(check_subscribe_callback, pattern=f"^{CallbackData.CHECK_SUBSCRIBE}$"))

    # ===== إضافة معالجات الأحداث =====
    application.add_handler(ChatJoinRequestHandler(chat_join_request_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_chat_member_handler))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback_handler))
    application.add_handler(ChatMemberHandler(track_chat_add, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler))
    application.add_handler(MessageHandler(filters.CAPTION & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, message_handler_main))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.AUDIO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.VOICE & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.ANIMATION & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER, delete_service_messages))

    # ===== أوامر البوت =====
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
        BotCommand("support_reply", "الرد على تذكرة"),
        BotCommand("help", "المساعدة"),
        BotCommand("developer", "المطور"),
        BotCommand("updates", "آخر التحديثات"),
        BotCommand("sendcode", "إرسال كود البوت"),
        BotCommand("set_log_channel", "تعيين قناة التقارير"),
        BotCommand("ban", "حظر مستخدم"),
        BotCommand("mute", "كتم مستخدم"),
        BotCommand("warn", "تحذير مستخدم"),
        BotCommand("kick", "طرد مستخدم"),
        BotCommand("restrict", "تقييد مستخدم"),
        BotCommand("pin", "تثبيت رسالة"),
        BotCommand("unban", "إلغاء حظر مستخدم"),
        BotCommand("contests", "المسابقات"),
        BotCommand("create_contest", "إنشاء مسابقة"),
        BotCommand("declare_winner", "إعلان فائز"),
        BotCommand("set_rules", "تعيين قوانين المجموعة"),
        BotCommand("rules", "عرض قوانين المجموعة"),
        BotCommand("coupon", "استخدام كوبون خصم"),
        BotCommand("poll", "إنشاء استطلاع رأي"),
        BotCommand("vote", "التصويت في استطلاع"),
        BotCommand("faq", "الأسئلة الشائعة"),
        BotCommand("announce", "إعلان جديد"),
    ]
    await application.bot.set_my_commands(commands)

    # ===== تشغيل المهام الخلفية =====
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

    print(f"🚀 تم تشغيل {BOT_NAME} (الإصدار 21.0.0 - النسخة العالمية الكاملة)")
    print("✅ جميع التحسينات العالمية تم تطبيقها:")
    print("   • ✅ خادم ويب موحد - لا تعارض في المنافذ")
    print("   • ✅ نظام صلاحيات محسن: مالك مخفي > مشرف مخفي > مشرف حقيقي")
    print("   • ✅ معالج /syncgroup يعمل للمشرفين والأعضاء العاديين بشكل مختلف")
    print("   • ✅ تسجيل تلقائي للمجموعة والمالك عند إضافة البوت")
    print("   • ✅ إشعار المشرفين عند طلب التفعيل من عضو عادي")
    print("   • ✅ حلقة تحديث المشرفين والمالكين المخفيين التلقائية (كل ساعة)")
    print("   • ✅ التحقق المباشر من تيليجرام عند الحاجة مع تحديث قاعدة البيانات")
    print("   • ✅ كاش ذكي للصلاحيات لتسريع الأداء")
    print("   • ✅ 200 رد تلقائي للمجموعات مع أوزان")
    print("   • ✅ نظام ردود متقدم مع إعدادات لكل مجموعة")
    print("   • ✅ دعم المالك والمشرفين المخفيين المتعددين")
    print("   • ✅ نظام المسابقات المتكامل")
    print("   • ✅ دعم أوامر /set_rules و /rules لقوانين المجموعة")
    print("   • ✅ دعم حذف رسائل الخدمة التلقائي")
    print("   • ✅ دعم الترحيب والوداع في المجموعات")
    print("   • ✅ إصلاح ثغرة صلاحيات المشرفين (التحقق المزدوج)")
    print("   • ✅ إصلاح تسجيل المالك المخفي (إعادة المحاولة وإشعار جميع المشرفين)")
    print("   • ✅ معالجة خطأ User_bot_to_bot_disabled")
    print("   • ✅ تحسين أمان أمر /sendcode (إزالة التوكن والمفاتيح)")
    print("   • ✅ إضافة دوال إعادة التشغيل التلقائي (safe_loop)")
    print("   • ✅ إضافة نظام النبض الداخلي (self_ping)")
    print("   • ✅ نظام كوبونات الخصم")
    print("   • ✅ نظام استطلاعات الرأي")
    print("   • ✅ نظام الإعلانات المدفوعة")
    print("   • ✅ نظام الأسئلة الشائعة (FAQ)")
    print("   • ✅ نظام القوانين المتقدم للمجموعات")
    print("   • ✅ نظام الإعلانات المجدولة")

    # ===== تشغيل البوت مع خادم ويب موحد =====
    try:
        port = int(os.getenv("PORT", "10000"))
        hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")

        await setup_unified_web_server(application, port)

        if hostname:
            webhook_url = f"https://{hostname}/{TOKEN}"
            await application.initialize()
            await application.start()
            await application.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "chat_member", "chat_join_request", "pre_checkout_query"]
            )
            logger.info(f"✅ تم تعيين Webhook إلى: {webhook_url}")
            await asyncio.Event().wait()
        else:
            logger.info("🔄 استخدام Polling (بدون Webhook)")
            await run_polling_safe(application)

    except Exception as e:
        logger.error(f"❌ فشل بدء البوت: {e}")
        try:
            await application.bot.delete_webhook()
        except:
            pass
        await run_polling_safe(application)
    finally:
        await cleanup_resources()
        await task_manager.cancel_all()


# ===================================================================
# ===== 62. نقطة الدخول الرئيسية =====
# ===================================================================

if __name__ == "__main__":
    try:
        os.environ["WEB_CONCURRENCY"] = "1"
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 تم إيقاف البوت")
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

# ===================================================================
# ===== نهاية الكود الكامل لريلاكس مانيجر - الإصدار 21.0.0 =====
# ===================================================================

