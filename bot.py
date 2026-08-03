
#]#!/usr/bin/env python3#احدث نسخةة
# -*- coding: utf-8 -*-
"""
ريلاكس مانيجر - بوت متكامل لإدارة القنوات والمجموعات
الإصدار: 20.0.19-patched - النسخة العالمية مع نظام صلاحيات محسن وأمان متقدم
المطور: @RelaxMgr
تم التصحيح: إصلاح جميع الأخطاء الحرجة وتحسين الأداء والأمان
"""

import sys
import aiosqlite
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
import numpy as np  # ✅ تمت الإضافة لاستخدامه في check_nsfw_video
from replies import ALL_REPLIES, get_weighted_reply
import logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
import sys, traceback
def log_uncaught(exc_type, exc_value, exc_tb):
    with open("crash.log", "a") as f:
        f.write(f"{datetime.now()} - UNCAUGHT:\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
sys.excepthook = log_uncaught
# ===================== التحقق من إصدار بايثون =====================
def check_python_version():
    required_version = (3, 8)
    current_version = sys.version_info
    if current_version < required_version:
        print(f"❌ يحتاج البوت إلى بايثون {required_version[0]}.{required_version[1]} أو أحدث")
        print(f"📌 الإصدار الحالي: {current_version[0]}.{current_version[1]}")
        sys.exit(1)

check_python_version()

# ===================== تعريف المتغيرات قبل الاستخدام =====================
JINJA2_AVAILABLE = False
CV2_AVAILABLE = False
PIL_AVAILABLE = False
BLEACH_AVAILABLE = False
KEYRING_AVAILABLE = False
REDIS_AVAILABLE = False
NEST_ASYNCIO_AVAILABLE = False
PYOTP_AVAILABLE = False

# ===================== محاولة استيراد المكتبات مع معالجة الأخطاء =====================
try:
    import jinja2
    JINJA2_AVAILABLE = True
except ImportError:
    print("⚠️ Jinja2 غير متاح - سيتم استخدام HTML النقي")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    print("⚠️ OpenCV غير متاح - سيتم تعطيل فحص الفيديو")

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    print("⚠️ PIL غير متاح - سيتم تعطيل معالجة الصور")

try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    print("⚠️ Bleach غير متاح - سيتم استخدام تنظيف أساسي")

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    print("⚠️ Keyring غير متاح - سيتم استخدام التخزين المحلي")

try:
    import aioredis
    REDIS_AVAILABLE = True
except ImportError:
    print("⚠️ aioredis غير متاح - سيتم استخدام التخزين المؤقت في الذاكرة")

try:
    import nest_asyncio
    NEST_ASYNCIO_AVAILABLE = True
    nest_asyncio.apply()
except ImportError:
    pass

try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    print("⚠️ pyotp غير متاح - سيتم تعطيل المصادقة الثنائية")

# ===================== استيراد مكتبات تيليجرام =====================
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember, BotCommand, LabeledPrice, ChatPermissions
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler, ChatMemberHandler, ChatJoinRequestHandler
from telegram.error import TimedOut, NetworkError, BadRequest, Forbidden, Conflict
from telegram.request import HTTPXRequest
import httpx

# ===================== استيراد مكتبات إضافية =====================
try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from aiohttp import web, WSMsgType
import aiohttp

# ===================== المسارات الأساسية =====================
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

def get_temp_path() -> Path:
    return get_writable_path(BASE_PATH, "temp")

DATA_PATH = get_writable_path(BASE_PATH, "data")  # ✅ تم التعديل: استخدام DATA_PATH للملفات القابلة للكتابة
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
REPLIES_FILE = DATA_PATH / "replies.json"  # ✅ تم التعديل: نقل إلى DATA_PATH
# ===================== المسارات الأساسية ================
BANNED_WORDS_FILES = [
    DATA_PATH / "banned_words.txt",
    BASE_PATH / "assets" / "banned_words.txt",
]
# ===================== المسارات الأساسية =====================
...
REPLIES_FILE = DATA_PATH / "replies.json"
BANNED_WORDS_FILE = DATA_PATH / "banned_words.txt"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
DATA_PATH.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
TEMP_PATH.mkdir(parents=True, exist_ok=True)
STATIC_PATH.mkdir(parents=True, exist_ok=True)
TEMPLATES_PATH.mkdir(parents=True, exist_ok=True)
LANG_PATH.mkdir(parents=True, exist_ok=True)

# ===================== نظام التسجيل المحسن مع إخفاء البيانات الحساسة =====================
class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        # إخفاء التوكنات والمفاتيح
        sensitive_patterns = [
            (TOKEN, "[TOKEN_HIDDEN]") if 'TOKEN' in globals() else None,
            (ENCRYPTION_KEY, "[ENCRYPTION_KEY_HIDDEN]") if 'ENCRYPTION_KEY' in globals() else None,
            (BACKUP_ENCRYPTION_KEY, "[BACKUP_KEY_HIDDEN]") if 'BACKUP_ENCRYPTION_KEY' in globals() else None,
        ]
        for pattern, replacement in sensitive_patterns:
            if pattern and isinstance(pattern, (str, bytes)):
                try:
                    pattern_str = pattern.decode() if isinstance(pattern, bytes) else pattern
                    if pattern_str and pattern_str in msg:
                        msg = msg.replace(pattern_str, replacement)
                except:
                    pass
        record.msg = msg
        return True

from logging.handlers import RotatingFileHandler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        RotatingFileHandler(
            LOG_PATH,
            maxBytes=10*1024*1024,
            backupCount=5,
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

for handler in logger.handlers:
    handler.addFilter(SensitiveDataFilter())

# ===================== تحميل ملفات البيئة =====================
def load_env_files():
    try:
        from dotenv import load_dotenv
        env_files = [
            ".env",
            ".env.local",
            str(BASE_PATH / ".env"),
            str(BASE_PATH / "config" / ".env"),
            str(Path.home() / ".bot" / ".env"),
        ]
        loaded = False
        for env_file in env_files:
            if os.path.exists(env_file):
                load_dotenv(env_file, override=True)
                loaded = True
        return loaded
    except ImportError:
        print("⚠️ python-dotenv غير مثبت - سيتم استخدام متغيرات البيئة فقط")
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

# ===================== الثوابت الأساسية =====================
TOKEN = get_env_or_default("BOT_TOKEN", None, str)
if TOKEN is None or TOKEN == "":
    raise ValueError("❌ لم يتم العثور على BOT_TOKEN في ملفات البيئة")

PRIMARY_OWNER_ID = get_env_or_default("MAIN_ADMIN_ID", 0, int)
if PRIMARY_OWNER_ID == 0:
    raise ValueError("❌ MAIN_ADMIN_ID غير محدد في ملفات البيئة")

BOT_NAME = get_env_or_default("BOT_NAME", "ريلاكس مانيجر", str)
BOT_USERNAME = get_env_or_default("BOT_USERNAME", "Reelaaaxbot", str)
USE_PROXY = get_env_or_default("USE_PROXY", False, bool)
PROXY_URL = get_env_or_default("PROXY_URL", "http://127.0.0.1:10809", str)
ENABLE_2FA = get_env_or_default("ENABLE_2FA", False, bool)
ADMIN_2FA_SECRET = get_env_or_default("ADMIN_2FA_SECRET", "", str)
DB_ENCRYPTION = get_env_or_default("DB_ENCRYPTION", True, bool)
MAX_BACKUPS = get_env_or_default("MAX_BACKUPS", 10, int)
SECURITY_LOG_LEVEL = get_env_or_default("SECURITY_LOG_LEVEL", "CRITICAL", str)

GOOGLE_DRIVE_FOLDER_ID = get_env_or_default("GOOGLE_DRIVE_FOLDER_ID", "", str)
CLOUD_BACKUP_ENABLED = get_env_or_default("CLOUD_BACKUP_ENABLED", False, bool)
GOOGLE_CREDENTIALS_FILE = get_env_or_default("GOOGLE_CREDENTIALS_FILE", "credentials.json", str)
TOKEN_FILE = get_env_or_default("TOKEN_FILE", "token.json", str)

# ===== إعدادات Render =====
RENDER_PORT = int(os.getenv("PORT", "10000"))
WEB_PORT = get_env_or_default("WEB_PORT", RENDER_PORT, int)
if WEB_PORT == 8080 and RENDER_PORT != 8080:
    WEB_PORT = RENDER_PORT

WEB_HOST = get_env_or_default("WEB_HOST", "0.0.0.0", str)
WEB_PASSWORD = get_env_or_default("WEB_PASSWORD", "", str)
if not WEB_PASSWORD and os.getenv('ENVIRONMENT', 'development') == 'production':
    print("⚠️ تحذير أمني: WEB_PASSWORD غير معيّنة في بيئة الإنتاج! سيتم طلب كلمة مرور عشوائية.")
    WEB_PASSWORD = secrets.token_urlsafe(16)
    # ✅ لا نطبعها في السجل
    logger.info("🔑 تم إنشاء كلمة مرور مؤقتة للويب (مخفية)")
WEB_USERNAME = get_env_or_default("WEB_USERNAME", "admin", str)
WEB_SECRET_KEY = get_env_or_default("WEB_SECRET_KEY", secrets.token_urlsafe(32), str)
WEB_SESSION_TIMEOUT = get_env_or_default("WEB_SESSION_TIMEOUT", 3600, int)
WEB_RATE_LIMIT = get_env_or_default("WEB_RATE_LIMIT", 100, int)
WEB_RATE_WINDOW = get_env_or_default("WEB_RATE_WINDOW", 60, int)

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

# ===================== التشفير المعتمد على كلمة المرور =====================
def derive_key_from_password(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key

def get_encryption_key() -> bytes:
    # محاولة استرجاع المفتاح من keyring أولاً
    if KEYRING_AVAILABLE:
        try:
            key = keyring.get_password("relax_bot", "db_key")
            if key:
                return base64.urlsafe_b64decode(key)
        except Exception as e:
            logger.warning(f"فشل استرجاع المفتاح من keyring: {e}")

    # ثم محاولة قراءة من ملف مشفر
    key_file = DATA_PATH / ".db_key"
    salt_file = DATA_PATH / ".db_salt"

    if key_file.exists() and salt_file.exists():
        try:
            with open(key_file, 'rb') as f:
                key = f.read()
            if len(key) == 44:  # Fernet key length
                return key
        except Exception as e:
            logger.warning(f"فشل قراءة مفتاح التشفير من الملف: {e}")

    password = os.getenv('DB_ENCRYPTION_PASSWORD')
    if password and len(password) >= 8:
        salt = os.urandom(16)
        key = derive_key_from_password(password, salt)
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
            with open(salt_file, 'wb') as f:
                f.write(salt)
            if KEYRING_AVAILABLE:
                try:
                    keyring.set_password("relax_bot", "db_key", base64.urlsafe_b64encode(key).decode())
                except:
                    pass
        except Exception as e:
            logger.warning(f"فشل حفظ مفتاح التشفير: {e}")
        print("✅ تم إنشاء مفتاح التشفير من متغير البيئة")
        return key

    # توليد مفتاح عشوائي كحل أخير
    if not sys.stdin.isatty():
        print("🔐 بيئة غير تفاعلية - إنشاء مفتاح عشوائي")
        key = Fernet.generate_key()
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
        except:
            pass
        return key

    # طلب كلمة مرور من المستخدم (تفاعلي)
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
    except Exception as e:
        print(f"⚠️ فشل في الحصول على كلمة المرور - استخدام مفتاح عشوائي: {e}")
        key = Fernet.generate_key()
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
        except:
            pass
        return key

ENCRYPTION_KEY = get_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

# ===================== مفتاح منفصل للنسخ الاحتياطي =====================
def get_backup_encryption_key() -> bytes:
    backup_key_file = DATA_PATH / ".backup_key"
    if backup_key_file.exists():
        try:
            with open(backup_key_file, 'rb') as f:
                return f.read()
        except Exception as e:
            logger.warning(f"فشل قراءة مفتاح النسخ الاحتياطي: {e}")

    new_key = Fernet.generate_key()
    try:
        with open(backup_key_file, 'wb') as f:
            f.write(new_key)
    except Exception as e:
        logger.warning(f"فشل حفظ مفتاح النسخ الاحتياطي: {e}")
    print("✅ تم توليد مفتاح جديد لتشفير النسخ الاحتياطية")
    return new_key

BACKUP_ENCRYPTION_KEY = get_backup_encryption_key()
BACKUP_CIPHER = Fernet(BACKUP_ENCRYPTION_KEY)

# ===================== متغيرات تشغيل الخلفية =====================
_background_tasks_started = False

# ===================== تحسينات التخزين المؤقت =====================
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

# ===================== تخزين مؤقت محسن للترجمة =====================
class TimedLRUCache:
    def __init__(self, maxsize=200, ttl=3600):
        self.cache = {}
        self.maxsize = maxsize
        self.ttl = ttl
        self._lock = asyncio.Lock()

    async def get(self, key):
        async with self._lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if time_module.time() - timestamp < self.ttl:
                    return value
                else:
                    del self.cache[key]
            return None

    async def set(self, key, value):
        async with self._lock:
            if key in self.cache:
                del self.cache[key]
            self.cache[key] = (value, time_module.time())
            if len(self.cache) > self.maxsize:
                oldest = min(self.cache.keys(), key=lambda k: self.cache[k][1])
                del self.cache[oldest]

    async def clear(self):
        async with self._lock:
            self.cache.clear()

_translation_cache = TimedLRUCache(maxsize=500, ttl=3600)

# ===================== متغيرات NSFW =====================
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

# جلسة aiohttp عالمية لإعادة الاستخدام
_http_session = None
_http_session_lock = asyncio.Lock()

async def get_http_session():
    global _http_session
    async with _http_session_lock:
        if _http_session is None or _http_session.closed:
            _http_session = aiohttp.ClientSession()
        return _http_session

# ===================== الثوابت =====================
MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 20 * 1024 * 1024))
MAX_CHANNELS_PER_CYCLE = int(os.getenv('MAX_CHANNELS_PER_CYCLE', '20'))
PUBLISH_RETRY_DELAY = 300
MAX_POSTS_PER_SESSION = 50
MAX_UNPUBLISHED_POSTS = 1000
DB_TIMEOUT = 30
MAX_CONNECTIONS = 20
SESSION_TIMEOUT_SECONDS = 300

# ===================== معرف المستخدم المخفي (Anonymous Admin) =====================
ANONYMOUS_ADMIN_ID = int(os.getenv("ANONYMOUS_ADMIN_ID", "1087968824"))

# ===================== تحسينات اللغة =====================
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

# ===================== تحميل الردود التلقائية من ملف =====================
ALL_REPLIES = {}

def load_replies_from_file() -> Dict[str, Union[str, List[str]]]:
    """تحميل الردود التلقائية من ملف JSON"""
    global ALL_REPLIES  # ✅ تم التصحيح: إضافة global
    
    # الملفات الممكنة
    possible_files = [
        REPLIES_FILE,
        BASE_PATH / "data" / "replies.json",
        Path.home() / ".bot_replies" / "replies.json",
        DATA_PATH / "replies.json",
    ]
    
    for file_path in possible_files:
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    ALL_REPLIES = json.load(f)
                    logger.info(f"✅ تم تحميل {len(ALL_REPLIES)} رد تلقائي من {file_path}")
                    return ALL_REPLIES
            except Exception as e:
                logger.warning(f"⚠️ فشل تحميل الردود من {file_path}: {e}")
    
    # إنشاء ملف افتراضي
    try:
        default_replies = {
            "مرحبا": ["مرحباً بك! 👋", "أهلاً وسهلاً! 🌸", "مرحباً! كيف يمكنني مساعدتك؟"],
            "السلام عليكم": ["وعليكم السلام ورحمة الله 🌸", "وعليكم السلام! 🤍"],
            "كيف حالك": ["بخير والحمد لله، وأنت؟ 🤍", "الحمد لله، كيف أنت؟"],
            "شكرا": ["عفواً! 🌸", "العفو، نحن في خدمتك! 🤍"],
            "مساعدة": ["📌 إليك قائمة الأوامر المتاحة:\n/start - القائمة الرئيسية\n/help - المساعدة\n/trial - تجربة مجانية"],
            "مشكلة": ["🙏 نأسف للإزعاج. يرجى كتابة مشكلتك بالتفصيل وسنحاول مساعدتك."],
            "بوت": ["🤖 أنا بوت إدارة القنوات والمجموعات، يمكنني مساعدتك في إدارة قنواتك ومجموعاتك بكل سهولة!"],
            "تحديث": ["📢 تابع قناة التحديثات لمعرفة كل جديد:\n@Reelaaaxbot"],
            "قناة": ["📡 لإضافة قناة، استخدم /start ثم اختر 'إضافة قناة'"],
            "مجموعة": ["👥 لإدارة المجموعات، استخدم /start ثم اختر 'مجموعاتي'"],
            "اشتراك": ["💎 للاشتراك، استخدم /subscribe أو اضغط على زر الاشتراك في القائمة الرئيسية"],
            "تجربة": ["🎁 للتجربة المجانية، استخدم /trial أو اضغط على زر التجربة المجانية"],
            "تذكير": ["⏰ لإعدادات التذكيرات، استخدم /start ثم اختر 'إعدادات التذكيرات'"],
            "ترجمة": ["🌐 لإعدادات الترجمة، استخدم /start ثم اختر 'إعدادات الترجمة'"],
            "إحالات": ["🔗 للإحالات، استخدم /start ثم اختر 'الإحالات'"],
            "رتبة": ["📊 لعرض رتبتك، استخدم /rank"],
            "مسابقة": ["🏆 للمسابقات، استخدم /contests"],
            "قوانين": ["📋 لعرض قوانين المجموعة، استخدم /rules"],
            "مطور": ["👨‍💻 المطور: @RelaxMgr"],
            "دعم": ["📞 للدعم، استخدم /support"],
            "ارقام": ["🔢 للأرقام، استخدم /stats لعرض الإحصائيات"],
            "احصائيات": ["📊 للإحصائيات، استخدم /stats أو اضغط على زر الإحصائيات"],
            "منشور": ["📝 لإضافة منشورات، استخدم /start ثم اختر 'إضافة 15 منشور'"],
            "نشر": ["📤 للنشر، استخدم /start ثم اختر 'نشر واحد' أو 'نشر الكل'"],
            "قفل": ["🔒 لقفل المجموعة، استخدم /lock"],
            "فتح": ["🔓 لفتح المجموعة، استخدم /unlock"],
            "حظر": ["🛑 لحظر مستخدم، استخدم /ban"],
            "كتم": ["🔇 لكتم مستخدم، استخدم /mute"],
            "تحذير": ["⚠️ لتحذير مستخدم، استخدم /warn"],
            "طرد": ["👢 لطرد مستخدم، استخدم /kick"],
            "تثبيت": ["📌 لتثبيت رسالة، استخدم /pin"],
            "جدولة": ["⏰ لجدولة منشور، استخدم /schedule"],
            "لوحة": ["🔧 للوحة التحكم، استخدم /panel"],
            "امن": ["🔐 لإعدادات الأمان، استخدم /security"],
            "sync": ["🔄 لمزامنة المجموعة، استخدم /syncgroup"],
            "مالك": ["👑 لتسجيل نفسك كمالك مخفي، استخدم /register_hidden_owner"],
            "مشرف": ["👑 لإضافة مشرف مخفي، استخدم /add_hidden_admin"],
            "نسخ": ["💾 للنسخ الاحتياطي، استخدم /admin_panel ثم اختر 'نسخة احتياطية'"],
            "استعادة": ["🔄 لاستعادة نسخة، استخدم /admin_panel ثم اختر 'استعادة نسخة'"],
            "تذاكر": ["📋 لتذاكر الدعم، استخدم /support"],
            "نظام": ["⚙️ لعرض حالة النظام، استخدم /admin_panel ثم اختر 'مقاييس الأداء'"],
        }
        
        with open(REPLIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_replies, f, ensure_ascii=False, indent=2)
        
        ALL_REPLIES = default_replies
        logger.info(f"✅ تم إنشاء ملف الردود الافتراضي: {REPLIES_FILE}")
        return ALL_REPLIES
    except Exception as e:
        logger.error(f"❌ فشل إنشاء ملف الردود: {e}")
        # ردود احتياطية في الذاكرة
        ALL_REPLIES = {
            "مرحبا": "مرحباً بك! 👋",
            "السلام عليكم": "وعليكم السلام 🌸",
            "شكرا": "عفواً! 🤍",
            "مساعدة": "استخدم /help للمساعدة",
        }
        return ALL_REPLIES

def get_reply_for_keyword(text: str, chat_id: Optional[int] = None) -> Optional[str]:
    """الحصول على رد مناسب للنص المدخل"""
    if not text:
        return None
    
    text_lower = text.lower().strip()
    
    # البحث المباشر عن الكلمة المفتاحية
    for key, value in ALL_REPLIES.items():
        if key in text_lower:
            if isinstance(value, list):
                return random.choice(value)
            return value
    
    # البحث باستخدام regex للكلمات المتشابهة
    for key, value in ALL_REPLIES.items():
        if re.search(r'\b' + re.escape(key) + r'\b', text_lower, re.IGNORECASE):
            if isinstance(value, list):
                return random.choice(value)
            return value
    
    return None

def reload_replies_from_file() -> bool:
    """إعادة تحميل الردود من الملف"""
    try:
        load_replies_from_file()
        return True
    except Exception as e:
        logger.error(f"فشل إعادة تحميل الردود: {e}")
        return False

# تحميل الردود عند بدء التشغيل
load_replies_from_file()

# ===================== استيراد الكلمات المحظورة من ملف =====================
BANNED_PATTERNS = []
_BANNED_PATTERNS_LOCK = asyncio.Lock()

def load_banned_words_from_file(file_paths: list) -> List[str]:
    """تحميل الكلمات المحظورة من أول ملف موجود في قائمة المسارات"""
    for file_path in file_paths:
        if file_path.exists():
            print(f"✅ تم العثور على ملف الكلمات المحظورة: {file_path}")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    words = []
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        word = line.lower()
                        if len(word) >= 2:
                            words.append(word)
                    print(f"✅ تم تحميل {len(words)} كلمة محظورة من {file_path}")
                    return words
            except Exception as e:
                print(f"❌ فشل تحميل {file_path}: {e}")
                continue

    # إذا لم يوجد أي ملف، أنشئ ملفاً افتراضياً في المسار الأول
    default_path = file_paths[0]
    print(f"⚠️ لم يتم العثور على ملف الكلمات المحظورة، سيتم إنشاؤه في {default_path}")
    try:
        # أنشئ المجلد إذا لم يكن موجوداً
        default_path.parent.mkdir(parents=True, exist_ok=True)
        with open(default_path, 'w', encoding='utf-8') as f:
            f.write("# قائمة الكلمات المحظورة - كل كلمة في سطر منفصل\n")
            f.write("# ابدأ السطر بـ # للتعليق\n")
            f.write("# استخدم * للتعبيرات النمطية (مثل: سكس.*\n")
            f.write("\n")
            f.write("بورن\nسكس\nجنس\nعري\nخمر\nخمور\nمخدرات\nحشيش\nكحول\nدعارة\n")
        print(f"✅ تم إنشاء ملف {default_path} مع كلمات افتراضية")
        return ["بورن", "سكس", "جنس", "عري", "خمر", "خمور", "مخدرات", "حشيش", "كحول", "دعارة"]
    except Exception as e:
        print(f"❌ فشل إنشاء الملف الافتراضي: {e}")
        return []

async def rebuild_banned_patterns():
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

def import_banned_words_from_file(conn, words: List[str], added_by: int = 1) -> int:
    if not words:
        return 0
    imported = 0
    try:
        for word in words:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?, ?, ?, ?)",
                    (word, -1, added_by, utc_now_iso())
                )
                imported += 1
            except:
                continue
        conn.commit()
        print(f"✅ تم استيراد {imported} كلمة محظورة إلى قاعدة البيانات")
    except Exception as e:
        print(f"❌ فشل استيراد الكلمات المحظورة: {e}")
    return imported

# ===================== نظام كشف NSFW المحسن =====================
async def check_nsfw_cached(image_bytes: bytes, cache_key: str = None) -> dict:
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
    try:
        if not SIGHTENGINE_API_USER or not SIGHTENGINE_API_SECRET:
            return {"nsfw": False, "score": 0, "error": "API غير مفعل"}

        if not PIL_AVAILABLE:
            return {"nsfw": False, "score": 0, "error": "مكتبة PIL غير مثبتة"}

        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((800, 800))
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=80)
        compressed = buffer.getvalue()

        image_b64 = base64.b64encode(compressed).decode('utf-8')

        # ✅ استخدام POST بدلاً من GET
        session = await get_http_session()
        url = "https://api.sightengine.com/1.0/check.json"
        data = {
            "models": "nudity-2.0,wad",
            "api_user": SIGHTENGINE_API_USER,
            "api_secret": SIGHTENGINE_API_SECRET,
            "image": image_b64
        }

        async with session.post(url, data=data, timeout=10) as resp:
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
    if not PIL_AVAILABLE or not CV2_AVAILABLE:
        return {"nsfw": False, "score": 0, "error": "مكتبات معالجة الفيديو غير مثبتة"}

    try:
        if not video_bytes:
            return {"nsfw": False, "score": 0, "error": "فيديو فارغ"}

        import cv2
        # numpy مستورد بالفعل في الأعلى
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

# ===================== نظام اللغات من ملفات منفصلة =====================
_lang_data = {}
_lang_cache_time = {}
LANG_CACHE_TTL = 300
_lang_lock = asyncio.Lock()
user_language = {}
_user_language_lock = asyncio.Lock()

# ✅ تم إضافة تخزين دائم للغة في قاعدة البيانات (سيتم تنفيذه في دوال لاحقة)

def load_all_languages():
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
            "help": "❓ **Help**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 **Available Commands:**\n/start - Main Menu\n/trial - Free Trial\n/subscribe - Subscribe\n/syncgroup - Activate Group\n/security - Security Settings\n/register_hidden_owner - Register Hidden Owner\n/add_hidden_admin - Add Hidden Admin\n/remove_hidden_admin - Remove Hidden Admin\n/list_hidden_admins - List Hidden Admins\n/rank - Your Rank\n/top - Top 10\n/stats - Channel Stats\n/lock - Lock Group\n/unlock - Unlock Group\n/schedule - Schedule Post\n/panel - Control Panel\n/language - Change Language\n/support - Support Center\n/help - This Help\n/developer - Developer\n/updates - Updates\n/contests - Contests\n/create_contest - Create Contest\n/declare_winner - Declare Winner\n/set_rules - Set Group Rules\n/rules - View Group Rules",
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
    lang = user_language.get(user_id, 'ar')
    texts = _lang_data.get(lang, {})
    
    if key not in texts:
        en_texts = _lang_data.get('en', {})
        if key in en_texts:
            return en_texts[key]
    
    return texts.get(key, key)

async def set_user_language(user_id: int, lang: str):
    async with _user_language_lock:
        user_language[user_id] = lang
    # ✅ حفظ في قاعدة البيانات
    async def _save(conn):
        await conn.execute(
            "INSERT OR REPLACE INTO user_settings (user_id, language) VALUES (?, ?)",
            (user_id, lang)
        )
        await conn.commit()
    await execute_db(_save)

# ===================== دوال التنظيف والتهرب =====================
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
    
    if not BLEACH_AVAILABLE:
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'[^\w\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\u200c\u200d@._\-+:#]', ' ', text)
        text = ' '.join(text.split())
        if len(text) > max_length:
            text = text[:max_length]
        return text
    
    try:
        if allow_tags is None:
            allow_tags = ['b', 'i', 'u', 's', 'a', 'code', 'pre', 'strong', 'em']
        # ✅ تم حذف الوسيط غير المدعوم styles
        cleaned = bleach.clean(
            text,
            tags=allow_tags,
            attributes={'a': ['href', 'title']},
            strip=True
        )
    except:
        cleaned = text
    
    if len(cleaned) > max_length:
        # ✅ تقطيع آمن يحافظ على سلامة النص
        cleaned = cleaned[:max_length]
    return cleaned

def encode_callback_data(data: str) -> str:
    return urllib.parse.quote(data, safe='')

def decode_callback_data(data: str) -> str:
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

# ===================== نظام سجلات متقدم =====================
class AdvancedLogger:
    def __init__(self):
        self.loggers = {}
        self._setup_loggers()

    def _setup_loggers(self):
        error_logger = logging.getLogger('error_logger')
        error_logger.setLevel(logging.ERROR)
        error_handler = logging.FileHandler(ERROR_LOG, encoding='utf-8')
        error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        error_logger.addHandler(error_handler)
        self.loggers['error'] = error_logger

        access_logger = logging.getLogger('access_logger')
        access_logger.setLevel(logging.INFO)
        access_handler = logging.FileHandler(ACCESS_LOG, encoding='utf-8')
        access_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        access_logger.addHandler(access_handler)
        self.loggers['access'] = access_logger

        security_logger = logging.getLogger('security_logger')
        security_logger.setLevel(logging.WARNING)
        security_handler = logging.FileHandler(SECURITY_LOG, encoding='utf-8')
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

# ===================== نظام إدارة الأخطاء =====================
class ErrorHandler:
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.errors = defaultdict(int)
        self._lock = asyncio.Lock()

    async def handle_async(self, func: Callable, *args, **kwargs) -> Any:
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

# ===================== نظام إدارة الذاكرة =====================
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
            _security_cache_time.clear()
        await _translation_cache.clear()
        NSFW_CACHE.clear()
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
            advanced_logger.log_access(0, "MEMORY_OPTIMIZED", {"timestamp": utc_now_iso()})
        except Exception as e:
            advanced_logger.log_error("فشل حلقة تحسين الذاكرة", e)
            # ✅ لا تخرج من الحلقة، استمر
            continue

# ===================== نظام الإشعارات المتقدم =====================
class NotificationSystem:
    def __init__(self):
        self.pending_notifications = []
        self._lock = asyncio.Lock()
        self._scheduled_tasks = []

    async def send_notification(self, bot, user_id: int, text: str, parse_mode: str = "MarkdownV2", reply_markup=None):
        try:
            await safe_send_markdown(bot, user_id, text, reply_markup)
            advanced_logger.log_access(user_id, "NOTIFICATION_SENT", {"text": text[:50]})
            return True
        except Exception as e:
            advanced_logger.log_error("فشل إرسال الإشعار", e, {"user_id": user_id})
            return False

    async def send_bulk_notification(self, bot, user_ids: List[int], text: str, parse_mode: str = "MarkdownV2", delay: float = 0.5):
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
        async def delayed():
            await asyncio.sleep(delay_seconds)
            await self.send_notification(bot, user_id, text)
        task = asyncio.create_task(delayed())
        self._scheduled_tasks.append(task)
        task.add_done_callback(lambda t: self._scheduled_tasks.remove(t) if t in self._scheduled_tasks else None)
        return task

notification_system = NotificationSystem()

# ===================== دوال الإرسال الآمنة =====================
async def safe_send_markdown(bot, chat_id: int, text: str, reply_markup=None, **kwargs):
    if not text:
        return None
    clean_text = sanitize_text(text)
    MAX_LEN = 4096
    
    # محاولة الإرسال بـ MarkdownV2
    try:
        escaped = escape_markdown_v2(clean_text)
        escaped = re.sub(r'\\{2,}', '\\\\', escaped)
        if len(escaped) > MAX_LEN:
            # ✅ تقطيع آمن يحافظ على سلامة Markdown
            # نبحث عن آخر فاصلة أو نقطة أو مسافة قبل MAX_LEN
            cut_point = MAX_LEN - 3
            # نجد آخر حرف آمن للتقطيع
            while cut_point > 0 and escaped[cut_point - 1] not in (' ', '\n', '.', '،', ',', '?', '!'):
                cut_point -= 1
            if cut_point <= 0:
                cut_point = MAX_LEN - 3
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
            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', clean_text)
            if len(plain) > MAX_LEN:
                plain = plain[:MAX_LEN-3] + "..."
            return await bot.send_message(
                chat_id=chat_id,
                text=plain,
                reply_markup=reply_markup,
                **kwargs
            )
    except Exception as e:
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
            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', clean_text)
            if len(plain) > MAX_LEN:
                plain = plain[:MAX_LEN-3] + "..."
            return await bot.send_message(
                chat_id=chat_id,
                text=plain,
                reply_markup=reply_markup,
                **kwargs
            )

async def safe_edit_markdown(query, text: str, reply_markup=None, **kwargs):
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
            while cut_point > 0 and escaped[cut_point - 1] not in (' ', '\n', '.', '،', ',', '?', '!'):
                cut_point -= 1
            if cut_point <= 0:
                cut_point = MAX_LEN - 3
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

# ===================== التحقق من التشغيل الواحد =====================
# ✅ تم استبدال socket.AF_UNIX بآلية تعمل على جميع المنصات
def check_single_instance():
    """التحقق من تشغيل نسخة واحدة فقط من البوت باستخدام ملف lock"""
    lock_file = TEMP_PATH / "bot.lock"
    try:
        # محاولة فتح الملف للكتابة (حصري)
        if platform.system() == 'Windows':
            # على Windows نستخدم طريقة مختلفة
            import msvcrt
            lock_fd = open(lock_file, 'w')
            try:
                msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
            except:
                return None
            return lock_fd
        else:
            # على Unix نستخدم fcntl
            import fcntl
            lock_fd = open(lock_file, 'w')
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except:
                return None
            return lock_fd
    except Exception as e:
        print(f"⚠️ لا يمكن التحقق من التشغيل الواحد: {e}")
        return None

#lock_fd = check_single_instance()
#if lock_fd is None:
 #   print("⚠️ بوت آخر يعمل بالفعل! جاري الخروج...")
  #  sys.exit(1)

# ===================== دوال الوقت =====================
def utc_now():
    return datetime.now(timezone.utc)

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
    # إذا كان التاريخ يحتوي على معلومات المنطقة، نحولها إلى UTC
    if hasattr(mecca_dt, 'tzinfo') and mecca_dt.tzinfo is not None:
        return mecca_dt.astimezone(timezone.utc)
    # وإلا نطرح 3 ساعات
    return mecca_dt - timedelta(hours=3)

def utc_to_mecca(utc_dt):
    if utc_dt is None:
        return None
    if hasattr(utc_dt, 'tzinfo') and utc_dt.tzinfo is not None:
        return utc_dt.astimezone(timezone(timedelta(hours=3)))
    return utc_dt + timedelta(hours=3)

# ===================== نظام الأمان والتدقيق =====================
class SecurityAudit:
    async def log(self, event_type: str, user_id: int, details: dict, severity: str = "INFO"):
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
                from telegram import Bot
                bot = Bot(token=TOKEN)
                await bot.send_message(
                    chat_id=log_channel,
                    text=f"🔐 **تقرير أمني**\n\n📌 الحدث: {event_type}\n👤 المستخدم: `{user_id}`\n📊 التفاصيل: {json.dumps(details, default=str)[:200]}\n⚠️ الخطورة: {severity}\n🕐 الوقت: {mecca_now().strftime('%Y-%m-%d %H:%M:%S')}",
                    parse_mode="MarkdownV2"
                )
        except Exception as e:
            logger.warning(f"فشل إرسال التقرير إلى القناة: {e}")

        return True

security_audit = SecurityAudit()

# ===================== نظام كشف النشاط المشبوه =====================
class AnomalyDetector:
    def __init__(self):
        self.user_activity = defaultdict(list)
        self.lock = asyncio.Lock()

    async def detect_anomaly(self, user_id: int, action: str) -> bool:
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

# ===================== Pool اتصالات قاعدة البيانات =====================
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
                await self._pool.execute("PRAGMA max_page_count=1000000")
                await self._pool.execute("PRAGMA secure_delete=ON")
                self._pool.row_factory = aiosqlite.Row

    async def get_connection(self):
        if self._pool is None:
            await self.initialize()
        return self._pool

    async def execute(self, query: str, params: tuple = None):
        conn = await self.get_connection()
        try:
            async with conn.execute(query, params or ()) as cursor:
                return await cursor.fetchall()
        except sqlite3.IntegrityError as e:
            logger.warning(f"خطأ في تكامل البيانات: {e}")
            raise
        except Exception as e:
            logger.error(f"خطأ في تنفيذ الاستعلام: {e}")
            raise

    async def execute_many(self, queries: List[Tuple[str, tuple]]):
        conn = await self.get_connection()
        async with conn:
            for query, params in queries:
                try:
                    await conn.execute(query, params)
                except sqlite3.IntegrityError as e:
                    logger.warning(f"تجاهل خطأ تكامل البيانات: {e}")
                    continue
            await conn.commit()

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None

db_pool = DatabasePool(max_connections=MAX_CONNECTIONS)

# ✅ إصلاح execute_db لإغلاق الاتصال بشكل صحيح
async def execute_db(func: Callable):
    conn = await db_pool.get_connection()
    original_factory = conn.row_factory
    try:
        return await func(conn)
    finally:
        conn.row_factory = original_factory
        # لا نغلق الاتصال لأنه من التجمع، لكننا نعيده (يتم إدارته تلقائياً)

# ===================== دوال قاعدة البيانات الأساسية (مساعدات) =====================
async def db_get_log_channel_id() -> Optional[int]:
    try:
        async def _get(conn):
            cur = await conn.execute("SELECT value FROM bot_settings WHERE key = 'log_channel'")
            row = await cur.fetchone()
            return int(row[0]) if row else None
        return await execute_db(_get)
    except:
        return None

async def db_get_channel_info(channel_db_id: int) -> Optional[Dict]:
    """الحصول على معلومات القناة من قاعدة البيانات"""
    try:
        async def _get(conn):
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT channel_id, channel_name FROM user_channels WHERE id = ?",
                (channel_db_id,)
            )
            return await cur.fetchone()
        result = await execute_db(_get)
        if result:
            return {
                'channel_id': result['channel_id'],
                'channel_name': result['channel_name'] or result['channel_id']
            }
        return None
    except Exception as e:
        logger.error(f"خطأ في db_get_channel_info: {e}")
        return None

async def db_get_hidden_admins(chat_id: int) -> List[Dict]:
    """الحصول على قائمة المشرفين المخفيين في مجموعة"""
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT admin_id, added_by, added_at
            FROM hidden_admins
            WHERE chat_id=?
            ORDER BY added_at DESC
        """, (chat_id,))
        rows = await cur.fetchall()
        return [{'admin_id': row['admin_id'], 'added_by': row['added_by'], 'added_at': row['added_at']} for row in rows]
    return await execute_db(_get)

async def db_is_hidden_admin(chat_id: int, user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم مشرفاً مخفياً في مجموعة"""
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_check)

async def db_is_hidden_owner(chat_id: int, user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم مالكاً مخفياً في مجموعة"""
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_check)

# ===================== نظام التخزين المؤقت باستخدام Redis =====================
class CacheManager:
    def __init__(self):
        self.redis = None
        self.use_redis = REDIS_AVAILABLE and os.getenv("REDIS_URL") is not None
        # ✅ استخدام LRUCache محلي محدود الحجم
        if CACHETOOLS_AVAILABLE:
            self.local_cache = TTLCache(maxsize=200, ttl=300)
        else:
            self.local_cache = {}
            self.local_cache_time = {}
            self.local_cache_ttl = 300
        self._lock = asyncio.Lock()

    async def init(self):
        if self.use_redis:
            try:
                self.redis = await aioredis.from_url(os.getenv("REDIS_URL"))
                await self.redis.ping()
                logger.info("✅ تم الاتصال بـ Redis")
            except Exception as e:
                logger.warning(f"⚠️ فشل الاتصال بـ Redis: {e}")
                self.use_redis = False

    async def get(self, key: str):
        if self.use_redis:
            try:
                value = await self.redis.get(key)
                if value:
                    return json.loads(value)
            except:
                pass
        # استخدام الكاش المحلي
        if CACHETOOLS_AVAILABLE:
            return self.local_cache.get(key)
        else:
            if key in self.local_cache:
                value, timestamp = self.local_cache[key]
                if time_module.time() - timestamp < self.local_cache_ttl:
                    return value
                else:
                    del self.local_cache[key]
            return None

    async def set(self, key: str, value: Any, ttl: int = 300):
        if self.use_redis:
            try:
                await self.redis.setex(key, ttl, json.dumps(value))
                return
            except:
                pass
        async with self._lock:
            if CACHETOOLS_AVAILABLE:
                self.local_cache[key] = value
            else:
                self.local_cache[key] = (value, time_module.time())

    async def delete(self, key: str):
        if self.use_redis:
            try:
                await self.redis.delete(key)
            except:
                pass
        async with self._lock:
            if CACHETOOLS_AVAILABLE:
                self.local_cache.pop(key, None)
            else:
                self.local_cache.pop(key, None)

cache_manager = CacheManager()

# ===================== دوال التشفير المحسنة =====================
def encrypt_file_stream(src: Path, dst: Path, cipher: Fernet, chunk_size: int = 64*1024):
    # ✅ طريقة التشفير التدفقي الصحيحة باستخدام Fernet غير ممكنة مباشرة
    # نستخدم التشفير الكامل للملفات الصغيرة أو التدفق باستخدام AES-GCM
    # لكن للتبسيط، سنقوم بتشفير الملف كاملًا (للملفات حتى 10 ميجا)
    if src.stat().st_size > 10 * 1024 * 1024:
        # للملفات الكبيرة، نستخدم طريقة بديلة (AES-GCM) ولكننا نكتفي بـ Fernet الكامل هنا
        pass
    with open(src, 'rb') as f_in:
        data = f_in.read()
    encrypted = cipher.encrypt(data)
    with open(dst, 'wb') as f_out:
        f_out.write(encrypted)

def decrypt_file_stream(src: Path, dst: Path, cipher: Fernet, chunk_size: int = 64*1024):
    with open(src, 'rb') as f_in:
        data = f_in.read()
    decrypted = cipher.decrypt(data)
    with open(dst, 'wb') as f_out:
        f_out.write(decrypted)

def encrypt_db_backup() -> Path:
    if not DB_ENCRYPTION:
        return DB_PATH
    cipher = Fernet(ENCRYPTION_KEY)
    encrypted_path = DB_PATH.with_suffix('.enc')
    encrypt_file_stream(DB_PATH, encrypted_path, cipher)
    return encrypted_path

def decrypt_db_backup(encrypted_path: Path) -> bytes:
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
    try:
        import zstandard
        ZSTD_COMPRESSOR = zstandard.ZstdCompressor(level=3)
        return ZSTD_COMPRESSOR.compress(data)
    except:
        return gzip.compress(data)

def decompress_backup(data: bytes) -> bytes:
    try:
        import zstandard
        ZSTD_DECOMPRESSOR = zstandard.ZstdDecompressor()
        return ZSTD_DECOMPRESSOR.decompress(data)
    except:
        return gzip.decompress(data)

# ===================== نظام Backoff ذكي مع Jitter =====================
async def retry_with_jitter(func: Callable, max_retries: int = 5, base_delay: float = 1) -> Any:
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

# ===================== نظام Rate Limiting متقدم =====================
class GlobalRateLimiter:
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
            # ✅ تنظيف المفاتيح الفارغة
            if not user_requests:
                self.records.pop(key, None)
            return True

global_rate_limiter = GlobalRateLimiter()

# ===================== تعريف CallbackData =====================
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
    SECURITY_WARN_PREFIX = "security:warn:"
    SECURITY_SLOWMODE_PREFIX = "security:slow_mode:"
    SECURITY_BANNED_WORDS_MENU_PREFIX = "security:banned_words_menu:"
    SECURITY_WELCOME_PREFIX = "security:welcome_enabled:"
    SECURITY_GOODBYE_PREFIX = "security:goodbye_enabled:"
    SECURITY_MAIN = "security:main"
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
    ADMIN_AUTO_REPLY_SELECT_PREFIX = "admin_auto_reply_select:"
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
    SECURITY_ENABLE_ALL_PREFIX = "security:enable_all:"
    SECURITY_DISABLE_ALL_PREFIX = "security:disable_all:"
    SECURITY_DELETE_PENALTY_PREFIX = "security:delete_penalty:"
    PANEL_LOCK_PREFIX = "panel:lock:"
    PANEL_UNLOCK_PREFIX = "panel:unlock:"
    PANEL_CLOSE = "panel:close"
    CHECK_SUBSCRIBE = "check_subscribe"

# ===================== تعريف UserState =====================
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

# ✅ تم إضافة تخزين UserState في قاعدة البيانات (سيتم تنفيذه في دوال لاحقة)
# نهاية الجزء الأول...

# *****************************************************************************
# ** الجزء الثاني (المتبقي) - سيتم إضافته في رسالة منفصلة بسبب طول الكود **
# *****************************************************************************
# ===================== دوال قاعدة البيانات الأساسية (مصححة ومحسنة) =====================

# ثابت لأسماء الأعمدة لتجنب التكرار
class DBColumns:
    USERS = ['user_id', 'auto_publish', 'banned', 'trial_used', 'subscription_end', 
             'referral_code', 'referred_by', 'active_channel', 'auto_reply_enabled', 
             'auto_recycle', 'last_daily_reward', 'last_weekly_reward', 'language']
    POSTS = ['id', 'channel_db_id', 'text', 'media_type', 'media_file_id', 'published', 
             'fail_count', 'views_count', 'last_view_time', 'created_at']
    CHANNELS = ['id', 'user_id', 'channel_id', 'channel_name', 'banned', 'created_at']
    GROUPS = ['chat_id', 'chat_name', 'username', 'added_by', 'added_at', 'banned']

# دوال مساعدة للتحقق من صحة البيانات
def safe_parse_datetime(date_str: str) -> Optional[datetime]:
    """تحويل سلسلة تاريخ إلى datetime مع التعامل مع الأخطاء"""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S']:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

def validate_media_file_id(file_id: str) -> Optional[str]:
    """التحقق من صحة معرف الملف وتقليصه إذا لزم الأمر"""
    if not file_id:
        return None
    return file_id[:255] if len(file_id) > 255 else file_id

def parse_days_of_week_safe(days_str: str) -> List[int]:
    """تحويل سلسلة أيام الأسبوع إلى قائمة"""
    if not days_str:
        return []
    try:
        result = json.loads(days_str)
        if isinstance(result, list):
            return [int(d) for d in result if isinstance(d, (int, str)) and str(d).isdigit()]
        return []
    except:
        return []

def parse_dates_safe(dates_str: str) -> List[str]:
    """تحويل سلسلة التواريخ إلى قائمة"""
    if not dates_str:
        return []
    try:
        result = json.loads(dates_str)
        if isinstance(result, list):
            return [str(d) for d in result if d]
        return []
    except:
        return []

async def db_ensure_columns(table: str, columns: Dict[str, str]) -> None:
    """التحقق من وجود الأعمدة وإضافتها إذا لزم الأمر"""
    async def _ensure(conn):
        cur = await conn.execute(f"PRAGMA table_info({table})")
        existing = [row[1] for row in await cur.fetchall()]
        for col_name, col_type in columns.items():
            if col_name not in existing:
                await conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
        await conn.commit()
    await execute_db(_ensure)

async def db_upsert(table: str, data: Dict, conflict_column: str) -> None:
    """إدراج أو تحديث صف في قاعدة البيانات"""
    columns = ', '.join(data.keys())
    placeholders = ', '.join(['?' for _ in data])
    updates = ', '.join([f"{col}=excluded.{col}" for col in data.keys()])
    values = list(data.values())
    
    async def _upsert(conn):
        await conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict_column}) DO UPDATE SET {updates}",
            values
        )
        await conn.commit()
    await execute_db(_upsert)

async def db_row_exists(conn, table: str, where: str, params: tuple) -> bool:
    """التحقق من وجود صف في قاعدة البيانات"""
    cur = await conn.execute(f"SELECT 1 FROM {table} WHERE {where}", params)
    return await cur.fetchone() is not None

# ===================== دوال المستخدمين الأساسية (مصححة) =====================

async def db_register_user(user_id: int) -> bool:
    async def _register(conn):
        if await db_row_exists(conn, "users", "user_id=?", (user_id,)):
            return False
        await conn.execute("""
            INSERT INTO users (
                user_id, auto_publish, banned, trial_used, auto_reply_enabled, 
                auto_recycle, subscription_end, language
            ) VALUES (?, 1, 0, 0, 1, 1, NULL, 'ar')
        """, (user_id,))
        await conn.commit()
        return True
    return await execute_db(_register)

async def db_get_all_users(limit: int = 1000):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT user_id, banned FROM users ORDER BY user_id LIMIT ?", (limit,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_update_user_cache(user_id: int, username: str, first_name: str):
    async def _update(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO users_cache (user_id, username, first_name, last_updated) 
            VALUES (?, ?, ?, ?)
        """, (user_id, username or "", first_name or "", utc_now_iso()))
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
        await conn.execute("""
            UPDATE users SET trial_used=1, subscription_end=? 
            WHERE user_id=?
        """, (end_date, user_id))
        await conn.commit()
        return 30
    return await execute_db(_activate)

async def db_activate_subscription(user_id: int, days: int):
    async def _activate(conn):
        if days <= 0:
            return
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            current_end = safe_parse_datetime(row[0])
            if current_end and current_end > utc_now():
                new_end = current_end + timedelta(days=days)
            else:
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
            end_date = safe_parse_datetime(row[0])
            return end_date is not None and end_date > utc_now()
        return False
    return await execute_db(_check)

async def db_get_subscription_days_left(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            end_date = safe_parse_datetime(row[0])
            if end_date:
                days = (end_date - utc_now()).days
                return max(0, days)
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

# ===================== دوال قنوات المستخدمين (مصححة) =====================

async def db_add_channel(user_id: int, channel_id: str, channel_name: str) -> Optional[int]:
    async def _add(conn):
        if await db_row_exists(conn, "user_channels", "user_id=? AND channel_id=?", (user_id, channel_id)):
            return None
        cur = await conn.execute("""
            INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) 
            VALUES (?, ?, ?, ?) RETURNING id
        """, (user_id, channel_id, channel_name, utc_now_iso()))
        row = await cur.fetchone()
        await conn.commit()
        return row[0] if row else None
    return await execute_db(_add)

async def db_get_channels(user_id: int) -> List[Dict]:
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        try:
            cur = await conn.execute("""
                SELECT id, channel_id, channel_name, banned 
                FROM user_channels 
                WHERE user_id=? 
                ORDER BY id
            """, (user_id,))
            rows = await cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    'id': row['id'] or 0,
                    'channel_id': row['channel_id'] or "unknown",
                    'channel_name': row['channel_name'] or row['channel_id'] or "Unknown",
                    'banned': row['banned'] or 0
                })
            return result
        except Exception as e:
            logger.error(f"خطأ في جلب قنوات المستخدم {user_id}: {e}")
            return []
    return await execute_db(_get)

async def db_get_channel_info(channel_db_id: int) -> Optional[Dict]:
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT channel_id, channel_name FROM user_channels WHERE id=?", (channel_db_id,))
        row = await cur.fetchone()
        if row:
            return {
                'channel_id': row['channel_id'] or "unknown",
                'channel_name': row['channel_name'] or row['channel_id'] or "Unknown"
            }
        return None
    return await execute_db(_get)

async def db_delete_channel_by_id(user_id: int, channel_db_id: int) -> bool:
    async def _delete(conn):
        await conn.execute("DELETE FROM user_channels WHERE id=? AND user_id=?", (channel_db_id, user_id))
        await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (channel_db_id,))
        await conn.execute("DELETE FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
        return True
    return await execute_db(_delete)

async def db_get_active_channel(user_id: int) -> Optional[int]:
    async def _get(conn):
        cur = await conn.execute("SELECT active_channel FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0] is not None:
            cur2 = await conn.execute("SELECT banned FROM user_channels WHERE id=?", (row[0],))
            row2 = await cur2.fetchone()
            if row2 and row2[0] == 0:
                return row[0]
        cur = await conn.execute("""
            SELECT id FROM user_channels 
            WHERE user_id=? AND banned=0 
            ORDER BY id LIMIT 1
        """, (user_id,))
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

async def db_get_all_user_channels_no_limit():
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT uc.user_id, uc.id, uc.channel_id, uc.channel_name, uc.banned 
            FROM user_channels uc 
            ORDER BY uc.id
        """)
        return await cur.fetchall()
    return await execute_db(_get)

async def db_all_users_channels(only_banned: bool = False, limit: int = 500):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        if only_banned:
            cur = await conn.execute("""
                SELECT user_id, id, channel_id, channel_name, banned 
                FROM user_channels 
                WHERE banned=1 
                LIMIT ?
            """, (limit,))
        else:
            cur = await conn.execute("""
                SELECT user_id, id, channel_id, channel_name, banned 
                FROM user_channels 
                LIMIT ?
            """, (limit,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_register_channel(channel_id: int, channel_name: str, added_by: int):
    async def _register(conn):
        if await db_row_exists(conn, "bot_channels", "channel_id=?", (channel_id,)):
            await conn.execute("""
                UPDATE bot_channels 
                SET channel_name=?, added_by=? 
                WHERE channel_id=?
            """, (channel_name, added_by, channel_id))
            await conn.commit()
            return False
        await conn.execute("""
            INSERT INTO bot_channels (channel_id, channel_name, added_by, added_at) 
            VALUES (?, ?, ?, ?)
        """, (channel_id, channel_name, added_by, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_register)

async def db_get_all_bot_channels(only_banned: bool = False):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        if only_banned:
            cur = await conn.execute("""
                SELECT channel_id, channel_name, added_by, added_at, banned 
                FROM bot_channels 
                WHERE banned=1 
                ORDER BY added_at DESC
            """)
        else:
            cur = await conn.execute("""
                SELECT channel_id, channel_name, added_by, added_at, banned 
                FROM bot_channels 
                ORDER BY added_at DESC
            """)
        return await cur.fetchall()
    return await execute_db(_get)

# ===================== دوال المنشورات (مصححة) =====================

async def db_save_posts(channel_db_id: int, posts: list) -> int:
    async def _save(conn):
        values = []
        for text_content, media_type, media_file_id in posts:
            clean_text = sanitize_text(text_content)[:4096] if text_content else ""
            safe_media_id = validate_media_file_id(media_file_id)
            values.append((channel_db_id, clean_text, media_type or "text", safe_media_id, utc_now_iso()))
        
        if not values:
            return 0
            
        await conn.executemany("""
            INSERT INTO posts (channel_db_id, text, media_type, media_file_id, created_at) 
            VALUES (?, ?, ?, ?, ?)
        """, values)
        await conn.commit()
        return len(values)
    return await execute_db(_save)

async def db_get_next_post(channel_db_id: int):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT id, text, media_type, media_file_id 
            FROM posts 
            WHERE channel_db_id=? AND published=0 AND (fail_count IS NULL OR fail_count < 3) 
            ORDER BY id LIMIT 1
        """, (channel_db_id,))
        row = await cur.fetchone()
        if row:
            return {
                'id': row['id'], 
                'text': row['text'], 
                'media_type': row['media_type'], 
                'media_file_id': row['media_file_id']
            }
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
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT id, text, media_type 
            FROM posts 
            WHERE channel_db_id=? AND published=0 
            ORDER BY id LIMIT ?
        """, (channel_db_id, limit))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_delete_single_post(post_id: int, user_id: int, channel_db_id: int) -> bool:
    async def _delete(conn):
        if not await db_row_exists(conn, "user_channels", "id=? AND user_id=? AND banned=0", (channel_db_id, user_id)):
            return False
        if not await db_row_exists(conn, "posts", "id=? AND channel_db_id=?", (post_id, channel_db_id)):
            return False
        await conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
        await conn.commit()
        return True
    return await execute_db(_delete)

async def db_get_user_unpublished_posts(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("""
            SELECT COUNT(*) 
            FROM posts p 
            JOIN user_channels uc ON p.channel_db_id=uc.id 
            WHERE uc.user_id=? AND p.published=0 AND uc.banned=0
        """, (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_get_user_total_posts(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("""
            SELECT COUNT(*) 
            FROM posts p 
            JOIN user_channels uc ON p.channel_db_id=uc.id 
            WHERE uc.user_id=? AND uc.banned=0
        """, (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_unpublished_count(channel_db_id: int) -> int:
    async def _count(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=0", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_count)

async def db_update_post_views(post_id: int, views_count: int = None):
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
    await execute_db(_update_views)

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

# ===================== دوال المجموعات المحسنة (مصححة) =====================

async def db_register_group(chat_id: int, chat_name: str, added_by: int, username: str = None) -> bool:
    async def _register(conn):
        if await db_row_exists(conn, "bot_groups", "chat_id=?", (chat_id,)):
            await conn.execute("""
                UPDATE bot_groups 
                SET chat_name=?, username=?, added_by=? 
                WHERE chat_id=?
            """, (chat_name, username, added_by, chat_id))
            await conn.commit()
            return False
        await conn.execute("""
            INSERT INTO bot_groups (chat_id, chat_name, username, added_by, added_at) 
            VALUES (?, ?, ?, ?, ?)
        """, (chat_id, chat_name, username, added_by, utc_now_iso()))
        await conn.execute("""
            INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) 
            VALUES (?, ?)
        """, (added_by, chat_id))
        await conn.commit()
        return True
    return await execute_db(_register)

async def db_get_user_groups(user_id: int) -> List[Dict]:
    """الحصول على قائمة المجموعات التي يمتلك فيها المستخدم صلاحيات (مشرف، مالك مخفي، مشرف مخفي)"""
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        try:
            # ✅ تم إصلاح الاستدعاء الذاتي - استخدام استعلام مباشر
            # استعلام واحد يجمع جميع المجموعات التي للمستخدم فيها صلاحية
            cur = await conn.execute("""
                SELECT DISTINCT 
                    bg.chat_id, 
                    bg.chat_name, 
                    bg.username, 
                    bg.banned
                FROM bot_groups bg
                WHERE bg.chat_id IN (
                    SELECT chat_id FROM group_admins WHERE user_id = ?
                    UNION
                    SELECT chat_id FROM hidden_owner_groups WHERE owner_id = ?
                    UNION
                    SELECT chat_id FROM hidden_admins WHERE admin_id = ?
                )
                ORDER BY bg.chat_name
            """, (user_id, user_id, user_id))
            rows = await cur.fetchall()
            result = []
            for row in rows:
                result.append({
                    'chat_id': row['chat_id'],
                    'chat_name': row['chat_name'],
                    'username': row['username'],
                    'banned': row['banned']
                })
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
        except Exception as e:
            logger.error(f"خطأ في حساب عدد مجموعات المستخدم: {e}")
            return 0
    return await execute_db(_get)

async def db_get_all_groups(only_banned: bool = False, limit: int = 500):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        if only_banned:
            cur = await conn.execute("""
                SELECT chat_id, chat_name, username, added_by, added_at, banned 
                FROM bot_groups 
                WHERE banned=1 
                ORDER BY added_at DESC LIMIT ?
            """, (limit,))
        else:
            cur = await conn.execute("""
                SELECT chat_id, chat_name, username, added_by, added_at, banned 
                FROM bot_groups 
                ORDER BY added_at DESC LIMIT ?
            """, (limit,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_set_chat_lock(chat_id: int, locked: bool, locked_by: int = None):
    async def _set(conn):
        if locked:
            await conn.execute("""
                INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) 
                VALUES (?, 1, ?, ?)
            """, (chat_id, utc_now_iso(), locked_by))
        else:
            await conn.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await conn.commit()
    return await execute_db(_set)

async def is_chat_locked(chat_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT locked FROM chat_locks WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_check)

# ===================== دوال الصلاحيات العالمية (مصححة) =====================

async def db_is_real_admin(chat_id: int, user_id: int) -> bool:
    async def _check(conn):
        return await db_row_exists(conn, "group_admins", "chat_id=? AND user_id=?", (chat_id, user_id))
    return await execute_db(_check)

async def db_is_hidden_owner(chat_id: int, user_id: int) -> bool:
    async def _check(conn):
        return await db_row_exists(conn, "hidden_owner_groups", "chat_id=? AND owner_id=?", (chat_id, user_id))
    return await execute_db(_check)

async def db_is_hidden_admin(chat_id: int, user_id: int) -> bool:
    async def _check(conn):
        return await db_row_exists(conn, "hidden_admins", "chat_id=? AND admin_id=?", (chat_id, user_id))
    return await execute_db(_check)

async def db_register_hidden_owner_group(chat_id: int, owner_id: int):
    async def _register(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden)
            VALUES (?, ?, 1)
        """, (chat_id, owner_id))
        await conn.execute("""
            INSERT OR IGNORE INTO user_groups_link (user_id, chat_id)
            VALUES (?, ?)
        """, (owner_id, chat_id))
        await conn.commit()
    return await execute_db(_register)

async def db_add_hidden_admin(chat_id: int, admin_id: int, added_by: int) -> bool:
    async def _add(conn):
        try:
            if await db_row_exists(conn, "hidden_admins", "chat_id=? AND admin_id=?", (chat_id, admin_id)):
                return False
            await conn.execute("""
                INSERT INTO hidden_admins (chat_id, admin_id, added_by, added_at)
                VALUES (?, ?, ?, ?)
            """, (chat_id, admin_id, added_by, utc_now_iso()))
            await conn.execute("""
                INSERT OR IGNORE INTO user_groups_link (user_id, chat_id)
                VALUES (?, ?)
            """, (admin_id, chat_id))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في إضافة مشرف مخفي: {e}")
            return False
    return await execute_db(_add)

async def db_remove_hidden_admin(chat_id: int, admin_id: int) -> bool:
    async def _remove(conn):
        await conn.execute("""
            DELETE FROM hidden_admins
            WHERE chat_id=? AND admin_id=?
        """, (chat_id, admin_id))
        await conn.execute("""
            DELETE FROM user_groups_link
            WHERE user_id=? AND chat_id=?
        """, (admin_id, chat_id))
        await conn.commit()
        return True
    return await execute_db(_remove)

async def db_sync_group_admins(chat_id: int, bot, owner_id: int = None) -> int:
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
                
            if owner_id and owner_id not in admin_ids:
                await conn.execute("""
                    INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden)
                    VALUES (?, ?, 1)
                """, (chat_id, owner_id))
                await conn.execute("""
                    INSERT OR IGNORE INTO user_groups_link (user_id, chat_id)
                    VALUES (?, ?)
                """, (owner_id, chat_id))
            
            await conn.commit()
            return len(admin_ids)
        count = await execute_db(_update)
        
        for admin_id in admin_ids:
            await invalidate_auth_cache(chat_id, admin_id)
        if owner_id:
            await invalidate_auth_cache(chat_id, owner_id)
        
        return count
    except Exception as e:
        logger.error(f"خطأ في مزامنة مشرفي المجموعة {chat_id}: {e}")
        return 0

# ===================== دوال الأمان (مصححة ومحسنة) =====================

# ثوابت أعمدة الأمان - موحدة مع init_db_improved
SECURITY_COLUMNS = {
    'delete_links': 'INTEGER DEFAULT 0',
    'mentions': 'INTEGER DEFAULT 0',
    'warn_message': 'INTEGER DEFAULT 1',
    'slow_mode': 'INTEGER DEFAULT 0',
    'slow_mode_seconds': 'INTEGER DEFAULT 5',
    'welcome_enabled': 'INTEGER DEFAULT 0',
    'welcome_text': 'TEXT',
    'goodbye_enabled': 'INTEGER DEFAULT 0',
    'goodbye_text': 'TEXT',
    'delete_banned_words': 'INTEGER DEFAULT 0',
    'auto_penalty': 'TEXT DEFAULT "none"',
    'auto_mute_duration': 'INTEGER DEFAULT 60',
    'delete_videos': 'INTEGER DEFAULT 0',
    'delete_audio': 'INTEGER DEFAULT 0',
    'delete_animation': 'INTEGER DEFAULT 0',
    'delete_service': 'INTEGER DEFAULT 0',
    'delete_documents': 'INTEGER DEFAULT 0',
    'delete_stickers': 'INTEGER DEFAULT 0',
    'delete_penalty': 'TEXT DEFAULT "none"',
    'delete_penalty_duration': 'INTEGER DEFAULT 0'
}

# ✅ تخزين مؤقت لحالة التحقق من الأعمدة لتجنب تكرار الاستعلام
_security_columns_checked = set()

async def ensure_security_columns(conn):
    """التحقق من وجود جميع أعمدة الأمان وإضافتها إذا لزم الأمر (مع تخزين مؤقت)"""
    # ✅ التحقق من التخزين المؤقت لتجنب استعلامات متكررة
    if 'group_security' in _security_columns_checked:
        return
    cur = await conn.execute("PRAGMA table_info(group_security)")
    existing = [row[1] for row in await cur.fetchall()]
    for col, col_type in SECURITY_COLUMNS.items():
        if col not in existing:
            await conn.execute(f"ALTER TABLE group_security ADD COLUMN {col} {col_type}")
    await conn.commit()
    _security_columns_checked.add('group_security')

# ✅ استخدام TTLCache للذاكرة المؤقتة إذا كانت متاحة
if CACHETOOLS_AVAILABLE:
    _security_cache = TTLCache(maxsize=500, ttl=300)
else:
    _security_cache = {}
    _security_cache_time = {}
    _SECURITY_CACHE_TTL = 300

async def db_get_security_settings(chat_id: int, force_refresh: bool = False) -> Dict:
    default_settings = {
        'delete_links': False,
        'mentions': False,
        'warn_message': True,
        'slow_mode': False,
        'slow_mode_seconds': 5,
        'welcome_enabled': False,
        'welcome_text': "مرحباً {user} في {chat} 🤍",
        'goodbye_enabled': False,
        'goodbye_text': "وداعاً {user} 👋",
        'delete_banned_words': False,
        'auto_penalty': 'none',
        'auto_mute_duration': 60,
        'delete_videos': False,
        'delete_audio': False,
        'delete_animation': False,
        'delete_service': False,
        'delete_documents': False,
        'delete_stickers': False,
        'delete_penalty': 'none',
        'delete_penalty_duration': 0,
        # إضافة مفاتيح الواجهة
        'links': False,
        'warn': True,
    }

    # التحقق من التخزين المؤقت
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
            await ensure_security_columns(conn)
            conn.row_factory = aiosqlite.Row
            
            col_names = list(SECURITY_COLUMNS.keys())
            query = f"SELECT {', '.join(col_names)} FROM group_security WHERE chat_id=?"
            
            cur = await conn.execute(query, (chat_id,))
            row = await cur.fetchone()
            
            if row:
                settings = {}
                for col in col_names:
                    value = row[col]
                    if col in ['delete_links', 'mentions', 'warn_message', 'slow_mode', 
                              'welcome_enabled', 'goodbye_enabled', 'delete_banned_words', 
                              'delete_videos', 'delete_audio', 'delete_animation', 
                              'delete_service', 'delete_documents', 'delete_stickers']:
                        settings[col] = value == 1
                    elif col in ['slow_mode_seconds', 'auto_mute_duration', 'delete_penalty_duration']:
                        settings[col] = value if value is not None else default_settings.get(col, 0)
                    elif col in ['welcome_text', 'goodbye_text', 'auto_penalty', 'delete_penalty']:
                        settings[col] = value if value is not None else default_settings.get(col, '')
                    else:
                        settings[col] = value
                
                # ✅ إضافة مفاتيح الواجهة التي يستخدمها الكيبورد
                settings['links'] = settings.get('delete_links', False)
                settings['warn'] = settings.get('warn_message', True)
                
                # تخزين في الكاش
                if CACHETOOLS_AVAILABLE:
                    _security_cache[chat_id] = settings
                else:
                    _security_cache[chat_id] = (time_module.time(), settings)
                return settings

            # إنشاء إعدادات افتراضية
            await conn.execute(
                f"""INSERT INTO group_security (chat_id, {', '.join(col_names)})
                   VALUES (?, {', '.join(['?' for _ in col_names])})""",
                (chat_id, *[default_settings.get(col, 0) for col in col_names])
            )
            await conn.commit()
            
            # إرجاع الإعدادات الافتراضية مع مفاتيح الواجهة
            result = default_settings.copy()
            result['links'] = result.get('delete_links', False)
            result['warn'] = result.get('warn_message', True)
            
            if CACHETOOLS_AVAILABLE:
                _security_cache[chat_id] = result
            else:
                _security_cache[chat_id] = (time_module.time(), result)
            return result
            
        return await execute_db(_get)
    except Exception as e:
        advanced_logger.log_error("خطأ في db_get_security_settings", e, {"chat_id": chat_id})
        result = default_settings.copy()
        result['links'] = result.get('delete_links', False)
        result['warn'] = result.get('warn_message', True)
        return result

async def db_set_security_settings(chat_id: int, **kwargs):
    try:
        async def _set(conn):
            await ensure_security_columns(conn)
            
            if not await db_row_exists(conn, "group_security", "chat_id=?", (chat_id,)):
                col_names = list(SECURITY_COLUMNS.keys())
                default_values = [1 if col in ['warn_message'] else 0 for col in col_names]
                await conn.execute(
                    f"INSERT INTO group_security (chat_id, {', '.join(col_names)}) "
                    f"VALUES (?, {', '.join(['?' for _ in col_names])})",
                    (chat_id, *default_values)
                )
                await conn.commit()
            
            updates = []
            values = []
            for key, value in kwargs.items():
                if key in SECURITY_COLUMNS:
                    if key in ['links', 'mentions', 'warn', 'slow_mode', 'welcome_enabled', 
                              'goodbye_enabled', 'delete_banned_words', 'delete_videos',
                              'delete_audio', 'delete_animation', 'delete_service',
                              'delete_documents', 'delete_stickers']:
                        updates.append(f"{key}=?")
                        values.append(1 if value else 0)
                    elif key in ['slow_mode_seconds', 'auto_mute_duration', 'delete_penalty_duration']:
                        updates.append(f"{key}=?")
                        values.append(int(value) if value is not None else 0)
                    else:
                        updates.append(f"{key}=?")
                        values.append(str(value) if value is not None else '')
            
            if updates:
                query = f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id=?"
                values.append(chat_id)
                await conn.execute(query, values)
                await conn.commit()
        
        await execute_db(_set)
        
        # تحديث الكاش
        if CACHETOOLS_AVAILABLE:
            _security_cache.pop(chat_id, None)
        else:
            _security_cache.pop(chat_id, None)
            _security_cache_time.pop(chat_id, None)
        await cache_manager.delete(f"security_{chat_id}")
        
    except sqlite3.OperationalError as e:
        if "no such column" in str(e):
            await db_ensure_columns("group_security", SECURITY_COLUMNS)
            return await db_set_security_settings(chat_id, **kwargs)
        else:
            raise

async def db_get_delete_settings(chat_id: int) -> dict:
    settings = await db_get_security_settings(chat_id)
    return {k: v for k, v in settings.items() if k.startswith('delete_')}

async def db_check_slow_mode(chat_id: int, user_id: int) -> bool:
    settings = await db_get_security_settings(chat_id)
    if not settings['slow_mode']:
        return True
    seconds = settings.get('slow_mode_seconds', 5)
    async def _check(conn):
        cur = await conn.execute("SELECT message_time FROM user_messages WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        row = await cur.fetchone()
        now = utc_now()
        if row:
            last_time = safe_parse_datetime(row[0])
            if last_time and (now - last_time).total_seconds() < seconds:
                return False
        await conn.execute("""
            INSERT OR REPLACE INTO user_messages (user_id, chat_id, message_time) 
            VALUES (?, ?, ?)
        """, (user_id, chat_id, now.isoformat()))
        await conn.commit()
        return True
    return await execute_db(_check)

async def db_add_banned_word(word: str, chat_id: int, added_by: int) -> bool:
    async def _add(conn):
        if await db_row_exists(conn, "banned_words", "word=? AND chat_id=?", (word, chat_id)):
            return False
        await conn.execute("""
            INSERT INTO banned_words (word, chat_id, added_by, added_at) 
            VALUES (?, ?, ?, ?)
        """, (word, chat_id, added_by, utc_now_iso()))
        await conn.commit()
        if '*' in word or '?' in word or '+' in word:
            await rebuild_banned_patterns()
        return True
    return await execute_db(_add)

async def db_remove_banned_word(word: str, chat_id: int) -> bool:
    async def _remove(conn):
        await conn.execute("DELETE FROM banned_words WHERE word=? AND chat_id=?", (word, chat_id))
        await conn.commit()
        if '*' in word or '?' in word or '+' in word:
            await rebuild_banned_patterns()
        return True
    return await execute_db(_remove)

async def db_get_banned_words(chat_id: int, limit: int = 200):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT word, added_by, added_at 
            FROM banned_words 
            WHERE chat_id=? OR chat_id=-1 
            ORDER BY word
            LIMIT ?
        """, (chat_id, limit))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_contains_banned_word(text: str, chat_id: int) -> Optional[str]:
    words = await db_get_banned_words(chat_id)
    text_lower = text.lower()
    for word in words:
        if word['word'] in text_lower:
            return word['word']
    for pattern in BANNED_PATTERNS:
        if pattern.search(text_lower):
            return pattern.pattern
    return None

async def add_banned_pattern(pattern: str) -> bool:
    try:
        compiled = re.compile(pattern.lower())
        BANNED_PATTERNS.append(compiled)
        return True
    except:
        return False

async def check_banned_patterns(text: str) -> bool:
    text_lower = text.lower()
    for pattern in BANNED_PATTERNS:
        if pattern.search(text_lower):
            return True
    return False

async def db_get_hidden_admins(chat_id: int) -> List[Dict]:
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT admin_id, added_by, added_at
            FROM hidden_admins
            WHERE chat_id=?
            ORDER BY added_at DESC
        """, (chat_id,))
        rows = await cur.fetchall()
        result = []
        for row in rows:
            result.append({
                'admin_id': row['admin_id'],
                'added_by': row['added_by'],
                'added_at': row['added_at'] if row['added_at'] else utc_now_iso()
            })
        return result
    return await execute_db(_get)

async def db_get_all_hidden_admins(user_id: int) -> List[Dict]:
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT chat_id, added_at
            FROM hidden_admins
            WHERE admin_id=?
        """, (user_id,))
        rows = await cur.fetchall()
        result = []
        for row in rows:
            result.append({
                'chat_id': row['chat_id'],
                'added_at': row['added_at'] if row['added_at'] else utc_now_iso()
            })
        return result
    return await execute_db(_get)

async def db_user_has_hidden_admin_role(chat_id: int, user_id: int) -> bool:
    async def _check(conn):
        if await db_is_hidden_owner(chat_id, user_id):
            return False
        if await db_is_hidden_admin(chat_id, user_id):
            return True
        return False
    return await execute_db(_check)

async def db_get_hidden_owner_groups(user_id: int):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT chat_id FROM hidden_owner_groups WHERE owner_id=?", (user_id,))
        return [row['chat_id'] for row in await cur.fetchall()]
    return await execute_db(_get)

async def db_get_hidden_admins_for_user(user_id: int):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT chat_id, added_by, added_at
            FROM hidden_admins
            WHERE admin_id=?
        """, (user_id,))
        return await cur.fetchall()
    return await execute_db(_get)

# ===================== دوال الجدولة (مصححة) =====================

class ScheduleType(Enum):
    INTERVAL = "interval"
    CRON = "cron"
    RECURRING = "recurring"

def validate_cron_expression(cron_expr: str) -> bool:
    if not cron_expr:
        return False
    parts = cron_expr.split()
    if len(parts) < 5 or len(parts) > 6:
        return False
    for part in parts[:5]:
        if part not in ['*'] and not part.isdigit() and not '/' in part and not ',' in part:
            return False
    return True

async def db_save_schedule(channel_db_id: int, schedule_type: str, 
                          interval_minutes: int = None, interval_hours: int = None, 
                          interval_days: int = None, days_of_week: str = None, 
                          specific_dates: str = None, publish_time: str = None, 
                          cron_expression: str = None):
    if schedule_type == 'cron' and cron_expression:
        if not validate_cron_expression(cron_expression):
            raise ValueError("تعبير كرون غير صالح")
    
    async def _save(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO schedule (
                channel_db_id, schedule_type, interval_minutes, interval_hours, 
                interval_days, days_of_week, specific_dates, publish_time, 
                cron_expression, next_publish_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """, (
            channel_db_id, schedule_type, interval_minutes, interval_hours, 
            interval_days, days_of_week, specific_dates, publish_time or "00:00", 
            cron_expression
        ))
        await conn.commit()
    return await execute_db(_save)

async def db_get_schedule(channel_db_id: int) -> Dict:
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT schedule_type, interval_minutes, interval_hours, interval_days, 
                   days_of_week, specific_dates, publish_time, cron_expression, next_publish_date 
            FROM schedule 
            WHERE channel_db_id=?
        """, (channel_db_id,))
        row = await cur.fetchone()
        if row:
            return {
                'type': row['schedule_type'] or 'interval_minutes',
                'interval_minutes': row['interval_minutes'] or 12,
                'interval_hours': row['interval_hours'] or 0,
                'interval_days': row['interval_days'] or 0,
                'days_of_week': row['days_of_week'] or '[]',
                'specific_dates': row['specific_dates'] or '[]',
                'publish_time': row['publish_time'] or '00:00',
                'cron_expression': row['cron_expression'],
                'next_publish_date': row['next_publish_date']
            }
        return {
            'type': 'interval_minutes', 'interval_minutes': 12, 'interval_hours': 0, 
            'interval_days': 0, 'days_of_week': '[]', 'specific_dates': '[]', 
            'publish_time': '00:00', 'cron_expression': None, 'next_publish_date': None
        }
    return await execute_db(_get)

async def db_set_next_publish_date(channel_db_id: int, next_date: Optional[datetime]):
    async def _set(conn):
        if next_date:
            await conn.execute("""
                UPDATE schedule 
                SET next_publish_date=? 
                WHERE channel_db_id=?
            """, (next_date.isoformat(), channel_db_id))
        else:
            await conn.execute("""
                UPDATE schedule 
                SET next_publish_date=NULL 
                WHERE channel_db_id=?
            """, (channel_db_id,))
        await conn.commit()
    return await execute_db(_set)

async def db_set_last_publish(channel_db_id: int, publish_time: datetime):
    async def _set(conn):
        await conn.execute("""
            INSERT INTO last_publish (channel_db_id, last_publish_time) 
            VALUES (?, ?) 
            ON CONFLICT(channel_db_id) DO UPDATE SET last_publish_time = ?
        """, (channel_db_id, publish_time.isoformat(), publish_time.isoformat()))
        await conn.commit()
    return await execute_db(_set)

async def schedule_cron(channel_db_id: int, cron_expression: str):
    if not validate_cron_expression(cron_expression):
        raise ValueError("تعبير كرون غير صالح")
    
    async def _save(conn):
        await conn.execute("""
            UPDATE schedule 
            SET schedule_type='cron', cron_expression=?, next_publish_date=NULL
            WHERE channel_db_id=?
        """, (cron_expression, channel_db_id))
        await conn.commit()
    return await execute_db(_save)

async def db_update_next_publish_date(channel_db_id: int):
    async def _update(conn):
        schedule = await db_get_schedule(channel_db_id)
        
        cur = await conn.execute("SELECT last_publish_time FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
        last_row = await cur.fetchone()
        last_time = safe_parse_datetime(last_row[0]) if last_row else utc_now()
        if not last_time:
            last_time = utc_now()
        
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
                    date_obj = safe_parse_datetime(date_str)
                    if date_obj:
                        date_obj = date_obj.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        if date_obj > last_time:
                            next_date = date_obj
                            break
                if not next_date and specific_dates:
                    first_date = safe_parse_datetime(specific_dates[0])
                    if first_date:
                        next_date = first_date.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=365)
            if not next_date:
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
            
            await conn.execute("""
                UPDATE schedule 
                SET next_publish_date=? 
                WHERE channel_db_id=?
            """, (next_date.isoformat(), channel_db_id))
            await conn.commit()
    return await execute_db(_update)

async def db_set_publish_time(channel_db_id: int, time_str: str):
    async def _set(conn):
        await conn.execute("UPDATE schedule SET publish_time=? WHERE channel_db_id=?", (time_str, channel_db_id))
        await conn.commit()
    return await execute_db(_set)

async def db_add_scheduled_post(chat_id: int, text: str, publish_time: datetime):
    async def _add(conn):
        await conn.execute("""
            INSERT INTO scheduled_posts (chat_id, text, publish_time, fail_count) 
            VALUES (?, ?, ?, 0)
        """, (chat_id, sanitize_text(text)[:4096], publish_time.isoformat()))
        await conn.commit()
    return await execute_db(_add)

async def db_get_due_scheduled_posts(now: datetime, limit: int = 50):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT id, chat_id, text, fail_count 
            FROM scheduled_posts 
            WHERE publish_time <= ? 
            LIMIT ?
        """, (now.isoformat(), limit))
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

# ===================== دوال الردود (مصححة) =====================

async def db_add_reply(keyword: str, reply: str):
    async def _add(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO group_replies (keyword, reply) 
            VALUES (?, ?)
        """, (keyword.lower()[:100], reply[:4096]))
        await conn.commit()
    return await execute_db(_add)

async def db_del_reply(keyword: str):
    async def _del(conn):
        await conn.execute("DELETE FROM group_replies WHERE keyword=?", (keyword.lower(),))
        await conn.commit()
    return await execute_db(_del)

async def db_get_reply(keyword: str) -> Optional[str]:
    async def _get(conn):
        cur = await conn.execute("SELECT reply FROM group_replies WHERE keyword=?", (keyword.lower(),))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_get_all_replies(limit: int = 100):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT keyword, reply FROM group_replies ORDER BY keyword LIMIT ?", (limit,))
        return await cur.fetchall()
    return await execute_db(_get)

# ===================== دوال الردود المتقدمة (مصححة) =====================

async def db_get_auto_reply_settings(chat_id: int) -> dict:
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT enabled, only_admins, ignore_bots FROM auto_reply_settings WHERE chat_id=?",
            (chat_id,)
        )
        row = await cur.fetchone()
        if row:
            return {
                'enabled': row['enabled'] == 1,
                'only_admins': row['only_admins'] == 1,
                'ignore_bots': row['ignore_bots'] == 1
            }
        await conn.execute("""
            INSERT INTO auto_reply_settings (chat_id, enabled, only_admins, ignore_bots) 
            VALUES (?, 1, 0, 1)
        """, (chat_id,))
        await conn.commit()
        return {'enabled': True, 'only_admins': False, 'ignore_bots': True}
    return await execute_db(_get)

async def db_set_auto_reply_enabled(chat_id: int, enabled: bool) -> None:
    async def _set(conn):
        if await db_row_exists(conn, "auto_reply_settings", "chat_id=?", (chat_id,)):
            await conn.execute("""
                UPDATE auto_reply_settings 
                SET enabled=?, updated_at=CURRENT_TIMESTAMP 
                WHERE chat_id=?
            """, (1 if enabled else 0, chat_id))
        else:
            await conn.execute("""
                INSERT INTO auto_reply_settings (chat_id, enabled, only_admins, ignore_bots) 
                VALUES (?, ?, 0, 1)
            """, (chat_id, 1 if enabled else 0))
        await conn.commit()
    return await execute_db(_set)

async def db_set_auto_reply_only_admins(chat_id: int, only_admins: bool) -> None:
    async def _set(conn):
        if await db_row_exists(conn, "auto_reply_settings", "chat_id=?", (chat_id,)):
            await conn.execute("""
                UPDATE auto_reply_settings 
                SET only_admins=?, updated_at=CURRENT_TIMESTAMP 
                WHERE chat_id=?
            """, (1 if only_admins else 0, chat_id))
        else:
            await conn.execute("""
                INSERT INTO auto_reply_settings (chat_id, enabled, only_admins, ignore_bots) 
                VALUES (?, 1, ?, 1)
            """, (chat_id, 1 if only_admins else 0))
        await conn.commit()
    return await execute_db(_set)

async def db_toggle_auto_reply(chat_id: int) -> bool:
    settings = await db_get_auto_reply_settings(chat_id)
    new_status = not settings['enabled']
    await db_set_auto_reply_enabled(chat_id, new_status)
    return new_status

async def db_get_user_auto_reply_status(user_id: int) -> bool:
    async def _get(conn):
        cur = await conn.execute(
            "SELECT auto_reply_enabled FROM users WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] == 1 if row else True
    return await execute_db(_get)

async def db_set_user_auto_reply_status(user_id: int, enabled: bool) -> None:
    async def _set(conn):
        await conn.execute(
            "UPDATE users SET auto_reply_enabled=? WHERE user_id=?",
            (1 if enabled else 0, user_id)
        )
        await conn.commit()
    return await execute_db(_set)

# ===================== دوال التذاكر (مصححة) =====================

async def db_get_next_ticket_number():
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='last_ticket_number'")
        row = await cur.fetchone()
        return int(row[0]) if row else 0
    return await execute_db(_get)

async def db_save_ticket(user_id, username, message, ticket_num):
    async def _save(conn):
        created_at = utc_now_iso()
        await conn.execute("""
            INSERT INTO support_tickets (user_id, username, message, ticket_number, status, created_at) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username[:50], sanitize_text(message)[:4096], ticket_num, 'pending', created_at))
        await conn.commit()
        return True
    return await execute_db(_save)

async def db_get_user_ticket(user_id):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT ticket_number, status, created_at 
            FROM support_tickets 
            WHERE user_id=? 
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        return await cur.fetchone()
    return await execute_db(_get)

async def db_get_all_tickets(limit=20):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT id, user_id, username, message, ticket_number, status, created_at 
            FROM support_tickets 
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_get_last_ticket_id_for_user(user_id):
    async def _get(conn):
        cur = await conn.execute("""
            SELECT id FROM support_tickets 
            WHERE user_id=? 
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_mark_ticket_replied(ticket_id):
    async def _mark(conn):
        await conn.execute("UPDATE support_tickets SET status='replied', replied=1 WHERE id=?", (ticket_id,))
        await conn.commit()
    return await execute_db(_mark)

async def db_delete_all_tickets() -> int:
    async def _delete(conn):
        cur = await conn.execute("DELETE FROM support_tickets")
        count = cur.rowcount
        await conn.execute("UPDATE settings SET value='0' WHERE key='last_ticket_number'")
        await conn.commit()
        return count
    return await execute_db(_delete)

# ===================== دوال الإحالات (مصححة) =====================

DEFAULT_REFERRAL_SETTINGS = {
    'reward_days_per_referral': '3',
    'max_referrals_per_day': '5',
    'welcome_bonus_points': '10'
}

async def db_get_referral_settings() -> dict:
    async def _get(conn):
        settings = DEFAULT_REFERRAL_SETTINGS.copy()
        cur = await conn.execute("SELECT key, value FROM referral_settings")
        rows = await cur.fetchall()
        for key, value in rows:
            settings[key] = value
        return settings
    return await execute_db(_get)

async def db_get_referral_code(user_id: int) -> Optional[str]:
    async def _get(conn):
        cur = await conn.execute("SELECT referral_code FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row and row[0] else None
    return await execute_db(_get)

async def db_generate_referral_code(user_id: int) -> str:
    async def _generate(conn):
        code_hash = hashlib.md5(f"{user_id}{time_module.time()}".encode()).hexdigest()[:8]
        referral_code = f"REF{code_hash.upper()}"
        await conn.execute("UPDATE users SET referral_code=? WHERE user_id=?", (referral_code, user_id))
        await conn.commit()
        return referral_code
    return await execute_db(_generate)

async def db_get_user_by_referral_code(referral_code: str) -> Optional[int]:
    async def _get(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE referral_code=?", (referral_code,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_add_referral(referrer_id: int, referred_id: int) -> Dict:
    async def _add(conn):
        if referrer_id == referred_id:
            return {'success': False, 'reason': 'self_referral'}
        
        if await db_row_exists(conn, "referrals", "referred_id=?", (referred_id,)):
            return {'success': False, 'reason': 'already_referred'}
        
        today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        cur = await conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND referred_at >= ?",
            (referrer_id, today_start)
        )
        count_today = (await cur.fetchone())[0]
        
        settings = await db_get_referral_settings()
        max_per_day = int(settings.get('max_referrals_per_day', '5'))
        if count_today >= max_per_day:
            return {'success': False, 'reason': 'max_daily_limit'}
        
        await conn.execute("""
            INSERT INTO referrals (referrer_id, referred_id) 
            VALUES (?, ?)
        """, (referrer_id, referred_id))
        await conn.commit()
        return {'success': True, 'reason': 'ok'}
    return await execute_db(_add)

async def db_auto_reward_referral(referrer_id: int, referred_id: int) -> int:
    async def _reward(conn):
        settings = await db_get_referral_settings()
        reward_days = int(settings.get('reward_days_per_referral', '3'))
        await conn.execute("""
            INSERT INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days)
            VALUES (?, 1, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET
                referral_count = referral_count + 1,
                total_reward_days = total_reward_days + ?
        """, (referrer_id, reward_days, reward_days))
        await conn.execute("""
            UPDATE referrals 
            SET is_rewarded=1 
            WHERE referrer_id=? AND referred_id=?
        """, (referrer_id, referred_id))
        await conn.commit()
        return reward_days
    return await execute_db(_reward)

async def db_get_referral_stats(user_id: int) -> dict:
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,))
        total_referrals = (await cur.fetchone())[0]
        cur = await conn.execute("""
            SELECT referral_count, total_reward_days, claimed_reward_days 
            FROM referral_rewards 
            WHERE user_id=?
        """, (user_id,))
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
    async def _claim(conn):
        cur = await conn.execute("""
            SELECT total_reward_days, claimed_reward_days 
            FROM referral_rewards 
            WHERE user_id=?
        """, (user_id,))
        row = await cur.fetchone()
        if not row:
            return 0
        total = row[0]
        claimed = row[1]
        available = total - claimed
        if available <= 0:
            return 0
        
        current_sub = max(0, await db_get_subscription_days_left(user_id))
        new_sub_days = current_sub + available
        end_date = (utc_now() + timedelta(days=new_sub_days)).isoformat()
        await conn.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (end_date, user_id))
        await conn.execute("""
            UPDATE referral_rewards 
            SET claimed_reward_days = claimed_reward_days + ? 
            WHERE user_id=?
        """, (available, user_id))
        await conn.commit()
        return available
    return await execute_db(_claim)

async def db_get_welcome_bonus_points() -> int:
    settings = await db_get_referral_settings()
    return int(settings.get('welcome_bonus_points', '10'))

# ===================== دوال التذكيرات (مصححة) =====================

async def db_get_user_reminder_settings(user_id: int) -> dict:
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT subscription_reminder, daily_stats_reminder, weekly_report, 
                   reminder_days_before, last_reminder_sent, notification_lang 
            FROM user_reminder_settings 
            WHERE user_id=?
        """, (user_id,))
        row = await cur.fetchone()
        if row:
            return {
                'subscription_reminder': row['subscription_reminder'] == 1,
                'daily_stats_reminder': row['daily_stats_reminder'] == 1,
                'weekly_report': row['weekly_report'] == 1,
                'reminder_days_before': row['reminder_days_before'] if row['reminder_days_before'] is not None else 3,
                'last_reminder_sent': row['last_reminder_sent'] if row['last_reminder_sent'] is not None else 0,
                'notification_lang': row['notification_lang'] if row['notification_lang'] else 'ar'
            }
        else:
            lang = user_language.get(user_id, 'ar')
            await conn.execute("""
                INSERT INTO user_reminder_settings (
                    user_id, subscription_reminder, daily_stats_reminder, weekly_report, 
                    reminder_days_before, last_reminder_sent, notification_lang
                ) VALUES (?, 1, 0, 1, 3, 0, ?)
            """, (user_id, lang))
            await conn.commit()
            return {
                'subscription_reminder': True, 
                'daily_stats_reminder': False, 
                'weekly_report': True, 
                'reminder_days_before': 3, 
                'last_reminder_sent': 0, 
                'notification_lang': lang
            }
    return await execute_db(_get)

async def db_update_reminder_settings(user_id: int, **kwargs):
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
                values.append(int(value) if value is not None else 3)
            elif key == 'notification_lang':
                fields.append("notification_lang=?")
                values.append(str(value) if value else 'ar')
        if fields:
            query = f"UPDATE user_reminder_settings SET {', '.join(fields)} WHERE user_id=?"
            values.append(user_id)
            await conn.execute(query, values)
            await conn.commit()
    return await execute_db(_update)

async def db_update_last_reminder_sent(user_id: int, reminder_type: str):
    async def _update(conn):
        now_timestamp = int(time_module.time())
        await conn.execute("""
            UPDATE user_reminder_settings 
            SET last_reminder_sent=? 
            WHERE user_id=?
        """, (now_timestamp, user_id))
        await conn.commit()
    return await execute_db(_update)

async def db_get_users_needing_reminder(limit: int = 500) -> list:
    async def _get(conn):
        now = utc_now()
        users = []
        cutoff_date = (now + timedelta(days=10)).isoformat()
        cur = await conn.execute("""
            SELECT user_id, subscription_end 
            FROM users 
            WHERE subscription_end IS NOT NULL AND subscription_end <= ? AND banned=0
            LIMIT ?
        """, (cutoff_date, limit))
        rows = await cur.fetchall()
        
        for user_id, subscription_end_str in rows:
            end_date = safe_parse_datetime(subscription_end_str)
            if not end_date:
                continue
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
        return users
    return await execute_db(_get)

async def db_get_all_active_users_for_report(limit: int = 1000) -> list:
    async def _get(conn):
        thirty_days_ago = (utc_now() - timedelta(days=30)).isoformat()
        cur = await conn.execute("""
            SELECT DISTINCT u.user_id 
            FROM users u
            LEFT JOIN user_channels uc ON u.user_id = uc.user_id
            WHERE uc.created_at >= ? OR u.user_id IN (
                SELECT user_id FROM users_cache WHERE last_updated >= ?
            )
            LIMIT ?
        """, (thirty_days_ago, thirty_days_ago, limit))
        return [row[0] for row in await cur.fetchall()]
    return await execute_db(_get)

# ===================== دوال المستويات (مصححة) =====================

LEVEL_REQUIREMENTS = {1: 0, 2: 100, 3: 250, 4: 500, 5: 1000, 6: 2000, 7: 3500, 8: 5000, 9: 7500, 10: 10000}

class UserPointsTracker:
    def __init__(self):
        self.data = {}
        self._lock = asyncio.Lock()
    
    async def get(self, user_id: int) -> tuple:
        async with self._lock:
            return self.data.get(user_id, (0, 0.0))
    
    async def set(self, user_id: int, count: int, timestamp: float):
        async with self._lock:
            self.data[user_id] = (count, timestamp)
    
    async def cleanup(self):
        async with self._lock:
            now = time_module.time()
            expired = [uid for uid, (_, ts) in self.data.items() if now - ts > 3600]
            for uid in expired:
                del self.data[uid]

user_points_tracker = UserPointsTracker()

async def db_get_user_level(user_id: int) -> dict:
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT points, level FROM user_levels WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row:
            return {'points': row['points'], 'level': row['level']}
        await conn.execute("INSERT INTO user_levels (user_id, points, level) VALUES (?, 0, 1)", (user_id,))
        await conn.commit()
        return {'points': 0, 'level': 1}
    return await execute_db(_get)

async def db_update_user_level(user_id: int, points: int, level: int):
    async def _update(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO user_levels (user_id, points, level) 
            VALUES (?, ?, ?)
        """, (user_id, points, level))
        await conn.commit()
    return await execute_db(_update)

async def add_points(user_id: int, update: Update = None, context: ContextTypes.DEFAULT_TYPE = None):
    """إضافة نقاط للمستخدم مع تحديد سرعة الإضافة (1 نقطة لكل ساعة بحد أقصى 20 نقطة)"""
    now = utc_now()
    count, last_timestamp = await user_points_tracker.get(user_id)
    
    if last_timestamp > 0:
        last_time = datetime.fromtimestamp(last_timestamp, tz=timezone.utc)
        if (now - last_time).total_seconds() < 3600:
            if count >= 20:
                return
            new_count = count + 1
        else:
            new_count = 1
    else:
        new_count = 1
    
    await user_points_tracker.set(user_id, new_count, now.timestamp())
    
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
            await safe_send_markdown(context.bot, update.effective_user.id, msg)
        except:
            pass
    
    await db_update_user_level(user_id, points, level)
 
async def get_rank(user_id: int) -> dict:
    return await db_get_user_level(user_id)

async def get_top_users(limit: int = 10):
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT user_id, points, level 
            FROM user_levels 
            ORDER BY points DESC LIMIT ?
        """, (limit,))
        return await cur.fetchall()
    return await execute_db(_get)

async def daily_reward(user_id: int) -> int:
    today = utc_now().date()
    async def _check(conn):
        cur = await conn.execute("SELECT last_daily_reward FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            last_date = safe_parse_datetime(row[0])
            if last_date and last_date.date() == today:
                return 0
        await conn.execute("UPDATE users SET last_daily_reward=? WHERE user_id=?", (utc_now_iso(), user_id))
        await conn.commit()
        return 10
    reward = await execute_db(_check)
    if reward > 0:
        data = await db_get_user_level(user_id)
        await db_update_user_level(user_id, data['points'] + reward, data['level'])
    return reward

async def weekly_reward(user_id: int) -> int:
    week_start = (utc_now() - timedelta(days=utc_now().weekday())).date()
    async def _check(conn):
        cur = await conn.execute("SELECT last_weekly_reward FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            last_date = safe_parse_datetime(row[0])
            if last_date and last_date.date() >= week_start:
                return 0
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
    async def _get_achievements(conn):
        cur = await conn.execute("SELECT achievements FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else '[]'

    achievements = json.loads(await execute_db(_get_achievements) or '[]')

    if action == 'first_post' and 'first_post' not in achievements:
        achievements.append('first_post')
        level_data = await db_get_user_level(user_id)
        await db_update_user_level(user_id, level_data['points'] + ACHIEVEMENTS['first_post']['points'], level_data['level'])
        return f"{ACHIEVEMENTS['first_post']['icon']} {ACHIEVEMENTS['first_post']['name']} (+{ACHIEVEMENTS['first_post']['points']} نقطة)"

    if action == 'first_referral' and 'first_referral' not in achievements:
        achievements.append('first_referral')
        level_data = await db_get_user_level(user_id)
        await db_update_user_level(user_id, level_data['points'] + ACHIEVEMENTS['first_referral']['points'], level_data['level'])
        return f"{ACHIEVEMENTS['first_referral']['icon']} {ACHIEVEMENTS['first_referral']['name']} (+{ACHIEVEMENTS['first_referral']['points']} نقطة)"

    return ""

# ===================== دوال الإعدادات العامة (مصححة) =====================

async def db_get_publish_interval() -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='publish_interval'")
        row = await cur.fetchone()
        return int(row[0]) if row else DEFAULT_PUBLISH_INTERVAL_SECONDS
    return await execute_db(_get)

async def db_get_publish_interval_seconds() -> int:
    return await db_get_publish_interval()

async def db_set_publish_interval_seconds(seconds: int) -> None:
    """تعيين فترة النشر (لا تحتاج صلاحية هنا، يتم التحقق في الطبقة العليا)"""
    async def _set(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO settings (key, value) 
            VALUES ('publish_interval', ?)
        """, (str(seconds),))
        await conn.commit()
    return await execute_db(_set)

async def db_get_updates_channel() -> Optional[str]:
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

async def db_set_updates_channel(channel: str) -> bool:
    if not channel:
        return False
    channel = channel.strip()
    if channel.startswith('@'):
        channel = channel[1:]
    if not channel:
        return False
    async def _set(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO settings (key, value) 
            VALUES ('updates_channel', ?)
        """, (channel,))
        await conn.commit()
    await execute_db(_set)
    logger.info(f"✅ تم حفظ قناة التحديثات: {channel}")
    return True

async def db_get_force_subscribe_status() -> bool:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='force_subscribe_enabled'")
        row = await cur.fetchone()
        return row and row[0] == '1'
    return await execute_db(_get)

async def db_set_force_subscribe_status(enabled: bool):
    async def _set(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO settings (key, value) 
            VALUES ('force_subscribe_enabled', ?)
        """, ('1' if enabled else '0',))
        await conn.commit()
    return await execute_db(_set)

async def db_get_force_subscribe_channel() -> Optional[str]:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='force_subscribe_channel'")
        row = await cur.fetchone()
        return row[0] if row and row[0] else None
    return await execute_db(_get)

async def db_set_force_subscribe_channel(channel: str):
    async def _set(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO settings (key, value) 
            VALUES ('force_subscribe_channel', ?)
        """, (channel,))
        await conn.commit()
    return await execute_db(_set)

async def db_get_log_channel_id() -> Optional[int]:
    """إرجاع معرف قناة السجلات كـ int"""
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='log_channel_id'")
        row = await cur.fetchone()
        if row and row[0]:
            try:
                return int(row[0])
            except ValueError:
                return None
        return None
    return await execute_db(_get)

async def db_set_log_channel_id(channel_id: int):
    async def _set(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO settings (key, value) 
            VALUES ('log_channel_id', ?)
        """, (str(channel_id),))
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
        await conn.execute("""
            INSERT OR REPLACE INTO settings (key, value) 
            VALUES ('auto_backup', ?)
        """, ('1' if enabled else '0',))
        await conn.commit()
    return await execute_db(_set)

async def db_get_last_backup_time() -> Optional[str]:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='last_backup'")
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_get_allowed_sendcode_user() -> Optional[int]:
    async def _get(conn):
        cur = await conn.execute("SELECT user_id FROM allowed_sendcode_user WHERE id=1")
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_set_allowed_sendcode_user(user_id: int) -> None:
    async def _set(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO allowed_sendcode_user (id, user_id) 
            VALUES (1, ?)
        """, (user_id,))
        await conn.commit()
    return await execute_db(_set)

# ===================== دوال الترجمة (مصححة) =====================

user_translation_settings_cache = {}
_user_translation_cache_lock = asyncio.Lock()

async def get_user_translation_language(user_id: int) -> str:
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
    async def _set(conn):
        await conn.execute(
            "INSERT OR REPLACE INTO user_translation (user_id, lang) VALUES (?, ?)",
            (user_id, lang)
        )
        await conn.commit()
    await execute_db(_set)
    async with _user_translation_cache_lock:
        user_translation_settings_cache[user_id] = lang

async def translate_text(text: str, target_lang: str) -> str:
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

# ===================== دوال المسابقات (مصححة) =====================

class ContestTypes(Enum):
    QUIZ = "quiz"
    RAFFLE = "raffle"
    VOTE = "vote"
    SUBMISSION = "submission"

async def db_get_active_contests_with_participants(limit: int = 10) -> list:
    try:
        async def _get(conn):
            conn.row_factory = aiosqlite.Row
            now = utc_now().isoformat()
            try:
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
                    result.append({
                        'id': row['id'],
                        'title': row['title'],
                        'description': row['description'],
                        'prize': row['prize'],
                        'end_date': row['end_date'],
                        'participants': row['participants'],
                        'contest_type': row.get('contest_type', 'raffle')
                    })
                return result
            except Exception as e:
                logger.error(f"خطأ في تنفيذ الاستعلام: {e}")
                return []
        return await execute_db(_get)
    except Exception as e:
        logger.error(f"خطأ في db_get_active_contests_with_participants: {e}")
        return []

async def db_create_contest(creator_id: int, title: str, description: str, prize: str, end_date: datetime, contest_type: str = 'raffle') -> Optional[int]:
    try:
        async def _create(conn):
            if not isinstance(end_date, datetime):
                raise ValueError("end_date must be datetime object")
            end_date_str = end_date.isoformat()
            created_at_str = utc_now_iso()
            cur = await conn.execute("""
                INSERT INTO contests (creator_id, title, description, prize, end_date, status, created_at, contest_type)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
            """, (creator_id, title[:255], description[:1000], prize[:255], end_date_str, created_at_str, contest_type))
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

async def db_get_contest(contest_id: int) -> Optional[Dict]:
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT id, title, description, prize, end_date, status, winner_id, creator_id, created_at, contest_type
            FROM contests WHERE id = ?
        """, (contest_id,))
        row = await cur.fetchone()
        if row:
            return {
                'id': row['id'], 
                'title': row['title'], 
                'description': row['description'],
                'prize': row['prize'], 
                'end_date': row['end_date'], 
                'status': row['status'],
                'winner_id': row['winner_id'], 
                'creator_id': row['creator_id'], 
                'created_at': row['created_at'],
                'contest_type': row.get('contest_type', 'raffle')
            }
        return None
    return await execute_db(_get)

async def db_participate_in_contest(user_id: int, contest_id: int, answer: str = "") -> bool:
    async def _participate(conn):
        try:
            await conn.execute(
                "INSERT INTO contest_participants (user_id, contest_id, answer, joined_at) VALUES (?, ?, ?, ?)",
                (user_id, contest_id, answer[:500], utc_now_iso())
            )
            await conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    return await execute_db(_participate)

async def db_get_user_participation(user_id: int, contest_id: int) -> Optional[Dict]:
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

async def db_delete_contest(contest_id: int) -> bool:
    """حذف مسابقة (بدون تحقق صلاحية هنا، يتم في الطبقة العليا)"""
    async def _delete(conn):
        await conn.execute("DELETE FROM contest_participants WHERE contest_id = ?", (contest_id,))
        await conn.execute("DELETE FROM contests WHERE id = ?", (contest_id,))
        await conn.commit()
        return True
    return await execute_db(_delete)

async def db_get_random_participant(contest_id: int) -> Optional[int]:
    async def _get(conn):
        cur = await conn.execute(
            "SELECT user_id FROM contest_participants WHERE contest_id = ? ORDER BY RANDOM() LIMIT 1",
            (contest_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

# ===================== دوال إحصائيات القنوات (مصححة) =====================

async def db_get_channel_stats(channel_db_id: int) -> dict:
    async def _get_stats(conn):
        conn.row_factory = aiosqlite.Row
        
        # استعلام واحد محسن باستخدام JOIN و GROUP BY
        cur = await conn.execute("""
            SELECT
                COUNT(*) as total_posts,
                SUM(CASE WHEN published = 1 THEN 1 ELSE 0 END) as published_posts,
                SUM(CASE WHEN published = 0 THEN 1 ELSE 0 END) as unpublished_posts,
                COALESCE(SUM(views_count), 0) as total_views,
                COALESCE(AVG(views_count), 0) as avg_views,
                MAX(created_at) as last_post_time,
                MIN(created_at) as first_post_time,
                SUM(CASE WHEN date(created_at) = date('now') AND published = 1 THEN 1 ELSE 0 END) as published_today,
                SUM(CASE WHEN created_at >= date('now', '-7 days') AND published = 1 THEN 1 ELSE 0 END) as published_this_week,
                SUM(CASE WHEN created_at >= date('now', '-30 days') AND published = 1 THEN 1 ELSE 0 END) as published_this_month
            FROM posts
            WHERE channel_db_id = ?
        """, (channel_db_id,))
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
        total_views = row['total_views'] or 0
        avg_views = row['avg_views'] or 0
        
        avg_time_between = 0
        if published_posts > 1 and row['last_post_time'] and row['first_post_time']:
            last_dt = safe_parse_datetime(row['last_post_time'])
            first_dt = safe_parse_datetime(row['first_post_time'])
            if last_dt and first_dt:
                time_diff = (last_dt - first_dt).total_seconds()
                avg_time_between = time_diff / (published_posts - 1) if published_posts > 1 else 0
        
        best_hour = 0
        best_day = 0
        
        if published_posts > 0:
            # أفضل ساعة
            cur = await conn.execute("""
                SELECT strftime('%H', created_at) as hour, COUNT(*) as count
                FROM posts
                WHERE channel_db_id = ? AND published = 1
                GROUP BY hour
                ORDER BY count DESC
                LIMIT 1
            """, (channel_db_id,))
            hour_row = await cur.fetchone()
            if hour_row:
                best_hour = int(hour_row['hour'])
            
            # أفضل يوم
            cur = await conn.execute("""
                SELECT strftime('%w', created_at) as day, COUNT(*) as count
                FROM posts
                WHERE channel_db_id = ? AND published = 1
                GROUP BY day
                ORDER BY count DESC
                LIMIT 1
            """, (channel_db_id,))
            day_row = await cur.fetchone()
            if day_row:
                best_day = int(day_row['day'])
        
        # المنشور الأكثر والأقل مشاهدة
        most_viewed = None
        least_viewed = None
        
        cur = await conn.execute("""
            SELECT id, text, views_count
            FROM posts
            WHERE channel_db_id = ? AND published = 1
            ORDER BY views_count DESC
            LIMIT 1
        """, (channel_db_id,))
        most_row = await cur.fetchone()
        if most_row:
            text = most_row['text']
            if text and len(text) > 50:
                text = text[:50] + '...'
            most_viewed = {'id': most_row['id'], 'text': text, 'views': most_row['views_count']}
        
        cur = await conn.execute("""
            SELECT id, text, views_count
            FROM posts
            WHERE channel_db_id = ? AND published = 1 AND views_count > 0
            ORDER BY views_count ASC
            LIMIT 1
        """, (channel_db_id,))
        least_row = await cur.fetchone()
        if least_row:
            text = least_row['text']
            if text and len(text) > 50:
                text = text[:50] + '...'
            least_viewed = {'id': least_row['id'], 'text': text, 'views': least_row['views_count']}
        
        return {
            'total_posts': total_posts,
            'published_posts': published_posts,
            'unpublished_posts': row['unpublished_posts'] or 0,
            'total_views': total_views,
            'avg_views': round(avg_views, 2) if avg_views else 0,
            'last_post_time': row['last_post_time'],
            'first_post_time': row['first_post_time'],
            'avg_time_between_posts': round(avg_time_between / 3600, 2) if avg_time_between else 0,
            'best_publish_hour': best_hour,
            'best_publish_day': best_day,
            'published_today': row['published_today'] or 0,
            'published_this_week': row['published_this_week'] or 0,
            'published_this_month': row['published_this_month'] or 0,
            'most_viewed_post': most_viewed,
            'least_viewed_post': least_viewed,
        }
    return await execute_db(_get_stats)

async def db_get_channel_stats_summary(user_id: int) -> Optional[Dict]:
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
        
        for channel in channels:
            if not channel['banned']:
                active_channels += 1
            stats = await db_get_channel_stats(channel['id'])
            if stats and stats['total_posts'] > 0:
                total_posts += stats['total_posts']
                total_published += stats['published_posts']
                total_views += stats['total_views']
                if stats['total_views'] > best_channel_views:
                    best_channel_views = stats['total_views']
                    best_channel = {
                        'name': channel['channel_name'],
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
    async def _get_growth(conn):
        conn.row_factory = aiosqlite.Row
        start_date = (utc_now() - timedelta(days=days)).isoformat()
        cur = await conn.execute("""
            SELECT
                date(created_at) as post_date,
                COUNT(*) as count,
                COALESCE(SUM(views_count), 0) as views
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

# ===================== دوال الصحة (مصححة) =====================

async def check_database_health() -> bool:
    try:
        async def _check(conn):
            cur = await conn.execute("SELECT 1")
            row = await cur.fetchone()
            return row is not None
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

def get_ram_usage():
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            'total': round(mem.total / (1024**3), 1),
            'used': round(mem.used / (1024**3), 1),
            'percent': mem.percent
        }
    except:
        # محاولة قراءة من /proc/meminfo (Linux)
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

# ===================== دوال مساعدة =====================

def contains_link(text: str) -> bool:
    patterns = [
        r'https?://\S+',
        r'www\.\S+',
        r't\.me/\S+',
        r'telegram\.me/\S+',
        r'\b[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+\S*'
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)

def contains_mention(text: str) -> bool:
    return bool(re.search(r'@\w+', text))

async def invalidate_user_cache(user_id: int):
    try:
        if user_id in _admin_cache:
            del _admin_cache[user_id]
        keys_to_remove = [k for k in _admin_cache.keys() if str(user_id) in k]
        for key in keys_to_remove:
            del _admin_cache[key]
    except:
        pass

async def invalidate_auth_cache(chat_id: int, user_id: int):
    try:
        cache_key = f"auth_{chat_id}_{user_id}"
        if CACHETOOLS_AVAILABLE:
            if cache_key in _auth_cache:
                del _auth_cache[cache_key]
        else:
            if cache_key in _auth_cache:
                del _auth_cache[cache_key]
    except:
        pass

async def cleanup_points_cache():
    while True:
        await asyncio.sleep(3600)
        await user_points_tracker.cleanup()

async def ensure_db_connection():
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

# ===================== دوال النسخ الاحتياطي (مصححة) =====================

async def create_backup() -> Path:
    try:
        timestamp = mecca_now().strftime('%Y%m%d_%H%M%S')
        backup_file = BACKUP_DIR / f"backup_{timestamp}.enc"
        
        with open(DB_PATH, 'rb') as f_in:
            data = f_in.read()
            compressed = compress_backup(data)
            encrypted = BACKUP_CIPHER.encrypt(compressed)
            with open(backup_file, 'wb') as f_out:
                f_out.write(encrypted)
        
        backups = sorted(BACKUP_DIR.glob("backup_*.enc"), key=lambda x: x.stat().st_mtime, reverse=True)
        for old_backup in backups[MAX_BACKUPS:]:
            old_backup.unlink()
        
        if CLOUD_BACKUP_ENABLED:
            await upload_backup_to_drive(backup_file)
        
        logger.info(f"✅ تم إنشاء نسخة احتياطية مشفرة: {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"❌ فشل إنشاء النسخة الاحتياطية: {e}")
        raise

async def incremental_backup() -> Optional[Path]:
    try:
        last_backup = await db_get_last_backup_time()
        if last_backup:
            last_time = safe_parse_datetime(last_backup)
            if not last_time:
                last_time = utc_now() - timedelta(days=7)
        else:
            last_time = utc_now() - timedelta(days=7)

        backup_data = {}

        async def _get_new_posts(conn):
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM posts WHERE created_at > ? LIMIT 1000",
                (last_time.isoformat(),)
            )
            return await cur.fetchall()

        new_posts = await execute_db(_get_new_posts)
        if new_posts:
            backup_data['posts'] = [dict(post) for post in new_posts]

        async def _get_new_users(conn):
            conn.row_factory = aiosqlite.Row
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

    await db_pool.close()
    
    if backup_path.suffix == '.inc':
        data = json.loads(decompressed.decode('utf-8'))
        async def _merge_data(conn):
            if 'posts' in data:
                for post in data['posts']:
                    await conn.execute("""
                        INSERT OR IGNORE INTO posts (id, channel_db_id, text, media_type, media_file_id, published, fail_count, views_count, last_view_time, created_at) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        post['id'], post['channel_db_id'], post['text'], post['media_type'], 
                        post['media_file_id'], post['published'], post['fail_count'], 
                        post['views_count'], post['last_view_time'], post['created_at']
                    ))
            if 'users' in data:
                for user in data['users']:
                    await conn.execute("""
                        INSERT OR IGNORE INTO users (user_id, auto_publish, banned, trial_used, subscription_end, referral_code, referred_by, active_channel, auto_reply_enabled, auto_recycle, language) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user['user_id'], user['auto_publish'], user['banned'], user['trial_used'], 
                        user['subscription_end'], user['referral_code'], user['referred_by'], 
                        user['active_channel'], user['auto_reply_enabled'], user['auto_recycle'],
                        user.get('language', 'ar')
                    ))
            await conn.commit()
        
        await db_pool.initialize()
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
                    last_time = safe_parse_datetime(last_backup)
                    if not last_time or (utc_now() - last_time).days >= 7:
                        await create_backup()
                    else:
                        await incremental_backup()
                
                async def _update_backup_time(conn):
                    await conn.execute("""
                        INSERT OR REPLACE INTO settings (key, value) 
                        VALUES ('last_backup', ?)
                    """, (utc_now_iso(),))
                    await conn.commit()
                await execute_db(_update_backup_time)
            
            consecutive_errors = 0
            backoff = AUTO_BACKUP_SLEEP
        except Exception as e:
            logger.error(f"⚠️ خطأ في النسخ الاحتياطي التلقائي: {e}")
            consecutive_errors += 1
            backoff = min(backoff * 1.5, max_backoff)
            await asyncio.sleep(backoff)

# ===================== دوال جوجل درايف (مصححة) =====================

_DRIVE_SERVICE_CACHE = None
_DRIVE_SERVICE_CACHE_TIME = 0
_DRIVE_SERVICE_CACHE_TTL = 3600

async def get_google_drive_service(force_refresh: bool = False):
    global _DRIVE_SERVICE_CACHE, _DRIVE_SERVICE_CACHE_TIME
    if not CLOUD_BACKUP_ENABLED:
        return None
    
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from google_auth_oauthlib.flow import InstalledAppFlow
        
        now = time_module.time()
        if not force_refresh and _DRIVE_SERVICE_CACHE and (now - _DRIVE_SERVICE_CACHE_TIME) < _DRIVE_SERVICE_CACHE_TTL:
            return _DRIVE_SERVICE_CACHE
        
        creds = None
        token_path = Path(TOKEN_FILE)
        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(token_path),
                    ['https://www.googleapis.com/auth/drive.file']
                )
            except Exception as e:
                logger.warning(f"⚠️ فشل تحميل التوكن المخزن: {e}")
                if token_path.exists():
                    token_path.unlink()
        
        if creds and creds.valid:
            _DRIVE_SERVICE_CACHE = build('drive', 'v3', credentials=creds)
            _DRIVE_SERVICE_CACHE_TIME = now
            return _DRIVE_SERVICE_CACHE
        
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, 'w') as token:
                    token.write(creds.to_json())
                _DRIVE_SERVICE_CACHE = build('drive', 'v3', credentials=creds)
                _DRIVE_SERVICE_CACHE_TIME = now
                return _DRIVE_SERVICE_CACHE
            except Exception as e:
                logger.warning(f"⚠️ فشل تجديد التوكن: {e}")
                if token_path.exists():
                    token_path.unlink()
        
        if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
            logger.error(f"❌ ملف الاعتمادات غير موجود: {GOOGLE_CREDENTIALS_FILE}")
            return None
        
        flow = InstalledAppFlow.from_client_secrets_file(
            GOOGLE_CREDENTIALS_FILE,
            ['https://www.googleapis.com/auth/drive.file']
        )
        
        try:
            creds = flow.run_local_server(port=8080, open_browser=False)
        except:
            try:
                creds = flow.run_local_server(port=8081, open_browser=False)
            except:
                creds = flow.run_local_server(port=0, open_browser=False)
        
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        
        _DRIVE_SERVICE_CACHE = build('drive', 'v3', credentials=creds)
        _DRIVE_SERVICE_CACHE_TIME = now
        return _DRIVE_SERVICE_CACHE
        
    except Exception as e:
        logger.error(f"❌ خطأ في خدمة Google Drive: {e}")
        return None

async def upload_backup_to_drive(backup_path: Path, max_retries: int = 3) -> Optional[str]:
    if not CLOUD_BACKUP_ENABLED or not GOOGLE_DRIVE_FOLDER_ID:
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
            
            from googleapiclient.http import MediaFileUpload
            
            # تنظيف الملفات القديمة
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
            
            # رفع الملف
            file_name = f"backup_{mecca_now().strftime('%Y%m%d_%H%M%S')}.enc"
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

# ===================== دوال التهيئة المحسنة لقاعدة البيانات =====================

async def init_db_improved():
    """تهيئة قاعدة البيانات مع إنشاء الجداول والفهارس"""
    async def _init(conn):
        await conn.execute("PRAGMA foreign_keys=ON")
        
        # جدول users (يحتوي على عمود language)
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
                achievements TEXT DEFAULT '[]',
                language TEXT DEFAULT 'ar'
            )
        """)
        
        # باقي الجداول (كما في الإصدار السابق مع التأكد من وجود جميع الأعمدة)
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
                FOREIGN KEY (user_id) REFERENCES users(user_id)
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
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schedule (
                channel_db_id INTEGER PRIMARY KEY,
                schedule_type TEXT DEFAULT 'interval_minutes',
                interval_minutes INTEGER,
                interval_hours INTEGER,
                interval_days INTEGER,
                days_of_week TEXT,
                specific_dates TEXT,
                publish_time TEXT,
                cron_expression TEXT,
                next_publish_date TEXT,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS last_publish (
                channel_db_id INTEGER PRIMARY KEY,
                last_publish_time TEXT,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
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
                chat_id INTEGER PRIMARY KEY,
                owner_id INTEGER,
                is_hidden INTEGER DEFAULT 1
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
            CREATE TABLE IF NOT EXISTS user_groups_link (
                user_id INTEGER,
                chat_id INTEGER,
                PRIMARY KEY (user_id, chat_id)
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
                welcome_text TEXT,
                goodbye_enabled INTEGER DEFAULT 0,
                goodbye_text TEXT,
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
                word TEXT,
                chat_id INTEGER,
                added_by INTEGER,
                added_at TEXT,
                PRIMARY KEY (word, chat_id)
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
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                message TEXT,
                ticket_number INTEGER,
                status TEXT,
                created_at TEXT,
                replied INTEGER DEFAULT 0
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id INTEGER,
                referred_id INTEGER,
                referred_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_rewarded INTEGER DEFAULT 0,
                PRIMARY KEY (referrer_id, referred_id)
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
            CREATE TABLE IF NOT EXISTS user_levels (
                user_id INTEGER PRIMARY KEY,
                points INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1
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
                contest_id INTEGER PRIMARY KEY,
                winner_id INTEGER,
                announced_at TEXT
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_warnings (
                user_id INTEGER,
                chat_id INTEGER,
                warns INTEGER DEFAULT 0,
                reason TEXT,
                warned_by INTEGER,
                warned_at TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS moderation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                action TEXT,
                target_id INTEGER,
                admin_id INTEGER,
                reason TEXT,
                created_at TEXT
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
            CREATE TABLE IF NOT EXISTS group_rules (
                chat_id INTEGER PRIMARY KEY,
                rules_text TEXT,
                set_by INTEGER,
                set_at TEXT
            )
        """)
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS allowed_sendcode_user (
                id INTEGER PRIMARY KEY,
                user_id INTEGER
            )
        """)
        
        # إضافة المطور الأساسي كمشرف
        await conn.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (PRIMARY_OWNER_ID,))
        
        # إنشاء الفهارس
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_channels_user ON user_channels(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_banned_words_chat ON banned_words(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_group_admins_chat ON group_admins(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_hidden_admins_chat ON hidden_admins(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_hidden_owner_groups_owner ON hidden_owner_groups(owner_id)")
        
        await conn.commit()
        
        # إضافة إعدادات الإحالات الافتراضية
        for key, value in DEFAULT_REFERRAL_SETTINGS.items():
            await conn.execute("INSERT OR IGNORE INTO referral_settings (key, value) VALUES (?, ?)", (key, value))
        
        # إعدادات البوت الافتراضية
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('publish_interval', ?)", (str(DEFAULT_PUBLISH_INTERVAL_SECONDS),))
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_ticket_number', '0')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_backup', '1')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('force_subscribe_enabled', '0')")
        
        await conn.commit()
        
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح!")
        
    await execute_db(_init)

# ===================== نهاية الجزء الثاني المحسن =====================
# ===================== الجزء الثالث: واجهات المستخدم والكيبوردات الأساسية =====================

def get_auto_reply_keyboard(chat_id: int, settings: dict) -> InlineKeyboardMarkup:
    """إنشاء كيبورد إعدادات الردود التلقائية لمجموعة"""
    status_text = "🟢 مفعل" if settings['enabled'] else "🔴 معطل"
    admin_text = "👑 مشرفين فقط" if settings['only_admins'] else "👥 الجميع"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📝 الردود التلقائية: {status_text}",
            callback_data=f"{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}{chat_id}"
        )],
        [InlineKeyboardButton(
            f"👥 المستخدمون: {admin_text}",
            callback_data=f"{CallbackData.AUTO_REPLY_ADMINS_PREFIX}{chat_id}"
        )],
        [InlineKeyboardButton(
            "🔄 إعادة تعيين الردود",
            callback_data=f"{CallbackData.AUTO_REPLY_RESET_PREFIX}{chat_id}"
        )],
        [InlineKeyboardButton(
            "📊 إحصائيات الردود",
            callback_data=f"{CallbackData.AUTO_REPLY_STATS_PREFIX}{chat_id}"
        )],
        [InlineKeyboardButton(
            "🔙 رجوع",
            callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}"
        )]
    ])
# ===================== معالجات الأوامر =====================

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /start"""
    user_id = update.effective_user.id
    await db_register_user(user_id)
    if update.effective_user.username:
        await db_update_user_cache(user_id, update.effective_user.username, update.effective_user.first_name)
    await main_menu_callback(update, context)


async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /help"""
    user_id = update.effective_user.id
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'help'), reply_markup=keyboard)


async def trial_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /trial"""
    await trial_callback(update, context)


async def subscribe_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /subscribe"""
    await subscribe_menu_callback(update, context)


async def support_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /support"""
    await support_menu_callback(update, context)


async def support_reply_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /support_reply"""
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return
    
    args = context.args
    if len(args) < 2:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/support_reply معرف_المستخدم نص_الرد`")
        return
    
    target_id = int(args[0])
    reply_text = " ".join(args[1:])
    
    try:
        await context.bot.send_message(chat_id=target_id, text=f"📩 **رد الدعم:**\n\n{reply_text}")
        ticket_id = await db_get_last_ticket_id_for_user(target_id)
        if ticket_id:
            await db_mark_ticket_replied(ticket_id)
        await safe_send_markdown(context.bot, user_id, f"✅ تم إرسال الرد إلى المستخدم `{target_id}`")
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ فشل الإرسال: {str(e)[:100]}")


async def rank_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /rank"""
    await handle_text_callbacks(update, context)


async def top_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /top"""
    await handle_text_callbacks(update, context)


async def developer_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /developer"""
    await developer_callback(update, context)


async def updates_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /updates"""
    await updates_callback(update, context)


async def stats_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /stats"""
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels:
        await safe_send_markdown(context.bot, user_id, "📭 لا توجد قنوات مسجلة.")
        return
    
    total_posts = 0
    for ch in channels:
        total_posts += await db_get_posts_count(ch['id'])
    
    text = f"📊 **إحصائياتك**\n━━━━━━━━━━━━━━━━━━━━━━\n📡 عدد القنوات: {len(channels)}\n📝 إجمالي المنشورات: {total_posts}"
    await safe_send_markdown(context.bot, user_id, text)


async def sendcode_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /sendcode"""
    user_id = update.effective_user.id
    allowed_user = await db_get_allowed_sendcode_user()
    if user_id != PRIMARY_OWNER_ID and user_id != allowed_user:
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح!")
        return
    
    if context.args:
        # إرسال كود إلى قناة
        channel_id = context.args[0]
        code_text = " ".join(context.args[1:]) if len(context.args) > 1 else "رمز التحقق"
        try:
            await context.bot.send_message(chat_id=channel_id, text=code_text)
            await safe_send_markdown(context.bot, user_id, f"✅ تم إرسال الكود إلى `{channel_id}`")
        except Exception as e:
            await safe_send_markdown(context.bot, user_id, f"❌ فشل الإرسال: {str(e)[:100]}")
    else:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/sendcode معرف_القناة نص_الكود`")


async def lock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /lock"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    await db_set_chat_lock(chat_id, True, user_id)
    await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'locked'))


async def unlock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /unlock"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    await db_set_chat_lock(chat_id, False)
    await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'unlocked'))


async def schedule_post_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /schedule"""
    await handle_text_callbacks(update, context)


async def panel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /panel"""
    await admin_panel_callback(update, context)


async def set_log_channel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /set_log_channel"""
    await admin_set_log_channel_callback(update, context)


async def handle_moderation_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أوامر الإدارة (ban, mute, warn, kick, restrict, pin, unban)"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, "🔒 هذا الأمر يعمل فقط في المجموعات!")
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    command = update.message.text.split()[0][1:]  # اسم الأمر
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح!")
        return
    
    # استخراج المستخدم المستهدف
    if not update.message.reply_to_message:
        await safe_send_markdown(context.bot, user_id, "📌 **الاستخدام:** أضف رداً على رسالة المستخدم.")
        return
    
    target_id = update.message.reply_to_message.from_user.id
    if target_id == context.bot.id:
        await safe_send_markdown(context.bot, user_id, "❌ لا يمكن تنفيذ هذا الإجراء على البوت!")
        return
    
    reason = " ".join(context.args) if context.args else ""
    
    # تنفيذ الإجراء
    if command in ['ban', 'kick', 'mute', 'warn', 'restrict', 'unban']:
        success, msg = await execute_moderation_action(context.bot, chat_id, target_id, command, reason, None, user_id)
        await safe_send_markdown(context.bot, user_id, msg)
    elif command == 'pin':
        if update.message.reply_to_message:
            success, msg = await execute_pin(context.bot, chat_id, update.message.reply_to_message.message_id)
            await safe_send_markdown(context.bot, user_id, msg)
    else:
        await safe_send_markdown(context.bot, user_id, f"❌ أمر غير معروف: /{command}")


async def set_rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /set_rules"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, "🔒 هذا الأمر يعمل فقط في المجموعات!")
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح!")
        return
    
    if not context.args:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/set_rules نص القوانين`")
        return
    
    rules_text = " ".join(context.args)
    async def _set_rules(conn):
        await conn.execute("INSERT OR REPLACE INTO group_rules (chat_id, rules_text, set_by, set_at) VALUES (?, ?, ?, ?)",
                          (chat_id, rules_text, user_id, utc_now_iso()))
        await conn.commit()
    await execute_db(_set_rules)
    await safe_send_markdown(context.bot, chat_id, "✅ تم تعيين قوانين المجموعة بنجاح!")


async def rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /rules"""
    if not update.effective_chat:
        return
    
    chat_id = update.effective_chat.id
    async def _get_rules(conn):
        cur = await conn.execute("SELECT rules_text FROM group_rules WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        return row[0] if row else None
    rules = await execute_db(_get_rules)
    
    if rules:
        await safe_send_markdown(context.bot, chat_id, f"📋 **قوانين المجموعة**\n━━━━━━━━━━━━━━━━━━━━━━\n{rules}")
    else:
        await safe_send_markdown(context.bot, chat_id, "📋 لا توجد قوانين مسجلة لهذه المجموعة.")


async def syncgroup_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /syncgroup"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, "🔒 هذا الأمر يعمل فقط في المجموعات!")
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    chat_name = update.effective_chat.title or "بدون اسم"
    
    # تسجيل المجموعة
    await db_register_group(chat_id, chat_name, user_id, update.effective_chat.username)
    
    # التحقق من أن المستخدم مشرف
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            await db_register_hidden_owner_group(chat_id, user_id)
            await db_sync_group_admins(chat_id, context.bot, user_id)
            await invalidate_auth_cache(chat_id, user_id)
            await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'group_registered'))
        else:
            # إشعار المشرفين
            await notify_group_admins(context.bot, chat_id, user_id, chat_name)
            await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'activation_requested'))
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ خطأ: {str(e)[:100]}")


async def language_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /language"""
    await handle_text_callbacks(update, context)


async def register_hidden_owner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /register_hidden_owner"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, "🔒 هذا الأمر يعمل فقط في المجموعات!")
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ['administrator', 'creator']:
            await safe_send_markdown(context.bot, user_id, "❌ يجب أن تكون مشرفاً في المجموعة لتسجيل نفسك كمالك مخفي!")
            return
        
        if await db_is_hidden_owner(chat_id, user_id):
            await safe_send_markdown(context.bot, user_id, "⚠️ أنت مسجل بالفعل كمالك مخفي!")
            return
        
        await db_register_hidden_owner_group(chat_id, user_id)
        await invalidate_auth_cache(chat_id, user_id)
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'hidden_owner_registered'))
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ فشل التسجيل: {str(e)[:100]}")


async def add_hidden_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /add_hidden_admin"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, "🔒 هذا الأمر يعمل فقط في المجموعات!")
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await db_is_hidden_owner(chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 يجب أن تكون مالكاً مخفياً!")
        return
    
    args = context.args
    if not args:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/add_hidden_admin معرف_المستخدم`")
        return
    
    try:
        new_admin_id = int(args[0])
    except ValueError:
        await safe_send_markdown(context.bot, user_id, "❌ معرف غير صحيح!")
        return
    
    if await db_is_hidden_owner(chat_id, new_admin_id):
        await safe_send_markdown(context.bot, user_id, "⚠️ هذا المستخدم مالك مخفي بالفعل!")
        return
    
    if await db_add_hidden_admin(chat_id, new_admin_id, user_id):
        await invalidate_auth_cache(chat_id, new_admin_id)
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'hidden_admin_added').format(new_admin_id))
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل إضافة المشرف المخفي")


async def remove_hidden_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /remove_hidden_admin"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, "🔒 هذا الأمر يعمل فقط في المجموعات!")
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await db_is_hidden_owner(chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 يجب أن تكون مالكاً مخفياً!")
        return
    
    args = context.args
    if not args:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/remove_hidden_admin معرف_المستخدم`")
        return
    
    try:
        admin_id = int(args[0])
    except ValueError:
        await safe_send_markdown(context.bot, user_id, "❌ معرف غير صحيح!")
        return
    
    if await db_remove_hidden_admin(chat_id, admin_id):
        await invalidate_auth_cache(chat_id, admin_id)
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'hidden_admin_removed').format(admin_id))
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل إزالة المشرف المخفي")


async def list_hidden_admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /list_hidden_admins"""
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, "🔒 هذا الأمر يعمل فقط في المجموعات!")
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await db_is_hidden_owner(chat_id, user_id) and not await db_is_hidden_admin(chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح!")
        return
    
    admins = await db_get_hidden_admins(chat_id)
    if not admins:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'no_hidden_admins'))
        return
    
    text = get_text(user_id, 'hidden_admin_list').format(
        "\n".join([f"• `{a['admin_id']}` (أضيف بواسطة `{a['added_by']}`)" for a in admins])
    )
    await safe_send_markdown(context.bot, user_id, text)
# ===================== معالجات الكولباك =====================

async def cancel_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء الجلسة الحالية"""
    query = update.callback_query
    if query:
        await query.answer()
    context.user_data.clear()
    if query:
        await query.edit_message_text("❌ تم الإلغاء.")
    await main_menu_callback(update, context)


async def add_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة قناة جديدة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_CHANNEL_ID
    await safe_edit_markdown(query, "📡 أرسل معرف القناة (مثال: @channel أو -100123456)")


async def my_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قنوات المستخدم"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels:
        await safe_edit_markdown(query, "📭 لا توجد قنوات مسجلة.")
        return
    keyboard = []
    for ch in channels:
        status = "⛔" if ch['banned'] else "✅"
        keyboard.append([InlineKeyboardButton(f"{status} {ch['channel_name']}", callback_data=f"{CallbackData.CHANNELS_SELECT_PREFIX}{ch['id']}")])
        keyboard.append([InlineKeyboardButton("🗑️ حذف", callback_data=f"{CallbackData.CHANNELS_DELETE_PREFIX}{ch['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await safe_edit_markdown(query, "📡 **قنواتي**\nاختر قناة للتحكم بها:", reply_markup=InlineKeyboardMarkup(keyboard))


async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف قناة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    success = await db_delete_channel_by_id(user_id, channel_db_id)
    if success:
        await query.answer("✅ تم حذف القناة", show_alert=True)
    else:
        await query.answer("❌ فشل الحذف", show_alert=True)
    await my_channels_callback(update, context)


async def select_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار قناة نشطة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    await db_set_active_channel(user_id, channel_db_id)
    context.user_data['active_channel'] = channel_db_id
    await query.answer("✅ تم تحديد القناة", show_alert=True)
    await main_menu_callback(update, context)


async def add_15_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة 15 منشور"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel')
    if not active:
        active = await db_get_active_channel(user_id)
        if not active:
            await safe_edit_markdown(query, "⚠️ لا توجد قناة نشطة. أضف قناة أولاً.")
            return
        context.user_data['active_channel'] = active
    context.user_data['state'] = UserState.ADDING_POSTS
    context.user_data['post_count'] = 0
    context.user_data['max_posts'] = 15
    await safe_edit_markdown(query, "📝 **أضف 15 منشوراً**\nأرسل المنشور الأول (نص، صورة، فيديو، مستند، صوت، إلخ).")


async def publish_one_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نشر منشور واحد"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel')
    if not active:
        active = await db_get_active_channel(user_id)
        if not active:
            await safe_edit_markdown(query, "⚠️ لا توجد قناة نشطة.")
            return
        context.user_data['active_channel'] = active
    ch_info = await db_get_channel_info(active)
    if not ch_info:
        await safe_edit_markdown(query, "❌ القناة غير موجودة.")
        return
    try:
        channel_id = ch_info['channel_id']
        post = await db_get_next_post(active)
        if not post:
            await safe_edit_markdown(query, "📭 لا توجد منشورات غير منشورة.")
            return
        # محاولة النشر
        success = False
        try:
            if post['media_type'] == 'photo' and post['media_file_id']:
                await context.bot.send_photo(channel_id, post['media_file_id'], caption=post['text'] or None)
            elif post['media_type'] == 'video' and post['media_file_id']:
                await context.bot.send_video(channel_id, post['media_file_id'], caption=post['text'] or None)
            elif post['media_type'] == 'document' and post['media_file_id']:
                await context.bot.send_document(channel_id, post['media_file_id'], caption=post['text'] or None)
            elif post['media_type'] == 'audio' and post['media_file_id']:
                await context.bot.send_audio(channel_id, post['media_file_id'], caption=post['text'] or None)
            elif post['media_type'] == 'voice' and post['media_file_id']:
                await context.bot.send_voice(channel_id, post['media_file_id'], caption=post['text'] or None)
            elif post['media_type'] == 'animation' and post['media_file_id']:
                await context.bot.send_animation(channel_id, post['media_file_id'], caption=post['text'] or None)
            else:
                await context.bot.send_message(channel_id, post['text'] or "منشور")
            success = True
        except Exception as e:
            await safe_edit_markdown(query, f"❌ فشل النشر: {str(e)[:100]}")
            return
        if success:
            await db_mark_published(post['id'])
            await safe_edit_markdown(query, "✅ تم نشر المنشور بنجاح!")
    except Exception as e:
        await safe_edit_markdown(query, f"❌ خطأ: {str(e)[:100]}")


async def my_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المنشورات غير المنشورة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel')
    if not active:
        active = await db_get_active_channel(user_id)
        if not active:
            await safe_edit_markdown(query, "⚠️ لا توجد قناة نشطة.")
            return
        context.user_data['active_channel'] = active
    posts = await db_get_user_posts_for_channel(active, limit=20)
    if not posts:
        await safe_edit_markdown(query, "📭 لا توجد منشورات غير منشورة.")
        return
    text = "📋 **منشوراتي غير المنشورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    for idx, post in enumerate(posts[:10], 1):
        preview = post['text'][:30] + "..." if post['text'] and len(post['text']) > 30 else post['text'] or "بدون نص"
        text += f"{idx}. {preview}\n"
        keyboard.append([InlineKeyboardButton(f"🗑️ حذف {idx}", callback_data=f"{CallbackData.POSTS_DELETE_SINGLE_PREFIX}{post['id']}")])
    keyboard.append([InlineKeyboardButton("🗑️ حذف الكل", callback_data=f"{CallbackData.POSTS_CONFIRM_CLEAR_ALL_PREFIX}{active}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))


async def delete_single_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف منشور واحد"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    post_id = int(query.data.split(":")[-1])
    active = context.user_data.get('active_channel')
    if not active:
        active = await db_get_active_channel(user_id)
    if active:
        await db_delete_single_post(post_id, user_id, active)
    await my_posts_callback(update, context)


async def confirm_clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد حذف جميع المنشورات"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    active = int(query.data.split(":")[-1])
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم", callback_data=f"{CallbackData.POSTS_CLEAR_ALL_PREFIX}{active}")],
        [InlineKeyboardButton("❌ لا", callback_data=CallbackData.POSTS_MY)]
    ])
    await safe_edit_markdown(query, "⚠️ **تأكيد حذف جميع المنشورات**\nهل أنت متأكد؟", reply_markup=keyboard)


async def clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف جميع المنشورات"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    active = int(query.data.split(":")[-1])
    async def _clear(conn):
        await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (active,))
        await conn.commit()
    await execute_db(_clear)
    await safe_edit_markdown(query, "✅ تم حذف جميع المنشورات.")
    await my_posts_callback(update, context)


async def recycle_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعادة تدوير المنشورات"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel')
    if not active:
        active = await db_get_active_channel(user_id)
        if not active:
            await safe_edit_markdown(query, "⚠️ لا توجد قناة نشطة.")
            return
        context.user_data['active_channel'] = active
    await db_reset_posts_to_unpublished(active, user_id)
    await safe_edit_markdown(query, "♻️ تم إعادة تدوير جميع المنشورات.")


async def my_pending_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إحصائيات المنشورات غير المنشورة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel')
    if not active:
        active = await db_get_active_channel(user_id)
        if not active:
            await safe_edit_markdown(query, "⚠️ لا توجد قناة نشطة.")
            return
        context.user_data['active_channel'] = active
    unpublished = await db_unpublished_count(active)
    total = await db_get_posts_count(active)
    text = get_text(user_id, 'pending_stats').format(unpublished, total)
    await safe_edit_markdown(query, text)


async def my_full_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إحصائيات كاملة للمستخدم"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    total_posts = 0
    unpublished = 0
    for ch in channels:
        total_posts += await db_get_posts_count(ch['id'])
        unpublished += await db_unpublished_count(ch['id'])
    groups = await db_get_user_groups_count(user_id)
    auto = await db_auto_status(user_id)
    text = get_text(user_id, 'stats').format(len(channels), total_posts, unpublished, groups, "مفعل" if auto else "معطل")
    await safe_edit_markdown(query, text)


async def my_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض مجموعات المستخدم"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    groups = await db_get_user_groups(user_id)
    if not groups:
        await safe_edit_markdown(query, "📭 لا توجد مجموعات مسجلة.")
        return
    keyboard = []
    for g in groups:
        chat_name = g['chat_name'] or str(g['chat_id'])
        status = "⛔" if g['banned'] else "✅"
        keyboard.append([InlineKeyboardButton(f"{status} {chat_name}", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{g['chat_id']}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await safe_edit_markdown(query, "👥 **مجموعاتي**\nاختر مجموعة للتحكم بها:", reply_markup=InlineKeyboardMarkup(keyboard))


async def group_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعدادات المجموعة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    # التحقق من الصلاحية
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 الأمان", callback_data=f"{CallbackData.SECURITY_SELECT_GROUP}{chat_id}")],
        [InlineKeyboardButton("📝 الردود التلقائية", callback_data=f"{CallbackData.ADMIN_AUTO_REPLY_SELECT_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🚫 الكلمات المحظورة", callback_data=f"{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🛠️ إجراءات متقدمة", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")],
        [InlineKeyboardButton("📜 سجل الإجراءات", callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.GROUPS_MY)]
    ])
    await safe_edit_markdown(query, "⚙️ **إعدادات المجموعة**\nاختر الإعداد المطلوب:", reply_markup=keyboard)


async def settings_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الإعدادات"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    auto = await db_auto_status(user_id)
    auto_recycle = await db_get_auto_recycle(user_id)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔄 النشر التلقائي: {'مفعل' if auto else 'معطل'}", callback_data=CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH)],
        [InlineKeyboardButton(f"♻️ إعادة التدوير: {'مفعل' if auto_recycle else 'معطل'}", callback_data=CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    await safe_edit_markdown(query, get_text(user_id, 'settings'), reply_markup=keyboard)


async def toggle_auto_publish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل النشر التلقائي"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    current = await db_auto_status(user_id)
    new_status = not current
    await db_set_auto(user_id, new_status)
    await settings_menu_callback(update, context)


async def toggle_auto_recycle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل إعادة التدوير التلقائي"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    current = await db_get_auto_recycle(user_id)
    new_status = not current
    await db_set_auto_recycle(user_id, new_status)
    await settings_menu_callback(update, context)


async def schedule_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الجدولة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    context.user_data['schedule_channel_id'] = channel_db_id
    schedule = await db_get_schedule(channel_db_id)
    text = f"⏰ **إعدادات الجدولة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"النوع: {schedule['type']}\n"
    if schedule['type'] == 'interval_minutes':
        text += f"الفاصل: {schedule['interval_minutes']} دقيقة"
    elif schedule['type'] == 'interval_hours':
        text += f"الفاصل: {schedule['interval_hours']} ساعة"
    elif schedule['type'] == 'interval_days':
        text += f"الفاصل: {schedule['interval_days']} يوم"
    elif schedule['type'] == 'days':
        days = json.loads(schedule.get('days_of_week', '[]'))
        day_names = ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
        text += f"الأيام: {', '.join([day_names[d] for d in days])}"
    elif schedule['type'] == 'dates':
        dates = json.loads(schedule.get('specific_dates', '[]'))
        text += f"التواريخ: {', '.join(dates[:3])}{'...' if len(dates)>3 else ''}"
    elif schedule['type'] == 'cron':
        text += f"CRON: {schedule.get('cron_expression', 'غير محدد')}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱️ دقائق", callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_MINUTES_PREFIX}{channel_db_id}")],
        [InlineKeyboardButton("⏱️ ساعات", callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_HOURS_PREFIX}{channel_db_id}")],
        [InlineKeyboardButton("⏱️ أيام", callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_DAYS_PREFIX}{channel_db_id}")],
        [InlineKeyboardButton("📅 أيام الأسبوع", callback_data=f"{CallbackData.SCHEDULE_SET_DAYS_PREFIX}{channel_db_id}")],
        [InlineKeyboardButton("📅 تواريخ محددة", callback_data=f"{CallbackData.SCHEDULE_SET_DATES_PREFIX}{channel_db_id}")],
        [InlineKeyboardButton("🕐 وقت النشر", callback_data=f"{CallbackData.SCHEDULE_SET_PUBLISH_TIME_PREFIX}{channel_db_id}")],
        [InlineKeyboardButton("⏰ CRON", callback_data=f"schedule:set_cron:{channel_db_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    await safe_edit_markdown(query, text, reply_markup=keyboard)


async def set_interval_minutes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين الفاصل بالدقائق"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    context.user_data['schedule_channel_id'] = channel_db_id
    context.user_data['state'] = UserState.WAITING_INTERVAL_MINUTES
    await safe_edit_markdown(query, "⏱️ أرسل عدد الدقائق (مثال: 30)")


async def set_interval_hours_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين الفاصل بالساعات"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    context.user_data['schedule_channel_id'] = channel_db_id
    context.user_data['state'] = UserState.WAITING_INTERVAL_HOURS
    await safe_edit_markdown(query, "⏱️ أرسل عدد الساعات (مثال: 2)")


async def set_interval_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين الفاصل بالأيام"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    context.user_data['schedule_channel_id'] = channel_db_id
    context.user_data['state'] = UserState.WAITING_INTERVAL_DAYS
    await safe_edit_markdown(query, "⏱️ أرسل عدد الأيام (مثال: 1)")


async def set_cron_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين تعبير CRON"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    context.user_data['schedule_channel_id'] = channel_db_id
    context.user_data['state'] = UserState.WAITING_PUBLISH_TIME  # سنستخدم نفس الحالة
    await safe_edit_markdown(query, "⏰ أرسل تعبير CRON (مثال: 0 12 * * *)")


async def set_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار أيام الأسبوع"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    context.user_data['schedule_channel_id'] = channel_db_id
    context.user_data['selected_days'] = []
    keyboard = await build_days_keyboard(user_id, context)
    await safe_edit_markdown(query, "📅 اختر أيام النشر:", reply_markup=keyboard)


async def set_dates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين تواريخ محددة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    context.user_data['schedule_channel_id'] = channel_db_id
    context.user_data['state'] = UserState.WAITING_DATES
    await safe_edit_markdown(query, "📅 أرسل التواريخ مفصولة بفواصل (مثال: 2024-12-25,2025-01-01)")


async def set_publish_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين وقت النشر"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    context.user_data['schedule_channel_id'] = channel_db_id
    context.user_data['state'] = UserState.WAITING_PUBLISH_TIME
    await safe_edit_markdown(query, "🕐 أرسل وقت النشر (مثال: 14:30)")


async def day_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار يوم من أيام الأسبوع"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    day_index = int(query.data.split(":")[-1])
    selected = context.user_data.get('selected_days', [])
    if day_index in selected:
        selected.remove(day_index)
    else:
        selected.append(day_index)
    context.user_data['selected_days'] = sorted(selected)
    keyboard = await build_days_keyboard(user_id, context)
    await safe_edit_markdown(query, "📅 اختر أيام النشر:", reply_markup=keyboard)


async def save_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حفظ أيام الأسبوع"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channel_db_id = context.user_data.get('schedule_channel_id')
    selected = context.user_data.get('selected_days', [])
    if not selected:
        await safe_edit_markdown(query, "⚠️ لم تختر أي أيام.")
        return
    days_json = json.dumps(selected)
    await db_save_schedule(channel_db_id, 'days', days_of_week=days_json)
    await safe_edit_markdown(query, "✅ تم حفظ أيام النشر.")
    await schedule_menu_callback(update, context)


async def advanced_actions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الإجراءات المتقدمة للمجموعة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if chat_id == 0:
        # إذا كان 0، نطلب اختيار مجموعة
        groups = await db_get_user_groups(user_id)
        if not groups:
            await safe_edit_markdown(query, "📭 لا توجد مجموعات.")
            return
        keyboard = []
        for g in groups:
            keyboard.append([InlineKeyboardButton(g['chat_name'], callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{g['chat_id']}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)])
        await safe_edit_markdown(query, "🛠️ **اختر مجموعة للإجراءات المتقدمة:**", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    keyboard = get_advanced_group_actions_keyboard(chat_id)
    await safe_edit_markdown(query, "🛠️ **الإجراءات المتقدمة**\nاختر الإجراء:", reply_markup=keyboard)


async def advanced_mute_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار مدة الكتم من الإجراءات المتقدمة"""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    duration = int(parts[1])
    chat_id = int(parts[2])
    user_id = update.effective_user.id
    context.user_data['mute_duration'] = duration
    context.user_data['mute_chat_id'] = chat_id
    await safe_edit_markdown(query, f"⏱️ تم اختيار {duration} دقيقة.\nالآن أرسل معرف المستخدم (user_id) أو قم بالرد على رسالته.")


async def group_action_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حظر مستخدم"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    context.user_data['moderation_action'] = 'ban'
    context.user_data['moderation_chat_id'] = chat_id
    await safe_edit_markdown(query, "🛑 أرسل معرف المستخدم (user_id) أو قم بالرد على رسالته لحظره.")


async def group_action_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كتم مستخدم"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    # عرض خيارات المدة
    keyboard = get_advanced_mute_duration_keyboard(chat_id)
    await safe_edit_markdown(query, "🔇 **اختر مدة الكتم:**", reply_markup=keyboard)


async def group_action_warn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحذير مستخدم"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    context.user_data['moderation_action'] = 'warn'
    context.user_data['moderation_chat_id'] = chat_id
    await safe_edit_markdown(query, "⚠️ أرسل معرف المستخدم (user_id) أو قم بالرد على رسالته لتحذيره.")


async def group_action_kick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طرد مستخدم"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    context.user_data['moderation_action'] = 'kick'
    context.user_data['moderation_chat_id'] = chat_id
    await safe_edit_markdown(query, "👢 أرسل معرف المستخدم (user_id) أو قم بالرد على رسالته لطرده.")


async def group_action_restrict_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تقييد مستخدم"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    context.user_data['moderation_action'] = 'restrict'
    context.user_data['moderation_chat_id'] = chat_id
    await safe_edit_markdown(query, "🔒 أرسل معرف المستخدم (user_id) أو قم بالرد على رسالته لتقييده.")


async def group_action_pin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تثبيت رسالة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    context.user_data['moderation_action'] = 'pin'
    context.user_data['moderation_chat_id'] = chat_id
    await safe_edit_markdown(query, "📌 قم بالرد على الرسالة التي تريد تثبيتها.")


async def group_action_log_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سجل الإجراءات"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    log_text = await get_moderation_log(chat_id, limit=20)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]])
    await safe_edit_markdown(query, log_text, reply_markup=keyboard)


async def group_action_unban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء حظر مستخدم"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    context.user_data['moderation_action'] = 'unban'
    context.user_data['moderation_chat_id'] = chat_id
    await safe_edit_markdown(query, "🔓 أرسل معرف المستخدم (user_id) لإلغاء حظره.")


async def auto_reply_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل الردود التلقائية للمجموعة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    new_status = await db_toggle_auto_reply(chat_id)
    settings = await db_get_auto_reply_settings(chat_id)
    keyboard = get_auto_reply_keyboard(chat_id, settings)
    await safe_edit_markdown(query, f"✅ تم تغيير حالة الردود التلقائية إلى: {'مفعل' if new_status else 'معطل'}", reply_markup=keyboard)


async def auto_reply_admins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل وضع المشرفين فقط في الردود التلقائية"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    settings = await db_get_auto_reply_settings(chat_id)
    new_only_admins = not settings['only_admins']
    await db_set_auto_reply_only_admins(chat_id, new_only_admins)
    settings = await db_get_auto_reply_settings(chat_id)
    keyboard = get_auto_reply_keyboard(chat_id, settings)
    await safe_edit_markdown(query, f"✅ تم تغيير وضع الردود إلى: {'مشرفين فقط' if new_only_admins else 'الجميع'}", reply_markup=keyboard)


async def auto_reply_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعادة تعيين الردود التلقائية (تأكيد)"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم", callback_data=f"{CallbackData.AUTO_REPLY_CONFIRM_RESET_PREFIX}{chat_id}")],
        [InlineKeyboardButton("❌ لا", callback_data=f"{CallbackData.AUTO_REPLY_CANCEL_PREFIX}{chat_id}")]
    ])
    await safe_edit_markdown(query, "⚠️ **تأكيد إعادة تعيين الردود**\nسيتم حذف جميع الردود المخصصة لهذه المجموعة.", reply_markup=keyboard)


async def auto_reply_confirm_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد إعادة تعيين الردود التلقائية"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    async def _reset(conn):
        await conn.execute("DELETE FROM group_replies WHERE keyword LIKE ?", (f"{chat_id}:%",))
        await conn.commit()
    await execute_db(_reset)
    settings = await db_get_auto_reply_settings(chat_id)
    keyboard = get_auto_reply_keyboard(chat_id, settings)
    await safe_edit_markdown(query, "✅ تم إعادة تعيين جميع الردود المخصصة لهذه المجموعة.", reply_markup=keyboard)


async def auto_reply_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء إعادة تعيين الردود"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    settings = await db_get_auto_reply_settings(chat_id)
    keyboard = get_auto_reply_keyboard(chat_id, settings)
    await safe_edit_markdown(query, "❌ تم الإلغاء.", reply_markup=keyboard)


async def auto_reply_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إحصائيات الردود التلقائية للمجموعة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    async def _count(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM group_replies WHERE keyword LIKE ?", (f"{chat_id}:%",))
        return (await cur.fetchone())[0]
    count = await execute_db(_count)
    settings = await db_get_auto_reply_settings(chat_id)
    keyboard = get_auto_reply_keyboard(chat_id, settings)
    await safe_edit_markdown(query, f"📊 **إحصائيات الردود التلقائية**\n━━━━━━━━━━━━━━━━━━━━━━\nعدد الردود المخصصة: {count}\nالحالة: {'مفعلة' if settings['enabled'] else 'معطلة'}\nالوضع: {'مشرفين فقط' if settings['only_admins'] else 'الجميع'}", reply_markup=keyboard)


async def user_auto_reply_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل الردود التلقائية للمستخدم"""
    query = update.callback_query
    await query.answer()
    user_id = int(query.data.split(":")[-1])
    current = await db_get_user_auto_reply_status(user_id)
    new_status = not current
    await db_set_user_auto_reply_status(user_id, new_status)
    keyboard = get_user_auto_reply_keyboard(user_id, new_status)
    await safe_edit_markdown(query, f"✅ تم تغيير حالة الردود التلقائية إلى: {'مفعل' if new_status else 'معطل'}", reply_markup=keyboard)


async def admin_auto_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لوحة إدارة الردود التلقائية (اختيار مجموعة)"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    groups = await db_get_user_groups(user_id)
    if not groups:
        await safe_edit_markdown(query, "📭 لا توجد مجموعات.")
        return
    keyboard = []
    for g in groups:
        keyboard.append([InlineKeyboardButton(g['chat_name'], callback_data=f"{CallbackData.ADMIN_AUTO_REPLY_SELECT_PREFIX}{g['chat_id']}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)])
    await safe_edit_markdown(query, "📝 **اختر مجموعة لإدارة الردود التلقائية:**", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_auto_reply_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة الردود التلقائية لمجموعة محددة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    settings = await db_get_auto_reply_settings(chat_id)
    keyboard = get_auto_reply_keyboard(chat_id, settings)
    await safe_edit_markdown(query, f"📝 **إعدادات الردود التلقائية للمجموعة**\nاختر الإجراء:", reply_markup=keyboard)


async def panel_lock_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قفل المجموعة من لوحة التحكم"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    await db_set_chat_lock(chat_id, True, user_id)
    await query.answer("🔒 تم قفل المجموعة", show_alert=True)
    await group_settings_callback(update, context)


async def panel_unlock_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فتح المجموعة من لوحة التحكم"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    await db_set_chat_lock(chat_id, False)
    await query.answer("🔓 تم فتح المجموعة", show_alert=True)
    await group_settings_callback(update, context)


async def panel_close_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إغلاق لوحة التحكم"""
    query = update.callback_query
    await query.answer()
    await query.message.delete()


async def publish_all_channels_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نشر جميع المنشورات في جميع القنوات"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels:
        await safe_edit_markdown(query, "📭 لا توجد قنوات.")
        return
    published = 0
    failed = 0
    for ch in channels:
        ch_info = await db_get_channel_info(ch['id'])
        if not ch_info:
            continue
        channel_id = ch_info['channel_id']
        while True:
            post = await db_get_next_post(ch['id'])
            if not post:
                break
            try:
                if post['media_type'] == 'photo' and post['media_file_id']:
                    await context.bot.send_photo(channel_id, post['media_file_id'], caption=post['text'] or None)
                elif post['media_type'] == 'video' and post['media_file_id']:
                    await context.bot.send_video(channel_id, post['media_file_id'], caption=post['text'] or None)
                else:
                    await context.bot.send_message(channel_id, post['text'] or "منشور")
                await db_mark_published(post['id'])
                published += 1
            except:
                failed += 1
    await safe_edit_markdown(query, f"✅ تم النشر: {published} منشور\n❌ فشل: {failed}")


async def delete_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف مجموعة من قائمة المجموعات"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    async def _delete(conn):
        await conn.execute("DELETE FROM bot_groups WHERE chat_id=?", (chat_id,))
        await conn.execute("DELETE FROM group_admins WHERE chat_id=?", (chat_id,))
        await conn.execute("DELETE FROM hidden_admins WHERE chat_id=?", (chat_id,))
        await conn.execute("DELETE FROM hidden_owner_groups WHERE chat_id=?", (chat_id,))
        await conn.execute("DELETE FROM group_security WHERE chat_id=?", (chat_id,))
        await conn.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await conn.commit()
    await execute_db(_delete)
    await query.answer("✅ تم حذف المجموعة", show_alert=True)
    await my_groups_callback(update, context)


async def message_handler_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل في الخاص"""
    if update.message is None or update.effective_user is None:
        return
    user_id = update.effective_user.id
    text = update.message.text or update.message.caption or ""
    state = context.user_data.get('state', UserState.NONE)

    # معالجة حالات المستخدم
    if state == UserState.WAITING_CHANNEL_ID:
        channel_id = text.strip()
        if channel_id:
            channel_name = channel_id
            try:
                chat = await context.bot.get_chat(channel_id)
                channel_name = chat.title or channel_id
            except:
                pass
            result = await db_add_channel(user_id, channel_id, channel_name)
            if result:
                await safe_send_markdown(context.bot, user_id, get_text(user_id, 'channel_added').format(channel_name))
                await main_menu_callback(update, context)
            else:
                await safe_send_markdown(context.bot, user_id, get_text(user_id, 'channel_exists'))
        context.user_data['state'] = UserState.NONE
        return

    elif state == UserState.ADDING_POSTS:
        post_count = context.user_data.get('post_count', 0)
        max_posts = context.user_data.get('max_posts', 15)
        active = context.user_data.get('active_channel')
        if not active:
            active = await db_get_active_channel(user_id)
            if not active:
                await safe_send_markdown(context.bot, user_id, "⚠️ لا توجد قناة نشطة.")
                context.user_data['state'] = UserState.NONE
                return
            context.user_data['active_channel'] = active

        # حفظ المنشور
        media_type = "text"
        media_file_id = None
        if update.message.photo:
            media_type = "photo"
            media_file_id = update.message.photo[-1].file_id
        elif update.message.video:
            media_type = "video"
            media_file_id = update.message.video.file_id
        elif update.message.document:
            media_type = "document"
            media_file_id = update.message.document.file_id
        elif update.message.audio:
            media_type = "audio"
            media_file_id = update.message.audio.file_id
        elif update.message.voice:
            media_type = "voice"
            media_file_id = update.message.voice.file_id
        elif update.message.animation:
            media_type = "animation"
            media_file_id = update.message.animation.file_id

        if text or media_file_id:
            await db_save_posts(active, [(text, media_type, media_file_id)])
            post_count += 1
            context.user_data['post_count'] = post_count
            remaining = max_posts - post_count
            if remaining <= 0:
                context.user_data['state'] = UserState.NONE
                await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة {max_posts} منشورات بنجاح!")
                await main_menu_callback(update, context)
            else:
                await safe_send_markdown(context.bot, user_id, f"✅ تم حفظ المنشور {post_count}/{max_posts}\nأرسل المنشور التالي (متبقي {remaining}) أو اضغط /cancel للإلغاء.")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ أرسل محتوى صالح (نص، صورة، فيديو، إلخ).")
        return

    # الردود التلقائية في الخاص
    if state != UserState.NONE:
        return

    # ردود تلقائية عامة
    reply = get_reply_for_keyword(text)
    if reply:
        await update.message.reply_text(reply)

def get_user_auto_reply_keyboard(user_id: int, enabled: bool) -> InlineKeyboardMarkup:
    """إنشاء كيبورد إعدادات الردود التلقائية للمستخدم"""
    status_text = "🟢 مفعل" if enabled else "🔴 معطل"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📝 الردود التلقائية: {status_text}",
            callback_data=f"{CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX}{user_id}"
        )],
        [InlineKeyboardButton(
            "🔙 رجوع",
            callback_data=CallbackData.BACK
        )]
    ])

def get_replies_keyboard() -> InlineKeyboardMarkup:
    """إنشاء كيبورد إدارة الردود"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة رد", callback_data=CallbackData.ADMIN_ADD_REPLY),
         InlineKeyboardButton("📋 عرض الردود", callback_data=CallbackData.ADMIN_LIST_REPLIES)],
        [InlineKeyboardButton("🗑️ حذف رد", callback_data=CallbackData.ADMIN_DEL_REPLY),
         InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])

def get_group_banned_words_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """إنشاء كيبورد إدارة الكلمات المحظورة لمجموعة"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كلمة", callback_data=f"{CallbackData.BANNED_WORDS_ADD_PREFIX}{chat_id}"),
         InlineKeyboardButton("📋 عرض الكلمات", callback_data=f"{CallbackData.BANNED_WORDS_LIST_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🗑️ حذف كلمة", callback_data=f"{CallbackData.BANNED_WORDS_REMOVE_PREFIX}{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

def get_banned_words_admin_keyboard() -> InlineKeyboardMarkup:
    """إنشاء كيبورد إدارة الكلمات المحظورة العامة"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كلمة عامة", callback_data=CallbackData.ADMIN_ADD_BANNED_WORD),
         InlineKeyboardButton("📋 عرض الكلمات", callback_data=CallbackData.ADMIN_LIST_BANNED_WORDS)],
        [InlineKeyboardButton("🗑️ حذف كلمة", callback_data=CallbackData.ADMIN_REMOVE_BANNED_WORD),
         InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_BANNED_WORDS)]
    ])

def get_advanced_group_actions_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """إنشاء كيبورد الإجراءات المتقدمة لمجموعة"""
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
    """إنشاء كيبورد اختيار مدة الكتم"""
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
    """إنشاء كيبورد لوحة الأدمن"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'admin_users'), callback_data=CallbackData.ADMIN_USERS),
         InlineKeyboardButton("🚫 المستخدمون المحظورون", callback_data=CallbackData.ADMIN_BANNED_USERS)],
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
    """إنشاء كيبورد إعدادات الأمان"""
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
    """إنشاء كيبورد اختيار العقوبة"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 طرد", callback_data=f"{CallbackData.PENALTY_KICK}:{chat_id}"),
         InlineKeyboardButton("🛑 حظر", callback_data=f"{CallbackData.PENALTY_BAN}:{chat_id}")],
        [InlineKeyboardButton("🔇 كتم", callback_data=f"{CallbackData.PENALTY_MUTE}:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

def mute_duration_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """إنشاء كيبورد اختيار مدة الكتم للعقوبة"""
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
    """بناء كيبورد اختيار أيام الأسبوع للجدولة"""
    selected = context.user_data.get('selected_days', [])
    day_names = [get_text(uid, 'monday'), get_text(uid, 'tuesday'), get_text(uid, 'wednesday'),
                 get_text(uid, 'thursday'), get_text(uid, 'friday'), get_text(uid, 'saturday'),
                 get_text(uid, 'sunday')]
    kb_buttons = []
    for i in range(0, 7, 3):
        row = []
        for j in range(3):
            if i + j < 7:
                day_index = i + j
                name = day_names[day_index]
                mark = "✅ " if day_index in selected else ""
                row.append(InlineKeyboardButton(f"{mark}{name}", callback_data=f"{CallbackData.SCHEDULE_DAY_SELECT_PREFIX}{day_index}"))
        if row:
            kb_buttons.append(row)
    kb_buttons.append([
        InlineKeyboardButton("✔️ حفظ", callback_data=CallbackData.SCHEDULE_SAVE_DAYS),
        InlineKeyboardButton(get_text(uid, 'back'), callback_data=CallbackData.BACK)
    ])
    return InlineKeyboardMarkup(kb_buttons)

async def get_main_keyboard(user_id: int):
    """الحصول على الكيبورد الرئيسي للبوت مع البيانات المحدثة"""
    channels = await db_get_channels(user_id)
    active = None
    
    if channels:
        try:
            active = await db_get_active_channel(user_id)
            if active is not None:
                channel_exists = False
                for ch in channels:
                    if ch['id'] == active:
                        channel_exists = True
                        break
                if not channel_exists:
                    active = channels[0]['id']
                    await db_set_active_channel(user_id, active)
            else:
                active = channels[0]['id']
                await db_set_active_channel(user_id, active)
        except:
            active = channels[0]['id'] if channels else None
    
    cnt = 0
    ch_display = get_text(user_id, 'no_channels')
    
    if active is not None:
        try:
            cnt = await db_unpublished_count(active)
            ch_info = await db_get_channel_info(active)
            if ch_info:
                ch_tele_id = ch_info['channel_id'] if ch_info.get('channel_id') else "unknown"
                ch_name = ch_info['channel_name'] if ch_info.get('channel_name') else ch_tele_id
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
    
    title = get_text(user_id, 'main_title').format(
        BOT_NAME, user_id, my_groups, sub_text, ch_display, cnt, auto_text
    )
    
    updates_channel = None
    try:
        updates_channel = await db_get_updates_channel()
    except:
        updates_channel = None
    updates_url = f"https://t.me/{updates_channel}" if updates_channel else None
    
    keyboard = []

    # الصف الأول - المجموعات وإضافة قناة
    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'my_groups_btn'), callback_data=CallbackData.GROUPS_MY),
        InlineKeyboardButton(get_text(user_id, 'add_channel'), callback_data=CallbackData.CHANNELS_ADD)
    ])

    # الصف الثاني - قنواتي والإعدادات
    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'my_channels'), callback_data=CallbackData.CHANNELS_MY),
        InlineKeyboardButton(get_text(user_id, 'settings_btn'), callback_data=CallbackData.SETTINGS_MENU)
    ])

    # إذا كانت هناك قنوات، أضف أزرار المنشورات
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

    # أزرار إضافية
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
    
    # تنظيف الكيبورد من الصفوف الفارغة
    valid_keyboard = []
    for row in keyboard:
        if row and all(isinstance(btn, InlineKeyboardButton) for btn in row):
            valid_keyboard.append(row)
    
    if not valid_keyboard:
        valid_keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    
    return InlineKeyboardMarkup(valid_keyboard), title, active

# ===================== دوال الصلاحيات الإضافية =====================

async def is_bot_admin(user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم مشرفاً في البوت"""
    if user_id == PRIMARY_OWNER_ID:
        return True
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM bot_admins WHERE user_id=?", (user_id,))
        return await cur.fetchone() is not None
    return await execute_db(_check)

async def add_bot_admin(user_id: int) -> bool:
    """إضافة مشرف جديد للبوت"""
    if user_id == PRIMARY_OWNER_ID:
        return True
    async def _add(conn):
        await conn.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (user_id,))
        await conn.commit()
        return True
    return await execute_db(_add)

async def remove_bot_admin(user_id: int) -> bool:
    """إزالة مشرف من البوت"""
    if user_id == PRIMARY_OWNER_ID:
        return False
    async def _remove(conn):
        await conn.execute("DELETE FROM bot_admins WHERE user_id=?", (user_id,))
        await conn.commit()
        return True
    return await execute_db(_remove)

async def get_all_bot_admins() -> List[int]:
    """الحصول على قائمة مشرفي البوت"""
    async def _get(conn):
        cur = await conn.execute("SELECT user_id FROM bot_admins")
        return [row[0] for row in await cur.fetchall()]
    return await execute_db(_get)

# ===================== دوال التحقق من الصلاحيات =====================

async def is_user_bot(bot, user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم بوتاً"""
    try:
        user = await bot.get_chat(user_id)
        return user.is_bot
    except:
        return False

async def is_currently_admin_in_group(bot, chat_id: int, user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم مشرفاً حالياً في المجموعة"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def is_authorized_in_group(bot, chat_id: int, user_id: int) -> bool:
    """التحقق من أن المستخدم مصرح له في المجموعة (مشرف حقيقي أو مالك مخفي)"""
    # التحقق من التخزين المؤقت
    cache_key = f"auth_{chat_id}_{user_id}"
    if CACHETOOLS_AVAILABLE:
        if cache_key in _auth_cache:
            return _auth_cache[cache_key]
    else:
        if cache_key in _auth_cache:
            return _auth_cache[cache_key]
    
    # التحقق من الصلاحيات
    try:
        # 1. التحقق من المشرفين الحقيقيين في تيليجرام
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            # تحديث قاعدة البيانات
            await db_register_hidden_owner_group(chat_id, user_id)
            await db_sync_group_admins(chat_id, bot, user_id)
            await invalidate_auth_cache(chat_id, user_id)
            if CACHETOOLS_AVAILABLE:
                _auth_cache[cache_key] = True
            else:
                _auth_cache[cache_key] = True
            return True
        
        # 2. التحقق من المالك المخفي
        if await db_is_hidden_owner(chat_id, user_id):
            # تأكد من أن المالك المخفي لا يزال مشرفاً في تيليجرام
            if await db_is_real_admin(chat_id, user_id):
                if CACHETOOLS_AVAILABLE:
                    _auth_cache[cache_key] = True
                else:
                    _auth_cache[cache_key] = True
                return True
            else:
                # إذا كان المالك المخفي لم يعد مشرفاً، قم بإزالته
                async def _remove_owner(conn):
                    await conn.execute("DELETE FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
                    await conn.execute("DELETE FROM user_groups_link WHERE user_id=? AND chat_id=?", (user_id, chat_id))
                    await conn.commit()
                await execute_db(_remove_owner)
                await invalidate_auth_cache(chat_id, user_id)
                if CACHETOOLS_AVAILABLE:
                    _auth_cache[cache_key] = False
                else:
                    _auth_cache[cache_key] = False
                return False
        
        # 3. التحقق من المشرف المخفي
        if await db_is_hidden_admin(chat_id, user_id):
            if CACHETOOLS_AVAILABLE:
                _auth_cache[cache_key] = True
            else:
                _auth_cache[cache_key] = True
            return True
        
        # 4. التحقق من قاعدة البيانات (مشرف حقيقي)
        if await db_is_real_admin(chat_id, user_id):
            if CACHETOOLS_AVAILABLE:
                _auth_cache[cache_key] = True
            else:
                _auth_cache[cache_key] = True
            return True
        
        # 5. المستخدم المطور الأساسي
        if user_id == PRIMARY_OWNER_ID:
            if CACHETOOLS_AVAILABLE:
                _auth_cache[cache_key] = True
            else:
                _auth_cache[cache_key] = True
            return True
        
        if CACHETOOLS_AVAILABLE:
            _auth_cache[cache_key] = False
        else:
            _auth_cache[cache_key] = False
        return False
        
    except Exception as e:
        logger.error(f"خطأ في التحقق من صلاحيات المستخدم {user_id} في المجموعة {chat_id}: {e}")
        return False

async def check_bot_admin_permissions_group(bot, chat_id: int) -> dict:
    """التحقق من صلاحيات البوت في المجموعة"""
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if bot_member.status not in ['administrator', 'creator']:
            return {'can_act': False, 'reason': "البوت ليس مشرفاً في هذه المجموعة!"}
        
        permissions = {
            'can_delete_messages': bot_member.can_delete_messages,
            'can_restrict_members': bot_member.can_restrict_members,
            'can_promote_members': bot_member.can_promote_members,
            'can_pin_messages': bot_member.can_pin_messages,
            'can_invite_users': bot_member.can_invite_users
        }
        
        can_act = all([
            permissions['can_delete_messages'],
            permissions['can_restrict_members'],
            permissions['can_pin_messages']
        ])
        
        if not can_act:
            missing = []
            if not permissions['can_delete_messages']:
                missing.append("حذف الرسائل")
            if not permissions['can_restrict_members']:
                missing.append("تقييد الأعضاء")
            if not permissions['can_pin_messages']:
                missing.append("تثبيت الرسائل")
            return {
                'can_act': False,
                'reason': f"البوت يفتقد صلاحيات: {', '.join(missing)}",
                'permissions': permissions
            }
        return {'can_act': True, 'permissions': permissions}
    except Exception as e:
        return {'can_act': False, 'reason': f"خطأ في التحقق: {str(e)[:100]}"}

async def detect_owner_type(bot, chat_id: int) -> dict:
    """اكتشاف نوع المالك في المجموعة"""
    try:
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.status == 'creator':
                return {'user_id': admin.user.id, 'is_creator': True}
        if admins:
            return {'user_id': admins[0].user.id, 'is_creator': False}
        return {}
    except:
        return {}

# ===================== دوال الإجراءات والعقوبات =====================

async def execute_moderation_action(bot, chat_id: int, target_id: int, action: str, 
                                     reason: str = "", duration: int = None, admin_id: int = None) -> tuple:
    """تنفيذ إجراءات الإدارة في المجموعة"""
    try:
        if action == "ban":
            await bot.ban_chat_member(chat_id, target_id)
            await log_moderation_action(chat_id, action, target_id, admin_id, reason)
            return True, f"✅ تم حظر المستخدم `{target_id}`"
            
        elif action == "mute":
            permissions = ChatPermissions(can_send_messages=False)
            if duration and duration > 0:
                until_date = datetime.now(timezone.utc) + timedelta(minutes=duration)
                await bot.restrict_chat_member(chat_id, target_id, permissions, until_date=until_date)
                await log_moderation_action(chat_id, action, target_id, admin_id, reason, duration)
                return True, f"✅ تم كتم المستخدم `{target_id}` لمدة {duration} دقيقة"
            else:
                await bot.restrict_chat_member(chat_id, target_id, permissions)
                await log_moderation_action(chat_id, action, target_id, admin_id, reason, -1)
                return True, f"✅ تم كتم المستخدم `{target_id}` بشكل دائم"
                
        elif action == "warn":
            # تسجيل التحذير
            async def _warn(conn):
                cur = await conn.execute("SELECT warns FROM user_warnings WHERE user_id=? AND chat_id=?", (target_id, chat_id))
                row = await cur.fetchone()
                warns = (row[0] + 1) if row else 1
                await conn.execute("""
                    INSERT OR REPLACE INTO user_warnings (user_id, chat_id, warns, reason, warned_by, warned_at) 
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (target_id, chat_id, warns, reason, admin_id, utc_now_iso()))
                await conn.commit()
                return warns
            warns = await execute_db(_warn)
            await log_moderation_action(chat_id, action, target_id, admin_id, reason, warns)
            
            if warns >= 3:
                await bot.ban_chat_member(chat_id, target_id)
                return True, f"⚠️ تم تحذير المستخدم `{target_id}` (التحذير {warns}/3) وتم حظره تلقائياً!"
            return True, f"⚠️ تم تحذير المستخدم `{target_id}` (التحذير {warns}/3)"
            
        elif action == "kick":
            await bot.ban_chat_member(chat_id, target_id)
            await bot.unban_chat_member(chat_id, target_id)
            await log_moderation_action(chat_id, action, target_id, admin_id, reason)
            return True, f"✅ تم طرد المستخدم `{target_id}`"
            
        elif action == "restrict":
            permissions = ChatPermissions(
                can_send_messages=True,
                can_send_media=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
            await bot.restrict_chat_member(chat_id, target_id, permissions)
            await log_moderation_action(chat_id, action, target_id, admin_id, reason)
            return True, f"✅ تم تقييد المستخدم `{target_id}`"
            
        elif action == "unban":
            await bot.unban_chat_member(chat_id, target_id)
            await log_moderation_action(chat_id, action, target_id, admin_id, reason)
            return True, f"✅ تم إلغاء حظر المستخدم `{target_id}`"
            
        else:
            return False, f"❌ إجراء غير معروف: {action}"
            
    except Exception as e:
        return False, f"❌ فشل الإجراء: {str(e)[:100]}"

async def execute_pin(bot, chat_id: int, message_id: int) -> tuple:
    """تثبيت رسالة في المجموعة"""
    try:
        await bot.pin_chat_message(chat_id, message_id)
        return True, "✅ تم تثبيت الرسالة بنجاح!"
    except Exception as e:
        return False, f"❌ فشل التثبيت: {str(e)[:100]}"

async def apply_penalty_with_duration(bot, chat_id: int, user_id: int, penalty: str, duration: int):
    """تطبيق عقوبة مع مدة محددة"""
    try:
        if penalty == 'ban':
            await bot.ban_chat_member(chat_id, user_id)
        elif penalty == 'kick':
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id)
        elif penalty == 'mute':
            permissions = ChatPermissions(can_send_messages=False)
            if duration > 0:
                until_date = datetime.now(timezone.utc) + timedelta(minutes=duration)
                await bot.restrict_chat_member(chat_id, user_id, permissions, until_date=until_date)
            else:
                await bot.restrict_chat_member(chat_id, user_id, permissions)
        await log_moderation_action(chat_id, penalty, user_id, bot.id, f"تلقائي ({penalty})", duration)
    except Exception as e:
        logger.error(f"فشل تطبيق العقوبة {penalty} على المستخدم {user_id}: {e}")

async def log_moderation_action(chat_id: int, action: str, target_id: int, 
                                 admin_id: int = None, reason: str = "", duration: int = None):
    """تسجيل إجراءات الإدارة في قاعدة البيانات"""
    try:
        async def _log(conn):
            await conn.execute("""
                INSERT INTO moderation_log (chat_id, action, target_id, admin_id, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (chat_id, action, target_id, admin_id, reason[:500] if reason else "", utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
    except Exception as e:
        logger.error(f"فشل تسجيل الإجراء في سجل الإدارة: {e}")

async def delete_and_penalize(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    """حذف الرسالة وتطبيق عقوبة على المرسل"""
    try:
        await update.message.delete()
        await context.bot.send_message(update.effective_chat.id, message)
        
        # تطبيق العقوبة التلقائية
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        settings = await db_get_security_settings(chat_id)
        penalty = settings.get('delete_penalty', settings.get('auto_penalty', 'none'))
        if penalty != 'none':
            duration = settings.get('delete_penalty_duration', settings.get('auto_mute_duration', 60))
            await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, duration)
    except Exception as e:
        logger.error(f"فشل تطبيق العقوبة: {e}")

async def get_moderation_log(chat_id: int, limit: int = 20) -> str:
    """الحصول على سجل إجراءات الإدارة للمجموعة"""
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT action, target_id, admin_id, reason, created_at
            FROM moderation_log
            WHERE chat_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (chat_id, limit))
        return await cur.fetchall()
    
    logs = await execute_db(_get)
    if not logs:
        return "📜 **سجل الإجراءات**\n━━━━━━━━━━━━━━━━━━━━━━\n📭 لا توجد إجراءات مسجلة."
    
    text = "📜 **سجل الإجراءات**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    action_icons = {
        "ban": "🛑", "mute": "🔇", "warn": "⚠️", "kick": "👢", 
        "restrict": "🔒", "unban": "🔓", "pin": "📌"
    }
    
    for log in logs:
        try:
            dt = datetime.fromisoformat(log['created_at'])
            dt_mecca = utc_to_mecca(dt)
            time_str = dt_mecca.strftime("%Y-%m-%d %H:%M")
        except:
            time_str = "?"
        
        icon = action_icons.get(log['action'], "📌")
        text += f"{icon} {log['action']} | 👤 `{log['target_id']}` | 👑 `{log['admin_id']}` | 🕐 {time_str}\n"
        if log['reason']:
            text += f"📝 {log['reason']}\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"
    
    return text

# ===================== دوال معالجات النصوص (Callback Handlers) =====================

async def handle_text_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج عام للاستدعاءات النصية (rank, top, language, schedule_post)"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    data = query.data if query else context.user_data.get('callback_data', '')
    
    if data == "rank":
        level_data = await get_rank(user_id)
        text = f"📊 **رتبتك**\n━━━━━━━━━━━━━━━━━━━━━━\n🎯 المستوى: {level_data['level']}\n⭐ النقاط: {level_data['points']}\n📈 النقاط المطلوبة للمستوى التالي: {LEVEL_REQUIREMENTS.get(level_data['level'] + 1, 'MAX')}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
        if query:
            await safe_edit_markdown(query, text, reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
            
    elif data == "top":
        top_users = await get_top_users(limit=10)
        if not top_users:
            text = "📭 لا يوجد مستخدمون مسجلون بعد."
        else:
            text = "🏆 **أفضل 10 مستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            for idx, user in enumerate(top_users, 1):
                try:
                    user_info = await context.bot.get_chat(user['user_id'])
                    name = user_info.first_name or str(user['user_id'])
                except:
                    name = str(user['user_id'])
                medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
                text += f"{medal} {name[:20]} - المستوى {user['level']} ({user['points']} نقطة)\n"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
        if query:
            await safe_edit_markdown(query, text, reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
            
    elif data == "language":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("العربية 🇸🇦", callback_data="lang_ar"),
             InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")],
            [InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr"),
             InlineKeyboardButton("Türkçe 🇹🇷", callback_data="lang_tr")],
            [InlineKeyboardButton("中文 🇨🇳", callback_data="lang_zh"),
             InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
            [InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de"),
             InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es")],
            [InlineKeyboardButton("Italiano 🇮🇹", callback_data="lang_it"),
             InlineKeyboardButton("Português 🇵🇹", callback_data="lang_pt")],
            [InlineKeyboardButton("日本語 🇯🇵", callback_data="lang_ja"),
             InlineKeyboardButton("한국어 🇰🇷", callback_data="lang_ko")],
            [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
        ])
        if query:
            await safe_edit_markdown(query, get_text(user_id, 'welcome'), reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'welcome'), reply_markup=keyboard)
            
    elif data == "schedule_post":
        context.user_data['state'] = UserState.WAITING_SCHEDULE_POST
        msg = "📝 **جدولة منشور**\n\nأرسل المنشور بالصيغة التالية:\n`YYYY-MM-DD HH:MM نص المنشور`\n\nمثال:\n`2025-01-01 14:30 هذا منشور مجدول`"
        if query:
            await safe_edit_markdown(query, msg)
        else:
            await safe_send_markdown(context.bot, user_id, msg)

# ===================== دوال معالجات اللغة =====================

async def lang_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج تغيير اللغة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = query.data.split("_")[-1]
    
    if lang in SUPPORTED_LANGUAGES:
        await set_user_language(user_id, lang)
        await query.edit_message_text(f"✅ تم تغيير اللغة إلى {SUPPORTED_LANGUAGES[lang]}")
        await main_menu_callback(update, context)
    else:
        await query.edit_message_text("❌ لغة غير مدعومة")

# ===================== دوال القوائم الرئيسية =====================

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة إلى القائمة الرئيسية"""
    query = update.callback_query if update.callback_query else None
    if query:
        try:
            await query.answer()
        except:
            pass
    
    user_id = update.effective_user.id
    
    # التحقق من الاشتراك الإجباري
    if not await ensure_force_subscribe(update, context, user_id):
        return
    
    keyboard, title, active = await get_main_keyboard(user_id)
    if active:
        context.user_data['active_channel'] = active
    
    if query:
        try:
            await safe_edit_markdown(query, title, reply_markup=keyboard)
        except Exception as e:
            try:
                await query.edit_message_text(title, reply_markup=keyboard)
            except:
                pass
    else:
        try:
            await safe_send_markdown(context.bot, user_id, title, reply_markup=keyboard)
        except Exception as e:
            try:
                await context.bot.send_message(chat_id=user_id, text=title, reply_markup=keyboard)
            except:
                pass

async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الرجوع إلى القائمة الرئيسية"""
    await main_menu_callback(update, context)

# ===================== دوال معالجات المجموعات =====================

async def security_select_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار مجموعة لإعدادات الأمان"""
    if update.message:
        user_id = update.effective_user.id
        groups = await db_get_user_groups(user_id)
        if not groups:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد مجموعات مسجلة.")
            return
        
        keyboard = []
        for group in groups:
            chat_id = group['chat_id']
            chat_name = group['chat_name']
            keyboard.append([InlineKeyboardButton(f"🔐 {chat_name[:30]}", callback_data=f"{CallbackData.SECURITY_SELECT_GROUP}{chat_id}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
        
        await safe_send_markdown(
            context.bot, user_id, 
            "🔐 **اختر مجموعة لإعدادات الأمان:**\n\nاختر مجموعة من القائمة للتحكم في إعدادات الأمان الخاصة بها.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    query = update.callback_query
    if query:
        await query.answer()
        user_id = update.effective_user.id
        chat_id = int(query.data.split(":")[-1])
        
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
            return
        
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        
        # بناء النص
        status_texts = {
            'links': "🟢" if settings['links'] else "🔴",
            'mentions': "🟢" if settings['mentions'] else "🔴",
            'warn': "🟢" if settings['warn'] else "🔴",
            'slow_mode': "🟢" if settings['slow_mode'] else "🔴",
            'welcome_enabled': "🟢" if settings['welcome_enabled'] else "🔴",
            'goodbye_enabled': "🟢" if settings['goodbye_enabled'] else "🔴",
            'delete_banned_words': "🟢" if settings['delete_banned_words'] else "🔴",
            'delete_videos': "🟢" if settings['delete_videos'] else "🔴",
            'delete_service': "🟢" if settings['delete_service'] else "🔴",
            'delete_documents': "🟢" if settings['delete_documents'] else "🔴",
            'delete_stickers': "🟢" if settings['delete_stickers'] else "🔴",
            'delete_audio': "🟢" if settings['delete_audio'] else "🔴",
            'delete_animation': "🟢" if settings['delete_animation'] else "🔴"
        }
        
        penalty_texts = {
            'none': "🚫 لا شيء",
            'kick': "👢 طرد",
            'ban': "🛑 حظر",
            'mute': "🔇 كتم"
        }
        
        text = (
            f"🔐 **إعدادات الأمان للمجموعة**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 الروابط: {status_texts['links']}\n"
            f"@ المعرفات: {status_texts['mentions']}\n"
            f"⚠️ التحذير: {status_texts['warn']}\n"
            f"⏱️ الوضع البطيء: {status_texts['slow_mode']} ({settings['slow_mode_seconds']} ثانية)\n"
            f"🚫 الكلمات المحظورة: {status_texts['delete_banned_words']}\n"
            f"🎬 حذف الفيديوهات: {status_texts['delete_videos']}\n"
            f"🎵 حذف الصوتيات: {status_texts['delete_audio']}\n"
            f"🎞️ حذف المتحركات: {status_texts['delete_animation']}\n"
            f"🛠️ حذف رسائل الخدمة: {status_texts['delete_service']}\n"
            f"📄 حذف الملفات: {status_texts['delete_documents']}\n"
            f"🖼️ حذف الملصقات: {status_texts['delete_stickers']}\n"
            f"🎯 الترحيب: {status_texts['welcome_enabled']}\n"
            f"👋 الوداع: {status_texts['goodbye_enabled']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚖️ العقوبة: {penalty_texts.get(settings.get('auto_penalty', 'none'), '🚫 لا شيء')}\n"
            f"⏱️ مدة الكتم: {settings.get('auto_mute_duration', 60)} دقيقة\n"
            f"⚖️ عقوبة الحذف: {penalty_texts.get(settings.get('delete_penalty', 'none'), '🚫 لا شيء')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 **اختر الإعداد لتغييره:**"
        )
        
        await safe_edit_markdown(query, text, reply_markup=security_keyboard(chat_id))

async def security_refresh_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحديث قائمة المجموعات في لوحة الأمان"""
    await my_groups_callback(update, context)

async def _update_security_panel(query, chat_id: int, user_id: int):
    """تحديث لوحة الأمان بعد تغيير الإعدادات"""
    settings = await db_get_security_settings(chat_id, force_refresh=True)
    
    status_texts = {
        'links': "🟢" if settings['links'] else "🔴",
        'mentions': "🟢" if settings['mentions'] else "🔴",
        'warn': "🟢" if settings['warn'] else "🔴",
        'slow_mode': "🟢" if settings['slow_mode'] else "🔴",
        'welcome_enabled': "🟢" if settings['welcome_enabled'] else "🔴",
        'goodbye_enabled': "🟢" if settings['goodbye_enabled'] else "🔴",
        'delete_banned_words': "🟢" if settings['delete_banned_words'] else "🔴",
        'delete_videos': "🟢" if settings['delete_videos'] else "🔴",
        'delete_service': "🟢" if settings['delete_service'] else "🔴",
        'delete_documents': "🟢" if settings['delete_documents'] else "🔴",
        'delete_stickers': "🟢" if settings['delete_stickers'] else "🔴",
        'delete_audio': "🟢" if settings['delete_audio'] else "🔴",
        'delete_animation': "🟢" if settings['delete_animation'] else "🔴"
    }
    
    penalty_texts = {
        'none': "🚫 لا شيء",
        'kick': "👢 طرد",
        'ban': "🛑 حظر",
        'mute': "🔇 كتم"
    }
    
    text = (
        f"🔐 **إعدادات الأمان**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 الروابط: {status_texts['links']}\n"
        f"@ المعرفات: {status_texts['mentions']}\n"
        f"⚠️ التحذير: {status_texts['warn']}\n"
        f"⏱️ الوضع البطيء: {status_texts['slow_mode']} ({settings['slow_mode_seconds']} ثانية)\n"
        f"🚫 الكلمات المحظورة: {status_texts['delete_banned_words']}\n"
        f"🎬 حذف الفيديوهات: {status_texts['delete_videos']}\n"
        f"🎵 حذف الصوتيات: {status_texts['delete_audio']}\n"
        f"🎞️ حذف المتحركات: {status_texts['delete_animation']}\n"
        f"🛠️ حذف رسائل الخدمة: {status_texts['delete_service']}\n"
        f"📄 حذف الملفات: {status_texts['delete_documents']}\n"
        f"🖼️ حذف الملصقات: {status_texts['delete_stickers']}\n"
        f"🎯 الترحيب: {status_texts['welcome_enabled']}\n"
        f"👋 الوداع: {status_texts['goodbye_enabled']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚖️ العقوبة: {penalty_texts.get(settings.get('auto_penalty', 'none'), '🚫 لا شيء')}\n"
        f"⏱️ مدة الكتم: {settings.get('auto_mute_duration', 60)} دقيقة\n"
        f"⚖️ عقوبة الحذف: {penalty_texts.get(settings.get('delete_penalty', 'none'), '🚫 لا شيء')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 **اختر الإعداد لتغييره:**"
    )
    
    await safe_edit_markdown(query, text, reply_markup=security_keyboard(chat_id))

async def universal_security_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج عام لتغيير إعدادات الأمان"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    
    if len(parts) >= 3:
        setting = parts[1]
        chat_id = int(parts[2])
        
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("❌ غير مصرح", show_alert=True)
            return
        
        settings = await db_get_security_settings(chat_id)
        mapping = {
            'links': 'delete_links',
            'mentions': 'mentions',
            'warn': 'warn_message',
            'slow_mode': 'slow_mode',
            'welcome_enabled': 'welcome_enabled',
            'goodbye_enabled': 'goodbye_enabled',
            'delete_banned_words': 'delete_banned_words',
            'delete_videos': 'delete_videos',
            'delete_service': 'delete_service',
            'delete_documents': 'delete_documents',
            'delete_stickers': 'delete_stickers',
            'delete_audio': 'delete_audio',
            'delete_animation': 'delete_animation'
        }
        
        if setting in mapping:
            db_key = mapping[setting]
            current = settings.get(db_key, False)
            
            if setting == 'slow_mode':
                await db_set_security_settings(chat_id, **{db_key: not current})
            else:
                await db_set_security_settings(chat_id, **{db_key: not current})
            
            await security_audit.log(f"SECURITY_TOGGLE_{setting.upper()}", user_id, {"chat_id": chat_id, "new_value": not current}, "INFO")
            _security_cache.pop(chat_id, None)
            await cache_manager.delete(f"security_{chat_id}")
            await query.answer("✅ تم التحديث")
            await _update_security_panel(query, chat_id, user_id)

# ===================== دوال معالجات الأمان =====================

async def security_enable_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل جميع إعدادات الحذف"""
    await security_bulk_toggle(update, context, True)

async def security_disable_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعطيل جميع إعدادات الحذف"""
    await security_bulk_toggle(update, context, False)

async def security_bulk_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, enabled: bool):
    """تفعيل أو تعطيل جميع إعدادات الحذف دفعة واحدة"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    
    if enabled:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم، تفعيل الكل", callback_data=f"confirm_enable_all:{chat_id}")],
            [InlineKeyboardButton("❌ إلغاء", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
        ])
        await query.edit_message_text(
            "⚠️ **تأكيد تفعيل الكل**\n\nسيتم تفعيل جميع أنواع الحذف:\n• الفيديوهات\n• الصوتيات\n• المتحركات\n• رسائل الخدمة\n• الملفات\n• الملصقات\n\nهل أنت متأكد؟",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return
    else:
        keys = ['delete_videos', 'delete_audio', 'delete_animation', 'delete_service', 'delete_documents', 'delete_stickers']
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        for key in keys:
            settings[key] = False
        await db_set_security_settings(chat_id, **{k: settings[k] for k in keys})
        await security_audit.log("SECURITY_DISABLE_ALL", user_id, {"chat_id": chat_id}, "INFO")
        if chat_id in _security_cache:
            del _security_cache[chat_id]
        _security_cache.pop(chat_id, None)
        _security_cache_time.pop(chat_id, None)
        await cache_manager.delete(f"security_{chat_id}")
        await query.answer("✅ تم تعطيل الكل")
        await _update_security_panel(query, chat_id, user_id)

async def confirm_enable_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد تفعيل جميع إعدادات الحذف"""
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.split(":")[-1])
    user_id = update.effective_user.id
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    
    keys = ['delete_videos', 'delete_audio', 'delete_animation', 'delete_service', 'delete_documents', 'delete_stickers']
    settings = await db_get_security_settings(chat_id, force_refresh=True)
    for key in keys:
        settings[key] = True
    await db_set_security_settings(chat_id, **{k: settings[k] for k in keys})
    await security_audit.log("SECURITY_ENABLE_ALL", user_id, {"chat_id": chat_id}, "INFO")
    if chat_id in _security_cache:
        del _security_cache[chat_id]
    _security_cache.pop(chat_id, None)
    _security_cache_time.pop(chat_id, None)
    await cache_manager.delete(f"security_{chat_id}")
    await query.answer("✅ تم تفعيل الكل")
    await _update_security_panel(query, chat_id, user_id)

async def security_delete_penalty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار عقوبة الحذف"""
    query = update.callback_query
    await query.answer()
    chat_id = int(query.data.split(":")[-1])
    user_id = update.effective_user.id
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 لا شيء", callback_data=f"set_delete_penalty:none:{chat_id}"),
         InlineKeyboardButton("👢 طرد", callback_data=f"set_delete_penalty:kick:{chat_id}")],
        [InlineKeyboardButton("🛑 حظر", callback_data=f"set_delete_penalty:ban:{chat_id}"),
         InlineKeyboardButton("🔇 كتم", callback_data=f"set_delete_penalty:mute:{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع إلى الأمان", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])
    
    await query.edit_message_text(
        "⚖️ **اختر عقوبة حذف المحتوى**\n\nسيتم تطبيق هذه العقوبة عند حذف أي محتوى مخالف.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def set_delete_penalty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين عقوبة الحذف"""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    if len(parts) == 3:
        penalty = parts[1]
        chat_id = int(parts[2])
        user_id = update.effective_user.id
        
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
            return
        
        await db_set_security_settings(chat_id, delete_penalty=penalty, delete_penalty_duration=60)
        await security_audit.log("SECURITY_DELETE_PENALTY_SET", user_id, {"chat_id": chat_id, "penalty": penalty}, "INFO")
        await query.answer(f"✅ تم تعيين عقوبة الحذف إلى: {penalty}")
        await _update_security_panel(query, chat_id, user_id)

async def security_banned_words_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الكلمات المحظورة للمجموعة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('security_chat_id')
    
    if not chat_id:
        return
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['banned_words_chat_id'] = chat_id
    msg = "🚫 **إدارة الكلمات المحظورة للمجموعة**\n\nاختر الإجراء المناسب:"
    
    if query:
        await query.edit_message_text(msg, reply_markup=get_group_banned_words_keyboard(chat_id))
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=get_group_banned_words_keyboard(chat_id))

async def security_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إغلاق لوحة الأمان"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.delete()

# ===================== دوال الكلمات المحظورة =====================

async def banned_words_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة كلمة محظورة للمجموعة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('banned_words_chat_id')
    
    if not chat_id:
        return
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_GROUP_BANNED_WORD
    context.user_data['banned_words_chat_id'] = chat_id
    msg = "➕ **إضافة كلمة محظورة**\n\nأرسل الكلمة التي تريد إضافتها للكلمات المحظورة:\n\n📌 يمكنك استخدام * للتعبيرات النمطية (مثل: سكس.*)"
    
    if query:
        await query.edit_message_text(msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

async def banned_words_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الكلمات المحظورة للمجموعة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('banned_words_chat_id')
    
    if not chat_id:
        return
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    words = await db_get_banned_words(chat_id)
    
    if not words:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}{chat_id}")]])
        if query:
            await query.edit_message_text("📭 لا توجد كلمات محظورة في هذه المجموعة.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد كلمات محظورة في هذه المجموعة.", reply_markup=kb)
        return
    
    text = "🚫 **الكلمات المحظورة في المجموعة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for word in words[:20]:
        text += f"• `{word['word']}`"
        if word['added_by']:
            text += f" (أضيف بواسطة {word['added_by']})"
        text += "\n"
    
    if len(words) > 20:
        text += f"\n... و {len(words) - 20} كلمة أخرى"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}{chat_id}")]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def banned_words_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إزالة كلمة محظورة من المجموعة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('banned_words_chat_id')
    
    if not chat_id:
        return
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_REMOVE_GROUP_BANNED_WORD
    context.user_data['banned_words_chat_id'] = chat_id
    msg = "🗑️ **حذف كلمة محظورة**\n\nأرسل الكلمة التي تريد حذفها من الكلمات المحظورة:"
    
    if query:
        await query.edit_message_text(msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

# ===================== دوال العقوبات =====================

async def penalty_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة اختيار العقوبة التلقائية"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('security_chat_id')
    
    if not chat_id:
        return
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    msg = "⚖️ **اختر العقوبة التلقائية:**\n\nسيتم تطبيق هذه العقوبة عند مخالفة قواعد الحماية:"
    
    if query:
        await query.edit_message_text(msg, reply_markup=penalty_keyboard(chat_id))
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=penalty_keyboard(chat_id))

async def penalty_kick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين العقوبة إلى طرد"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('security_chat_id')
    
    if not chat_id:
        return
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    await db_set_security_settings(chat_id, auto_penalty='kick')
    await security_audit.log("PENALTY_KICK_SET", user_id, {"chat_id": chat_id}, "INFO")
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]])
    if query:
        await query.edit_message_text("✅ تم تعيين العقوبة التلقائية إلى: **طرد**", reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, "✅ تم تعيين العقوبة التلقائية إلى: **طرد**", reply_markup=kb)

async def penalty_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين العقوبة إلى حظر"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('security_chat_id')
    
    if not chat_id:
        return
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    await db_set_security_settings(chat_id, auto_penalty='ban')
    await security_audit.log("PENALTY_BAN_SET", user_id, {"chat_id": chat_id}, "INFO")
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]])
    if query:
        await query.edit_message_text("✅ تم تعيين العقوبة التلقائية إلى: **حظر**", reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, "✅ تم تعيين العقوبة التلقائية إلى: **حظر**", reply_markup=kb)

async def penalty_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين العقوبة إلى كتم"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('security_chat_id')
    
    if not chat_id:
        return
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['penalty_chat_id'] = chat_id
    msg = "🔇 **اختر مدة الكتم:**"
    
    if query:
        await query.edit_message_text(msg, reply_markup=mute_duration_keyboard(chat_id))
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=mute_duration_keyboard(chat_id))

async def penalty_mute_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار مدة الكتم للعقوبة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    data_parts = query.data.split(":") if query else context.user_data.get('penalty_mute_data', '').split(":")
    if len(data_parts) == 3:
        duration = data_parts[1]
        chat_id = int(data_parts[2])
        user_id = update.effective_user.id
        
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            if query:
                await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
            else:
                await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
            return
        
        if duration == "permanent":
            minutes = -1
            text = "دائم"
        else:
            minutes = int(duration)
            if minutes < 60:
                text = f"{minutes} دقيقة"
            elif minutes < 1440:
                text = f"{minutes // 60} ساعة"
            else:
                text = f"{minutes // 1440} يوم"
        
        await db_set_security_settings(chat_id, auto_penalty='mute', auto_mute_duration=minutes)
        await security_audit.log("PENALTY_MUTE_SET", user_id, {"chat_id": chat_id, "duration": minutes}, "INFO")
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]])
        if query:
            await query.edit_message_text(f"✅ تم تعيين العقوبة التلقائية إلى: **كتم {text}**", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين العقوبة التلقائية إلى: **كتم {text}**", reply_markup=kb)

# ===================== دوال الدعم والاشتراكات والترجمة والإحالات والتذكيرات =====================

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المساعدة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    
    if query:
        await safe_edit_markdown(query, get_text(user_id, 'help'), reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'help'), reply_markup=keyboard)

async def support_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الدعم"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    context.user_data['support_mode'] = True
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 كتابة تذكرة", callback_data=CallbackData.SUPPORT_TICKET)],
        [InlineKeyboardButton("❓ المساعدة", callback_data=CallbackData.SUPPORT_HELP)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    
    text = get_text(user_id, 'support_welcome')
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def support_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض مساعدة الدعم"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.SUPPORT_MENU)]
    ])
    
    text = get_text(user_id, 'support_help')
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def support_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كتابة تذكرة دعم"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    context.user_data['support_mode'] = True
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 إلغاء", callback_data=CallbackData.SUPPORT_MENU)]
    ])
    
    text = "📝 **اكتب رسالتك** (سيتم إرسالها كتذكرة دعم)\nيمكنك إلغاء العملية بالضغط على الزر أدناه."
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def support_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الرجوع من الدعم"""
    await support_menu_callback(update, context)

async def trial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل التجربة المجانية"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if await db_has_used_trial(user_id):
        if query:
            await query.edit_message_text(get_text(user_id, 'trial_used'))
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'trial_used'))
        return
    
    if await db_has_active_subscription(user_id):
        if query:
            await query.edit_message_text(get_text(user_id, 'already_subscribed'))
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'already_subscribed'))
        return
    
    await db_activate_trial(user_id)
    
    if query:
        await query.edit_message_text(get_text(user_id, 'trial'))
    else:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'trial'))
    
    await main_menu_callback(update, context)

async def subscribe_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الاشتراك"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if await db_has_active_subscription(user_id):
        days = await db_get_subscription_days_left(user_id)
        msg = f"✅ اشتراكك مفعل، متبقي {days} يوم\nشكراً لدعمك ❤️"
        if query:
            await query.edit_message_text(msg)
        else:
            await safe_send_markdown(context.bot, user_id, msg)
        return
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ 1 يوم - 5 نجوم", callback_data=CallbackData.BUY_SUBSCRIPTION_1),
         InlineKeyboardButton("⭐ 2 يوم - 9 نجوم", callback_data=CallbackData.BUY_SUBSCRIPTION_2)],
        [InlineKeyboardButton("⭐ شهر (30 يوم) - 50 نجمة", callback_data=CallbackData.BUY_SUBSCRIPTION_30),
         InlineKeyboardButton("⭐ 3 أشهر (90 يوم) - 120 نجمة", callback_data=CallbackData.BUY_SUBSCRIPTION_90)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    
    text = get_text(user_id, 'subscribe')
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def buy_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, days: int, price: int, title: str):
    """شراء اشتراك"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        await context.bot.send_invoice(
            chat_id=user_id,
            title=title,
            description=f"اشتراك {days} يوم",
            payload=f"sub_{days}_{price}",
            currency="XTR",
            prices=[LabeledPrice(label=f"اشتراك {days} يوم", amount=price)],
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False
        )
    except Exception as e:
        if "Stars" in str(e):
            if query:
                await query.edit_message_text("❌ الدفع بالنجوم غير مفعل حالياً، استخدم /trial")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ الدفع بالنجوم غير مفعل حالياً، استخدم /trial")
        else:
            if query:
                await query.edit_message_text(f"❌ خطأ: {str(e)[:100]}")
            else:
                await safe_send_markdown(context.bot, user_id, f"❌ خطأ: {str(e)[:100]}")

async def buy_subscription_1_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شراء اشتراك 1 يوم"""
    if update.callback_query:
        await update.callback_query.answer()
    await buy_subscription_callback(update, context, 1, 5, "اشتراك 1 يوم")

async def buy_subscription_2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شراء اشتراك 2 يوم"""
    if update.callback_query:
        await update.callback_query.answer()
    await buy_subscription_callback(update, context, 2, 9, "اشتراك 2 يوم")

async def buy_subscription_30_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شراء اشتراك شهر"""
    if update.callback_query:
        await update.callback_query.answer()
    await buy_subscription_callback(update, context, 30, 50, "اشتراك شهر")

async def buy_subscription_90_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شراء اشتراك 3 أشهر"""
    if update.callback_query:
        await update.callback_query.answer()
    await buy_subscription_callback(update, context, 90, 120, "اشتراك 3 أشهر")

async def developer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات المطور"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    text = f"""👑 **معلومات المطور**
━━━━━━━━━━━━━━━━━━━━━━
🤖 **البوت:** {BOT_NAME}
📦 **الإصدار:** 20.0.19
👨‍💻 **المطور:** @RelaxMgr

🔐 **الميزات الأمنية المتقدمة:**
• تشفير قاعدة البيانات بكلمة مرور (PBKDF2)
• نظام كشف النشاط المشبوه
• تخزين مؤقت محسن مع دعم Redis
• Pool اتصالات قاعدة البيانات
• نظام Rate Limiting متقدم
• مصادقة ثنائية (2FA)
• دعم جميع أنواع الميديا
• مترجم ذكي غير متزامن
• Health Check متقدم
• مراقبة الذاكرة التلقائية
• نظام المسابقات المتكامل
• واجهة ويب متكاملة
• تنقية النصوص باستخدام bleach
• 200 رد تلقائي للمجموعات مع أوزان
• نظام ردود ذكي مع تحليل المشاعر
• دعم المالك والمشرفين المخفيين المتعددين
• نظام ردود متقدم مع إعدادات لكل مجموعة
• إمكانية تفعيل/تعطيل الردود لكل مجموعة
• وضع المشرفين فقط للردود
• تشفير بيانات الكولباك
• حد أقصى للمنشورات غير المنشورة
• 🔞 كشف المحتوى غير اللائق (NSFW) مع تخزين مؤقت
• 📥 استيراد الكلمات المحظورة من ملف مع دعم Regex
• 🌐 دعم 12 لغة مع ترجمة تلقائية
• 📊 رسوم بيانية تفاعلية في واجهة الويب
• 📤 تصدير البيانات (CSV)
• 🌙 وضع Dark Mode
• ⏱️ جدولة CRON
• 👑 دعم كامل للمشرفين المتعددين
• 🎬 حذف الفيديوهات التلقائي
• 🎵 حذف الصوتيات التلقائي
• 🎞️ حذف المتحركات التلقائي
• 🛠️ حذف رسائل الخدمة التلقائي
• 📄 حذف الملفات التلقائي
• 🖼️ حذف الملصقات التلقائي
• ⚡ تفعيل/تعطيل الكل
• ⚖️ عقوبة خاصة للحذف
• 🔒 دعم كامل للمستخدمين المجهولين (Anonymous Admins)

⚡ **وضع السرعة:** {'مفعل' if not BATTERY_SAVER_MODE else 'معطل'}

━━━━━━━━━━━━━━━━━━━━━━
📞 **طرق التواصل:**
✅ **تيليجرام:** @RelaxMgr
✅ **البوت:** @{BOT_USERNAME}"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 تواصل مع المطور", url=f"https://t.me/RelaxMgr")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def updates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قناة التحديثات"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    updates_channel = await db_get_updates_channel()
    
    if updates_channel:
        text = f"""📢 **قناة التحديثات**
━━━━━━━━━━━━━━━━━━━━━━
📌 القناة: @{updates_channel}

📢 تابع القناة لمعرفة آخر التحديثات:
• ميزات جديدة ✨
• تحسينات الأداء ⚡
• إصلاحات الأخطاء 🔧
• عروض حصرية 🎁

🔗 اضغط على الزر أدناه لفتح القناة."""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 افتح القناة", url=f"https://t.me/{updates_channel}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
    else:
        text = """📢 **لم يتم تعيين قناة التحديثات بعد**

📌 **لتعيين قناة التحديثات:**
1. استخدم `/admin_panel`
2. اضغط على `⚙️ قناة التحديثات`
3. أرسل معرف القناة

⚠️ تأكد من أن البوت مشرف في القناة."""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 الذهاب للوحة الأدمن", callback_data=CallbackData.ADMIN_PANEL)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def referral_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة الإحالات"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    referral_code = await db_get_referral_code(user_id)
    if not referral_code:
        referral_code = await db_generate_referral_code(user_id)
    
    stats = await db_get_referral_stats(user_id)
    settings = await db_get_referral_settings()
    reward_days = int(settings.get('reward_days_per_referral', '3'))
    welcome_points = int(settings.get('welcome_bonus_points', '10'))
    
    text = get_text(user_id, 'referral_title').format(
        referral_code, BOT_USERNAME, referral_code, 
        stats['total_referrals'], stats['available_days'], reward_days, welcome_points
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'copy_link'), callback_data=f"{CallbackData.REFERRAL_COPY_LINK_PREFIX}{referral_code}"),
         InlineKeyboardButton(get_text(user_id, 'claim_reward'), callback_data=CallbackData.REFERRAL_CLAIM_REWARD)],
        [InlineKeyboardButton(get_text(user_id, 'referral_list'), callback_data=CallbackData.REFERRAL_LIST),
         InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def referral_copy_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نسخ رابط الإحالة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    referral_code = query.data.split(":")[-1] if query else context.user_data.get('referral_code')
    
    if not referral_code:
        return
    
    text = f"🔗 **رابط الإحالة الخاص بك:**\n`https://t.me/{BOT_USERNAME}?start=ref_{referral_code}`\n\nيمكنك الضغط مع الاستمرار على الرابط لنسخه."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.REFERRAL_MENU)]])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def referral_claim_reward_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """صرف مكافآت الإحالات"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    stats = await db_get_referral_stats(user_id)
    
    if stats['available_days'] <= 0:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.REFERRAL_MENU)]])
        if query:
            await safe_edit_markdown(query, get_text(user_id, 'no_reward_available'), reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'no_reward_available'), reply_markup=kb)
        return
    
    claimed = await db_claim_referral_reward(user_id)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.REFERRAL_MENU)]])
    
    if query:
        await safe_edit_markdown(query, get_text(user_id, 'reward_claimed').format(claimed), reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'reward_claimed').format(claimed), reply_markup=kb)

async def referral_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة المحالين"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    async def _get_referrals(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT r.referred_id, r.referred_at, r.is_rewarded, 
                   u.first_name, u.username 
            FROM referrals r 
            LEFT JOIN users_cache u ON r.referred_id = u.user_id 
            WHERE r.referrer_id = ? 
            ORDER BY r.referred_at DESC LIMIT 20
        """, (user_id,))
        return await cur.fetchall()
    
    referrals = await execute_db(_get_referrals)
    
    if not referrals:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.REFERRAL_MENU)]])
        if query:
            await safe_edit_markdown(query, get_text(user_id, 'no_referrals'), reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'no_referrals'), reply_markup=kb)
        return
    
    text = f"📊 **{get_text(user_id, 'referral_list')}**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for referred_id, referred_at, is_rewarded, first_name, username in referrals:
        try:
            referred_dt = datetime.fromisoformat(referred_at)
            referred_mecca = utc_to_mecca(referred_dt)
            date_str = referred_mecca.strftime("%Y-%m-%d")
        except:
            date_str = referred_at[:10] if referred_at else "تاريخ غير معروف"
        
        status = "✅" if is_rewarded else "⏳"
        name = first_name or username or str(referred_id)
        text += f"{status} {name} - {date_str}\n"
    
    text += "\n✅ = تم منح المكافأة  |  ⏳ = قيد الانتظار"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'claim_reward'), callback_data=CallbackData.REFERRAL_CLAIM_REWARD)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.REFERRAL_MENU)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

# ===================== دوال التذكيرات =====================

async def reminder_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة التذكيرات"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    settings = await db_get_user_reminder_settings(user_id)
    
    status_sub = "🟢 مفعل" if settings['subscription_reminder'] else "🔴 معطل"
    status_daily = "🟢 مفعل" if settings['daily_stats_reminder'] else "🔴 معطل"
    status_weekly = "🟢 مفعل" if settings['weekly_report'] else "🔴 معطل"
    
    text = get_text(user_id, 'reminder_title').format(
        status_sub, status_daily, status_weekly, settings['reminder_days_before']
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'reminder_sub'), callback_data=CallbackData.REMINDER_TOGGLE_SUB),
         InlineKeyboardButton(get_text(user_id, 'reminder_daily'), callback_data=CallbackData.REMINDER_TOGGLE_DAILY)],
        [InlineKeyboardButton(get_text(user_id, 'reminder_weekly'), callback_data=CallbackData.REMINDER_TOGGLE_WEEKLY),
         InlineKeyboardButton(get_text(user_id, 'reminder_days_btn'), callback_data=CallbackData.REMINDER_SET_DAYS)],
        [InlineKeyboardButton(get_text(user_id, 'reminder_lang_btn'), callback_data=CallbackData.REMINDER_SET_LANG),
         InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def reminder_toggle_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل تذكير الاشتراك"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    settings = await db_get_user_reminder_settings(user_id)
    await db_update_reminder_settings(user_id, subscription_reminder=not settings['subscription_reminder'])
    await reminder_menu_callback(update, context)

async def reminder_toggle_daily_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل التقرير اليومي"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    settings = await db_get_user_reminder_settings(user_id)
    await db_update_reminder_settings(user_id, daily_stats_reminder=not settings['daily_stats_reminder'])
    await reminder_menu_callback(update, context)

async def reminder_toggle_weekly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل التقرير الأسبوعي"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    settings = await db_get_user_reminder_settings(user_id)
    await db_update_reminder_settings(user_id, weekly_report=not settings['weekly_report'])
    await reminder_menu_callback(update, context)

async def reminder_set_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين عدد أيام التذكير"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_REMINDER_DAYS
    
    msg = "⏰ **عدد أيام التذكير**\n\nأرسل عدد الأيام التي تريد أن يتم تذكيرك بها قبل انتهاء الاشتراك (1-10 أيام):"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.REMINDER_MENU)]])
    
    if query:
        await query.edit_message_text(msg, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=kb)

async def reminder_set_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين لغة الإشعارات"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("العربية 🇸🇦", callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}ar"),
         InlineKeyboardButton("English 🇬🇧", callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}en")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.REMINDER_MENU)]
    ])
    
    msg = "🌐 **اختر لغة الإشعارات:**"
    
    if query:
        await query.edit_message_text(msg, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=keyboard)

async def reminder_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغيير لغة الإشعارات"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    lang = query.data.split(":")[-1] if query else context.user_data.get('reminder_lang')
    
    if not lang:
        return
    
    await db_update_reminder_settings(user_id, notification_lang=lang)
    await reminder_menu_callback(update, context)

# ===================== دوال الترجمة =====================

async def translation_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة الترجمة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    current_lang = await get_user_translation_language(user_id)
    
    lang_names = {
        'ar': 'العربية', 'en': 'English', 'fr': 'Français', 'tr': 'Türkçe',
        'zh': '中文', 'ru': 'Русский', 'de': 'Deutsch', 'es': 'Español',
        'it': 'Italiano', 'pt': 'Português', 'ja': '日本語', 'ko': '한국어'
    }
    
    if current_lang == 'off':
        status_text = get_text(user_id, 'translation_status_off')
    elif current_lang in lang_names:
        status_text = get_text(user_id, 'translation_status_on').format(lang_names[current_lang])
    else:
        status_text = get_text(user_id, 'translation_status_off')
    
    text = f"""🌐 **{get_text(user_id, 'translation_settings')}**
━━━━━━━━━━━━━━━━━━━━━━
📌 **الحالة:** {status_text}
{get_text(user_id, 'translation_how_it_works')}
━━━━━━━━━━━━━━━━━━━━━━
{get_text(user_id, 'translation_choose')}"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'translation_off'), callback_data=CallbackData.TRANSLATION_OFF)],
        [InlineKeyboardButton("🇸🇦 العربية", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}ar"),
         InlineKeyboardButton("🇬🇧 English", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}en")],
        [InlineKeyboardButton("🇫🇷 Français", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}fr"),
         InlineKeyboardButton("🇹🇷 Türkçe", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}tr")],
        [InlineKeyboardButton("🇨🇳 中文", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}zh"),
         InlineKeyboardButton("🇷🇺 Русский", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}ru")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}de"),
         InlineKeyboardButton("🇪🇸 Español", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}es")],
        [InlineKeyboardButton("🇮🇹 Italiano", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}it"),
         InlineKeyboardButton("🇵🇹 Português", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}pt")],
        [InlineKeyboardButton("🇯🇵 日本語", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}ja"),
         InlineKeyboardButton("🇰🇷 한국어", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}ko")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def translation_off_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إيقاف الترجمة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    await set_user_translation_language(user_id, 'off')
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    
    if query:
        await query.edit_message_text(get_text(user_id, 'translation_disabled'), reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'translation_disabled'), reply_markup=kb)

async def translation_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين لغة الترجمة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    lang = query.data.split(":")[-1] if query else context.user_data.get('translation_lang')
    
    if not lang:
        return
    
    await set_user_translation_language(user_id, lang)
    
    lang_names = {
        'ar': 'العربية', 'en': 'English', 'fr': 'Français', 'tr': 'Türkçe',
        'zh': '中文', 'ru': 'Русский', 'de': 'Deutsch', 'es': 'Español',
        'it': 'Italiano', 'pt': 'Português', 'ja': '日本語', 'ko': '한국어'
    }
    lang_name = lang_names.get(lang, lang)
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    
    if query:
        await query.edit_message_text(get_text(user_id, 'translation_enabled').format(lang_name), reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'translation_enabled').format(lang_name), reply_markup=kb)

# ==================================================================================================
# ===================== الجزء الرابع: لوحة الأدمن، معالجات الأحداث، العمليات الخلفية، الـ Main =====================
# ==================================================================================================

# ===================== دوال لوحة الأدمن (admin_*) =====================

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض لوحة الأدمن"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    if query:
        await safe_edit_markdown(query, "👑 **لوحة التحكم الإدارية**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإجراء المطلوب:", reply_markup=get_admin_keyboard(user_id))
    else:
        await safe_send_markdown(context.bot, user_id, "👑 **لوحة التحكم الإدارية**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإجراء المطلوب:", reply_markup=get_admin_keyboard(user_id))

async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة المستخدمين"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    users = await db_get_all_users()
    
    if not users:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text("📭 لا يوجد مستخدمون مسجلون.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا يوجد مستخدمون مسجلون.", reply_markup=kb)
        return
    
    text = "👥 **قائمة المستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for user in users[:50]:
        status = "🚫 محظور" if user['banned'] else "✅ نشط"
        text += f"• `{user['user_id']}` - {status}\n"
    
    if len(users) > 50:
        text += f"\nو {len(users)-50} آخرون..."
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def admin_banned_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المستخدمين المحظورين"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    users = await db_get_all_users()
    banned_users = [u for u in users if u['banned'] == 1]
    
    if not banned_users:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text("📭 لا يوجد مستخدمون محظورون.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا يوجد مستخدمون محظورون.", reply_markup=kb)
        return
    
    text = "🚫 **المستخدمون المحظورون**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for user in banned_users[:50]:
        text += f"• `{user['user_id']}`\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔓 إلغاء حظر الكل", callback_data=CallbackData.ADMIN_UNBAN_ALL_USERS)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def admin_unban_all_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء حظر جميع المستخدمين"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    async def _unban_all(conn):
        await conn.execute("UPDATE users SET banned=0 WHERE banned=1")
        await conn.commit()
    
    await execute_db(_unban_all)
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await query.edit_message_text("✅ تم إلغاء حظر جميع المستخدمين.", reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, "✅ تم إلغاء حظر جميع المستخدمين.", reply_markup=kb)

async def admin_all_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع قنوات المستخدمين"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    channels = await db_get_all_user_channels_no_limit()
    
    if not channels:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text("📭 لا توجد قنوات مسجلة.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد قنوات مسجلة.", reply_markup=kb)
        return
    
    text = "📡 **قنوات المستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    
    for idx, channel in enumerate(channels[:100], 1):
        status = "⛔ محظورة" if channel['banned'] else "✅ نشطة"
        ban_status_text = "🔓 إلغاء الحظر" if channel['banned'] else "⛔ حظر"
        ban_callback = f"{CallbackData.ADMIN_TOGGLE_CHANNEL_BAN_PREFIX}{channel['id']}"
        
        text += f"{idx}. {status} `{channel['channel_name']}`\n"
        text += f"   👤 المستخدم: `{channel['user_id']}`\n"
        text += f"   🆔 القناة: `{channel['channel_id']}`\n"
        keyboard.append([InlineKeyboardButton(ban_status_text, callback_data=ban_callback)])
    
    if len(channels) > 100:
        text += f"\nو {len(channels)-100} قناة أخرى..."
    
    keyboard.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_banned_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القنوات المحظورة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    channels = await db_all_users_channels(only_banned=True, limit=500)
    
    if not channels:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text("📭 لا توجد قنوات محظورة.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد قنوات محظورة.", reply_markup=kb)
        return
    
    text = "⛔ **قنوات المستخدمين المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for channel in channels[:50]:
        text += f"• المستخدم: `{channel['user_id']}` | القناة: {channel['channel_name']} (`{channel['channel_id']}`)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❤️ تنشيط الكل", callback_data=CallbackData.ADMIN_ACTIVATE_ALL_CHANNELS)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def admin_activate_all_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل جميع القنوات المحظورة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    async def _activate_all(conn):
        await conn.execute("UPDATE user_channels SET banned=0 WHERE banned=1")
        await conn.commit()
    
    await execute_db(_activate_all)
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await query.edit_message_text("✅ تم إلغاء حظر جميع قنوات المستخدمين.", reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, "✅ تم إلغاء حظر جميع قنوات المستخدمين.", reply_markup=kb)

async def admin_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع المجموعات"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    groups = await db_get_all_groups(only_banned=False)
    
    if not groups:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text("📭 لا توجد مجموعات مسجلة.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد مجموعات مسجلة.", reply_markup=kb)
        return
    
    text = "👥 **المجموعات المسجلة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    
    for group in groups[:50]:
        status = "⛔ محظورة" if group['banned'] else "✅ نشطة"
        ban_status_text = "🔓 إلغاء الحظر" if group['banned'] else "⛔ حظر"
        ban_callback = f"{CallbackData.ADMIN_TOGGLE_GROUP_BAN_PREFIX}{group['chat_id']}"
        
        text += f"• {group['chat_name']} (ID: `{group['chat_id']}`)\n"
        text += f"  أضيف بواسطة: `{group['added_by']}`\n"
        text += f"  الحالة: {status}\n"
        keyboard.append([InlineKeyboardButton(ban_status_text, callback_data=ban_callback)])
    
    if len(groups) > 50:
        text += f"\nو {len(groups)-50} أخرى..."
    
    keyboard.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_banned_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المجموعات المحظورة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    groups = await db_get_all_groups(only_banned=True)
    
    if not groups:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text("📭 لا توجد مجموعات محظورة.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد مجموعات محظورة.", reply_markup=kb)
        return
    
    text = "🚷 **المجموعات المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for group in groups[:50]:
        text += f"• {group['chat_name']} (ID: `{group['chat_id']}`)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔓 إلغاء حظر الكل", callback_data=CallbackData.ADMIN_UNBAN_ALL_GROUPS)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def admin_unban_all_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء حظر جميع المجموعات"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    async def _unban_groups(conn):
        await conn.execute("UPDATE bot_groups SET banned=0 WHERE banned=1")
        await conn.commit()
    
    await execute_db(_unban_groups)
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await query.edit_message_text("✅ تم إلغاء حظر جميع المجموعات.", reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, "✅ تم إلغاء حظر جميع المجموعات.", reply_markup=kb)

async def admin_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قنوات البوت"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    channels = await db_get_all_bot_channels(only_banned=False)
    
    if not channels:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text("📭 لا توجد قنوات أضيف إليها البوت.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد قنوات أضيف إليها البوت.", reply_markup=kb)
        return
    
    text = "📢 **قنوات البوت**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for channel in channels[:50]:
        text += f"• {channel['channel_name']} (ID: `{channel['channel_id']}`)\n"
        text += f"  أضيف بواسطة: `{channel['added_by']}`\n"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def admin_banned_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قنوات البوت المحظورة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    channels = await db_get_all_bot_channels(only_banned=True)
    
    if not channels:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text("📭 لا توجد قنوات بوت محظورة.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد قنوات بوت محظورة.", reply_markup=kb)
        return
    
    text = "🚫 **قنوات البوت المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for channel in channels[:50]:
        text += f"• {channel['channel_name']} (ID: `{channel['channel_id']}`)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔓 إلغاء حظر الكل", callback_data=CallbackData.ADMIN_UNBAN_ALL_BOT_CHANNELS)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def admin_unban_all_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء حظر جميع قنوات البوت"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    async def _unban_bot_channels(conn):
        await conn.execute("UPDATE bot_channels SET banned=0 WHERE banned=1")
        await conn.commit()
    
    await execute_db(_unban_bot_channels)
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await query.edit_message_text("✅ تم إلغاء حظر جميع قنوات البوت.", reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, "✅ تم إلغاء حظر جميع قنوات البوت.", reply_markup=kb)

async def admin_monitor_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مراقبة المستخدمين"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    all_users = await db_get_all_users()
    total_users = len(all_users)
    active_users = len([u for u in all_users if u['banned'] == 0])
    banned_users = len([u for u in all_users if u['banned'] == 1])
    
    admins_list = await get_all_bot_admins()
    admin_count = len(admins_list)
    
    all_channels = await db_all_users_channels()
    channels_count = len(all_channels)
    
    all_groups = await db_get_all_groups()
    groups_count = len(all_groups)
    
    text = (
        f"📂 **مراقبة المستخدمين**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 **إجمالي المستخدمين:** `{total_users}`\n"
        f"✅ **النشطاء:** `{active_users}`\n"
        f"🚫 **المحظورون:** `{banned_users}`\n"
        f"👑 **المشرفون:** `{admin_count}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 **قنوات المستخدمين:** `{channels_count}`\n"
        f"👥 **المجموعات المسجلة:** `{groups_count}`\n"
    )
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def admin_add_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة مشرف جديد"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_ADMIN_ID_ADD
    
    if query:
        await safe_edit_markdown(query, "👑 أرسل معرف المستخدم (user_id) لإضافته كمشرف:")
    else:
        await safe_send_markdown(context.bot, user_id, "👑 أرسل معرف المستخدم (user_id) لإضافته كمشرف:")

async def admin_remove_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إزالة مشرف"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    admins = await get_all_bot_admins()
    
    if not admins:
        if query:
            await query.edit_message_text("📭 لا يوجد مشرفون لإزالتهم.")
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا يوجد مشرفون لإزالتهم.")
        return
    
    text = "👑 **المشرفون الحاليون:**\n"
    for a in admins:
        text += f"- `{a}`\n"
    text += "\n🗑️ أرسل معرف المستخدم (user_id) لإزالته من المشرفين:"
    
    context.user_data['state'] = UserState.WAITING_ADMIN_ID_REMOVE
    
    if query:
        await safe_edit_markdown(query, text)
    else:
        await safe_send_markdown(context.bot, user_id, text)

async def admin_ram_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض حالة الرام"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    ram = get_ram_usage()
    text = f"🖥️ **حالة الرام**\n━━━━━━━━━━━━━━━━━━━━━━\n• الإجمالي: {ram['total']} GB\n• المستخدم: {ram['used']} GB\n• النسبة: {ram['percent']}%"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الإحصائيات العامة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    total, banned, posts, groups, channels = await db_stats()
    text = f"📊 **إحصائيات عامة**\n━━━━━━━━━━━━━━━━━━━━━━\n• المستخدمين: {total}\n• المحظورين: {banned}\n• المنشورات غير المنشورة: {posts}\n• المجموعات: {groups}\n• قنوات المستخدمين: {channels}"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def admin_metrics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض مقاييس الأداء"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    stats = metrics.get_stats()
    ram = get_ram_usage()
    
    text = f"""📈 **مقاييس الأداء**
━━━━━━━━━━━━━━━━━━━━━━
⏱️ **وقت التشغيل:** {int(stats['uptime'] / 3600)} ساعة {int((stats['uptime'] % 3600) / 60)} دقيقة
📊 **إجمالي الأوامر:** {stats['total_commands']}
⚡ **متوسط وقت الاستجابة:** {stats['avg_response_time']:.3f} ثانية
🖥️ **حالة النظام:**
• إجمالي الرام: {ram['total']} GB
• المستخدم: {ram['used']} GB
• النسبة: {ram['percent']}%
📋 **الأخطاء المسجلة:**
{chr(10).join([f'• {k}: {v}' for k, v in stats['errors'].items()]) if stats['errors'] else '• لا توجد أخطاء'}"""
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

# ===================== دوال النسخ الاحتياطي =====================

async def admin_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء نسخة احتياطية"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    try:
        await create_backup()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text("✅ تم إنشاء نسخة احتياطية مشفرة جديدة.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "✅ تم إنشاء نسخة احتياطية مشفرة جديدة.", reply_markup=kb)
    except Exception as e:
        error_id = log_error(e, {'user_id': user_id, 'action': 'admin_backup'})
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text(f"❌ فشل إنشاء النسخة (الرمز: `{error_id}`)", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, f"❌ فشل إنشاء النسخة (الرمز: `{error_id}`)", reply_markup=kb)

async def admin_restore_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استعادة نسخة احتياطية"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    backups = await list_backups()
    
    if not backups:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text("📭 لا توجد نسخ احتياطية.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد نسخ احتياطية.", reply_markup=kb)
        return
    
    kb = []
    for b in backups[:10]:
        kb.append([InlineKeyboardButton(b.name, callback_data=f"{CallbackData.ADMIN_RESTORE_BACKUP_SELECT_PREFIX}{b.name}")])
    kb.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)])
    
    if query:
        await query.edit_message_text("📂 **اختر النسخة الاحتياطية للاستعادة:**", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await safe_send_markdown(context.bot, user_id, "📂 **اختر النسخة الاحتياطية للاستعادة:**", reply_markup=InlineKeyboardMarkup(kb))

async def admin_restore_backup_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار نسخة للاستعادة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    backup_name = query.data.split(":")[-1] if query else context.user_data.get('restore_backup_name')
    if not backup_name:
        return
    
    backup_path = BACKUP_DIR / backup_name
    
    try:
        await restore_backup(backup_path)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text("✅ تم استعادة النسخة الاحتياطية المشفرة.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "✅ تم استعادة النسخة الاحتياطية المشفرة.", reply_markup=kb)
    except Exception as e:
        error_id = log_error(e, {'user_id': user_id, 'backup': backup_name})
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text(f"❌ فشل الاستعادة (الرمز: `{error_id}`)", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, f"❌ فشل الاستعادة (الرمز: `{error_id}`)", reply_markup=kb)

async def admin_backup_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعدادات النسخ الاحتياطي"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    auto = await db_get_auto_backup()
    status = "مفعل" if auto else "معطل"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 تبديل النسخ التلقائي", callback_data=CallbackData.ADMIN_TOGGLE_AUTO_BACKUP)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    text = f"""⚙️ **إعدادات النسخ الاحتياطي**
━━━━━━━━━━━━━━━━━━━━━━
• النسخ التلقائي: {status}
• تشفير النسخ: ✅ مفعل
• الحد الأقصى للنسخ: {MAX_BACKUPS}

يمكنك تبديل الحالة بالزر أدناه."""
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def admin_toggle_auto_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل النسخ الاحتياطي التلقائي"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    auto = await db_get_auto_backup()
    new_auto = not auto
    await db_set_auto_backup(new_auto)
    status = "مفعل" if new_auto else "معطل"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_BACKUP_SETTINGS)]])
    
    if query:
        await query.edit_message_text(f"✅ تم تغيير إعداد النسخ التلقائي إلى: {status}", reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, f"✅ تم تغيير إعداد النسخ التلقائي إلى: {status}", reply_markup=kb)

async def admin_change_interval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغيير وقت النشر العام"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    current = await db_get_publish_interval()
    current_min = current // 60
    
    context.user_data['state'] = UserState.WAITING_INTERVAL_MINUTES
    context.user_data['admin_interval'] = True
    
    msg = f"⏱️ **وقت النشر العام الحالي:** {current_min} دقيقة\n\n📌 **ملاحظة:** هذا الإعداد يؤثر على الفاصل الزمني بين دورات النشر.\nأرسل العدد الجديد من الدقائق (الحد الأدنى 1 دقيقة، الحد الأقصى 1440 دقيقة = 24 ساعة):"
    
    if query:
        await safe_edit_markdown(query, msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

async def admin_send_update_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نشر تحديث في قناة التحديثات"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_UPDATE_TEXT
    
    msg = "📢 أرسل نص التحديث الذي تريد نشره في قناة التحديثات:"
    
    if query:
        await safe_edit_markdown(query, msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

async def admin_set_update_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين قناة التحديثات"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_UPDATE_CHANNEL
    
    msg = """⚙️ **تعيين قناة التحديثات**

📢 أرسل معرف قناة التحديثات:

• `@username` (مثل: @my_channel)
• أو المعرف الرقمي (مثل: -1001234567890)

⚠️ **تنبيهات مهمة:**
• تأكد من أن البوت مشرف في القناة
• تأكد من أن البوت لديه صلاحية الإرسال
• القناة يجب أن تكون عامة (Public)"""
    
    if query:
        await safe_edit_markdown(query, msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

async def admin_show_update_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قناة التحديثات الحالية"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    channel = await db_get_updates_channel()
    
    if channel:
        text = f"📢 **قناة التحديثات الحالية:**\n`@{channel}`"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 فتح القناة", url=f"https://t.me/{channel}")],
            [InlineKeyboardButton("🔄 تغيير القناة", callback_data=CallbackData.ADMIN_SET_UPDATE_CHANNEL)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
        ])
    else:
        text = "📢 **لم يتم تعيين قناة تحديثات بعد**"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ تعيين قناة", callback_data=CallbackData.ADMIN_SET_UPDATE_CHANNEL)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
        ])
    
    await safe_edit_markdown(query, text, reply_markup=keyboard)

async def admin_updates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات التحديثات"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    channel = await db_get_updates_channel()
    text = f"📢 **قناة التحديثات الحالية:** @{channel}\n\nيمكنك تغييرها باستخدام زر '⚙️ قناة التحديثات'"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

# ===================== دوال الاشتراك الإجباري =====================

async def admin_force_subscribe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل الاشتراك الإجباري"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    enabled = await db_get_force_subscribe_status()
    new_status = not enabled
    await db_set_force_subscribe_status(new_status)
    status_text = "مفعل" if new_status else "معطل"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await query.edit_message_text(f"✅ تم {status_text} الاشتراك الإجباري.", reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, f"✅ تم {status_text} الاشتراك الإجباري.", reply_markup=kb)

async def admin_set_force_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين قناة الاشتراك الإجباري"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_FORCE_CHANNEL
    
    msg = "⚙️ أرسل معرف قناة الاشتراك الإجباري (مثال: @channel_username):"
    
    if query:
        await safe_edit_markdown(query, msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

# ===================== دوال البث والإرسال الجماعي =====================

async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة لجميع المستخدمين"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_BROADCAST
    
    msg = "📨 أرسل النص الذي تريد إرساله إلى جميع المستخدمين:"
    
    if query:
        await safe_edit_markdown(query, msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

async def admin_confirm_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد إرسال البث"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    broadcast_text = context.user_data.get('broadcast_text', '')
    
    if not broadcast_text:
        if query:
            await query.edit_message_text("❌ لا يوجد نص للإرسال")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ لا يوجد نص للإرسال")
        return
    
    # التحقق من النص
    dangerous_patterns = [r'<script', r'javascript:', r'data:', r'vbscript:', r'<\?php', r'<%', r'{%']
    for pattern in dangerous_patterns:
        if re.search(pattern, broadcast_text, re.IGNORECASE):
            if query:
                await query.edit_message_text("❌ النص يحتوي على كود ضار! تم منع الإرسال.")
            else:
                await safe_send_markdown(context.bot, user_id, "❌ النص يحتوي على كود ضار! تم منع الإرسال.")
            return
    
    if len(broadcast_text) > 4000:
        if query:
            await query.edit_message_text("❌ النص طويل جداً (الحد الأقصى 4000 حرف)")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ النص طويل جداً (الحد الأقصى 4000 حرف)")
        return
    
    if query:
        await query.edit_message_text("📨 جاري الإرسال... يرجى الانتظار")
    else:
        await safe_send_markdown(context.bot, user_id, "📨 جاري الإرسال... يرجى الانتظار")
    
    async def _get_active_users(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE banned = 0")
        return [row[0] for row in await cur.fetchall()]
    
    users = await execute_db(_get_active_users)
    sent = 0
    failed = 0
    
    if not users:
        if query:
            await query.edit_message_text("📭 لا يوجد مستخدمين نشطين لإرسال الرسالة لهم.")
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا يوجد مستخدمين نشطين لإرسال الرسالة لهم.")
        return
    
    sem = asyncio.Semaphore(20)
    
    async def send_one(uid):
        async with sem:
            try:
                await safe_send_markdown(context.bot, uid, broadcast_text)
                return True
            except:
                return False
    
    tasks = [send_one(uid) for uid in users]
    results = await asyncio.gather(*tasks)
    sent = sum(results)
    failed = len(results) - sent
    
    context.user_data.pop('broadcast_text', None)
    context.user_data.pop('state', None)
    
    msg = f"✅ **تم إرسال الرسالة**\n\n📨 تم الإرسال إلى: {sent} مستخدم\n❌ فشل الإرسال إلى: {failed} مستخدم"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await query.edit_message_text(msg, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=kb)

# ===================== دوال التذاكر =====================

async def admin_support_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تذاكر الدعم"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    tickets = await db_get_all_tickets(limit=20)
    
    if not tickets:
        if query:
            await query.edit_message_text("📭 لا توجد تذاكر دعم مسجلة")
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد تذاكر دعم مسجلة")
        return
    
    text = "📋 **تذاكر الدعم**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    
    for ticket in tickets:
        try:
            created_utc = datetime.fromisoformat(ticket['created_at'])
            created_mecca = utc_to_mecca(created_utc)
            created_str = created_mecca.strftime("%Y-%m-%d %H:%M")
        except:
            created_str = ticket['created_at']
        
        status_icon = "🟡" if ticket['status'] == "pending" else "🟢"
        msg_preview = ticket['message'][:40] + "..." if len(ticket['message']) > 40 else ticket['message']
        
        text += f"\n{status_icon} #{ticket['ticket_number']} | 👤 {ticket['username']}\n"
        text += f"🆔 `{ticket['user_id']}` | 📅 {created_str}\n"
        text += f"📝 {msg_preview}\n"
        text += f"💡 `/support_reply {ticket['user_id']} نص الرد`\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def admin_delete_all_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف جميع التذاكر"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    confirm_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، احذف الكل", callback_data=CallbackData.ADMIN_CONFIRM_DELETE_TICKETS),
         InlineKeyboardButton("❌ لا، إلغاء", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    if query:
        await query.edit_message_text("⚠️ **تأكيد حذف جميع التذاكر**\n\nهل أنت متأكد من حذف جميع تذاكر الدعم؟", reply_markup=confirm_kb)
    else:
        await safe_send_markdown(context.bot, user_id, "⚠️ **تأكيد حذف جميع التذاكر**\n\nهل أنت متأكد من حذف جميع تذاكر الدعم؟", reply_markup=confirm_kb)

async def admin_confirm_delete_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد حذف جميع التذاكر"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    count = await db_delete_all_tickets()
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await query.edit_message_text(f"✅ تم حذف {count} تذكرة بنجاح.", reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, f"✅ تم حذف {count} تذكرة بنجاح.", reply_markup=kb)

# ===================== دوال صلاحيات /sendcode =====================

async def admin_manage_sendcode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة صلاحية /sendcode"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    allowed_user = await db_get_allowed_sendcode_user()
    
    if allowed_user:
        current_text = f"👤 المستخدم الحالي المصرح له بـ /sendcode:\n`{allowed_user}`"
    else:
        current_text = "📭 لم يتم تعيين مستخدم مصرح له بـ /sendcode."
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ تعيين مستخدم جديد", callback_data=CallbackData.ADMIN_SET_SENDCODE_USER)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    if query:
        await safe_edit_markdown(query, current_text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, current_text, reply_markup=keyboard)

async def admin_set_sendcode_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين مستخدم لصلاحية /sendcode"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_SENDCODE_USER
    
    msg = "➕ أرسل معرف المستخدم (user_id) الذي تريد منحه صلاحية استخدام أمر /sendcode:"
    
    if query:
        await query.edit_message_text(msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

# ===================== دوال قناة التقارير =====================

async def admin_show_log_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قناة التقارير الحالية"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    log_ch = await db_get_log_channel_id()
    
    if log_ch:
        text = f"📋 **قناة التقارير الحالية:**\n`{log_ch}`\n\nيمكنك تغييرها باستخدام زر 'تعيين قناة التقارير'."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await safe_edit_markdown(query, text, reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)
    else:
        text = "📋 **لم يتم تعيين قناة تقارير بعد.**\nاستخدم زر 'تعيين قناة التقارير' لتعيينها."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
        if query:
            await query.edit_message_text(text, reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def admin_set_log_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين قناة التقارير"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_LOG_CHANNEL
    
    msg = """📢 **تعيين قناة التقارير**

أرسل معرف القناة (ID) أو معرف المستخدم (@username) للقناة التي تريد استقبال التقارير فيها.

مثال: `-1001234567890` أو `@channel_username`

⚠️ تأكد من أن البوت مشرف في القناة ولديه صلاحية إرسال الرسائل."""
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_PANEL)]])
    
    if query:
        await query.edit_message_text(msg, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=kb)

# ===================== دوال الردود التلقائية =====================

async def admin_replies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة الردود التلقائية"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    msg = "💬 **إدارة ردود المجموعة**"
    
    if query:
        await query.edit_message_text(msg, reply_markup=get_replies_keyboard())
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=get_replies_keyboard())

async def admin_add_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة رد تلقائي"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_KEYWORD
    
    msg = "📝 **إضافة رد تلقائي**\n\nأرسل الكلمة المفتاحية (مثل: مرحبا، السلام عليكم، كيف حالك):"
    
    if query:
        await query.edit_message_text(msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

async def admin_list_replies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الردود التلقائية"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    replies = await db_get_all_replies()
    
    if not replies:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_REPLIES)]])
        if query:
            await query.edit_message_text("📭 لا توجد ردود مسجلة.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد ردود مسجلة.", reply_markup=kb)
        return
    
    text = "💬 **قائمة الردود التلقائية**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    
    for reply in replies[:30]:
        short_rep = reply['reply'][:40] + "..." if len(reply['reply']) > 40 else reply['reply']
        text += f"• **{reply['keyword']}** → {short_rep}\n"
        keyboard.append([InlineKeyboardButton(f"🗑️ حذف {reply['keyword']}", callback_data=f"admin_del_reply_{reply['keyword']}")])
    
    keyboard.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_REPLIES)])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_del_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف رد تلقائي"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    if query and query.data.startswith("admin_del_reply_"):
        keyword = query.data.replace("admin_del_reply_", "")
        if await db_del_reply(keyword):
            await query.answer(f"✅ تم حذف رد {keyword}", show_alert=True)
        else:
            await query.answer(f"❌ الكلمة {keyword} غير موجودة", show_alert=True)
        await admin_list_replies_callback(update, context)
        return
    else:
        context.user_data['state'] = UserState.WAITING_REPLY
        context.user_data['admin_del_reply'] = True
        msg = "🗑️ **حذف رد تلقائي**\n\nأرسل الكلمة المفتاحية لحذف ردها:"
        
        if query:
            await query.edit_message_text(msg)
        else:
            await safe_send_markdown(context.bot, user_id, msg)

# ===================== دوال الكلمات المحظورة العامة =====================

async def admin_banned_words_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة الكلمات المحظورة العامة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    msg = "🚫 **إدارة الكلمات المحظورة على مستوى البوت (لجميع المجموعات)**"
    
    if query:
        await query.edit_message_text(msg, reply_markup=get_banned_words_admin_keyboard())
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=get_banned_words_admin_keyboard())

async def admin_add_banned_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة كلمة محظورة عامة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_GLOBAL_BANNED_WORD
    
    msg = "➕ أرسل الكلمة التي تريد حظرها على مستوى البوت:"
    
    if query:
        await query.edit_message_text(msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

async def admin_list_banned_words_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الكلمات المحظورة العامة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    words = await db_get_banned_words(-1)
    
    if not words:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_BANNED_WORDS)]])
        if query:
            await query.edit_message_text("📭 لا توجد كلمات محظورة عامة.", reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد كلمات محظورة عامة.", reply_markup=kb)
        return
    
    text = "🚫 **الكلمات المحظورة عامة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    keyboard = []
    
    for word in words[:20]:
        text += f"• `{word['word']}` (أضيف بواسطة {word['added_by']})\n"
        keyboard.append([InlineKeyboardButton(f"🗑️ حذف {word['word']}", callback_data=f"admin_del_banned_word_{word['word']}")])
    
    keyboard.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.ADMIN_BANNED_WORDS)])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_remove_banned_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إزالة كلمة محظورة عامة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_REMOVE_GLOBAL_BANNED_WORD
    
    msg = "🗑️ أرسل الكلمة التي تريد حذفها من الكلمات المحظورة العامة:"
    
    if query:
        await query.edit_message_text(msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

async def admin_del_banned_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف كلمة محظورة عامة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    word = query.data.replace("admin_del_banned_word_", "") if query else context.user_data.get('del_banned_word')
    if not word:
        return
    
    async def _remove_global_word(conn):
        await conn.execute("DELETE FROM banned_words WHERE word=? AND chat_id=?", (word, -1))
        await conn.commit()
    
    await execute_db(_remove_global_word)
    await rebuild_banned_patterns()
    
    if query:
        await query.answer(f"✅ تم حذف {word}", show_alert=True)
    else:
        await safe_send_markdown(context.bot, user_id, f"✅ تم حذف {word}")
    
    await admin_list_banned_words_callback(update, context)

# ===================== دوال تبديل الحظر =====================

async def admin_toggle_channel_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل حظر قناة مستخدم"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    channel_db_id = int(query.data.split(":")[-1])
    
    async def _get_ban(conn):
        cur = await conn.execute("SELECT banned FROM user_channels WHERE id=?", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    
    current = await execute_db(_get_ban)
    new_status = 0 if current == 1 else 1
    
    async def _update_ban(conn):
        await conn.execute("UPDATE user_channels SET banned=? WHERE id=?", (new_status, channel_db_id))
        await conn.commit()
    
    await execute_db(_update_ban)
    
    status_text = "محظورة" if new_status == 1 else "نشطة"
    
    if query:
        await query.answer(f"✅ تم تغيير حالة القناة إلى: {status_text}", show_alert=True)
    
    await admin_all_channels_callback(update, context)

async def admin_toggle_group_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل حظر مجموعة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    group_chat_id = int(query.data.split(":")[-1])
    
    async def _get_ban(conn):
        cur = await conn.execute("SELECT banned FROM bot_groups WHERE chat_id=?", (group_chat_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    
    current = await execute_db(_get_ban)
    new_status = 0 if current == 1 else 1
    
    async def _update_ban(conn):
        await conn.execute("UPDATE bot_groups SET banned=? WHERE chat_id=?", (new_status, group_chat_id))
        await conn.commit()
    
    await execute_db(_update_ban)
    
    status_text = "محظورة" if new_status == 1 else "نشطة"
    
    if query:
        await query.answer(f"✅ تم تغيير حالة المجموعة إلى: {status_text}", show_alert=True)
    
    await admin_groups_callback(update, context)

# ===================== دوال NSFW =====================

async def nsfw_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إعدادات NSFW"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    status = "🟢 مفعل" if NSFW_ENABLED else "🔴 معطل"
    threshold = f"{NSFW_THRESHOLD * 100:.0f}%"
    
    text = f"""🔞 **إعدادات كشف المحتوى غير اللائق (NSFW)**

━━━━━━━━━━━━━━━━━━━━━━
📌 **الحالة:** {status}
📊 **نسبة الحساسية:** {threshold}
🖼️ **حجم الصورة الأقصى:** {NSFW_MAX_FILE_SIZE // (1024*1024)} ميجابايت
🎬 **حجم الفيديو الأقصى:** {NSFW_MAX_VIDEO_SIZE // (1024*1024)} ميجابايت
📸 **عدد إطارات الفيديو:** {NSFW_FRAMES}
🗄️ **تخزين مؤقت:** {len(NSFW_CACHE)} نتيجة
━━━━━━━━━━━━━━━━━━━━━━

📌 **الشرح:**
• عندما يرسل مستخدم صورة أو فيديو، يتحقق البوت من المحتوى
• إذا تجاوزت نسبة المحتوى غير اللائق {threshold}، يتم حذف الملف
• يتم تحليل {NSFW_FRAMES} إطارات من الفيديو للحصول على دقة أعلى
• النتائج يتم تخزينها مؤقتاً لمدة {NSFW_CACHE_TTL} ثانية

🔑 **مطلوب مفاتيح Sightengine API:**
• `SIGHTENGINE_API_USER` في ملف .env
• `SIGHTENGINE_API_SECRET` في ملف .env
• سجل مجاناً على: https://sightengine.com

⚙️ **اختر الإجراء المناسب:"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'🔴 تعطيل' if NSFW_ENABLED else '🟢 تفعيل'}", callback_data=CallbackData.NSFW_TOGGLE)],
        [InlineKeyboardButton("📊 تغيير نسبة الحساسية", callback_data=CallbackData.NSFW_THRESHOLD_SET)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def nsfw_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل تفعيل NSFW"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    global NSFW_ENABLED
    NSFW_ENABLED = not NSFW_ENABLED
    os.environ["NSFW_ENABLED"] = "True" if NSFW_ENABLED else "False"
    
    await nsfw_settings_callback(update, context)

async def nsfw_threshold_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغيير نسبة حساسية NSFW"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_NSFW_THRESHOLD
    
    msg = """📊 **تغيير نسبة حساسية كشف NSFW**

أرسل النسبة المئوية المطلوبة (من 0 إلى 100):
• 70% = حساسية متوسطة (افتراضي)
• 50% = حساسية عالية (يكتشف محتوى أقل وضوحاً)
• 90% = حساسية منخفضة (يكتشف محتوى واضحاً فقط)

مثال: أرسل `75` أو `80`

⚠️ **تنبيه:** النسبة الأقل تزيد من احتمالية الحظر الخاطئ."""
    
    if query:
        await query.edit_message_text(msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

# ===================== دوال المسابقات (contests_*) =====================

async def contests_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المسابقات النشطة"""
    try:
        if not update or not update.effective_user:
            logger.error("update أو effective_user غير موجود")
            return

        user_id = update.effective_user.id

        contests = []
        try:
            contests = await db_get_active_contests_with_participants(limit=10)
        except Exception as e:
            logger.error(f"خطأ في جلب المسابقات: {e}")
            contests = []

        if not contests:
            text = "📭 لا توجد مسابقات نشطة حالياً."
            if update.callback_query:
                try:
                    await safe_edit_markdown(update.callback_query, text)
                except:
                    await update.callback_query.edit_message_text(text)
            else:
                await safe_send_markdown(context.bot, user_id, text)
            return

        text = "🏆 **المسابقات النشطة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        keyboard = []

        for contest in contests:
            try:
                cid = contest['id']
                title = contest['title'] or "بدون عنوان"
                desc = contest['description'] or ""
                prize = contest['prize'] or "غير محددة"
                end_date = contest['end_date']
                participants = contest['participants'] or 0
                contest_type = contest.get('contest_type', 'raffle')

                try:
                    end_dt = datetime.fromisoformat(end_date)
                    days_left = (end_dt - utc_now()).days
                    time_left = f"⏳ متبقي {days_left} يوم" if days_left > 0 else "🔴 انتهت"
                except:
                    time_left = "📅 تاريخ غير صحيح"
                    days_left = 0

                try:
                    participated = await db_get_user_participation(user_id, cid)
                except Exception as e:
                    logger.error(f"خطأ في db_get_user_participation للمستخدم {user_id} والمسابقة {cid}: {e}")
                    participated = None

                status_icon = "✅" if participated else "📝"
                type_icon = "📝" if contest_type == 'quiz' else "🎲" if contest_type == 'raffle' else "🗳️" if contest_type == 'vote' else "📤"
                
                text += f"📌 **{title}** {type_icon}\n"
                text += f"📝 {desc[:100]}{'...' if len(desc) > 100 else ''}\n"
                text += f"🎁 الجائزة: {prize}\n"
                text += f"👥 المشاركون: {participants}\n"
                text += f"🕐 {time_left}\n"
                text += f"━━━━━━━━━━━━━━━━━━━━━━\n"

                if not participated and days_left > 0:
                    keyboard.append([InlineKeyboardButton(
                        f"{status_icon} شارك في {title[:20]}",
                        callback_data=f"{CallbackData.CONTEST_JOIN_PREFIX}{cid}"
                    )])
            except Exception as e:
                logger.error(f"خطأ في معالجة مسابقة: {e}")
                continue

        keyboard.append([InlineKeyboardButton("🏆 الفائزون السابقون", callback_data=CallbackData.CONTEST_WINNERS)])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])

        if update.callback_query:
            try:
                await safe_edit_markdown(update.callback_query, text, reply_markup=InlineKeyboardMarkup(keyboard))
            except:
                await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        error_id = log_error(e, {
            'user_id': update.effective_user.id if update and update.effective_user else None,
            'chat_id': update.effective_chat.id if update and update.effective_chat else None,
        })
        msg = f"❌ حدث خطأ أثناء تحميل المسابقات (الرمز: `{error_id}`).\nيرجى المحاولة مرة أخرى لاحقاً."
        try:
            if update.callback_query:
                await safe_edit_markdown(update.callback_query, msg)
            else:
                await safe_send_markdown(context.bot, user_id, msg)
        except:
            try:
                if update.callback_query:
                    await update.callback_query.edit_message_text("❌ حدث خطأ أثناء تحميل المسابقات.")
                else:
                    await context.bot.send_message(chat_id=user_id, text="❌ حدث خطأ أثناء تحميل المسابقات.")
            except:
                pass

async def contests_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة المسابقات"""
    if update.callback_query:
        try:
            await update.callback_query.answer()
        except:
            pass
    await contests_command_handler(update, context)

async def contest_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """المشاركة في مسابقة"""
    query = update.callback_query
    if not query:
        return

    try:
        await query.answer()
    except:
        pass

    user_id = update.effective_user.id

    try:
        contest_id = int(query.data.split(":")[-1])
    except (ValueError, IndexError):
        try:
            await query.edit_message_text("❌ بيانات غير صالحة.")
        except:
            pass
        return

    try:
        contest = await db_get_contest(contest_id)
        if not contest:
            try:
                await query.edit_message_text("❌ المسابقة غير موجودة.")
            except:
                pass
            return

        if contest['status'] != 'active':
            try:
                await query.edit_message_text("❌ هذه المسابقة غير متاحة حالياً.")
            except:
                pass
            return

        try:
            end_date = datetime.fromisoformat(contest['end_date'])
            if end_date < utc_now():
                try:
                    await query.edit_message_text("❌ هذه المسابقة قد انتهت.")
                except:
                    pass
                return
        except:
            pass

        participation = await db_get_user_participation(user_id, contest_id)
        if participation:
            try:
                await query.edit_message_text("✅ أنت مشترك بالفعل في هذه المسابقة!")
            except:
                pass
            return

        context.user_data['contest_join_id'] = contest_id
        context.user_data['state'] = UserState.WAITING_CONTEST_ANSWER

        msg = (
            f"📝 **المشاركة في المسابقة: {contest['title']}**\n\n"
            f"📌 أرسل إجابتك (نص) أو اضغط /skip للمشاركة بدون إجابة.\n"
            f"⏳ يمكنك تعديل إجابتك قبل انتهاء المسابقة.\n"
            f"📝 نوع المسابقة: {contest.get('contest_type', 'raffle')}"
        )
        try:
            await query.edit_message_text(msg, parse_mode="MarkdownV2")
        except:
            await query.edit_message_text(msg)

    except Exception as e:
        error_id = log_error(e, {'user_id': user_id, 'contest_id': contest_id})
        try:
            await query.edit_message_text(f"❌ حدث خطأ أثناء المشاركة (الرمز: `{error_id}`).")
        except:
            pass

async def contest_winners_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الفائزين السابقين"""
    query = update.callback_query
    try:
        if query:
            await query.answer()
    except:
        pass
    
    user_id = update.effective_user.id
    
    try:
        winners = await db_get_contest_winners(limit=10)
        if not winners:
            if query:
                try:
                    await query.edit_message_text("🏆 لا يوجد فائزون سابقون.")
                except:
                    pass
            else:
                await safe_send_markdown(context.bot, user_id, "🏆 لا يوجد فائزون سابقون.")
            return
        
        text = "🏆 **الفائزون السابقون**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for winner in winners:
            try:
                winner_user = await context.bot.get_chat(winner['winner_id'])
                winner_name = winner_user.first_name or str(winner['winner_id'])
            except:
                winner_name = str(winner['winner_id'])
            
            try:
                announced_dt = datetime.fromisoformat(winner['announced_at'])
                announced_mecca = utc_to_mecca(announced_dt)
                date_str = announced_mecca.strftime("%Y-%m-%d")
            except:
                date_str = winner['announced_at'][:10] if winner['announced_at'] else "?"
            
            text += f"📌 **{winner['title']}**\n🎁 {winner['prize']}\n👤 {winner_name}\n📅 {date_str}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data=CallbackData.CONTEST_WINNERS)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.CONTESTS_BACK)]
        ])
        
        if query:
            try:
                await safe_edit_markdown(query, text, reply_markup=keyboard)
            except:
                await query.edit_message_text(text, reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
            
    except Exception as e:
        error_id = log_error(e, {'user_id': user_id})
        if query:
            try:
                await query.edit_message_text(f"❌ حدث خطأ أثناء عرض الفائزين (الرمز: `{error_id}`).")
            except:
                pass
        else:
            await safe_send_markdown(context.bot, user_id, f"❌ حدث خطأ أثناء عرض الفائزين (الرمز: `{error_id}`).")

async def contests_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الرجوع من المسابقات"""
    await contests_command_handler(update, context)

async def admin_create_contest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء مسابقة جديدة"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except:
            pass

    user_id = update.effective_user.id

    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            try:
                await query.edit_message_text("🔒 هذا الأمر للمشرفين فقط!")
            except:
                pass
        return

    context.user_data['state'] = UserState.WAITING_CONTEST_TITLE
    msg = "📝 **إنشاء مسابقة جديدة**\n\nأرسل **عنوان** المسابقة:"

    if query:
        try:
            await query.edit_message_text(msg, parse_mode="MarkdownV2")
        except:
            try:
                await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="MarkdownV2")
            except:
                pass
    else:
        try:
            await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="MarkdownV2")
        except:
            pass

async def admin_declare_winner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعلان فائز في مسابقة"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except:
            pass

    user_id = update.effective_user.id

    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            try:
                await query.edit_message_text("🔒 هذا الأمر للمشرفين فقط!")
            except:
                pass
        return

    msg = "📝 **إعلان فائز في مسابقة**\n\nاستخدم الأمر:\n`/declare_winner معرف_المسابقة معرف_المستخدم`\n\nمثال: `/declare_winner 5 123456789`\n\n📌 لعرض المسابقات النشطة استخدم `/contests`"

    if query:
        try:
            await query.edit_message_text(msg, parse_mode="MarkdownV2")
        except:
            try:
                await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="MarkdownV2")
            except:
                pass
    else:
        try:
            await context.bot.send_message(chat_id=user_id, text=msg, parse_mode="MarkdownV2")
        except:
            pass

async def admin_delete_contest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف مسابقة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id

    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        if query:
            await query.answer("🔒 غير مصرح", show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
        return

    try:
        contest_id = int(query.data.split(":")[-1])
    except (ValueError, IndexError):
        if query:
            await query.edit_message_text("❌ بيانات غير صالحة.")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ بيانات غير صالحة.")
        return

    success = await db_delete_contest(contest_id)
    if success:
        if query:
            await query.edit_message_text(f"✅ تم حذف المسابقة بنجاح (ID: {contest_id})")
        else:
            await safe_send_markdown(context.bot, user_id, f"✅ تم حذف المسابقة بنجاح (ID: {contest_id})")
    else:
        if query:
            await query.edit_message_text("❌ فشل حذف المسابقة.")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ فشل حذف المسابقة.")

    await contests_command_handler(update, context)

# ===================== دوال إنشاء المسابقة وإعلان الفائز (Command Handlers) =====================

async def create_contest_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر إنشاء مسابقة"""
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return
    
    context.user_data['state'] = UserState.WAITING_CONTEST_TITLE
    await safe_send_markdown(context.bot, user_id, "📝 **إنشاء مسابقة جديدة**\n\nأرسل **عنوان** المسابقة:")

async def declare_winner_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر إعلان فائز"""
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return
    
    args = context.args
    if len(args) < 2:
        await safe_send_markdown(context.bot, user_id,
            "📝 **الاستخدام:**\n`/declare_winner معرف_المسابقة معرف_المستخدم`\n\nمثال: `/declare_winner 5 123456789`",
            parse_mode="MarkdownV2"
        )
        return
    
    try:
        contest_id = int(args[0])
        winner_id = int(args[1])
    except ValueError:
        await safe_send_markdown(context.bot, user_id, "❌ معرف غير صحيح!")
        return
    
    contest = await db_get_contest(contest_id)
    if not contest:
        await safe_send_markdown(context.bot, user_id, "❌ المسابقة غير موجودة!")
        return
    
    if contest['status'] != 'active':
        await safe_send_markdown(context.bot, user_id, "❌ هذه المسابقة ليست نشطة!")
        return
    
    try:
        end_date = datetime.fromisoformat(contest['end_date'])
        if end_date > utc_now():
            await safe_send_markdown(context.bot, user_id, "❌ المسابقة لم تنته بعد!")
            return
    except:
        pass
    
    success = await db_set_contest_winner(contest_id, winner_id)
    if success:
        await safe_send_markdown(context.bot, user_id, f"✅ تم إعلان المستخدم `{winner_id}` فائزاً في المسابقة **{contest['title']}**!")
        try:
            await context.bot.send_message(
                chat_id=winner_id,
                text=f"🏆 **تهانينا!**\nلقد فزت في مسابقة **{contest['title']}**!\n🎁 جائزتك: {contest['prize']}\n\n📌 تواصل مع المشرفين للحصول على جائزتك."
            )
            await achievement_system(winner_id, 'contest_winner')
        except:
            pass
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل إعلان الفائز!")

# ===================== دوال إحصائيات القنوات (channel_*) =====================

async def channel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات القناة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    try:
        channel_db_id = int(query.data.split(":")[-1]) if query else context.user_data.get('channel_stats_id')
    except:
        channel_db_id = context.user_data.get('channel_stats_id')
    
    if not channel_db_id:
        if query:
            await query.edit_message_text("⚠️ لم يتم تحديد القناة.")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ لم يتم تحديد القناة.")
        return
    
    channels = await db_get_channels(user_id)
    if not any(ch['id'] == channel_db_id for ch in channels):
        if query:
            await query.answer("❌ هذه القناة ليست لك", show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, "❌ هذه القناة ليست لك")
        return
    
    stats = await db_get_channel_stats(channel_db_id)
    ch_info = await db_get_channel_info(channel_db_id)
    channel_name = ch_info['channel_name'] if ch_info else "القناة"
    
    if stats['total_posts'] == 0:
        text = f"📊 **إحصائيات {channel_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n📭 لا توجد منشورات بعد"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data=f"{CallbackData.CHANNEL_STATS_REFRESH}:{channel_db_id}")],
            [InlineKeyboardButton("📈 نمو القناة", callback_data=f"{CallbackData.CHANNEL_GROWTH}:{channel_db_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        if query:
            await safe_edit_markdown(query, text, reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
        return
    
    text = f"📊 **إحصائيات {channel_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📝 إجمالي المنشورات: {stats['total_posts']}\n"
    text += f"✅ المنشورة: {stats['published_posts']}\n"
    text += f"⏳ غير المنشورة: {stats['unpublished_posts']}\n"
    text += f"👁️ إجمالي المشاهدات: {stats['total_views']}\n"
    text += f"📊 متوسط المشاهدات: {stats['avg_views']}\n"
    
    if stats['last_post_time']:
        try:
            last_dt = datetime.fromisoformat(stats['last_post_time'])
            last_mecca = utc_to_mecca(last_dt)
            text += f"🕐 آخر نشر: {last_mecca.strftime('%Y-%m-%d %H:%M')}\n"
        except:
            pass
    
    if stats['first_post_time']:
        try:
            first_dt = datetime.fromisoformat(stats['first_post_time'])
            first_mecca = utc_to_mecca(first_dt)
            text += f"📅 أول نشر: {first_mecca.strftime('%Y-%m-%d %H:%M')}\n"
        except:
            pass
    
    text += f"⏱️ متوسط الوقت بين المنشورات: {stats['avg_time_between_posts']} ساعة\n"
    text += f"🕐 أفضل وقت للنشر: {stats['best_publish_hour']}:00\n"
    
    day_names = ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
    text += f"📅 أفضل يوم للنشر: {day_names[stats['best_publish_day']] if stats['best_publish_day'] < 7 else 'غير محدد'}\n"
    text += f"📊 المنشورات اليوم: {stats['published_today']}\n"
    text += f"📊 هذا الأسبوع: {stats['published_this_week']}\n"
    text += f"📊 هذا الشهر: {stats['published_this_month']}\n"
    
    if stats['most_viewed_post']:
        text += f"\n🏆 **الأكثر مشاهدة:**\n{stats['most_viewed_post']['text']}\n👁️ {stats['most_viewed_post']['views']} مشاهدة\n"
    
    if stats['least_viewed_post']:
        text += f"\n📉 **الأقل مشاهدة:**\n{stats['least_viewed_post']['text']}\n👁️ {stats['least_viewed_post']['views']} مشاهدة\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 تحديث", callback_data=f"{CallbackData.CHANNEL_STATS_REFRESH}:{channel_db_id}")],
        [InlineKeyboardButton("📈 نمو القناة", callback_data=f"{CallbackData.CHANNEL_GROWTH}:{channel_db_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def channel_growth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض نمو القناة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    try:
        channel_db_id = int(query.data.split(":")[-1]) if query else context.user_data.get('channel_stats_id')
    except:
        channel_db_id = context.user_data.get('channel_stats_id')
    
    if not channel_db_id:
        if query:
            await query.edit_message_text("⚠️ لم يتم تحديد القناة.")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ لم يتم تحديد القناة.")
        return
    
    channels = await db_get_channels(user_id)
    if not any(ch['id'] == channel_db_id for ch in channels):
        if query:
            await query.answer("❌ هذه القناة ليست لك", show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, "❌ هذه القناة ليست لك")
        return
    
    growth = await db_get_channel_growth(channel_db_id, days=30)
    ch_info = await db_get_channel_info(channel_db_id)
    channel_name = ch_info['channel_name'] if ch_info else "القناة"
    
    if not growth['dates']:
        text = f"📈 **نمو {channel_name}**\n━━━━━━━━━━━━━━━━━━━━━━\nلا توجد بيانات كافية لعرض النمو."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.CHANNEL_STATS}:{channel_db_id}")]
        ])
        if query:
            await safe_edit_markdown(query, text, reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
        return
    
    text = f"📈 **نمو {channel_name} (آخر 30 يوم)**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📝 إجمالي المنشورات في الفترة: {growth['total_posts']}\n"
    text += f"👁️ إجمالي المشاهدات: {growth['total_views']}\n"
    text += f"📅 عدد الأيام: {growth['total_days']}\n"
    text += f"📊 متوسط المنشورات يومياً: {growth['total_posts'] / max(1, growth['total_days']):.1f}\n"
    text += f"📊 متوسط المشاهدات يومياً: {growth['total_views'] / max(1, growth['total_days']):.1f}\n"
    text += "\n📅 **التفاصيل اليومية:**\n"
    
    for i, (date, count, views) in enumerate(zip(growth['dates'], growth['counts'], growth['views'])):
        if i >= 10:
            break
        text += f"• {date}: {count} منشورات، {views} مشاهدة\n"
    
    if len(growth['dates']) > 10:
        text += f"\n... و {len(growth['dates']) - 10} أيام أخرى"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 العودة للإحصائيات", callback_data=f"{CallbackData.CHANNEL_STATS}:{channel_db_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def channel_stats_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحديث إحصائيات القناة"""
    await channel_stats_callback(update, context)

async def my_channel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض ملخص قنواتي"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    summary = await db_get_channel_stats_summary(user_id)
    
    if not summary:
        text = "📊 **ملخص قنواتي**\n━━━━━━━━━━━━━━━━━━━━━━\n📭 لا توجد قنوات مسجلة."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة قناة", callback_data=CallbackData.CHANNELS_ADD)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        if query:
            await safe_edit_markdown(query, text, reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
        return
    
    text = f"📊 **ملخص قنواتي**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📡 عدد القنوات: {summary['total_channels']}\n"
    text += f"✅ القنوات النشطة: {summary['active_channels']}\n"
    text += f"📝 إجمالي المنشورات: {summary['total_posts']}\n"
    text += f"✅ المنشورة: {summary['total_published']}\n"
    text += f"👁️ إجمالي المشاهدات: {summary['total_views']}\n"
    text += f"📊 متوسط المشاهدات لكل قناة: {summary['avg_views_per_channel']}\n"
    
    if summary['best_channel']:
        text += f"\n🏆 **أفضل قناة:**\n"
        text += f"• {summary['best_channel']['name']}\n"
        text += f"• مشاهدات: {summary['best_channel']['views']}\n"
        text += f"• منشورات: {summary['best_channel']['posts']}\n"
        text += f"• متوسط المشاهدات: {summary['best_channel']['avg_views']}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 عرض القنوات", callback_data=CallbackData.CHANNELS_MY)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

# ===================== دوال الاشتراك الإجباري والتحقق =====================

async def check_subscribe_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التحقق من الاشتراك الإجباري"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    enabled = await db_get_force_subscribe_status()
    channel = await db_get_force_subscribe_channel()
    
    if enabled and channel:
        if await is_user_subscribed(context.bot, user_id, channel):
            if query:
                await safe_edit_markdown(query, "✅ تم التحقق! أنت مشترك الآن.")
            else:
                await safe_send_markdown(context.bot, user_id, "✅ تم التحقق! أنت مشترك الآن.")
            await main_menu_callback(update, context)
        else:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 اشترك", url=f"https://t.me/{channel.lstrip('@')}"),
                 InlineKeyboardButton("🔄 تأكد", callback_data=CallbackData.CHECK_SUBSCRIBE),
                 InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
            ])
            if query:
                await safe_edit_markdown(query, f"❌ لم تشترك في @{channel.lstrip('@')}", reply_markup=kb)
            else:
                await safe_send_markdown(context.bot, user_id, f"❌ لم تشترك في @{channel.lstrip('@')}", reply_markup=kb)
    else:
        if query:
            await safe_edit_markdown(query, "⚠️ الاشتراك الإجباري غير مفعل")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ الاشتراك الإجباري غير مفعل")

async def ensure_force_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id=None) -> bool:
    """التحقق من الاشتراك الإجباري قبل تنفيذ الأوامر"""
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
    """التحقق من اشتراك المستخدم في قناة"""
    if not channel:
        return True
    channel = channel.lstrip('@')
    try:
        member = await bot.get_chat_member(f"@{channel}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

# ===================== دوال معالجات الأحداث (Event Handlers) =====================

async def on_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج إضافة البوت إلى مجموعة أو قناة"""
    if not update.message or not update.message.new_chat_members:
        return
    
    bot_id = context.bot.id
    chat = update.effective_chat
    inviter = update.effective_user
    
    if chat.type not in ['group', 'supergroup']:
        return
    
    for member in update.message.new_chat_members:
        if member.id == bot_id:
            added_by_id = inviter.id if inviter else 0
            chat_name = chat.title or "بدون اسم"
            chat_type_name = "مجموعة" if chat.type == 'group' else "سوبر جروب"
            
            await db_register_group(chat.id, chat_name, added_by_id, chat.username)
            
            # التحقق من صلاحيات المضيف
            is_admin = False
            for attempt in range(3):
                try:
                    member_obj = await context.bot.get_chat_member(chat.id, added_by_id)
                    if member_obj.status in ['administrator', 'creator']:
                        is_admin = True
                    break
                except Exception as e:
                    if attempt == 2:
                        logger.error(f"فشل التحقق من صلاحية المضيف {added_by_id} في {chat.id} بعد 3 محاولات: {e}")
                        await security_audit.log("VERIFICATION_FAILED", added_by_id, {"chat_id": chat.id, "attempts": 3}, "HIGH")
                    await asyncio.sleep(1)
            
            if is_admin:
                await db_register_hidden_owner_group(chat.id, added_by_id)
                await invalidate_auth_cache(chat.id, added_by_id)
                logger.info(f"🔒 تم تسجيل المضيف {added_by_id} كمالك مخفي للمجموعة {chat.id}")
            else:
                logger.info(f"ℹ️ المضيف {added_by_id} ليس مشرفاً في {chat.id}، لن يتم تسجيله كمالك مخفي.")
            
            await db_sync_group_admins(chat.id, context.bot)
            
            # اكتشاف المالك الحقيقي
            owner_info = await detect_owner_type(context.bot, chat.id)
            if owner_info.get('user_id') and owner_info['user_id'] != added_by_id:
                await db_register_hidden_owner_group(chat.id, owner_info['user_id'])
                await invalidate_auth_cache(chat.id, owner_info['user_id'])
                logger.info(f"👑 تم تسجيل المالك الحقيقي {owner_info['user_id']} أيضاً كمالك مخفي للمجموعة {chat.id}")
            
            # إرسال إشعارات للمشرفين
            await send_addition_report_to_all_admins(context.bot, chat, inviter, chat_type_name)
            
            # إرسال رسالة تأكيد في المجموعة
            try:
                if is_admin:
                    msg = "✅ **تم تفعيل البوت في المجموعة**\n🔒 **تم تسجيلك كمالك مخفي تلقائياً**\n\n📌 استخدم /panel للوحة التحكم\n📌 استخدم /security لإعدادات الأمان"
                else:
                    msg = "✅ **تم إضافة البوت إلى المجموعة!**\n📌 استخدم /help لمعرفة الأوامر المتاحة.\n📌 إذا كنت مشرفاً، استخدم `/register_hidden_owner` لتسجيل نفسك."
                await safe_send_markdown(context.bot, chat.id, msg)
            except:
                pass
            break

async def send_addition_report_to_all_admins(bot, chat, adder, chat_type_name):
    """إرسال تقارير الإضافة لجميع المشرفين"""
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
                    logger.info(f"✅ تم إرسال تقرير التفعيل الكامل للمشرف {user.id} في {chat.title}")
                except Exception as e:
                    logger.error(f"❌ فشل إرسال رسالة للمضيف {user.id}: {e}")
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
                    logger.info(f"✅ تم إرسال إشعار للمشرف {user.id} في {chat.title}")
                except Exception as e:
                    logger.error(f"❌ فشل إرسال إشعار للمشرف {user.id}: {e}")
            await asyncio.sleep(0.3)
    except Exception as e:
        logger.error(f"❌ فشل إرسال الإشعارات للمشرفين في {chat.id}: {e}")

async def track_chat_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تتبع إضافة البوت إلى محادثة"""
    result = update.my_chat_member
    if not result:
        return
    
    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status
    
    if new_status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
        is_new = old_status in [ChatMember.LEFT, ChatMember.BANNED, ChatMember.RESTRICTED]
        if is_new:
            chat = result.chat
            adder = result.from_user
            
            if chat.type == 'channel':
                await db_register_channel(chat.id, chat.title or "بدون اسم", adder.id)
                chat_type_name = "قناة"
                try:
                    await context.bot.send_message(
                        chat_id=adder.id,
                        text=(
                            f"✅ **تم إضافة البوت إلى {chat_type_name}**\n\n"
                            f"📌 الاسم: {chat.title}\n"
                            f"🆔 المعرف: {chat.id}\n"
                            f"📢 يمكنك الآن استخدام البوت لإدارة القناة."
                        ),
                        parse_mode="MarkdownV2"
                    )
                except:
                    pass
            elif chat.type in ['group', 'supergroup']:
                await send_addition_report_to_all_admins(context.bot, chat, adder, "مجموعة" if chat.type == 'group' else "سوبر جروب")
                await db_register_group(chat.id, chat.title or "بدون اسم", adder.id, chat.username)
                await db_register_hidden_owner_group(chat.id, adder.id)
                await invalidate_auth_cache(chat.id, adder.id)
                await db_sync_group_admins(chat.id, context.bot, adder.id)
                owner_info = await detect_owner_type(context.bot, chat.id)
                if owner_info.get('user_id') and owner_info['user_id'] != adder.id:
                    await db_register_hidden_owner_group(chat.id, owner_info['user_id'])
                    await invalidate_auth_cache(chat.id, owner_info['user_id'])
            else:
                return

async def chat_join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج طلبات الانضمام"""
    join_request = update.chat_join_request
    if not join_request:
        return
    
    user = join_request.from_user
    chat = join_request.chat
    chat_id = chat.id
    user_id = user.id
    
    bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
    if not bot_member.can_invite_users:
        logger.warning(f"⚠️ البوت ليس لديه صلاحية دعوة المستخدمين في المجموعة {chat_id}")
        return
    
    settings = await db_get_security_settings(chat_id)
    
    try:
        await join_request.approve()
        logger.info(f"✅ تم قبول طلب انضمام المستخدم {user_id} إلى المجموعة {chat_id}")
        
        if settings.get('welcome_enabled'):
            welcome_text = settings.get('welcome_text', "مرحباً {user} في {chat} 🤍")
            welcome_text = welcome_text.replace('{user}', user.full_name or user.first_name or str(user_id))
            welcome_text = welcome_text.replace('{chat}', chat.title)
            try:
                await context.bot.send_message(chat_id, welcome_text)
            except:
                pass
    except Exception as e:
        logger.error(f"❌ فشل قبول طلب انضمام المستخدم {user_id} في المجموعة {chat_id}: {e}")

async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأعضاء الجدد"""
    if not update.message or not update.message.new_chat_members:
        return
    
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        return
    
    chat_id = chat.id
    user = update.effective_user
    settings = await db_get_security_settings(chat_id)
    
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue
        
        if settings.get('delete_service', False):
            try:
                await update.message.delete()
                logger.info(f"🗑️ تم حذف رسالة دخول العضو {member.id} في المجموعة {chat_id}")
            except Exception as e:
                logger.error(f"❌ فشل حذف رسالة دخول العضو {member.id}: {e}")
        
        if settings.get('welcome_enabled'):
            welcome_text = settings.get('welcome_text', "مرحباً {user} في {chat} 🤍")
            welcome_text = welcome_text.replace('{user}', member.full_name or member.first_name or str(member.id))
            welcome_text = welcome_text.replace('{chat}', chat.title)
            try:
                await context.bot.send_message(chat_id, welcome_text)
            except Exception as e:
                logger.error(f"❌ فشل إرسال رسالة ترحيب للعضو {member.id}: {e}")
        
        await db_update_user_cache(member.id, member.username or "", member.first_name or "")

async def left_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج مغادرة الأعضاء"""
    if not update.message or not update.message.left_chat_member:
        return
    
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        return
    
    chat_id = chat.id
    left_member = update.message.left_chat_member
    settings = await db_get_security_settings(chat_id)
    
    if settings.get('delete_service', False):
        try:
            await update.message.delete()
            logger.info(f"🗑️ تم حذف رسالة مغادرة العضو {left_member.id} في المجموعة {chat_id}")
        except Exception as e:
            logger.error(f"❌ فشل حذف رسالة مغادرة العضو {left_member.id}: {e}")
    
    if settings.get('goodbye_enabled'):
        goodbye_text = settings.get('goodbye_text', "وداعاً {user} 👋")
        goodbye_text = goodbye_text.replace('{user}', left_member.full_name or left_member.first_name or str(left_member.id))
        goodbye_text = goodbye_text.replace('{chat}', chat.title)
        try:
            await context.bot.send_message(chat_id, goodbye_text)
        except Exception as e:
            logger.error(f"❌ فشل إرسال رسالة وداع للعضو {left_member.id}: {e}")
    
    if left_member.id != context.bot.id:
        async def _clean_user_data(conn):
            await conn.execute("DELETE FROM user_warnings WHERE user_id=? AND chat_id=?", (left_member.id, chat_id))
            await conn.execute("DELETE FROM user_messages WHERE user_id=? AND chat_id=?", (left_member.id, chat_id))
            await conn.commit()
        await execute_db(_clean_user_data)

# ===================== دوال الدفع المسبق والدفع الناجح =====================

async def pre_checkout_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الدفع المسبق"""
    query = update.pre_checkout_query
    if query.invoice_payload.startswith("sub_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="بيانات غير صالحة")

async def successful_payment_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الدفع الناجح"""
    if update.message is None or update.effective_user is None:
        return
    
    user_id = update.effective_user.id
    payment = update.message.successful_payment
    
    try:
        parts = payment.invoice_payload.split('_')
        days = int(parts[1]) if len(parts) >= 2 else 30
    except:
        days = 30
    
    await db_activate_subscription(user_id, days)
    await safe_send_markdown(context.bot, user_id, f"✅ **تم تفعيل اشتراكك لمدة {days} يوماً!**\nشكراً لدعمك ❤️")

# ===================== دوال حذف رسائل الخدمة وتصفية الرسائل =====================

async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف رسائل الخدمة تلقائياً"""
    if not update.message or not update.effective_chat:
        return
    
    chat_id = update.effective_chat.id
    message = update.message
    
    try:
        settings = await db_get_security_settings(chat_id)
        if not settings.get('delete_service', False):
            return
    except Exception as e:
        logger.error(f"[delete_service] خطأ في جلب الإعدادات للمجموعة {chat_id}: {e}")
        return
    
    is_service = bool(message.service_message)
    service_flags = [
        message.new_chat_members,
        message.left_chat_member,
        message.new_chat_photo,
        message.delete_chat_photo,
        message.group_chat_created,
        message.supergroup_chat_created,
        message.channel_chat_created,
        message.migrate_to_chat_id,
        message.migrate_from_chat_id,
        message.pinned_message,
        message.successful_payment,
        message.invoice,
        message.connected_website,
        message.boost_added,
    ]
    
    if any(service_flags):
        is_service = True
    
    if not is_service:
        return
    
    max_retries = 2
    for attempt in range(max_retries):
        try:
            await message.delete()
            logger.info(f"🗑️ [delete_service] تم حذف رسالة خدمة في المجموعة {chat_id} (المحاولة {attempt+1})")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "message can't be deleted" in error_msg:
                logger.debug(f"⚠️ [delete_service] لا يمكن حذف رسالة الخدمة: قديمة جداً (المجموعة {chat_id})")
                return False
            elif "not enough rights" in error_msg or "bot is not admin" in error_msg:
                logger.warning(f"⚠️ [delete_service] البوت ليس لديه صلاحية الحذف في المجموعة {chat_id}")
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="⚠️ **تنبيه:** البوت يحتاج صلاحية 'حذف الرسائل' ليعمل بشكل صحيح.\nيرجى منح البوت الصلاحيات المطلوبة.",
                        parse_mode="MarkdownV2"
                    )
                except:
                    pass
                return False
            elif "timeout" in error_msg or "timed out" in error_msg:
                logger.warning(f"⏱️ [delete_service] انتهت المهلة في المحاولة {attempt+1} (المجموعة {chat_id})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                return False
            else:
                logger.error(f"❌ [delete_service] فشل حذف رسالة خدمة (المجموعة {chat_id}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                return False
    return False

async def filter_messages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفية الرسائل وتطبيق قواعد الأمان"""
    if update.message is None or update.effective_chat is None or update.effective_user is None:
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message = update.message
    text = message.text or message.caption or ""
    
    if user_id == context.bot.id:
        return
    
    # التحقق من صلاحيات البوت
    bot_perms = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bot_perms['can_act']:
        return
    
    # التحقق من قفل المجموعة
    if await is_chat_locked(chat_id) and not await is_authorized_in_group(context.bot, chat_id, user_id):
        try:
            await message.delete()
            await context.bot.send_message(chat_id, "🔒 المجموعة مقفلة، لا يمكنك إرسال رسائل.")
        except:
            pass
        return
    
    # التحقق من الوضع البطيء
    if not await db_check_slow_mode(chat_id, user_id):
        try:
            await message.delete()
            await context.bot.send_message(chat_id, "⏱️ الوضع البطيء مفعل، انتظر قبل إرسال رسالة أخرى.")
        except:
            pass
        return
    
    settings = await db_get_security_settings(chat_id)
    
    # التحقق من الروابط
    if settings.get('links', False) and contains_link(text):
        await delete_and_penalize(update, context, "🚫 ممنوع إرسال الروابط!")
        return
    
    # التحقق من المعرفات
    if settings.get('mentions', False) and contains_mention(text):
        await delete_and_penalize(update, context, "🚫 ممنوع إرسال المعرفات (@username)!")
        return
    
    # التحقق من الكلمات المحظورة
    if settings.get('delete_banned_words', False):
        word = await db_contains_banned_word(text, chat_id)
        if word:
            await delete_and_penalize(update, context, f"🚫 كلمة محظورة: `{word}`")
            return
    
    # حذف الوسائط
    delete_media = False
    media_type = None
    
    if settings.get('delete_videos', False) and message.video:
        delete_media = True
        media_type = "فيديو"
    elif settings.get('delete_audio', False) and message.audio:
        delete_media = True
        media_type = "صوت"
    elif settings.get('delete_animation', False) and message.animation:
        delete_media = True
        media_type = "متحرك"
    elif settings.get('delete_documents', False) and message.document:
        delete_media = True
        media_type = "مستند"
    elif settings.get('delete_stickers', False) and message.sticker:
        delete_media = True
        media_type = "ملصق"
    
    if delete_media:
        try:
            await message.delete()
            await context.bot.send_message(chat_id, f"🚫 ممنوع إرسال {media_type}!")
        except:
            pass
        
        penalty = settings.get('delete_penalty', settings.get('auto_penalty', 'none'))
        if penalty != 'none':
            duration = settings.get('delete_penalty_duration', settings.get('auto_mute_duration', 60))
            await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, duration)
        return
    
    # فحص NSFW
    if NSFW_ENABLED and (message.photo or message.video):
        try:
            if message.photo:
                file_id = message.photo[-1].file_id
                file = await context.bot.get_file(file_id)
                file_bytes = await file.download_as_bytearray()
                result = await check_nsfw_cached(bytes(file_bytes))
                if result.get('nsfw', False):
                    await message.delete()
                    await context.bot.send_message(chat_id, "🔞 تم حذف المحتوى غير اللائق!")
                    return
            elif message.video:
                file = await context.bot.get_file(message.video.file_id)
                file_bytes = await file.download_as_bytearray()
                result = await check_nsfw_video(bytes(file_bytes))
                if result.get('nsfw', False):
                    await message.delete()
                    await context.bot.send_message(chat_id, "🔞 تم حذف الفيديو غير اللائق!")
                    return
        except Exception as e:
            logger.error(f"فشل فحص NSFW: {e}")
    
    # إضافة نقاط للمستخدم
    if not user_id == context.bot.id:
        await add_points(user_id, update, context)
    
    # الردود التلقائية
    if text:
        auto_reply_settings = await db_get_auto_reply_settings(chat_id)
        if auto_reply_settings['enabled']:
            if auto_reply_settings['only_admins'] and not await is_authorized_in_group(context.bot, chat_id, user_id):
                pass
            else:
                if auto_reply_settings['ignore_bots'] and update.effective_user.is_bot:
                    pass
                else:
                    # البحث عن رد مخصص في قاعدة البيانات
                    reply = await db_get_reply(f"{chat_id}:{text.lower()}")
                    if not reply:
                        reply = await db_get_reply(text.lower())
                    
                    # البحث في الردود المدمجة
                    if not reply:
                        reply = get_reply_for_keyword(text)
                    
                    if reply:
                        try:
                            await message.reply_text(reply)
                        except:
                            pass

# ===================== نظام قياس الأداء (Metrics) =====================

class MetricsCollector:
    def __init__(self):
        self.start_time = time_module.time()
        self.total_commands = 0
        self.total_callbacks = 0
        self.total_messages = 0
        self.errors = defaultdict(int)
        self.response_times = deque(maxlen=1000)
        self._lock = asyncio.Lock()

    async def record_command(self):
        async with self._lock:
            self.total_commands += 1

    async def record_callback(self):
        async with self._lock:
            self.total_callbacks += 1

    async def record_message(self):
        async with self._lock:
            self.total_messages += 1

    async def record_error(self, error_type: str):
        async with self._lock:
            self.errors[error_type] += 1

    async def record_response_time(self, duration: float):
        async with self._lock:
            self.response_times.append(duration)

    def get_stats(self) -> dict:
        avg_response = sum(self.response_times) / len(self.response_times) if self.response_times else 0
        return {
            'uptime': time_module.time() - self.start_time,
            'total_commands': self.total_commands,
            'total_callbacks': self.total_callbacks,
            'total_messages': self.total_messages,
            'avg_response_time': avg_response,
            'errors': dict(self.errors)
        }

metrics = MetricsCollector()

# ===================== معالج الأخطاء العالمي المحسن =====================

async def global_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء العالمي"""
    try:
        error = context.error
        error_id = advanced_logger.log_error("خطأ في تحديث", error, {
            'user_id': update.effective_user.id if update and update.effective_user else None,
            'chat_id': update.effective_chat.id if update and update.effective_chat else None,
            'message': update.effective_message.text if update and update.effective_message else None
        })

        # تسجيل الخطأ في نظام القياس
        error_type = type(error).__name__
        await metrics.record_error(error_type)

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

        if isinstance(error, NetworkError):
            logger.warning(f"🌐 خطأ في الشبكة: {error}")
            return

        # إرسال رسالة للمستخدم
        if update and update.effective_user and context and context.bot:
            if not await is_user_bot(context.bot, update.effective_user.id):
                try:
                    await safe_send_markdown(
                        context.bot,
                        update.effective_user.id,
                        f"❌ حدث خطأ:\n`{str(error)[:300]}`\n(الرمز: `{error_id}`)"
                    )
                except:
                    pass

        # إرسال إشعار للمطور
        if PRIMARY_OWNER_ID and context and context.bot:
            try:
                error_text = f"🚨 **خطأ في البوت** (الرمز: {error_id})\n\n"
                error_text += f"📌 المستخدم: {update.effective_user.id if update and update.effective_user else 'غير معروف'}\n"
                error_text += f"⚠️ الخطأ: `{str(error)[:300]}`\n"
                if update and update.effective_message and update.effective_message.text:
                    error_text += f"📝 الرسالة: `{update.effective_message.text[:100]}`\n"
                if update and update.effective_chat:
                    error_text += f"💬 المحادثة: `{update.effective_chat.id}`\n"
                await safe_send_markdown(context.bot, PRIMARY_OWNER_ID, error_text)
            except Exception as e:
                logger.error(f"فشل إرسال إشعار الخطأ للمطور: {e}")
    except Exception as e:
        logger.error(f"فشل معالج الأخطاء نفسه: {e}")

# ===================== خادم الويب المبسط =====================

web_app = web.Application()

async def index_handler(request):
    """الصفحة الرئيسية لخادم الويب"""
    html_content = """<!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ريلاكس مانيجر</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                text-align: center;
                padding: 50px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
                margin: 0;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .container {
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 40px;
                max-width: 600px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            }
            h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
            }
            .version {
                font-size: 0.9em;
                opacity: 0.8;
                margin-bottom: 30px;
            }
            .status {
                background: rgba(0, 255, 0, 0.2);
                padding: 10px 20px;
                border-radius: 10px;
                display: inline-block;
                margin-bottom: 30px;
            }
            .links {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            .links a {
                color: white;
                text-decoration: none;
                background: rgba(255, 255, 255, 0.2);
                padding: 12px 20px;
                border-radius: 10px;
                transition: all 0.3s ease;
            }
            .links a:hover {
                background: rgba(255, 255, 255, 0.3);
                transform: scale(1.02);
            }
            .features {
                margin-top: 30px;
                text-align: right;
                font-size: 0.9em;
                opacity: 0.9;
            }
            .features li {
                list-style: none;
                padding: 5px 0;
            }
            .footer {
                margin-top: 30px;
                font-size: 0.8em;
                opacity: 0.7;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌿 ريلاكس مانيجر</h1>
            <div class="version">الإصدار 20.0.19</div>
            <div class="status">✅ البوت يعمل بكفاءة</div>
            <div class="links">
                <a href="/health">📊 التحقق من الصحة</a>
                <a href="https://t.me/Reelaaaxbot">🤖 البوت على تيليجرام</a>
            </div>
            <div class="features">
                <h3>✨ الميزات الرئيسية:</h3>
                <li>📡 إدارة القنوات والمجموعات</li>
                <li>🔐 نظام أمان متقدم</li>
                <li>🌐 دعم 12 لغة</li>
                <li>🎯 نظام مسابقات متكامل</li>
                <li>📊 إحصائيات وتحليلات</li>
                <li>🔞 كشف المحتوى غير اللائق</li>
            </div>
            <div class="footer">© 2026 ريلاكس مانيجر - جميع الحقوق محفوظة</div>
        </div>
    </body>
    </html>"""
    return web.Response(text=html_content, content_type="text/html", charset="utf-8")

async def health_check_handler(request):
    """نقطة التحقق من صحة البوت"""
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
            'timestamp': mecca_now_iso()
        }, status=status)
    except Exception as e:
        return web.json_response({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': mecca_now_iso()
        }, status=503)

# إضافة المسارات
web_app.router.add_get('/', index_handler)
web_app.router.add_get('/index.html', index_handler)
web_app.router.add_get('/health', health_check_handler)

async def start_web_server():
    """تشغيل خادم الويب على المنفذ الصحيح (مرة واحدة فقط)"""
    try:
        port = int(os.getenv("PORT", WEB_PORT))
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, WEB_HOST, port)
        await site.start()
        logger.info(f"✅ خادم الويب يعمل على http://{WEB_HOST}:{port}")
        global WEB_PORT_USED
        WEB_PORT_USED = port
        return True
    except OSError as e:
        if "address already in use" in str(e):
            logger.warning(f"⚠️ المنفذ {port} مشغول - قد يكون البوت يعمل بالفعل")
        else:
            logger.error(f"❌ فشل تشغيل خادم الويب: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ فشل تشغيل خادم الويب: {e}")
        return False

# ===================== نظام إدارة المهام =====================

class TaskManager:
    """إدارة المهام الخلفية"""
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

        # تنظيف المهام المكتملة
        done_tasks = {t for t in self.tasks if t.done()}
        self.tasks.difference_update(done_tasks)

        # إلغاء أقدم مهمة إذا تجاوزنا الحد
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

# ===================== دوال إعادة التشغيل التلقائي =====================

async def safe_loop(coro_func, name="background_loop"):
    """تشغيل حلقة خلفية مع إعادة تشغيل تلقائي في حال تعطلها"""
    while True:
        try:
            if asyncio.iscoroutinefunction(coro_func):
                await coro_func()
            else:
                await coro_func()
        except asyncio.CancelledError:
            logger.info(f"🛑 تم إلغاء الحلقة: {name}")
            break
        except Exception as e:
            logger.error(f"❌ تعطلت الحلقة {name}: {e}. إعادة التشغيل بعد 10 ثوانٍ...")
            await asyncio.sleep(10)

# ===================== دوال العمليات الخلفية =====================

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
            
            # التحقق من الاشتراك
            if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
                return
            
            # التحقق من صلاحيات البوت
            has_permission, permission_msg = await check_bot_permissions(bot, ch_tele_id)
            if not has_permission:
                return

            auto_recycle = await db_get_auto_recycle(user_id)
            total = await db_get_posts_count(ch_db_id)
            published = await db_get_published_count(ch_db_id)

            # إعادة التدوير التلقائي
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

            # الحصول على المنشور التالي
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

            # ترجمة المحتوى
            translation_lang = await get_user_translation_language(user_id)
            final_text = post['text']
            if translation_lang != 'off' and final_text:
                try:
                    translated = await translate_text(final_text, translation_lang)
                    if translated and translated != final_text:
                        final_text = f"{final_text}\n\n🌐 {translated}"
                except:
                    pass

            # محاولة النشر مع إعادة المحاولة
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
        except Exception as e:
            logger.error(f"خطأ في حلقة المنشورات المجدولة: {e}")

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
        except Exception as e:
            logger.error(f"خطأ في حلقة التذكيرات: {e}")

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
            
            # تنظيف ذاكرة النقاط
            await user_points_tracker.cleanup()
        except Exception as e:
            logger.error(f"خطأ في حلقة التنظيف: {e}")

async def broadcast_stats_periodically():
    """بث الإحصائيات الدورية"""
    while True:
        await asyncio.sleep(60)
        try:
            total, banned, posts, groups, channels = await db_stats()
            logger.info(f"📊 إحصائيات: مستخدمين={total}, محظورين={banned}, منشورات={posts}, مجموعات={groups}, قنوات={channels}")
        except Exception as e:
            logger.error(f"خطأ في بث الإحصائيات: {e}")

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
                            await achievement_system(winner_id, 'contest_winner')
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
        except Exception as e:
            logger.error(f"خطأ في حلقة إغلاق المسابقات: {e}")

async def refresh_group_admins_and_hidden_owners_loop(bot):
    """تحديث المشرفين والمالكين المخفيين تلقائياً"""
    while True:
        await asyncio.sleep(3600)  # كل ساعة
        try:
            groups = await db_get_all_groups(only_banned=False)
            for group in groups:
                chat_id = group['chat_id']
                try:
                    # تحديث المشرفين
                    await db_sync_group_admins(chat_id, bot)
                    
                    # التحقق من المالكين المخفيين
                    owner_info = await detect_owner_type(bot, chat_id)
                    if owner_info.get('user_id'):
                        # التحقق من وجود المالك المخفي
                        if not await db_is_hidden_owner(chat_id, owner_info['user_id']):
                            await db_register_hidden_owner_group(chat_id, owner_info['user_id'])
                            await invalidate_auth_cache(chat_id, owner_info['user_id'])
                            logger.info(f"👑 تم تسجيل المالك الحقيقي {owner_info['user_id']} كمالك مخفي للمجموعة {chat_id}")
                except Exception as e:
                    logger.error(f"فشل تحديث المجموعة {chat_id}: {e}")
        except Exception as e:
            logger.error(f"فشل تحديث المشرفين: {e}")

async def memory_monitor():
    """مراقبة الذاكرة وتحسينها تلقائياً"""
    while True:
        try:
            ram = get_ram_usage()
            if ram['percent'] > 80:
                logger.warning(f"⚠️ استخدام الذاكرة عالي: {ram['percent']}% - جاري التحسين...")
                await memory_optimizer()
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"خطأ في مراقبة الذاكرة: {e}")
            await asyncio.sleep(60)

async def self_ping_loop():
    """الحفاظ على تشغيل البوت عن طريق ping الذاتي"""
    while True:
        await asyncio.sleep(300)  # كل 5 دقائق
        try:
            # محاولة الاتصال بقاعدة البيانات
            await ensure_db_connection()
        except Exception as e:
            logger.error(f"خطأ في ping الذاتي: {e}")

async def check_bot_permissions(bot, channel_id):
    """التحقق من صلاحيات البوت في القناة"""
    try:
        bot_member = await bot.get_chat_member(channel_id, bot.id)
        if bot_member.status not in ['administrator', 'creator']:
            return False, "البوت ليس مشرفاً في هذه القناة"
        if not bot_member.can_post_messages:
            return False, "البوت ليس لديه صلاحية الإرسال في هذه القناة"
        return True, "✅"
    except Exception as e:
        return False, f"خطأ في التحقق: {str(e)[:100]}"
async def self_http_ping_loop():
    """إرسال ping داخلي للحفاظ على نشاط Render (فقط إذا كان الخادم يعمل)"""
    port = int(os.getenv("PORT", 10000))
    url = f"http://localhost:{port}/health"
    # تحقق أولي
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                if resp.status != 200:
                    logger.warning("⚠️ خادم الويب لا يستجيب، إلغاء ping")
                    return
    except:
        logger.warning("⚠️ خادم الويب غير متاح، إلغاء ping")
        return

    while True:
        await asyncio.sleep(120)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        logger.debug("✅ ping داخلي ناجح")
        except Exception:
            pass  # طبيعي

async def notify_group_admins(bot, chat_id: int, requester_id: int, chat_name: str):
    """إشعار مشرفي المجموعة بطلب التفعيل"""
    try:
        admins = await bot.get_chat_administrators(chat_id)
        if not admins:
            try:
                await bot.send_message(
                    chat_id,
                    f"📢 **طلب تفعيل البوت!**\n\n"
                    f"👤 المستخدم: {requester_id}\n"
                    f"📌 المجموعة: {chat_name}\n\n"
                    f"لتفعيل البوت، استخدم:\n"
                    f"`/syncgroup`"
                )
            except:
                pass
            return
        
        for admin in admins:
            if admin.user.id != requester_id:
                try:
                    await bot.send_message(
                        admin.user.id,
                        f"📢 **طلب تفعيل البوت!**\n\n"
                        f"👤 المستخدم: {requester_id}\n"
                        f"📌 المجموعة: {chat_name}\n"
                        f"🆔 المعرف: `{chat_id}`\n\n"
                        f"لتفعيل البوت، استخدم:\n"
                        f"`/syncgroup` في المجموعة."
                    )
                    await asyncio.sleep(0.5)
                except:
                    pass
    except Exception as e:
        logger.error(f"فشل إشعار المشرفين: {e}")

# ===================== دوال التهيئة =====================

async def init_db_improved():
    """تهيئة قاعدة البيانات مع إنشاء الجداول والفهارس"""
    async def _init(conn):
        # تمكين المفاتيح الخارجية
        await conn.execute("PRAGMA foreign_keys=ON")
        
        # إنشاء جداول المستخدمين
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
                achievements TEXT DEFAULT '[]',
                language TEXT DEFAULT 'ar'
            )
        """)
        
        # إنشاء جدول users_cache
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users_cache (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_updated TEXT
            )
        """)
        
        # إنشاء جدول user_channels
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
        
        # إنشاء جدول posts
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
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
            )
        """)
        
        # إنشاء جدول schedule
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schedule (
                channel_db_id INTEGER PRIMARY KEY,
                schedule_type TEXT DEFAULT 'interval_minutes',
                interval_minutes INTEGER,
                interval_hours INTEGER,
                interval_days INTEGER,
                days_of_week TEXT,
                specific_dates TEXT,
                publish_time TEXT,
                cron_expression TEXT,
                next_publish_date TEXT,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
            )
        """)
        
        # إنشاء جدول last_publish
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS last_publish (
                channel_db_id INTEGER PRIMARY KEY,
                last_publish_time TEXT,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
            )
        """)
        
        # إنشاء جدول scheduled_posts
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                text TEXT,
                publish_time TEXT,
                fail_count INTEGER DEFAULT 0
            )
        """)
        
        # إنشاء جدول bot_groups
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
        
        # إنشاء جدول group_admins
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_admins (
                chat_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        
        # إنشاء جدول hidden_owner_groups
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_owner_groups (
                chat_id INTEGER PRIMARY KEY,
                owner_id INTEGER,
                is_hidden INTEGER DEFAULT 1
            )
        """)
        
        # إنشاء جدول hidden_admins
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_admins (
                chat_id INTEGER,
                admin_id INTEGER,
                added_by INTEGER,
                added_at TEXT,
                PRIMARY KEY (chat_id, admin_id)
            )
        """)
        
        # إنشاء جدول user_groups_link
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_groups_link (
                user_id INTEGER,
                chat_id INTEGER,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        # إنشاء جدول group_security
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_security (
                chat_id INTEGER PRIMARY KEY,
                delete_links INTEGER DEFAULT 0,
                mentions INTEGER DEFAULT 0,
                warn_message INTEGER DEFAULT 1,
                slow_mode INTEGER DEFAULT 0,
                slow_mode_seconds INTEGER DEFAULT 5,
                welcome_enabled INTEGER DEFAULT 0,
                welcome_text TEXT,
                goodbye_enabled INTEGER DEFAULT 0,
                goodbye_text TEXT,
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
        
        # إنشاء جدول chat_locks
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_locks (
                chat_id INTEGER PRIMARY KEY,
                locked INTEGER DEFAULT 0,
                locked_at TEXT,
                locked_by INTEGER
            )
        """)
        
        # إنشاء جدول user_messages
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_messages (
                user_id INTEGER,
                chat_id INTEGER,
                message_time TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        # إنشاء جدول banned_words
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS banned_words (
                word TEXT,
                chat_id INTEGER,
                added_by INTEGER,
                added_at TEXT,
                PRIMARY KEY (word, chat_id)
            )
        """)
        
        # إنشاء جدول group_replies
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_replies (
                keyword TEXT PRIMARY KEY,
                reply TEXT
            )
        """)
        
        # إنشاء جدول auto_reply_settings
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_reply_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                only_admins INTEGER DEFAULT 0,
                ignore_bots INTEGER DEFAULT 1,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # إنشاء جدول support_tickets
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                message TEXT,
                ticket_number INTEGER,
                status TEXT,
                created_at TEXT,
                replied INTEGER DEFAULT 0
            )
        """)
        
        # إنشاء جدول settings
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # إنشاء جدول referral_settings
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # إنشاء جدول referrals
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id INTEGER,
                referred_id INTEGER,
                referred_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_rewarded INTEGER DEFAULT 0,
                PRIMARY KEY (referrer_id, referred_id)
            )
        """)
        
        # إنشاء جدول referral_rewards
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_rewards (
                user_id INTEGER PRIMARY KEY,
                referral_count INTEGER DEFAULT 0,
                total_reward_days INTEGER DEFAULT 0,
                claimed_reward_days INTEGER DEFAULT 0
            )
        """)
        
        # إنشاء جدول user_reminder_settings
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
        
        # إنشاء جدول user_levels
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_levels (
                user_id INTEGER PRIMARY KEY,
                points INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1
            )
        """)
        
        # إنشاء جدول user_translation
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_translation (
                user_id INTEGER PRIMARY KEY,
                lang TEXT DEFAULT 'off'
            )
        """)
        
        # إنشاء جدول contests
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
        
        # إنشاء جدول contest_participants
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
        
        # إنشاء جدول contest_winners
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contest_winners (
                contest_id INTEGER PRIMARY KEY,
                winner_id INTEGER,
                announced_at TEXT
            )
        """)
        
        # إنشاء جدول user_warnings
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_warnings (
                user_id INTEGER,
                chat_id INTEGER,
                warns INTEGER DEFAULT 0,
                reason TEXT,
                warned_by INTEGER,
                warned_at TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        
        # إنشاء جدول moderation_log
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS moderation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                action TEXT,
                target_id INTEGER,
                admin_id INTEGER,
                reason TEXT,
                created_at TEXT
            )
        """)
        
        # إنشاء جدول bot_admins
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY
            )
        """)
        
        # إنشاء جدول bot_channels
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_channels (
                channel_id INTEGER PRIMARY KEY,
                channel_name TEXT,
                added_by INTEGER,
                added_at TEXT,
                banned INTEGER DEFAULT 0
            )
        """)
        
        # إنشاء جدول group_rules
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_rules (
                chat_id INTEGER PRIMARY KEY,
                rules_text TEXT,
                set_by INTEGER,
                set_at TEXT
            )
        """)
        
        # إنشاء جدول allowed_sendcode_user
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS allowed_sendcode_user (
                id INTEGER PRIMARY KEY,
                user_id INTEGER
            )
        """)
        
        # إضافة المطور الأساسي كمشرف
        await conn.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (PRIMARY_OWNER_ID,))
        
        # إنشاء الفهارس لتحسين الأداء
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_channels_user ON user_channels(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_banned_words_chat ON banned_words(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_group_admins_chat ON group_admins(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_hidden_admins_chat ON hidden_admins(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_hidden_owner_groups_owner ON hidden_owner_groups(owner_id)")
        
        await conn.commit()
        
        # إضافة إعدادات الإحالات الافتراضية
        for key, value in DEFAULT_REFERRAL_SETTINGS.items():
            await conn.execute("INSERT OR IGNORE INTO referral_settings (key, value) VALUES (?, ?)", (key, value))
        
        # إضافة إعدادات البوت الافتراضية
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('publish_interval', ?)", (str(DEFAULT_PUBLISH_INTERVAL_SECONDS),))
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_ticket_number', '0')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_backup', '1')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('force_subscribe_enabled', '0')")
        
        await conn.commit()
        
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح!")
        
        await execute_db(_init)
# ====================================================================================
#                      الدالة الرئيسية النهائية المُصححة (ضعها في آخر الملف)
# ====================================================================================

async def main():
    """🚀 التشغيل الرئيسي للبوت - Webhook مع بروكسي (حل مشكلة 409)"""
    print("=" * 60)
    print("🌿 ريلاكس مانيجر - الإصدار 20.0.19 (Webhook + Proxy)")
    print("🔒 حل مشكلة Conflict 409 نهائياً")
    print("=" * 60)
    
    # ===================== 1. قاعدة البيانات =====================
    print("📌 [1/9] تهيئة قاعدة البيانات...")
    await init_db_improved()
    
    # ===================== 2. الكلمات المحظورة =====================
    print("📌 [2/9] تحميل الكلمات المحظورة...")
    try:
        words = load_banned_words_from_file([BANNED_WORDS_FILE])
        if words:
            async def add_banned(conn):
                for w in words:
                    await conn.execute(
                        "INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?, ?, ?, ?)",
                        (w, -1, PRIMARY_OWNER_ID, utc_now_iso())
                    )
                await conn.commit()
            await execute_db(add_banned)
            await rebuild_banned_patterns()
            print(f"✅ تم استيراد {len(words)} كلمة محظورة")
    except Exception as e:
        print(f"⚠️ فشل استيراد الكلمات: {e}")
    
    # ===================== 3. اللغات والردود =====================
    print("📌 [3/9] تحميل اللغات والردود...")
    load_all_languages()
    load_replies_from_file()
    
    # ===================== 4. إعداد التطبيق (بدون HTTPXRequest) =====================
    print("📌 [4/9] إعداد التطبيق...")
    
    # بناء التطبيق بالطريقة الافتراضية (تتجنب خطأ HTTPXRequest)
    application = Application.builder().token(TOKEN).build()
    application.add_error_handler(global_error_handler)
    
    # إعداد البروكسي عبر متغيرات البيئة
    if USE_PROXY:
        os.environ["HTTP_PROXY"] = PROXY_URL
        os.environ["HTTPS_PROXY"] = PROXY_URL
        print(f"🌐 استخدام بروكسي: {PROXY_URL}")
    else:
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)
        print("ℹ️ اتصال مباشر (بدون بروكسي)")
    
    # ===================== 5. الأوامر =====================
    print("📌 [5/9] تسجيل الأوامر...")
    for cmd, handler in [
        ("start", start_command_handler),
        ("help", help_command_handler),
        ("trial", trial_command_handler),
        ("subscribe", subscribe_command_handler),
        ("support", support_command_handler),
        ("syncgroup", syncgroup_command_handler),
        ("security", security_select_group_callback),
        ("register_hidden_owner", register_hidden_owner_handler),
        ("add_hidden_admin", add_hidden_admin_command),
        ("remove_hidden_admin", remove_hidden_admin_command),
        ("list_hidden_admins", list_hidden_admins_command),
        ("rank", rank_command_handler),
        ("top", top_command_handler),
        ("stats", stats_command_handler),
        ("lock", lock_chat_command_handler),
        ("unlock", unlock_chat_command_handler),
        ("schedule", schedule_post_command_handler),
        ("panel", panel_command_handler),
        ("ban", handle_moderation_commands),
        ("mute", handle_moderation_commands),
        ("warn", handle_moderation_commands),
        ("kick", handle_moderation_commands),
        ("restrict", handle_moderation_commands),
        ("pin", handle_moderation_commands),
        ("unban", handle_moderation_commands),
        ("contests", contests_command_handler),
        ("create_contest", create_contest_command_handler),
        ("declare_winner", declare_winner_command_handler),
        ("set_rules", set_rules_command_handler),
        ("rules", rules_command_handler),
        ("developer", developer_command_handler),
        ("updates", updates_command_handler),
        ("sendcode", sendcode_command_handler),
        ("set_log_channel", set_log_channel_command_handler),
        ("language", language_command_handler),
        ("support_reply", support_reply_command_handler),
    ]:
        application.add_handler(CommandHandler(cmd, handler))
    
    # ===================== 6. الأزرار (CallbackQuery) =====================
    print("📌 [6/9] تسجيل الأزرار...")
    
    # اللغة
    application.add_handler(CallbackQueryHandler(lang_callback_handler, pattern="^lang_"))
    
    # النصوص
    application.add_handler(CallbackQueryHandler(handle_text_callbacks, pattern="^(rank|top|schedule_post|language)$"))
    
    # القوائم الأساسية
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
    application.add_handler(CallbackQueryHandler(my_pending_stats_callback, pattern=f"^{CallbackData.STATS_PENDING}$"))
    application.add_handler(CallbackQueryHandler(my_full_stats_callback, pattern=f"^{CallbackData.STATS_FULL}$"))
    
    # المجموعات
    application.add_handler(CallbackQueryHandler(my_groups_callback, pattern=f"^{CallbackData.GROUPS_MY}$"))
    application.add_handler(CallbackQueryHandler(group_settings_callback, pattern=f"^{CallbackData.GROUPS_SETTINGS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(delete_group_callback, pattern="^delete_group:"))
    
    # الإعدادات
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
    
    # الأمان
    application.add_handler(CallbackQueryHandler(security_enable_all_callback, pattern=f"^{CallbackData.SECURITY_ENABLE_ALL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(security_disable_all_callback, pattern=f"^{CallbackData.SECURITY_DISABLE_ALL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(security_delete_penalty_callback, pattern=f"^{CallbackData.SECURITY_DELETE_PENALTY_PREFIX}"))
    application.add_handler(CallbackQueryHandler(set_delete_penalty_callback, pattern="^set_delete_penalty:"))
    application.add_handler(CallbackQueryHandler(confirm_enable_all_callback, pattern="^confirm_enable_all:"))
    application.add_handler(CallbackQueryHandler(security_banned_words_menu_callback, pattern=f"^{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}"))
    application.add_handler(CallbackQueryHandler(universal_security_toggle, pattern="^security:"))
    application.add_handler(CallbackQueryHandler(security_close_callback, pattern=f"^{CallbackData.SECURITY_CLOSE}$"))
    application.add_handler(CallbackQueryHandler(security_select_group_callback, pattern=f"^{CallbackData.SECURITY_SELECT_GROUP}"))
    application.add_handler(CallbackQueryHandler(security_refresh_groups_callback, pattern=f"^{CallbackData.SECURITY_REFRESH_GROUPS}$"))
    
    # الكلمات المحظورة
    application.add_handler(CallbackQueryHandler(banned_words_add_callback, pattern=f"^{CallbackData.BANNED_WORDS_ADD_PREFIX}"))
    application.add_handler(CallbackQueryHandler(banned_words_list_callback, pattern=f"^{CallbackData.BANNED_WORDS_LIST_PREFIX}"))
    application.add_handler(CallbackQueryHandler(banned_words_remove_callback, pattern=f"^{CallbackData.BANNED_WORDS_REMOVE_PREFIX}"))
    
    # العقوبات - مدة الكتم
    mute_durations = [
        ("5", "GROUP_MUTE_DURATION_5"),
        ("30", "GROUP_MUTE_DURATION_30"),
        ("60", "GROUP_MUTE_DURATION_60"),
        ("720", "GROUP_MUTE_DURATION_720"),
        ("1440", "GROUP_MUTE_DURATION_1440"),
        ("10080", "GROUP_MUTE_DURATION_10080"),
        ("PERMANENT", "GROUP_MUTE_DURATION_PERMANENT"),
    ]
    for value, attr_name in mute_durations:
        application.add_handler(CallbackQueryHandler(
            penalty_mute_duration_callback,
            pattern=f"^{getattr(CallbackData, attr_name)}$"
        ))
    
    application.add_handler(CallbackQueryHandler(penalty_menu_callback, pattern=f"^{CallbackData.PENALTY_MENU}:"))
    application.add_handler(CallbackQueryHandler(penalty_kick_callback, pattern=f"^{CallbackData.PENALTY_KICK}:"))
    application.add_handler(CallbackQueryHandler(penalty_ban_callback, pattern=f"^{CallbackData.PENALTY_BAN}:"))
    application.add_handler(CallbackQueryHandler(penalty_mute_callback, pattern=f"^{CallbackData.PENALTY_MUTE}:"))
    
    # الدعم والاشتراكات
    application.add_handler(CallbackQueryHandler(help_callback, pattern=f"^{CallbackData.HELP}$"))
    application.add_handler(CallbackQueryHandler(support_menu_callback, pattern=f"^{CallbackData.SUPPORT_MENU}$"))
    application.add_handler(CallbackQueryHandler(support_help_callback, pattern=f"^{CallbackData.SUPPORT_HELP}$"))
    application.add_handler(CallbackQueryHandler(support_ticket_callback, pattern=f"^{CallbackData.SUPPORT_TICKET}$"))
    application.add_handler(CallbackQueryHandler(support_back_callback, pattern=f"^{CallbackData.SUPPORT_BACK}$"))
    application.add_handler(CallbackQueryHandler(trial_callback, pattern=f"^{CallbackData.TRIAL}$"))
    application.add_handler(CallbackQueryHandler(subscribe_menu_callback, pattern=f"^{CallbackData.SUBSCRIBE_MENU}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_1_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_1}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_2_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_2}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_30_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_30}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_90_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_90}$"))
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
    
    # ===================== لوحة الأدمن =====================
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
    application.add_handler(CallbackQueryHandler(admin_del_reply_callback, pattern="^admin_del_reply_"))
    application.add_handler(CallbackQueryHandler(admin_banned_words_callback, pattern=f"^{CallbackData.ADMIN_BANNED_WORDS}$"))
    application.add_handler(CallbackQueryHandler(admin_add_banned_word_callback, pattern=f"^{CallbackData.ADMIN_ADD_BANNED_WORD}$"))
    application.add_handler(CallbackQueryHandler(admin_list_banned_words_callback, pattern=f"^{CallbackData.ADMIN_LIST_BANNED_WORDS}$"))
    application.add_handler(CallbackQueryHandler(admin_remove_banned_word_callback, pattern=f"^{CallbackData.ADMIN_REMOVE_BANNED_WORD}$"))
    application.add_handler(CallbackQueryHandler(admin_del_banned_word_callback, pattern="^admin_del_banned_word_"))
    
    # ===================== الردود التلقائية =====================
    application.add_handler(CallbackQueryHandler(auto_reply_toggle_callback, pattern=f"^{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_admins_callback, pattern=f"^{CallbackData.AUTO_REPLY_ADMINS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_reset_callback, pattern=f"^{CallbackData.AUTO_REPLY_RESET_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_confirm_reset_callback, pattern=f"^{CallbackData.AUTO_REPLY_CONFIRM_RESET_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_cancel_callback, pattern=f"^{CallbackData.AUTO_REPLY_CANCEL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_stats_callback, pattern=f"^{CallbackData.AUTO_REPLY_STATS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(user_auto_reply_toggle_callback, pattern=f"^{CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(admin_auto_reply_callback, pattern=f"^{CallbackData.ADMIN_AUTO_REPLY}$"))
    application.add_handler(CallbackQueryHandler(admin_auto_reply_select_callback, pattern=f"^{CallbackData.ADMIN_AUTO_REPLY_SELECT_PREFIX}"))
    
    # ===================== NSFW =====================
    application.add_handler(CallbackQueryHandler(nsfw_settings_callback, pattern=f"^{CallbackData.NSFW_SETTINGS}$"))
    application.add_handler(CallbackQueryHandler(nsfw_toggle_callback, pattern=f"^{CallbackData.NSFW_TOGGLE}$"))
    application.add_handler(CallbackQueryHandler(nsfw_threshold_callback, pattern=f"^{CallbackData.NSFW_THRESHOLD_SET}$"))
    
    # ===================== المسابقات =====================
    application.add_handler(CallbackQueryHandler(contests_menu_callback, pattern=f"^{CallbackData.CONTESTS_MENU}$"))
    application.add_handler(CallbackQueryHandler(contest_join_callback, pattern=f"^{CallbackData.CONTEST_JOIN_PREFIX}"))
    application.add_handler(CallbackQueryHandler(contest_winners_callback, pattern=f"^{CallbackData.CONTEST_WINNERS}$"))
    application.add_handler(CallbackQueryHandler(contests_back_callback, pattern=f"^{CallbackData.CONTESTS_BACK}$"))
    application.add_handler(CallbackQueryHandler(admin_create_contest_callback, pattern=f"^{CallbackData.ADMIN_CREATE_CONTEST}$"))
    application.add_handler(CallbackQueryHandler(admin_declare_winner_callback, pattern=f"^{CallbackData.ADMIN_DECLARE_WINNER}$"))
    application.add_handler(CallbackQueryHandler(admin_delete_contest_callback, pattern=f"^{CallbackData.ADMIN_DEL_CONTEST_PREFIX}"))
    
    # ===================== تبديل الحظر =====================
    application.add_handler(CallbackQueryHandler(admin_toggle_channel_ban_callback, pattern=f"^{CallbackData.ADMIN_TOGGLE_CHANNEL_BAN_PREFIX}"))
    application.add_handler(CallbackQueryHandler(admin_toggle_group_ban_callback, pattern=f"^{CallbackData.ADMIN_TOGGLE_GROUP_BAN_PREFIX}"))
    
    # ===================== إحصائيات القنوات =====================
    application.add_handler(CallbackQueryHandler(channel_stats_callback, pattern=f"^{CallbackData.CHANNEL_STATS}:"))
    application.add_handler(CallbackQueryHandler(channel_growth_callback, pattern=f"^{CallbackData.CHANNEL_GROWTH}:"))
    application.add_handler(CallbackQueryHandler(channel_stats_refresh_callback, pattern=f"^{CallbackData.CHANNEL_STATS_REFRESH}:"))
    application.add_handler(CallbackQueryHandler(my_channel_stats_callback, pattern=f"^{CallbackData.MY_CHANNEL_STATS}$"))
    
    # ===================== اشتراك إجباري =====================
    application.add_handler(CallbackQueryHandler(check_subscribe_callback_handler, pattern=f"^{CallbackData.CHECK_SUBSCRIBE}$"))
    
    # ===================== لوحة التحكم =====================
    application.add_handler(CallbackQueryHandler(panel_lock_callback_handler, pattern=f"^{CallbackData.PANEL_LOCK_PREFIX}"))
    application.add_handler(CallbackQueryHandler(panel_unlock_callback_handler, pattern=f"^{CallbackData.PANEL_UNLOCK_PREFIX}"))
    application.add_handler(CallbackQueryHandler(panel_close_callback_handler, pattern=f"^{CallbackData.PANEL_CLOSE}$"))
    
    # ===================== إجراءات متقدمة =====================
    application.add_handler(CallbackQueryHandler(advanced_actions_callback, pattern=f"^{CallbackData.ADVANCED_ACTIONS}:"))
    application.add_handler(CallbackQueryHandler(group_action_ban_callback, pattern=f"^{CallbackData.GROUP_ACTION_BAN}:"))
    application.add_handler(CallbackQueryHandler(group_action_mute_callback, pattern=f"^{CallbackData.GROUP_ACTION_MUTE}:"))
    application.add_handler(CallbackQueryHandler(group_action_warn_callback, pattern=f"^{CallbackData.GROUP_ACTION_WARN}:"))
    application.add_handler(CallbackQueryHandler(group_action_kick_callback, pattern=f"^{CallbackData.GROUP_ACTION_KICK}:"))
    application.add_handler(CallbackQueryHandler(group_action_restrict_callback, pattern=f"^{CallbackData.GROUP_ACTION_RESTRICT}:"))
    application.add_handler(CallbackQueryHandler(group_action_pin_callback, pattern=f"^{CallbackData.GROUP_ACTION_PIN}:"))
    application.add_handler(CallbackQueryHandler(group_action_log_callback, pattern=f"^{CallbackData.GROUP_ACTION_LOG}:"))
    application.add_handler(CallbackQueryHandler(group_action_unban_callback, pattern=f"^{CallbackData.GROUP_ACTION_UNBAN}:"))
    application.add_handler(CallbackQueryHandler(advanced_mute_duration_callback, pattern="^adv_mute_duration:"))
    application.add_handler(CallbackQueryHandler(publish_all_channels_callback_handler, pattern=f"^{CallbackData.PUBLISH_ALL_CHANNELS}$"))
    
    # ===================== 7. الأحداث =====================
    print("📌 [7/9] تسجيل الأحداث...")
    application.add_handler(ChatJoinRequestHandler(chat_join_request_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_chat_member_handler))
    application.add_handler(ChatMemberHandler(track_chat_add, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))
    
    # ===================== 8. المدفوعات =====================
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback_handler))
    
    # ===================== 9. تصفية الرسائل =====================
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler))
    application.add_handler(MessageHandler(filters.CAPTION & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, message_handler_main))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.AUDIO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.VOICE & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.ANIMATION & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER,
        delete_service_messages
    ))
    
    # ===================== 10. تعيين قائمة الأوامر (داخل الدالة) =====================
    print("📌 [8/9] تعيين القائمة...")
    await application.bot.set_my_commands([
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
    ])
    
    # ===================== 11. Webhook =====================
    print("📌 [9/9] إعداد Webhook...")
    await application.bot.delete_webhook(drop_pending_updates=True)
    
    host = os.getenv("RENDER_EXTERNAL_HOSTNAME", "localhost")
    webhook_url = f"https://{host}/webhook"
    await application.bot.set_webhook(url=webhook_url)
    print(f"✅ Webhook: {webhook_url}")
    
    # ===================== 12. معالج Webhook =====================
    async def webhook_handler(request):
        try:
            data = await request.json()
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
            return web.Response(status=200)
        except Exception as e:
            logger.error(f"خطأ Webhook: {e}")
            return web.Response(status=500)
    
    # إضافة المسار
    web_app.router.add_post('/webhook', webhook_handler)
    
    # ===================== 13. المهام الخلفية =====================
    print("📌 تشغيل المهام...")
    task_manager.create_task(safe_loop(memory_monitor, "memory_monitor"))
    task_manager.create_task(safe_loop(lambda: auto_publish_loop_improved(application.bot), "auto_publish"))
    task_manager.create_task(safe_loop(auto_backup, "auto_backup"))
    task_manager.create_task(safe_loop(lambda: run_scheduled_posts_loop_improved(application.bot), "scheduled_posts"))
    task_manager.create_task(safe_loop(lambda: send_reminders_loop_improved(application.bot), "reminders"))
    task_manager.create_task(safe_loop(cleanup_expired_sessions_improved, "cleanup_sessions"))
    task_manager.create_task(safe_loop(broadcast_stats_periodically, "broadcast_stats"))
    task_manager.create_task(safe_loop(cleanup_points_cache, "cleanup_points"))
    task_manager.create_task(safe_loop(lambda: auto_close_contests_loop(application.bot), "auto_close_contests"))
    task_manager.create_task(safe_loop(lambda: refresh_group_admins_and_hidden_owners_loop(application.bot), "refresh_admins"))
    task_manager.create_task(safe_loop(self_ping_loop, "ping"))
    
    # ===================== 14. خادم الويب =====================
    port = int(os.getenv("PORT", WEB_PORT))
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_HOST, port)
    await site.start()
    print(f"✅ خادم الويب: http://{WEB_HOST}:{port}")
    
    # ===================== 15. تشغيل البوت =====================
    print("=" * 60)
    print(f"🚀 البوت يعمل عبر Webhook")
    print(f"🔗 {webhook_url}")
    print("✅ تم حل مشكلة 409 نهائياً")
    print("=" * 60)
    
    try:
        await application.run_webhook(
            listen=WEB_HOST,
            port=port,
            url_path="/webhook",
            webhook_url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "chat_member", "chat_join_request", "pre_checkout_query"]
        )
    except KeyboardInterrupt:
        print("🛑 تم الإيقاف")
    finally:
        await application.bot.delete_webhook()
        await db_pool.close()
        await task_manager.cancel_all()
        print("🧹 تنظيف الموارد")


# ====================================================================================
#                      دالة الحلقات الآمنة
# ====================================================================================

async def safe_loop(coro_func, name="background"):
    """تشغيل حلقة مع إعادة تشغيل تلقائي"""
    while True:
        try:
            if asyncio.iscoroutinefunction(coro_func):
                await coro_func()
            else:
                await coro_func()
        except asyncio.CancelledError:
            print(f"🛑 إلغاء: {name}")
            break
        except Exception as e:
            print(f"❌ خطأ في {name}: {e}")
            await asyncio.sleep(10)


# ====================================================================================
#                      نقطة الدخول
# ====================================================================================

if __name__ == "__main__":
    try:
        print("🚀 بدء البوت...")
        if not TOKEN:
            raise ValueError("BOT_TOKEN غير موجود")
        if not PRIMARY_OWNER_ID:
            raise ValueError("MAIN_ADMIN_ID غير موجود")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 تم الإيقاف")
        sys.exit(0)
    except Exception as e:
        print(f"❌ خطأ: {e}")
        traceback.print_exc()
        sys.exit(1)

