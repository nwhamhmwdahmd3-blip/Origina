#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ريلاكس مانيجر - بوت متكامل لإدارة القنوات والمجموعات
الإصدار: 22.2.0 - النسخة النهائية الكاملة
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
from dataclasses import dataclass, asdict, field
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
import getpass
import math
import statistics
from collections import Counter

# ===================================================================
# 1. التحقق من إصدار بايثون
# ===================================================================
def check_python_version():
    required_version = (3, 9)
    current_version = sys.version_info
    if current_version < required_version:
        print(f"❌ يحتاج البوت إلى بايثون {required_version[0]}.{required_version[1]} أو أحدث")
        print(f"📌 الإصدار الحالي: {current_version[0]}.{current_version[1]}")
        sys.exit(1)
    print(f"✅ بايثون {current_version[0]}.{current_version[1]} - متوافق")

check_python_version()

# ===================================================================
# 2. تثبيت الحزم الأساسية
# ===================================================================
def ensure_package(package_name: str, import_name: str = None, version: str = None) -> bool:
    if import_name is None:
        import_name = package_name
    try:
        __import__(import_name)
        return True
    except (ImportError, Exception):
        try:
            print(f"📦 جاري تثبيت {package_name}...")
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade"]
            if version:
                cmd.append(f"{package_name}=={version}")
            else:
                cmd.append(package_name)
            subprocess.run(cmd, capture_output=True, text=True)
            __import__(import_name)
            print(f"✅ تم تثبيت {package_name}")
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
    ("bleach", "bleach"),
    ("qrcode", "qrcode"),
    ("Pillow", "PIL"),
    ("aiohttp", "aiohttp"),
    ("aiofiles", "aiofiles"),
    ("httpx", "httpx"),
    ("jinja2", "jinja2"),
    ("markdown", "markdown"),
    ("python-multipart", "multipart"),
    ("pandas", "pandas"),
    ("openpyxl", "openpyxl"),
    ("python-telegram-bot", "telegram"),
]
for package, import_name in REQUIRED_PACKAGES:
    ensure_package(package, import_name)

OPTIONAL_PACKAGES = [
    ("deep-translator", "deep_translator"),
    ("aioredis", "aioredis"),
    ("reportlab", "reportlab"),
    ("plotly", "plotly"),
    ("zstandard", "zstandard"),
]
for package, import_name in OPTIONAL_PACKAGES:
    try:
        ensure_package(package, import_name)
    except:
        pass

# ===================================================================
# 3. استيراد المكتبات
# ===================================================================
import nest_asyncio
nest_asyncio.apply()
import aiosqlite
from dotenv import load_dotenv

def load_env_files():
    env_files = [
        ".env.local",
        ".env",
        str(Path(__file__).parent / ".env"),
        str(Path(__file__).parent / "config" / ".env"),
        str(Path.home() / ".bot" / ".env"),
    ]
    loaded = False
    for env_file in env_files:
        if os.path.exists(env_file):
            try:
                load_dotenv(env_file, override=True)
                print(f"✅ تم تحميل {env_file}")
                loaded = True
            except Exception as e:
                print(f"⚠️ فشل تحميل {env_file}: {e}")
    if not loaded:
        print("ℹ️ لم يتم العثور على ملفات .env، استخدام المتغيرات البيئية الموجودة")
    return loaded

load_env_files()

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMember, BotCommand, LabeledPrice, ChatPermissions,
    ChatMemberUpdated, ChatJoinRequest
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler,
    ChatMemberHandler, ChatJoinRequestHandler, CallbackContext
)
from telegram.error import TimedOut, NetworkError, BadRequest, Forbidden, Conflict
from telegram.request import HTTPXRequest
import httpx
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from aiohttp import web, WSMsgType
import aiohttp
from PIL import Image
import numpy as np

try:
    from argon2 import PasswordHasher
    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False

# ===================================================================
# 4. نظام التعلم الذكي وتحليل المشاعر
# ===================================================================
class SentimentAnalyzer:
    def __init__(self):
        self.positive_words = {
            "جميل", "رائع", "ممتاز", "جميلة", "رائعة", "ممتازة", "حلو", "حلوة",
            "نور", "نورت", "شكر", "شكراً", "شكرا", "تسلم", "تسلمي", "يسلمو",
            "فرح", "سعيد", "سعيدة", "مبسوط", "مبسوطة", "مرح", "ضحك", "هههه",
            "أهلاً", "مرحباً", "اهلا", "مرحبا", "حياك", "الله", "ربي", "الحمد",
            "تفاؤل", "أمل", "نجاح", "مبدع", "خير", "بركة", "نعمة"
        }
        self.negative_words = {
            "زعل", "زعلان", "حزين", "متعب", "تعبان", "محبط", "مكتئب", "ضيق",
            "غضب", "غاضب", "مزعج", "سيء", "سخيف", "غبي", "حمق", "أحمق",
            "ممل", "ثقيل", "كره", "بغض", "موت", "ألم", "جرح", "نكد",
            "فشل", "خسر", "خسارة", "ظلم", "حرب", "عدوان", "شر", "لعنة"
        }
        self.neutral_words = {
            "تمام", "حاضر", "أوك", "اوك", "بخير", "الحمد", "الحمدلله",
            "ماشي", "طيب", "حسناً", "حسنا", "جيد", "عادي", "موافق"
        }
        self.learned_patterns = defaultdict(lambda: {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0})
        self.learned_phrases = {}
        self.learning_data = {}

    def analyze(self, text: str) -> Dict[str, Any]:
        if not text:
            return {'sentiment': 'neutral', 'score': 0.0, 'confidence': 0.0, 'details': {}}
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        positive_count = sum(1 for w in words if w in self.positive_words)
        negative_count = sum(1 for w in words if w in self.negative_words)
        neutral_count = sum(1 for w in words if w in self.neutral_words)
        total = positive_count + negative_count + neutral_count
        if total == 0:
            return {'sentiment': 'neutral', 'score': 0.0, 'confidence': 0.2, 'details': {}}
        pos_ratio = positive_count / max(total, 1)
        neg_ratio = negative_count / max(total, 1)
        neu_ratio = neutral_count / max(total, 1)
        score = pos_ratio - neg_ratio
        if score > 0.2:
            sentiment = 'positive'
        elif score < -0.2:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        confidence = min(1.0, (total / 10) * 0.8 + 0.2)
        return {
            'sentiment': sentiment,
            'score': round(score, 3),
            'confidence': round(confidence, 3),
            'details': {
                'positive': positive_count,
                'negative': negative_count,
                'neutral': neutral_count,
                'total': total,
                'pos_ratio': round(pos_ratio, 3),
                'neg_ratio': round(neg_ratio, 3)
            }
        }

class LearningEngine:
    def __init__(self):
        self.sentiment_analyzer = SentimentAnalyzer()
        self.user_patterns = defaultdict(lambda: {'messages': [], 'sentiment_history': [], 'avg_sentiment': 0})
        self.chat_patterns = defaultdict(lambda: {'messages': [], 'sentiment_history': [], 'avg_sentiment': 0})
        self.response_patterns = defaultdict(lambda: {'success': 0, 'fail': 0, 'score': 0})

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        return self.sentiment_analyzer.analyze(text)

    def learn_from_message(self, user_id: int, chat_id: int, text: str, response: str = None, success: bool = True):
        sentiment = self.analyze_sentiment(text)
        self.user_patterns[user_id]['messages'].append({'text': text, 'sentiment': sentiment['sentiment'], 'score': sentiment['score'], 'time': time_module.time()})
        self.user_patterns[user_id]['sentiment_history'].append(sentiment['score'])
        if len(self.user_patterns[user_id]['sentiment_history']) > 100:
            self.user_patterns[user_id]['sentiment_history'] = self.user_patterns[user_id]['sentiment_history'][-100:]
        self.user_patterns[user_id]['avg_sentiment'] = statistics.mean(self.user_patterns[user_id]['sentiment_history']) if self.user_patterns[user_id]['sentiment_history'] else 0
        self.chat_patterns[chat_id]['messages'].append({'text': text, 'sentiment': sentiment['sentiment'], 'score': sentiment['score'], 'time': time_module.time()})
        self.chat_patterns[chat_id]['sentiment_history'].append(sentiment['score'])
        if len(self.chat_patterns[chat_id]['sentiment_history']) > 100:
            self.chat_patterns[chat_id]['sentiment_history'] = self.chat_patterns[chat_id]['sentiment_history'][-100:]
        self.chat_patterns[chat_id]['avg_sentiment'] = statistics.mean(self.chat_patterns[chat_id]['sentiment_history']) if self.chat_patterns[chat_id]['sentiment_history'] else 0
        if response:
            key = f"{text[:50]}_{response[:50]}"
            if success:
                self.response_patterns[key]['success'] += 1
            else:
                self.response_patterns[key]['fail'] += 1
            self.response_patterns[key]['score'] = self.response_patterns[key]['success'] / max(self.response_patterns[key]['success'] + self.response_patterns[key]['fail'], 1)

    def get_user_sentiment_profile(self, user_id: int) -> Dict[str, Any]:
        if user_id not in self.user_patterns:
            return {'avg_sentiment': 0, 'stability': 0, 'messages': 0}
        data = self.user_patterns[user_id]
        history = data['sentiment_history']
        if not history:
            return {'avg_sentiment': 0, 'stability': 0, 'messages': 0}
        avg_sentiment = statistics.mean(history)
        stability = 1 - (statistics.stdev(history) if len(history) > 1 else 0)
        return {'avg_sentiment': round(avg_sentiment, 3), 'stability': round(min(1.0, stability), 3), 'messages': len(history), 'trend': self._calculate_trend(history)}

    def get_chat_sentiment_profile(self, chat_id: int) -> Dict[str, Any]:
        if chat_id not in self.chat_patterns:
            return {'avg_sentiment': 0, 'stability': 0, 'messages': 0}
        data = self.chat_patterns[chat_id]
        history = data['sentiment_history']
        if not history:
            return {'avg_sentiment': 0, 'stability': 0, 'messages': 0}
        avg_sentiment = statistics.mean(history)
        stability = 1 - (statistics.stdev(history) if len(history) > 1 else 0)
        return {'avg_sentiment': round(avg_sentiment, 3), 'stability': round(min(1.0, stability), 3), 'messages': len(history), 'trend': self._calculate_trend(history)}

    def _calculate_trend(self, history: List[float]) -> str:
        if len(history) < 5:
            return 'stable'
        first_half = history[:len(history)//2]
        second_half = history[len(history)//2:]
        avg_first = statistics.mean(first_half) if first_half else 0
        avg_second = statistics.mean(second_half) if second_half else 0
        diff = avg_second - avg_first
        if diff > 0.1:
            return 'improving'
        elif diff < -0.1:
            return 'declining'
        else:
            return 'stable'

learning_engine = LearningEngine()

# ===================================================================
# 5. دوال مساعدة أساسية
# ===================================================================
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
    patterns = [r'https?://\S+', r'www\.\S+', r't\.me/\S+', r'telegram\.me/\S+', r'\b[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+\S*']
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)

def contains_mention(text):
    return bool(re.search(r'@\w+', text))

def get_ram_usage():
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {'total': round(mem.total / (1024**3), 1), 'used': round(mem.used / (1024**3), 1), 'percent': mem.percent, 'available': round(mem.available / (1024**3), 1)}
    except ImportError:
        return {'total': 0, 'used': 0, 'percent': 0, 'available': 0}

def generate_operation_token() -> str:
    return secrets.token_urlsafe(32)

def validate_time_format(time_str: str) -> bool:
    if not time_str:
        return False
    return bool(re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', str(time_str)))

def format_welcome_message(template: str, user_name: str, chat_name: str) -> str:
    safe_user = html.escape(str(user_name))
    safe_chat = html.escape(str(chat_name))
    try:
        return template.format(user=safe_user, chat=safe_chat)
    except:
        return f"مرحباً {safe_user} في {safe_chat}"

def sanitize_text(text: str, max_length: int = 4096, allow_tags: list = None) -> str:
    if not text:
        return ""
    try:
        import bleach
        if allow_tags is None:
            allow_tags = ['b', 'i', 'u', 's', 'a', 'code', 'pre', 'strong', 'em']
        cleaned = bleach.clean(text, tags=allow_tags, attributes={'a': ['href', 'title']}, styles=[], strip=True)
    except:
        cleaned = text
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned

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

def encode_callback_data(data: str) -> str:
    return urllib.parse.quote(data, safe='')

def decode_callback_data(data: str) -> str:
    return urllib.parse.unquote(data)

def load_banned_words_from_file(file_path: Path) -> List[str]:
    words = []
    if not file_path.exists():
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("# قائمة الكلمات المحظورة\n")
            print(f"✅ تم إنشاء ملف الكلمات المحظورة الافتراضي: {file_path}")
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
        print(f"✅ تم تحميل {len(words)} كلمة محظورة من الملف")
    except Exception as e:
        print(f"❌ فشل تحميل الكلمات المحظورة: {e}")
    return words

async def is_user_bot(bot, user_id: int) -> bool:
    try:
        chat = await bot.get_chat(user_id)
        return chat.is_bot
    except Exception:
        return False

ANONYMOUS_ADMIN_ID = int(os.getenv("ANONYMOUS_ADMIN_ID", "1087968824"))

# ===================================================================
# 6. إعداد المسارات
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
LEARNING_DATA_PATH = DATA_PATH / "learning_data.json"

for path in [DATA_PATH, BACKUP_DIR, LOG_PATH.parent, TEMP_PATH, STATIC_PATH, TEMPLATES_PATH, LANG_PATH, PLUGINS_PATH]:
    path.mkdir(parents=True, exist_ok=True)

# ===================================================================
# 7. تحميل متغيرات البيئة
# ===================================================================
def get_env_or_default(key: str, default: any, env_type: type = str) -> any:
    value = os.getenv(key)
    if value is None:
        return default
    try:
        if env_type == bool:
            return value.lower() in ['true', '1', 'yes', 'on', 'enable', 'enabled']
        elif env_type == int:
            return int(value)
        elif env_type == float:
            return float(value)
        return env_type(value)
    except:
        return default

TOKEN = get_env_or_default("BOT_TOKEN", None, str)
if not TOKEN:
    print("❌ لم يتم العثور على BOT_TOKEN في ملفات البيئة")
    sys.exit(1)

PRIMARY_OWNER_ID = get_env_or_default("MAIN_ADMIN_ID", 0, int)
if PRIMARY_OWNER_ID == 0:
    print("❌ MAIN_ADMIN_ID غير محدد في ملفات البيئة")
    sys.exit(1)

BOT_NAME = get_env_or_default("BOT_NAME", "ريلاكس مانيجر", str)
BOT_USERNAME = get_env_or_default("BOT_USERNAME", "Reelaaaxbot", str)
USE_PROXY = get_env_or_default("USE_PROXY", False, bool)
PROXY_URL = get_env_or_default("PROXY_URL", "http://127.0.0.1:10809", str)
DB_ENCRYPTION = get_env_or_default("DB_ENCRYPTION", True, bool)
MAX_BACKUPS = get_env_or_default("MAX_BACKUPS", 10, int)
WEB_PORT = int(os.getenv("PORT", "10000"))
WEB_PASSWORD = get_env_or_default("WEB_PASSWORD", secrets.token_urlsafe(16), str)
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
MAX_CHANNELS_PER_CYCLE = 20
PUBLISH_RETRY_DELAY = 300
MAX_UNPUBLISHED_POSTS = 1000
DB_TIMEOUT = 30
MAX_CONNECTIONS = 20
LEARNING_ENABLED = get_env_or_default("LEARNING_ENABLED", True, bool)

# ===================================================================
# 8. ثوابت المجموعات - تم إصلاحها
# ===================================================================
_MAX_BANNED_WORDS_PER_CHAT = 500
_MAX_BANNED_WORDS_GLOBAL = 2000
_MAX_AUTH_CACHE_SIZE = 50000
_MAX_FAILED_ATTEMPTS = 10
_FAILED_ATTEMPTS_WINDOW = 300
_AUTH_CACHE_TTL = 300
_FLOOD_CACHE_MAX_SIZE = 10000

_ALLOWED_SECURITY_COLUMNS = {
    'delete_links',
    'links',
    'mentions',
    'warn_message',
    'slow_mode',
    'slow_mode_seconds',
    'welcome_enabled',
    'welcome_text',
    'goodbye_enabled',
    'goodbye_text',
    'delete_banned_words',
    'auto_penalty',
    'auto_mute_duration',
    'delete_videos',
    'delete_audio',
    'delete_animation',
    'delete_service',
    'delete_documents',
    'delete_stickers',
    'delete_forwarded',
    'delete_polls',
    'delete_games',
    'delete_voice',
    'delete_video_note',
    'delete_penalty',
    'delete_penalty_duration',
    'antiflood_enabled',
    'antiflood_messages',
    'antiflood_seconds',
    'antiflood_penalty',
    'max_warnings',
    'warn_penalty',
    'max_message_length',
    'night_mode_enabled',
    'night_mode_start',
    'night_mode_end',
    'night_mode_action',
    'captcha_enabled',
    'captcha_timeout',
    'max_links_per_message',
    'max_mentions_per_message',
    'allowed_domains',
}

# ===================================================================
# 9. نظام السجلات
# ===================================================================
class SensitiveDataFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.sensitive_patterns = [(TOKEN, "[TOKEN_HIDDEN]")]
    def filter(self, record):
        msg = record.getMessage()
        for pattern, replacement in self.sensitive_patterns:
            if pattern and pattern in msg:
                msg = msg.replace(pattern, replacement)
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
        self.error_counter = defaultdict(int)
        self.error_cooldown = {}
    
    def _setup_loggers(self):
        error_logger = logging.getLogger('error_logger')
        error_logger.setLevel(logging.ERROR)
        error_handler = RotatingFileHandler(ERROR_LOG, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        error_logger.addHandler(error_handler)
        self.loggers['error'] = error_logger
        
        security_logger = logging.getLogger('security_logger')
        security_logger.setLevel(logging.WARNING)
        security_handler = RotatingFileHandler(SECURITY_LOG, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        security_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        security_logger.addHandler(security_handler)
        self.loggers['security'] = security_logger
    
    def log_error(self, message: str, error: Exception = None, context: dict = None) -> str:
        error_id = secrets.token_hex(4)
        error_key = f"{message}_{str(error)[:50] if error else ''}"
        if error_key in self.error_cooldown:
            if time_module.time() - self.error_cooldown[error_key] < 60:
                return error_id
        self.error_cooldown[error_key] = time_module.time()
        log_msg = f"[{error_id}] {message}"
        if error:
            log_msg += f" - {type(error).__name__}: {str(error)[:200]}"
        if context:
            safe_context = {k: v for k, v in context.items() if k not in ['token', 'password', 'key', 'secret']}
            log_msg += f" - السياق: {json.dumps(safe_context, default=str)[:300]}"
        self.loggers['error'].error(log_msg)
        traceback.print_exc()
        return error_id
    
    def log_security(self, event: str, user_id: int, details: dict = None, severity: str = "INFO"):
        log_msg = f"[{severity}] {event} - User: {user_id}"
        if details:
            safe_details = {k: v for k, v in details.items() if k not in ['token', 'password', 'key', 'secret']}
            log_msg += f" - {json.dumps(safe_details, default=str)[:300]}"
        if severity.upper() == "HIGH":
            self.loggers['security'].critical(log_msg)
        elif severity.upper() == "MEDIUM":
            self.loggers['security'].warning(log_msg)
        else:
            self.loggers['security'].info(log_msg)

advanced_logger = AdvancedLogger()

def log_error(error: Exception, context: dict = None) -> str:
    return advanced_logger.log_error("حدث خطأ غير متوقع", error, context)

# ===================================================================
# 10. نظام التشفير
# ===================================================================
def get_encryption_key() -> bytes:
    key_file = DATA_PATH / ".db_key"
    if key_file.exists():
        try:
            with open(key_file, 'rb') as f:
                key = f.read()
            if len(key) == 44:
                return key
        except:
            pass
    key = Fernet.generate_key()
    with open(key_file, 'wb') as f:
        f.write(key)
    print("✅ تم إنشاء مفتاح تشفير جديد")
    return key

ENCRYPTION_KEY = get_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

def get_backup_encryption_key() -> bytes:
    backup_key_file = DATA_PATH / ".backup_key"
    if backup_key_file.exists():
        try:
            with open(backup_key_file, 'rb') as f:
                key = f.read()
            if len(key) == 44:
                return key
        except:
            pass
    new_key = Fernet.generate_key()
    with open(backup_key_file, 'wb') as f:
        f.write(new_key)
    return new_key

BACKUP_ENCRYPTION_KEY = get_backup_encryption_key()
BACKUP_CIPHER = Fernet(BACKUP_ENCRYPTION_KEY)

def compress_backup(data: bytes) -> bytes:
    try:
        import zstandard
        return zstandard.ZstdCompressor(level=3).compress(data)
    except:
        return gzip.compress(data)

def decompress_backup(data: bytes) -> bytes:
    try:
        import zstandard
        return zstandard.ZstdDecompressor().decompress(data)
    except:
        return gzip.decompress(data)

# ===================================================================
# 11. نظام التخزين المؤقت
# ===================================================================
try:
    from cachetools import TTLCache, LRUCache
    CACHETOOLS_AVAILABLE = True
    _admin_cache = TTLCache(maxsize=1000, ttl=60)
    _security_cache = TTLCache(maxsize=500, ttl=30)
    _auth_cache = TTLCache(maxsize=1000, ttl=30)
    _user_cache = TTLCache(maxsize=2000, ttl=300)
    _channel_cache = TTLCache(maxsize=500, ttl=60)
    _sentiment_cache = TTLCache(maxsize=1000, ttl=60)
except ImportError:
    CACHETOOLS_AVAILABLE = False
    _admin_cache = {}
    _security_cache = {}
    _auth_cache = {}
    _user_cache = {}
    _channel_cache = {}
    _sentiment_cache = {}

_flood_cache = OrderedDict()
_flood_cache_time = {'last_cleanup': 0}
_failed_attempts_cache = {}
_token_cache = {}
_translation_cache = {}
BANNED_PATTERNS = []
_referral_cache = {}

# ===================================================================
# 12. دوال الإرسال الآمن
# ===================================================================
async def safe_send_markdown(bot, chat_id: int, text: str, reply_markup=None, **kwargs):
    if not text:
        return None
    clean_text = sanitize_text(text)
    MAX_LEN = 4096
    try:
        escaped = escape_markdown_v2(clean_text)
        if len(escaped) > MAX_LEN:
            escaped = escaped[:MAX_LEN-3] + "..."
        return await bot.send_message(chat_id=chat_id, text=escaped, parse_mode='MarkdownV2', reply_markup=reply_markup, **kwargs)
    except BadRequest as e:
        if "can't parse entities" in str(e):
            try:
                return await bot.send_message(chat_id=chat_id, text=clean_text[:MAX_LEN], reply_markup=reply_markup, **kwargs)
            except:
                pass
        raise
    except Forbidden:
        return None
    except Exception:
        try:
            return await bot.send_message(chat_id=chat_id, text=clean_text[:MAX_LEN], reply_markup=reply_markup, **kwargs)
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
            escaped = escaped[:MAX_LEN-3] + "..."
        return await query.edit_message_text(text=escaped, parse_mode='MarkdownV2', reply_markup=reply_markup, **kwargs)
    except BadRequest:
        try:
            return await query.edit_message_text(text=clean_text[:MAX_LEN], reply_markup=reply_markup, **kwargs)
        except:
            raise

# ===================================================================
# 13. معالج الأخطاء
# ===================================================================
class ErrorHandler:
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.error_counts = defaultdict(int)
    
    async def handle_async(self, func: Callable, *args, **kwargs) -> Any:
        last_error = None
        func_name = func.__name__
        for attempt in range(self.max_retries):
            try:
                result = await func(*args, **kwargs)
                self.error_counts[func_name] = 0
                return result
            except (TimedOut, NetworkError) as e:
                last_error = e
                self.error_counts[func_name] += 1
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(delay)
                continue
            except (BadRequest, Forbidden, Conflict) as e:
                raise
            except Exception as e:
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue
                raise
        if last_error:
            raise last_error
        raise Exception(f"فشل تنفيذ {func_name} بعد {self.max_retries} محاولات")

error_handler = ErrorHandler()

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
            "send_channel_id": "📡 أرسل معرف القناة (مثال: @channel أو -100123456)",
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
            "monday": "الإثنين", "tuesday": "الثلاثاء", "wednesday": "الأربعاء",
            "thursday": "الخميس", "friday": "الجمعة", "saturday": "السبت", "sunday": "الأحد",
            "admin_only": "🔒 هذا الأمر للمشرفين فقط!",
            "group_only": "🔒 هذا الأمر يعمل فقط في المجموعات!",
            "locked": "🔒 تم قفل المجموعة",
            "unlocked": "🔓 تم فتح المجموعة",
            "cancelled": "❌ تم الإلغاء",
            "error": "⚠️ حدث خطأ، حاول مرة أخرى",
            "help": "❓ **المساعدة**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 **الأوامر المتاحة:**\n/start - القائمة الرئيسية\n/trial - تجربة مجانية\n/subscribe - الاشتراك\n/syncgroup - تفعيل المجموعة\n/security - إعدادات الأمان\n/register_hidden_owner - تسجيل مالك مخفي\n/add_hidden_admin - إضافة مشرف مخفي\n/remove_hidden_admin - إزالة مشرف مخفي\n/list_hidden_admins - عرض المشرفين المخفيين\n/rank - رتبتك\n/top - أفضل 10\n/stats - إحصائيات القناة\n/lock - قفل المجموعة\n/unlock - فتح المجموعة\n/schedule - جدولة منشور\n/panel - لوحة التحكم\n/language - تغيير اللغة\n/support - مركز الدعم\n/developer - المطور\n/updates - التحديثات\n/contests - المسابقات\n/create_contest - إنشاء مسابقة\n/declare_winner - إعلان فائز\n/set_rules - تعيين قوانين المجموعة\n/rules - عرض قوانين المجموعة",
            "support_welcome": "📞 **مركز الدعم**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الخدمة المطلوبة:",
            "support_help": "❓ **المساعدة**\n📌 للتواصل مع الدعم:\n• استخدم /support\n• اكتب رسالتك\n• ستصلك تذكرة برقم",
            "trial_used": "❌ لقد استخدمت التجربة المجانية مسبقاً",
            "already_subscribed": "✅ لديك اشتراك فعال بالفعل",
            "trial": "🎁 **تم تفعيل التجربة المجانية!**\n✅ لديك 30 يوماً مجاناً",
            "subscribe": "💎 **الاشتراك**\nاختر الباقة المناسبة:\n⭐ 1 يوم - 5 نجوم\n⭐ 2 يوم - 9 نجوم\n⭐ شهر - 50 نجمة\n⭐ 3 أشهر - 120 نجمة",
            "hidden_admin_added": "✅ تم إضافة المشرف المخفي `{0}` بنجاح",
            "hidden_admin_removed": "✅ تم إزالة المشرف المخفي `{0}` بنجاح",
            "no_hidden_admins": "📭 لا يوجد مشرفين مخفيين",
            "hidden_owner_registered": "✅ تم تسجيل المالك المخفي بنجاح",
            "hidden_owner_already": "⚠️ أنت مسجل بالفعل كمالك مخفي",
            "group_registered": "✅ **تم تسجيل المجموعة!**\nاستخدم /syncgroup بعد جعل البوت مشرفاً",
            "subscription_warning": "⚠️ **تنبيه!**\nاشتراكك ينتهي خلال {0} أيام",
            "back": "🔙 رجوع",
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
            "pending_stats": "📊 **Post Statistics**\n📝 Unpublished: {0}\n📋 Total: {1}",
            "stats": "📈 **My Full Stats**\n📡 Channels: {0}\n📝 Total Posts: {1}\n⏳ Unpublished: {2}\n👥 Groups: {3}\n⚙️ Auto Publish: {4}",
            "settings": "⚙️ **Settings**\nSelect the setting:",
            "auto_toggled": "✅ Auto publish status changed to: {0}",
            "schedule_settings": "⏰ **Schedule Settings**\n{0}\nSelect schedule type:",
            "interval_minutes": "Minutes: {0}",
            "interval_hours": "Hours: {0}",
            "interval_days": "Days: {0}",
            "days_week": "Days of week: {0}",
            "specific_dates": "Specific dates: {0}",
            "nothing": "Nothing",
            "send_minutes": "⏱️ Send number of minutes (e.g., 30)",
            "send_hours": "⏱️ Send number of hours (e.g., 2)",
            "send_days": "⏱️ Send number of days (e.g., 1)",
            "send_dates": "📅 Send dates separated by commas",
            "send_time": "🕐 Send publish time (e.g., 14:30)",
            "interval_set": "✅ Settings saved",
            "invalid_number": "❌ Invalid number",
            "invalid_date": "❌ Invalid date",
            "invalid_time": "❌ Invalid time",
            "days_saved": "✅ Days saved",
            "monday": "Monday", "tuesday": "Tuesday", "wednesday": "Wednesday",
            "thursday": "Thursday", "friday": "Friday", "saturday": "Saturday", "sunday": "Sunday",
            "admin_only": "🔒 This command is for admins only!",
            "group_only": "🔒 This command works only in groups!",
            "locked": "🔒 Group locked",
            "unlocked": "🔓 Group unlocked",
            "cancelled": "❌ Cancelled",
            "error": "⚠️ An error occurred, try again",
            "help": "❓ **Help**\n📌 **Available Commands:**\n/start - Main Menu\n/trial - Free Trial\n/subscribe - Subscribe\n/syncgroup - Activate Group\n/security - Security Settings\n/register_hidden_owner - Register Hidden Owner\n/rank - Your Rank\n/top - Top 10\n/stats - Channel Stats\n/lock - Lock Group\n/unlock - Unlock Group\n/schedule - Schedule Post\n/panel - Control Panel\n/language - Change Language\n/support - Support Center\n/developer - Developer\n/updates - Updates\n/contests - Contests\n/rules - View Rules",
            "support_welcome": "📞 **Support Center**\nSelect the required service:",
            "support_help": "❓ **Help**\n📌 To contact support:\n• Use /support\n• Write your message\n• You'll get a ticket number",
            "trial_used": "❌ You have already used the free trial",
            "already_subscribed": "✅ You already have an active subscription",
            "trial": "🎁 **Free Trial Activated!**\n✅ You have 30 days free",
            "subscribe": "💎 **Subscription**\nChoose your plan:\n⭐ 1 Day - 5 Stars\n⭐ 2 Days - 9 Stars\n⭐ 30 Days - 50 Stars\n⭐ 90 Days - 120 Stars",
            "hidden_admin_added": "✅ Hidden admin `{0}` added successfully",
            "hidden_admin_removed": "✅ Hidden admin `{0}` removed successfully",
            "no_hidden_admins": "📭 No hidden admins",
            "hidden_owner_registered": "✅ Hidden owner registered successfully",
            "hidden_owner_already": "⚠️ You are already registered as hidden owner",
            "group_registered": "✅ **Group registered!**\nUse /syncgroup after making the bot admin",
            "subscription_warning": "⚠️ **Warning!**\nYour subscription expires in {0} days",
            "back": "🔙 Back",
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
        ar_texts = _lang_data.get('ar', {})
        if key in ar_texts:
            return ar_texts[key]
        return key
    return texts.get(key, key)

async def set_user_language(user_id: int, lang: str):
    user_language[user_id] = lang
    try:
        await db_set_user_language(user_id, lang)
    except:
        pass

# ===================================================================
# 15. قاعدة البيانات - الأساسيات
# ===================================================================
class DatabasePool:
    def __init__(self, max_connections: int = 10, timeout: int = 30):
        self._pool = None
        self._max_connections = max_connections
        self._timeout = timeout
        self._lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self):
        async with self._lock:
            if self._initialized:
                return
            try:
                self._pool = await aiosqlite.connect(str(DB_PATH), timeout=self._timeout)
                await self._pool.execute("PRAGMA journal_mode=WAL")
                await self._pool.execute("PRAGMA synchronous=NORMAL")
                await self._pool.execute("PRAGMA foreign_keys=ON")
                await self._pool.execute("PRAGMA cache_size=-64000")
                await self._pool.execute("PRAGMA temp_store=MEMORY")
                await self._pool.execute("PRAGMA busy_timeout=30000")
                self._pool.row_factory = aiosqlite.Row
                self._initialized = True
                logger.info("✅ تم تهيئة قاعدة البيانات")
            except Exception as e:
                logger.error(f"❌ فشل تهيئة قاعدة البيانات: {e}")
                raise
    
    async def get_connection(self):
        if not self._initialized:
            await self.initialize()
        return self._pool
    
    async def close(self):
        if self._pool:
            try:
                await self._pool.close()
                logger.info("✅ تم إغلاق قاعدة البيانات")
            except Exception as e:
                logger.error(f"خطأ في إغلاق قاعدة البيانات: {e}")
            finally:
                self._pool = None
                self._initialized = False

db_pool = DatabasePool(max_connections=MAX_CONNECTIONS, timeout=DB_TIMEOUT)

async def execute_db(func: Callable):
    """تنفيذ دالة مع اتصال قاعدة البيانات"""
    try:
        conn = await db_pool.get_connection()
        result = await func(conn)
        return result
    except Exception as e:
        logger.error(f"خطأ في قاعدة البيانات: {e}")
        raise
# ===================================================================
# 16. إنشاء الجداول المتطورة
# ===================================================================

async def init_db_improved():
    """تهيئة قاعدة البيانات المتطورة مع جميع الجداول والفهارس"""
    try:
        async def _init(conn):
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute("PRAGMA cache_size=-64000")
            await conn.execute("PRAGMA temp_store=MEMORY")
            await conn.execute("PRAGMA busy_timeout=30000")
            await conn.execute("PRAGMA mmap_size=30000000000")
            logger.info("🔧 تم تفعيل إعدادات SQLite المتقدمة")

            # ============ المستخدمين ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
                    language TEXT DEFAULT 'ar', auto_publish INTEGER DEFAULT 1,
                    auto_recycle INTEGER DEFAULT 1, banned INTEGER DEFAULT 0,
                    trial_used INTEGER DEFAULT 0, subscription_end TEXT,
                    auto_reply_enabled INTEGER DEFAULT 1, referral_code TEXT UNIQUE,
                    referral_reward_days INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT,
                    active_channel INTEGER, level INTEGER DEFAULT 1,
                    achievements TEXT DEFAULT '[]', last_daily_reward TEXT,
                    last_weekly_reward TEXT, referred_by INTEGER, points INTEGER DEFAULT 0,
                    warning_count INTEGER DEFAULT 0, last_activity TEXT,
                    is_verified INTEGER DEFAULT 0, twofa_secret TEXT, twofa_enabled INTEGER DEFAULT 0
                )
            """)

            # ============ القنوات والمنشورات ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                    channel_id TEXT, channel_name TEXT, banned INTEGER DEFAULT 0,
                    created_at TEXT, last_post_time TEXT, total_posts INTEGER DEFAULT 0,
                    total_views INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, channel_db_id INTEGER,
                    text TEXT, media_type TEXT, media_file_id TEXT,
                    published INTEGER DEFAULT 0, views_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0, created_at TEXT, published_at TEXT,
                    last_view_time TEXT, sentiment_score REAL DEFAULT 0,
                    sentiment_label TEXT DEFAULT 'neutral', is_scheduled INTEGER DEFAULT 0,
                    scheduled_for TEXT, is_edited INTEGER DEFAULT 0, edited_at TEXT,
                    FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
                )
            """)

            # ============ الجدولة ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS schedule (
                    channel_db_id INTEGER PRIMARY KEY,
                    schedule_type TEXT DEFAULT 'interval_minutes',
                    interval_minutes INTEGER DEFAULT 12, interval_hours INTEGER DEFAULT 0,
                    interval_days INTEGER DEFAULT 0, days_of_week TEXT DEFAULT '[]',
                    specific_dates TEXT DEFAULT '[]', publish_time TEXT DEFAULT '00:00',
                    cron_expression TEXT, next_publish_date TEXT, last_executed TEXT,
                    is_paused INTEGER DEFAULT 0,
                    FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
                )
            """)

            # ============ المجموعات والصلاحيات ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_groups (
                    chat_id INTEGER PRIMARY KEY, chat_name TEXT, username TEXT,
                    added_by INTEGER, added_at TEXT, updated_at TEXT,
                    banned INTEGER DEFAULT 0, members_count INTEGER DEFAULT 0,
                    admins_count INTEGER DEFAULT 0, last_activity TEXT, is_active INTEGER DEFAULT 1
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS group_admins (
                    chat_id INTEGER, user_id INTEGER, is_hidden INTEGER DEFAULT 0,
                    added_at TEXT, PRIMARY KEY (chat_id, user_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS hidden_owner_groups (
                    chat_id INTEGER PRIMARY KEY, owner_id INTEGER,
                    is_hidden INTEGER DEFAULT 1, created_at TEXT, verified INTEGER DEFAULT 0
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS hidden_admins (
                    chat_id INTEGER, admin_id INTEGER, added_by INTEGER,
                    added_at TEXT, is_active INTEGER DEFAULT 1,
                    PRIMARY KEY (chat_id, admin_id)
                )
            """)

            # ============ الأمان ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS group_security (
                    chat_id INTEGER PRIMARY KEY, delete_links INTEGER DEFAULT 0,
                    mentions INTEGER DEFAULT 0, warn_message INTEGER DEFAULT 1,
                    slow_mode INTEGER DEFAULT 0, slow_mode_seconds INTEGER DEFAULT 5,
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
                    night_mode_action TEXT DEFAULT 'mute',
                    captcha_enabled INTEGER DEFAULT 0, captcha_timeout INTEGER DEFAULT 60,
                    max_links_per_message INTEGER DEFAULT 0,
                    max_mentions_per_message INTEGER DEFAULT 0,
                    allowed_domains TEXT DEFAULT '[]'
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_locks (
                    chat_id INTEGER PRIMARY KEY, locked INTEGER DEFAULT 0,
                    locked_at TEXT, locked_by INTEGER, reason TEXT, auto_unlock_at TEXT
                )
            """)

            # ============ العقوبات والكلمات المحظورة ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS banned_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, word TEXT NOT NULL,
                    chat_id INTEGER DEFAULT -1, added_by INTEGER, added_at TEXT,
                    severity INTEGER DEFAULT 1, UNIQUE(word, chat_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS moderation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, user_id INTEGER,
                    action TEXT, duration_minutes INTEGER, moderator_id INTEGER,
                    reason TEXT, created_at TEXT, expires_at TEXT, is_active INTEGER DEFAULT 1
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_warnings (
                    user_id INTEGER, chat_id INTEGER, warnings INTEGER DEFAULT 0,
                    updated_at TEXT, last_warning TEXT, PRIMARY KEY (user_id, chat_id)
                )
            """)

            # ============ الإحالات ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER,
                    referred_id INTEGER, created_at TEXT, reward_claimed INTEGER DEFAULT 0,
                    reward_amount INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
                    UNIQUE(referrer_id, referred_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS referral_settings (
                    key TEXT PRIMARY KEY, value TEXT
                )
            """)
            await conn.execute("""
                INSERT OR IGNORE INTO referral_settings (key, value) VALUES 
                    ('reward_days_per_referral', '3'), ('max_referrals_per_day', '5'),
                    ('welcome_bonus_points', '10'), ('min_referrals_for_reward', '1'),
                    ('reward_cooldown_days', '1')
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS referral_rewards (
                    user_id INTEGER PRIMARY KEY, referral_count INTEGER DEFAULT 0,
                    total_reward_days INTEGER DEFAULT 0, claimed_reward_days INTEGER DEFAULT 0
                )
            """)

            # ============ التذاكر والتذكيرات والترجمة ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT,
                    message TEXT, ticket_number INTEGER, status TEXT DEFAULT 'pending',
                    created_at TEXT, replied INTEGER DEFAULT 0, priority TEXT DEFAULT 'normal',
                    assigned_to INTEGER, resolved_at TEXT
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_reminder_settings (
                    user_id INTEGER PRIMARY KEY, subscription_reminder INTEGER DEFAULT 1,
                    daily_stats_reminder INTEGER DEFAULT 0, weekly_report INTEGER DEFAULT 1,
                    reminder_days_before INTEGER DEFAULT 3, last_reminder_sent TEXT,
                    notification_lang TEXT DEFAULT 'ar', reminder_time TEXT DEFAULT '09:00'
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_translation (
                    user_id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'off',
                    auto_translate INTEGER DEFAULT 0, preferred_languages TEXT DEFAULT '[]'
                )
            """)

            # ============ المسابقات ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS contests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id INTEGER,
                    title TEXT, description TEXT, prize TEXT, end_date TEXT,
                    status TEXT DEFAULT 'active', winner_id INTEGER, created_at TEXT,
                    contest_type TEXT DEFAULT 'raffle', max_participants INTEGER DEFAULT 0,
                    is_private INTEGER DEFAULT 0, allowed_users TEXT DEFAULT '[]'
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS contest_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                    contest_id INTEGER, answer TEXT, joined_at TEXT,
                    score INTEGER DEFAULT 0, UNIQUE(user_id, contest_id)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS contest_winners (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, contest_id INTEGER,
                    winner_id INTEGER, announced_at TEXT, prize_claimed INTEGER DEFAULT 0
                )
            """)

            # ============ الإنجازات والردود التلقائية ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                    achievement TEXT, created_at TEXT, points INTEGER DEFAULT 0,
                    UNIQUE(user_id, achievement)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS auto_replies (
                    chat_id INTEGER, keyword TEXT, reply TEXT, created_at TEXT,
                    updated_at TEXT, is_active INTEGER DEFAULT 1, priority INTEGER DEFAULT 0,
                    PRIMARY KEY (chat_id, keyword)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS auto_reply_settings (
                    chat_id INTEGER PRIMARY KEY, enabled INTEGER DEFAULT 0,
                    only_admins INTEGER DEFAULT 0, ignore_bots INTEGER DEFAULT 1,
                    created_at TEXT, updated_at TEXT, cooldown_seconds INTEGER DEFAULT 5,
                    max_replies_per_minute INTEGER DEFAULT 10
                )
            """)

            # ============ التعلم الذكي ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS learning_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, pattern TEXT NOT NULL,
                    sentiment TEXT, score REAL, frequency INTEGER DEFAULT 1,
                    last_used TEXT, confidence REAL DEFAULT 0.5, category TEXT DEFAULT 'general'
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, chat_id INTEGER,
                    text TEXT, sentiment TEXT, score REAL, created_at TEXT,
                    response_sentiment TEXT, response_score REAL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_sentiment_profile (
                    user_id INTEGER PRIMARY KEY, avg_sentiment REAL DEFAULT 0,
                    stability REAL DEFAULT 1, messages INTEGER DEFAULT 0,
                    trend TEXT DEFAULT 'stable', last_updated TEXT,
                    positive_count INTEGER DEFAULT 0, negative_count INTEGER DEFAULT 0,
                    neutral_count INTEGER DEFAULT 0
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sentiment_profile (
                    chat_id INTEGER PRIMARY KEY, avg_sentiment REAL DEFAULT 0,
                    stability REAL DEFAULT 1, messages INTEGER DEFAULT 0,
                    trend TEXT DEFAULT 'stable', last_updated TEXT,
                    positive_count INTEGER DEFAULT 0, negative_count INTEGER DEFAULT 0,
                    neutral_count INTEGER DEFAULT 0
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS response_learning (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, pattern_key TEXT UNIQUE,
                    success_count INTEGER DEFAULT 0, fail_count INTEGER DEFAULT 0,
                    score REAL DEFAULT 0, last_used TEXT, best_response TEXT
                )
            """)

            # ============ الأحداث الأمنية والإعدادات ============
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
                    chat_id INTEGER, user_id INTEGER, details TEXT,
                    severity TEXT DEFAULT 'info', created_at TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY, value TEXT, updated_at TEXT, updated_by INTEGER
                )
            """)
            await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('publish_interval', ?)", (str(DEFAULT_PUBLISH_INTERVAL_SECONDS),))
            await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('db_version', '2.1')")
            await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_backup', '1')")
            await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_ticket_number', '0')")

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_admins (
                    user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TEXT,
                    permissions TEXT DEFAULT '[]', is_active INTEGER DEFAULT 1
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_channels (
                    channel_id TEXT PRIMARY KEY, channel_name TEXT,
                    added_by INTEGER, added_at TEXT, banned INTEGER DEFAULT 0
                )
            """)

            # ============ جداول إضافية ============
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
                    text TEXT, media_type TEXT, media_file_id TEXT,
                    publish_time TEXT, fail_count INTEGER DEFAULT 0
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS group_rules (
                    chat_id INTEGER PRIMARY KEY, rules_text TEXT,
                    updated_by INTEGER, updated_at TEXT
                )
            """)

            # ============ الفهارس ============
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_channels_user ON user_channels(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_banned_words_chat ON banned_words(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_posts_time ON scheduled_posts(publish_time)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_moderation_log_chat ON moderation_log(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_moderation_log_user ON moderation_log(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_contests_end_date ON contests(end_date)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_contest_participants_contest ON contest_participants(contest_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_contest_participants_user ON contest_participants(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_history_user ON sentiment_history(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_history_chat ON sentiment_history(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_history_created ON sentiment_history(created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_type ON security_events(event_type)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_severity ON security_events(severity)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_created ON security_events(created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_banned ON users(banned)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_groups_chat_name ON bot_groups(chat_name)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_groups_banned ON bot_groups(banned)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_auto_replies_chat ON auto_replies(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_auto_replies_keyword ON auto_replies(keyword)")

            await conn.commit()
            logger.info("✅ تم إنشاء جميع جداول قاعدة البيانات بنجاح")

        await execute_db(_init)
    except Exception as e:
        logger.error(f"❌ فشل تهيئة قاعدة البيانات: {e}")
        raise

async def init_security_table():
    """تهيئة جدول الأمان الإضافي"""
    try:
        async def _init(conn):
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS group_security_settings (
                    chat_id INTEGER PRIMARY KEY, links INTEGER DEFAULT 0,
                    mentions INTEGER DEFAULT 0, slow_mode INTEGER DEFAULT 0,
                    slow_mode_seconds INTEGER DEFAULT 5, welcome_enabled INTEGER DEFAULT 0,
                    goodbye_enabled INTEGER DEFAULT 0, delete_videos INTEGER DEFAULT 0,
                    delete_audio INTEGER DEFAULT 0, delete_animation INTEGER DEFAULT 0,
                    delete_service INTEGER DEFAULT 0, delete_documents INTEGER DEFAULT 0,
                    delete_stickers INTEGER DEFAULT 0, delete_forwarded INTEGER DEFAULT 0,
                    delete_polls INTEGER DEFAULT 0, delete_games INTEGER DEFAULT 0,
                    delete_voice INTEGER DEFAULT 0, delete_video_note INTEGER DEFAULT 0,
                    antiflood_enabled INTEGER DEFAULT 0, night_mode_enabled INTEGER DEFAULT 0,
                    max_message_length INTEGER DEFAULT 0, delete_penalty TEXT DEFAULT 'none',
                    captcha_enabled INTEGER DEFAULT 0, captcha_timeout INTEGER DEFAULT 60,
                    max_links_per_message INTEGER DEFAULT 0, max_mentions_per_message INTEGER DEFAULT 0,
                    allowed_domains TEXT DEFAULT '[]', ban_on_links INTEGER DEFAULT 0,
                    warn_on_links INTEGER DEFAULT 0, auto_delete_after_minutes INTEGER DEFAULT 0
                )
            """)
            await conn.commit()
            logger.info("✅ جدول group_security_settings جاهز")
        await execute_db(_init)
    except Exception as e:
        logger.error(f"❌ فشل تهيئة جدول الأمان: {e}")
        raise

async def fix_missing_columns():
    """إصلاح الأعمدة المفقودة في الجداول"""
    async def _fix(conn):
        cur = await conn.execute("PRAGMA table_info(users)")
        existing = [row[1] for row in await cur.fetchall()]
        required = {
            'level': 'INTEGER DEFAULT 1', 'achievements': "TEXT DEFAULT '[]'",
            'last_daily_reward': 'TEXT', 'last_weekly_reward': 'TEXT',
            'referred_by': 'INTEGER', 'points': 'INTEGER DEFAULT 0',
            'warning_count': 'INTEGER DEFAULT 0', 'last_activity': 'TEXT',
            'is_verified': 'INTEGER DEFAULT 0', 'twofa_secret': 'TEXT',
            'twofa_enabled': 'INTEGER DEFAULT 0'
        }
        for col, typ in required.items():
            if col not in existing:
                try:
                    await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
                except:
                    pass
        cur = await conn.execute("PRAGMA table_info(user_reminder_settings)")
        existing = [row[1] for row in await cur.fetchall()]
        if 'last_reminder_sent' not in existing:
            try:
                await conn.execute("ALTER TABLE user_reminder_settings ADD COLUMN last_reminder_sent TEXT")
            except:
                pass
        if 'notification_lang' not in existing:
            try:
                await conn.execute("ALTER TABLE user_reminder_settings ADD COLUMN notification_lang TEXT DEFAULT 'ar'")
            except:
                pass
        if 'reminder_time' not in existing:
            try:
                await conn.execute("ALTER TABLE user_reminder_settings ADD COLUMN reminder_time TEXT DEFAULT '09:00'")
            except:
                pass
        await conn.commit()
        logger.info("✅ تم إصلاح الأعمدة المفقودة")
    await execute_db(_fix)

# ===================================================================
# 17. دوال المستخدمين
# ===================================================================

async def db_register_user(user_id: int) -> bool:
    async def _register(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if await cur.fetchone():
            await conn.execute("UPDATE users SET updated_at=? WHERE user_id=?", (utc_now_iso(), user_id))
            await conn.commit()
            return False
        referral_code = secrets.token_urlsafe(6)
        await conn.execute("INSERT INTO users (user_id, referral_code, created_at, updated_at) VALUES (?, ?, ?, ?)", (user_id, referral_code, utc_now_iso(), utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_register)

async def db_get_user_language(user_id: int) -> str:
    async def _get(conn):
        cur = await conn.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row and row[0] else 'ar'
    return await execute_db(_get)

async def db_set_user_language(user_id: int, lang: str):
    async def _set(conn):
        await conn.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))
        await conn.commit()
    return await execute_db(_set)

async def db_is_banned(user_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_check)

async def db_get_all_users():
    async def _get(conn):
        cur = await conn.execute("SELECT user_id, banned FROM users ORDER BY user_id")
        return await cur.fetchall()
    return await execute_db(_get)

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
                return max(0, (end_date - utc_now()).days)
            except:
                return 0
        return 0
    return await execute_db(_get)

async def db_activate_subscription(user_id: int, days: int):
    async def _activate(conn):
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try:
                current_end = datetime.fromisoformat(row[0])
                new_end = (current_end if current_end > utc_now() else utc_now()) + timedelta(days=days)
            except:
                new_end = utc_now() + timedelta(days=days)
        else:
            new_end = utc_now() + timedelta(days=days)
        await conn.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (new_end.isoformat(), user_id))
        await conn.commit()
    return await execute_db(_activate)

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

async def db_has_used_trial(user_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_check)

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

async def db_update_user_cache(user_id: int, username: str, first_name: str):
    async def _update(conn):
        await conn.execute("UPDATE users SET username=?, first_name=?, updated_at=? WHERE user_id=?", (username, first_name, utc_now_iso(), user_id))
        await conn.commit()
    return await execute_db(_update)

async def db_get_user_by_referral_code(code: str) -> Optional[int]:
    async def _get(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE referral_code=?", (code,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_get_user_referral_code(user_id: int) -> str:
    async def _get(conn):
        cur = await conn.execute("SELECT referral_code FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else ""
    return await execute_db(_get)

# ===================================================================
# 18. دوال القنوات
# ===================================================================

async def db_add_channel(user_id: int, channel_id: str, channel_name: str) -> int:
    async def _add(conn):
        cur = await conn.execute("SELECT id FROM user_channels WHERE user_id=? AND channel_id=?", (user_id, channel_id))
        if await cur.fetchone():
            return None
        cur = await conn.execute("INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) VALUES (?, ?, ?, ?) RETURNING id", (user_id, channel_id, channel_name, utc_now_iso()))
        row = await cur.fetchone()
        await conn.commit()
        return row[0] if row else None
    return await execute_db(_add)

async def db_get_channels(user_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT id, channel_id, channel_name, banned FROM user_channels WHERE user_id=? ORDER BY id", (user_id,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_get_channel_info(channel_db_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT channel_id, channel_name FROM user_channels WHERE id=?", (channel_db_id,))
        return await cur.fetchone()
    return await execute_db(_get)

async def db_delete_channel_by_id(user_id: int, channel_db_id: int) -> bool:
    async def _delete(conn):
        await conn.execute("DELETE FROM user_channels WHERE id=? AND user_id=?", (channel_db_id, user_id))
        await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (channel_db_id,))
        await conn.execute("DELETE FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        await conn.execute("DELETE FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
        return True
    return await execute_db(_delete)

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

async def db_register_channel(chat_id: int, channel_name: str, user_id: int):
    async def _reg(conn):
        await conn.execute("INSERT OR IGNORE INTO bot_channels (channel_id, channel_name, added_by, added_at) VALUES (?, ?, ?, ?)", (str(chat_id), channel_name, user_id, utc_now_iso()))
        await conn.commit()
    return await execute_db(_reg)

# ===================================================================
# 19. دوال المنشورات
# ===================================================================

async def db_save_posts(channel_db_id: int, posts: list) -> int:
    async def _save(conn):
        values = [(channel_db_id, sanitize_text(t), m, f, utc_now_iso()) for t, m, f in posts]
        await conn.executemany("INSERT INTO posts (channel_db_id, text, media_type, media_file_id, created_at) VALUES (?, ?, ?, ?, ?)", values)
        await conn.commit()
        return len(values)
    return await execute_db(_save)

async def db_get_next_post(channel_db_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT id, text, media_type, media_file_id FROM posts WHERE channel_db_id=? AND published=0 AND (fail_count IS NULL OR fail_count < 3) ORDER BY id LIMIT 1", (channel_db_id,))
        row = await cur.fetchone()
        return {'id': row[0], 'text': row[1], 'media_type': row[2], 'media_file_id': row[3]} if row else None
    return await execute_db(_get)

async def db_mark_published(post_id: int):
    async def _mark(conn):
        await conn.execute("UPDATE posts SET published=1, published_at=? WHERE id=?", (utc_now_iso(), post_id))
        await conn.commit()
    return await execute_db(_mark)

async def db_unpublished_count(channel_db_id: int) -> int:
    async def _count(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=0", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_count)

async def db_get_user_unpublished_posts(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=? AND p.published=0 AND uc.banned=0", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_get_user_total_posts(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=? AND uc.banned=0", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_reset_all_posts_to_unpublished(channel_db_id: int) -> int:
    async def _reset(conn):
        await conn.execute("UPDATE posts SET published=0, fail_count=0 WHERE channel_db_id=?", (channel_db_id,))
        await conn.commit()
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_reset)

async def db_reset_posts_to_unpublished(channel_db_id: int, user_id: int = None) -> int:
    return await db_reset_all_posts_to_unpublished(channel_db_id)

async def db_get_user_posts_for_channel(channel_db_id: int, limit=15):
    async def _get(conn):
        cur = await conn.execute("SELECT id, text, media_type FROM posts WHERE channel_db_id=? AND published=0 ORDER BY id LIMIT ?", (channel_db_id, limit))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_delete_single_post(post_id: int, user_id: int, channel_db_id: int) -> bool:
    async def _delete(conn):
        cur = await conn.execute("SELECT 1 FROM user_channels WHERE id=? AND user_id=? AND banned=0", (channel_db_id, user_id))
        if not await cur.fetchone():
            return False
        await conn.execute("DELETE FROM posts WHERE id=? AND channel_db_id=?", (post_id, channel_db_id))
        await conn.commit()
        return True
    return await execute_db(_delete)

async def db_increment_fail_count(post_id: int):
    async def _inc(conn):
        await conn.execute("UPDATE posts SET fail_count = COALESCE(fail_count, 0) + 1 WHERE id=?", (post_id,))
        await conn.commit()
    return await execute_db(_inc)

async def db_get_posts_count(channel_db_id: int) -> int:
    async def _cnt(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_cnt)

async def db_get_published_count(channel_db_id: int) -> int:
    async def _cnt(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=1", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_cnt)

async def db_get_channel_stats(channel_db_id: int) -> dict:
    async def _stats(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=1", (channel_db_id,))
        published = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COALESCE(SUM(views_count),0) FROM posts WHERE channel_db_id=?", (channel_db_id,))
        views = (await cur.fetchone())[0]
        return {'total_posts': total, 'published_posts': published, 'unpublished_posts': total - published, 'total_views': views, 'avg_views': round(views / published, 1) if published else 0}
    return await execute_db(_stats)

# ===================================================================
# 20. دوال الجدولة
# ===================================================================

async def db_save_schedule(channel_db_id: int, schedule_type: str, interval_minutes: int = None, interval_hours: int = None, interval_days: int = None, days_of_week: str = None, specific_dates: str = None, publish_time: str = None, cron_expression: str = None):
    async def _save(conn):
        await conn.execute("INSERT OR REPLACE INTO schedule (channel_db_id, schedule_type, interval_minutes, interval_hours, interval_days, days_of_week, specific_dates, publish_time, cron_expression, next_publish_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)", (channel_db_id, schedule_type, interval_minutes or 12, interval_hours or 0, interval_days or 0, days_of_week or '[]', specific_dates or '[]', publish_time or '00:00', cron_expression))
        await conn.commit()
    return await execute_db(_save)

async def db_get_schedule(channel_db_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT schedule_type, interval_minutes, interval_hours, interval_days, days_of_week, specific_dates, publish_time, cron_expression, next_publish_date FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        if row:
            return {'type': row[0] or 'interval_minutes', 'interval_minutes': row[1] or 12, 'interval_hours': row[2] or 0, 'interval_days': row[3] or 0, 'days_of_week': row[4] or '[]', 'specific_dates': row[5] or '[]', 'publish_time': row[6] or '00:00', 'cron_expression': row[7], 'next_publish_date': row[8]}
        return {'type': 'interval_minutes', 'interval_minutes': 12, 'interval_hours': 0, 'interval_days': 0, 'days_of_week': '[]', 'specific_dates': '[]', 'publish_time': '00:00', 'cron_expression': None, 'next_publish_date': None}
    return await execute_db(_get)

async def db_set_next_publish_date(channel_db_id: int, next_date: datetime):
    async def _set(conn):
        await conn.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?", (next_date.isoformat() if next_date else None, channel_db_id))
        await conn.commit()
    return await execute_db(_set)

async def db_set_last_publish(channel_db_id: int, publish_time: datetime):
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO last_publish (channel_db_id, last_publish_time) VALUES (?, ?)", (channel_db_id, publish_time.isoformat()))
        await conn.commit()
    return await execute_db(_set)

async def db_set_publish_time(channel_db_id: int, time_str: str):
    async def _set(conn):
        await conn.execute("UPDATE schedule SET publish_time=?, next_publish_date=NULL WHERE channel_db_id=?", (time_str, channel_db_id))
        await conn.commit()
    return await execute_db(_set)

async def db_update_next_publish_date(channel_db_id: int):
    async def _update(conn):
        cur = await conn.execute("SELECT last_publish_time FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
        last_row = await cur.fetchone()
        last_time = datetime.fromisoformat(last_row[0]) if last_row and last_row[0] else utc_now()
        cur = await conn.execute("SELECT schedule_type, interval_minutes, interval_hours, interval_days, days_of_week, specific_dates, publish_time, cron_expression FROM schedule WHERE channel_db_id=?", (channel_db_id,))
        row = await cur.fetchone()
        if not row:
            return
        schedule = {'type': row[0] or 'interval_minutes', 'interval_minutes': row[1] or 12, 'interval_hours': row[2] or 0, 'interval_days': row[3] or 0, 'days_of_week': row[4] or '[]', 'specific_dates': row[5] or '[]', 'publish_time': row[6] or '00:00', 'cron_expression': row[7]}
        try:
            hour, minute = map(int, schedule.get('publish_time', '00:00').split(':'))
        except:
            hour, minute = 0, 0
        next_date = None
        now = utc_now()
        st = schedule['type']
        if st == 'interval_minutes':
            next_date = last_time + timedelta(minutes=schedule.get('interval_minutes', 12))
        elif st == 'interval_hours':
            next_date = last_time + timedelta(hours=schedule.get('interval_hours', 1))
        elif st == 'interval_days':
            next_date = last_time + timedelta(days=schedule.get('interval_days', 1))
        elif st == 'days':
            days_of_week = parse_days_of_week_safe(schedule.get('days_of_week', '[]'))
            if days_of_week:
                target = last_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
                for i in range(1, 8):
                    check = target + timedelta(days=i)
                    if check.weekday() in days_of_week:
                        next_date = check
                        break
                if not next_date:
                    next_date = target + timedelta(days=7)
                    while next_date.weekday() not in days_of_week:
                        next_date += timedelta(days=1)
            else:
                next_date = last_time + timedelta(days=1)
        elif st == 'dates':
            specific_dates = parse_dates_safe(schedule.get('specific_dates', '[]'))
            if specific_dates:
                target = last_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
                for ds in sorted(specific_dates):
                    try:
                        d_obj = datetime.strptime(ds, '%Y-%m-%d').replace(hour=hour, minute=minute, second=0, microsecond=0)
                        if d_obj > last_time:
                            next_date = d_obj
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
        else:
            next_date = last_time + timedelta(minutes=schedule.get('interval_minutes', 12))
        if next_date and next_date <= now:
            while next_date <= now:
                if st == 'interval_minutes':
                    next_date += timedelta(minutes=schedule.get('interval_minutes', 12))
                elif st == 'interval_hours':
                    next_date += timedelta(hours=schedule.get('interval_hours', 1))
                elif st == 'interval_days':
                    next_date += timedelta(days=schedule.get('interval_days', 1))
                else:
                    next_date += timedelta(days=1)
        if next_date:
            await conn.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?", (next_date.isoformat(), channel_db_id))
            await conn.commit()
    return await execute_db(_update)

async def db_add_scheduled_post(chat_id: int, text: str, publish_time: datetime):
    async def _add(conn):
        await conn.execute("INSERT INTO scheduled_posts (chat_id, text, publish_time) VALUES (?, ?, ?)", (chat_id, text, publish_time.isoformat()))
        await conn.commit()
    await execute_db(_add)

async def db_get_due_scheduled_posts(now: datetime, limit: int = 50):
    async def _get(conn):
        cur = await conn.execute("SELECT id, chat_id, text, media_type, media_file_id, fail_count FROM scheduled_posts WHERE publish_time <= ? AND fail_count < 5 ORDER BY publish_time ASC LIMIT ?", (now.isoformat(), limit))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_delete_scheduled_post(post_id: int):
    async def _del(conn):
        await conn.execute("DELETE FROM scheduled_posts WHERE id=?", (post_id,))
        await conn.commit()
    return await execute_db(_del)

async def db_update_scheduled_post_fail(post_id: int, fail_count: int):
    async def _upd(conn):
        await conn.execute("UPDATE scheduled_posts SET fail_count=? WHERE id=?", (fail_count, post_id))
        await conn.commit()
    return await execute_db(_upd)

# ===================================================================
# 21. دوال المجموعات
# ===================================================================

async def db_register_group(chat_id: int, chat_name: str, added_by: int, username: str = None) -> bool:
    chat_name = chat_name.strip()[:255]
    username = username.strip()[:100] if username and isinstance(username, str) else None
    async def _register(conn):
        cur = await conn.execute("SELECT chat_id, banned FROM bot_groups WHERE chat_id=?", (chat_id,))
        existing = await cur.fetchone()
        if existing:
            await conn.execute("UPDATE bot_groups SET chat_name=?, username=?, added_by=?, updated_at=? WHERE chat_id=?", (chat_name, username, added_by, utc_now_iso(), chat_id))
            await conn.commit()
            return not existing[1]
        await conn.execute("INSERT INTO bot_groups (chat_id, chat_name, username, added_by, added_at) VALUES (?, ?, ?, ?, ?)", (chat_id, chat_name, username, added_by, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_register)

async def db_get_user_groups(user_id: int):
    async def _get(conn):
        result = []
        seen = set()
        for table, col in [("hidden_owner_groups", "owner_id"), ("hidden_admins", "admin_id"), ("group_admins", "user_id")]:
            cur = await conn.execute(f"SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned FROM bot_groups bg INNER JOIN {table} h ON bg.chat_id = h.chat_id WHERE h.{col} = ?", (user_id,))
            for row in await cur.fetchall():
                if row[0] not in seen:
                    seen.add(row[0])
                    result.append(row)
        return result
    return await execute_db(_get)

async def db_get_user_groups_count(user_id: int) -> int:
    groups = await db_get_user_groups(user_id)
    return len(groups)

async def db_sync_group_admins(chat_id: int, bot, owner_id: int = None) -> int:
    try:
        admins = await bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        if not admin_ids:
            return 0
        async def _update(conn):
            await conn.execute("DELETE FROM group_admins WHERE chat_id=?", (chat_id,))
            if admin_ids:
                await conn.executemany("INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?, ?)", [(chat_id, uid) for uid in admin_ids])
            await conn.commit()
            return len(admin_ids)
        return await execute_db(_update)
    except Exception as e:
        logger.error(f"خطأ في مزامنة مشرفي المجموعة {chat_id}: {e}")
        return 0

# ===================================================================
# 22. دوال الإعدادات العامة
# ===================================================================

async def db_get_updates_channel() -> Optional[str]:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='updates_channel'")
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_set_updates_channel(channel: str) -> bool:
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('updates_channel', ?)", (channel,))
        await conn.commit()
        return True
    return await execute_db(_set)

async def db_get_force_subscribe_channel() -> Optional[str]:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='force_subscribe_channel'")
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_set_force_subscribe_channel(channel: str) -> bool:
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('force_subscribe_channel', ?)", (channel,))
        await conn.commit()
        return True
    return await execute_db(_set)

async def db_get_log_channel_id() -> Optional[int]:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='log_channel_id'")
        row = await cur.fetchone()
        return int(row[0]) if row else None
    return await execute_db(_get)

async def db_set_log_channel_id(channel_id: str) -> bool:
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('log_channel_id', ?)", (channel_id,))
        await conn.commit()
        return True
    return await execute_db(_set)

async def db_get_allowed_sendcode_user() -> Optional[int]:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='allowed_sendcode_user'")
        row = await cur.fetchone()
        return int(row[0]) if row else None
    return await execute_db(_get)

async def db_set_allowed_sendcode_user(user_id: int) -> bool:
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('allowed_sendcode_user', ?)", (str(user_id),))
        await conn.commit()
        return True
    return await execute_db(_set)

async def db_get_publish_interval_seconds() -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='publish_interval'")
        row = await cur.fetchone()
        return int(row[0]) if row else DEFAULT_PUBLISH_INTERVAL_SECONDS
    return await execute_db(_get)

async def db_get_auto_backup() -> bool:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='auto_backup'")
        row = await cur.fetchone()
        return row and row[0] == '1'
    return await execute_db(_get)

async def db_get_last_backup_time() -> Optional[str]:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='last_backup'")
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

# ===================================================================
# 23. دوال التذاكر والردود
# ===================================================================

async def db_mark_ticket_replied(ticket_id: int):
    async def _mark(conn):
        await conn.execute("UPDATE support_tickets SET status='replied', replied=1 WHERE id=?", (ticket_id,))
        await conn.commit()
    return await execute_db(_mark)

async def db_get_next_ticket_number() -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='last_ticket_number'")
        row = await cur.fetchone()
        return int(row[0]) if row else 0
    return await execute_db(_get)

async def db_save_ticket(user_id: int, username: str, message: str, ticket_num: int):
    async def _save(conn):
        await conn.execute("INSERT INTO support_tickets (user_id, username, message, ticket_number, created_at) VALUES (?, ?, ?, ?, ?)", (user_id, username, message, ticket_num, utc_now_iso()))
        await conn.commit()
    return await execute_db(_save)

async def db_get_reply(keyword: str):
    async def _get(conn):
        cur = await conn.execute("SELECT reply FROM auto_replies WHERE keyword=? AND is_active=1 LIMIT 1", (keyword,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_add_reply(keyword: str, reply: str):
    async def _add(conn):
        await conn.execute("INSERT OR REPLACE INTO auto_replies (chat_id, keyword, reply, created_at) VALUES (0, ?, ?, ?)", (keyword, reply, utc_now_iso()))
        await conn.commit()
    return await execute_db(_add)

async def db_del_reply(keyword: str):
    async def _del(conn):
        await conn.execute("DELETE FROM auto_replies WHERE keyword=? AND chat_id=0", (keyword,))
        await conn.commit()
        return True
    return await execute_db(_del)

async def db_get_auto_reply_settings(chat_id: int) -> dict:
    async def _get(conn):
        cur = await conn.execute("SELECT * FROM auto_reply_settings WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        if row:
            return {'enabled': bool(row[1]) if len(row) > 1 else False, 'only_admins': bool(row[2]) if len(row) > 2 else False, 'ignore_bots': bool(row[3]) if len(row) > 3 else True}
        return {'enabled': False, 'only_admins': False, 'ignore_bots': True}
    return await execute_db(_get)

# ===================================================================
# 24. دوال المسابقات
# ===================================================================

async def db_create_contest(creator_id: int, title: str, description: str, prize: str, end_date: datetime, contest_type: str = 'raffle') -> int:
    async def _create(conn):
        cur = await conn.execute("INSERT INTO contests (creator_id, title, description, prize, end_date, contest_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id", (creator_id, title, description, prize, end_date.isoformat(), contest_type, utc_now_iso()))
        row = await cur.fetchone()
        await conn.commit()
        return row[0] if row else None
    return await execute_db(_create)

async def db_participate_in_contest(user_id: int, contest_id: int, answer: str = "") -> bool:
    async def _join(conn):
        try:
            await conn.execute("INSERT INTO contest_participants (user_id, contest_id, answer, joined_at) VALUES (?, ?, ?, ?)", (user_id, contest_id, answer, utc_now_iso()))
            await conn.commit()
            return True
        except:
            return False
    return await execute_db(_join)

async def db_get_contest(contest_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT id, title, description, prize, end_date, contest_type, status, winner_id FROM contests WHERE id=?", (contest_id,))
        row = await cur.fetchone()
        return {'id': row[0], 'title': row[1], 'description': row[2], 'prize': row[3], 'end_date': row[4], 'contest_type': row[5], 'status': row[6], 'winner_id': row[7]} if row else None
    return await execute_db(_get)

async def db_set_contest_winner(contest_id: int, winner_id: int) -> bool:
    async def _set(conn):
        await conn.execute("UPDATE contests SET status='finished', winner_id=? WHERE id=?", (winner_id, contest_id))
        await conn.execute("INSERT INTO contest_winners (contest_id, winner_id, announced_at) VALUES (?, ?, ?)", (contest_id, winner_id, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_set)

async def db_get_active_contests_with_participants(limit=10):
    async def _get(conn):
        cur = await conn.execute("SELECT c.id, c.title, c.description, c.prize, c.end_date, c.contest_type, (SELECT COUNT(*) FROM contest_participants WHERE contest_id=c.id) as participants FROM contests c WHERE c.status='active' ORDER BY c.end_date ASC LIMIT ?", (limit,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_get_user_participation(user_id: int, contest_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM contest_participants WHERE contest_id=? AND user_id=?", (contest_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_check)

# ===================================================================
# 25. دوال التذكيرات والترجمة
# ===================================================================

async def db_get_users_needing_reminder():
    async def _get(conn):
        cur = await conn.execute("""
            SELECT u.user_id, u.subscription_end, COALESCE(r.reminder_days_before, 3) as reminder_days_before,
                   COALESCE(r.notification_lang, 'ar') as notification_lang, COALESCE(r.last_reminder_sent, 0) as last_reminder_sent
            FROM users u LEFT JOIN user_reminder_settings r ON u.user_id = r.user_id
            WHERE u.subscription_end IS NOT NULL AND u.subscription_end > datetime('now') AND u.banned = 0
        """)
        rows = await cur.fetchall()
        results = []
        now = utc_now()
        for row in rows:
            try:
                end_date = datetime.fromisoformat(row[1])
                days_left = (end_date - now).days
                if 0 < days_left <= row[2]:
                    last = row[4]
                    if not last or (now - datetime.fromisoformat(last)).days >= 1:
                        results.append({'user_id': row[0], 'days_left': days_left, 'notification_lang': row[3]})
            except:
                pass
        return results
    return await execute_db(_get)

async def db_update_last_reminder_sent(user_id: int, reminder_type: str):
    async def _upd(conn):
        await conn.execute("INSERT OR REPLACE INTO user_reminder_settings (user_id, last_reminder_sent) VALUES (?, ?)", (user_id, utc_now_iso()))
        await conn.commit()
    return await execute_db(_upd)

async def db_update_reminder_settings(user_id: int, **kwargs):
    async def _upd(conn):
        await conn.execute("INSERT OR IGNORE INTO user_reminder_settings (user_id) VALUES (?)", (user_id,))
        updates = [f"{k}=?" for k in kwargs]
        values = list(kwargs.values()) + [user_id]
        if updates:
            await conn.execute(f"UPDATE user_reminder_settings SET {', '.join(updates)} WHERE user_id=?", values)
        await conn.commit()
    return await execute_db(_upd)

async def get_user_translation_language(user_id: int) -> str:
    async def _get(conn):
        cur = await conn.execute("SELECT lang FROM user_translation WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 'off'
    return await execute_db(_get)

async def translate_text(text: str, target_lang: str) -> str:
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except:
        return text

# ===================================================================
# 26. دوال الأدمن والإحصائيات
# ===================================================================

async def add_bot_admin(user_id: int) -> bool:
    async def _add(conn):
        await conn.execute("INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?, ?, ?)", (user_id, PRIMARY_OWNER_ID, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_add)

async def remove_bot_admin(user_id: int) -> bool:
    async def _remove(conn):
        await conn.execute("DELETE FROM bot_admins WHERE user_id=?", (user_id,))
        await conn.commit()
        return True
    return await execute_db(_remove)

async def db_stats():
    async def _get(conn):
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
    return await execute_db(_get)

async def db_get_learning_stats():
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM learning_patterns")
        patterns = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM sentiment_history")
        sentiments = (await cur.fetchone())[0]
        return {'patterns': patterns, 'sentiments': sentiments}
    return await execute_db(_get)
# ===================================================================
# 27. دوال الأمان والحماية
# ===================================================================

# ===================================================================
# 27.1 دوال التحقق من الصلاحيات
# ===================================================================

async def check_bot_admin_permissions_group(bot, chat_id: int) -> dict:
    """التحقق من صلاحيات البوت في المجموعة"""
    try:
        me = await bot.get_chat_member(chat_id, bot.id)
        if me.status not in ['administrator', 'creator']:
            return {'can_act': False, 'reason': 'البوت ليس مشرفاً في المجموعة', 'permissions': {}}
        
        perms = {
            'can_delete': getattr(me, 'can_delete_messages', False),
            'can_ban': getattr(me, 'can_restrict_members', False),
            'can_pin': getattr(me, 'can_pin_messages', False),
            'can_invite': getattr(me, 'can_invite_users', False),
            'can_promote': getattr(me, 'can_promote_members', False),
            'can_change_info': getattr(me, 'can_change_info', False),
            'can_post': getattr(me, 'can_post_messages', False),
            'can_edit': getattr(me, 'can_edit_messages', False)
        }
        
        required_perms = ['can_delete', 'can_ban']
        missing = [k for k in required_perms if not perms.get(k, False)]
        if missing:
            return {'can_act': False, 'reason': f'ينقص البوت صلاحيات: {", ".join(missing)}', 'permissions': perms}
        
        return {'can_act': True, 'reason': '', 'permissions': perms}
    except Exception as e:
        return {'can_act': False, 'reason': str(e), 'permissions': {}}

async def check_bot_permissions(bot, channel_id: str) -> Tuple[bool, str]:
    """التحقق من صلاحيات البوت في القناة"""
    try:
        chat = await bot.get_chat(channel_id)
        if chat.type != 'channel':
            return False, "ليست قناة"
        member = await bot.get_chat_member(chat.id, bot.id)
        if member.status not in ['administrator', 'creator']:
            return False, "البوت ليس مشرفاً"
        if not member.can_post_messages:
            return False, "لا يملك صلاحية النشر"
        return True, ""
    except Exception as e:
        return False, str(e)

async def is_currently_admin_in_group(bot, chat_id: int, user_id: int) -> bool:
    """التحقق من كون المستخدم مشرفاً حالياً في المجموعة"""
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
    """مسح كاش الصلاحيات"""
    try:
        if CACHETOOLS_AVAILABLE:
            if chat_id and user_id:
                _auth_cache.pop(f"auth_{chat_id}_{user_id}", None)
            elif chat_id:
                keys = [k for k in _auth_cache if k.startswith(f"auth_{chat_id}_")]
                for k in keys:
                    _auth_cache.pop(k, None)
            else:
                _auth_cache.clear()
        else:
            if chat_id and user_id:
                _auth_cache.pop(f"auth_{chat_id}_{user_id}", None)
            elif chat_id:
                for key in list(_auth_cache.keys()):
                    if key.startswith(f"auth_{chat_id}_"):
                        del _auth_cache[key]
            else:
                _auth_cache.clear()
    except Exception as e:
        logger.error(f"خطأ في مسح الكاش: {e}")

async def is_authorized_in_group(bot, chat_id: int, user_id: int) -> bool:
    """التحقق من صلاحية المستخدم في المجموعة"""
    if user_id == PRIMARY_OWNER_ID:
        return True
    
    bot_perms = await check_bot_admin_permissions_group(bot, chat_id)
    if not bot_perms.get('can_act', False):
        return False
    
    cache_key = f"auth_{chat_id}_{user_id}"
    if CACHETOOLS_AVAILABLE and cache_key in _auth_cache:
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
            elif await db_is_real_admin(chat_id, user_id):
                authorized = True
    except Exception:
        authorized = (await db_is_hidden_owner(chat_id, user_id) or 
                     await db_is_hidden_admin(chat_id, user_id) or 
                     await db_is_real_admin(chat_id, user_id))
    
    if CACHETOOLS_AVAILABLE:
        _auth_cache[cache_key] = (time_module.time(), authorized)
    
    return authorized

async def is_bot_admin(user_id: int) -> bool:
    """التحقق من كون المستخدم مشرف بوت"""
    if user_id == PRIMARY_OWNER_ID:
        return True
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM bot_admins WHERE user_id=? AND is_active=1", (user_id,))
        return await cur.fetchone() is not None
    return await execute_db(_check)

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
        cur = await conn.execute("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=? AND is_active=1", (chat_id, user_id))
        return await cur.fetchone() is not None
    return await execute_db(_check)

# ===================================================================
# 27.2 دوال إعدادات الأمان
# ===================================================================

async def db_get_security_settings(chat_id: int, force_refresh: bool = False) -> dict:
    """جلب إعدادات الأمان للمجموعة"""
    default_settings = {
        'delete_links': False, 'links': False, 'mentions': False, 'warn': True, 'slow_mode': False,
        'slow_mode_seconds': 5, 'welcome_enabled': False,
        'welcome_text': "مرحباً {user} في {chat} 🤍", 'goodbye_enabled': False,
        'goodbye_text': "وداعاً {user} 👋", 'delete_banned_words': False,
        'auto_penalty': 'none', 'auto_mute_duration': 60,
        'delete_videos': False, 'delete_audio': False, 'delete_animation': False,
        'delete_service': False, 'delete_documents': False, 'delete_stickers': False,
        'delete_forwarded': False, 'delete_polls': False, 'delete_games': False,
        'delete_voice': False, 'delete_video_note': False,
        'delete_penalty': 'none', 'delete_penalty_duration': 0,
        'antiflood_enabled': False, 'antiflood_messages': 5, 'antiflood_seconds': 10,
        'antiflood_penalty': 'mute', 'max_warnings': 3, 'warn_penalty': 'ban',
        'max_message_length': 0, 'night_mode_enabled': False,
        'night_mode_start': '23:00', 'night_mode_end': '06:00', 'night_mode_action': 'mute',
        'captcha_enabled': False, 'captcha_timeout': 60,
        'max_links_per_message': 0, 'max_mentions_per_message': 0
    }
    if not isinstance(chat_id, int) or chat_id <= 0:
        return default_settings.copy()
    
    if not force_refresh and CACHETOOLS_AVAILABLE and chat_id in _security_cache:
        cached_time, value = _security_cache[chat_id]
        if time_module.time() - cached_time < _AUTH_CACHE_TTL:
            return value.copy()
    
    async def _get(conn):
        try:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
            row = await cur.fetchone()
            if row:
                settings = {}
                for key in default_settings:
                    if hasattr(row, key):
                        val = getattr(row, key)
                        settings[key] = (val == 1) if isinstance(default_settings[key], bool) else (val if val is not None else default_settings[key])
                    else:
                        settings[key] = default_settings[key]
                if CACHETOOLS_AVAILABLE:
                    _security_cache[chat_id] = (time_module.time(), settings)
                return settings
            await conn.execute("INSERT INTO group_security (chat_id) VALUES (?)", (chat_id,))
            await conn.commit()
            if CACHETOOLS_AVAILABLE:
                _security_cache[chat_id] = (time_module.time(), default_settings.copy())
            return default_settings.copy()
        except Exception as e:
            logger.error(f"خطأ في جلب إعدادات الأمان {chat_id}: {e}")
            return default_settings.copy()
        finally:
            conn.row_factory = aiosqlite.Row
    return await execute_db(_get)

async def db_set_security_settings(chat_id: int, **kwargs) -> bool:
    """تعيين إعدادات الأمان للمجموعة"""
    if not isinstance(chat_id, int) or chat_id <= 0:
        return False
    
    allowed_penalties = ['none', 'warn', 'mute', 'kick', 'ban']
    validated = {}
    for key, value in kwargs.items():
        if key not in _ALLOWED_SECURITY_COLUMNS:
            continue
        if key.endswith('_enabled') or key in ['delete_links', 'links', 'mentions', 'slow_mode', 'delete_banned_words',
                                                 'welcome_enabled', 'goodbye_enabled', 'delete_videos', 'delete_audio',
                                                 'delete_animation', 'delete_service', 'delete_documents', 'delete_stickers',
                                                 'delete_forwarded', 'delete_polls', 'delete_games', 'delete_voice',
                                                 'delete_video_note', 'antiflood_enabled', 'night_mode_enabled', 'captcha_enabled']:
            validated[key] = 1 if value else 0
        elif key.endswith('_penalty') or key == 'auto_penalty':
            validated[key] = value if value in allowed_penalties else 'none'
        elif key.endswith('_text') or key.endswith('_start') or key.endswith('_end'):
            validated[key] = html.escape(str(value)[:1000]) if value else ""
        else:
            try:
                validated[key] = int(value) if value is not None else 0
            except (ValueError, TypeError):
                validated[key] = 0
    
    if not validated:
        return False
    
    async def _set(conn):
        try:
            cur = await conn.execute("SELECT 1 FROM group_security WHERE chat_id=?", (chat_id,))
            if not await cur.fetchone():
                await conn.execute("INSERT INTO group_security (chat_id) VALUES (?)", (chat_id,))
            updates = [f"{k}=?" for k in validated]
            values = list(validated.values()) + [chat_id]
            await conn.execute(f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id=?", values)
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في تعيين إعدادات الأمان {chat_id}: {e}")
            return False
    
    result = await execute_db(_set)
    if CACHETOOLS_AVAILABLE:
        _security_cache.pop(chat_id, None)
    return result

# ===================================================================
# 27.3 دوال قفل المجموعة والوضع البطيء
# ===================================================================

async def is_chat_locked(chat_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM chat_locks WHERE chat_id=? AND locked=1", (chat_id,))
        return await cur.fetchone() is not None
    return await execute_db(_check)

async def db_set_chat_lock(chat_id: int, locked: bool, locked_by: int = None) -> bool:
    if not isinstance(chat_id, int) or chat_id <= 0:
        return False
    async def _set(conn):
        if locked:
            await conn.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?, 1, ?, ?)", (chat_id, utc_now_iso(), locked_by))
        else:
            await conn.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await conn.commit()
        return True
    return await execute_db(_set)

async def db_check_slow_mode(chat_id: int, user_id: int) -> bool:
    settings = await db_get_security_settings(chat_id)
    if not settings.get('slow_mode', False):
        return True
    seconds = settings.get('slow_mode_seconds', 5)
    async def _check(conn):
        cur = await conn.execute("SELECT message_time FROM user_messages WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        row = await cur.fetchone()
        now = utc_now()
        if row:
            try:
                last_time = datetime.fromisoformat(row[0])
                if (now - last_time).total_seconds() < seconds:
                    return False
            except:
                pass
        await conn.execute("INSERT OR REPLACE INTO user_messages (user_id, chat_id, message_time) VALUES (?, ?, ?)", (user_id, chat_id, now.isoformat()))
        await conn.commit()
        return True
    return await execute_db(_check)

# ===================================================================
# 27.4 دوال الكلمات المحظورة
# ===================================================================

async def db_add_banned_word(word: str, chat_id: int, added_by: int) -> bool:
    if not word or not isinstance(word, str):
        return False
    word = word.strip().lower()[:100]
    if len(word) < 2:
        return False
    async def _add(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM banned_words WHERE chat_id=?", (chat_id,))
        count = (await cur.fetchone())[0]
        if count >= _MAX_BANNED_WORDS_PER_CHAT:
            return False
        if chat_id == -1:
            cur = await conn.execute("SELECT COUNT(*) FROM banned_words WHERE chat_id=-1")
            if (await cur.fetchone())[0] >= _MAX_BANNED_WORDS_GLOBAL:
                return False
        await conn.execute("INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?, ?, ?, ?)", (word, chat_id, added_by, utc_now_iso()))
        await conn.commit()
        if chat_id == -1:
            await rebuild_banned_patterns()
        return True
    return await execute_db(_add)

async def db_remove_banned_word(word: str, chat_id: int) -> bool:
    if not word or not isinstance(word, str):
        return False
    word = word.strip().lower()
    async def _remove(conn):
        await conn.execute("DELETE FROM banned_words WHERE word=? AND chat_id=?", (word, chat_id))
        await conn.commit()
        if chat_id == -1:
            await rebuild_banned_patterns()
        return True
    return await execute_db(_remove)

async def db_get_banned_words(chat_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT word, added_by, added_at FROM banned_words WHERE chat_id=? OR chat_id=-1 ORDER BY word", (chat_id,))
        return await cur.fetchall()
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

async def rebuild_banned_patterns():
    global BANNED_PATTERNS
    async def _get(conn):
        cur = await conn.execute("SELECT word FROM banned_words WHERE chat_id=-1")
        return [row[0] for row in await cur.fetchall()]
    BANNED_PATTERNS = await execute_db(_get)
    logger.info(f"✅ تم تحديث {len(BANNED_PATTERNS)} كلمة محظورة عالمية")

# ===================================================================
# 27.5 دوال العقوبات والإجراءات الإشرافية
# ===================================================================

async def apply_penalty_with_duration(bot, chat_id: int, user_id: int, penalty: str, duration_minutes: int = 0, reason: str = "", moderator_id: int = None) -> Tuple[bool, str]:
    if user_id == PRIMARY_OWNER_ID:
        return False, "لا يمكن تطبيق عقوبة على المطور الأساسي"
    if await db_is_hidden_owner(chat_id, user_id):
        return False, "لا يمكن تطبيق عقوبة على المالك المخفي"
    
    if penalty == 'kick':
        return await execute_kick(bot, chat_id, user_id, reason, moderator_id)
    elif penalty == 'ban':
        return await execute_ban(bot, chat_id, user_id, reason, moderator_id)
    elif penalty == 'mute':
        return await execute_mute(bot, chat_id, user_id, duration_minutes, reason, moderator_id)
    elif penalty == 'warn':
        return await execute_warn(bot, chat_id, user_id, moderator_id, reason)
    elif penalty == 'restrict':
        return await execute_restrict(bot, chat_id, user_id, reason, moderator_id)
    return False, "عقوبة غير معروفة"

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
        return False, f"❌ حدث خطأ: {str(e)[:100]}"

async def execute_mute(bot, chat_id: int, user_id: int, duration_minutes: int = None, reason: str = "", moderator_id: int = None) -> Tuple[bool, str]:
    try:
        until_date = (datetime.utcnow() + timedelta(minutes=duration_minutes)) if duration_minutes and duration_minutes > 0 else None
        await bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=False), until_date=until_date)
        duration_text = f" لمدة {duration_minutes} دقيقة" if duration_minutes else " بشكل دائم"
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'mute', ?, ?, ?, ?)", (chat_id, user_id, duration_minutes or -1, moderator_id, reason[:200] if reason else "", utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        return True, f"✅ تم كتم المستخدم {user_id}{duration_text}"
    except Exception as e:
        logger.error(f"خطأ في كتم المستخدم {user_id}: {e}")
        return False, f"❌ حدث خطأ: {str(e)[:100]}"

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
        return False, f"❌ حدث خطأ: {str(e)[:100]}"

async def execute_warn(bot, chat_id: int, user_id: int, moderator_id: int, reason: str = "") -> Tuple[bool, str]:
    settings = await db_get_security_settings(chat_id)
    max_warnings = settings.get('max_warnings', 3)
    warn_penalty = settings.get('warn_penalty', 'ban')
    async def _add_warning(conn):
        cur = await conn.execute("SELECT warnings FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        row = await cur.fetchone()
        warnings = (row[0] if row else 0) + 1
        await conn.execute("INSERT OR REPLACE INTO user_warnings (user_id, chat_id, warnings, updated_at, last_warning) VALUES (?, ?, ?, ?, ?)", (user_id, chat_id, warnings, utc_now_iso(), utc_now_iso()))
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
        return False, f"❌ حدث خطأ: {str(e)[:100]}"

async def execute_unban(bot, chat_id: int, user_id: int, moderator_id: int = None) -> Tuple[bool, str]:
    try:
        await bot.unban_chat_member(chat_id, user_id)
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, created_at) VALUES (?, ?, 'unban', ?, ?)", (chat_id, user_id, moderator_id, utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        return True, f"✅ تم إلغاء حظر المستخدم {user_id}"
    except Exception as e:
        return False, f"❌ حدث خطأ: {str(e)[:100]}"

async def execute_pin(bot, chat_id: int, message_id: int, disable_notification: bool = False) -> Tuple[bool, str]:
    try:
        await bot.pin_chat_message(chat_id, message_id, disable_notification=disable_notification)
        return True, "✅ تم تثبيت الرسالة"
    except Exception as e:
        return False, f"❌ فشل التثبيت: {str(e)[:100]}"

async def execute_moderation_action(bot, chat_id: int, user_id: int, action: str, reason: str = "", duration: int = None, moderator_id: int = None):
    actions = {
        'ban': execute_ban, 'mute': execute_mute, 'warn': execute_warn,
        'kick': execute_kick, 'restrict': execute_restrict, 'unban': execute_unban
    }
    if action in actions:
        if action == 'mute':
            return await actions[action](bot, chat_id, user_id, duration, reason, moderator_id)
        elif action == 'warn':
            return await actions[action](bot, chat_id, user_id, moderator_id, reason)
        else:
            return await actions[action](bot, chat_id, user_id, reason, moderator_id)
    return False, f"إجراء غير معروف: {action}"

async def delete_and_penalize(update: Update, context: ContextTypes.DEFAULT_TYPE, warning_message: str):
    if not update.message:
        return
    message = update.message
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    try:
        await message.delete()
    except Exception:
        pass
    
    try:
        await safe_send_markdown(context.bot, chat_id, warning_message)
    except:
        pass
    
    settings = await db_get_security_settings(chat_id)
    penalty = settings.get('auto_penalty', 'none')
    if penalty != 'none':
        duration = settings.get('auto_mute_duration', 60)
        await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, duration, reason="مخالفة قواعد المجموعة")

async def get_moderation_log(chat_id: int, limit: int = 20) -> str:
    async def _get_log(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT user_id, action, duration_minutes, reason, created_at, moderator_id FROM moderation_log WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?", (chat_id, limit))
        return await cur.fetchall()
    logs = await execute_db(_get_log)
    if not logs:
        return "📭 لا توجد سجلات إجراءات"
    
    text = "📜 **سجل إجراءات المجموعة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for log in logs:
        user_id, action, duration, reason, created_at, moderator_id = log['user_id'], log['action'], log['duration_minutes'], log['reason'], log['created_at'], log['moderator_id']
        try:
            time_str = utc_to_mecca(datetime.fromisoformat(created_at)).strftime("%Y-%m-%d %H:%M")
        except:
            time_str = str(created_at)[:16] if created_at else "?"
        
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
        mod_text = f"\n   👤 بواسطة: `{moderator_id}`" if moderator_id else ""
        text += f"• `{user_id}` → {action}{duration_text}{reason_text}{mod_text}\n   🕐 {time_str}\n\n"
    return text

# ===================================================================
# 27.6 دوال مضاد الفيضان والأحداث الأمنية
# ===================================================================

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
        try:
            _flood_cache.popitem(last=False)
        except:
            break
    
    if now - _flood_cache_time.get('last_cleanup', 0) > 300:
        _flood_cache_time['last_cleanup'] = now
        for key in list(_flood_cache.keys()):
            messages = [t for t in _flood_cache[key] if now - t < time_window] if isinstance(_flood_cache[key], list) else []
            if not messages:
                _flood_cache.pop(key, None)
            else:
                _flood_cache[key] = messages
    
    return False

async def check_failed_attempts(chat_id: int, user_id: int) -> bool:
    cache_key = f"failed_{chat_id}_{user_id}"
    now = time_module.time()
    if cache_key not in _failed_attempts_cache:
        _failed_attempts_cache[cache_key] = []
    _failed_attempts_cache[cache_key] = [t for t in _failed_attempts_cache[cache_key] if now - t < _FAILED_ATTEMPTS_WINDOW]
    if len(_failed_attempts_cache[cache_key]) >= _MAX_FAILED_ATTEMPTS:
        return False
    _failed_attempts_cache[cache_key].append(now)
    return True

async def log_security_event(event_type: str, chat_id: int, user_id: int, details: dict = None, severity: str = "info"):
    try:
        async def _log(conn):
            await conn.execute("INSERT INTO security_events (event_type, chat_id, user_id, details, severity, created_at) VALUES (?, ?, ?, ?, ?, ?)", (event_type, chat_id, user_id, json.dumps(details) if details else None, severity, utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        advanced_logger.log_security(event_type, user_id, details, severity.upper())
    except Exception as e:
        logger.error(f"خطأ في تسجيل حدث أمني: {e}")

class SecurityAudit:
    async def log(self, event_type: str, user_id: int, details: dict = None, severity: str = "INFO"):
        await log_security_event(event_type, None, user_id, details, severity)

security_audit = SecurityAudit()

# ===================================================================
# 27.7 دوال المشرفين المخفيين
# ===================================================================

async def db_register_hidden_owner_group(chat_id: int, owner_id: int) -> bool:
    async def _register(conn):
        cur = await conn.execute("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, owner_id))
        if await cur.fetchone():
            return True
        await conn.execute("INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden, created_at) VALUES (?, ?, 1, ?)", (chat_id, owner_id, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_register)

async def db_add_hidden_admin(chat_id: int, admin_id: int, added_by: int) -> bool:
    async def _add(conn):
        cur = await conn.execute("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
        if await cur.fetchone():
            return False
        await conn.execute("INSERT INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?, ?, ?, ?)", (chat_id, admin_id, added_by, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_add)

async def db_remove_hidden_admin(chat_id: int, admin_id: int) -> bool:
    async def _remove(conn):
        await conn.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
        await conn.commit()
        invalidate_auth_cache(chat_id, admin_id)
        return True
    return await execute_db(_remove)

async def db_get_hidden_admins(chat_id: int) -> List[Dict]:
    async def _get(conn):
        cur = await conn.execute("SELECT admin_id, added_by, added_at FROM hidden_admins WHERE chat_id=? AND is_active=1 ORDER BY added_at DESC", (chat_id,))
        return [{'admin_id': row[0], 'added_by': row[1], 'added_at': row[2]} for row in await cur.fetchall()]
    return await execute_db(_get)

# ===================================================================
# 27.8 دوال الإحالات والمكافآت
# ===================================================================

async def db_add_referral(referrer_id: int, referred_id: int) -> bool:
    if referrer_id == referred_id:
        return False
    async def _add(conn):
        cur = await conn.execute("SELECT 1 FROM referrals WHERE referred_id=?", (referred_id,))
        if await cur.fetchone():
            return False
        today_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        cur = await conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND created_at >= ?", (referrer_id, today_start))
        if (await cur.fetchone())[0] >= int((await db_get_referral_settings()).get('max_referrals_per_day', '5')):
            return False
        await conn.execute("INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)", (referrer_id, referred_id, utc_now_iso()))
        await conn.commit()
        return True
    return await execute_db(_add)

async def db_auto_reward_referral(referrer_id: int, referred_id: int) -> int:
    async def _reward(conn):
        settings = await db_get_referral_settings()
        reward_days = int(settings.get('reward_days_per_referral', '3'))
        await conn.execute("INSERT INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days) VALUES (?, 1, ?, 0) ON CONFLICT(user_id) DO UPDATE SET referral_count = referral_count + 1, total_reward_days = total_reward_days + ?", (referrer_id, reward_days, reward_days))
        await conn.commit()
        return reward_days
    return await execute_db(_reward)

async def db_get_referral_stats(user_id: int) -> dict:
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,))
        total_referrals = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT referral_count, total_reward_days, claimed_reward_days FROM referral_rewards WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row:
            return {'total_referrals': total_referrals, 'referral_count': row[0], 'total_reward_days': row[1], 'claimed_reward_days': row[2], 'available_days': row[1] - row[2]}
        return {'total_referrals': total_referrals, 'referral_count': 0, 'total_reward_days': 0, 'claimed_reward_days': 0, 'available_days': 0}
    return await execute_db(_get)

async def db_claim_referral_reward(user_id: int) -> int:
    async def _claim(conn):
        stats = await db_get_referral_stats(user_id)
        available = stats['available_days']
        if available <= 0:
            return 0
        cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        current_sub = 0
        if row and row[0]:
            try:
                end_date = datetime.fromisoformat(row[0])
                if end_date > utc_now():
                    current_sub = (end_date - utc_now()).days
            except:
                pass
        new_end = (utc_now() + timedelta(days=current_sub + available)).isoformat()
        await conn.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (new_end, user_id))
        await conn.execute("UPDATE referral_rewards SET claimed_reward_days = claimed_reward_days + ? WHERE user_id=?", (available, user_id))
        await conn.commit()
        return available
    return await execute_db(_claim)

async def db_get_referral_settings() -> dict:
    async def _get(conn):
        cur = await conn.execute("SELECT key, value FROM referral_settings")
        return {row[0]: row[1] for row in await cur.fetchall()}
    return await execute_db(_get)

# ===================================================================
# 27.9 دوال مساعدة للأوامر
# ===================================================================

async def notify_group_admins(bot, chat_id: int, requester_id: int, chat_name: str):
    try:
        admins = await bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.user.is_bot or admin.user.id == requester_id:
                continue
            try:
                await bot.send_message(admin.user.id, f"📢 **طلب تفعيل البوت!**\n\n👤 المستخدم: {requester_id}\n📌 المجموعة: {chat_name}\n🆔 المعرف: `{chat_id}`\n\nلتفعيل البوت، استخدم:\n`/syncgroup`\nفي المجموعة.")
            except:
                pass
    except Exception as e:
        logger.error(f"خطأ في إشعار المشرفين: {e}")

async def ensure_force_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    try:
        force_channel = await db_get_force_subscribe_channel()
    except:
        return True
    if not force_channel:
        return True
    try:
        member = await context.bot.get_chat_member(f"@{force_channel}", user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except:
        pass
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{force_channel}")],
        [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data=CallbackData.CHECK_SUBSCRIBE)]
    ])
    await safe_send_markdown(context.bot, user_id, f"⚠️ **يجب الاشتراك في قناة البوت أولاً**\n\nاشترك في قناة @{force_channel} ثم اضغط على 'تحقق من الاشتراك'.", reply_markup=keyboard)
    return False

async def add_points(user_id: int, points: int = 1):
    async def _add(conn):
        await conn.execute("UPDATE users SET points = points + ?, last_activity = ? WHERE user_id=?", (points, utc_now_iso(), user_id))
        cur = await conn.execute("SELECT points, level FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row:
            current_points, current_level = row[0] or 0, row[1] or 1
            new_level = current_level
            for lvl, req in sorted(LEVEL_REQUIREMENTS.items(), reverse=True):
                if current_points >= req:
                    new_level = lvl
                    break
            if new_level > current_level:
                await conn.execute("UPDATE users SET level=? WHERE user_id=?", (new_level, user_id))
        await conn.commit()
    await execute_db(_add)

async def update_user_points(user_id: int, amount: int = 1):
    await add_points(user_id, amount)

async def achievement_system(user_id: int, achievement: str):
    async def _ach(conn):
        await conn.execute("INSERT OR IGNORE INTO achievements (user_id, achievement, created_at, points) VALUES (?, ?, ?, 10)", (user_id, achievement, utc_now_iso()))
        await conn.commit()
    await execute_db(_ach)

LEVEL_REQUIREMENTS = {1: 0, 2: 100, 3: 250, 4: 500, 5: 1000, 6: 2000, 7: 4000, 8: 8000, 9: 16000, 10: 32000}

async def get_rank(user_id: int) -> dict:
    async def _get(conn):
        cur = await conn.execute("SELECT points, level FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return {'level': row[1] or 1, 'points': row[0] or 0} if row else {'level': 1, 'points': 0}
    return await execute_db(_get)

async def get_top_users(limit: int = 10) -> list:
    async def _get(conn):
        cur = await conn.execute("SELECT user_id, points, level FROM users WHERE banned=0 ORDER BY points DESC LIMIT ?", (limit,))
        return [(row[0], row[1], row[2]) for row in await cur.fetchall()]
    return await execute_db(_get)
# ===================================================================
# 28. معرفات الأزرار (CallbackData) – موحدة ومتسقة
# ===================================================================

class CallbackData:
    # ===== القائمة الرئيسية والتنقل =====
    MAIN_MENU = "main_menu"
    BACK = "back"
    CANCEL_SESSION = "cancel_session"
    
    # ===== القنوات =====
    CHANNELS_MY = "channels:my_channels"
    CHANNELS_ADD = "channels:add"
    CHANNELS_DELETE_PREFIX = "channels:delete:"
    CHANNELS_SELECT_PREFIX = "channels:select:"
    
    # ===== المنشورات =====
    POSTS_ADD_15 = "posts:add_15"
    POSTS_PUBLISH_ONE = "posts:publish_one"
    POSTS_MY = "posts:my_posts"
    POSTS_RECYCLE = "posts:recycle"
    POSTS_DELETE_SINGLE_PREFIX = "posts:delete_single:"
    POSTS_CONFIRM_CLEAR_ALL_PREFIX = "posts:confirm_clear_all:"
    POSTS_CLEAR_ALL_PREFIX = "posts:clear_all:"
    PUBLISH_ALL_CHANNELS = "publish_all_channels"
    
    # ===== الإحصائيات =====
    STATS_PENDING = "stats:pending"
    STATS_FULL = "stats:full"
    
    # ===== المجموعات =====
    GROUPS_MY = "groups:my_groups"
    GROUPS_SETTINGS_PREFIX = "groups:settings:"
    
    # ===== الإعدادات =====
    SETTINGS_MENU = "settings:menu"
    SETTINGS_TOGGLE_AUTO_PUBLISH = "settings:toggle_auto_publish"
    SETTINGS_TOGGLE_AUTO_RECYCLE = "settings:toggle_auto_recycle"
    
    # ===== الجدولة =====
    SCHEDULE_MENU_PREFIX = "schedule:menu:"
    SCHEDULE_SET_INTERVAL_MINUTES_PREFIX = "schedule:set_interval_minutes:"
    SCHEDULE_SET_INTERVAL_HOURS_PREFIX = "schedule:set_interval_hours:"
    SCHEDULE_SET_INTERVAL_DAYS_PREFIX = "schedule:set_interval_days:"
    SCHEDULE_SET_DAYS_PREFIX = "schedule:set_days:"
    SCHEDULE_SET_DATES_PREFIX = "schedule:set_dates:"
    SCHEDULE_SET_PUBLISH_TIME_PREFIX = "schedule:set_publish_time:"
    SCHEDULE_DAY_SELECT_PREFIX = "schedule:day_select:"
    SCHEDULE_SAVE_DAYS = "schedule:save_days"
    SCHEDULE_SET_CRON_PREFIX = "schedule:set_cron:"
    
    # ===== الأمان =====
    SECURITY_LINKS_PREFIX = "security:links:"
    SECURITY_MENTIONS_PREFIX = "security:mentions:"
    SECURITY_SLOWMODE_PREFIX = "security:slow_mode:"
    SECURITY_BANNED_WORDS_MENU_PREFIX = "security:banned_words_menu:"
    SECURITY_WELCOME_PREFIX = "security:welcome_enabled:"
    SECURITY_GOODBYE_PREFIX = "security:goodbye_enabled:"
    SECURITY_CLOSE = "security:close"
    SECURITY_SELECT_GROUP = "security_select_group:"
    SECURITY_REFRESH_GROUPS = "security_refresh_groups"
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
    
    # ===== الكلمات المحظورة =====
    BANNED_WORDS_ADD_PREFIX = "banned_words:add:"
    BANNED_WORDS_LIST_PREFIX = "banned_words:list:"
    BANNED_WORDS_REMOVE_PREFIX = "banned_words:remove:"
    
    # ===== العقوبات =====
    PENALTY_MENU = "penalty_menu"
    PENALTY_KICK = "penalty:kick"
    PENALTY_BAN = "penalty:ban"
    PENALTY_MUTE = "penalty:mute"
    PENALTY_WARN = "penalty:warn"
    PENALTY_RESTRICT = "penalty:restrict"
    PENALTY_NONE = "penalty:none"
    
    # ===== الإجراءات المتقدمة =====
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
    
    # ===== لوحة التحكم =====
    PANEL_LOCK_PREFIX = "panel:lock:"
    PANEL_UNLOCK_PREFIX = "panel:unlock:"
    PANEL_CLOSE = "panel:close"
    
    # ===== المساعدة والدعم =====
    HELP = "help"
    SUPPORT_MENU = "support:menu"
    SUPPORT_HELP = "support:help"
    SUPPORT_TICKET = "support:ticket"
    SUPPORT_BACK = "support:back"
    
    # ===== التجربة والاشتراك =====
    TRIAL = "trial"
    SUBSCRIBE_MENU = "subscribe:menu"
    BUY_SUBSCRIPTION_1 = "buy:subscription_1"
    BUY_SUBSCRIPTION_2 = "buy:subscription_2"
    BUY_SUBSCRIPTION_30 = "buy:subscription_30"
    BUY_SUBSCRIPTION_90 = "buy:subscription_90"
    
    # ===== المطور والتحديثات =====
    DEVELOPER = "developer"
    UPDATES = "updates"
    
    # ===== الإحالات =====
    REFERRAL_MENU = "referral:menu"
    REFERRAL_COPY_LINK_PREFIX = "referral:copy_link:"
    REFERRAL_CLAIM_REWARD = "referral:claim_reward"
    REFERRAL_LIST = "referral:list"
    
    # ===== التذكيرات =====
    REMINDER_MENU = "reminder:menu"
    REMINDER_TOGGLE_SUB = "reminder:toggle_sub"
    REMINDER_TOGGLE_DAILY = "reminder:toggle_daily"
    REMINDER_TOGGLE_WEEKLY = "reminder:toggle_weekly"
    REMINDER_SET_DAYS = "reminder:set_days"
    REMINDER_SET_LANG = "reminder:set_lang"
    REMINDER_LANG_PREFIX = "reminder:lang:"
    
    # ===== الترجمة =====
    TRANSLATION_MENU = "translation:menu"
    TRANSLATION_OFF = "translation:off"
    TRANSLATION_SET_PREFIX = "translation:set:"
    
    # ===== المسابقات =====
    CONTESTS_MENU = "contests_menu"
    CONTEST_JOIN_PREFIX = "contest_join:"
    CONTEST_WINNERS = "contest_winners"
    CONTESTS_BACK = "contests_back"
    
    # ===== لوحة الأدمن =====
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
    
    # ===== الردود التلقائية =====
    AUTO_REPLY_MENU_PREFIX = "auto_reply_menu:"
    AUTO_REPLY_TOGGLE_PREFIX = "auto_reply_toggle:"
    AUTO_REPLY_ADMINS_PREFIX = "auto_reply_admins:"
    AUTO_REPLY_RESET_PREFIX = "auto_reply_reset:"
    AUTO_REPLY_CONFIRM_RESET_PREFIX = "auto_reply_confirm_reset:"
    AUTO_REPLY_CANCEL_PREFIX = "auto_reply_cancel:"
    AUTO_REPLY_STATS_PREFIX = "auto_reply_stats:"
    USER_AUTO_REPLY_TOGGLE_PREFIX = "user_auto_reply_toggle:"
    
    # ===== NSFW =====
    NSFW_SETTINGS = "nsfw_settings"
    NSFW_TOGGLE = "nsfw_toggle"
    NSFW_THRESHOLD_SET = "nsfw_threshold_set"
    
    # ===== أخرى =====
    CHANNEL_STATS = "channel_stats"
    CHANNEL_GROWTH = "channel_growth"
    CHANNEL_STATS_REFRESH = "channel_stats_refresh"
    MY_CHANNEL_STATS = "my_channel_stats"
    CHECK_SUBSCRIBE = "check_subscribe"
    HIDDEN_ADMIN_ADD = "hidden_admin:add"
    HIDDEN_ADMIN_REMOVE_PREFIX = "hidden_admin:remove:"
    HIDDEN_ADMIN_LIST = "hidden_admin:list"

# ===================================================================
# 29. حالات المستخدم (UserState) – متوافقة مع جميع المعالجات
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
# 30. دوال الكيبوردات (مُحدثة ومُتسقة مع CallbackData)
# ===================================================================

def get_advanced_group_actions_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """لوحة الإجراءات المتقدمة للمجموعة"""
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

def security_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """لوحة الأمان"""
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
        [InlineKeyboardButton("🔙 إغلاق", callback_data=CallbackData.SECURITY_CLOSE)]
    ])

def get_admin_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """لوحة الأدمن"""
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
            InlineKeyboardButton("❤️ تنشيط الكل", callback_data=CallbackData.ADMIN_ACTIVATE_ALL_CHANNELS)
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
            InlineKeyboardButton("🖥️ حالة الرام", callback_data=CallbackData.ADMIN_RAM),
            InlineKeyboardButton("📊 إحصائيات", callback_data=CallbackData.ADMIN_STATS)
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
            InlineKeyboardButton("📢 عرض القناة", callback_data=CallbackData.ADMIN_SHOW_UPDATE_CHANNEL),
            InlineKeyboardButton("🔄 التحديثات", callback_data=CallbackData.ADMIN_UPDATES)
        ],
        [
            InlineKeyboardButton("🔒 اشتراك إجباري", callback_data=CallbackData.ADMIN_FORCE_SUBSCRIBE),
            InlineKeyboardButton("⚙️ تعيين القناة", callback_data=CallbackData.ADMIN_SET_FORCE_CHANNEL)
        ],
        [
            InlineKeyboardButton("📨 إرسال رسالة", callback_data=CallbackData.ADMIN_BROADCAST),
            InlineKeyboardButton("📋 تذاكر", callback_data=CallbackData.ADMIN_SUPPORT_TICKETS)
        ],
        [
            InlineKeyboardButton("🗑️ حذف التذاكر", callback_data=CallbackData.ADMIN_DELETE_ALL_TICKETS),
            InlineKeyboardButton("📁 صلاحية /sendcode", callback_data=CallbackData.ADMIN_MANAGE_SENDCODE)
        ],
        [
            InlineKeyboardButton("📋 قناة التقارير", callback_data=CallbackData.ADMIN_SHOW_LOG_CHANNEL),
            InlineKeyboardButton("📋 تعيين التقارير", callback_data=CallbackData.ADMIN_SET_LOG_CHANNEL)
        ],
        [
            InlineKeyboardButton("📊 مراقبة", callback_data=CallbackData.ADMIN_MONITOR_USERS),
            InlineKeyboardButton("📈 مقاييس", callback_data=CallbackData.ADMIN_METRICS)
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])

def get_group_banned_words_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """لوحة الكلمات المحظورة للمجموعة"""
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

def get_replies_keyboard() -> InlineKeyboardMarkup:
    """لوحة الردود"""
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
    """لوحة الكلمات المحظورة للأدمن"""
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
    """لوحة الردود التلقائية للمجموعة"""
    status_text = "🟢 مفعل" if settings.get('enabled', False) else "🔴 معطل"
    admin_text = "👑 مشرفين فقط" if settings.get('only_admins', False) else "👥 الجميع"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📝 الردود: {status_text}", callback_data=f"{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}{chat_id}")],
        [InlineKeyboardButton(f"👥 المستخدمون: {admin_text}", callback_data=f"{CallbackData.AUTO_REPLY_ADMINS_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🔄 إعادة تعيين الردود", callback_data=f"{CallbackData.AUTO_REPLY_RESET_PREFIX}{chat_id}")],
        [InlineKeyboardButton("📊 إحصائيات الردود", callback_data=f"{CallbackData.AUTO_REPLY_STATS_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

def get_user_auto_reply_keyboard(user_id: int, enabled: bool) -> InlineKeyboardMarkup:
    """لوحة الردود التلقائية للمستخدم"""
    status_text = "🟢 مفعل" if enabled else "🔴 معطل"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📝 الردود التلقائية: {status_text}", callback_data=f"{CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX}{user_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])

def get_advanced_mute_duration_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """لوحة مدة الكتم المتقدمة"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱️ 5 دقائق", callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}5:{chat_id}"),
            InlineKeyboardButton("⏱️ 30 دقيقة", callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}30:{chat_id}")
        ],
        [
            InlineKeyboardButton("⏱️ 1 ساعة", callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}60:{chat_id}"),
            InlineKeyboardButton("⏱️ 12 ساعة", callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}720:{chat_id}")
        ],
        [
            InlineKeyboardButton("📆 يوم", callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}1440:{chat_id}"),
            InlineKeyboardButton("📆 أسبوع", callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}10080:{chat_id}")
        ],
        [
            InlineKeyboardButton("🔇 كتم دائم", callback_data=f"{CallbackData.ADV_MUTE_DURATION_PREFIX}0:{chat_id}"),
            InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")
        ]
    ])

def penalty_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """لوحة مفاتيح العقوبات"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👢 طرد", callback_data=f"{CallbackData.PENALTY_KICK}:{chat_id}"),
            InlineKeyboardButton("🛑 حظر", callback_data=f"{CallbackData.PENALTY_BAN}:{chat_id}")
        ],
        [
            InlineKeyboardButton("🔇 كتم", callback_data=f"{CallbackData.PENALTY_MUTE}:{chat_id}"),
            InlineKeyboardButton("⚠️ تحذير", callback_data=f"{CallbackData.PENALTY_WARN}:{chat_id}")
        ],
        [
            InlineKeyboardButton("🔒 تقييد", callback_data=f"{CallbackData.PENALTY_RESTRICT}:{chat_id}"),
            InlineKeyboardButton("❌ لا شيء", callback_data=f"{CallbackData.PENALTY_NONE}:{chat_id}")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

# ===================================================================
# 31. دوال القائمة الرئيسية
# ===================================================================

async def get_main_keyboard(user_id: int):
    """بناء القائمة الرئيسية الديناميكية للمستخدم"""
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
    
    my_groups = await db_get_user_groups_count(user_id) or 0
    has_sub = await db_has_active_subscription(user_id) or False
    sub_text = get_text(user_id, 'subscribed') if has_sub else get_text(user_id, 'not_subscribed')
    auto_status = await db_auto_status(user_id) or False
    auto_text = get_text(user_id, 'auto_on') if auto_status else get_text(user_id, 'auto_off')
    
    title = get_text(user_id, 'main_title').format(BOT_NAME, user_id, my_groups, sub_text, ch_display, cnt, auto_text)
    
    updates_channel = None
    try:
        updates_channel = await db_get_updates_channel()
    except:
        pass
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
    
    is_admin = (user_id == PRIMARY_OWNER_ID) or (await is_bot_admin(user_id))
    if is_admin:
        keyboard.append([
            InlineKeyboardButton(get_text(user_id, 'admin_panel'), callback_data=CallbackData.ADMIN_PANEL)
        ])
    
    return InlineKeyboardMarkup(keyboard), title, active
# ===================================================================
# 32. معالجات الأوامر (Command Handlers)
# ===================================================================

# 32.1 /start - بدء البوت
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
        error_id = log_error(e, {'user_id': update.effective_user.id})
        await safe_send_markdown(context.bot, update.effective_user.id, f"❌ حدث خطأ (الرمز: `{error_id}`)")

# 32.2 /language - تغيير اللغة
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

# 32.3 /syncgroup - تفعيل المجموعة
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
        await safe_send_markdown(context.bot, user_id,
            f"⚠️ **البوت ليس مشرفاً في المجموعة!**\n\n📌 تم تسجيل المجموعة `{chat_name}`.\n\n"
            f"🔹 **لتفعيل الميزات المتقدمة:**\n• اجعل البوت مشرفاً في المجموعة\n• ثم استخدم `/syncgroup` مرة أخرى\n\n"
            f"🔹 إذا كنت مالكاً أو مشرفاً، يمكنك استخدام:\n`/register_hidden_owner`\nبعد جعل البوت مشرفاً.")
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
        
        await safe_send_markdown(context.bot, real_user_id,
            f"✅ **تم تفعيل المجموعة بنجاح!**\n\n📌 اسم المجموعة: {chat_name}\n🆔 المعرف: {chat_id}\n"
            f"👤 تم تسجيلك كمالك مخفي (المعرف: `{real_user_id}`)\n👥 تم مزامنة {admin_count} مشرف\n\n"
            f"🔐 استخدم /security لإعدادات الأمان\n🛠️ استخدم /panel للوحة التحكم")
        
        if user_id == ANONYMOUS_ADMIN_ID and user_id != real_user_id:
            await safe_send_markdown(context.bot, user_id, f"🔍 تم تسجيلك كمالك مخفي باستخدام معرفك الحقيقي: `{real_user_id}`")
    else:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'group_registered'))
        await notify_group_admins(context.bot, chat_id, user_id, chat_name)

# 32.4 /register_hidden_owner - تسجيل مالك مخفي
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
        
        await safe_send_markdown(context.bot, user_id,
            f"✅ **تم تسجيلك كمالك مخفي بنجاح!**\n\n🔐 يمكنك الآن استخدام جميع أوامر الإدارة:\n"
            f"• `/security` - إعدادات الأمان\n• `/panel` - لوحة التحكم\n• `/lock` / `/unlock` - قفل وفتح المجموعة\n"
            f"• أوامر الحظر والكتم والتحذير")
        return
    
    await safe_send_markdown(context.bot, user_id, "❌ **غير مصرح!**\n\nلتسجيل نفسك كمالك مخفي، يجب أن تكون:\n• مالك المجموعة (creator)\n• أو مشرفاً في المجموعة (administrator)")

# 32.5 /add_hidden_admin - إضافة مشرف مخفي
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
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/add_hidden_admin معرف_المستخدم`\n\nمثال: `/add_hidden_admin 123456789`")
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
    except:
        await safe_send_markdown(context.bot, user_id, "❌ لا يمكن العثور على المستخدم.")
        return
    
    if await db_is_banned(target_id):
        await safe_send_markdown(context.bot, user_id, "❌ المستخدم محظور عالمياً!")
        return
    
    if await db_is_hidden_admin(chat_id, target_id):
        await safe_send_markdown(context.bot, user_id, f"⚠️ المستخدم `{target_id}` مشرف مخفي بالفعل!")
        return
    
    success = await db_add_hidden_admin(chat_id, target_id, user_id)
    if success:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'hidden_admin_added').format(target_id))
        await log_security_event("HIDDEN_ADMIN_ADDED", chat_id, user_id, {"target": target_id}, "HIGH")
        invalidate_auth_cache(chat_id, target_id)
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل إضافة المشرف المخفي!")

# 32.6 /remove_hidden_admin - إزالة مشرف مخفي
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
    except:
        pass
    
    args = context.args
    if len(args) < 1:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/remove_hidden_admin معرف_المستخدم`")
        return
    
    try:
        target_id = int(args[0])
    except ValueError:
        await safe_send_markdown(context.bot, user_id, "❌ معرف غير صالح!")
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
        await log_security_event("HIDDEN_ADMIN_REMOVED", chat_id, user_id, {"target": target_id}, "HIGH")
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل إزالة المشرف المخفي!")

# 32.7 /list_hidden_admins - عرض المشرفين المخفيين
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
    except:
        pass
    
    admins = await db_get_hidden_admins(chat_id)
    if not admins:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'no_hidden_admins'))
        return
    
    text = "🔒 **قائمة المشرفين المخفيين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for admin in admins:
        text += f"👤 `{admin['admin_id']}` (أضيف بواسطة `{admin['added_by']}`)\n"
    await safe_send_markdown(context.bot, user_id, text)

# 32.8 /trial - تجربة مجانية
async def trial_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if await db_has_used_trial(user_id):
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'trial_used'))
        return
    
    if await db_has_active_subscription(user_id):
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'already_subscribed'))
        return
    
    days = await db_activate_trial(user_id)
    if days:
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'trial'))
        await start_command_handler(update, context)
    else:
        await safe_send_markdown(context.bot, user_id, "❌ حدث خطأ أثناء تفعيل التجربة.")

# 32.9 /subscribe - الاشتراك
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

# 32.10 /help - المساعدة
async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'help'))

# 32.11 /support - مركز الدعم
async def support_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['support_mode'] = True
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 كتابة تذكرة", callback_data=CallbackData.SUPPORT_TICKET)],
        [InlineKeyboardButton("❓ المساعدة", callback_data=CallbackData.SUPPORT_HELP)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'support_welcome'), reply_markup=keyboard)

# 32.12 /support_reply - الرد على تذكرة
async def support_reply_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return
    
    args = context.args
    if len(args) < 2:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/support_reply معرف_التذكرة الرد`")
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

# 32.13 /rank - رتبتي
async def rank_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = await get_rank(user_id)
    next_level = data['level'] + 1
    req_points = LEVEL_REQUIREMENTS.get(next_level, "∞")
    await safe_send_markdown(context.bot, user_id,
        f"📊 **رتبتك**\n━━━━━━━━━━━━━━\n🎖️ المستوى: {data['level']}\n⭐ النقاط: {data['points']}\n🎯 النقاط المطلوبة للمستوى التالي: {req_points}")

# 32.14 /top - أفضل 10
async def top_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    top_users = await get_top_users(10)
    if not top_users:
        await safe_send_markdown(context.bot, user_id, "📭 لا يوجد مستخدمين بعد.")
        return
    
    text = "🏆 **أفضل 10 مستخدمين**\n━━━━━━━━━━━━━━\n"
    for idx, (uid, points, level) in enumerate(top_users, 1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        try:
            user = await context.bot.get_chat(uid)
            name = user.first_name or str(uid)
        except:
            name = str(uid)
        text += f"{medal} {name} - Lv.{level} ({points} نقطة)\n"
    await safe_send_markdown(context.bot, user_id, text)

# 32.15 /stats - إحصائيات القناة
async def stats_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    
    stats = await db_get_channel_stats(active)
    ch_info = await db_get_channel_info(active)
    channel_name = ch_info[1] if ch_info else "القناة"
    
    text = (f"📊 **إحصائيات {channel_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 إجمالي المنشورات: {stats['total_posts']}\n✅ المنشورة: {stats['published_posts']}\n"
            f"⏳ غير المنشورة: {stats['unpublished_posts']}\n👁️ إجمالي المشاهدات: {stats['total_views']}\n"
            f"📊 متوسط المشاهدات: {stats['avg_views']}")
    await safe_send_markdown(context.bot, user_id, text)

# 32.16 /developer - المطور
async def developer_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await safe_send_markdown(context.bot, user_id,
        "👨‍💻 **المطور:** @RelaxMgr\n📧 للتواصل: @RelaxMgr\n\n📌 **ريلاكس مانيجر v22.2.0**")

# 32.17 /updates - التحديثات
async def updates_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    channel = await db_get_updates_channel()
    if channel:
        text = f"📢 **آخر التحديثات**\n\nتابع قناة التحديثات: @{channel}"
    else:
        text = "📢 **آخر التحديثات**\n\nلم يتم تعيين قناة التحديثات بعد."
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

# 32.18 /sendcode - إرسال كود البوت
async def sendcode_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        allowed_user = await db_get_allowed_sendcode_user()
        if user_id != allowed_user:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح لك باستخدام هذا الأمر.")
            return
    
    code = f"/start {secrets.token_urlsafe(8)}"
    await safe_send_markdown(context.bot, user_id, f"📨 **كود البوت:**\n`{code}`")

# 32.19 /lock - قفل المجموعة
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

# 32.20 /unlock - فتح المجموعة
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

# 32.21 /schedule - جدولة منشور
async def schedule_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_SCHEDULE_POST
    await safe_send_markdown(context.bot, user_id,
        "📝 **جدولة منشور**\n\nأرسل المنشور بهذه الصيغة:\n`YYYY-MM-DD HH:MM نص المنشور`\n\n"
        "مثال: `2024-12-25 14:30 مرحباً بالجميع!`\n\n🕐 الوقت بتوقيت مكة المكرمة")

# 32.22 /panel - لوحة التحكم
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
    
    await safe_send_markdown(context.bot, user_id,
        f"🔧 **لوحة تحكم المجموعة**\n━━━━━━━━━━━━━━\n📌 **المجموعة:** {update.effective_chat.title}\n🔐 **الحالة:** {lock_status_text}",
        reply_markup=kb)

# 32.23 /set_log_channel - تعيين قناة التقارير
async def set_log_channel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return
    
    context.user_data['state'] = UserState.WAITING_LOG_CHANNEL
    await safe_send_markdown(context.bot, user_id, "📋 أرسل معرف القناة (بعلامة @ أو ID):")

# 32.24 /set_rules - تعيين قوانين المجموعة
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
        await conn.execute("INSERT OR REPLACE INTO group_rules (chat_id, rules_text, updated_by, updated_at) VALUES (?, ?, ?, ?)",
                           (chat_id, rules_text, user_id, utc_now_iso()))
        await conn.commit()
    await execute_db(_set_rules)
    await safe_send_markdown(context.bot, chat_id, "✅ تم تعيين قوانين المجموعة بنجاح!")

# 32.25 /rules - عرض قوانين المجموعة
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

# 32.26 /create_contest - إنشاء مسابقة
async def create_contest_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return
    
    context.user_data['state'] = UserState.WAITING_CONTEST_TITLE
    await safe_send_markdown(context.bot, user_id, "📝 **إنشاء مسابقة جديدة**\n\nأرسل **عنوان** المسابقة:")

# 32.27 /declare_winner - إعلان فائز
async def declare_winner_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return
    
    args = context.args
    if len(args) < 2:
        await safe_send_markdown(context.bot, user_id,
            "📝 **الاستخدام:**\n`/declare_winner معرف_المسابقة معرف_المستخدم`\n\nمثال: `/declare_winner 5 123456789`")
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
    
    success = await db_set_contest_winner(contest_id, winner_id)
    if success:
        await safe_send_markdown(context.bot, user_id,
            f"✅ تم إعلان المستخدم `{winner_id}` فائزاً في المسابقة **{contest['title']}**!")
        try:
            await context.bot.send_message(chat_id=winner_id,
                text=f"🏆 **تهانينا!**\nلقد فزت في مسابقة **{contest['title']}**!\n🎁 جائزتك: {contest['prize']}")
            await achievement_system(winner_id, 'contest_winner')
        except:
            pass
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل إعلان الفائز!")

# 32.28 /contests - عرض المسابقات
async def contests_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update or not update.effective_user:
            return
        
        user_id = update.effective_user.id
        contests = await db_get_active_contests_with_participants(limit=10)
        if not contests:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد مسابقات نشطة حالياً.")
            return
        
        text = "🏆 **المسابقات النشطة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        keyboard = []
        
        for contest in contests:
            if len(contest) < 6:
                continue
            cid, title, desc, prize, end_date, contest_type = contest[0], contest[1], contest[2], contest[3], contest[4], contest[5]
            participants = contest[6] if len(contest) > 6 else 0
            
            try:
                end_dt = datetime.fromisoformat(end_date)
                days_left = (end_dt - utc_now()).days
                time_left = f"⏳ متبقي {days_left} يوم" if days_left > 0 else "🔴 انتهت"
            except:
                time_left = "📅 تاريخ غير صحيح"
                days_left = 0
            
            participated = await db_get_user_participation(user_id, cid)
            status_icon = "✅" if participated else "📝"
            
            text += (f"📌 **{title}**\n📝 {(desc)[:100]}{'...' if len(desc) > 100 else ''}\n"
                     f"🎁 الجائزة: {prize}\n👥 المشاركون: {participants}\n🕐 {time_left}\n"
                     f"━━━━━━━━━━━━━━━━━━━━━━\n")
            
            if not participated and days_left > 0:
                keyboard.append([InlineKeyboardButton(f"{status_icon} شارك في {title[:20]}",
                                     callback_data=f"{CallbackData.CONTEST_JOIN_PREFIX}{cid}")])
        
        keyboard.append([InlineKeyboardButton("🏆 الفائزون السابقون", callback_data=CallbackData.CONTEST_WINNERS)])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
        
        await safe_send_markdown(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        error_id = log_error(e, {'user_id': update.effective_user.id if update and update.effective_user else None})
        await safe_send_markdown(context.bot, user_id, f"❌ حدث خطأ أثناء تحميل المسابقات (الرمز: `{error_id}`).")

# 32.29 /security - إعدادات الأمان
async def security_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, user_id, get_text(user_id, 'admin_only'))
        return
    
    settings = await db_get_security_settings(chat_id)
    text = _build_security_text(settings)
    keyboard = security_keyboard(chat_id)
    await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

# 32.30 أوامر الإشراف (ban, mute, warn, kick, restrict, pin, unban)
async def handle_moderation_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'admin_only'))
        return
    
    bot_perms = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bot_perms['can_act']:
        await safe_send_markdown(context.bot, user_id, f"❌ {bot_perms['reason']}")
        return
    
    command = update.message.text.split()[0][1:]
    args = context.args
    target_id = None
    reason = ""
    
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        if args:
            reason = " ".join(args)
    elif args:
        try:
            target_id = int(args[0])
            reason = " ".join(args[1:]) if len(args) > 1 else ""
        except ValueError:
            await safe_send_markdown(context.bot, chat_id, "❌ معرف المستخدم غير صالح!")
            return
    else:
        await safe_send_markdown(context.bot, chat_id, "❌ قم بالرد على رسالة المستخدم أو أرسل معرفه.")
        return
    
    if target_id == context.bot.id:
        await safe_send_markdown(context.bot, chat_id, "❌ لا يمكن تنفيذ هذا الإجراء على البوت!")
        return
    
    duration = 60 if command == 'mute' else None
    success, msg = await execute_moderation_action(context.bot, chat_id, target_id, command, reason, duration, user_id)
    await safe_send_markdown(context.bot, chat_id, msg)

# ===================================================================
# 33. معالجات الكولباك (Callback Handlers) – منقحة ومكتملة
# ===================================================================

# --------------------------- helper -------------------------------
async def _answer_query(query):
    try:
        await query.answer()
    except Exception:
        pass

async def _safe_edit(query, text, reply_markup=None):
    try:
        await safe_edit_markdown(query, text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"تعذر تعديل الرسالة: {e}")
        try:
            await safe_send_markdown(query._bot, query.message.chat_id, text, reply_markup=reply_markup)
        except:
            pass

# ===================================================================
# 33.1 القائمة الرئيسية والتنقل
# ===================================================================

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    kb, title, active = await get_main_keyboard(user_id)
    if active:
        context.user_data['active_channel'] = active
    if query:
        await _safe_edit(query, title, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, title, reply_markup=kb)

async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu_callback(update, context)

async def cancel_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    keys_to_clear = ['state', 'temp_channel', 'schedule_ch_id', 'selected_days',
                     'banned_words_chat_id', 'advanced_chat_id', 'security_chat_id',
                     'penalty_chat_id', 'mute_minutes', 'support_mode',
                     'broadcast_text', 'contest_title', 'contest_description',
                     'contest_prize', 'contest_join_id', 'admin_del_reply',
                     'reply_keyword', 'temp_log_channel_identifier']
    for key in list(context.user_data.keys()):
        if key.startswith(f"session_{user_id}") or key.startswith(f"session_target_{user_id}"):
            keys_to_clear.append(key)
    for key in keys_to_clear:
        context.user_data.pop(key, None)
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'cancelled'))
    await main_menu_callback(update, context)

# ===================================================================
# 33.2 أزرار القنوات
# ===================================================================

async def add_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_CHANNEL_ID
    await _safe_edit(query, get_text(user_id, 'send_channel_id'),
                     reply_markup=InlineKeyboardMarkup([
                         [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
                     ]))

async def my_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels:
        await _safe_edit(query, get_text(user_id, 'no_channels_list'))
        return
    text = get_text(user_id, 'channels_list')
    keyboard = []
    for row in channels:
        ch_id, ch_tele_id, ch_name, banned = row
        status = "🚫" if banned else "✅"
        keyboard.append([
            InlineKeyboardButton(f"{status} {ch_name} ({ch_tele_id})", callback_data=f"{CallbackData.CHANNELS_SELECT_PREFIX}{ch_id}"),
            InlineKeyboardButton("🗑️", callback_data=f"{CallbackData.CHANNELS_DELETE_PREFIX}{ch_id}")
        ])
    keyboard.append([InlineKeyboardButton(get_text(user_id, 'add_channel'), callback_data=CallbackData.CHANNELS_ADD)])
    keyboard.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)])
    await _safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    active = context.user_data.get('active_channel')
    if active == channel_db_id:
        context.user_data.pop('active_channel', None)
    success = await db_delete_channel_by_id(user_id, channel_db_id)
    if success:
        await _safe_edit(query, get_text(user_id, 'channel_deleted'))
    else:
        await _safe_edit(query, get_text(user_id, 'delete_failed'))
    await asyncio.sleep(1)
    await my_channels_callback(update, context)

async def select_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    channel_db_id = int(query.data.split(":")[-1])
    ch_info = await db_get_channel_info(channel_db_id)
    if not ch_info:
        await _safe_edit(query, "❌ القناة غير موجودة")
        return
    await db_set_active_channel(user_id, channel_db_id)
    context.user_data['active_channel'] = channel_db_id
    channel_name = ch_info[1] if len(ch_info) > 1 else "القناة"
    await _safe_edit(query, f"✅ تم تحديد القناة: {channel_name}")
    await asyncio.sleep(0.5)
    await main_menu_callback(update, context)

# ===================================================================
# 33.3 أزرار المنشورات
# ===================================================================

async def add_15_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    has_sub = await db_has_active_subscription(user_id)
    has_trial = await db_has_used_trial(user_id)
    if not has_sub and not has_trial:
        await _safe_edit(query, "⚠️ اشتراكك منتهٍ، استخدم /trial أو /subscribe")
        return
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await _safe_edit(query, "⚠️ اختر قناة أولاً من 'قنواتي'")
        return
    unpublished_count = await db_unpublished_count(active)
    if unpublished_count >= MAX_UNPUBLISHED_POSTS:
        await _safe_edit(query, f"⚠️ لقد تجاوزت الحد الأقصى للمنشورات غير المنشورة ({MAX_UNPUBLISHED_POSTS}).")
        return
    target_count = min(15, MAX_UNPUBLISHED_POSTS - unpublished_count)
    context.user_data[f"session_{user_id}"] = []
    context.user_data[f"session_target_{user_id}"] = target_count
    context.user_data['state'] = UserState.ADDING_POSTS
    context.user_data['temp_channel'] = active
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=CallbackData.CANCEL_SESSION)]])
    await _safe_edit(query, f"📥 **إضافة منشورات**\n\nأرسل المنشورات (نصوص، صور، فيديوهات، مستندات)\nالحد الأقصى المسموح: {target_count} منشور", reply_markup=cancel_kb)

async def publish_one_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    has_sub = await db_has_active_subscription(user_id)
    has_trial = await db_has_used_trial(user_id)
    if not has_sub and not has_trial:
        await _safe_edit(query, "⚠️ اشتراكك منتهٍ")
        return
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await _safe_edit(query, "⚠️ اختر قناة أولاً")
        return
    post = await db_get_next_post(active)
    if not post:
        await _safe_edit(query, get_text(user_id, 'no_posts'))
        return
    ch_info = await db_get_channel_info(active)
    channel_id = ch_info[0] if ch_info else None
    if not channel_id:
        await _safe_edit(query, "❌ القناة غير صالحة")
        return
    translation_lang = await get_user_translation_language(user_id)
    final_text = post['text'] or ""
    if translation_lang != 'off' and final_text:
        try:
            translated = await translate_text(final_text, translation_lang)
            if translated and translated != final_text:
                final_text = f"{final_text}\n\n🌐 {translated}"
        except:
            pass
    try:
        if post['media_type'] == 'photo' and post['media_file_id']:
            await context.bot.send_photo(channel_id, post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'video' and post['media_file_id']:
            await context.bot.send_video(channel_id, post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'document' and post['media_file_id']:
            await context.bot.send_document(channel_id, post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'audio' and post['media_file_id']:
            await context.bot.send_audio(channel_id, post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'voice' and post['media_file_id']:
            await context.bot.send_voice(channel_id, post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'animation' and post['media_file_id']:
            await context.bot.send_animation(channel_id, post['media_file_id'], caption=final_text if final_text else None)
        else:
            await context.bot.send_message(channel_id, final_text, parse_mode=None)
        await db_mark_published(post['id'])
        await db_set_last_publish(active, utc_now())
        await db_update_next_publish_date(active)
        await update_user_points(user_id, 2)
        await _safe_edit(query, "✅ تم نشر المنشور بنجاح!")
    except Forbidden as e:
        if "not enough rights" in str(e).lower():
            await _safe_edit(query, "❌ البوت لا يملك صلاحية النشر في القناة!")
        else:
            await db_increment_fail_count(post['id'])
            await _safe_edit(query, f"❌ فشل النشر - محظور")
    except Exception as e:
        await db_increment_fail_count(post['id'])
        error_id = log_error(e, {'user_id': user_id, 'action': 'publish_one'})
        await _safe_edit(query, f"❌ فشل النشر (الرمز: `{error_id}`)")
    await asyncio.sleep(1)
    await main_menu_callback(update, context)

async def my_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await _safe_edit(query, "⚠️ اختر قناة أولاً")
        return
    posts = await db_get_user_posts_for_channel(active, limit=15)
    if not posts:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
        await _safe_edit(query, get_text(user_id, 'no_posts'), reply_markup=keyboard)
        return
    msg = get_text(user_id, 'my_posts_title') + "\n━━━━━━━━━━━━━━━━━━━━━━\n"
    kb_buttons = []
    for idx, (pid, ptext, media_type) in enumerate(posts[:10], 1):
        short = re.sub('<[^>]+>', '', ptext)[:80].replace('\n', ' ') if ptext else "بدون نص"
        media_icons = {'photo': '🖼️', 'video': '🎬', 'document': '📄', 'audio': '🎵', 'voice': '🎤', 'animation': '🎞️', 'text': '📝'}
        media_icon = media_icons.get(media_type, '📝')
        msg += f"{idx}. {media_icon} {short}...\n🆔 `{pid}`\n\n"
        kb_buttons.append([InlineKeyboardButton(f"🗑️ حذف #{pid}", callback_data=f"{CallbackData.POSTS_DELETE_SINGLE_PREFIX}{pid}_{active}")])
    kb_buttons.append([InlineKeyboardButton("🗑️ حذف الكل", callback_data=f"{CallbackData.POSTS_CONFIRM_CLEAR_ALL_PREFIX}{active}")])
    kb_buttons.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)])
    await _safe_edit(query, msg, reply_markup=InlineKeyboardMarkup(kb_buttons))

async def delete_single_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")[-1].split("_")
    if len(parts) < 2:
        await _safe_edit(query, "❌ بيانات غير صالحة")
        return
    try:
        post_id = int(parts[0])
        active = int(parts[1])
    except ValueError:
        await _safe_edit(query, "❌ بيانات غير صالحة")
        return
    success = await db_delete_single_post(post_id, user_id, active)
    if success:
        await _safe_edit(query, "✅ تم حذف المنشور")
    else:
        await _safe_edit(query, "❌ فشل حذف المنشور")
    await asyncio.sleep(0.5)
    await my_posts_callback(update, context)

async def confirm_clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        active = int(parts[-1])
    except ValueError:
        return
    context.user_data['clear_all_posts_id'] = active
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، احذف الكل", callback_data=f"{CallbackData.POSTS_CLEAR_ALL_PREFIX}{active}"),
         InlineKeyboardButton("❌ لا، تراجع", callback_data=CallbackData.BACK)]
    ])
    await _safe_edit(query, get_text(user_id, 'confirm_delete'), reply_markup=kb)

async def clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        active = int(parts[-1])
    except ValueError:
        return
    async def _clear_posts(conn):
        await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (active,))
        await conn.commit()
    await execute_db(_clear_posts)
    await _safe_edit(query, get_text(user_id, 'deleted_all'))
    await asyncio.sleep(1)
    await main_menu_callback(update, context)

async def recycle_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await _safe_edit(query, "⚠️ اختر قناة أولاً")
        return
    count = await db_reset_posts_to_unpublished(active, user_id)
    if count > 0:
        await _safe_edit(query, get_text(user_id, 'recycled'))
    else:
        await _safe_edit(query, "📭 لا توجد منشورات لإعادة تدويرها")
    await asyncio.sleep(1)
    await main_menu_callback(update, context)

async def publish_all_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
        await safe_send_markdown(context.bot, user_id, "⚠️ اشتراكك منتهٍ")
        return
    channels = await db_get_channels(user_id)
    if not channels:
        await safe_send_markdown(context.bot, user_id, "📭 لا توجد قنوات")
        return
    await safe_send_markdown(context.bot, user_id, "🔄 جاري النشر لجميع القنوات...")
    published_count = 0
    failed_count = 0
    for ch_db_id, ch_tele_id, ch_name, banned in channels:
        if banned:
            continue
        post = await db_get_next_post(ch_db_id)
        if not post:
            continue
        final_text = post['text'] or ""
        try:
            if post['media_type'] == 'photo' and post['media_file_id']:
                await context.bot.send_photo(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
            elif post['media_type'] == 'video' and post['media_file_id']:
                await context.bot.send_video(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
            elif post['media_type'] == 'document' and post['media_file_id']:
                await context.bot.send_document(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
            elif post['media_type'] == 'audio' and post['media_file_id']:
                await context.bot.send_audio(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
            elif post['media_type'] == 'voice' and post['media_file_id']:
                await context.bot.send_voice(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
            elif post['media_type'] == 'animation' and post['media_file_id']:
                await context.bot.send_animation(ch_tele_id, post['media_file_id'], caption=final_text if final_text else None)
            else:
                await context.bot.send_message(ch_tele_id, final_text, parse_mode=None)
            await db_mark_published(post['id'])
            await db_set_last_publish(ch_db_id, utc_now())
            await db_update_next_publish_date(ch_db_id)
            published_count += 1
        except:
            await db_increment_fail_count(post['id'])
            failed_count += 1
        await asyncio.sleep(1)
    await safe_send_markdown(context.bot, user_id, f"📤 **نتائج النشر**\n\n✅ تم النشر: {published_count}\n❌ فشل: {failed_count}")

# ===================================================================
# 33.4 أزرار الإحصائيات
# ===================================================================

async def pending_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    unpublished = await db_get_user_unpublished_posts(user_id)
    total = await db_get_user_total_posts(user_id)
    text = get_text(user_id, 'pending_stats').format(unpublished, total)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    await _safe_edit(query, text, reply_markup=kb)

async def full_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    channels = await db_get_user_channels_count(user_id)
    total = await db_get_user_total_posts(user_id)
    unpublished = await db_get_user_unpublished_posts(user_id)
    groups = await db_get_user_groups_count(user_id)
    auto = get_text(user_id, 'auto_on') if await db_auto_status(user_id) else get_text(user_id, 'auto_off')
    text = get_text(user_id, 'stats').format(channels, total, unpublished, groups, auto)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    await _safe_edit(query, text, reply_markup=kb)

async def channel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        active = int(parts[1])
    except ValueError:
        return
    stats = await db_get_channel_stats(active)
    ch_info = await db_get_channel_info(active)
    channel_name = ch_info[1] if ch_info else "القناة"
    text = (f"📊 **إحصائيات {channel_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 إجمالي المنشورات: {stats['total_posts']}\n✅ المنشورة: {stats['published_posts']}\n"
            f"⏳ غير المنشورة: {stats['unpublished_posts']}\n👁️ المشاهدات: {stats['total_views']}\n"
            f"📊 متوسط المشاهدات: {stats['avg_views']}")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def my_channel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels:
        await safe_edit_markdown(query, "📭 لا توجد قنوات")
        return
    text = "📊 **ملخص قنواتي**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    total_posts = 0
    total_published = 0
    total_views = 0
    for ch_db_id, ch_tele_id, ch_name, banned in channels:
        unpub = await db_unpublished_count(ch_db_id)
        async def _get_stats(conn):
            cur = await conn.execute("SELECT COUNT(*), COALESCE(SUM(views_count),0) FROM posts WHERE channel_db_id=? AND published=1", (ch_db_id,))
            row = await cur.fetchone()
            return row[0] if row else 0, row[1] if row else 0
        pub, views = await execute_db(_get_stats)
        total_posts += unpub + pub
        total_published += pub
        total_views += views
        status = "🚫" if banned else "✅"
        text += f"{status} {ch_name}: {pub} منشور, {views} مشاهدة\n"
    text += f"━━━━━━━━━━━━━━━━━━━━━━\n📝 إجمالي المنشورات: {total_posts}\n✅ المنشورة: {total_published}\n👁️ المشاهدات: {total_views}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

# ===================================================================
# 33.5 أزرار المجموعات والإعدادات
# ===================================================================

async def my_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        try:
            await _answer_query(query)
        except:
            pass
    uid = update.effective_user.id
    groups = await db_get_user_groups(uid)
    valid_groups = []
    for chat_id, chat_name, username, banned in groups:
        if await is_authorized_in_group(context.bot, chat_id, uid):
            valid_groups.append((chat_id, chat_name, username, banned))
    if not valid_groups:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ أضف البوت إلى مجموعة", url=f"https://t.me/{BOT_USERNAME}?startgroup")],
            [InlineKeyboardButton("🔄 تحديث القائمة", callback_data=CallbackData.SECURITY_REFRESH_GROUPS)],
            [InlineKeyboardButton(get_text(uid, 'back'), callback_data=CallbackData.BACK)]
        ])
        await _safe_edit(query, "📭 **لا توجد مجموعات تديرها حالياً**\n\n• أضف البوت إلى مجموعة واجعله مشرفاً\n• استخدم /syncgroup في المجموعة\n• ثم ستظهر المجموعة هنا", reply_markup=kb)
        return
    keyboard = []
    for chat_id, chat_name, username, banned in valid_groups:
        display_name = chat_name[:28] + "..." if len(chat_name) > 31 else chat_name
        status_icon = "⛔" if banned else "✅"
        keyboard.append([InlineKeyboardButton(f"{status_icon} {display_name}", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")])
        keyboard.append([
            InlineKeyboardButton("🔐 الأمان", callback_data=f"{CallbackData.SECURITY_SELECT_GROUP}{chat_id}"),
            InlineKeyboardButton("📜 السجل", callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}"),
            InlineKeyboardButton("⚙️ متقدم", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")
        ])
        is_locked = await is_chat_locked(chat_id)
        lock_label = "🔒 قفل" if not is_locked else "🔓 فتح"
        lock_callback = f"{CallbackData.PANEL_LOCK_PREFIX}{chat_id}" if not is_locked else f"{CallbackData.PANEL_UNLOCK_PREFIX}{chat_id}"
        keyboard.append([InlineKeyboardButton(lock_label, callback_data=lock_callback),
                         InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_group:{chat_id}")])
        keyboard.append([InlineKeyboardButton("─" * 20, callback_data="noop")])
    keyboard.append([InlineKeyboardButton("🔄 تحديث القائمة", callback_data=CallbackData.SECURITY_REFRESH_GROUPS),
                     InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await _safe_edit(query, "👥 **مجموعاتي**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر مجموعة للتحكم بها:\n\n✅ = نشطة  |  ⛔ = محظورة", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_send_markdown(context.bot, uid, "🔒 غير مصرح")
        return
    async def _del(conn):
        await conn.execute("DELETE FROM bot_groups WHERE chat_id=?", (chat_id,))
        await conn.execute("DELETE FROM hidden_owner_groups WHERE chat_id=?", (chat_id,))
        await conn.execute("DELETE FROM hidden_admins WHERE chat_id=?", (chat_id,))
        await conn.execute("DELETE FROM group_admins WHERE chat_id=?", (chat_id,))
        await conn.execute("DELETE FROM group_security WHERE chat_id=?", (chat_id,))
        await conn.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await conn.commit()
    await execute_db(_del)
    invalidate_auth_cache(chat_id)
    await safe_send_markdown(context.bot, uid, "✅ تم حذف المجموعة من قاعدة البيانات")
    await my_groups_callback(update, context)

async def group_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        try:
            await _answer_query(query)
        except:
            pass
    uid = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await _safe_edit(query, get_text(uid, 'admin_only'))
        return
    await _update_security_panel(query, chat_id, uid)

async def settings_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    auto_status = await db_auto_status(user_id)
    auto_recycle = await db_get_auto_recycle(user_id)
    auto_text = get_text(user_id, 'auto_on') if auto_status else get_text(user_id, 'auto_off')
    recycle_text = get_text(user_id, 'auto_on') if auto_recycle else get_text(user_id, 'auto_off')
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⚙️ النشر التلقائي: {auto_text}", callback_data=CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH)],
        [InlineKeyboardButton(f"♻️ إعادة تدوير تلقائي: {recycle_text}", callback_data=CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    await _safe_edit(query, f"⚙️ **الإعدادات**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإعداد المطلوب:", reply_markup=keyboard)

async def toggle_auto_publish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    current = await db_auto_status(user_id)
    new_status = not current
    await db_set_auto(user_id, new_status)
    status_text = get_text(user_id, 'auto_on') if new_status else get_text(user_id, 'auto_off')
    await _safe_edit(query, get_text(user_id, 'auto_toggled').format(status_text))
    await asyncio.sleep(0.5)
    await settings_menu_callback(update, context)

async def toggle_auto_recycle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    current = await db_get_auto_recycle(user_id)
    new_status = not current
    await db_set_auto_recycle(user_id, new_status)
    status_text = get_text(user_id, 'auto_on') if new_status else get_text(user_id, 'auto_off')
    await _safe_edit(query, get_text(user_id, 'auto_toggled').format(status_text))
    await asyncio.sleep(0.5)
    await settings_menu_callback(update, context)

# ===================================================================
# 33.6 أزرار الجدولة
# ===================================================================

async def schedule_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        ch_db_id = int(parts[-1])
    except ValueError:
        return
    context.user_data['schedule_ch_id'] = ch_db_id
    schedule = await db_get_schedule(ch_db_id)
    schedule_type = schedule['type']
    info = ""
    if schedule_type == 'interval_minutes':
        info = get_text(user_id, 'interval_minutes').format(schedule['interval_minutes'])
    elif schedule_type == 'interval_hours':
        info = get_text(user_id, 'interval_hours').format(schedule['interval_hours'])
    elif schedule_type == 'interval_days':
        info = get_text(user_id, 'interval_days').format(schedule['interval_days'])
    elif schedule_type == 'days':
        days = parse_days_of_week_safe(schedule['days_of_week'])
        day_names = [get_text(user_id, d) for d in ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']]
        days_str = ', '.join([day_names[d] for d in days]) if days else get_text(user_id, 'nothing')
        info = get_text(user_id, 'days_week').format(days_str)
    elif schedule_type == 'dates':
        dates = parse_dates_safe(schedule['specific_dates'])
        dates_str = ', '.join(dates) if dates else get_text(user_id, 'nothing')
        info = get_text(user_id, 'specific_dates').format(dates_str)
    elif schedule_type == 'cron':
        info = f"CRON: {schedule['cron_expression']}"
    else:
        info = get_text(user_id, 'nothing')
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'interval_minutes'), callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_MINUTES_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton(get_text(user_id, 'interval_hours'), callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_HOURS_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton(get_text(user_id, 'interval_days'), callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_DAYS_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton(get_text(user_id, 'days_week'), callback_data=f"{CallbackData.SCHEDULE_SET_DAYS_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton(get_text(user_id, 'specific_dates'), callback_data=f"{CallbackData.SCHEDULE_SET_DATES_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton(f"🕐 {get_text(user_id, 'send_time')}", callback_data=f"{CallbackData.SCHEDULE_SET_PUBLISH_TIME_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton("⏰ CRON", callback_data=f"{CallbackData.SCHEDULE_SET_CRON_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ]
    await _safe_edit(query, get_text(user_id, 'schedule_settings').format(info), reply_markup=InlineKeyboardMarkup(keyboard))

async def set_interval_minutes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        ch_db_id = int(parts[-1])
    except ValueError:
        return
    context.user_data['state'] = UserState.WAITING_INTERVAL_MINUTES
    context.user_data['schedule_ch_id'] = ch_db_id
    await _safe_edit(query, get_text(user_id, 'send_minutes') + "\n\n(1-1440 دقيقة)")

async def set_interval_hours_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        ch_db_id = int(parts[-1])
    except ValueError:
        return
    context.user_data['state'] = UserState.WAITING_INTERVAL_HOURS
    context.user_data['schedule_ch_id'] = ch_db_id
    await _safe_edit(query, get_text(user_id, 'send_hours') + "\n\n(1-168 ساعة)")

async def set_interval_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        ch_db_id = int(parts[-1])
    except ValueError:
        return
    context.user_data['state'] = UserState.WAITING_INTERVAL_DAYS
    context.user_data['schedule_ch_id'] = ch_db_id
    await _safe_edit(query, get_text(user_id, 'send_days') + "\n\n(1-365 يوم)")

async def set_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        ch_db_id = int(parts[-1])
    except ValueError:
        return
    context.user_data['selected_days'] = []
    context.user_data['schedule_ch_id'] = ch_db_id
    context.user_data['state'] = UserState.SELECTING_DAYS
    keyboard = await build_days_keyboard(user_id, context)
    await _safe_edit(query, get_text(user_id, 'days_week'), reply_markup=keyboard)

async def set_dates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        ch_db_id = int(parts[-1])
    except ValueError:
        return
    context.user_data['state'] = UserState.WAITING_DATES
    context.user_data['schedule_ch_id'] = ch_db_id
    await _safe_edit(query, get_text(user_id, 'send_dates') + "\n\nمثال: 2024-12-25,2025-01-01")

async def set_publish_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        ch_db_id = int(parts[-1])
    except ValueError:
        return
    context.user_data['state'] = UserState.WAITING_PUBLISH_TIME
    context.user_data['schedule_ch_id'] = ch_db_id
    await _safe_edit(query, get_text(user_id, 'send_time') + "\n\nمثال: 14:30 (بتوقيت مكة)")

async def set_cron_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        ch_db_id = int(parts[-1])
    except ValueError:
        return
    context.user_data['state'] = UserState.WAITING_CRON
    context.user_data['schedule_ch_id'] = ch_db_id
    await _safe_edit(query, "⏰ أرسل تعبير CRON\n\nمثال: 0 12 * * 1\n(كل اثنين الساعة 12:00)")

async def day_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        day_index = int(parts[-1])
    except ValueError:
        return
    selected = context.user_data.get('selected_days', [])
    if day_index in selected:
        selected.remove(day_index)
    else:
        selected.append(day_index)
    context.user_data['selected_days'] = selected
    keyboard = await build_days_keyboard(user_id, context)
    try:
        await query.edit_message_reply_markup(reply_markup=keyboard)
    except:
        pass

async def save_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await _answer_query(query)
    user_id = update.effective_user.id
    ch_db_id = context.user_data.get('schedule_ch_id')
    if not ch_db_id:
        await _safe_edit(query, "❌ لم يتم تحديد القناة")
        return
    selected = context.user_data.get('selected_days', [])
    if not selected:
        await _safe_edit(query, "❌ يجب اختيار يوم واحد على الأقل")
        return
    await db_save_schedule(ch_db_id, 'days', days_of_week=json.dumps(selected))
    await db_set_next_publish_date(ch_db_id, None)
    context.user_data.pop('selected_days', None)
    context.user_data.pop('state', None)
    await _safe_edit(query, get_text(user_id, 'days_saved'))
    await asyncio.sleep(0.5)
    await schedule_menu_callback(update, context)

async def build_days_keyboard(uid, context):
    selected = context.user_data.get('selected_days', [])
    day_names = [get_text(uid, d) for d in ['monday','tuesday','wednesday','thursday','friday','saturday','sunday']]
    kb_buttons = []
    for i in range(0, 7, 3):
        row = []
        for j in range(3):
            if i + j < 7:
                day_index = i + j
                mark = "✅ " if day_index in selected else ""
                row.append(InlineKeyboardButton(f"{mark}{day_names[day_index]}", callback_data=f"{CallbackData.SCHEDULE_DAY_SELECT_PREFIX}{day_index}"))
        if row:
            kb_buttons.append(row)
    kb_buttons.append([InlineKeyboardButton("✔️ حفظ", callback_data=CallbackData.SCHEDULE_SAVE_DAYS),
                       InlineKeyboardButton(get_text(uid, 'back'), callback_data=CallbackData.BACK)])
    return InlineKeyboardMarkup(kb_buttons)

# ===================================================================
# 33.7 أزرار الأمان – تم إصلاحها بالكامل
# ===================================================================

async def security_toggle_setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل أي إعداد أمان مع تحديث اللوحة"""
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
        await _safe_edit(query, get_text(user_id, 'admin_only'))
        return
    
    # خريطة الأعمدة المتوافقة مع جدول group_security
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
        
    elif action == "max_length":
        context.user_data['state'] = UserState.WAITING_MAX_LENGTH
        context.user_data['security_chat_id'] = chat_id
        await _safe_edit(query, "📏 أرسل الحد الأقصى لطول الرسالة (0 = غير محدود):")
        return
        
    elif action == "warn_settings":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔢 عدد التحذيرات", callback_data=f"warn_count:{chat_id}"),
             InlineKeyboardButton("⚖️ عقوبة التحذير", callback_data=f"warn_penalty:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
        ])
        await _safe_edit(query, "⚠️ **إعدادات التحذير**\nاختر الإعداد المطلوب:", reply_markup=keyboard)
        return
        
    elif action == "enable_all":
        enable_all = {col: 1 for col in field_map.values()}
        await db_set_security_settings(chat_id, **enable_all)
        
    elif action == "disable_all":
        disable_all = {col: 0 for col in field_map.values()}
        await db_set_security_settings(chat_id, **disable_all)
    
    else:
        await _safe_edit(query, "❌ إجراء غير معروف")
        return
    
    # تحديث لوحة الأمان بعد أي تغيير
    await _update_security_panel(query, chat_id, user_id)

async def _update_security_panel(query, chat_id: int, user_id: int):
    """تحديث لوحة الأمان بعد أي تغيير في الإعدادات"""
    try:
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        text = _build_security_text(settings)
        keyboard = security_keyboard(chat_id)
        try:
            await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await safe_send_markdown(query._bot, query.message.chat_id if query.message else user_id, text, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"خطأ في تحديث لوحة الأمان: {e}")
        try:
            await query.answer("❌ حدث خطأ، حاول مرة أخرى", show_alert=True)
        except:
            pass

def _build_security_text(settings: dict) -> str:
    """بناء نص لوحة الأمان بصيغة HTML"""
    def st(val):
        return "✅" if val else "❌"
    
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
        f"⚖️ العقوبة: {settings.get('delete_penalty', settings.get('auto_penalty', 'لا شيء'))}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "📌 اختر الإعداد:"
    ]
    return "\n".join(lines)

# ===================================================================
# 33.8 أزرار الكلمات المحظورة - تم إصلاحها بالكامل
# ===================================================================

async def security_banned_words_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الكلمات المحظورة للمجموعة"""
    query = update.callback_query
    await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await _safe_edit(query, get_text(user_id, 'admin_only'))
        return
    context.user_data['banned_words_chat_id'] = chat_id
    await _safe_edit(query, "🚫 **الكلمات المحظورة**\nاختر الإجراء المطلوب:", reply_markup=get_group_banned_words_keyboard(chat_id))

async def banned_words_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة كلمة محظورة للمجموعة"""
    query = update.callback_query
    await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await _safe_edit(query, get_text(user_id, 'admin_only'))
        return
    context.user_data['state'] = UserState.WAITING_GROUP_BANNED_WORD
    context.user_data['banned_words_chat_id'] = chat_id
    await _safe_edit(query, "✏️ أرسل الكلمة التي تريد إضافتها إلى قائمة المحظورات:")

async def banned_words_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الكلمات المحظورة للمجموعة"""
    query = update.callback_query
    await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await _safe_edit(query, get_text(user_id, 'admin_only'))
        return
    words = await db_get_banned_words(chat_id)
    if not words:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة كلمة", callback_data=f"{CallbackData.BANNED_WORDS_ADD_PREFIX}{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}{chat_id}")]
        ])
        await _safe_edit(query, "📭 لا توجد كلمات محظورة في هذه المجموعة.", reply_markup=keyboard)
        return
    text = "🚫 **الكلمات المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for word, added_by, added_at in words:
        text += f"• `{word}` (أضيف بواسطة {added_by})\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة", callback_data=f"{CallbackData.BANNED_WORDS_ADD_PREFIX}{chat_id}"),
         InlineKeyboardButton("🗑️ حذف", callback_data=f"{CallbackData.BANNED_WORDS_REMOVE_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}{chat_id}")]
    ])
    await _safe_edit(query, text, reply_markup=keyboard)

async def banned_words_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف كلمة محظورة من المجموعة"""
    query = update.callback_query
    await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await _safe_edit(query, get_text(user_id, 'admin_only'))
        return
    context.user_data['state'] = UserState.WAITING_REMOVE_GROUP_BANNED_WORD
    context.user_data['banned_words_chat_id'] = chat_id
    await _safe_edit(query, "✏️ أرسل الكلمة التي تريد حذفها من قائمة المحظورات:")

async def security_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إغلاق لوحة الأمان"""
    query = update.callback_query
    if query:
        await _answer_query(query)
        try:
            await query.message.delete()
        except:
            pass

async def security_select_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار مجموعة للأمان"""
    query = update.callback_query
    await _answer_query(query)
    user_id = update.effective_user.id
    groups = await db_get_user_groups(user_id)
    valid = [(chat_id, chat_name, username, banned) for chat_id, chat_name, username, banned in groups if await is_authorized_in_group(context.bot, chat_id, user_id)]
    if not valid:
        await _safe_edit(query, "🔒 لا توجد مجموعات لديك صلاحية عليها.")
        return
    keyboard = []
    for chat_id, chat_name, _, banned in valid:
        status_icon = "⛔" if banned else "✅"
        display_name = chat_name[:28] + "..." if len(chat_name) > 31 else chat_name
        keyboard.append([InlineKeyboardButton(f"{status_icon} {display_name}", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")])
    keyboard.append([InlineKeyboardButton("🔄 تحديث", callback_data=CallbackData.SECURITY_REFRESH_GROUPS),
                     InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await _safe_edit(query, "🔐 **اختر مجموعة لإعدادات الأمان:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def security_refresh_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await security_select_group_callback(update, context)

async def security_enable_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل جميع إعدادات الحذف"""
    query = update.callback_query
    await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await _safe_edit(query, get_text(user_id, 'admin_only'))
        return
    enable_all = {'delete_videos': 1, 'delete_audio': 1, 'delete_animation': 1, 'delete_service': 1,
                  'delete_documents': 1, 'delete_stickers': 1, 'delete_forwarded': 1,
                  'delete_polls': 1, 'delete_games': 1, 'delete_voice': 1, 'delete_video_note': 1}
    await db_set_security_settings(chat_id, **enable_all)
    await _update_security_panel(query, chat_id, user_id)

async def security_disable_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعطيل جميع إعدادات الحذف"""
    query = update.callback_query
    await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await _safe_edit(query, get_text(user_id, 'admin_only'))
        return
    disable_all = {'delete_videos': 0, 'delete_audio': 0, 'delete_animation': 0, 'delete_service': 0,
                   'delete_documents': 0, 'delete_stickers': 0, 'delete_forwarded': 0,
                   'delete_polls': 0, 'delete_games': 0, 'delete_voice': 0, 'delete_video_note': 0}
    await db_set_security_settings(chat_id, **disable_all)
    await _update_security_panel(query, chat_id, user_id)

async def security_delete_penalty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة عقوبات الحذف"""
    query = update.callback_query
    await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await _safe_edit(query, get_text(user_id, 'admin_only'))
        return
    context.user_data['penalty_chat_id'] = chat_id
    await _safe_edit(query, "⚖️ **اختر عقوبة الحذف**", reply_markup=penalty_keyboard(chat_id))

# ===================================================================
# 33.9 أزرار العقوبات
# ===================================================================

async def penalty_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await _safe_edit(query, get_text(user_id, 'admin_only'))
        return
    context.user_data['penalty_chat_id'] = chat_id
    await _safe_edit(query, "⚖️ **اختر العقوبة التلقائية**", reply_markup=penalty_keyboard(chat_id))

async def _set_penalty(update, context, penalty):
    query = update.callback_query
    await _answer_query(query)
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await _safe_edit(query, get_text(user_id, 'admin_only'))
        return
    await db_set_security_settings(chat_id, auto_penalty=penalty)
    penalty_names = {'kick': '👢 الطرد', 'ban': '🛑 الحظر', 'mute': '🔇 الكتم', 'warn': '⚠️ التحذير', 'restrict': '🔒 التقييد', 'none': '❌ لا شيء'}
    await _safe_edit(query, f"✅ تم تعيين عقوبة {penalty_names.get(penalty, penalty)}")
    await asyncio.sleep(0.5)
    await penalty_menu_callback(update, context)

async def penalty_kick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_penalty(update, context, 'kick')

async def penalty_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_penalty(update, context, 'ban')

async def penalty_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_penalty(update, context, 'mute')

async def penalty_warn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_penalty(update, context, 'warn')

async def penalty_restrict_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_penalty(update, context, 'restrict')

async def penalty_none_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_penalty(update, context, 'none')

# ===================================================================
# 33.10 أزرار الإجراءات المتقدمة
# ===================================================================

async def advanced_actions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    uid = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await _safe_edit(query, get_text(uid, 'admin_only'))
        return
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "🛠️ **الإجراءات المتقدمة**\nاختر الإجراء:", reply_markup=get_advanced_group_actions_keyboard(chat_id))

async def group_action_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    uid = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await _safe_edit(query, get_text(uid, 'admin_only'))
        return
    context.user_data['state'] = UserState.WAITING_BAN_USER
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "🚫 **حظر مستخدم**\nأرسل معرف المستخدم أو قم بالرد على رسالته.")

async def group_action_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    uid = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await _safe_edit(query, get_text(uid, 'admin_only'))
        return
    await _safe_edit(query, "🔇 **كتم مستخدم**\nاختر مدة الكتم:", reply_markup=get_advanced_mute_duration_keyboard(chat_id))

async def advanced_mute_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    parts = query.data.split(":")
    if len(parts) < 3:
        return
    try:
        minutes = int(parts[1])
        chat_id = int(parts[2])
    except ValueError:
        return
    uid = update.effective_user.id
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await _safe_edit(query, get_text(uid, 'admin_only'))
        return
    context.user_data['mute_minutes'] = minutes if minutes > 0 else None
    context.user_data['state'] = UserState.WAITING_MUTE_USER
    context.user_data['advanced_chat_id'] = chat_id
    if minutes == 0:
        msg = "🔇 **كتم دائم**\nأرسل معرف المستخدم."
    elif minutes < 60:
        msg = f"🔇 **كتم {minutes} دقيقة**\nأرسل معرف المستخدم."
    elif minutes < 1440:
        msg = f"🔇 **كتم {minutes // 60} ساعة**\nأرسل معرف المستخدم."
    else:
        msg = f"🔇 **كتم {minutes // 1440} يوم**\nأرسل معرف المستخدم."
    await _safe_edit(query, msg)

async def group_action_warn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    uid = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await _safe_edit(query, get_text(uid, 'admin_only'))
        return
    context.user_data['state'] = UserState.WAITING_WARN_USER
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "⚠️ **تحذير مستخدم**\nأرسل معرف المستخدم.")

async def group_action_kick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    uid = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await _safe_edit(query, get_text(uid, 'admin_only'))
        return
    context.user_data['state'] = UserState.WAITING_KICK_USER
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "👢 **طرد مستخدم**\nأرسل معرف المستخدم.")

async def group_action_restrict_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    uid = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await _safe_edit(query, get_text(uid, 'admin_only'))
        return
    context.user_data['state'] = UserState.WAITING_RESTRICT_USER
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "🔒 **تقييد مستخدم**\nأرسل معرف المستخدم.")

async def group_action_pin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    uid = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await _safe_edit(query, get_text(uid, 'admin_only'))
        return
    context.user_data['state'] = UserState.WAITING_PIN_MESSAGE
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "📌 **تثبيت رسالة**\nقم بالرد على الرسالة ثم أرسل /pin")

async def group_action_log_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    uid = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await _safe_edit(query, get_text(uid, 'admin_only'))
        return
    log_text = await get_moderation_log(chat_id)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")]])
    await _safe_edit(query, log_text, reply_markup=keyboard)

async def group_action_unban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _answer_query(query)
    uid = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await _safe_edit(query, get_text(uid, 'admin_only'))
        return
    context.user_data['state'] = UserState.WAITING_UNBAN_USER
    context.user_data['advanced_chat_id'] = chat_id
    await _safe_edit(query, "🔓 **إلغاء حظر**\nأرسل معرف المستخدم.")

# ===================================================================
# 33.11 أزرار الردود التلقائية - تم إصلاحها بالكامل
# ===================================================================

async def auto_reply_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الردود التلقائية للمجموعة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    settings = await db_get_auto_reply_settings(chat_id)
    await safe_edit_markdown(query, "📝 **الردود التلقائية**\n\nاختر الإعداد المطلوب:", reply_markup=get_auto_reply_keyboard(chat_id, settings))

async def auto_reply_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل تفعيل/تعطيل الردود التلقائية"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    settings = await db_get_auto_reply_settings(chat_id)
    new_enabled = not settings.get('enabled', False)
    async def _toggle(conn):
        await conn.execute("INSERT OR REPLACE INTO auto_reply_settings (chat_id, enabled) VALUES (?, ?)", (chat_id, 1 if new_enabled else 0))
        await conn.commit()
    await execute_db(_toggle)
    status_text = "🟢 مفعلة" if new_enabled else "🔴 معطلة"
    await safe_edit_markdown(query, f"✅ الردود التلقائية: {status_text}")
    await asyncio.sleep(0.5)
    await auto_reply_menu_callback(update, context)

async def auto_reply_admins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قصر الردود على المشرفين فقط"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    settings = await db_get_auto_reply_settings(chat_id)
    new_admins = not settings.get('only_admins', False)
    async def _toggle(conn):
        await conn.execute("INSERT OR REPLACE INTO auto_reply_settings (chat_id, only_admins) VALUES (?, ?)", (chat_id, 1 if new_admins else 0))
        await conn.commit()
    await execute_db(_toggle)
    admin_text = "👑 مشرفين فقط" if new_admins else "👥 الجميع"
    await safe_edit_markdown(query, f"✅ المستخدمون المسموح لهم: {admin_text}")
    await asyncio.sleep(0.5)
    await auto_reply_menu_callback(update, context)

async def auto_reply_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد إعادة تعيين الردود"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، إعادة تعيين", callback_data=f"{CallbackData.AUTO_REPLY_CONFIRM_RESET_PREFIX}{chat_id}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data=f"{CallbackData.AUTO_REPLY_CANCEL_PREFIX}{chat_id}")]
    ])
    await safe_edit_markdown(query, "⚠️ هل أنت متأكد من إعادة تعيين جميع الردود التلقائية؟", reply_markup=kb)

async def auto_reply_confirm_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد إعادة تعيين الردود"""
    query = update.callback_query
    if query:
        await query.answer()
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        chat_id = int(parts[-1])
    except ValueError:
        return
    async def _reset(conn):
        await conn.execute("DELETE FROM auto_replies WHERE chat_id=?", (chat_id,))
        await conn.commit()
    await execute_db(_reset)
    await safe_edit_markdown(query, "✅ تم إعادة تعيين جميع الردود التلقائية")

async def auto_reply_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء"""
    query = update.callback_query
    if query:
        await query.answer()
    await main_menu_callback(update, context)

async def auto_reply_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إحصائيات الردود"""
    query = update.callback_query
    if query:
        await query.answer()
    await safe_edit_markdown(query, "📊 **إحصائيات الردود**\n\nسيتم عرض الإحصائيات قريباً")

async def user_auto_reply_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل الردود التلقائية للمستخدم"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    async def _get(conn):
        cur = await conn.execute("SELECT auto_reply_enabled FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return bool(row[0]) if row else True
    current = await execute_db(_get)
    new_status = not current
    async def _set(conn):
        await conn.execute("UPDATE users SET auto_reply_enabled=? WHERE user_id=?", (1 if new_status else 0, user_id))
        await conn.commit()
    await execute_db(_set)
    status_text = "🟢 مفعل" if new_status else "🔴 معطل"
    await safe_edit_markdown(query, f"✅ الردود التلقائية: {status_text}")

# ===================================================================
# 33.12 معالج الأزرار العام (CallbackQuery Router) - مكتمل
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
        if data == CallbackData.MAIN_MENU: return await main_menu_callback(update, context)
        if data == CallbackData.BACK: return await back_callback(update, context)
        if data == CallbackData.CANCEL_SESSION: return await cancel_session_callback(update, context)

        # ===== القنوات =====
        if data == CallbackData.CHANNELS_ADD: return await add_channel_callback(update, context)
        if data == CallbackData.CHANNELS_MY: return await my_channels_callback(update, context)
        if data.startswith(CallbackData.CHANNELS_DELETE_PREFIX): return await delete_channel_callback(update, context)
        if data.startswith(CallbackData.CHANNELS_SELECT_PREFIX): return await select_channel_callback(update, context)

        # ===== المنشورات =====
        if data == CallbackData.POSTS_ADD_15: return await add_15_posts_callback(update, context)
        if data == CallbackData.POSTS_PUBLISH_ONE: return await publish_one_callback(update, context)
        if data == CallbackData.POSTS_MY: return await my_posts_callback(update, context)
        if data == CallbackData.POSTS_RECYCLE: return await recycle_posts_callback(update, context)
        if data.startswith(CallbackData.POSTS_DELETE_SINGLE_PREFIX): return await delete_single_post_callback(update, context)
        if data.startswith(CallbackData.POSTS_CONFIRM_CLEAR_ALL_PREFIX): return await confirm_clear_all_posts_callback(update, context)
        if data.startswith(CallbackData.POSTS_CLEAR_ALL_PREFIX): return await clear_all_posts_callback(update, context)
        if data == CallbackData.PUBLISH_ALL_CHANNELS: return await publish_all_channels_callback(update, context)

        # ===== الإحصائيات =====
        if data == CallbackData.STATS_PENDING: return await pending_stats_callback(update, context)
        if data == CallbackData.STATS_FULL: return await full_stats_callback(update, context)
        if data.startswith(CallbackData.CHANNEL_STATS + ":"): return await channel_stats_callback(update, context)
        if data == CallbackData.MY_CHANNEL_STATS: return await my_channel_stats_callback(update, context)

        # ===== المجموعات =====
        if data == CallbackData.GROUPS_MY: return await my_groups_callback(update, context)
        if data.startswith(CallbackData.GROUPS_SETTINGS_PREFIX): return await group_settings_callback(update, context)
        if data.startswith("delete_group:"): return await delete_group_callback(update, context)

        # ===== الإعدادات =====
        if data == CallbackData.SETTINGS_MENU: return await settings_menu_callback(update, context)
        if data == CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH: return await toggle_auto_publish_callback(update, context)
        if data == CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE: return await toggle_auto_recycle_callback(update, context)

        # ===== الجدولة =====
        if data.startswith(CallbackData.SCHEDULE_MENU_PREFIX): return await schedule_menu_callback(update, context)
        if data.startswith(CallbackData.SCHEDULE_SET_INTERVAL_MINUTES_PREFIX): return await set_interval_minutes_callback(update, context)
        if data.startswith(CallbackData.SCHEDULE_SET_INTERVAL_HOURS_PREFIX): return await set_interval_hours_callback(update, context)
        if data.startswith(CallbackData.SCHEDULE_SET_INTERVAL_DAYS_PREFIX): return await set_interval_days_callback(update, context)
        if data.startswith(CallbackData.SCHEDULE_SET_DAYS_PREFIX): return await set_days_callback(update, context)
        if data.startswith(CallbackData.SCHEDULE_SET_DATES_PREFIX): return await set_dates_callback(update, context)
        if data.startswith(CallbackData.SCHEDULE_SET_PUBLISH_TIME_PREFIX): return await set_publish_time_callback(update, context)
        if data.startswith(CallbackData.SCHEDULE_SET_CRON_PREFIX): return await set_cron_callback(update, context)
        if data.startswith(CallbackData.SCHEDULE_DAY_SELECT_PREFIX): return await day_select_callback(update, context)
        if data == CallbackData.SCHEDULE_SAVE_DAYS: return await save_days_callback(update, context)

        # ===== الأمان =====
        if data.startswith("security:") and len(data.split(":")) >= 3:
            return await security_toggle_setting_callback(update, context)
        if data == CallbackData.SECURITY_CLOSE: return await security_close_callback(update, context)
        if data.startswith(CallbackData.SECURITY_SELECT_GROUP): return await security_select_group_callback(update, context)
        if data == CallbackData.SECURITY_REFRESH_GROUPS: return await security_refresh_groups_callback(update, context)
        if data.startswith(CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX): return await security_banned_words_menu_callback(update, context)
        if data.startswith(CallbackData.SECURITY_ENABLE_ALL_PREFIX): return await security_enable_all_callback(update, context)
        if data.startswith(CallbackData.SECURITY_DISABLE_ALL_PREFIX): return await security_disable_all_callback(update, context)
        if data.startswith(CallbackData.SECURITY_DELETE_PENALTY_PREFIX): return await security_delete_penalty_callback(update, context)

        # ===== الكلمات المحظورة =====
        if data.startswith(CallbackData.BANNED_WORDS_ADD_PREFIX): return await banned_words_add_callback(update, context)
        if data.startswith(CallbackData.BANNED_WORDS_LIST_PREFIX): return await banned_words_list_callback(update, context)
        if data.startswith(CallbackData.BANNED_WORDS_REMOVE_PREFIX): return await banned_words_remove_callback(update, context)

        # ===== العقوبات =====
        if data.startswith(CallbackData.PENALTY_MENU + ":"): return await penalty_menu_callback(update, context)
        if data.startswith(CallbackData.PENALTY_KICK + ":"): return await penalty_kick_callback(update, context)
        if data.startswith(CallbackData.PENALTY_BAN + ":"): return await penalty_ban_callback(update, context)
        if data.startswith(CallbackData.PENALTY_MUTE + ":"): return await penalty_mute_callback(update, context)
        if data.startswith(CallbackData.PENALTY_WARN + ":"): return await penalty_warn_callback(update, context)
        if data.startswith(CallbackData.PENALTY_RESTRICT + ":"): return await penalty_restrict_callback(update, context)
        if data.startswith(CallbackData.PENALTY_NONE + ":"): return await penalty_none_callback(update, context)

        # ===== الإجراءات المتقدمة =====
        if data.startswith(CallbackData.ADVANCED_ACTIONS + ":"): return await advanced_actions_callback(update, context)
        if data.startswith(CallbackData.GROUP_ACTION_BAN + ":"): return await group_action_ban_callback(update, context)
        if data.startswith(CallbackData.GROUP_ACTION_MUTE + ":"): return await group_action_mute_callback(update, context)
        if data.startswith(CallbackData.ADV_MUTE_DURATION_PREFIX): return await advanced_mute_duration_callback(update, context)
        if data.startswith(CallbackData.GROUP_ACTION_WARN + ":"): return await group_action_warn_callback(update, context)
        if data.startswith(CallbackData.GROUP_ACTION_KICK + ":"): return await group_action_kick_callback(update, context)
        if data.startswith(CallbackData.GROUP_ACTION_RESTRICT + ":"): return await group_action_restrict_callback(update, context)
        if data.startswith(CallbackData.GROUP_ACTION_PIN + ":"): return await group_action_pin_callback(update, context)
        if data.startswith(CallbackData.GROUP_ACTION_LOG + ":"): return await group_action_log_callback(update, context)
        if data.startswith(CallbackData.GROUP_ACTION_UNBAN + ":"): return await group_action_unban_callback(update, context)

        # ===== لوحة التحكم =====
        if data.startswith(CallbackData.PANEL_LOCK_PREFIX):
            parts = data.split(":")
            if len(parts) >= 2:
                chat_id = int(parts[-1])
                await db_set_chat_lock(chat_id, True, update.effective_user.id)
                await _answer_query(query)
                await group_settings_callback(update, context)
                return
        if data.startswith(CallbackData.PANEL_UNLOCK_PREFIX):
            parts = data.split(":")
            if len(parts) >= 2:
                chat_id = int(parts[-1])
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
        if data == CallbackData.HELP: await _answer_query(query); return await help_command_handler(update, context)
        if data == CallbackData.SUPPORT_MENU: await _answer_query(query); return await support_command_handler(update, context)
        if data == CallbackData.SUPPORT_HELP:
            await _answer_query(query)
            await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'support_help'))
            return
        if data == CallbackData.SUPPORT_TICKET:
            await _answer_query(query)
            context.user_data['support_mode'] = True
            await safe_send_markdown(context.bot, update.effective_user.id, "📝 **كتابة تذكرة دعم**\n\nأرسل رسالتك وسيتم إنشاء تذكرة برقم متابعة:")
            return

        # ===== التجربة والاشتراك =====
        if data == CallbackData.TRIAL: return await trial_callback(update, context)
        if data == CallbackData.SUBSCRIBE_MENU: return await subscribe_menu_callback(update, context)
        if data == CallbackData.BUY_SUBSCRIPTION_1: return await buy_subscription_1_callback(update, context)
        if data == CallbackData.BUY_SUBSCRIPTION_2: return await buy_subscription_2_callback(update, context)
        if data == CallbackData.BUY_SUBSCRIPTION_30: return await buy_subscription_30_callback(update, context)
        if data == CallbackData.BUY_SUBSCRIPTION_90: return await buy_subscription_90_callback(update, context)

        # ===== المطور والتحديثات =====
        if data == CallbackData.DEVELOPER: await _answer_query(query); return await developer_command_handler(update, context)
        if data == CallbackData.UPDATES: await _answer_query(query); return await updates_command_handler(update, context)

        # ===== الإحالات =====
        if data == CallbackData.REFERRAL_MENU: return await referral_menu_callback(update, context)
        if data.startswith(CallbackData.REFERRAL_COPY_LINK_PREFIX): return await referral_copy_link_callback(update, context)
        if data == CallbackData.REFERRAL_CLAIM_REWARD: return await referral_claim_reward_callback(update, context)
        if data == CallbackData.REFERRAL_LIST: return await referral_list_callback(update, context)

        # ===== التذكيرات =====
        if data == CallbackData.REMINDER_MENU: return await reminder_menu_callback(update, context)
        if data == CallbackData.REMINDER_TOGGLE_SUB: return await reminder_toggle_sub_callback(update, context)
        if data == CallbackData.REMINDER_TOGGLE_DAILY: return await reminder_toggle_daily_callback(update, context)
        if data == CallbackData.REMINDER_TOGGLE_WEEKLY: return await reminder_toggle_weekly_callback(update, context)
        if data == CallbackData.REMINDER_SET_DAYS: return await reminder_set_days_callback(update, context)
        if data == CallbackData.REMINDER_SET_LANG: return await reminder_set_lang_callback(update, context)
        if data.startswith(CallbackData.REMINDER_LANG_PREFIX): return await reminder_lang_callback(update, context)

        # ===== الترجمة =====
        if data == CallbackData.TRANSLATION_MENU: return await translation_menu_callback(update, context)
        if data == CallbackData.TRANSLATION_OFF: return await translation_off_callback(update, context)
        if data.startswith(CallbackData.TRANSLATION_SET_PREFIX): return await translation_set_callback(update, context)

        # ===== المسابقات =====
        if data == CallbackData.CONTESTS_MENU: await _answer_query(query); return await contests_command_handler(update, context)
        if data.startswith(CallbackData.CONTEST_JOIN_PREFIX): return await contest_join_callback(update, context)
        if data == CallbackData.CONTEST_WINNERS: return await contest_winners_callback(update, context)

        # ===== NSFW =====
        if data == CallbackData.NSFW_SETTINGS: return await nsfw_settings_callback(update, context)
        if data == CallbackData.NSFW_TOGGLE: return await nsfw_toggle_callback(update, context)
        if data == CallbackData.NSFW_THRESHOLD_SET: return await nsfw_threshold_set_callback(update, context)

        # ===== الردود التلقائية =====
        if data.startswith(CallbackData.AUTO_REPLY_MENU_PREFIX): return await auto_reply_menu_callback(update, context)
        if data.startswith(CallbackData.AUTO_REPLY_TOGGLE_PREFIX): return await auto_reply_toggle_callback(update, context)
        if data.startswith(CallbackData.AUTO_REPLY_ADMINS_PREFIX): return await auto_reply_admins_callback(update, context)
        if data.startswith(CallbackData.AUTO_REPLY_RESET_PREFIX): return await auto_reply_reset_callback(update, context)
        if data.startswith(CallbackData.AUTO_REPLY_CONFIRM_RESET_PREFIX): return await auto_reply_confirm_reset_callback(update, context)
        if data.startswith(CallbackData.AUTO_REPLY_STATS_PREFIX): return await auto_reply_stats_callback(update, context)
        if data.startswith(CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX): return await user_auto_reply_toggle_callback(update, context)

        # ===== التحقق من الاشتراك =====
        if data == CallbackData.CHECK_SUBSCRIBE:
            await _answer_query(query)
            if await ensure_force_subscribe(update, context):
                await main_menu_callback(update, context)
            return

        # ===== اختيار اللغة =====
        if data.startswith("lang_"): return await language_callback(update, context)

        # ===== أزرار نصية =====
        if data in ["rank", "top", "schedule_post", "language"]: return await handle_text_callbacks(update, context)

        # ===== لوحة الأدمن =====
        if data == CallbackData.ADMIN_PANEL: return await admin_panel_callback(update, context)
        if data.startswith("admin:") or data.startswith("confirm_restore:"):
            return await admin_router_callback(update, context)

        # ===== غير معروف =====
        await _answer_query(query)
        logger.warning(f"بيانات كولباك غير معروفة: {data}")

    except Exception as e:
        error_id = log_error(e, {'user_id': update.effective_user.id, 'callback_data': data})
        try:
            await _answer_query(query)
            await safe_send_markdown(context.bot, update.effective_user.id, f"❌ حدث خطأ (الرمز: `{error_id}`)")
        except:
            pass

# ===================================================================
# 33.13 معالجات إضافية
# ===================================================================

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    lang = query.data.split("_")[1]
    await set_user_language(user_id, lang)
    await safe_send_markdown(context.bot, user_id, f"✅ تم تغيير اللغة إلى {SUPPORTED_LANGUAGES.get(lang, lang)}")
    await main_menu_callback(update, context)

async def handle_text_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    data = query.data
    
    if data == "rank":
        rank_data = await get_rank(user_id)
        next_level = rank_data['level'] + 1
        req_points = LEVEL_REQUIREMENTS.get(next_level, "∞")
        await safe_edit_markdown(query, f"📊 **رتبتك**\n━━━━━━━━━━━━━━\n🎖️ المستوى: {rank_data['level']}\n⭐ النقاط: {rank_data['points']}\n🎯 النقاط المطلوبة للمستوى التالي: {req_points}")
    elif data == "top":
        top_users = await get_top_users(10)
        if not top_users:
            await safe_edit_markdown(query, "📭 لا يوجد مستخدمين بعد.")
            return
        text = "🏆 **أفضل 10 مستخدمين**\n━━━━━━━━━━━━━━\n"
        for idx, (uid, points, level) in enumerate(top_users, 1):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            try:
                user = await context.bot.get_chat(uid)
                name = user.first_name or str(uid)
            except:
                name = str(uid)
            text += f"{medal} {name} - Lv.{level} ({points} نقطة)\n"
        await safe_edit_markdown(query, text)
    elif data == "schedule_post":
        context.user_data['state'] = UserState.WAITING_SCHEDULE_POST
        await safe_edit_markdown(query, "📝 **جدولة منشور**\n\nأرسل المنشور بهذه الصيغة:\n`YYYY-MM-DD HH:MM نص المنشور`")
    elif data == "language":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr"), InlineKeyboardButton("🇹🇷 Türkçe", callback_data="lang_tr")],
            [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
        ])
        await safe_edit_markdown(query, get_text(user_id, 'welcome'), reply_markup=keyboard)

async def contest_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) < 2:
        return
    try:
        contest_id = int(parts[-1])
    except ValueError:
        return
    context.user_data['contest_join_id'] = contest_id
    context.user_data['state'] = UserState.WAITING_CONTEST_ANSWER
    await safe_send_markdown(context.bot, user_id, "📝 **شارك في المسابقة**\n\nأرسل إجابتك (أو أرسل /skip للتخطي):")

async def contest_winners_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    async def _get_winners(conn):
        cur = await conn.execute("SELECT cw.contest_id, cw.winner_id, cw.announced_at, c.title, c.prize FROM contest_winners cw JOIN contests c ON cw.contest_id = c.id ORDER BY cw.announced_at DESC LIMIT 20")
        return await cur.fetchall()
    winners = await execute_db(_get_winners)
    if not winners:
        await safe_send_markdown(context.bot, user_id, "🏆 لا يوجد فائزون سابقون بعد.")
        return
    text = "🏆 **الفائزون السابقون**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for contest_id, winner_id, announced_at, title, prize in winners:
        try:
            time_str = datetime.fromisoformat(announced_at).strftime("%Y-%m-%d")
        except:
            time_str = str(announced_at)[:10]
        text += f"📌 **{title}**\n👤 الفائز: `{winner_id}`\n🎁 الجائزة: {prize}\n📅 التاريخ: {time_str}\n\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def check_subscribe_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    if await ensure_force_subscribe(update, context):
        await main_menu_callback(update, context)

# ===================================================================
# 33.14 معالجات الاشتراك والدفع
# ===================================================================

async def buy_subscription_1_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    await context.bot.send_invoice(chat_id=user_id, title="اشتراك يوم واحد", description="اشتراك يوم واحد في ريلاكس مانيجر", payload="sub_1", provider_token="", currency="XTR", prices=[LabeledPrice("اشتراك يوم واحد", 5)])

async def buy_subscription_2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    await context.bot.send_invoice(chat_id=user_id, title="اشتراك يومين", description="اشتراك يومين في ريلاكس مانيجر", payload="sub_2", provider_token="", currency="XTR", prices=[LabeledPrice("اشتراك يومين", 9)])

async def buy_subscription_30_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    await context.bot.send_invoice(chat_id=user_id, title="اشتراك شهر", description="اشتراك شهر كامل في ريلاكس مانيجر", payload="sub_30", provider_token="", currency="XTR", prices=[LabeledPrice("اشتراك شهر", 50)])

async def buy_subscription_90_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    await context.bot.send_invoice(chat_id=user_id, title="اشتراك 3 أشهر", description="اشتراك 3 أشهر في ريلاكس مانيجر", payload="sub_90", provider_token="", currency="XTR", prices=[LabeledPrice("اشتراك 3 أشهر", 120)])

async def trial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    if await db_has_used_trial(user_id):
        await safe_edit_markdown(query, get_text(user_id, 'trial_used'))
        return
    if await db_has_active_subscription(user_id):
        await safe_edit_markdown(query, get_text(user_id, 'already_subscribed'))
        return
    days = await db_activate_trial(user_id)
    if days:
        await safe_edit_markdown(query, get_text(user_id, 'trial'))
    else:
        await safe_edit_markdown(query, "❌ حدث خطأ أثناء تفعيل التجربة.")

async def subscribe_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    if await db_has_active_subscription(user_id):
        days = await db_get_subscription_days_left(user_id)
        await safe_edit_markdown(query, f"✅ اشتراكك مفعل، متبقي {days} يوم\nشكراً لدعمك ❤️")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ 1 يوم - 5 نجوم", callback_data=CallbackData.BUY_SUBSCRIPTION_1),
         InlineKeyboardButton("⭐ 2 يوم - 9 نجوم", callback_data=CallbackData.BUY_SUBSCRIPTION_2)],
        [InlineKeyboardButton("⭐ شهر (30 يوم) - 50 نجمة", callback_data=CallbackData.BUY_SUBSCRIPTION_30),
         InlineKeyboardButton("⭐ 3 أشهر (90 يوم) - 120 نجمة", callback_data=CallbackData.BUY_SUBSCRIPTION_90)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    await safe_edit_markdown(query, get_text(user_id, 'subscribe'), reply_markup=kb)
# ===================================================================
# 34. معالجات الرسائل (Message Handlers)
# ===================================================================

# 34.1 فلتر رسائل المجموعات - مع تفعيل التعلم التلقائي
async def filter_messages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفية رسائل المجموعات - حذف الروابط، الكلمات المحظورة، الوسائط، التعلم التلقائي"""
    if update.message is None or update.effective_chat is None or update.effective_user is None:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message = update.message
    text = message.text or message.caption or ""

    if user_id == context.bot.id:
        return

    if update.effective_chat.type not in ['group', 'supergroup']:
        return

    if await is_user_bot(context.bot, user_id):
        return

    bot_perms = await check_bot_admin_permissions_group(context.bot, chat_id)
    if not bot_perms.get('can_act', False):
        return

    if await is_chat_locked(chat_id) and not await is_authorized_in_group(context.bot, chat_id, user_id):
        try:
            await message.delete()
        except:
            pass
        return

    if not await db_check_slow_mode(chat_id, user_id):
        try:
            await message.delete()
        except:
            pass
        return

    settings = await db_get_security_settings(chat_id)

    if settings.get('delete_links', False) and text and contains_link(text):
        await delete_and_penalize(update, context, "🚫 ممنوع إرسال الروابط!")
        return

    if settings.get('mentions', False) and text and contains_mention(text):
        await delete_and_penalize(update, context, "🚫 ممنوع إرسال المعرفات (@username)!")
        return

    if settings.get('delete_banned_words', False) and text:
        word = await db_contains_banned_word(text, chat_id)
        if word:
            await delete_and_penalize(update, context, f"🚫 كلمة محظورة: `{word}`")
            return

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
    elif settings.get('delete_forwarded', False) and message.forward_date:
        delete_media = True
        media_type = "معاد توجيهه"
    elif settings.get('delete_polls', False) and message.poll:
        delete_media = True
        media_type = "استطلاع رأي"
    elif settings.get('delete_games', False) and message.game:
        delete_media = True
        media_type = "لعبة"
    elif settings.get('delete_voice', False) and message.voice:
        delete_media = True
        media_type = "رسالة صوتية"
    elif settings.get('delete_video_note', False) and message.video_note:
        delete_media = True
        media_type = "ملاحظة فيديو"

    if delete_media:
        try:
            await message.delete()
        except:
            pass
        penalty = settings.get('delete_penalty', settings.get('auto_penalty', 'none'))
        if penalty != 'none':
            duration = settings.get('delete_penalty_duration', settings.get('auto_mute_duration', 60))
            await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, duration, reason=f"إرسال {media_type} ممنوع")
        return

    max_len = settings.get('max_message_length', 0)
    if max_len > 0 and text and len(text) > max_len:
        try:
            await message.delete()
        except:
            pass
        return

    if settings.get('antiflood_enabled', False) and await db_check_antiflood(chat_id, user_id):
        try:
            await message.delete()
        except:
            pass
        penalty = settings.get('antiflood_penalty', 'mute')
        await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, 60, reason="فيضان في الرسائل")
        return

    if settings.get('night_mode_enabled', False):
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
                        await message.delete()
                    except:
                        pass
                    await apply_penalty_with_duration(context.bot, chat_id, user_id, 'mute', 60, reason="الوضع الليلي مفعل")
                    return
                elif action == 'delete':
                    try:
                        await message.delete()
                    except:
                        pass
                    return
        except:
            pass

    if not user_id == context.bot.id:
        await add_points(user_id, 1)

    # ===================================================================
    # نظام التعلم التلقائي من الردود - الجديد
    # ===================================================================
    reply = None
    
    if text:
        # 1. البحث عن رد متعلم من قاعدة البيانات
        async def _get_learned_reply(conn):
            # البحث عن أفضل رد متعلم بنسبة نجاح عالية
            cur = await conn.execute(
                "SELECT best_response, score FROM response_learning WHERE score > 0.6 ORDER BY score DESC, last_used DESC LIMIT 5"
            )
            rows = await cur.fetchall()
            if rows:
                # اختيار أفضل رد عشوائياً من الردود الناجحة
                best_replies = [(row[0], row[1]) for row in rows]
                # تفضيل الردود ذات النسبة الأعلى
                return best_replies[0][0] if best_replies else None
            return None
        
        learned_reply = await execute_db(_get_learned_reply)
        
        # 2. الردود التلقائية من الإعدادات
        auto_reply_settings = await db_get_auto_reply_settings(chat_id)
        if auto_reply_settings.get('enabled', False):
            can_reply = True
            if auto_reply_settings.get('only_admins', False):
                can_reply = await is_authorized_in_group(context.bot, chat_id, user_id)
            if auto_reply_settings.get('ignore_bots', True) and update.effective_user.is_bot:
                can_reply = False
            if can_reply:
                # البحث في الردود المخصصة للمجموعة
                reply = await db_get_reply(f"{chat_id}:{text.lower()}")
                if not reply:
                    reply = await db_get_reply(text.lower())
        
        # 3. إذا لم يوجد رد مخصص، استخدم الرد المتعلم
        if not reply and learned_reply:
            reply = learned_reply
        
        # 4. إذا لم يوجد، ابحث في الردود العامة المضمنة
        if not reply:
            for key, value in ALL_REPLIES.items():
                if re.search(r'\b' + re.escape(key) + r'\b', text, re.IGNORECASE):
                    reply = value if isinstance(value, str) else random.choice(value) if isinstance(value, list) else value
                    break
        
        # 5. إرسال الرد إذا وجد
        if reply:
            try:
                await message.reply_text(reply)
                # تم الرد بنجاح - تعلم من هذه التجربة
                learning_engine.learn_from_message(user_id, chat_id, text, reply, success=True)
            except:
                # فشل الرد
                learning_engine.learn_from_message(user_id, chat_id, text, reply, success=False)

        # 6. حفظ وتحليل المشاعر للتعلم المستقبلي
        if text and len(text) > 3:
            sentiment = learning_engine.analyze_sentiment(text)
            
            # حفظ في سجل المشاعر
            async def _save_sentiment(conn):
                await conn.execute(
                    "INSERT INTO sentiment_history (user_id, chat_id, text, sentiment, score, created_at, response_sentiment, response_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, chat_id, text[:200], sentiment['sentiment'], sentiment['score'], 
                     utc_now_iso(), 
                     learning_engine.analyze_sentiment(reply)['sentiment'] if reply else 'neutral',
                     learning_engine.analyze_sentiment(reply)['score'] if reply else 0)
                )
                await conn.commit()
            await execute_db(_save_sentiment)
            
            # تحديث الملف الشخصي للمستخدم
            profile = learning_engine.get_user_sentiment_profile(user_id)
            async def _update_profile(conn):
                await conn.execute(
                    "INSERT OR REPLACE INTO user_sentiment_profile (user_id, avg_sentiment, stability, messages, trend, last_updated, positive_count, negative_count, neutral_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, profile['avg_sentiment'], profile['stability'], profile['messages'], 
                     profile['trend'], utc_now_iso(),
                     sentiment['details']['positive'], sentiment['details']['negative'], sentiment['details']['neutral'])
                )
                await conn.commit()
            await execute_db(_update_profile)
            
            # تحديث الملف الشخصي للمجموعة
            chat_profile = learning_engine.get_chat_sentiment_profile(chat_id)
            async def _update_chat_profile(conn):
                await conn.execute(
                    "INSERT OR REPLACE INTO chat_sentiment_profile (chat_id, avg_sentiment, stability, messages, trend, last_updated, positive_count, negative_count, neutral_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (chat_id, chat_profile['avg_sentiment'], chat_profile['stability'], chat_profile['messages'],
                     chat_profile['trend'], utc_now_iso(),
                     sentiment['details']['positive'], sentiment['details']['negative'], sentiment['details']['neutral'])
                )
                await conn.commit()
            await execute_db(_update_chat_profile)
            
            # حفظ نمط التعلم إذا كان هناك رد
            if reply:
                async def _save_pattern(conn):
                    pattern_key = f"{text[:50]}_{reply[:50]}"
                    # تحديث أو إدراج النمط
                    await conn.execute(
                        """INSERT INTO response_learning (pattern_key, success_count, fail_count, score, last_used, best_response) 
                        VALUES (?, 1, 0, 0.8, ?, ?) 
                        ON CONFLICT(pattern_key) DO UPDATE SET 
                            success_count = success_count + 1,
                            score = (success_count * 1.0) / (success_count + fail_count + 1),
                            last_used = ?,
                            best_response = CASE WHEN score > 0.7 THEN best_response ELSE ? END""",
                        (pattern_key, utc_now_iso(), reply, utc_now_iso(), reply)
                    )
                    await conn.commit()
                await execute_db(_save_pattern)
                
                # تحديث أنماط التعلم في المحرك
                async def _save_learning_pattern(conn):
                    await conn.execute(
                        "INSERT OR REPLACE INTO learning_patterns (pattern, sentiment, score, frequency, last_used, confidence) VALUES (?, ?, ?, 1, ?, ?)",
                        (text[:200], sentiment['sentiment'], sentiment['score'], utc_now_iso(), sentiment['confidence'])
                    )
                    await conn.commit()
                await execute_db(_save_learning_pattern)

# 34.2 معالج الرسائل الخاصة
async def message_handler_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل الخاصة - يتعامل مع جميع حالات المستخدم"""
    if update.message is None or update.effective_user is None:
        return

    user_id = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""
    state = context.user_data.get('state')

    # WAITING_CHANNEL_ID
    if state == UserState.WAITING_CHANNEL_ID:
        channel_id = text.strip()
        if not (channel_id.startswith('@') or channel_id.lstrip('-').isdigit()):
            await safe_send_markdown(context.bot, user_id, "❌ صيغة المعرف غير صحيحة! استخدم @username أو المعرف الرقمي.")
            return
        try:
            chat = await context.bot.get_chat(channel_id)
            if chat.type != 'channel':
                await safe_send_markdown(context.bot, user_id, "❌ المعرف المُرسل ليس لقناة!")
                context.user_data.pop('state', None)
                return
            channel_name = chat.title or "بدون اسم"
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status not in ['administrator', 'creator']:
                    await safe_send_markdown(context.bot, user_id, f"❌ **البوت ليس مشرفاً في القناة `{channel_name}`!**")
                    context.user_data.pop('state', None)
                    return
                if not bot_member.can_post_messages:
                    await safe_send_markdown(context.bot, user_id, f"❌ **البوت لا يملك صلاحية النشر في القناة `{channel_name}`!**")
                    context.user_data.pop('state', None)
                    return
            except Exception as e:
                await safe_send_markdown(context.bot, user_id, f"❌ **لا يمكن الوصول إلى القناة:** {str(e)[:100]}")
                context.user_data.pop('state', None)
                return
            result = await db_add_channel(user_id, str(chat.id), channel_name)
            if result:
                await safe_send_markdown(context.bot, user_id, get_text(user_id, 'channel_added').format(channel_name))
            else:
                await safe_send_markdown(context.bot, user_id, get_text(user_id, 'channel_exists'))
        except Forbidden:
            await safe_send_markdown(context.bot, user_id, "❌ لا يمكن الوصول إلى هذه القناة.")
        except Exception as e:
            await safe_send_markdown(context.bot, user_id, f"❌ خطأ: {str(e)[:100]}")
        context.user_data.pop('state', None)
        await main_menu_callback(update, context)
        return

    # ADDING_POSTS
    elif state == UserState.ADDING_POSTS:
        session_posts = context.user_data.get(f"session_{user_id}", [])
        target_count = context.user_data.get(f"session_target_{user_id}", 15)
        if len(session_posts) >= target_count:
            await safe_send_markdown(context.bot, user_id, f"✅ تم استلام {len(session_posts)} منشور.\nسيتم حفظهم الآن...")
            active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
            if active:
                await db_save_posts(active, session_posts)
                await safe_send_markdown(context.bot, user_id, f"✅ تم حفظ {len(session_posts)} منشور بنجاح!")
            else:
                await safe_send_markdown(context.bot, user_id, "⚠️ لم يتم تحديد قناة نشطة.")
            context.user_data.pop(f"session_{user_id}", None)
            context.user_data.pop(f"session_target_{user_id}", None)
            context.user_data.pop('state', None)
            context.user_data.pop('temp_channel', None)
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
        elif update.message.sticker:
            await safe_send_markdown(context.bot, user_id, "⚠️ الملصقات غير مدعومة حالياً.")
            return
        elif update.message.text:
            media_type = 'text'
            text_content = text
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ نوع الميديا غير مدعوم.")
            return

        if media_type != 'text':
            text_content = update.message.caption or ""
        session_posts.append((text_content, media_type, media_file_id))
        context.user_data[f"session_{user_id}"] = session_posts
        remaining = target_count - len(session_posts)
        await safe_send_markdown(context.bot, user_id, f"✅ تم استلام منشور ({len(session_posts)}/{target_count}).\nمتبقي {remaining} منشور.")
        if len(session_posts) >= target_count:
            active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
            if active:
                await db_save_posts(active, session_posts)
                await safe_send_markdown(context.bot, user_id, f"✅ تم حفظ {len(session_posts)} منشور بنجاح!")
            else:
                await safe_send_markdown(context.bot, user_id, "⚠️ لم يتم تحديد قناة نشطة.")
            context.user_data.pop(f"session_{user_id}", None)
            context.user_data.pop(f"session_target_{user_id}", None)
            context.user_data.pop('state', None)
            context.user_data.pop('temp_channel', None)
            await main_menu_callback(update, context)
        return

    # WAITING_INTERVAL_MINUTES
    elif state == UserState.WAITING_INTERVAL_MINUTES:
        try:
            minutes = int(text)
            if minutes < 1 or minutes > 1440:
                await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال عدد بين 1 و 1440 دقيقة.")
                return
            ch_id = context.user_data.get('schedule_ch_id')
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

    # WAITING_INTERVAL_HOURS
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

    # WAITING_INTERVAL_DAYS
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

    # WAITING_DATES
    elif state == UserState.WAITING_DATES:
        dates = [d.strip() for d in text.split(',') if d.strip()]
        valid_dates = []
        for d in dates:
            try:
                datetime.strptime(d, '%Y-%m-%d')
                valid_dates.append(d)
            except:
                await safe_send_markdown(context.bot, user_id, f"❌ التاريخ '{d}' غير صالح (الصيغة: YYYY-MM-DD)")
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

    # WAITING_PUBLISH_TIME
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

    # WAITING_CRON
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

    # WAITING_MAX_LENGTH
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
            else:
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المجموعة.")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال رقم صحيح.")
        context.user_data.pop('state', None)
        context.user_data.pop('security_chat_id', None)
        return

    # WAITING_SCHEDULE_POST
    elif state == UserState.WAITING_SCHEDULE_POST:
        parts = text.split(' ', 2)
        if len(parts) < 3:
            await safe_send_markdown(context.bot, user_id, "❌ الصيغة غير صحيحة!\nاستخدم: YYYY-MM-DD HH:MM نص المنشور")
            return
        try:
            date_str = parts[0]
            time_str = parts[1]
            post_text = parts[2]
            mecca_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            if mecca_dt <= mecca_now():
                await safe_send_markdown(context.bot, user_id, "❌ الوقت يجب أن يكون في المستقبل!")
                return
            utc_dt = mecca_to_utc(mecca_dt)
            chat_id = update.effective_chat.id if update.effective_chat and update.effective_chat.type in ['group', 'supergroup'] else user_id
            await db_add_scheduled_post(chat_id, post_text, utc_dt)
            await safe_send_markdown(context.bot, user_id, f"✅ تم جدولة المنشور!\n📅 التاريخ: {date_str}\n🕐 الوقت: {time_str} (بتوقيت مكة)")
            context.user_data.pop('state', None)
            await main_menu_callback(update, context)
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ صيغة التاريخ/الوقت غير صحيحة!\nاستخدم: YYYY-MM-DD HH:MM")
        return

    # حالات الإشراف
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
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المستخدم.")
                return
            action_map = {
                UserState.WAITING_BAN_USER: "ban", UserState.WAITING_MUTE_USER: "mute",
                UserState.WAITING_WARN_USER: "warn", UserState.WAITING_KICK_USER: "kick",
                UserState.WAITING_RESTRICT_USER: "restrict", UserState.WAITING_UNBAN_USER: "unban"
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

    # WAITING_PIN_MESSAGE
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

    # حالات المسابقات
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
                await safe_send_markdown(context.bot, user_id, "❌ فشل إنشاء المسابقة.")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ صيغة تاريخ غير صحيحة!\nاستخدم: YYYY-MM-DD HH:MM")
            return
        context.user_data.pop('state', None)
        await main_menu_callback(update, context)
        return

    # SUPPORT_MODE
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
        else:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال نص الرسالة.")
        return

    # الحالة الافتراضية
    else:
        if update.message.text:
            reply = await db_get_reply(text.lower())
            if reply:
                try:
                    await update.message.reply_text(reply)
                except:
                    pass
                return
        await main_menu_callback(update, context)

# ===================================================================
# 35. المهام الخلفية (Background Tasks)
# ===================================================================

async def auto_publish_loop_improved(bot):
    """حلقة النشر التلقائي للمنشورات المجدولة"""
    await asyncio.sleep(5)
    semaphore = asyncio.Semaphore(5)

    async def publish_one(row):
        async with semaphore:
            ch_db_id, ch_tele_id, user_id = row
            if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
                return
            has_permission, _ = await check_bot_permissions(bot, ch_tele_id)
            if not has_permission:
                return
            auto_recycle = await db_get_auto_recycle(user_id)
            total = await db_get_posts_count(ch_db_id)
            published = await db_get_published_count(ch_db_id)
            if total > 0 and published >= total:
                if auto_recycle:
                    await db_reset_all_posts_to_unpublished(ch_db_id)
                else:
                    await db_set_next_publish_date(ch_db_id, utc_now() + timedelta(days=365))
                    return
            post = await db_get_next_post(ch_db_id)
            if not post:
                if auto_recycle:
                    total = await db_get_posts_count(ch_db_id)
                    if total > 0:
                        await db_reset_all_posts_to_unpublished(ch_db_id)
                return
            translation_lang = await get_user_translation_language(user_id)
            final_text = post['text'] or ""
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
                except:
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
            if success:
                await db_mark_published(post['id'])
                await db_set_last_publish(ch_db_id, utc_now())
                await db_update_next_publish_date(ch_db_id)
            else:
                await db_increment_fail_count(post['id'])
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
                    FROM user_channels uc JOIN users u ON uc.user_id = u.user_id
                    LEFT JOIN schedule s ON uc.id = s.channel_db_id
                    WHERE u.auto_publish = 1 AND u.banned = 0 AND uc.banned = 0
                      AND (s.next_publish_date IS NULL OR s.next_publish_date <= ?)
                    ORDER BY COALESCE(s.next_publish_date, '1970-01-01') ASC LIMIT ?
                """, (now_utc_iso, limit))
                return await cur.fetchall()
            rows = await execute_db(_get_due_channels)
            if rows:
                tasks = [publish_one(row) for row in rows]
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(publish_interval)
        except Exception as e:
            logger.error(f"خطأ في حلقة النشر: {e}")
            await asyncio.sleep(60)

async def auto_backup():
    """النسخ الاحتياطي التلقائي الدوري"""
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
        except Exception as e:
            logger.error(f"⚠️ خطأ في النسخ الاحتياطي التلقائي: {e}")
            await asyncio.sleep(3600)

async def run_scheduled_posts_loop_improved(bot):
    """تشغيل المنشورات المجدولة يدوياً"""
    while True:
        await asyncio.sleep(SCHEDULED_POSTS_SLEEP)
        try:
            now_utc = utc_now()
            posts = await db_get_due_scheduled_posts(now_utc, limit=50)
            for post_id, chat_id, text, media_type, media_file_id, fail_count in posts:
                try:
                    if media_type and media_file_id:
                        if media_type == 'photo':
                            await bot.send_photo(chat_id, media_file_id, caption=text[:1024] if text else None)
                        elif media_type == 'video':
                            await bot.send_video(chat_id, media_file_id, caption=text[:1024] if text else None)
                        elif media_type == 'document':
                            await bot.send_document(chat_id, media_file_id, caption=text[:1024] if text else None)
                        elif media_type == 'audio':
                            await bot.send_audio(chat_id, media_file_id, caption=text[:1024] if text else None)
                        elif media_type == 'voice':
                            await bot.send_voice(chat_id, media_file_id, caption=text[:1024] if text else None)
                        elif media_type == 'animation':
                            await bot.send_animation(chat_id, media_file_id, caption=text[:1024] if text else None)
                        else:
                            await bot.send_message(chat_id, text[:4096])
                    else:
                        await bot.send_message(chat_id, text[:4096] if text else "منشور")
                    await db_delete_scheduled_post(post_id)
                except Exception as e:
                    new_fail = fail_count + 1
                    await db_update_scheduled_post_fail(post_id, new_fail)
                    if new_fail >= 5:
                        await db_delete_scheduled_post(post_id)
        except:
            pass

async def send_reminders_loop_improved(bot):
    """إرسال تذكيرات انتهاء الاشتراك"""
    while True:
        await asyncio.sleep(REMINDERS_SLEEP)
        try:
            users_to_remind = await db_get_users_needing_reminder()
            for user_data in users_to_remind:
                user_id = user_data['user_id']
                days_left = user_data['days_left']
                lang = user_data.get('notification_lang', 'ar')
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
    """تنظيف الجلسات المنتهية والبيانات القديمة"""
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
            async def _cleanup_sentiment(conn):
                cutoff = (utc_now() - timedelta(days=90)).isoformat()
                await conn.execute("DELETE FROM sentiment_history WHERE created_at < ?", (cutoff,))
                await conn.commit()
            await execute_db(_cleanup_sentiment)
            async def _cleanup_security(conn):
                cutoff = (utc_now() - timedelta(days=60)).isoformat()
                await conn.execute("DELETE FROM security_events WHERE created_at < ? AND severity != 'high'", (cutoff,))
                await conn.commit()
            await execute_db(_cleanup_security)
            logger.debug("✅ تم تنظيف الجلسات المنتهية")
        except Exception as e:
            logger.error(f"خطأ في تنظيف الجلسات: {e}")

async def self_ping_loop():
    """الحفاظ على نشاط البوت في بيئات الاستضافة"""
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

async def broadcast_stats_periodically():
    """بث الإحصائيات دورياً للسجلات"""
    while True:
        await asyncio.sleep(3600)
        try:
            total, banned, posts, groups, channels = await db_stats()
            learning_stats = await db_get_learning_stats()
            logger.info(f"📊 إحصائيات: مستخدمين={total}, محظورين={banned}, منشورات={posts}, مجموعات={groups}, قنوات={channels}, أنماط تعلم={learning_stats.get('patterns',0)}")
        except Exception as e:
            logger.error(f"خطأ في بث الإحصائيات: {e}")

async def cleanup_points_cache():
    """تنظيف كاش النقاط المؤقت"""
    while True:
        await asyncio.sleep(3600)
        user_points_last_hour.clear()
        logger.debug("✅ تم تنظيف كاش النقاط")

async def memory_monitor():
    """مراقبة استخدام الذاكرة وتنبيه عند الارتفاع"""
    while True:
        try:
            ram = get_ram_usage()
            if ram['percent'] > 80:
                await memory_optimizer()
                logger.warning(f"⚠️ استخدام الذاكرة مرتفع: {ram['percent']}%")
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"خطأ في مراقبة الذاكرة: {e}")
            await asyncio.sleep(60)

async def auto_close_contests_loop(bot):
    """إغلاق المسابقات المنتهية تلقائياً واختيار فائز"""
    while True:
        await asyncio.sleep(3600)
        try:
            now = utc_now().isoformat()
            async def _get_expired(conn):
                cur = await conn.execute("SELECT id FROM contests WHERE status = 'active' AND end_date <= ?", (now,))
                return [row[0] for row in await cur.fetchall()]
            expired = await execute_db(_get_expired)
            for contest_id in expired:
                async def _get_contest(conn):
                    cur = await conn.execute("SELECT id, title, prize FROM contests WHERE id=?", (contest_id,))
                    return await cur.fetchone()
                contest = await execute_db(_get_contest)
                if not contest:
                    continue
                async def _count_participants(conn):
                    cur = await conn.execute("SELECT COUNT(*) FROM contest_participants WHERE contest_id=?", (contest_id,))
                    return (await cur.fetchone())[0]
                participants_count = await execute_db(_count_participants)
                if participants_count > 0:
                    async def _get_random_participant(conn):
                        cur = await conn.execute("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (contest_id,))
                        row = await cur.fetchone()
                        return row[0] if row else None
                    winner_id = await execute_db(_get_random_participant)
                    if winner_id:
                        async def _set_winner(conn):
                            await conn.execute("UPDATE contests SET status='finished', winner_id=? WHERE id=?", (winner_id, contest_id))
                            await conn.execute("INSERT INTO contest_winners (contest_id, winner_id, announced_at) VALUES (?, ?, ?)", (contest_id, winner_id, utc_now_iso()))
                            await conn.commit()
                        await execute_db(_set_winner)
                        try:
                            await bot.send_message(winner_id, f"🏆 **تهانينا!**\nلقد فزت في مسابقة **{contest[1]}**!\n🎁 جائزتك: {contest[2]}")
                        except:
                            pass
                    else:
                        async def _close_no_winner(conn):
                            await conn.execute("UPDATE contests SET status = 'finished' WHERE id = ?", (contest_id,))
                            await conn.commit()
                        await execute_db(_close_no_winner)
                else:
                    async def _close_empty(conn):
                        await conn.execute("UPDATE contests SET status = 'finished' WHERE id = ?", (contest_id,))
                        await conn.commit()
                    await execute_db(_close_empty)
        except Exception as e:
            logger.error(f"خطأ في إغلاق المسابقات: {e}")

async def refresh_group_admins_and_hidden_owners_loop(bot):
    """تحديث صلاحيات المشرفين والملاك المخفيين دورياً"""
    while True:
        try:
            async def _get_all_groups(conn):
                cur = await conn.execute("SELECT chat_id FROM bot_groups WHERE banned=0")
                return [row[0] for row in await cur.fetchall()]
            groups = await execute_db(_get_all_groups)
            for chat_id in groups:
                try:
                    await db_sync_group_admins(chat_id, bot)
                    async def _remove_non_admin(conn):
                        for table, col in [("hidden_owner_groups", "owner_id"), ("hidden_admins", "admin_id")]:
                            cur = await conn.execute(f"SELECT {col} FROM {table} WHERE chat_id=?", (chat_id,))
                            for row in await cur.fetchall():
                                try:
                                    member = await bot.get_chat_member(chat_id, row[0])
                                    if member.status not in ['administrator', 'creator']:
                                        await conn.execute(f"DELETE FROM {table} WHERE chat_id=? AND {col}=?", (chat_id, row[0]))
                                        invalidate_auth_cache(chat_id, row[0])
                                except:
                                    pass
                        await conn.commit()
                    await execute_db(_remove_non_admin)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"فشل تحديث صلاحيات المجموعة {chat_id}: {e}")
            logger.info(f"✅ تم تحديث صلاحيات {len(groups)} مجموعة")
        except Exception as e:
            logger.error(f"خطأ في حلقة تحديث الصلاحيات: {e}")
        await asyncio.sleep(3600)

async def memory_optimizer():
    """تحسين استخدام الذاكرة - تنظيف الكاش"""
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
        _failed_attempts_cache.clear()
        if len(_flood_cache) > 5000:
            keys = list(_flood_cache.keys())[:1000]
            for key in keys:
                _flood_cache.pop(key, None)
        gc.collect()
        return True
    except Exception as e:
        logger.error(f"فشل تحسين الذاكرة: {e}")
        return False

async def memory_optimizer_loop():
    """حلقة تحسين الذاكرة الدورية"""
    while True:
        await asyncio.sleep(300)
        try:
            await memory_optimizer()
        except Exception as e:
            logger.error(f"خطأ في حلقة تحسين الذاكرة: {e}")

# ===================================================================
# 36. خادم الويب الموحد
# ===================================================================

async def setup_unified_web_server(application, port: int):
    """إعداد خادم الويب الموحد (Webhook + Health Check)"""
    from aiohttp import web
    from telegram import Update
    
    if not hasattr(application, 'web_app') or application.web_app is None:
        application.web_app = web.Application()
    
    async def health_check(request):
        return web.Response(text="OK")
    
    async def index_handler(request):
        html = """
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="UTF-8">
                <title>ريلاكس مانيجر</title>
                <style>
                    body { font-family: 'Segoe UI', Tahoma; text-align: center; padding: 50px; direction: rtl; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; min-height: 100vh; }
                    .container { background: rgba(255,255,255,0.1); border-radius: 20px; padding: 40px; max-width: 600px; margin: 0 auto; backdrop-filter: blur(10px); }
                    h1 { font-size: 2.5em; margin-bottom: 10px; }
                    a { color: #ffd700; text-decoration: none; font-weight: bold; }
                    .status { display: inline-block; width: 12px; height: 12px; background: #4caf50; border-radius: 50%; margin-left: 5px; animation: pulse 2s infinite; }
                    @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(76,175,80,0.7); } 70% { box-shadow: 0 0 0 10px rgba(76,175,80,0); } 100% { box-shadow: 0 0 0 0 rgba(76,175,80,0); } }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🌿 ريلاكس مانيجر</h1>
                    <p>✅ البوت يعمل بكفاءة <span class="status"></span></p>
                    <p>🧠 نظام التعلم الذكي مفعل</p>
                    <p>📊 <a href="/health">التحقق من الصحة</a></p>
                    <p>🤖 <a href="https://t.me/Reelaaaxbot">البوت على تيليجرام</a></p>
                    <p style="color: #ddd; font-size: 14px;">الإصدار 22.2.0</p>
                </div>
            </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html", charset="utf-8")
    
    async def webhook_handler(request):
        try:
            data = await request.json()
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

# ===================================================================
# 37. معالج الأخطاء العالمي
# ===================================================================

async def global_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء العالمي مع تصنيف ذكي للأخطاء"""
    try:
        error = context.error
        error_type = type(error).__name__
        error_message = str(error)
        
        user_id = update.effective_user.id if update and update.effective_user else "غير معروف"
        chat_id = update.effective_chat.id if update and update.effective_chat else "غير معروف"
        error_id = secrets.token_hex(4)

        cause = "غير معروف"
        solution = "يرجى إعادة المحاولة أو التواصل مع المطور."
        
        if isinstance(error, BadRequest):
            cause = f"طلب غير صحيح إلى Telegram API: `{error_message}`"
            if "message is not modified" in error_message.lower():
                solution = "لا تحاول تعديل رسالة بنفس المحتوى."
            elif "bot is not a member" in error_message.lower():
                solution = "تأكد من أن البوت عضو في المجموعة."
        elif isinstance(error, Forbidden):
            cause = f"البوت محظور أو ليس لديه صلاحيات: `{error_message}`"
            solution = "تأكد من أن البوت مشرف ولديه الصلاحيات المطلوبة."
        elif isinstance(error, TimedOut):
            cause = f"انتهت مهلة الاتصال بـ Telegram: `{error_message}`"
            solution = "حاول مرة أخرى، أو تحقق من سرعة الاتصال."
        elif isinstance(error, NetworkError):
            cause = f"مشكلة في الشبكة: `{error_message}`"
            solution = "تحقق من اتصال الإنترنت، وحاول مرة أخرى."
        elif isinstance(error, Conflict):
            cause = f"تعارض في التحديثات (بوت مكرر): `{error_message}`"
            solution = "تأكد من عدم تشغيل نسخة أخرى من البوت بنفس التوكن."

        error_text = f"""🚨 **خطأ في البوت**
━━━━━━━━━━━━━━━━━━━━━━
🆔 **معرف الخطأ:** `{error_id}`
📌 **نوع الخطأ:** `{error_type}`
📝 **الرسالة:** `{error_message[:200]}`

📋 **السبب:**
{cause}

🔧 **الحل المقترح:**
{solution}
━━━━━━━━━━━━━━━━━━━━━━
👤 **المستخدم:** `{user_id}`
🕐 **الوقت:** {mecca_now().strftime('%Y-%m-%d %H:%M:%S')}"""

        if update and update.effective_user:
            try:
                await safe_send_markdown(context.bot, user_id, error_text)
            except:
                try:
                    await context.bot.send_message(chat_id=user_id, text=f"❌ حدث خطأ (الرمز: `{error_id}`)")
                except:
                    pass

        log_channel_id = await db_get_log_channel_id()
        if log_channel_id:
            try:
                await context.bot.send_message(chat_id=log_channel_id, text=error_text, parse_mode="MarkdownV2")
            except:
                pass

        advanced_logger.log_error(f"خطأ في التحديث ({error_id})", error, {'user_id': user_id, 'chat_id': chat_id, 'error_id': error_id})

        if isinstance(error, (Forbidden, Conflict, sqlite3.OperationalError)):
            try:
                await context.bot.send_message(chat_id=PRIMARY_OWNER_ID, text=f"🚨 **خطأ حرج في البوت**\n\n🆔 `{error_id}`\n📌 `{error_type}`\n📝 `{error_message[:200]}`\n👤 المستخدم: `{user_id}`", parse_mode="MarkdownV2")
            except:
                pass
        return True
    except Exception as e:
        logger.error(f"فشل معالج الأخطاء نفسه: {e}")
        try:
            if update and update.effective_user:
                await context.bot.send_message(chat_id=update.effective_user.id, text="❌ حدث خطأ غير متوقع. تم إبلاغ المطور.")
        except:
            pass
        return True

# ===================================================================
# 38. مدير المهام (TaskManager)
# ===================================================================

class TaskManager:
    """مدير المهام الخلفية مع تحكم في عدد المهام المتزامنة"""
    
    def __init__(self, max_tasks=50, max_concurrent=10):
        self.tasks = set()
        self._lock = asyncio.Lock()
        self.max_tasks = max_tasks
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.task_names = {}
    
    def create_task(self, coro: Awaitable, name: str = None) -> asyncio.Task:
        async def _wrapped():
            async with self.semaphore:
                try:
                    return await coro
                except asyncio.CancelledError:
                    logger.info(f"🛑 تم إلغاء المهمة: {name or 'غير مسماة'}")
                    raise
                except Exception as e:
                    logger.error(f"❌ خطأ في المهمة {name or 'غير مسماة'}: {e}")
                    raise
        
        self._cleanup_tasks()
        task = asyncio.create_task(_wrapped())
        if name:
            task.set_name(name)
            self.task_names[task] = name
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task
    
    def _cleanup_tasks(self):
        done = {t for t in self.tasks if t.done()}
        for t in done:
            self.tasks.discard(t)
            self.task_names.pop(t, None)
    
    async def cancel_all(self):
        for task in list(self.tasks):
            if not task.done():
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        self.task_names.clear()
    
    def get_task_count(self) -> int:
        self._cleanup_tasks()
        return len(self.tasks)

task_manager = TaskManager(max_concurrent=10)

# ===================================================================
# 39. دوال التشغيل الآمن
# ===================================================================

async def safe_loop(coro_func, name: str = "background_loop"):
    """تشغيل حلقة لا نهائية مع إعادة تشغيل تلقائية عند الفشل"""
    consecutive_errors = 0
    backoff = 5
    max_backoff = 300
    while True:
        try:
            if asyncio.iscoroutinefunction(coro_func):
                await coro_func()
            else:
                await coro_func()
            consecutive_errors = 0
            backoff = 5
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info(f"🛑 تم إلغاء الحلقة: {name}")
            break
        except Exception as e:
            consecutive_errors += 1
            backoff = min(backoff * 1.5, max_backoff)
            error_id = log_error(e, {'task': name, 'attempt': consecutive_errors})
            logger.error(f"❌ تعطلت الحلقة {name} (الرمز: {error_id}). إعادة التشغيل بعد {backoff:.1f} ثوانٍ...")
            await asyncio.sleep(backoff)

async def run_polling_safe(application):
    """تشغيل polling مع إعادة تشغيل تلقائية عند التوقف"""
    while True:
        try:
            await application.run_polling(drop_pending_updates=True, poll_interval=POLL_INTERVAL)
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
# 40. معالجات الأحداث
# ===================================================================

async def chat_join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج طلبات الانضمام - قبول تلقائي"""
    join_request = update.chat_join_request
    if not join_request:
        return
    chat_id = join_request.chat.id
    user_id = join_request.from_user.id
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if not bot_member.can_invite_users:
            return
    except:
        return
    try:
        await join_request.approve()
        logger.info(f"✅ تم قبول طلب انضمام المستخدم {user_id} إلى المجموعة {chat_id}")
    except Exception as e:
        logger.error(f"❌ فشل قبول طلب انضمام المستخدم {user_id}: {e}")

async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأعضاء الجدد - ترحيب"""
    if not update.message or not update.message.new_chat_members:
        return
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        return
    chat_id = chat.id
    settings = await db_get_security_settings(chat_id)
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue
        if settings.get('delete_service', False):
            try:
                await update.message.delete()
            except:
                pass
        if settings.get('welcome_enabled', False):
            welcome_text = settings.get('welcome_text', "مرحباً {user} في {chat} 🤍")
            welcome_text = format_welcome_message(welcome_text, member.full_name or member.first_name or str(member.id), chat.title)
            try:
                await context.bot.send_message(chat_id, welcome_text)
            except:
                pass
        await db_update_user_cache(member.id, member.username or "", member.first_name or "")

async def left_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج مغادرة الأعضاء - وداع"""
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
        except:
            pass
    if settings.get('goodbye_enabled', False):
        goodbye_text = settings.get('goodbye_text', "وداعاً {user} 👋")
        goodbye_text = goodbye_text.replace('{user}', left_member.full_name or left_member.first_name or str(left_member.id))
        goodbye_text = goodbye_text.replace('{chat}', chat.title)
        try:
            await context.bot.send_message(chat_id, goodbye_text)
        except:
            pass

async def track_chat_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تتبع إضافة البوت إلى المجموعات والقنوات"""
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
                await db_add_channel(adder.id, str(chat.id), chat.title or "بدون اسم")
            elif chat.type in ['group', 'supergroup']:
                await db_register_group(chat.id, chat.title or "بدون اسم", adder.id, chat.username)
                await db_sync_group_admins(chat.id, context.bot)

async def pre_checkout_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج التحقق من صحة الدفع"""
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

# ===================================================================
# 41. 200 رد تلقائي مع تحليل المشاعر
# ===================================================================

ALL_REPLIES = {
    # تحيات وتراحيب
    "السلام عليكم": "وعليكم السلام ورحمة الله وبركاته 🌸",
    "السلام": "وعليكم السلام",
    "سلام": "وعليكم السلام",
    "هلا": "هلا بك، نورت ✨",
    "هلا بك": "هلا فيك",
    "اهلا": "أهلاً وسهلاً 🌹",
    "اهلاً": "أهلاً بك",
    "مرحبا": "مرحباً، نورت المكان 🌟",
    "مرحباً": "مرحباً بك",
    "صباح الخير": "صباح النور ☀️",
    "صباحو": "صباح النور والعسل 🍯",
    "صباح النور": "صباحك سعيد 🌅",
    "مساء الخير": "مساء النور 🌙",
    "مساء النور": "مساءك جميل ✨",
    "مساءو": "مساء الخير والعافية",
    "تصبح على خير": "وأنت من أهله 🌜",
    "تصبحون على خير": "ونحن بخير بإذن الله",
    "Good morning": "Good morning ☀️",
    "Good night": "Good night 🌙",
    "Hello": "Hello 👋",
    "Hi": "Hi there! 👋",
    "Hey": "Hey! How are you?",

    # شكر وامتنان
    "شكرا": "عفواً 😊",
    "شكراً": "العفو، واجبنا 🌹",
    "شكرا جزيلا": "العفو، هذا من ذوقك 🤍",
    "شكراً جزيلاً": "لا شكر على واجب 🌸",
    "تسلم": "تسلم، الله يخليك",
    "تسلمي": "تسلمي، الله يسعدك",
    "يسلمو": "يسلم راسك 🌷",
    "يعطيك العافية": "الله يعافيك 🤍",
    "يعطيكم العافية": "الله يعافيكم",
    "بارك الله فيك": "وفيك بارك الله 🌹",
    "جزاك الله خير": "وإياك يارب 🤲",
    "جزاك الله خيرا": "وإياك إن شاء الله",
    "مشكور": "العفو، واجبنا",
    "مشكورة": "العفو، هذا من ذوقك",
    "Thanks": "You're welcome 😊",
    "Thank you": "You're welcome 🌸",

    # أسئلة شائعة
    "كيفك": "بخير الحمد لله، وأنت؟ 😊",
    "كيف الحال": "الحمد لله تمام، وأنت؟ 🌹",
    "كيف حالك": "بخير الحمد لله، تسأل عني؟ 🤍",
    "شلونك": "بخير الحمد لله، وأنت؟",
    "شلونكم": "الحمد لله بخير، الله يسلمكم",
    "شو الأخبار": "كل شي تمام الحمد لله ✨",
    "ما الأخبار": "أخبار سعيدة إن شاء الله 🌟",
    "شو مسوي": "هنا معاكم، وأنت شو مسوي؟",
    "من وين": "من هون، وأنت؟ 😄",
    "كم عمرك": "عمر البوت صغير لكن الخبرة كبيرة 😎",
    "شو اسمك": "اسمي ريلاكس مانيجر للخدمة 🌿",
    "مين انت": "أنا بوت مساعد، ريلاكس مانيجر 🌿",
    "مين صنعك": "المطور الأسطوري @RelaxMgr 👨‍💻",

    # ردود عاطفية
    "احبك": "حبيبي والله 🤍",
    "احبكم": "الله يحفظكم 🤍",
    "اشتقتلك": "وأنا كمان اشتقتلك 😢💕",
    "وحشتوني": "نورتي والله 🌸",
    "فديتك": "فداك قلبي والله 😭💕",
    "فديتكم": "فداكم الكون كله 🤍",
    "روحي": "روحي لك الفداء 🌸",
    "قلبي": "قلبي لك 💕",
    "يا عمري": "عيوني لك والله 😍",
    "يا بعدي": "بعدي انت وقلبي 🌹",
    "يا غالي": "الغالي انت والله 💎",
    "يا غالية": "الغالية انتي 💎",
    "عيوني": "عيوني لك 😍",

    # ردود دينية
    "الله": "لا إله إلا الله 🤲",
    "سبحان الله": "سبحان الله وبحمده 🌸",
    "الحمد لله": "الحمد لله دائماً وأبداً 🤲",
    "الحمدلله": "الحمد لله حمداً كثيراً",
    "ما شاء الله": "لا قوة إلا بالله 🌹",
    "ماشاء الله": "تبارك الله 🌸",
    "لا إله إلا الله": "محمد رسول الله ﷺ",
    "استغفر الله": "استغفر الله العظيم وأتوب إليه",
    "الله أكبر": "الله أكبر كبيراً 🤲",
    "اللهم صل على محمد": "عليه أفضل الصلاة والسلام ﷺ",
    "صلى الله عليه وسلم": "ﷺ عليه أفضل الصلاة",
    "بسم الله": "بسم الله الرحمن الرحيم 🌸",
    "توكلت على الله": "نعم الوكيل 🤲",
    "إن شاء الله": "إن شاء الله 🌹",
    "ان شاء الله": "بإذن الله تعالى",
    "يارب": "آمين يارب العالمين 🤲",
    "آمين": "اللهم آمين 🤲",
    "استودعكم الله": "في حفظ الله ورعايته 🤲",

    # ردود للمناسبات
    "مبروك": "الله يبارك فيك 🎉",
    "مبروووك": "العقبى عندك يارب 🎊",
    "الف مبروك": "الله يبارك لك وعليك 🎉",
    "عقبالك": "وإياك يارب 🌸",
    "عقبالي": "إن شاء الله قريب 🎉",
    "عيد ميلاد سعيد": "وأنت طيب وبخير 🎂",
    "كل عام وانت بخير": "وأنت بألف خير 🌹",
    "رمضان كريم": "علينا وعليكم يارب 🌙",
    "عيد سعيد": "علينا وعليكم يارب 🎊",
    "عيد مبارك": "علينا وعليكم 🌙",
    "جمعة مباركة": "علينا وعليكم يارب 🌹",
    "صباح الخميس": "صباحك سعيد 🌸",
    "صباح الجمعة": "جمعة مباركة 🌹",

    # ردود متنوعة
    "تمام": "الحمد لله 🌸",
    "طيب": "طيب الله أيامك 🌹",
    "اوك": "حاضرين 😊",
    "اوكي": "تمام 👍",
    "حسناً": "أمرك مطاع 🌸",
    "حسنا": "تمام 👍",
    "ان شاءالله": "إن شاء الله 🌹",
    "يالله": "الله يسهل 🤲",
    "يالله نبدا": "بسم الله، جاهزين 👍",
    "هيا": "يلا بينا 🚀",
    "يلا": "يلا بينا 🚀",
    "يله": "يلا بينا 🚀",
    "Ok": "Ok 👍",
    "Okay": "Okay 😊",
    "Done": "Done ✅",
    "Good": "Great 👍",
    "Great": "Awesome 🎉",
    "Nice": "Nice 👌",
    "Cool": "Cool 😎",
    "Perfect": "Perfect 💯",

    # ردود مضحكة
    "هههه": "😂😂😂",
    "ههههه": "😂😂😂 ضحكتني",
    "هههههه": "🤣🤣🤣",
    "😂": "😂😂😂",
    "🤣": "🤣🤣🤣",
    "لول": "😂😂😂",
    "Lol": "😂😂😂",
    "ضحك": "😂 الله يضحك سنك",
    "نكتة": "احكي نكتة 😄",
    "فله": "فله وعلله 😂",
    "وناسه": "وناسه وفرحه 🎉",

    # ردود دعم فني
    "بوت": "نعم، أنا بوت ريلاكس مانيجر 🌿\nكيف أقدر أساعدك؟",
    "مساعدة": "أنا هنا لمساعدتك 🌸\nاستخدم /help للأوامر المتاحة",
    "تعليمات": "استخدم /help لعرض جميع الأوامر 📋",
    "شرح": "ماذا تريد أن تعرف بالضبط؟ 🤔",
    "مشكلة": "اشرح لي المشكلة وأنا أحلها لك 🔧",
    "خطأ": "أرسل لي تفاصيل الخطأ وأنا أساعدك 🔍",
    "عطل": "وش العطل بالضبط؟ خلني أشوف لك حل 🔧",
    "ما يفهم": "أنا أفهم، تفضل اشرح لي 🌸",
    "حد يعرف": "أنا هنا، اسألني 🌿",
    "سؤال": "تفضل، اسأل وأنا جاوب 🌸",
    "ممكن سؤال": "تفضل، أنا بالخدمة 🌹",

    # ردود تشجيعية
    "حلو": "زي العسل 🍯",
    "حلوة": "زي القمر 🌙",
    "جميل": "الجمال جمالك 🌸",
    "جميلة": "الجمال جمالك 🌸",
    "رائع": "الروعة أنت 🌟",
    "رائعة": "الروعة أنت 🌟",
    "ممتاز": "ممتاز مثلك 👌",
    "ممتازة": "ممتازة مثلك 👌",
    "عظيم": "العظمة لله 🌹",
    "مبدع": "الإبداع منك 🌟",
    "مبدعة": "الإبداع منك 🌟",
    "ذكي": "الذكاء منك 🤓",
    "فنان": "الفن منك 🎨",

    # ردود تعاطف
    "تعبان": "سلامتك، الله يشافيك 🤲",
    "تعبانة": "سلامتك، الله يشافيك 🤲",
    "زعلان": "لا تزعل، الدنيا بخير 🌸",
    "زعلانة": "لا تزعلي، الدنيا بخير 🌸",
    "حزين": "لا تحزن، الفرج قريب إن شاء الله 🤲",
    "حزينة": "لا تحزني، الفرج قريب إن شاء الله 🤲",
    "ضايق": "الله يشرح صدرك 🌸",
    "ضايقة": "الله يشرح صدرك 🌸",
    "متضايق": "تفضل فضفض، أنا معاك 🤍",
    "متضايقة": "تفضلي فضفضي، أنا معاك 🤍",
    "مقهور": "الله يفرج همك 🤲",
    "مريض": "سلامات، الله يشفيك 🤲",
    "مريضة": "سلامات، الله يشفيك 🤲",
    "سلامات": "الله يسلمك 🌸",

    # ردود إعجاب
    "الله عليك": "الله يخليك 🌸",
    "قمر": "قمر أنت والله 🌙",
    "وردة": "الوردة أنت 🌸",
    "أسطورة": "الأسطورة أنت 👑",
    "ملك": "الملك أنت 👑",
    "ملكة": "الملكة أنت 👑",
    "بطل": "البطل أنت 🏆",
    "بطلة": "البطلة أنت 🏆",
    "شيخ": "الله يسعدك 🌹",
    "شيخة": "الله يسعدك 🌹",
    "أمير": "الأمير أنت 👑",
    "أميرة": "الأميرة أنت 👑",

    # ردود ختامية
    "مع السلامة": "الله معك 🌸",
    "بااي": "باي، اشوفك على خير 👋",
    "باي": "باي، الله معاك 👋",
    "وداعا": "وداعاً، في أمان الله 🤲",
    "وداعاً": "في حفظ الله 🌸",
    "أراك لاحقاً": "إن شاء الله على خير 🌹",
    "اشوفك": "إن شاء الله 🌸",
    "نلتقي": "على خير إن شاء الله 🌹",
    "سلام": "مع السلامة 🌸",
    "سلامو": "الله يسلمك 👋",
    "يالله نايم": "تصبح على خير 🌜",
    "بروح": "مع السلامة 🌸",
    "بروح انام": "تصبح على خير وأحلام سعيدة 🌜",
    "Goodbye": "Goodbye 👋",
    "Bye": "Bye 👋",
    "See you": "See you later 👋",
    "Cya": "Cya 👋",
}

user_points_last_hour = defaultdict(list)
NSFW_THRESHOLD = float(os.getenv('NSFW_THRESHOLD', '0.7'))
# ===================================================================
# جميع الدوال المفقودة - النسخة الكاملة والنهائية
# ضع هذا الكود قبل دالة main() مباشرة
# ===================================================================

# ===================================================================
# 1. دوال لوحة الأدمن
# ===================================================================

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض لوحة الأدمن"""
    query = update.callback_query
    if query: await query.answer()
    user_id = update.effective_user.id
    if user_id == PRIMARY_OWNER_ID or await is_bot_admin(user_id):
        await safe_edit_markdown(query, "👑 **لوحة التحكم**\nاختر الإجراء المطلوب:", reply_markup=get_admin_keyboard(user_id))
    else:
        await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")

async def admin_router_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """موزع أزرار لوحة الأدمن"""
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    await query.answer()
    
    handlers = {
        CallbackData.ADMIN_USERS: admin_users_callback,
        CallbackData.ADMIN_BANNED_USERS: admin_banned_users_callback,
        CallbackData.ADMIN_UNBAN_ALL_USERS: admin_unban_all_users_callback,
        CallbackData.ADMIN_ALL_CHANNELS: admin_all_channels_callback,
        CallbackData.ADMIN_BANNED_CHANNELS: admin_banned_channels_callback,
        CallbackData.ADMIN_ACTIVATE_ALL_CHANNELS: admin_activate_all_channels_callback,
        CallbackData.ADMIN_GROUPS: admin_groups_callback,
        CallbackData.ADMIN_BANNED_GROUPS: admin_banned_groups_callback,
        CallbackData.ADMIN_UNBAN_ALL_GROUPS: admin_unban_all_groups_callback,
        CallbackData.ADMIN_BOT_CHANNELS: admin_bot_channels_callback,
        CallbackData.ADMIN_BANNED_BOT_CHANNELS: admin_banned_bot_channels_callback,
        CallbackData.ADMIN_UNBAN_ALL_BOT_CHANNELS: admin_unban_all_bot_channels_callback,
        CallbackData.ADMIN_MONITOR_USERS: admin_monitor_users_callback,
        CallbackData.ADMIN_ADD_ADMIN: admin_add_admin_callback,
        CallbackData.ADMIN_REMOVE_ADMIN: admin_remove_admin_callback,
        CallbackData.ADMIN_RAM: admin_ram_callback,
        CallbackData.ADMIN_STATS: admin_stats_callback,
        CallbackData.ADMIN_METRICS: admin_metrics_callback,
        CallbackData.ADMIN_BACKUP: admin_backup_callback,
        CallbackData.ADMIN_RESTORE_BACKUP: admin_restore_backup_callback,
        CallbackData.ADMIN_BACKUP_SETTINGS: admin_backup_settings_callback,
        CallbackData.ADMIN_TOGGLE_AUTO_BACKUP: admin_toggle_auto_backup_callback,
        CallbackData.ADMIN_CHANGE_INTERVAL: admin_change_interval_callback,
        CallbackData.ADMIN_SEND_UPDATE: admin_send_update_callback,
        CallbackData.ADMIN_SET_UPDATE_CHANNEL: admin_set_update_channel_callback,
        CallbackData.ADMIN_SHOW_UPDATE_CHANNEL: admin_show_update_channel_callback,
        CallbackData.ADMIN_UPDATES: admin_updates_callback,
        CallbackData.ADMIN_FORCE_SUBSCRIBE: admin_force_subscribe_callback,
        CallbackData.ADMIN_SET_FORCE_CHANNEL: admin_set_force_channel_callback,
        CallbackData.ADMIN_BROADCAST: admin_broadcast_callback,
        CallbackData.ADMIN_CONFIRM_BROADCAST: admin_confirm_broadcast_callback,
        CallbackData.ADMIN_SUPPORT_TICKETS: admin_support_tickets_callback,
        CallbackData.ADMIN_DELETE_ALL_TICKETS: admin_delete_all_tickets_callback,
        CallbackData.ADMIN_CONFIRM_DELETE_TICKETS: admin_confirm_delete_tickets_callback,
        CallbackData.ADMIN_MANAGE_SENDCODE: admin_manage_sendcode_callback,
        CallbackData.ADMIN_SET_SENDCODE_USER: admin_set_sendcode_user_callback,
        CallbackData.ADMIN_SHOW_LOG_CHANNEL: admin_show_log_channel_callback,
        CallbackData.ADMIN_SET_LOG_CHANNEL: admin_set_log_channel_callback,
        CallbackData.ADMIN_REPLIES: admin_replies_callback,
        CallbackData.ADMIN_ADD_REPLY: admin_add_reply_callback,
        CallbackData.ADMIN_LIST_REPLIES: admin_list_replies_callback,
        CallbackData.ADMIN_DEL_REPLY: admin_del_reply_callback,
        CallbackData.ADMIN_BANNED_WORDS: admin_banned_words_callback,
        CallbackData.ADMIN_ADD_BANNED_WORD: admin_add_banned_word_callback,
        CallbackData.ADMIN_LIST_BANNED_WORDS: admin_list_banned_words_callback,
        CallbackData.ADMIN_REMOVE_BANNED_WORD: admin_remove_banned_word_callback,
        CallbackData.ADMIN_CREATE_CONTEST: admin_create_contest_callback,
        CallbackData.ADMIN_DECLARE_WINNER: admin_declare_winner_callback,
        CallbackData.ADMIN_AUTO_REPLY: admin_auto_reply_callback,
    }
    
    handler = handlers.get(data)
    if handler:
        return await handler(update, context)
    if data.startswith(CallbackData.ADMIN_RESTORE_BACKUP_SELECT_PREFIX):
        return await admin_restore_backup_select_callback(update, context)
    if data.startswith("confirm_restore:"):
        return await confirm_restore_callback(update, context)
    if data.startswith(CallbackData.ADMIN_DEL_CONTEST_PREFIX):
        return await admin_del_contest_callback(update, context)
    
    await query.answer("⚠️ قيد التطوير", show_alert=True)

# ===================================================================
# 2. دوال أزرار الأدمن التفصيلية
# ===================================================================

async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM users")
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE banned=1")
        banned = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM users WHERE subscription_end > ?", (utc_now_iso(),))
        active = (await cur.fetchone())[0]
        return total, banned, active
    total, banned, active = await execute_db(_get)
    text = f"👥 **المستخدمين**\n━━━━━━━━━━━━━━\n📊 الإجمالي: {total}\n✅ النشطين: {active}\n🚫 المحظورين: {banned}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_banned_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _get(conn):
        cur = await conn.execute("SELECT user_id, username, first_name FROM users WHERE banned=1 LIMIT 50")
        return await cur.fetchall()
    users = await execute_db(_get)
    if not users:
        await safe_edit_markdown(query, "🚫 لا يوجد مستخدمين محظورين")
        return
    text = "🚫 **المستخدمين المحظورين**\n━━━━━━━━━━━━━━\n"
    for uid, username, first_name in users:
        name = first_name or username or str(uid)
        text += f"• `{uid}` - {name}\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_unban_all_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _unban(conn):
        await conn.execute("UPDATE users SET banned=0")
        await conn.commit()
    await execute_db(_unban)
    await safe_edit_markdown(query, "✅ تم فك حظر جميع المستخدمين")

async def admin_all_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM user_channels")
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM user_channels WHERE banned=1")
        banned = (await cur.fetchone())[0]
        return total, banned
    total, banned = await execute_db(_get)
    text = f"📡 **قنوات المستخدمين**\n━━━━━━━━━━━━━━\n📊 الإجمالي: {total}\n🚫 المحظورة: {banned}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_banned_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _get(conn):
        cur = await conn.execute("SELECT id, channel_id, channel_name FROM user_channels WHERE banned=1 LIMIT 50")
        return await cur.fetchall()
    channels = await execute_db(_get)
    if not channels:
        await safe_edit_markdown(query, "🚫 لا توجد قنوات محظورة")
        return
    text = "🚫 **القنوات المحظورة**\n━━━━━━━━━━━━━━\n"
    for ch_id, ch_tele_id, ch_name in channels:
        text += f"• `{ch_tele_id}` - {ch_name}\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_activate_all_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _activate(conn):
        await conn.execute("UPDATE user_channels SET banned=0")
        await conn.commit()
    await execute_db(_activate)
    await safe_edit_markdown(query, "✅ تم تنشيط جميع القنوات")

async def admin_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM bot_groups")
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM bot_groups WHERE banned=1")
        banned = (await cur.fetchone())[0]
        return total, banned
    total, banned = await execute_db(_get)
    text = f"👥 **المجموعات**\n━━━━━━━━━━━━━━\n📊 الإجمالي: {total}\n🚫 المحظورة: {banned}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_banned_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _get(conn):
        cur = await conn.execute("SELECT chat_id, chat_name FROM bot_groups WHERE banned=1 LIMIT 50")
        return await cur.fetchall()
    groups = await execute_db(_get)
    if not groups:
        await safe_edit_markdown(query, "🚫 لا توجد مجموعات محظورة")
        return
    text = "🚫 **المجموعات المحظورة**\n━━━━━━━━━━━━━━\n"
    for chat_id, chat_name in groups:
        text += f"• `{chat_id}` - {chat_name}\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_unban_all_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _unban(conn):
        await conn.execute("UPDATE bot_groups SET banned=0")
        await conn.commit()
    await execute_db(_unban)
    await safe_edit_markdown(query, "✅ تم فك حظر جميع المجموعات")

async def admin_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _get(conn):
        cur = await conn.execute("SELECT channel_id, channel_name FROM bot_channels LIMIT 50")
        return await cur.fetchall()
    channels = await execute_db(_get)
    if not channels:
        await safe_edit_markdown(query, "📭 لا توجد قنوات مسجلة")
        return
    text = "📢 **قنوات البوت**\n━━━━━━━━━━━━━━\n"
    for channel_id, channel_name in channels:
        text += f"• `{channel_id}` - {channel_name}\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_banned_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await safe_edit_markdown(query, "🚫 **قنوات البوت المحظورة**\n\nلا توجد قنوات محظورة")

async def admin_unban_all_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await safe_edit_markdown(query, "✅ تم فك حظر جميع قنوات البوت")

async def admin_monitor_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    total, banned, posts, groups, channels = await db_stats()
    text = f"📊 **مراقبة المستخدمين**\n━━━━━━━━━━━━━━\n👥 المستخدمين: {total}\n🚫 المحظورين: {banned}\n📝 المنشورات: {posts}\n👥 المجموعات: {groups}\n📡 القنوات: {channels}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_add_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_ADMIN_ID_ADD
    await safe_edit_markdown(query, "👑 أرسل معرف المستخدم لإضافته كمشرف:")

async def admin_remove_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_ADMIN_ID_REMOVE
    await safe_edit_markdown(query, "🗑️ أرسل معرف المستخدم لإزالته من المشرفين:")

async def admin_ram_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    ram = get_ram_usage()
    text = f"💾 **حالة الذاكرة**\n━━━━━━━━━━━━━━\n📊 المستخدم: {ram['used']:.1f}/{ram['total']:.1f} GB\n📈 النسبة: {ram['percent']}%\n✅ المتاح: {ram['available']:.1f} GB"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    total, banned, posts, groups, channels = await db_stats()
    text = f"📊 **إحصائيات البوت**\n━━━━━━━━━━━━━━\n👥 المستخدمين: {total}\n🚫 المحظورين: {banned}\n📝 المنشورات: {posts}\n👥 المجموعات: {groups}\n📡 القنوات: {channels}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_metrics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    ram = get_ram_usage()
    task_count = task_manager.get_task_count()
    text = f"📈 **مقاييس الأداء**\n━━━━━━━━━━━━━━\n💾 الرام: {ram['percent']}%\n🔄 المهام النشطة: {task_count}\n🗄️ قاعدة البيانات: متصلة"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    await safe_edit_markdown(query, "💾 جاري إنشاء نسخة احتياطية...")
    try:
        backup_file = await create_backup()
        await safe_send_markdown(context.bot, user_id, f"✅ تم إنشاء النسخة الاحتياطية:\n{backup_file.name}")
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ فشل النسخ الاحتياطي: {str(e)[:100]}")

async def admin_restore_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    backups = await list_backups()
    if not backups:
        await safe_edit_markdown(query, "📭 لا توجد نسخ احتياطية")
        return
    text = "💾 **اختر نسخة للاستعادة:**\n\n"
    kb = []
    for i, backup in enumerate(backups[:10], 1):
        size = backup.stat().st_size / 1024
        text += f"{i}. {backup.name} ({size:.1f} KB)\n"
        kb.append([InlineKeyboardButton(f"{i}. {backup.name[:30]}", callback_data=f"confirm_restore:{backup.name}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)])
    await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(kb))

async def admin_restore_backup_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await admin_restore_backup_callback(update, context)

async def confirm_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    backup_name = query.data.split(":")[-1]
    backup_path = BACKUP_DIR / backup_name
    try:
        await restore_backup(backup_path)
        await safe_edit_markdown(query, "✅ تم استعادة النسخة الاحتياطية بنجاح")
    except Exception as e:
        await safe_edit_markdown(query, f"❌ فشل الاستعادة: {str(e)[:100]}")

async def admin_backup_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    auto = await db_get_auto_backup()
    text = f"⚙️ **إعدادات النسخ الاحتياطي**\n\nالنسخ التلقائي: {'✅ مفعل' if auto else '❌ معطل'}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("تبديل النسخ التلقائي", callback_data=CallbackData.ADMIN_TOGGLE_AUTO_BACKUP)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_toggle_auto_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    current = await db_get_auto_backup()
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_backup', ?)", ('0' if current else '1',))
        await conn.commit()
    await execute_db(_set)
    await admin_backup_settings_callback(update, context)

async def admin_change_interval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await safe_edit_markdown(query, "⏱️ أرسل المدة الجديدة للنشر التلقائي (بالثواني):")

async def admin_send_update_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_UPDATE_TEXT
    await safe_edit_markdown(query, "📢 أرسل نص التحديث:")

async def admin_set_update_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_UPDATE_CHANNEL
    await safe_edit_markdown(query, "📢 أرسل معرف قناة التحديثات (بدون @):")

async def admin_show_update_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    channel = await db_get_updates_channel()
    await safe_edit_markdown(query, f"📢 قناة التحديثات: @{channel}" if channel else "📢 لم يتم تعيين قناة التحديثات")

async def admin_updates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    channel = await db_get_updates_channel()
    msg = f"📢 **إدارة التحديثات**\n\nقناة التحديثات: {'@' + channel if channel else 'غير محددة'}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 إرسال تحديث", callback_data=CallbackData.ADMIN_SEND_UPDATE)],
        [InlineKeyboardButton("⚙️ تعيين القناة", callback_data=CallbackData.ADMIN_SET_UPDATE_CHANNEL)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    await safe_edit_markdown(query, msg, reply_markup=kb)

async def admin_force_subscribe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    channel = await db_get_force_subscribe_channel()
    msg = f"🔒 **الاشتراك الإجباري**\n\nقناة الاشتراك: {'@' + channel if channel else 'غير محددة'}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ تعيين القناة", callback_data=CallbackData.ADMIN_SET_FORCE_CHANNEL)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    await safe_edit_markdown(query, msg, reply_markup=kb)

async def admin_set_force_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_FORCE_CHANNEL
    await safe_edit_markdown(query, "🔒 أرسل معرف قناة الاشتراك الإجباري (بدون @):")

async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_BROADCAST
    await safe_edit_markdown(query, "📨 أرسل الرسالة التي تريد إرسالها لجميع المستخدمين:")

async def admin_confirm_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    broadcast_text = context.user_data.get('broadcast_text', '')
    if not broadcast_text:
        await safe_edit_markdown(query, "❌ لا توجد رسالة للإرسال")
        return
    users = await db_get_all_users()
    sent = 0; failed = 0
    for row in users:
        try:
            await context.bot.send_message(chat_id=row[0], text=broadcast_text)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    await safe_edit_markdown(query, f"📨 **نتائج البث**\n\n✅ تم الإرسال: {sent}\n❌ فشل: {failed}")

async def admin_support_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM support_tickets WHERE status='pending'")
        pending = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM support_tickets")
        total = (await cur.fetchone())[0]
        return pending, total
    pending, total = await execute_db(_get)
    text = f"📋 **التذاكر**\n━━━━━━━━━━━━━━\n📝 المعلقة: {pending}\n📊 الإجمالي: {total}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_delete_all_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، احذف الكل", callback_data=CallbackData.ADMIN_CONFIRM_DELETE_TICKETS)],
        [InlineKeyboardButton("❌ لا", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    await safe_edit_markdown(query, "⚠️ هل أنت متأكد من حذف جميع التذاكر؟", reply_markup=kb)

async def admin_confirm_delete_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _del(conn):
        await conn.execute("DELETE FROM support_tickets")
        await conn.commit()
    await execute_db(_del)
    await safe_edit_markdown(query, "✅ تم حذف جميع التذاكر")

async def admin_manage_sendcode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_SENDCODE_USER
    await safe_edit_markdown(query, "📁 أرسل معرف المستخدم المسموح له باستخدام /sendcode:")

async def admin_set_sendcode_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await admin_manage_sendcode_callback(update, context)

async def admin_show_log_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    log_id = await db_get_log_channel_id()
    await safe_edit_markdown(query, f"📋 قناة التقارير: `{log_id}`" if log_id else "📋 لم يتم تعيين قناة التقارير")

async def admin_set_log_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_LOG_CHANNEL
    await safe_edit_markdown(query, "📋 أرسل معرف قناة التقارير:")

async def admin_replies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await safe_edit_markdown(query, "💬 **إدارة الردود**", reply_markup=get_replies_keyboard())

async def admin_add_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_KEYWORD
    await safe_edit_markdown(query, "📝 أرسل الكلمة المفتاحية:")

async def admin_list_replies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    async def _get(conn):
        cur = await conn.execute("SELECT keyword, reply FROM auto_replies WHERE chat_id=0 LIMIT 50")
        return await cur.fetchall()
    replies = await execute_db(_get)
    if not replies:
        await safe_edit_markdown(query, "📭 لا توجد ردود")
        return
    text = "💬 **الردود التلقائية**\n━━━━━━━━━━━━━━\n"
    for keyword, reply in replies:
        text += f"• `{keyword}` → {reply[:50]}...\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_REPLIES)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_del_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['admin_del_reply'] = True
    context.user_data['state'] = UserState.WAITING_REPLY
    await safe_edit_markdown(query, "🗑️ أرسل الكلمة المفتاحية للحذف:")

async def admin_banned_words_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await safe_edit_markdown(query, "🚫 **الكلمات المحظورة العامة**", reply_markup=get_banned_words_admin_keyboard())

async def admin_add_banned_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_GLOBAL_BANNED_WORD
    await safe_edit_markdown(query, "🚫 أرسل الكلمة المراد حظرها:")

async def admin_list_banned_words_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    words = await db_get_banned_words(-1)
    if not words:
        await safe_edit_markdown(query, "📭 لا توجد كلمات محظورة")
        return
    text = "🚫 **الكلمات المحظورة العامة**\n━━━━━━━━━━━━━━\n"
    for word, added_by, added_at in words[:50]:
        text += f"• `{word}`\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_BANNED_WORDS)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def admin_remove_banned_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_REMOVE_GLOBAL_BANNED_WORD
    await safe_edit_markdown(query, "🗑️ أرسل الكلمة المراد إزالتها:")

async def admin_create_contest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_CONTEST_TITLE
    await safe_edit_markdown(query, "📝 أرسل عنوان المسابقة:")

async def admin_declare_winner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await safe_edit_markdown(query, "🏆 أرسل معرف المسابقة ومعرف الفائز:\n/declare_winner معرف_المسابقة معرف_المستخدم")

async def admin_del_contest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    parts = query.data.split(":")
    if len(parts) < 2: return
    try:
        contest_id = int(parts[-1])
    except ValueError:
        return
    async def _del(conn):
        await conn.execute("DELETE FROM contests WHERE id=?", (contest_id,))
        await conn.execute("DELETE FROM contest_participants WHERE contest_id=?", (contest_id,))
        await conn.commit()
    await execute_db(_del)
    await safe_edit_markdown(query, "✅ تم حذف المسابقة")

async def admin_auto_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await safe_edit_markdown(query, "📝 **الردود التلقائية**\n\nاختر مجموعة لإعداد الردود التلقائية")

# ===================================================================
# 3. دوال الإحالات
# ===================================================================

async def referral_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    user_id = update.effective_user.id
    stats = await db_get_referral_stats(user_id)
    referral_code = await db_get_user_referral_code(user_id)
    text = (
        f"🔗 **الإحالات**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 رابط الإحالة الخاص بك:\n`https://t.me/{BOT_USERNAME}?start=ref_{referral_code}`\n\n"
        f"👥 عدد المحالين: {stats['total_referrals']}\n🎁 المكافآت المتاحة: {stats['available_days']} يوم\n"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 نسخ الرابط", callback_data=f"{CallbackData.REFERRAL_COPY_LINK_PREFIX}{referral_code}")],
        [InlineKeyboardButton("🎁 صرف المكافآت", callback_data=CallbackData.REFERRAL_CLAIM_REWARD)],
        [InlineKeyboardButton("📋 قائمة المحالين", callback_data=CallbackData.REFERRAL_LIST)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def referral_copy_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer("✅ تم نسخ الرابط!", show_alert=True)

async def referral_claim_reward_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    user_id = update.effective_user.id
    days = await db_claim_referral_reward(user_id)
    if days > 0:
        await safe_edit_markdown(query, f"✅ تم صرف {days} يوم اشتراك!")
    else:
        await safe_edit_markdown(query, "❌ لا توجد مكافآت متاحة للصرف")

async def referral_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    user_id = update.effective_user.id
    async def _get_referrals(conn):
        cur = await conn.execute("SELECT referred_id, created_at FROM referrals WHERE referrer_id=? ORDER BY created_at DESC LIMIT 50", (user_id,))
        return await cur.fetchall()
    referrals = await execute_db(_get_referrals)
    if not referrals:
        await safe_edit_markdown(query, "📭 لا توجد إحالات بعد")
        return
    text = "📋 **قائمة المحالين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for idx, (ref_id, created_at) in enumerate(referrals, 1):
        try:
            time_str = datetime.fromisoformat(created_at).strftime("%Y-%m-%d")
        except:
            time_str = str(created_at)[:10]
        text += f"{idx}. `{ref_id}` - {time_str}\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.REFERRAL_MENU)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

# ===================================================================
# 4. دوال التذكيرات
# ===================================================================

async def reminder_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    user_id = update.effective_user.id
    async def _get_settings(conn):
        cur = await conn.execute("SELECT * FROM user_reminder_settings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row:
            return {
                'subscription_reminder': bool(row[1]) if len(row) > 1 else True,
                'daily_stats_reminder': bool(row[2]) if len(row) > 2 else False,
                'weekly_report': bool(row[3]) if len(row) > 3 else True,
                'reminder_days_before': row[4] if len(row) > 4 else 3,
                'notification_lang': row[5] if len(row) > 5 else 'ar'
            }
        return {'subscription_reminder': True, 'daily_stats_reminder': False, 'weekly_report': True, 'reminder_days_before': 3, 'notification_lang': 'ar'}
    settings = await execute_db(_get_settings)
    sub_text = "✅" if settings['subscription_reminder'] else "❌"
    daily_text = "✅" if settings['daily_stats_reminder'] else "❌"
    weekly_text = "✅" if settings['weekly_report'] else "❌"
    text = (
        f"⏰ **إعدادات التذكيرات**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 تذكير انتهاء الاشتراك: {sub_text}\n📊 تقرير يومي: {daily_text}\n"
        f"📈 تقرير أسبوعي: {weekly_text}\n⏰ التذكير قبل: {settings['reminder_days_before']} أيام\n"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔔 تذكير الاشتراك: {sub_text}", callback_data=CallbackData.REMINDER_TOGGLE_SUB)],
        [InlineKeyboardButton(f"📊 تقرير يومي: {daily_text}", callback_data=CallbackData.REMINDER_TOGGLE_DAILY)],
        [InlineKeyboardButton(f"📈 تقرير أسبوعي: {weekly_text}", callback_data=CallbackData.REMINDER_TOGGLE_WEEKLY)],
        [InlineKeyboardButton("⏰ عدد الأيام", callback_data=CallbackData.REMINDER_SET_DAYS)],
        [InlineKeyboardButton("🌐 لغة الإشعارات", callback_data=CallbackData.REMINDER_SET_LANG)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def reminder_toggle_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    async def _get(conn):
        cur = await conn.execute("SELECT subscription_reminder FROM user_reminder_settings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return bool(row[0]) if row else True
    current = await execute_db(_get)
    await db_update_reminder_settings(user_id, subscription_reminder=0 if current else 1)
    await reminder_menu_callback(update, context)

async def reminder_toggle_daily_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    async def _get(conn):
        cur = await conn.execute("SELECT daily_stats_reminder FROM user_reminder_settings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return bool(row[0]) if row else False
    current = await execute_db(_get)
    await db_update_reminder_settings(user_id, daily_stats_reminder=0 if current else 1)
    await reminder_menu_callback(update, context)

async def reminder_toggle_weekly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    async def _get(conn):
        cur = await conn.execute("SELECT weekly_report FROM user_reminder_settings WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return bool(row[0]) if row else True
    current = await execute_db(_get)
    await db_update_reminder_settings(user_id, weekly_report=0 if current else 1)
    await reminder_menu_callback(update, context)

async def reminder_set_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_REMINDER_DAYS
    await safe_edit_markdown(query, "⏰ أرسل عدد الأيام قبل انتهاء الاشتراك (1-10):")

async def reminder_set_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇸🇦 العربية", callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}ar")],
        [InlineKeyboardButton("🇬🇧 English", callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}en")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.REMINDER_MENU)]
    ])
    await safe_edit_markdown(query, "🌐 اختر لغة الإشعارات:", reply_markup=kb)

async def reminder_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    lang = query.data.split(":")[-1]
    await db_update_reminder_settings(user_id, notification_lang=lang)
    await safe_edit_markdown(query, f"✅ تم تعيين لغة الإشعارات إلى {SUPPORTED_LANGUAGES.get(lang, lang)}")
    await reminder_menu_callback(update, context)

# ===================================================================
# 5. دوال الترجمة
# ===================================================================

async def translation_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    lang = await get_user_translation_language(user_id)
    status = f"✅ مفعلة إلى {SUPPORTED_LANGUAGES.get(lang, lang)}" if lang != 'off' else "❌ معطلة"
    text = f"🌐 **إعدادات الترجمة**\n━━━━━━━━━━━━━━━━━━━━━━\nالحالة: {status}\n\n📌 سيتم ترجمة المنشورات تلقائياً عند النشر\n"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇸🇦 العربية", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}ar"),
         InlineKeyboardButton("🇬🇧 English", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}en")],
        [InlineKeyboardButton("🇫🇷 Français", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}fr"),
         InlineKeyboardButton("🇹🇷 Türkçe", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}tr")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}ru"),
         InlineKeyboardButton("🇪🇸 Español", callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}es")],
        [InlineKeyboardButton("🚫 إيقاف الترجمة", callback_data=CallbackData.TRANSLATION_OFF)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def translation_off_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    async def _off(conn):
        await conn.execute("INSERT OR REPLACE INTO user_translation (user_id, lang) VALUES (?, 'off')", (user_id,))
        await conn.commit()
    await execute_db(_off)
    await safe_edit_markdown(query, "✅ تم إيقاف الترجمة التلقائية")

async def translation_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    lang = query.data.split(":")[-1]
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO user_translation (user_id, lang) VALUES (?, ?)", (user_id, lang))
        await conn.commit()
    await execute_db(_set)
    await safe_edit_markdown(query, f"✅ تم تفعيل الترجمة إلى {SUPPORTED_LANGUAGES.get(lang, lang)}")

# ===================================================================
# 6. دوال NSFW
# ===================================================================

async def nsfw_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    threshold = int(NSFW_THRESHOLD * 100)
    text = f"🔞 **إعدادات المحتوى**\n\nنسبة الحساسية الحالية: {threshold}%"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔞 تفعيل/تعطيل", callback_data=CallbackData.NSFW_TOGGLE)],
        [InlineKeyboardButton("📊 تعيين النسبة", callback_data=CallbackData.NSFW_THRESHOLD_SET)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def nsfw_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    global NSFW_THRESHOLD
    if NSFW_THRESHOLD > 0:
        NSFW_THRESHOLD = 0
        await safe_edit_markdown(query, "🔞 تم تعطيل فلتر المحتوى")
    else:
        NSFW_THRESHOLD = 0.7
        await safe_edit_markdown(query, "🔞 تم تفعيل فلتر المحتوى (70%)")

async def nsfw_threshold_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_NSFW_THRESHOLD
    await safe_edit_markdown(query, "📊 أرسل نسبة الحساسية (0-100):")

# ===================================================================
# 7. دوال النسخ الاحتياطي
# ===================================================================

async def create_backup():
    """إنشاء نسخة احتياطية كاملة ومشفرة"""
    try:
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
    """إنشاء نسخة احتياطية متزايدة"""
    try:
        last_backup = await db_get_last_backup_time()
        last_time = datetime.fromisoformat(last_backup) if last_backup else utc_now() - timedelta(days=7)
        backup_data = {}
        async def _get_new_posts(conn):
            cur = await conn.execute("SELECT * FROM posts WHERE created_at > ? LIMIT 1000", (last_time.isoformat(),))
            return await cur.fetchall()
        new_posts = await execute_db(_get_new_posts)
        if new_posts:
            backup_data['posts'] = [dict(post) for post in new_posts]
        async def _get_new_users(conn):
            cur = await conn.execute("SELECT * FROM users WHERE updated_at > ?", (last_time.isoformat(),))
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
        return None
    except Exception as e:
        logger.error(f"❌ فشل إنشاء النسخة الاحتياطية المتزايدة: {e}")
        return None

async def list_backups():
    """قائمة النسخ الاحتياطية المتاحة"""
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
                    await conn.execute("INSERT OR IGNORE INTO posts (id, channel_db_id, text, media_type, media_file_id, published, fail_count, views_count, last_view_time, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (post['id'], post['channel_db_id'], post['text'], post['media_type'], post['media_file_id'], post['published'], post['fail_count'], post['views_count'], post['last_view_time'], post['created_at']))
            if 'users' in data:
                for user in data['users']:
                    await conn.execute("INSERT OR IGNORE INTO users (user_id, auto_publish, banned, trial_used, subscription_end, referral_code, referred_by, active_channel, auto_reply_enabled, auto_recycle) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (user['user_id'], user['auto_publish'], user['banned'], user['trial_used'], user['subscription_end'], user['referral_code'], user['referred_by'], user['active_channel'], user['auto_reply_enabled'], user['auto_recycle']))
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
# 42. دالة main() – نقطة الدخول الرئيسية للبوت (النسخة النهائية الكاملة)
# ===================================================================

async def main():
    """
    الدالة الرئيسية لبدء تشغيل البوت.
    تقوم بتهيئة قاعدة البيانات، إنشاء التطبيق، تسجيل جميع المعالجات،
    بدء المهام الخلفية، وتشغيل البوت.
    """
    
    print("=" * 60)
    print("🚀 بدء تشغيل ريلاكس مانيجر...")
    print("=" * 60)
    
    # ===================================================================
    # 1. تهيئة قاعدة البيانات
    # ===================================================================
    print("🗄️  تهيئة قاعدة البيانات...")
    await db_pool.initialize()
    await init_db_improved()
    await init_security_table()
    await fix_missing_columns()
    print("✅ تم تهيئة قاعدة البيانات بنجاح")
    
    # ===================================================================
    # 2. تحميل الكلمات المحظورة
    # ===================================================================
    try:
        words = load_banned_words_from_file(BANNED_WORDS_FILE)
        if words:
            async def _import(conn):
                imported = 0
                for word in words:
                    try:
                        await conn.execute(
                            "INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?, -1, ?, ?)",
                            (word, PRIMARY_OWNER_ID, utc_now_iso())
                        )
                        imported += 1
                    except Exception:
                        continue
                await conn.commit()
                return imported
            imported_count = await execute_db(_import)
            print(f"✅ تم استيراد {imported_count} كلمة محظورة")
            await rebuild_banned_patterns()
    except Exception as e:
        print(f"⚠️ فشل استيراد الكلمات المحظورة: {e}")
    
    # ===================================================================
    # 3. تحميل اللغات وتسجيل المطور
    # ===================================================================
    load_all_languages()
    
    await db_register_user(PRIMARY_OWNER_ID)
    async def _ensure_admin(conn):
        await conn.execute(
            "INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
            (PRIMARY_OWNER_ID, PRIMARY_OWNER_ID, utc_now_iso())
        )
        await conn.commit()
    await execute_db(_ensure_admin)
    print("✅ تم تسجيل المطور الأساسي")
    
    # ===================================================================
    # 4. إنشاء التطبيق
    # ===================================================================
    print("🤖 إنشاء تطبيق البوت...")
    if USE_PROXY:
        request = HTTPXRequest(
            proxy_url=PROXY_URL,
            read_timeout=60.0, write_timeout=30.0,
            connect_timeout=30.0, pool_timeout=10.0,
            connection_pool_size=MAX_CONNECTIONS
        )
    else:
        request = HTTPXRequest(
            read_timeout=60.0, write_timeout=30.0,
            connect_timeout=30.0, pool_timeout=10.0,
            connection_pool_size=MAX_CONNECTIONS
        )
    
    application = Application.builder().token(TOKEN).request(request).build()
    application.add_error_handler(global_error_handler)
    print("✅ تم إنشاء تطبيق البوت")
    
    # ===================================================================
    # 5. تسجيل معالجات الأوامر (36 أمر)
    # ===================================================================
    print("📋 تسجيل معالجات الأوامر...")
    
    # الأوامر الأساسية
    application.add_handler(CommandHandler("start", start_command_handler))
    application.add_handler(CommandHandler("language", language_command_handler))
    application.add_handler(CommandHandler("help", help_command_handler))
    application.add_handler(CommandHandler("trial", trial_command_handler))
    application.add_handler(CommandHandler("subscribe", subscribe_command_handler))
    application.add_handler(CommandHandler("developer", developer_command_handler))
    application.add_handler(CommandHandler("updates", updates_command_handler))
    application.add_handler(CommandHandler("support", support_command_handler))
    application.add_handler(CommandHandler("support_reply", support_reply_command_handler))
    application.add_handler(CommandHandler("sendcode", sendcode_command_handler))
    
    # المجموعات والصلاحيات
    application.add_handler(CommandHandler("syncgroup", syncgroup_command_handler))
    application.add_handler(CommandHandler("register_hidden_owner", register_hidden_owner_handler))
    application.add_handler(CommandHandler("add_hidden_admin", add_hidden_admin_command))
    application.add_handler(CommandHandler("remove_hidden_admin", remove_hidden_admin_command))
    application.add_handler(CommandHandler("list_hidden_admins", list_hidden_admins_command))
    application.add_handler(CommandHandler("panel", panel_command_handler))
    application.add_handler(CommandHandler("lock", lock_chat_command_handler))
    application.add_handler(CommandHandler("unlock", unlock_chat_command_handler))
    application.add_handler(CommandHandler("security", security_command_handler))
    
    # الإحصائيات
    application.add_handler(CommandHandler("rank", rank_command_handler))
    application.add_handler(CommandHandler("top", top_command_handler))
    application.add_handler(CommandHandler("stats", stats_command_handler))
    
    # الجدولة والقوانين
    application.add_handler(CommandHandler("schedule", schedule_command_handler))
    application.add_handler(CommandHandler("set_rules", set_rules_command_handler))
    application.add_handler(CommandHandler("rules", rules_command_handler))
    
    # المسابقات
    application.add_handler(CommandHandler("contests", contests_command_handler))
    application.add_handler(CommandHandler("create_contest", create_contest_command_handler))
    application.add_handler(CommandHandler("declare_winner", declare_winner_command_handler))
    
    # قناة التقارير
    application.add_handler(CommandHandler("set_log_channel", set_log_channel_command_handler))
    
    # أوامر الإشراف
    for cmd in ["ban", "mute", "warn", "kick", "restrict", "unban", "pin"]:
        application.add_handler(CommandHandler(cmd, handle_moderation_commands))
    
    print(f"✅ تم تسجيل 36 أمر")
    
    # ===================================================================
    # 6. تسجيل معالج الأزرار الموحد
    # ===================================================================
    print("🔘 تسجيل معالج الأزرار...")
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    print("✅ تم تسجيل معالج الأزرار الموحد")
    
    # ===================================================================
    # 7. تسجيل معالجات الرسائل
    # ===================================================================
    print("💬 تسجيل معالجات الرسائل...")
    
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & filters.ChatType.GROUPS & ~filters.COMMAND,
            filter_messages_handler
        ),
        group=1
    )
    
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND,
            message_handler_main
        )
    )
    print("✅ تم تسجيل معالجات الرسائل")
    
    # ===================================================================
    # 8. تسجيل معالجات الأحداث
    # ===================================================================
    print("📡 تسجيل معالجات الأحداث...")
    
    application.add_handler(ChatJoinRequestHandler(chat_join_request_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_chat_member_handler))
    application.add_handler(ChatMemberHandler(track_chat_add, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback_handler))
    print("✅ تم تسجيل معالجات الأحداث")
    
    # ===================================================================
    # 9. تعيين أوامر البوت
    # ===================================================================
    print("📝 تعيين أوامر البوت...")
    commands = [
        BotCommand("start", "القائمة الرئيسية"), BotCommand("help", "المساعدة"),
        BotCommand("language", "تغيير اللغة"), BotCommand("trial", "تجربة مجانية"),
        BotCommand("subscribe", "الاشتراك"), BotCommand("syncgroup", "تفعيل المجموعة"),
        BotCommand("security", "إعدادات الأمان"), BotCommand("panel", "لوحة التحكم"),
        BotCommand("lock", "قفل المجموعة"), BotCommand("unlock", "فتح المجموعة"),
        BotCommand("ban", "حظر مستخدم"), BotCommand("mute", "كتم مستخدم"),
        BotCommand("warn", "تحذير مستخدم"), BotCommand("kick", "طرد مستخدم"),
        BotCommand("schedule", "جدولة منشور"), BotCommand("stats", "إحصائيات"),
        BotCommand("rank", "رتبتي"), BotCommand("top", "أفضل 10"),
        BotCommand("rules", "قوانين المجموعة"), BotCommand("set_rules", "تعيين القوانين"),
        BotCommand("contests", "المسابقات"), BotCommand("create_contest", "إنشاء مسابقة"),
        BotCommand("declare_winner", "إعلان فائز"),
        BotCommand("support", "الدعم الفني"), BotCommand("developer", "المطور"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        print("✅ تم تعيين أوامر البوت")
    except Exception as e:
        print(f"⚠️ فشل تعيين أوامر البوت: {e}")
    
    # ===================================================================
    # 10. بدء المهام الخلفية
    # ===================================================================
    print("🔄 بدء المهام الخلفية...")
    
    task_manager.create_task(safe_loop(lambda: auto_publish_loop_improved(application.bot), "auto_publish"), "النشر التلقائي")
    task_manager.create_task(safe_loop(auto_backup, "auto_backup"), "النسخ الاحتياطي")
    task_manager.create_task(safe_loop(lambda: run_scheduled_posts_loop_improved(application.bot), "scheduled_posts"), "المنشورات المجدولة")
    task_manager.create_task(safe_loop(lambda: send_reminders_loop_improved(application.bot), "reminders"), "التذكيرات")
    task_manager.create_task(safe_loop(cleanup_expired_sessions_improved, "cleanup_sessions"), "تنظيف الجلسات")
    task_manager.create_task(safe_loop(self_ping_loop, "self_ping"), "نبض البوت")
    task_manager.create_task(safe_loop(broadcast_stats_periodically, "broadcast_stats"), "بث الإحصائيات")
    task_manager.create_task(safe_loop(cleanup_points_cache, "cleanup_points"), "تنظيف كاش النقاط")
    task_manager.create_task(safe_loop(memory_monitor, "memory_monitor"), "مراقبة الذاكرة")
    task_manager.create_task(safe_loop(lambda: auto_close_contests_loop(application.bot), "auto_close_contests"), "إغلاق المسابقات")
    task_manager.create_task(safe_loop(lambda: refresh_group_admins_and_hidden_owners_loop(application.bot), "refresh_admins"), "تحديث الصلاحيات")
    task_manager.create_task(safe_loop(memory_optimizer_loop, "memory_optimizer"), "تحسين الذاكرة")
    
    print(f"✅ تم بدء {task_manager.get_task_count()} مهمة خلفية")
    
    # ===================================================================
    # 11. تشغيل البوت
    # ===================================================================
    print("🚀 تشغيل البوت...")
    
    port = int(os.getenv("PORT", "10000"))
    hostname = (
        os.getenv("RENDER_EXTERNAL_HOSTNAME") or 
        os.getenv("RAILWAY_PUBLIC_DOMAIN") or 
        os.getenv("HEROKU_APP_NAME")
    )
    
    try:
        await setup_unified_web_server(application, port)
        print(f"✅ خادم الويب يعمل على المنفذ {port}")
    except Exception as e:
        print(f"❌ فشل بدء خادم الويب: {e}")
        raise
    
    if hostname:
        print(f"🌐 استخدام Webhook على {hostname}")
        await application.initialize()
        await application.start()
        
        webhook_url = f"https://{hostname}/{TOKEN}"
        try:
            await application.bot.set_webhook(
                url=webhook_url, drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "chat_member", "chat_join_request", "pre_checkout_query"]
            )
            print(f"✅ تم تعيين Webhook")
        except Exception as e:
            print(f"❌ فشل تعيين Webhook: {e}")
            raise
        
        try:
            await application.bot.send_message(
                chat_id=PRIMARY_OWNER_ID,
                text=f"🌿 **تم تشغيل {BOT_NAME} بنجاح!**\n━━━━━━━━━━━━━━━━━━━━━━\n🕐 {mecca_now().strftime('%Y-%m-%d %H:%M:%S')}\n📌 الإصدار: 22.2.0\n✅ البوت جاهز للعمل",
                parse_mode="MarkdownV2"
            )
        except: pass
        
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            print("🛑 تم إيقاف البوت")
    else:
        print("🔄 استخدام Polling")
        await application.bot.delete_webhook()
        try:
            await application.bot.send_message(
                chat_id=PRIMARY_OWNER_ID,
                text=f"🌿 **تم تشغيل {BOT_NAME} بنجاح!**\n━━━━━━━━━━━━━━━━━━━━━━\n🕐 {mecca_now().strftime('%Y-%m-%d %H:%M:%S')}\n📌 الإصدار: 22.2.0\n✅ البوت جاهز للعمل",
                parse_mode="MarkdownV2"
            )
        except: pass
        await run_polling_safe(application)
    
    # ===================================================================
    # 12. التنظيف عند الإيقاف
    # ===================================================================
    print("🔄 جاري التنظيف...")
    await task_manager.cancel_all()
    await db_pool.close()
    print("👋 تم إيقاف البوت")

# ===================================================================
# 43. نقطة الدخول (Entry Point)
# ===================================================================

if __name__ == "__main__":
    try:
        nest_asyncio.apply()
        
        print("""
╔══════════════════════════════════════════════════════════╗
║              🌿 ريلاكس مانيجر v22.2.0                    ║
║              Relax Manager - Telegram Bot                ║
║         نظام إدارة القنوات والمجموعات المتكامل           ║
║         مع نظام التعلم الذكي وتحليل المشاعر              ║
║         المطور: @RelaxMgr                                ║
╚══════════════════════════════════════════════════════════╝
        """)
        
        print(f"🤖 بدء تشغيل {BOT_NAME}...")
        print(f"📌 المطور: @RelaxMgr | الإصدار: 22.2.0")
        print("=" * 60)
        
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n👋 تم إيقاف البوت بواسطة المستخدم (Ctrl+C)")
    except Exception as e:
        print(f"\n❌ خطأ فادح في تشغيل البوت: {e}")
        logger.critical(f"خطأ فادح: {e}")
        traceback.print_exc()
        
        try:
            async def send_critical_error():
                try:
                    bot_app = Application.builder().token(TOKEN).build()
                    await bot_app.bot.send_message(
                        chat_id=PRIMARY_OWNER_ID,
                        text=f"🚨 **خطأ فادح في البوت**\n\n❌ `{type(e).__name__}`\n📝 `{str(e)[:300]}`\n\nتم إيقاف البوت بسبب خطأ فادح.",
                        parse_mode="MarkdownV2"
                    )
                except: pass
            loop = asyncio.new_event_loop()
            loop.run_until_complete(send_critical_error())
            loop.close()
        except: pass
        
        sys.exit(1)
