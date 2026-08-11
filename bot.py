#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ريلاكس مانيجر - النسخة الذكية المتطورة
الإصدار: 22.0.0 - مع نظام تعلم ذاتي وتحليل مشاعر
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
# 1. check_python_version - محسنة مع دعم متقدم
# ===================================================================
def check_python_version():
    required_version = (3, 9)
    current_version = sys.version_info
    if current_version < required_version:
        print(f"❌ يحتاج البوت إلى بايثون {required_version[0]}.{required_version[1]} أو أحدث")
        print(f"📌 الإصدار الحالي: {current_version[0]}.{current_version[1]}")
        print("\n💡 **حلول:**")
        print("1️⃣ قم بتثبيت بايثون أحدث من: https://python.org")
        print("2️⃣ استخدم pyenv لتبديل الإصدارات")
        try:
            for ver in ['python3.9', 'python3.10', 'python3.11', 'python3.12']:
                result = subprocess.run(['which', ver], capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"\n✅ تم العثور على {ver} في: {result.stdout.strip()}")
                    print(f"📌 استخدم: {ver} bot.py")
                    break
        except:
            pass
        sys.exit(1)
    print(f"✅ بايثون {current_version[0]}.{current_version[1]} - متوافق")
check_python_version()

# ===================================================================
# 2. تثبيت الحزم الأساسية مع دعم الإصدارات
# ===================================================================
def ensure_package(package_name: str, import_name: str = None, version: str = None) -> bool:
    if import_name is None:
        import_name = package_name
    try:
        if version:
            __import__(import_name)
            import pkg_resources
            installed_version = pkg_resources.get_distribution(package_name).version
            if installed_version != version:
                print(f"⚠️ الإصدار المثبت {installed_version} مختلف عن المطلوب {version}")
        else:
            __import__(import_name)
        return True
    except (ImportError, pkg_resources.DistributionNotFound):
        try:
            print(f"📦 جاري تثبيت {package_name}...")
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade"]
            if version:
                cmd.append(f"{package_name}=={version}")
            else:
                cmd.append(package_name)
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                cmd = [sys.executable, "-m", "pip", "install"]
                if version:
                    cmd.append(f"{package_name}=={version}")
                else:
                    cmd.append(package_name)
                subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        "/etc/bot/.env",
        "/opt/bot/.env",
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
# 4. نظام التعلم الذاتي وتحليل المشاعر (بدون ذكاء اصطناعي خارجي)
# ===================================================================
class SentimentAnalyzer:
    """محلل مشاعر بسيط يعتمد على قوائم كلمات وإحصائيات"""
    
    def __init__(self):
        # قوائم الكلمات الإيجابية والسلبية والمحايدة
        self.positive_words = {
            "جميل", "رائع", "ممتاز", "جميلة", "رائعة", "ممتازة", "حلو", "حلوة",
            "نور", "نورت", "شكر", "شكراً", "شكرا", "تسلم", "تسلمي", "يسلمو",
            "فرح", "سعيد", "سعيدة", "مبسوط", "مبسوطة", "مرح", "ضحك", "هههه",
            "أهلاً", "مرحباً", "اهلا", "مرحبا", "حياك", "الله", "ربي", "الحمد",
            "تفاؤل", "أمل", "نجاح", "مبدع", "رائع", "خير", "بركة", "نعمة"
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
        
        # مخزن التعلم التكيفي
        self.learned_patterns = defaultdict(lambda: {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0})
        self.learned_phrases = {}
        self.learning_data = {}
        self._load_learned_data()
    
    def _load_learned_data(self):
        """تحميل بيانات التعلم من قاعدة البيانات أو ملف"""
        try:
            # محاولة تحميل من قاعدة البيانات
            # هذا سيتم تنفيذه لاحقاً عند تهيئة قاعدة البيانات
            pass
        except:
            pass
    
    def _save_learned_data(self):
        """حفظ بيانات التعلم"""
        try:
            # حفظ في قاعدة البيانات
            pass
        except:
            pass
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """تحليل مشاعر النص وإرجاع النتيجة مع التفاصيل"""
        if not text:
            return {'sentiment': 'neutral', 'score': 0.0, 'confidence': 0.0, 'details': {}}
        
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        
        positive_count = sum(1 for w in words if w in self.positive_words)
        negative_count = sum(1 for w in words if w in self.negative_words)
        neutral_count = sum(1 for w in words if w in self.neutral_words)
        
        # حساب النتيجة
        total = positive_count + negative_count + neutral_count
        if total == 0:
            # استخدام الكلمات المتعلمة
            learned_sentiment = self._analyze_learned(text)
            if learned_sentiment:
                return learned_sentiment
        
        # حساب النسبة المئوية
        pos_ratio = positive_count / max(total, 1)
        neg_ratio = negative_count / max(total, 1)
        neu_ratio = neutral_count / max(total, 1)
        
        # حساب النتيجة الإجمالية من -1 إلى 1
        score = pos_ratio - neg_ratio
        
        # تحديد المشاعر
        if score > 0.2:
            sentiment = 'positive'
        elif score < -0.2:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        # حساب الثقة
        confidence = min(1.0, (total / 10) * 0.8 + 0.2)
        
        # حفظ التعلم
        self._learn_pattern(text, sentiment, score)
        
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
    
    def _analyze_learned(self, text: str) -> Optional[Dict]:
        """تحليل النص باستخدام الأنماط المتعلمة"""
        text_lower = text.lower()
        best_match = None
        best_score = 0
        
        for pattern, data in self.learned_patterns.items():
            if pattern in text_lower:
                pos_ratio = data['positive'] / max(data['total'], 1)
                neg_ratio = data['negative'] / max(data['total'], 1)
                score = pos_ratio - neg_ratio
                confidence = min(1.0, data['total'] / 20)
                
                if confidence > best_score:
                    best_score = confidence
                    if score > 0.2:
                        sentiment = 'positive'
                    elif score < -0.2:
                        sentiment = 'negative'
                    else:
                        sentiment = 'neutral'
                    
                    best_match = {
                        'sentiment': sentiment,
                        'score': round(score, 3),
                        'confidence': round(confidence, 3),
                        'details': {'learned': True, 'total': data['total']}
                    }
        
        return best_match
    
    def _learn_pattern(self, text: str, sentiment: str, score: float):
        """تعلم نمط جديد من النص"""
        # استخراج الكلمات المفتاحية
        words = re.findall(r'\b\w+\b', text.lower())
        for word in words:
            if len(word) > 2:
                self.learned_patterns[word]['total'] += 1
                if sentiment == 'positive':
                    self.learned_patterns[word]['positive'] += 1
                elif sentiment == 'negative':
                    self.learned_patterns[word]['negative'] += 1
                else:
                    self.learned_patterns[word]['neutral'] += 1
        
        # حفظ التعلم بشكل دوري
        if random.random() < 0.1:
            self._save_learned_data()
    
    def get_word_sentiment(self, word: str) -> float:
        """الحصول على درجة المشاعر لكلمة محددة"""
        word = word.lower()
        if word in self.positive_words:
            return 1.0
        if word in self.negative_words:
            return -1.0
        if word in self.neutral_words:
            return 0.0
        
        # استخدام التعلم
        if word in self.learned_patterns:
            data = self.learned_patterns[word]
            pos_ratio = data['positive'] / max(data['total'], 1)
            neg_ratio = data['negative'] / max(data['total'], 1)
            return pos_ratio - neg_ratio
        
        return 0.0

class LearningEngine:
    """محرك التعلم الذاتي للبوت"""
    
    def __init__(self):
        self.sentiment_analyzer = SentimentAnalyzer()
        self.user_patterns = defaultdict(lambda: {'messages': [], 'sentiment_history': [], 'avg_sentiment': 0})
        self.chat_patterns = defaultdict(lambda: {'messages': [], 'sentiment_history': [], 'avg_sentiment': 0})
        self.response_patterns = defaultdict(lambda: {'success': 0, 'fail': 0, 'score': 0})
        self._load_learning_data()
    
    def _load_learning_data(self):
        """تحميل بيانات التعلم من قاعدة البيانات"""
        try:
            # سيتم تنفيذها مع قاعدة البيانات
            pass
        except:
            pass
    
    def _save_learning_data(self):
        """حفظ بيانات التعلم"""
        try:
            # سيتم تنفيذها مع قاعدة البيانات
            pass
        except:
            pass
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """تحليل مشاعر النص"""
        return self.sentiment_analyzer.analyze(text)
    
    def learn_from_message(self, user_id: int, chat_id: int, text: str, response: str = None, success: bool = True):
        """تعلم من الرسالة والاستجابة"""
        # تحليل المشاعر
        sentiment = self.analyze_sentiment(text)
        
        # تحديث نمط المستخدم
        self.user_patterns[user_id]['messages'].append({
            'text': text,
            'sentiment': sentiment['sentiment'],
            'score': sentiment['score'],
            'time': time_module.time()
        })
        self.user_patterns[user_id]['sentiment_history'].append(sentiment['score'])
        if len(self.user_patterns[user_id]['sentiment_history']) > 100:
            self.user_patterns[user_id]['sentiment_history'] = self.user_patterns[user_id]['sentiment_history'][-100:]
        self.user_patterns[user_id]['avg_sentiment'] = statistics.mean(self.user_patterns[user_id]['sentiment_history']) if self.user_patterns[user_id]['sentiment_history'] else 0
        
        # تحديث نمط المجموعة
        self.chat_patterns[chat_id]['messages'].append({
            'text': text,
            'sentiment': sentiment['sentiment'],
            'score': sentiment['score'],
            'time': time_module.time()
        })
        self.chat_patterns[chat_id]['sentiment_history'].append(sentiment['score'])
        if len(self.chat_patterns[chat_id]['sentiment_history']) > 100:
            self.chat_patterns[chat_id]['sentiment_history'] = self.chat_patterns[chat_id]['sentiment_history'][-100:]
        self.chat_patterns[chat_id]['avg_sentiment'] = statistics.mean(self.chat_patterns[chat_id]['sentiment_history']) if self.chat_patterns[chat_id]['sentiment_history'] else 0
        
        # تحديث نمط الاستجابة
        if response:
            key = f"{text[:50]}_{response[:50]}"
            if success:
                self.response_patterns[key]['success'] += 1
            else:
                self.response_patterns[key]['fail'] += 1
            self.response_patterns[key]['score'] = self.response_patterns[key]['success'] / max(self.response_patterns[key]['success'] + self.response_patterns[key]['fail'], 1)
        
        # حفظ التعلم بشكل دوري
        if random.random() < 0.05:
            self._save_learning_data()
    
    def get_user_sentiment_profile(self, user_id: int) -> Dict[str, Any]:
        """الحصول على ملف المشاعر للمستخدم"""
        if user_id not in self.user_patterns:
            return {'avg_sentiment': 0, 'stability': 0, 'messages': 0}
        
        data = self.user_patterns[user_id]
        history = data['sentiment_history']
        if not history:
            return {'avg_sentiment': 0, 'stability': 0, 'messages': 0}
        
        avg_sentiment = statistics.mean(history)
        stability = 1 - (statistics.stdev(history) if len(history) > 1 else 0)
        
        return {
            'avg_sentiment': round(avg_sentiment, 3),
            'stability': round(min(1.0, stability), 3),
            'messages': len(history),
            'trend': self._calculate_trend(history)
        }
    
    def get_chat_sentiment_profile(self, chat_id: int) -> Dict[str, Any]:
        """الحصول على ملف المشاعر للمجموعة"""
        if chat_id not in self.chat_patterns:
            return {'avg_sentiment': 0, 'stability': 0, 'messages': 0}
        
        data = self.chat_patterns[chat_id]
        history = data['sentiment_history']
        if not history:
            return {'avg_sentiment': 0, 'stability': 0, 'messages': 0}
        
        avg_sentiment = statistics.mean(history)
        stability = 1 - (statistics.stdev(history) if len(history) > 1 else 0)
        
        return {
            'avg_sentiment': round(avg_sentiment, 3),
            'stability': round(min(1.0, stability), 3),
            'messages': len(history),
            'trend': self._calculate_trend(history)
        }
    
    def _calculate_trend(self, history: List[float]) -> str:
        """حساب اتجاه المشاعر"""
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
    
    def suggest_response(self, text: str, user_id: int = None, chat_id: int = None) -> Optional[str]:
        """اقتراح استجابة ذكية بناءً على التحليل والتعلم"""
        # تحليل المشاعر
        sentiment = self.analyze_sentiment(text)
        
        # البحث عن أفضل استجابة متعلمة
        best_response = None
        best_score = 0
        
        for pattern, data in self.response_patterns.items():
            if pattern.startswith(text[:30]):
                if data['score'] > best_score:
                    best_score = data['score']
                    best_response = pattern.split('_')[-1]
        
        if best_response and best_score > 0.6:
            return best_response
        
        # استجابات ذكية بناءً على المشاعر
        if sentiment['sentiment'] == 'positive':
            responses = [
                "😊 سعيد أنك في مزاج جيد!",
                "🌹 كلماتك الجميلة تشرح الصدر!",
                "🌟 وجودك معنا يسعدنا!",
                "💫 فرحتنا بفرحك!"
            ]
            return random.choice(responses)
        
        elif sentiment['sentiment'] == 'negative':
            responses = [
                "😔 آسف أنك تشعر بهذا، كل شيء سيكون بخير.",
                "🌷 الحياة أجمل من أن تحزن، ابتسم.",
                "💪 أنت أقوى من ذلك، ستتجاوز هذا.",
                "🤗 لا تنسى أننا هنا لدعمك."
            ]
            return random.choice(responses)
        
        else:
            responses = [
                "📝 فهمت، كيف يمكنني مساعدتك؟",
                "👂 أنا هنا للإستماع إليك.",
                "💬 أخبرني المزيد.",
                "🤖 تحت أمرك، ماذا تريد؟"
            ]
            return random.choice(responses)
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """الحصول على إحصائيات التعلم"""
        total_users = len(self.user_patterns)
        total_chats = len(self.chat_patterns)
        total_patterns = len(self.response_patterns)
        
        return {
            'users_learned': total_users,
            'chats_learned': total_chats,
            'patterns_learned': total_patterns,
            'avg_user_sentiment': statistics.mean([self.user_patterns[u]['avg_sentiment'] for u in self.user_patterns]) if self.user_patterns else 0,
            'avg_chat_sentiment': statistics.mean([self.chat_patterns[c]['avg_sentiment'] for c in self.chat_patterns]) if self.chat_patterns else 0
        }

# إنشاء محرك التعلم العالمي
learning_engine = LearningEngine()

# ===================================================================
# 5. دوال مساعدة ذكية
# ===================================================================
async def is_user_bot(bot, user_id: int) -> bool:
    try:
        chat = await bot.get_chat(user_id)
        return chat.is_bot
    except Exception:
        return False

async def is_anonymous_admin(update: Update) -> bool:
    if not update.effective_user:
        return False
    return update.effective_user.id == ANONYMOUS_ADMIN_ID

async def get_real_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id == ANONYMOUS_ADMIN_ID:
        async def _get_real(conn):
            cur = await conn.execute(
                "SELECT user_id FROM anonymous_admins WHERE chat_id=? AND anonymous_id=?",
                (update.effective_chat.id, user_id)
            )
            row = await cur.fetchone()
            return row[0] if row else None
        real_id = await execute_db(_get_real)
        if real_id:
            return real_id
        try:
            admins = await context.bot.get_chat_administrators(update.effective_chat.id)
            if admins:
                for admin in admins:
                    if admin.status == 'creator':
                        return admin.user.id
                for admin in admins:
                    if admin.user.id != context.bot.id:
                        return admin.user.id
        except:
            pass
        return user_id
    return user_id

# ===================================================================
# 6. إعداد المسارات الذكية
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
        Path(f"/var/lib/bot/{subdir}"),
        Path(f"/opt/bot/{subdir}"),
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

for path in [DATA_PATH, BACKUP_DIR, LOG_PATH.parent, TEMP_PATH, STATIC_PATH,
             TEMPLATES_PATH, LANG_PATH, PLUGINS_PATH]:
    path.mkdir(parents=True, exist_ok=True)

# ===================================================================
# 7. تحميل متغيرات البيئة الذكية
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
    print("💡 تأكد من وجود ملف .env أو تعيين المتغير البيئي")
    sys.exit(1)

PRIMARY_OWNER_ID = get_env_or_default("MAIN_ADMIN_ID", 0, int)
if PRIMARY_OWNER_ID == 0:
    print("❌ MAIN_ADMIN_ID غير محدد في ملفات البيئة")
    print("💡 أضف MAIN_ADMIN_ID=your_telegram_id إلى ملف .env")
    sys.exit(1)

BOT_NAME = get_env_or_default("BOT_NAME", "ريلاكس مانيجر", str)
BOT_USERNAME = get_env_or_default("BOT_USERNAME", "Reelaaaxbot", str)
USE_PROXY = get_env_or_default("USE_PROXY", False, bool)
PROXY_URL = get_env_or_default("PROXY_URL", "http://127.0.0.1:10809", str)
ENABLE_2FA = get_env_or_default("ENABLE_2FA", False, bool)
ADMIN_2FA_SECRET = get_env_or_default("ADMIN_2FA_SECRET", "", str)
DB_ENCRYPTION = get_env_or_default("DB_ENCRYPTION", True, bool)
MAX_BACKUPS = get_env_or_default("MAX_BACKUPS", 10, int)
SECURITY_LOG_LEVEL = get_env_or_default("SECURITY_LOG_LEVEL", "CRITICAL", str)
RENDER_PORT = int(os.getenv("PORT", "10000"))
WEB_PORT = get_env_or_default("WEB_PORT", RENDER_PORT, int)
WEB_HOST = get_env_or_default("WEB_HOST", "0.0.0.0", str)
WEB_PASSWORD = get_env_or_default("WEB_PASSWORD", "", str)
if not WEB_PASSWORD and os.getenv('ENVIRONMENT', 'development') == 'production':
    WEB_PASSWORD = secrets.token_urlsafe(16)
    print(f"🔑 كلمة المرور المؤقتة للويب: {WEB_PASSWORD}")
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
LEARNING_ENABLED = get_env_or_default("LEARNING_ENABLED", True, bool)

# ===================================================================
# 8. ثوابت المجموعات المحسنة
# ===================================================================
_MAX_BANNED_WORDS_PER_CHAT = 500
_MAX_BANNED_WORDS_GLOBAL = 2000
_MAX_AUTH_CACHE_SIZE = 50000
_MAX_FAILED_ATTEMPTS = 10
_FAILED_ATTEMPTS_WINDOW = 300
_TOKEN_EXPIRY = 300
_AUTH_CACHE_TTL = 300
_FLOOD_CACHE_MAX_SIZE = 10000

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
# 9. نظام السجلات الذكي
# ===================================================================
class SensitiveDataFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.sensitive_patterns = [
            (TOKEN, "[TOKEN_HIDDEN]"),
            (WEB_PASSWORD, "[WEB_PASSWORD_HIDDEN]"),
            (WEB_SECRET_KEY, "[WEB_SECRET_HIDDEN]"),
        ]
        if ADMIN_2FA_SECRET:
            self.sensitive_patterns.append((ADMIN_2FA_SECRET, "[2FA_SECRET_HIDDEN]"))
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
        error_logger.addFilter(SensitiveDataFilter())
        self.loggers['error'] = error_logger
        access_logger = logging.getLogger('access_logger')
        access_logger.setLevel(logging.INFO)
        access_handler = RotatingFileHandler(ACCESS_LOG, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        access_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        access_logger.addHandler(access_handler)
        access_logger.addFilter(SensitiveDataFilter())
        self.loggers['access'] = access_logger
        security_logger = logging.getLogger('security_logger')
        security_logger.setLevel(logging.WARNING)
        security_handler = RotatingFileHandler(SECURITY_LOG, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        security_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        security_logger.addHandler(security_handler)
        security_logger.addFilter(SensitiveDataFilter())
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
            safe_context = {k: v for k, v in context.items() if k not in ['token', 'password', 'key', 'secret', 'api_key', 'auth']}
            log_msg += f" - السياق: {json.dumps(safe_context, default=str)[:300]}"
        self.loggers['error'].error(log_msg)
        traceback.print_exc()
        self.error_counter[error_id] = self.error_counter.get(error_id, 0) + 1
        return error_id
    def log_access(self, user_id: int, action: str, details: dict = None):
        log_msg = f"User: {user_id} - Action: {action}"
        if details:
            safe_details = {k: v for k, v in details.items() if k not in ['token', 'password', 'key', 'secret']}
            log_msg += f" - {json.dumps(safe_details, default=str)[:200]}"
        self.loggers['access'].info(log_msg)
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
# 10. نظام التشفير المتطور
# ===================================================================
def derive_key_from_password(password: str, salt: bytes) -> bytes:
    if ARGON2_AVAILABLE:
        try:
            ph = PasswordHasher(time_cost=3, memory_cost=32768, parallelism=2, hash_len=32)
            hash_value = ph.hash(password)
            return base64.urlsafe_b64encode(hashlib.sha256(hash_value.encode()).digest())
        except Exception as e:
            logger.warning(f"فشل استخدام Argon2، التبديل إلى PBKDF2: {e}")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=150000)
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

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
        print("⚠️ تم توليد مفتاح تشفير عشوائي (بدون كلمة مرور)")
        return key
    try:
        print("🔐 لإعداد تشفير قاعدة البيانات، أدخل كلمة مرور قوية:")
        password = getpass.getpass("كلمة المرور: ")
        confirm = getpass.getpass("تأكيد كلمة المرور: ")
        if password != confirm:
            print("❌ كلمات المرور غير متطابقة!")
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            print("⚠️ تم توليد مفتاح عشوائي بدلاً من ذلك")
            return key
        if len(password) < 8:
            print("❌ كلمة المرور يجب أن تكون 8 أحرف على الأقل!")
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            print("⚠️ تم توليد مفتاح عشوائي بدلاً من ذلك")
            return key
        salt = os.urandom(16)
        key = derive_key_from_password(password, salt)
        with open(key_file, 'wb') as f:
            f.write(key)
        with open(salt_file, 'wb') as f:
            f.write(salt)
        print("✅ تم إنشاء مفتاح التشفير وحفظه بشكل آمن")
        return key
    except Exception as e:
        print(f"⚠️ فشل في طلب كلمة المرور: {e}")
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

def encrypt_db_backup() -> Path:
    if not DB_ENCRYPTION:
        return DB_PATH
    encrypted_path = DB_PATH.with_suffix('.enc')
    encrypt_file_stream(DB_PATH, encrypted_path, cipher_suite)
    return encrypted_path

# ===================================================================
# 11. نظام التخزين المؤقت الذكي
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
_user_translation_cache_lock = asyncio.Lock()
_BANNED_PATTERNS_LOCK = asyncio.Lock()
BANNED_PATTERNS = []
# ===================================================================
# 12. نظام قاعدة البيانات المتطور
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
                await self._pool.execute("PRAGMA wal_autocheckpoint=1000")
                await self._pool.execute("PRAGMA optimize")
                await self._pool.execute("PRAGMA max_page_count=1000000")
                await self._pool.execute("PRAGMA secure_delete=ON")
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
    async def execute(self, query: str, params: tuple = None):
        conn = await self.get_connection()
        try:
            async with conn.execute(query, params or ()) as cursor:
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"خطأ في تنفيذ الاستعلام: {e}\n{query}")
            raise
    async def execute_many(self, queries: List[Tuple[str, tuple]]):
        conn = await self.get_connection()
        async with conn:
            for query, params in queries:
                await conn.execute(query, params)
            await conn.commit()
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
    try:
        conn = await db_pool.get_connection()
        result = await func(conn)
        return result
    except Exception as e:
        logger.error(f"خطأ في قاعدة البيانات: {e}")
        raise

# ===================================================================
# 13. إنشاء الجداول المتطورة (مع جداول التعلم)
# ===================================================================
# ===================================================================
# 16. إنشاء الجداول المتطورة (مع جميع الجداول والفهارس والأمان)
# ===================================================================

async def init_db_improved():
    """
    تهيئة قاعدة البيانات المتطورة مع جميع الجداول والفهارس والإعدادات.
    تدعم الترقية التلقائية وإضافة الأعمدة المفقودة.
    """
    try:
        async def _init(conn):
            # ===================================================================
            # 1. تمكين إعدادات SQLite المتقدمة
            # ===================================================================
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute("PRAGMA cache_size=-64000")
            await conn.execute("PRAGMA temp_store=MEMORY")
            await conn.execute("PRAGMA wal_autocheckpoint=1000")
            await conn.execute("PRAGMA optimize")
            await conn.execute("PRAGMA max_page_count=1000000")
            await conn.execute("PRAGMA secure_delete=ON")
            await conn.execute("PRAGMA busy_timeout=30000")
            await conn.execute("PRAGMA mmap_size=30000000000")
            
            logger.info("🔧 تم تفعيل إعدادات SQLite المتقدمة")
            
            # ===================================================================
            # 2. إنشاء الجداول الأساسية
            # ===================================================================
            
            # 2.1 جدول المستخدمين (Users) - متطور مع دعم الإنجازات
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
                    auto_reply_enabled INTEGER DEFAULT 1,
                    referral_code TEXT UNIQUE,
                    referral_reward_days INTEGER DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT,
                    active_channel INTEGER,
                    level INTEGER DEFAULT 1,
                    achievements TEXT DEFAULT '[]',
                    last_daily_reward TEXT,
                    last_weekly_reward TEXT,
                    referred_by INTEGER,
                    points INTEGER DEFAULT 0,
                    warning_count INTEGER DEFAULT 0,
                    last_activity TEXT,
                    is_verified INTEGER DEFAULT 0,
                    twofa_secret TEXT,
                    twofa_enabled INTEGER DEFAULT 0
                )
            """)
            logger.info("✅ جدول users")
            
            # 2.2 جدول ذاكرة التخزين المؤقت للمستخدمين
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users_cache (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_updated TEXT
                )
            """)
            logger.info("✅ جدول users_cache")
            
            # 2.3 جدول مستويات المستخدمين
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_levels (
                    user_id INTEGER PRIMARY KEY,
                    points INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    total_points INTEGER DEFAULT 0,
                    rank INTEGER DEFAULT 0,
                    last_updated TEXT
                )
            """)
            logger.info("✅ جدول user_levels")
            
            # ===================================================================
            # 3. جداول القنوات والمنشورات
            # ===================================================================
            
            # 3.1 جدول قنوات المستخدمين
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    channel_id TEXT,
                    channel_name TEXT,
                    banned INTEGER DEFAULT 0,
                    created_at TEXT,
                    last_post_time TEXT,
                    total_posts INTEGER DEFAULT 0,
                    total_views INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            logger.info("✅ جدول user_channels")
            
            # 3.2 جدول قنوات البوت
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_channels (
                    channel_id INTEGER PRIMARY KEY,
                    channel_name TEXT,
                    added_by INTEGER,
                    added_at TEXT,
                    banned INTEGER DEFAULT 0,
                    subscribers INTEGER DEFAULT 0,
                    last_activity TEXT
                )
            """)
            logger.info("✅ جدول bot_channels")
            
            # 3.3 جدول المنشورات (متطور)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_db_id INTEGER,
                    text TEXT,
                    media_type TEXT,
                    media_file_id TEXT,
                    published INTEGER DEFAULT 0,
                    views_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    published_at TEXT,
                    last_view_time TEXT,
                    sentiment_score REAL DEFAULT 0,
                    sentiment_label TEXT DEFAULT 'neutral',
                    is_scheduled INTEGER DEFAULT 0,
                    scheduled_for TEXT,
                    is_edited INTEGER DEFAULT 0,
                    edited_at TEXT,
                    FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
                )
            """)
            logger.info("✅ جدول posts")
            
            # ===================================================================
            # 4. جداول الجدولة والنشر
            # ===================================================================
            
            # 4.1 جدول الجدولة
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
                    last_executed TEXT,
                    is_paused INTEGER DEFAULT 0,
                    FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
                )
            """)
            logger.info("✅ جدول schedule")
            
            # 4.2 جدول آخر وقت نشر
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS last_publish (
                    channel_db_id INTEGER PRIMARY KEY,
                    last_publish_time TEXT,
                    last_post_id INTEGER,
                    total_published INTEGER DEFAULT 0,
                    FOREIGN KEY (channel_db_id) REFERENCES user_channels(id)
                )
            """)
            logger.info("✅ جدول last_publish")
            
            # 4.3 جدول المنشورات المجدولة
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    text TEXT,
                    media_type TEXT,
                    media_file_id TEXT,
                    publish_time TEXT,
                    fail_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    last_attempt TEXT,
                    is_sent INTEGER DEFAULT 0
                )
            """)
            logger.info("✅ جدول scheduled_posts")
            
            # ===================================================================
            # 5. جداول المجموعات والصلاحيات
            # ===================================================================
            
            # 5.1 جدول مجموعات البوت
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_groups (
                    chat_id INTEGER PRIMARY KEY,
                    chat_name TEXT,
                    username TEXT,
                    added_by INTEGER,
                    added_at TEXT,
                    updated_at TEXT,
                    banned INTEGER DEFAULT 0,
                    members_count INTEGER DEFAULT 0,
                    admins_count INTEGER DEFAULT 0,
                    last_activity TEXT,
                    is_active INTEGER DEFAULT 1
                )
            """)
            logger.info("✅ جدول bot_groups")
            
            # 5.2 جدول مشرفي المجموعات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS group_admins (
                    chat_id INTEGER,
                    user_id INTEGER,
                    is_hidden INTEGER DEFAULT 0,
                    added_at TEXT,
                    PRIMARY KEY (chat_id, user_id)
                )
            """)
            logger.info("✅ جدول group_admins")
            
            # 5.3 جدول الملاك المخفيين
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS hidden_owner_groups (
                    chat_id INTEGER PRIMARY KEY,
                    owner_id INTEGER,
                    is_hidden INTEGER DEFAULT 1,
                    created_at TEXT,
                    verified INTEGER DEFAULT 0
                )
            """)
            logger.info("✅ جدول hidden_owner_groups")
            
            # 5.4 جدول المشرفين المخفيين
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS hidden_admins (
                    chat_id INTEGER,
                    admin_id INTEGER,
                    added_by INTEGER,
                    added_at TEXT,
                    is_active INTEGER DEFAULT 1,
                    PRIMARY KEY (chat_id, admin_id)
                )
            """)
            logger.info("✅ جدول hidden_admins")
            
            # 5.5 جدول ربط المستخدمين بالمجموعات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_groups_link (
                    user_id INTEGER,
                    chat_id INTEGER,
                    created_at TEXT,
                    is_admin INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, chat_id)
                )
            """)
            logger.info("✅ جدول user_groups_link")
            
            # 5.6 جدول قوانين المجموعة
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS group_rules (
                    chat_id INTEGER PRIMARY KEY,
                    rules_text TEXT,
                    updated_by INTEGER,
                    updated_at TEXT,
                    version INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1
                )
            """)
            logger.info("✅ جدول group_rules")
            
            # ===================================================================
            # 6. جداول الأمان والعقوبات (متطورة)
            # ===================================================================
            
            # 6.1 جدول إعدادات الأمان للمجموعة
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
                    night_mode_action TEXT DEFAULT 'mute',
                    captcha_enabled INTEGER DEFAULT 0,
                    captcha_timeout INTEGER DEFAULT 60,
                    max_links_per_message INTEGER DEFAULT 0,
                    max_mentions_per_message INTEGER DEFAULT 0,
                    allowed_domains TEXT DEFAULT '[]'
                )
            """)
            logger.info("✅ جدول group_security")
            
            # 6.2 جدول قفل المجموعة
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_locks (
                    chat_id INTEGER PRIMARY KEY,
                    locked INTEGER DEFAULT 0,
                    locked_at TEXT,
                    locked_by INTEGER,
                    reason TEXT,
                    auto_unlock_at TEXT
                )
            """)
            logger.info("✅ جدول chat_locks")
            
            # 6.3 جدول رسائل المستخدمين (للتحكم في التدفق)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_messages (
                    user_id INTEGER,
                    chat_id INTEGER,
                    message_time TEXT,
                    message_count INTEGER DEFAULT 1,
                    last_message_id INTEGER,
                    PRIMARY KEY (user_id, chat_id)
                )
            """)
            logger.info("✅ جدول user_messages")
            
            # 6.4 جدول الكلمات المحظورة
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS banned_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL,
                    chat_id INTEGER DEFAULT -1,
                    added_by INTEGER,
                    added_at TEXT,
                    severity INTEGER DEFAULT 1,
                    UNIQUE(word, chat_id)
                )
            """)
            logger.info("✅ جدول banned_words")
            
            # 6.5 جدول سجل الإجراءات الإشرافية
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS moderation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    action TEXT,
                    duration_minutes INTEGER,
                    moderator_id INTEGER,
                    reason TEXT,
                    created_at TEXT,
                    expires_at TEXT,
                    is_active INTEGER DEFAULT 1
                )
            """)
            logger.info("✅ جدول moderation_log")
            
            # 6.6 جدول تحذيرات المستخدمين
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_warnings (
                    user_id INTEGER,
                    chat_id INTEGER,
                    warnings INTEGER DEFAULT 0,
                    updated_at TEXT,
                    last_warning TEXT,
                    PRIMARY KEY (user_id, chat_id)
                )
            """)
            logger.info("✅ جدول user_warnings")
            
            # ===================================================================
            # 7. جداول الإحالات والمكافآت
            # ===================================================================
            
            # 7.1 جدول الإحالات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER,
                    referred_id INTEGER,
                    created_at TEXT,
                    reward_claimed INTEGER DEFAULT 0,
                    reward_amount INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    UNIQUE(referrer_id, referred_id)
                )
            """)
            logger.info("✅ جدول referrals")
            
            # 7.2 جدول إعدادات الإحالات
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
                    ('welcome_bonus_points', '10'),
                    ('min_referrals_for_reward', '1'),
                    ('reward_cooldown_days', '1')
            """)
            logger.info("✅ جدول referral_settings")
            
            # ===================================================================
            # 8. جداول الدعم والتذاكر
            # ===================================================================
            
            # 8.1 جدول تذاكر الدعم
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    message TEXT,
                    ticket_number INTEGER,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT,
                    replied INTEGER DEFAULT 0,
                    priority TEXT DEFAULT 'normal',
                    assigned_to INTEGER,
                    resolved_at TEXT
                )
            """)
            logger.info("✅ جدول support_tickets")
            
            # ===================================================================
            # 9. جداول التذكيرات والترجمة
            # ===================================================================
            
            # 9.1 جدول إعدادات التذكيرات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_reminder_settings (
                    user_id INTEGER PRIMARY KEY,
                    subscription_reminder INTEGER DEFAULT 1,
                    daily_stats_reminder INTEGER DEFAULT 0,
                    weekly_report INTEGER DEFAULT 1,
                    reminder_days_before INTEGER DEFAULT 3,
                    last_reminder_sent INTEGER DEFAULT 0,
                    notification_lang TEXT DEFAULT 'ar',
                    reminder_time TEXT DEFAULT '09:00'
                )
            """)
            logger.info("✅ جدول user_reminder_settings")
            
            # 9.2 جدول إعدادات الترجمة
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_translation (
                    user_id INTEGER PRIMARY KEY,
                    lang TEXT DEFAULT 'off',
                    auto_translate INTEGER DEFAULT 0,
                    preferred_languages TEXT DEFAULT '[]'
                )
            """)
            logger.info("✅ جدول user_translation")
            
            # ===================================================================
            # 10. جداول المسابقات
            # ===================================================================
            
            # 10.1 جدول المسابقات
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
                    contest_type TEXT DEFAULT 'raffle',
                    max_participants INTEGER DEFAULT 0,
                    is_private INTEGER DEFAULT 0,
                    allowed_users TEXT DEFAULT '[]'
                )
            """)
            logger.info("✅ جدول contests")
            
            # 10.2 جدول المشاركين في المسابقات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS contest_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    contest_id INTEGER,
                    answer TEXT,
                    joined_at TEXT,
                    score INTEGER DEFAULT 0,
                    UNIQUE(user_id, contest_id)
                )
            """)
            logger.info("✅ جدول contest_participants")
            
            # 10.3 جدول الفائزين في المسابقات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS contest_winners (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contest_id INTEGER,
                    winner_id INTEGER,
                    announced_at TEXT,
                    prize_claimed INTEGER DEFAULT 0
                )
            """)
            logger.info("✅ جدول contest_winners")
            
            # ===================================================================
            # 11. جداول الإنجازات والردود التلقائية
            # ===================================================================
            
            # 11.1 جدول الإنجازات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    achievement TEXT,
                    created_at TEXT,
                    points INTEGER DEFAULT 0,
                    UNIQUE(user_id, achievement)
                )
            """)
            logger.info("✅ جدول achievements")
            
            # 11.2 جدول الردود التلقائية
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS auto_replies (
                    chat_id INTEGER,
                    keyword TEXT,
                    reply TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    is_active INTEGER DEFAULT 1,
                    priority INTEGER DEFAULT 0,
                    PRIMARY KEY (chat_id, keyword)
                )
            """)
            logger.info("✅ جدول auto_replies")
            
            # 11.3 جدول إعدادات الردود التلقائية
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS auto_reply_settings (
                    chat_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    only_admins INTEGER DEFAULT 0,
                    ignore_bots INTEGER DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT,
                    cooldown_seconds INTEGER DEFAULT 5,
                    max_replies_per_minute INTEGER DEFAULT 10
                )
            """)
            logger.info("✅ جدول auto_reply_settings")
            
            # ===================================================================
            # 12. جداول NSFW والإعدادات العامة
            # ===================================================================
            
            # 12.1 جدول إعدادات NSFW
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS nsfw_settings (
                    chat_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    threshold REAL DEFAULT 0.7,
                    updated_at TEXT,
                    auto_ban INTEGER DEFAULT 0,
                    log_channel INTEGER
                )
            """)
            logger.info("✅ جدول nsfw_settings")
            
            # 12.2 جدول المستخدمين المسموح لهم بـ /sendcode
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS allowed_sendcode_user (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    user_id INTEGER,
                    created_at TEXT
                )
            """)
            logger.info("✅ جدول allowed_sendcode_user")
            
            # 12.3 جدول المشرفين المجهولين
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS anonymous_admins (
                    chat_id INTEGER,
                    anonymous_id INTEGER,
                    user_id INTEGER,
                    created_at TEXT,
                    PRIMARY KEY (chat_id, anonymous_id)
                )
            """)
            logger.info("✅ جدول anonymous_admins")
            
            # ===================================================================
            # 13. جداول الجلسات والويب
            # ===================================================================
            
            # 13.1 جدول الجلسات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    data TEXT,
                    expires_at TEXT,
                    created_at TEXT,
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)
            logger.info("✅ جدول sessions")
            
            # 13.2 جدول جلسات الويب
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS web_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    user_id INTEGER,
                    created_at REAL,
                    expires REAL,
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)
            logger.info("✅ جدول web_sessions")
            
            # ===================================================================
            # 14. جداول الإعلانات والإعدادات
            # ===================================================================
            
            # 14.1 جدول الإعلانات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    text TEXT,
                    created_by INTEGER,
                    created_at TEXT,
                    scheduled_for TEXT,
                    status TEXT DEFAULT 'pending',
                    sent_count INTEGER DEFAULT 0,
                    is_global INTEGER DEFAULT 0,
                    target_users TEXT DEFAULT '[]'
                )
            """)
            logger.info("✅ جدول announcements")
            
            # 14.2 جدول الإعدادات العامة
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT,
                    updated_by INTEGER
                )
            """)
            await conn.execute("""
                INSERT OR IGNORE INTO settings (key, value) VALUES ('publish_interval', ?)
            """, (str(DEFAULT_PUBLISH_INTERVAL_SECONDS),))
            await conn.execute("""
                INSERT OR IGNORE INTO settings (key, value) VALUES ('db_version', '2.0')
            """)
            logger.info("✅ جدول settings")
            
            # 14.3 جدول مشرفي البوت
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_admins (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    added_at TEXT,
                    permissions TEXT DEFAULT '[]',
                    is_active INTEGER DEFAULT 1
                )
            """)
            logger.info("✅ جدول bot_admins")
            
            # ===================================================================
            # 15. جداول التعلم الذكي وتحليل المشاعر
            # ===================================================================
            
            # 15.1 جدول أنماط التعلم
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS learning_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    sentiment TEXT,
                    score REAL,
                    frequency INTEGER DEFAULT 1,
                    last_used TEXT,
                    confidence REAL DEFAULT 0.5,
                    category TEXT DEFAULT 'general'
                )
            """)
            logger.info("✅ جدول learning_patterns")
            
            # 15.2 جدول سجل المشاعر
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    chat_id INTEGER,
                    text TEXT,
                    sentiment TEXT,
                    score REAL,
                    created_at TEXT,
                    response_sentiment TEXT,
                    response_score REAL
                )
            """)
            logger.info("✅ جدول sentiment_history")
            
            # 15.3 جدول ملف تعريف المشاعر للمستخدمين
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_sentiment_profile (
                    user_id INTEGER PRIMARY KEY,
                    avg_sentiment REAL DEFAULT 0,
                    stability REAL DEFAULT 1,
                    messages INTEGER DEFAULT 0,
                    trend TEXT DEFAULT 'stable',
                    last_updated TEXT,
                    positive_count INTEGER DEFAULT 0,
                    negative_count INTEGER DEFAULT 0,
                    neutral_count INTEGER DEFAULT 0
                )
            """)
            logger.info("✅ جدول user_sentiment_profile")
            
            # 15.4 جدول ملف تعريف المشاعر للمجموعات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_sentiment_profile (
                    chat_id INTEGER PRIMARY KEY,
                    avg_sentiment REAL DEFAULT 0,
                    stability REAL DEFAULT 1,
                    messages INTEGER DEFAULT 0,
                    trend TEXT DEFAULT 'stable',
                    last_updated TEXT,
                    positive_count INTEGER DEFAULT 0,
                    negative_count INTEGER DEFAULT 0,
                    neutral_count INTEGER DEFAULT 0
                )
            """)
            logger.info("✅ جدول chat_sentiment_profile")
            
            # 15.5 جدول التعلم من الاستجابات
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS response_learning (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_key TEXT UNIQUE,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    score REAL DEFAULT 0,
                    last_used TEXT,
                    best_response TEXT
                )
            """)
            logger.info("✅ جدول response_learning")
            
            # ===================================================================
            # 16. جداول الأمان المتقدمة
            # ===================================================================
            
            # 16.1 جدول إعدادات الأمان (نسخة مبسطة للتوافق)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS group_security_settings (
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
                    delete_penalty TEXT DEFAULT 'none'
                )
            """)
            logger.info("✅ جدول group_security_settings")
            
            # 16.2 جدول الأحداث الأمنية ⚠️ مهم: يجب إنشاؤه قبل الفهارس
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    chat_id INTEGER,
                    user_id INTEGER,
                    details TEXT,
                    severity TEXT DEFAULT 'info',
                    created_at TEXT NOT NULL,
                    learned_from BOOLEAN DEFAULT 0,
                    sentiment_analysis TEXT,
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)
            logger.info("✅ جدول security_events (تم إنشاؤه قبل الفهارس)")
            
            # ===================================================================
            # 17. إنشاء الفهارس (بعد إنشاء جميع الجداول)
            # ===================================================================
            
            # فهارس الجداول الأساسية
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_channels_user ON user_channels(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_banned_words_chat ON banned_words(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_posts_time ON scheduled_posts(publish_time)")
            
            # فهارس الإحالات
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_created ON referrals(created_at)")
            
            # فهارس الإشراف
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_moderation_log_chat ON moderation_log(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_moderation_log_user ON moderation_log(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_moderation_log_created ON moderation_log(created_at)")
            
            # فهارس المسابقات
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_contests_end_date ON contests(end_date)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_contest_participants_contest ON contest_participants(contest_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_contest_participants_user ON contest_participants(user_id)")
            
            # فهارس التعلم والمشاعر
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_history_user ON sentiment_history(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_history_chat ON sentiment_history(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_history_created ON sentiment_history(created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sentiment_history_sentiment ON sentiment_history(sentiment)")
            
            # فهارس الأمان
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_type ON security_events(event_type)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_severity ON security_events(severity)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_created ON security_events(created_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_chat ON security_events(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_user ON security_events(user_id)")
            
            # فهارس إضافية
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_banned ON users(banned)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_groups_chat_name ON bot_groups(chat_name)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_groups_banned ON bot_groups(banned)")
            
            # فهارس الردود التلقائية
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_auto_replies_chat ON auto_replies(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_auto_replies_keyword ON auto_replies(keyword)")
            
            logger.info("✅ تم إنشاء جميع الفهارس")
            
            # ===================================================================
            # 18. تحديث الإصدار والتحقق من الصحة
            # ===================================================================
            
            # تحديث إصدار قاعدة البيانات
            await conn.execute("""
                INSERT OR REPLACE INTO settings (key, value) VALUES ('db_version', '2.1.0')
            """)
            
            # التحقق من صحة البيانات
            await conn.execute("""
                CREATE TRIGGER IF NOT EXISTS update_updated_at 
                AFTER UPDATE ON users
                BEGIN
                    UPDATE users SET updated_at = datetime('now') WHERE user_id = NEW.user_id;
                END
            """)
            
            await conn.commit()
            
            # ===================================================================
            # 19. تسجيل نجاح التهيئة
            # ===================================================================
            
            logger.info("✅ تم إنشاء جميع جداول قاعدة البيانات بنجاح (الإصدار 2.1.0)")
            logger.info(f"📊 إجمالي الجداول: 35+ جدول")
            logger.info(f"📊 إجمالي الفهارس: 25+ فهرس")
            logger.info("🧠 نظام التعلم الذكي جاهز")
            logger.info("🔐 نظام الأمان المتقدم جاهز")
            logger.info("📈 نظام تحليل المشاعر جاهز")
            
        # تنفيذ التهيئة
        await execute_db(_init)
        
    except Exception as e:
        logger.error(f"❌ فشل تهيئة قاعدة البيانات: {e}")
        logger.error(f"📌 نوع الخطأ: {type(e).__name__}")
        logger.error(f"📌 تفاصيل: {str(e)}")
        raise

# ===================================================================
# 14. دوال قاعدة البيانات - المستخدمين (محسنة بالتعلم)
# ===================================================================
async def db_register_user(user_id: int) -> bool:
    async def _register(conn):
        try:
            cur = await conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
            if await cur.fetchone():
                await conn.execute("UPDATE users SET updated_at=? WHERE user_id=?", (utc_now_iso(), user_id))
                await conn.commit()
                return False
            referral_code = secrets.token_urlsafe(6)
            await conn.execute(
                """INSERT INTO users 
                   (user_id, auto_publish, banned, trial_used, auto_reply_enabled, auto_recycle, 
                    referral_code, created_at, updated_at) 
                   VALUES (?, 1, 0, 0, 1, 1, ?, ?, ?)""",
                (user_id, referral_code, utc_now_iso(), utc_now_iso())
            )
            await conn.commit()
            logger.info(f"✅ تم تسجيل مستخدم جديد: {user_id}")
            # إنشاء ملف تعريف مشاعر للمستخدم
            await conn.execute(
                "INSERT OR IGNORE INTO user_sentiment_profile (user_id, last_updated) VALUES (?, ?)",
                (user_id, utc_now_iso())
            )
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في تسجيل المستخدم {user_id}: {e}")
            await conn.rollback()
            return False
    return await execute_db(_register)

async def db_get_all_users():
    async def _get(conn):
        cur = await conn.execute("SELECT user_id, banned, username, first_name FROM users ORDER BY user_id")
        return await cur.fetchall()
    return await execute_db(_get)

async def db_update_user_cache(user_id: int, username: str, first_name: str):
    async def _update(conn):
        try:
            await conn.execute(
                """INSERT OR REPLACE INTO users_cache 
                   (user_id, username, first_name, last_updated) 
                   VALUES (?, ?, ?, ?)""",
                (user_id, username or "", first_name or "", utc_now_iso())
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تحديث كاش المستخدم {user_id}: {e}")
    return await execute_db(_update)

async def db_is_banned(user_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_check)

async def db_set_ban(user_id: int, banned: bool):
    async def _set(conn):
        try:
            await conn.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, user_id))
            await conn.commit()
            logger.info(f"✅ تم {'حظر' if banned else 'إلغاء حظر'} المستخدم {user_id}")
        except Exception as e:
            logger.error(f"خطأ في تعيين حظر المستخدم {user_id}: {e}")
            await conn.rollback()
    return await execute_db(_set)

async def db_has_used_trial(user_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_check)

async def db_activate_trial(user_id: int) -> int:
    async def _activate(conn):
        try:
            cur = await conn.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
            if row and row[0] == 1:
                return 0
            end_date = (utc_now() + timedelta(days=30)).isoformat()
            await conn.execute("UPDATE users SET trial_used=1, subscription_end=? WHERE user_id=?", (end_date, user_id))
            await conn.commit()
            logger.info(f"✅ تم تفعيل التجربة المجانية للمستخدم {user_id}")
            return 30
        except Exception as e:
            logger.error(f"خطأ في تفعيل التجربة للمستخدم {user_id}: {e}")
            await conn.rollback()
            return 0
    return await execute_db(_activate)

async def db_activate_subscription(user_id: int, days: int):
    async def _activate(conn):
        try:
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
            logger.info(f"✅ تم تفعيل اشتراك {days} يوم للمستخدم {user_id}")
        except Exception as e:
            logger.error(f"خطأ في تفعيل الاشتراك للمستخدم {user_id}: {e}")
            await conn.rollback()
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
        try:
            await conn.execute("UPDATE users SET auto_publish=? WHERE user_id=?", (1 if enabled else 0, user_id))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تعيين النشر التلقائي للمستخدم {user_id}: {e}")
            await conn.rollback()
    return await execute_db(_set)

async def db_get_auto_recycle(user_id: int) -> bool:
    async def _get(conn):
        cur = await conn.execute("SELECT auto_recycle FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_get)

async def db_set_auto_recycle(user_id: int, enabled: bool):
    async def _set(conn):
        try:
            await conn.execute("UPDATE users SET auto_recycle=? WHERE user_id=?", (1 if enabled else 0, user_id))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تعيين إعادة التدوير للمستخدم {user_id}: {e}")
            await conn.rollback()
    return await execute_db(_set)

async def db_get_user_auto_reply_status(user_id: int) -> bool:
    async def _get(conn):
        cur = await conn.execute("SELECT auto_reply_enabled FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_get)

async def db_set_user_auto_reply_status(user_id: int, enabled: bool):
    async def _set(conn):
        try:
            await conn.execute("UPDATE users SET auto_reply_enabled=? WHERE user_id=?", (1 if enabled else 0, user_id))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تعيين الردود التلقائية للمستخدم {user_id}: {e}")
            await conn.rollback()
    return await execute_db(_set)

async def db_set_user_language(user_id: int, lang: str):
    async def _set(conn):
        try:
            await conn.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تعيين لغة المستخدم {user_id}: {e}")
    return await execute_db(_set)

async def db_get_user_language(user_id: int) -> str:
    async def _get(conn):
        cur = await conn.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row and row[0] else 'ar'
    return await execute_db(_get)

async def db_get_user_by_referral_code(code: str) -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE referral_code=?", (code,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_get_active_channel(user_id: int):
    async def _get(conn):
        try:
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
        except Exception as e:
            logger.error(f"خطأ في جلب القناة النشطة للمستخدم {user_id}: {e}")
            return None
    return await execute_db(_get)

async def db_set_active_channel(user_id: int, channel_db_id: int):
    async def _set(conn):
        try:
            await conn.execute("UPDATE users SET active_channel=? WHERE user_id=?", (channel_db_id, user_id))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تعيين القناة النشطة للمستخدم {user_id}: {e}")
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
# 15. دوال التعلم الذكي وتحليل المشاعر (متكاملة مع قاعدة البيانات)
# ===================================================================
async def db_save_learning_pattern(pattern: str, sentiment: str, score: float, confidence: float):
    """حفظ نمط تعلم جديد أو تحديث موجود"""
    async def _save(conn):
        cur = await conn.execute(
            "SELECT id, frequency, confidence FROM learning_patterns WHERE pattern = ?",
            (pattern,)
        )
        row = await cur.fetchone()
        if row:
            new_freq = row[1] + 1
            new_confidence = min(1.0, (row[2] * row[1] + confidence) / new_freq)
            await conn.execute(
                "UPDATE learning_patterns SET frequency = ?, confidence = ?, last_used = ?, sentiment = ?, score = ? WHERE id = ?",
                (new_freq, new_confidence, utc_now_iso(), sentiment, score, row[0])
            )
        else:
            await conn.execute(
                "INSERT INTO learning_patterns (pattern, sentiment, score, frequency, last_used, confidence) VALUES (?, ?, ?, 1, ?, ?)",
                (pattern, sentiment, score, utc_now_iso(), confidence)
            )
        await conn.commit()
    return await execute_db(_save)

async def db_save_sentiment_history(user_id: int, chat_id: int, text: str, sentiment: str, score: float):
    """حفظ سجل المشاعر لرسالة"""
    async def _save(conn):
        await conn.execute(
            "INSERT INTO sentiment_history (user_id, chat_id, text, sentiment, score, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, text[:500], sentiment, score, utc_now_iso())
        )
        # تحديث ملف تعريف المستخدم
        await conn.execute(
            "UPDATE user_sentiment_profile SET messages = messages + 1, last_updated = ? WHERE user_id = ?",
            (utc_now_iso(), user_id)
        )
        # تحديث ملف تعريف المجموعة
        await conn.execute(
            "UPDATE chat_sentiment_profile SET messages = messages + 1, last_updated = ? WHERE chat_id = ?",
            (utc_now_iso(), chat_id)
        )
        await conn.commit()
    return await execute_db(_save)

async def db_update_user_sentiment_profile(user_id: int, avg_sentiment: float, stability: float, trend: str):
    """تحديث ملف تعريف المشاعر للمستخدم"""
    async def _update(conn):
        await conn.execute(
            "UPDATE user_sentiment_profile SET avg_sentiment = ?, stability = ?, trend = ?, last_updated = ? WHERE user_id = ?",
            (avg_sentiment, stability, trend, utc_now_iso(), user_id)
        )
        await conn.commit()
    return await execute_db(_update)

async def db_update_chat_sentiment_profile(chat_id: int, avg_sentiment: float, stability: float, trend: str):
    """تحديث ملف تعريف المشاعر للمجموعة"""
    async def _update(conn):
        await conn.execute(
            "UPDATE chat_sentiment_profile SET avg_sentiment = ?, stability = ?, trend = ?, last_updated = ? WHERE chat_id = ?",
            (avg_sentiment, stability, trend, utc_now_iso(), chat_id)
        )
        await conn.commit()
    return await execute_db(_update)

async def db_get_user_sentiment_profile(user_id: int) -> Dict[str, Any]:
    """الحصول على ملف تعريف المشاعر للمستخدم"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT avg_sentiment, stability, messages, trend, last_updated FROM user_sentiment_profile WHERE user_id = ?",
            (user_id,)
        )
        row = await cur.fetchone()
        if row:
            return {
                'avg_sentiment': row[0] or 0,
                'stability': row[1] or 1,
                'messages': row[2] or 0,
                'trend': row[3] or 'stable',
                'last_updated': row[4]
            }
        # إنشاء ملف تعريف افتراضي
        await conn.execute(
            "INSERT OR IGNORE INTO user_sentiment_profile (user_id, last_updated) VALUES (?, ?)",
            (user_id, utc_now_iso())
        )
        await conn.commit()
        return {'avg_sentiment': 0, 'stability': 1, 'messages': 0, 'trend': 'stable', 'last_updated': utc_now_iso()}
    return await execute_db(_get)

async def db_get_chat_sentiment_profile(chat_id: int) -> Dict[str, Any]:
    """الحصول على ملف تعريف المشاعر للمجموعة"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT avg_sentiment, stability, messages, trend, last_updated FROM chat_sentiment_profile WHERE chat_id = ?",
            (chat_id,)
        )
        row = await cur.fetchone()
        if row:
            return {
                'avg_sentiment': row[0] or 0,
                'stability': row[1] or 1,
                'messages': row[2] or 0,
                'trend': row[3] or 'stable',
                'last_updated': row[4]
            }
        await conn.execute(
            "INSERT OR IGNORE INTO chat_sentiment_profile (chat_id, last_updated) VALUES (?, ?)",
            (chat_id, utc_now_iso())
        )
        await conn.commit()
        return {'avg_sentiment': 0, 'stability': 1, 'messages': 0, 'trend': 'stable', 'last_updated': utc_now_iso()}
    return await execute_db(_get)

async def db_save_response_learning(pattern_key: str, success: bool):
    """تسجيل نجاح أو فشل استجابة لتحسين التعلم"""
    async def _save(conn):
        cur = await conn.execute(
            "SELECT id, success_count, fail_count, score FROM response_learning WHERE pattern_key = ?",
            (pattern_key,)
        )
        row = await cur.fetchone()
        if row:
            if success:
                new_success = row[1] + 1
            else:
                new_fail = row[2] + 1
            total = new_success + (row[2] + (0 if success else 1))
            new_score = new_success / max(total, 1)
            await conn.execute(
                "UPDATE response_learning SET success_count = ?, fail_count = ?, score = ?, last_used = ? WHERE id = ?",
                (new_success, row[2] + (0 if success else 1), new_score, utc_now_iso(), row[0])
            )
        else:
            await conn.execute(
                "INSERT INTO response_learning (pattern_key, success_count, fail_count, score, last_used) VALUES (?, ?, ?, ?, ?)",
                (pattern_key, 1 if success else 0, 0 if success else 1, 1.0 if success else 0.0, utc_now_iso())
            )
        await conn.commit()
    return await execute_db(_save)

async def db_get_learned_response(pattern: str) -> Optional[str]:
    """الحصول على أفضل استجابة متعلمة لنمط معين"""
    async def _get(conn):
        # نبحث عن أنماط مشابهة
        cur = await conn.execute(
            "SELECT pattern_key, score FROM response_learning WHERE pattern_key LIKE ? ORDER BY score DESC LIMIT 5",
            (f"{pattern}%",)
        )
        rows = await cur.fetchall()
        if rows and rows[0][1] > 0.6:
            # استخراج الرد من pattern_key (يحتوي على النص الأصلي والرد)
            return rows[0][0].split('_')[-1] if '_' in rows[0][0] else None
        return None
    return await execute_db(_get)

async def db_get_learning_stats() -> Dict[str, Any]:
    """الحصول على إحصائيات التعلم من قاعدة البيانات"""
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM learning_patterns")
        patterns = (await cur.fetchone())[0] or 0
        cur = await conn.execute("SELECT COUNT(*) FROM sentiment_history")
        history = (await cur.fetchone())[0] or 0
        cur = await conn.execute("SELECT COUNT(*) FROM user_sentiment_profile")
        users = (await cur.fetchone())[0] or 0
        cur = await conn.execute("SELECT COUNT(*) FROM chat_sentiment_profile")
        chats = (await cur.fetchone())[0] or 0
        cur = await conn.execute("SELECT COUNT(*) FROM response_learning")
        responses = (await cur.fetchone())[0] or 0
        return {
            'patterns': patterns,
            'sentiment_history': history,
            'users_with_profile': users,
            'chats_with_profile': chats,
            'learned_responses': responses
        }
    return await execute_db(_get)

# ===================================================================
# 16. دوال القنوات والمنشورات (محسنة)
# ===================================================================
async def db_add_channel(user_id: int, channel_id: str, channel_name: str) -> int:
    async def _add(conn):
        try:
            cur = await conn.execute("SELECT id FROM user_channels WHERE user_id=? AND channel_id=?", (user_id, channel_id))
            if await cur.fetchone():
                return None
            cur = await conn.execute(
                """INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) 
                   VALUES (?, ?, ?, ?) RETURNING id""",
                (user_id, channel_id, channel_name, utc_now_iso())
            )
            row = await cur.fetchone()
            await conn.commit()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"خطأ في إضافة القناة {channel_id} للمستخدم {user_id}: {e}")
            await conn.rollback()
            return None
    return await execute_db(_add)

async def db_get_channels(user_id: int):
    async def _get(conn):
        try:
            cur = await conn.execute("SELECT id, channel_id, channel_name, banned FROM user_channels WHERE user_id=? ORDER BY id", (user_id,))
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
        try:
            await conn.execute("DELETE FROM user_channels WHERE id=? AND user_id=?", (channel_db_id, user_id))
            await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (channel_db_id,))
            await conn.execute("DELETE FROM schedule WHERE channel_db_id=?", (channel_db_id,))
            await conn.execute("DELETE FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
            await conn.commit()
            logger.info(f"✅ تم حذف القناة {channel_db_id} للمستخدم {user_id}")
            return True
        except Exception as e:
            logger.error(f"خطأ في حذف القناة {channel_db_id}: {e}")
            await conn.rollback()
            return False
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
        try:
            cur = await conn.execute("SELECT channel_id FROM bot_channels WHERE channel_id=?", (channel_id,))
            if await cur.fetchone():
                await conn.execute("UPDATE bot_channels SET channel_name=?, added_by=? WHERE channel_id=?", (channel_name, added_by, channel_id))
                await conn.commit()
                return False
            await conn.execute("INSERT INTO bot_channels (channel_id, channel_name, added_by, added_at) VALUES (?, ?, ?, ?)", (channel_id, channel_name, added_by, utc_now_iso()))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في تسجيل القناة {channel_id}: {e}")
            await conn.rollback()
            return False
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
        try:
            cur = await conn.execute("SELECT banned FROM user_channels WHERE id=?", (channel_db_id,))
            row = await cur.fetchone()
            if row:
                new_status = 1 if row[0] == 0 else 0
                await conn.execute("UPDATE user_channels SET banned=? WHERE id=?", (new_status, channel_db_id))
                await conn.commit()
                return new_status == 1
            return False
        except Exception as e:
            logger.error(f"خطأ في تبديل حظر القناة {channel_db_id}: {e}")
            await conn.rollback()
            return False
    return await execute_db(_toggle)

async def db_toggle_bot_channel_ban(channel_id: int):
    async def _toggle(conn):
        try:
            cur = await conn.execute("SELECT banned FROM bot_channels WHERE channel_id=?", (channel_id,))
            row = await cur.fetchone()
            if row:
                new_status = 1 if row[0] == 0 else 0
                await conn.execute("UPDATE bot_channels SET banned=? WHERE channel_id=?", (new_status, channel_id))
                await conn.commit()
                return new_status == 1
            return False
        except Exception as e:
            logger.error(f"خطأ في تبديل حظر قناة البوت {channel_id}: {e}")
            await conn.rollback()
            return False
    return await execute_db(_toggle)

# ===================================================================
# 17. دوال المنشورات (محسنة)
# ===================================================================
async def db_save_posts(channel_db_id: int, posts: list) -> int:
    async def _save(conn):
        try:
            values = []
            for text_content, media_type, media_file_id in posts:
                values.append((channel_db_id, sanitize_text(text_content), media_type, media_file_id, utc_now_iso()))
            await conn.executemany(
                """INSERT INTO posts (channel_db_id, text, media_type, media_file_id, created_at) 
                   VALUES (?, ?, ?, ?, ?)""",
                values
            )
            await conn.commit()
            return len(values)
        except Exception as e:
            logger.error(f"خطأ في حفظ المنشورات للقناة {channel_db_id}: {e}")
            await conn.rollback()
            return 0
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
        try:
            await conn.execute("UPDATE posts SET published=1, published_at=? WHERE id=?", (utc_now_iso(), post_id))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تحديث المنشور {post_id}: {e}")
            await conn.rollback()
    return await execute_db(_mark)

async def db_increment_fail_count(post_id: int):
    async def _inc(conn):
        try:
            await conn.execute("UPDATE posts SET fail_count = fail_count + 1 WHERE id=?", (post_id,))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في زيادة عداد الفشل للمنشور {post_id}: {e}")
            await conn.rollback()
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
        try:
            await conn.execute("UPDATE posts SET published=0, fail_count=0 WHERE channel_db_id=?", (channel_db_id,))
            await conn.commit()
            cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_db_id,))
            row = await cur.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"خطأ في إعادة تعيين المنشورات للقناة {channel_db_id}: {e}")
            await conn.rollback()
            return 0
    return await execute_db(_reset)

async def db_get_user_posts_for_channel(channel_db_id: int, limit=15):
    async def _get(conn):
        cur = await conn.execute("SELECT id, text, media_type FROM posts WHERE channel_db_id=? AND published=0 ORDER BY id LIMIT ?", (channel_db_id, limit))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_delete_single_post(post_id: int, user_id: int, channel_db_id: int) -> bool:
    async def _delete(conn):
        try:
            cur = await conn.execute("SELECT 1 FROM user_channels WHERE id=? AND user_id=? AND banned=0", (channel_db_id, user_id))
            if not await cur.fetchone():
                return False
            cur = await conn.execute("SELECT 1 FROM posts WHERE id=? AND channel_db_id=?", (post_id, channel_db_id))
            if not await cur.fetchone():
                return False
            await conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في حذف المنشور {post_id}: {e}")
            await conn.rollback()
            return False
    return await execute_db(_delete)

async def db_unpublished_count(channel_db_id: int) -> int:
    async def _count(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=0", (channel_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_count)

async def db_update_post_views(post_id: int, views_count: int = None):
    async def _update_views(conn):
        try:
            if views_count is not None:
                await conn.execute("UPDATE posts SET views_count = ?, last_view_time = ? WHERE id = ?", (views_count, utc_now_iso(), post_id))
            else:
                await conn.execute("UPDATE posts SET views_count = views_count + 1, last_view_time = ? WHERE id = ?", (utc_now_iso(), post_id))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تحديث مشاهدات المنشور {post_id}: {e}")
            await conn.rollback()
    return await execute_db(_update_views)

# ===================================================================
# 18. دوال الجدولة (محسنة)
# ===================================================================
async def db_save_schedule(channel_db_id: int, schedule_type: str, 
                           interval_minutes: int = None, interval_hours: int = None,
                           interval_days: int = None, days_of_week: str = None,
                           specific_dates: str = None, publish_time: str = None,
                           cron_expression: str = None):
    async def _save(conn):
        try:
            await conn.execute("""
                INSERT OR REPLACE INTO schedule 
                (channel_db_id, schedule_type, interval_minutes, interval_hours, interval_days, 
                 days_of_week, specific_dates, publish_time, cron_expression, next_publish_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """, (channel_db_id, schedule_type, interval_minutes or 12, interval_hours or 0,
                  interval_days or 0, days_of_week or '[]', specific_dates or '[]',
                  publish_time or '00:00', cron_expression))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في حفظ الجدولة للقناة {channel_db_id}: {e}")
            await conn.rollback()
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
        return {
            'type': 'interval_minutes',
            'interval_minutes': 12,
            'interval_hours': 0,
            'interval_days': 0,
            'days_of_week': '[]',
            'specific_dates': '[]',
            'publish_time': '00:00',
            'cron_expression': None,
            'next_publish_date': None
        }
    return await execute_db(_get)

async def db_set_next_publish_date(channel_db_id: int, next_date: datetime):
    async def _set(conn):
        try:
            if next_date:
                await conn.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?", (next_date.isoformat(), channel_db_id))
            else:
                await conn.execute("UPDATE schedule SET next_publish_date=NULL WHERE channel_db_id=?", (channel_db_id,))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تعيين تاريخ النشر التالي للقناة {channel_db_id}: {e}")
            await conn.rollback()
    return await execute_db(_set)

async def db_set_last_publish(channel_db_id: int, publish_time: datetime):
    async def _set(conn):
        try:
            await conn.execute("INSERT OR REPLACE INTO last_publish (channel_db_id, last_publish_time) VALUES (?, ?)", (channel_db_id, publish_time.isoformat()))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تعيين آخر نشر للقناة {channel_db_id}: {e}")
            await conn.rollback()
    return await execute_db(_set)

async def db_update_next_publish_date(channel_db_id: int):
    async def _update(conn):
        try:
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
        except Exception as e:
            logger.error(f"خطأ في تحديث تاريخ النشر التالي للقناة {channel_db_id}: {e}")
            await conn.rollback()
    return await execute_db(_update)

async def db_set_publish_time(channel_db_id: int, time_str: str):
    async def _set(conn):
        try:
            await conn.execute("UPDATE schedule SET publish_time=? WHERE channel_db_id=?", (time_str, channel_db_id))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تعيين وقت النشر للقناة {channel_db_id}: {e}")
            await conn.rollback()
    return await execute_db(_set)

async def db_add_scheduled_post(chat_id: int, text: str, publish_time: datetime, media_type: str = None, media_file_id: str = None):
    async def _add(conn):
        try:
            await conn.execute(
                """INSERT INTO scheduled_posts (chat_id, text, media_type, media_file_id, publish_time, fail_count, created_at) 
                   VALUES (?, ?, ?, ?, ?, 0, ?)""",
                (chat_id, sanitize_text(text), media_type, media_file_id, publish_time.isoformat(), utc_now_iso())
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في إضافة منشور مجدول: {e}")
            await conn.rollback()
    return await execute_db(_add)

async def db_get_due_scheduled_posts(now: datetime, limit: int = 50):
    async def _get(conn):
        cur = await conn.execute("SELECT id, chat_id, text, media_type, media_file_id, fail_count FROM scheduled_posts WHERE publish_time <= ? AND fail_count < 3 LIMIT ?", (now.isoformat(), limit))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_update_scheduled_post_fail(post_id: int, fail_count: int):
    async def _update(conn):
        try:
            await conn.execute("UPDATE scheduled_posts SET fail_count = ? WHERE id = ?", (fail_count, post_id))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في تحديث عداد فشل المنشور المجدول {post_id}: {e}")
            await conn.rollback()
    return await execute_db(_update)

async def db_delete_scheduled_post(post_id: int):
    async def _delete(conn):
        try:
            await conn.execute("DELETE FROM scheduled_posts WHERE id = ?", (post_id,))
            await conn.commit()
        except Exception as e:
            logger.error(f"خطأ في حذف المنشور المجدول {post_id}: {e}")
            await conn.rollback()
    return await execute_db(_delete)

async def db_stats():
    async def _stats(conn):
        try:
            cur = await conn.execute("SELECT COUNT(*) FROM users")
            total = (await cur.fetchone())[0] or 0
            cur = await conn.execute("SELECT COUNT(*) FROM users WHERE banned=1")
            banned = (await cur.fetchone())[0] or 0
            cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE published=0")
            posts = (await cur.fetchone())[0] or 0
            cur = await conn.execute("SELECT COUNT(*) FROM bot_groups")
            groups = (await cur.fetchone())[0] or 0
            cur = await conn.execute("SELECT COUNT(*) FROM user_channels")
            channels = (await cur.fetchone())[0] or 0
            return total, banned, posts, groups, channels
        except Exception as e:
            logger.error(f"خطأ في جلب الإحصائيات: {e}")
            return 0, 0, 0, 0, 0
    return await execute_db(_stats)
# ===================================================================
# 19. دوال الأمان والحماية المتطورة
# ===================================================================
_security_cache = {}

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
                logger.info(f"✅ تم إضافة العمود {col_name} إلى جدول الأمان")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                chat_id INTEGER,
                user_id INTEGER,
                details TEXT,
                severity TEXT DEFAULT 'info',
                created_at TEXT NOT NULL,
                learned_from BOOLEAN DEFAULT 0,
                sentiment_analysis TEXT
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_type ON security_events(event_type)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_severity ON security_events(severity)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_created ON security_events(created_at)")
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
        await log_security_event("brute_force_blocked", chat_id, user_id, {"attempts": len(_failed_attempts_cache[cache_key])}, severity="high")
        # تحليل المشاعر للمستخدم المهاجم
        sentiment = learning_engine.analyze_sentiment(f"محاولة اختراق متكررة من المستخدم {user_id}")
        await db_save_sentiment_history(user_id, chat_id, f"brute_force_blocked_attempt_{len(_failed_attempts_cache[cache_key])}", "negative", -0.8)
        return False
    _failed_attempts_cache[cache_key].append(now)
    return True

async def log_security_event(event_type: str, chat_id: int, user_id: int, 
                            details: dict = None, severity: str = "info", 
                            learned: bool = False, sentiment: str = None):
    """تسجيل حدث أمني مع تحليل المشاعر"""
    try:
        # تحليل المشاعر للحدث
        sentiment_analysis = None
        if details and 'reason' in details:
            sentiment_result = learning_engine.analyze_sentiment(details['reason'])
            sentiment_analysis = json.dumps(sentiment_result) if sentiment_result else None
        
        async def _log(conn):
            await conn.execute(
                """INSERT INTO security_events 
                   (event_type, chat_id, user_id, details, severity, created_at, learned_from, sentiment_analysis) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_type, chat_id, user_id, 
                 json.dumps(details) if details else None,
                 severity, utc_now_iso(), 
                 1 if learned else 0,
                 sentiment_analysis or sentiment)
            )
            await conn.commit()
        await execute_db(_log)
        advanced_logger.log_security(event_type, user_id, details, severity.upper())
        
        # التعلم من الحدث الأمني
        if details and 'reason' in details:
            await db_save_learning_pattern(
                f"security_{event_type}_{details.get('action', 'unknown')}",
                "negative" if severity.upper() in ["HIGH", "CRITICAL"] else "neutral",
                -0.5 if severity.upper() in ["HIGH", "CRITICAL"] else 0,
                0.8
            )
        
        # تحديث ملف تعريف المشاعر للمجموعة
        if chat_id and user_id:
            sentiment_score = -0.3 if severity.upper() in ["HIGH", "CRITICAL"] else 0
            await db_save_sentiment_history(user_id, chat_id, f"security_event_{event_type}", "negative" if sentiment_score < 0 else "neutral", sentiment_score)
            
    except Exception as e:
        logger.error(f"خطأ في تسجيل حدث أمني: {e}")

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
            # تحليل المشاعر للمستخدم الذي قام بالفيضان
            user_sentiment = learning_engine.get_user_sentiment_profile(user_id)
            if user_sentiment.get('avg_sentiment', 0) < -0.3:
                # المستخدم في حالة سلبية، زيادة العقوبة
                await log_security_event("flood_detected_negative", chat_id, user_id, 
                                        {"messages": len(messages), "sentiment": user_sentiment}, 
                                        severity="high")
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
        'links': 'delete_links',
        'mentions': 'mentions',
        'warn': 'warn_message',
        'slow_mode': 'slow_mode',
        'slow_mode_seconds': 'slow_mode_seconds',
        'welcome_enabled': 'welcome_enabled',
        'welcome_text': 'welcome_text',
        'goodbye_enabled': 'goodbye_enabled',
        'goodbye_text': 'goodbye_text',
        'delete_banned_words': 'delete_banned_words',
        'auto_penalty': 'auto_penalty',
        'auto_mute_duration': 'auto_mute_duration',
        'delete_videos': 'delete_videos',
        'delete_audio': 'delete_audio',
        'delete_animation': 'delete_animation',
        'delete_service': 'delete_service',
        'delete_documents': 'delete_documents',
        'delete_stickers': 'delete_stickers',
        'delete_forwarded': 'delete_forwarded',
        'delete_polls': 'delete_polls',
        'delete_games': 'delete_games',
        'delete_voice': 'delete_voice',
        'delete_video_note': 'delete_video_note',
        'delete_penalty': 'delete_penalty',
        'delete_penalty_duration': 'delete_penalty_duration',
        'antiflood_enabled': 'antiflood_enabled',
        'antiflood_messages': 'antiflood_messages',
        'antiflood_seconds': 'antiflood_seconds',
        'antiflood_penalty': 'antiflood_penalty',
        'max_warnings': 'max_warnings',
        'warn_penalty': 'warn_penalty',
        'max_message_length': 'max_message_length',
        'night_mode_enabled': 'night_mode_enabled',
        'night_mode_start': 'night_mode_start',
        'night_mode_end': 'night_mode_end',
        'night_mode_action': 'night_mode_action'
    }
    return mapping.get(setting_key)

async def db_get_security_settings(chat_id: int, force_refresh: bool = False) -> dict:
    default_settings = {
        'links': False, 'mentions': False, 'warn': True, 'slow_mode': False,
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
        'night_mode_start': '23:00', 'night_mode_end': '06:00', 'night_mode_action': 'mute'
    }
    if not isinstance(chat_id, int) or chat_id <= 0:
        return default_settings.copy()
    if not force_refresh and CACHETOOLS_AVAILABLE:
        if chat_id in _security_cache:
            cached_time, value = _security_cache[chat_id]
            if time_module.time() - cached_time < _AUTH_CACHE_TTL:
                return value.copy()
    async def _get(conn):
        try:
            original_factory = conn.row_factory
            conn.row_factory = aiosqlite.Row
            await ensure_security_columns(conn)
            cur = await conn.execute("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
            row = await cur.fetchone()
            if row:
                settings = {}
                for key in default_settings:
                    col_name = _get_column_name(key)
                    if col_name and hasattr(row, col_name):
                        val = getattr(row, col_name)
                        if isinstance(default_settings[key], bool):
                            settings[key] = val == 1 if val is not None else default_settings[key]
                        else:
                            settings[key] = val if val is not None else default_settings[key]
                    else:
                        settings[key] = default_settings[key]
                # تحليل المشاعر للمجموعة بناءً على الإعدادات
                sentiment_score = 0
                if settings.get('antiflood_enabled', False):
                    sentiment_score -= 0.2
                if settings.get('delete_banned_words', False):
                    sentiment_score -= 0.1
                if settings.get('welcome_enabled', False):
                    sentiment_score += 0.3
                if settings.get('goodbye_enabled', False):
                    sentiment_score += 0.2
                # تحديث ملف تعريف المشاعر للمجموعة
                await db_update_chat_sentiment_profile(chat_id, sentiment_score, 0.7, 'stable')
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
            conn.row_factory = original_factory
    return await execute_db(_get)

async def db_set_security_settings(chat_id: int, **kwargs) -> bool:
    if not isinstance(chat_id, int) or chat_id <= 0:
        return False
    allowed_penalties = ['none', 'warn', 'mute', 'kick', 'ban']
    validated = {}
    for key, value in kwargs.items():
        col_name = _get_column_name(key)
        if not col_name:
            continue
        if col_name not in _ALLOWED_SECURITY_COLUMNS:
            logger.warning(f"محاولة استخدام عمود غير مصرح به: {col_name}")
            continue
        if key.endswith('_enabled'):
            validated[col_name] = 1 if value else 0
        elif key.endswith('_penalty') or key == 'auto_penalty':
            validated[col_name] = value if value in allowed_penalties else 'none'
        elif key.endswith('_text') or key.endswith('_start') or key.endswith('_end'):
            validated[col_name] = html.escape(str(value)[:1000]) if value else ""
        else:
            try:
                validated[col_name] = int(value) if value is not None else 0
            except (ValueError, TypeError):
                validated[col_name] = 0
    if 'night_mode_start' in validated and not validate_time_format(validated['night_mode_start']):
        validated['night_mode_start'] = '23:00'
    if 'night_mode_end' in validated and not validate_time_format(validated['night_mode_end']):
        validated['night_mode_end'] = '06:00'
    if not validated:
        return False
    async def _set(conn):
        try:
            await ensure_security_columns(conn)
            cur = await conn.execute("SELECT 1 FROM group_security WHERE chat_id=?", (chat_id,))
            if not await cur.fetchone():
                await conn.execute("INSERT INTO group_security (chat_id) VALUES (?)", (chat_id,))
            updates = [f"{k}=?" for k in validated.keys()]
            values = list(validated.values())
            values.append(chat_id)
            await conn.execute(f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id=?", values)
            await conn.commit()
            # تحديث ملف تعريف المشاعر للمجموعة بناءً على الإعدادات الجديدة
            settings = await db_get_security_settings(chat_id, force_refresh=True)
            sentiment_score = 0
            if settings.get('antiflood_enabled', False):
                sentiment_score -= 0.2
            if settings.get('delete_banned_words', False):
                sentiment_score -= 0.1
            if settings.get('welcome_enabled', False):
                sentiment_score += 0.3
            if settings.get('goodbye_enabled', False):
                sentiment_score += 0.2
            await db_update_chat_sentiment_profile(chat_id, sentiment_score, 0.7, 'stable')
            return True
        except Exception as e:
            logger.error(f"خطأ في تعيين إعدادات الأمان {chat_id}: {e}")
            await conn.rollback()
            return False
    result = await execute_db(_set)
    if CACHETOOLS_AVAILABLE:
        _security_cache.pop(chat_id, None)
    return result

# ===================================================================
# 20. دوال قفل المجموعة والوضع البطيء (محسنة)
# ===================================================================
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
                await conn.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?, 1, ?, ?)", (chat_id, utc_now_iso(), locked_by))
                # تحليل المشاعر للمجموعة عند القفل
                await db_save_sentiment_history(locked_by, chat_id, "chat_locked", "neutral", -0.1)
            else:
                await conn.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
                await db_save_sentiment_history(locked_by, chat_id, "chat_unlocked", "positive", 0.2)
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في قفل المجموعة {chat_id}: {e}")
            await conn.rollback()
            return False
    return await execute_db(_set)

async def db_check_slow_mode(chat_id: int, user_id: int) -> bool:
    settings = await db_get_security_settings(chat_id)
    if not settings.get('slow_mode', False):
        return True
    seconds = settings.get('slow_mode_seconds', 5)
    async def _check(conn):
        try:
            cur = await conn.execute("SELECT message_time FROM user_messages WHERE chat_id=? AND user_id=?", (chat_id, user_id))
            row = await cur.fetchone()
            now = utc_now()
            if row:
                last_time = datetime.fromisoformat(row[0])
                if (now - last_time).total_seconds() < seconds:
                    # تحليل المشاعر للمستخدم المتجاوز للوضع البطيء
                    await db_save_sentiment_history(user_id, chat_id, "slow_mode_violation", "negative", -0.3)
                    return False
            await conn.execute("INSERT OR REPLACE INTO user_messages (user_id, chat_id, message_time) VALUES (?, ?, ?)", (user_id, chat_id, now.isoformat()))
            await conn.commit()
            return True
        except Exception as e:
            logger.error(f"خطأ في التحقق من الوضع البطيء {chat_id}: {e}")
            return True
    return await execute_db(_check)

# ===================================================================
# 21. دوال الكلمات المحظورة الذكية
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
            # تحليل المشاعر للكلمة المحظورة
            sentiment = learning_engine.analyze_sentiment(word)
            await db_save_learning_pattern(f"banned_word_{word}", sentiment['sentiment'], sentiment['score'], sentiment['confidence'])
            if chat_id == -1:
                await rebuild_banned_patterns()
            return True
        except Exception as e:
            logger.error(f"خطأ في إضافة كلمة محظورة: {e}")
            await conn.rollback()
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
            if chat_id == -1:
                await rebuild_banned_patterns()
            return True
        except Exception as e:
            logger.error(f"خطأ في حذف كلمة محظورة: {e}")
            await conn.rollback()
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
            # تحليل المشاعر للكلمة المحظورة
            sentiment = learning_engine.analyze_sentiment(text)
            await db_save_sentiment_history(0, chat_id, f"banned_word_{word}", "negative", -0.5)
            return word
    return None

async def rebuild_banned_patterns():
    global BANNED_PATTERNS
    async def _get(conn):
        cur = await conn.execute("SELECT word FROM banned_words WHERE chat_id=-1")
        return [row[0] for row in await cur.fetchall()]
    try:
        words = await execute_db(_get)
        BANNED_PATTERNS = words
        logger.info(f"✅ تم تحديث {len(BANNED_PATTERNS)} كلمة محظورة عالمية")
    except Exception as e:
        logger.error(f"خطأ في إعادة بناء أنماط الكلمات المحظورة: {e}")

# ===================================================================
# 22. دوال الصلاحيات المتقدمة (محسنة)
# ===================================================================
async def check_bot_admin_permissions_group(bot, chat_id: int) -> dict:
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
        if CACHETOOLS_AVAILABLE:
            if chat_id and user_id:
                key = f"auth_{chat_id}_{user_id}"
                _auth_cache.pop(key, None)
            elif chat_id:
                keys = [k for k in _auth_cache if k.startswith(f"auth_{chat_id}_")]
                for k in keys:
                    _auth_cache.pop(k, None)
            else:
                _auth_cache.clear()
        else:
            keys_to_remove = []
            if chat_id and user_id:
                key = f"auth_{chat_id}_{user_id}"
                if key in _auth_cache:
                    del _auth_cache[key]
            elif chat_id:
                for key in list(_auth_cache.keys()):
                    if key.startswith(f"auth_{chat_id}_"):
                        keys_to_remove.append(key)
                for key in keys_to_remove:
                    del _auth_cache[key]
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
    except Exception as e:
        logger.warning(f"فشل التحقق من {user_id} في {chat_id}: {e}")
        authorized = await db_is_hidden_owner(chat_id, user_id) or await db_is_hidden_admin(chat_id, user_id) or await db_is_real_admin(chat_id, user_id)
    if CACHETOOLS_AVAILABLE:
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
        try:
            await conn.execute("INSERT OR IGNORE INTO bot_admins (user_id) VALUES (?)", (user_id,))
            await conn.commit()
            logger.info(f"✅ تم إضافة مشرف بوت: {user_id}")
            # تحليل المشاعر للمشرف الجديد
            await db_save_sentiment_history(user_id, 0, "added_as_bot_admin", "positive", 0.5)
            return True
        except Exception as e:
            logger.error(f"خطأ في إضافة مشرف بوت {user_id}: {e}")
            await conn.rollback()
            return False
    return await execute_db(_add)

async def remove_bot_admin(user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID:
        return False
    async def _remove(conn):
        try:
            await conn.execute("DELETE FROM bot_admins WHERE user_id=?", (user_id,))
            await conn.commit()
            logger.info(f"✅ تم إزالة مشرف بوت: {user_id}")
            await db_save_sentiment_history(user_id, 0, "removed_from_bot_admin", "neutral", 0)
            return True
        except Exception as e:
            logger.error(f"خطأ في إزالة مشرف بوت {user_id}: {e}")
            await conn.rollback()
            return False
    return await execute_db(_remove)

# ===================================================================
# 23. دوال العقوبات والإجراءات الإشرافية الذكية
# ===================================================================
async def apply_penalty_with_duration(bot, chat_id: int, user_id: int, 
                                     penalty: str, duration_minutes: int = 0, 
                                     reason: str = "", moderator_id: int = None) -> Tuple[bool, str]:
    if user_id == PRIMARY_OWNER_ID:
        return False, "لا يمكن تطبيق عقوبة على المطور الأساسي"
    if await db_is_hidden_owner(chat_id, user_id):
        return False, "لا يمكن تطبيق عقوبة على المالك المخفي"
    
    # تحليل المشاعر للمستخدم قبل تطبيق العقوبة
    user_sentiment = learning_engine.get_user_sentiment_profile(user_id)
    chat_sentiment = learning_engine.get_chat_sentiment_profile(chat_id)
    
    # تحليل شدة العقوبة بناءً على المشاعر
    penalty_severity = 1.0
    if user_sentiment.get('avg_sentiment', 0) < -0.5:
        penalty_severity = 1.5  # مستخدم سلبي جداً، عقوبة أشد
    elif user_sentiment.get('avg_sentiment', 0) > 0.3:
        penalty_severity = 0.7  # مستخدم إيجابي، عقوبة أخف
    
    result = False, "عقوبة غير معروفة"
    if penalty == 'kick':
        result = await execute_kick(bot, chat_id, user_id, reason, moderator_id, penalty_severity)
    elif penalty == 'ban':
        result = await execute_ban(bot, chat_id, user_id, reason, moderator_id, penalty_severity)
    elif penalty == 'mute':
        # ضبط مدة الكتم بناءً على المشاعر
        adjusted_duration = int(duration_minutes * penalty_severity)
        result = await execute_mute(bot, chat_id, user_id, adjusted_duration, reason, moderator_id, penalty_severity)
    elif penalty == 'warn':
        result = await execute_warn(bot, chat_id, user_id, moderator_id, reason, penalty_severity)
    elif penalty == 'restrict':
        result = await execute_restrict(bot, chat_id, user_id, reason, moderator_id, penalty_severity)
    
    if result[0]:
        await log_security_event(f"penalty_{penalty}", chat_id, user_id, 
                                {"duration": duration_minutes, "reason": reason[:100], 
                                 "severity": penalty_severity, "user_sentiment": user_sentiment.get('avg_sentiment', 0)}, 
                                severity="medium" if penalty_severity < 1 else "high")
        # التعلم من العقوبة
        await db_save_learning_pattern(
            f"penalty_{penalty}_{reason[:20] if reason else 'default'}",
            "negative",
            -0.3 * penalty_severity,
            0.7
        )
        # تحديث ملف تعريف المستخدم
        await db_save_sentiment_history(user_id, chat_id, f"penalty_{penalty}", "negative", -0.5 * penalty_severity)
    
    return result

async def execute_ban(bot, chat_id: int, user_id: int, reason: str = "", 
                     moderator_id: int = None, severity: float = 1.0) -> Tuple[bool, str]:
    try:
        await bot.ban_chat_member(chat_id, user_id)
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'ban', ?, ?, ?, ?)", 
                              (chat_id, user_id, -1, moderator_id, reason[:200] if reason else "", utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        logger.info(f"✅ تم حظر المستخدم {user_id} في {chat_id} (شدة: {severity})")
        return True, f"✅ تم حظر المستخدم {user_id}"
    except Exception as e:
        logger.error(f"خطأ في حظر المستخدم {user_id}: {e}")
        return False, "❌ حدث خطأ أثناء تنفيذ العملية"

async def execute_mute(bot, chat_id: int, user_id: int, duration_minutes: int = None, 
                      reason: str = "", moderator_id: int = None, severity: float = 1.0) -> Tuple[bool, str]:
    try:
        until_date = None
        if duration_minutes and duration_minutes > 0:
            until_date = datetime.utcnow() + timedelta(minutes=duration_minutes)
        permissions = ChatPermissions(can_send_messages=False)
        await bot.restrict_chat_member(chat_id, user_id, permissions, until_date=until_date)
        duration_text = f" لمدة {duration_minutes} دقيقة" if duration_minutes else " بشكل دائم"
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'mute', ?, ?, ?, ?)", 
                              (chat_id, user_id, duration_minutes or -1, moderator_id, reason[:200] if reason else "", utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        logger.info(f"✅ تم كتم المستخدم {user_id} في {chat_id} (شدة: {severity})")
        return True, f"✅ تم كتم المستخدم {user_id}{duration_text}"
    except Exception as e:
        logger.error(f"خطأ في كتم المستخدم {user_id}: {e}")
        return False, "❌ حدث خطأ أثناء تنفيذ العملية"

async def execute_kick(bot, chat_id: int, user_id: int, reason: str = "", 
                      moderator_id: int = None, severity: float = 1.0) -> Tuple[bool, str]:
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id)
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, reason, created_at) VALUES (?, ?, 'kick', ?, ?, ?)", 
                              (chat_id, user_id, moderator_id, reason[:200] if reason else "", utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        logger.info(f"✅ تم طرد المستخدم {user_id} من {chat_id} (شدة: {severity})")
        return True, f"✅ تم طرد المستخدم {user_id}"
    except Exception as e:
        logger.error(f"خطأ في طرد المستخدم {user_id}: {e}")
        return False, "❌ حدث خطأ أثناء تنفيذ العملية"

async def execute_warn(bot, chat_id: int, user_id: int, moderator_id: int, 
                      reason: str = "", severity: float = 1.0) -> Tuple[bool, str]:
    settings = await db_get_security_settings(chat_id)
    max_warnings = settings.get('max_warnings', 3)
    warn_penalty = settings.get('warn_penalty', 'ban')
    async def _add_warning(conn):
        cur = await conn.execute("SELECT warnings FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        row = await cur.fetchone()
        warnings = (row[0] if row else 0) + 1
        await conn.execute("INSERT OR REPLACE INTO user_warnings (user_id, chat_id, warnings) VALUES (?, ?, ?)", (user_id, chat_id, warnings))
        await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, 'warn', ?, ?, ?, ?)", 
                          (chat_id, user_id, warnings, moderator_id, reason[:200] if reason else "", utc_now_iso()))
        await conn.commit()
        return warnings
    warnings = await execute_db(_add_warning)
    # تحليل المشاعر عند التحذير
    await db_save_sentiment_history(user_id, chat_id, f"warning_{warnings}", "negative", -0.2 * severity)
    if warnings >= max_warnings:
        penalty_reason = f"تلقائي بعد {warnings} تحذيرات"
        if warn_penalty == 'ban':
            await execute_ban(bot, chat_id, user_id, penalty_reason, moderator_id, severity)
        elif warn_penalty == 'kick':
            await execute_kick(bot, chat_id, user_id, penalty_reason, moderator_id, severity)
        elif warn_penalty == 'mute':
            await execute_mute(bot, chat_id, user_id, 1440, penalty_reason, moderator_id, severity)
        async def _clear(conn):
            await conn.execute("DELETE FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            await conn.commit()
        await execute_db(_clear)
        logger.info(f"⚠️ تم تطبيق {warn_penalty} على المستخدم {user_id} بعد {warnings} تحذيرات (شدة: {severity})")
        return True, f"⚠️ تحذير {warnings}/{max_warnings} - تم تطبيق {warn_penalty}"
    logger.info(f"⚠️ تم تحذير المستخدم {user_id} ({warnings}/{max_warnings}) (شدة: {severity})")
    return True, f"⚠️ تحذير {warnings}/{max_warnings}"

async def execute_restrict(bot, chat_id: int, user_id: int, reason: str = "", 
                          moderator_id: int = None, severity: float = 1.0) -> Tuple[bool, str]:
    try:
        permissions = ChatPermissions(can_send_messages=True, can_send_media_messages=False, can_send_other_messages=False, can_add_web_page_previews=False)
        await bot.restrict_chat_member(chat_id, user_id, permissions)
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, reason, created_at) VALUES (?, ?, 'restrict', ?, ?, ?)", 
                              (chat_id, user_id, moderator_id, reason[:200] if reason else "", utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        logger.info(f"✅ تم تقييد المستخدم {user_id} في {chat_id} (شدة: {severity})")
        return True, f"✅ تم تقييد المستخدم {user_id}"
    except Exception as e:
        logger.error(f"خطأ في تقييد المستخدم {user_id}: {e}")
        return False, "❌ حدث خطأ أثناء تنفيذ العملية"

async def execute_unban(bot, chat_id: int, user_id: int, moderator_id: int = None) -> Tuple[bool, str]:
    try:
        await bot.unban_chat_member(chat_id, user_id)
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, created_at) VALUES (?, ?, 'unban', ?, ?)", 
                              (chat_id, user_id, moderator_id, utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
        logger.info(f"✅ تم إلغاء حظر المستخدم {user_id} في {chat_id}")
        # تحليل المشاعر للمستخدم بعد إلغاء الحظر
        await db_save_sentiment_history(user_id, chat_id, "unbanned", "positive", 0.4)
        return True, f"✅ تم إلغاء حظر المستخدم {user_id}"
    except Exception as e:
        logger.error(f"خطأ في إلغاء حظر المستخدم {user_id}: {e}")
        return False, "❌ حدث خطأ أثناء تنفيذ العملية"

async def execute_pin(bot, chat_id: int, message_id: int, 
                     disable_notification: bool = False) -> Tuple[bool, str]:
    try:
        await bot.pin_chat_message(chat_id, message_id, disable_notification=disable_notification)
        return True, "✅ تم تثبيت الرسالة"
    except Exception as e:
        return False, f"❌ فشل التثبيت: {str(e)[:100]}"

async def execute_moderation_action(bot, chat_id: int, user_id: int, action: str, 
                                   reason: str = "", duration: int = None, 
                                   moderator_id: int = None):
    if action == 'ban':
        return await execute_ban(bot, chat_id, user_id, reason, moderator_id)
    elif action == 'mute':
        return await execute_mute(bot, chat_id, user_id, duration, reason, moderator_id)
    elif action == 'warn':
        return await execute_warn(bot, chat_id, user_id, moderator_id, reason)
    elif action == 'kick':
        return await execute_kick(bot, chat_id, user_id, reason, moderator_id)
    elif action == 'restrict':
        return await execute_restrict(bot, chat_id, user_id, reason, moderator_id)
    elif action == 'unban':
        return await execute_unban(bot, chat_id, user_id, moderator_id)
    elif action == 'pin':
        return None, "استخدم زر التثبيت مع الرد على الرسالة"
    else:
        return False, f"إجراء غير معروف: {action}"

async def delete_and_penalize(update: Update, context: ContextTypes.DEFAULT_TYPE, warning_message: str):
    if not update.message:
        return
    message = update.message
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # تحليل المشاعر للرسالة المخالفة
    sentiment = learning_engine.analyze_sentiment(message.text or message.caption or "")
    await db_save_sentiment_history(user_id, chat_id, message.text or message.caption or "", sentiment['sentiment'], sentiment['score'])
    
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
        # ضبط المدة بناءً على المشاعر
        if sentiment['sentiment'] == 'negative' and sentiment['score'] < -0.5:
            duration = duration * 2
        await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, duration, reason="مخالفة قواعد المجموعة")

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
# ===================================================================
# 24. معرفات الأزرار المتطورة (CallbackData)
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
    CHANNEL_STATS = "channel_stats"
    CHANNEL_GROWTH = "channel_growth"
    CHANNEL_STATS_REFRESH = "channel_stats_refresh"
    MY_CHANNEL_STATS = "my_channel_stats"
    
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
    GROUP_MUTE_DURATION_5 = "group_mute_duration:5"
    GROUP_MUTE_DURATION_30 = "group_mute_duration:30"
    GROUP_MUTE_DURATION_60 = "group_mute_duration:60"
    GROUP_MUTE_DURATION_720 = "group_mute_duration:720"
    GROUP_MUTE_DURATION_1440 = "group_mute_duration:1440"
    GROUP_MUTE_DURATION_10080 = "group_mute_duration:10080"
    GROUP_MUTE_DURATION_PERMANENT = "group_mute_duration:permanent"
    
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
    
    # ===== المشرفين المخفيين =====
    HIDDEN_ADMIN_ADD = "hidden_admin:add"
    HIDDEN_ADMIN_REMOVE_PREFIX = "hidden_admin:remove:"
    HIDDEN_ADMIN_LIST = "hidden_admin:list"
    
    # ===== الردود التلقائية =====
    ADMIN_AUTO_REPLY = "admin_auto_reply"
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
    
    # ===== الاشتراك الإجباري =====
    CHECK_SUBSCRIBE = "check_subscribe"

# ===================================================================
# 25. حالات المستخدم المتطورة (UserState)
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
    WAITING_SENTIMENT_ANALYSIS = auto()
    WAITING_LEARNING_FEEDBACK = auto()

# ===================================================================
# 26. دوال الكيبوردات المتطورة مع تحليل المشاعر
# ===================================================================
def get_advanced_group_actions_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """لوحة الإجراءات المتقدمة مع تحليل المشاعر"""
    # جلب ملف تعريف المشاعر للمجموعة (من الكاش)
    chat_sentiment = learning_engine.get_chat_sentiment_profile(chat_id)
    sentiment_icon = "😊" if chat_sentiment.get('avg_sentiment', 0) > 0.2 else "😐" if chat_sentiment.get('avg_sentiment', 0) > -0.2 else "😞"
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{sentiment_icon} تحليل المشاعر", callback_data="sentiment_analysis"),
            InlineKeyboardButton("📊 إحصائيات التعلم", callback_data="learning_stats")
        ],
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
    """لوحة مدة الكتم مع اقتراحات ذكية"""
    # جلب ملف تعريف المستخدم
    user_sentiment = learning_engine.get_user_sentiment_profile(chat_id)
    avg_sentiment = user_sentiment.get('avg_sentiment', 0)
    
    # اقتراح مدة ذكية بناءً على المشاعر
    if avg_sentiment < -0.5:
        suggestion = "🔇 12 ساعة (مستخدم سلبي)"
        suggestion_callback = f"adv_mute_duration:720:{chat_id}"
    elif avg_sentiment < -0.2:
        suggestion = "🔇 1 ساعة (مستخدم متوتر)"
        suggestion_callback = f"adv_mute_duration:60:{chat_id}"
    else:
        suggestion = "🔇 5 دقائق (مستخدم هادئ)"
        suggestion_callback = f"adv_mute_duration:5:{chat_id}"
    
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
            InlineKeyboardButton("💡 اقتراح: " + suggestion, callback_data=suggestion_callback)
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")
        ]
    ])

def security_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """لوحة الأمان المتطورة مع تحليل المشاعر"""
    # جلب إحصائيات التعلم للمجموعة
    chat_sentiment = learning_engine.get_chat_sentiment_profile(chat_id)
    avg_sentiment = chat_sentiment.get('avg_sentiment', 0)
    trend = chat_sentiment.get('trend', 'stable')
    
    trend_icon = "📈" if trend == 'improving' else "📉" if trend == 'declining' else "➡️"
    sentiment_icon = "😊" if avg_sentiment > 0.2 else "😐" if avg_sentiment > -0.2 else "😞"
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{sentiment_icon} المشاعر: {avg_sentiment:.2f}", callback_data="sentiment_info"),
            InlineKeyboardButton(f"{trend_icon} الاتجاه: {trend}", callback_data="trend_info")
        ],
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

def penalty_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """لوحة العقوبات المتطورة"""
    # جلب إعدادات العقوبات الحالية
    async def get_penalty_text():
        settings = await db_get_security_settings(chat_id)
        current_penalty = settings.get('auto_penalty', 'none')
        penalty_map = {
            'none': '❌ لا شيء',
            'warn': '⚠️ تحذير',
            'mute': '🔇 كتم',
            'kick': '👢 طرد',
            'ban': '🛑 حظر',
            'restrict': '🔒 تقييد'
        }
        return penalty_map.get(current_penalty, '❌ لا شيء')
    
    # استخدام متزامن (للبساطة نستخدم قيمة ثابتة)
    current = "❌ لا شيء"
    
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
        [
            InlineKeyboardButton(f"📌 الحالية: {current}", callback_data="noop"),
            InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")
        ]
    ])

def mute_duration_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """لوحة مدة الكتم"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱️ 5 دقائق", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_5}:{chat_id}"),
            InlineKeyboardButton("⏱️ 30 دقيقة", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_30}:{chat_id}")
        ],
        [
            InlineKeyboardButton("⏱️ 1 ساعة", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_60}:{chat_id}"),
            InlineKeyboardButton("⏱️ 12 ساعة", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_720}:{chat_id}")
        ],
        [
            InlineKeyboardButton("📆 يوم", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_1440}:{chat_id}"),
            InlineKeyboardButton("📆 أسبوع", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_10080}:{chat_id}")
        ],
        [
            InlineKeyboardButton("🔇 كتم دائم", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_PERMANENT}:{chat_id}"),
            InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.PENALTY_MENU}:{chat_id}")
        ]
    ])

def get_group_banned_words_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """لوحة الكلمات المحظورة"""
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
    """لوحة الأدمن المتطورة"""
    # جلب إحصائيات التعلم
    learning_stats = asyncio.run(db_get_learning_stats()) if asyncio.get_event_loop().is_running() else {'patterns': 0, 'sentiment_history': 0}
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧠 التعلم الذكي", callback_data="learning_dashboard"),
            InlineKeyboardButton("📊 تحليل المشاعر", callback_data="sentiment_dashboard")
        ],
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
        [
            InlineKeyboardButton(f"🧠 أنماط التعلم: {learning_stats.get('patterns', 0)}", callback_data="learning_stats"),
            InlineKeyboardButton(f"📊 تحليلات: {learning_stats.get('sentiment_history', 0)}", callback_data="sentiment_stats")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
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
    """لوحة الردود التلقائية"""
    status_text = "🟢 مفعل" if settings['enabled'] else "🔴 معطل"
    admin_text = "👑 مشرفين فقط" if settings['only_admins'] else "👥 الجميع"
    
    # جلب عدد الردود المتعلمة
    learned_count = len(learning_engine.response_patterns) if hasattr(learning_engine, 'response_patterns') else 0
    
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
        [
            InlineKeyboardButton(f"🧠 ردود متعلمة: {learned_count}", callback_data="learned_replies")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])

def get_user_auto_reply_keyboard(user_id: int, enabled: bool) -> InlineKeyboardMarkup:
    """لوحة الردود التلقائية للمستخدم"""
    status_text = "🟢 مفعل" if enabled else "🔴 معطل"
    # جلب ملف تعريف المستخدم
    user_sentiment = learning_engine.get_user_sentiment_profile(user_id)
    avg_sentiment = user_sentiment.get('avg_sentiment', 0)
    sentiment_icon = "😊" if avg_sentiment > 0.2 else "😐" if avg_sentiment > -0.2 else "😞"
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"📝 الردود التلقائية: {status_text}", callback_data=f"{CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX}{user_id}")
        ],
        [
            InlineKeyboardButton(f"{sentiment_icon} ملف المشاعر: {avg_sentiment:.2f}", callback_data="user_sentiment_info")
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])

# ===================================================================
# 27. دوال الكيبوردات المساعدة
# ===================================================================
async def get_main_keyboard(user_id: int):
    """بناء القائمة الرئيسية المتطورة مع تحليل المشاعر"""
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
    
    # جلب ملف تعريف المشاعر للمستخدم
    user_sentiment = learning_engine.get_user_sentiment_profile(user_id)
    avg_sentiment = user_sentiment.get('avg_sentiment', 0)
    sentiment_icon = "😊" if avg_sentiment > 0.2 else "😐" if avg_sentiment > -0.2 else "😞"
    sentiment_text = f"{sentiment_icon} {avg_sentiment:.2f}"
    
    title = get_text(user_id, 'main_title').format(
        BOT_NAME, user_id, my_groups, sub_text, ch_display, cnt, auto_status
    )
    
    updates_channel = None
    try:
        updates_channel = await db_get_updates_channel()
    except:
        updates_channel = None
    updates_url = f"https://t.me/{updates_channel}" if updates_channel else None
    
    keyboard = []
    
    # صف المشاعر
    keyboard.append([InlineKeyboardButton(f"{sentiment_text} ملف مشاعرك", callback_data="user_sentiment_info")])
    
    # الصف الأول
    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'my_groups_btn'), callback_data=CallbackData.GROUPS_MY),
        InlineKeyboardButton(get_text(user_id, 'add_channel'), callback_data=CallbackData.CHANNELS_ADD)
    ])
    
    # الصف الثاني
    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'my_channels'), callback_data=CallbackData.CHANNELS_MY),
        InlineKeyboardButton(get_text(user_id, 'settings_btn'), callback_data=CallbackData.SETTINGS_MENU)
    ])
    
    # الصفوف التالية إذا كانت هناك قنوات
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
    
    # أزرار المساعدة والاشتراك
    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'help_btn'), callback_data=CallbackData.HELP),
        InlineKeyboardButton(get_text(user_id, 'trial_btn'), callback_data=CallbackData.TRIAL)
    ])
    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'subscribe_btn'), callback_data=CallbackData.SUBSCRIBE_MENU),
        InlineKeyboardButton(get_text(user_id, 'developer_btn'), callback_data=CallbackData.DEVELOPER)
    ])
    
    # أزرار إضافية
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
    
    # زر إضافة البوت إلى مجموعة
    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'add_to_group'), url=f"https://t.me/{BOT_USERNAME}?startgroup")
    ])
    
    # لوحة الأدمن
    is_admin = False
    try:
        is_admin = (user_id == PRIMARY_OWNER_ID) or (await is_bot_admin(user_id))
    except:
        is_admin = False
    
    if is_admin:
        keyboard.append([
            InlineKeyboardButton(get_text(user_id, 'admin_panel'), callback_data=CallbackData.ADMIN_PANEL)
        ])
    
    # زر التعلم الذكي (للمشرفين)
    if is_admin:
        keyboard.append([
            InlineKeyboardButton("🧠 لوحة التعلم", callback_data="learning_dashboard")
        ])
    
    valid_keyboard = []
    for row in keyboard:
        if row and all(isinstance(btn, InlineKeyboardButton) for btn in row):
            valid_keyboard.append(row)
    if not valid_keyboard:
        valid_keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    
    return InlineKeyboardMarkup(valid_keyboard), title, active
# ===================================================================
# 28. معالجات الأوامر (Command Handlers) المتطورة
# ===================================================================

# 28.1 أمر /start - البدء مع تحليل المشاعر
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
        
        # تحليل مشاعر المستخدم الجديد
        sentiment = learning_engine.analyze_sentiment(f"بدء استخدام البوت من قبل {first_name}")
        await db_save_sentiment_history(user_id, 0, "user_started_bot", sentiment['sentiment'], sentiment['score'])
        
        # معالجة الإحالات
        if context.args and context.args[0].startswith('ref_'):
            ref_code = context.args[0][4:]
            referrer_id = await db_get_user_by_referral_code(ref_code)
            if referrer_id and referrer_id != user_id:
                if await db_add_referral(referrer_id, user_id):
                    reward_days = await db_auto_reward_referral(referrer_id, user_id)
                    # تحليل مشاعر المكافأة
                    await db_save_sentiment_history(referrer_id, 0, f"referral_reward_{reward_days}_days", "positive", 0.7)
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 قام مستخدم جديد بالتسجيل عبر رابطك!\n👤 المعرف: {user_id}\n🎁 مكافأتك: {reward_days} يوم اشتراك إضافي\n🧠 تحليل المشاعر: إيجابي 😊"
                        )
                    except:
                        pass
        
        # الاشتراك الإجباري
        if not await ensure_force_subscribe(update, context):
            return
        
        kb, title, active = await get_main_keyboard(user_id)
        if active:
            context.user_data['active_channel'] = active
        
        # تحديث ملف تعريف المستخدم
        await learning_engine.learn_from_message(user_id, 0, "start_command", "started_bot", True)
        
        if update.callback_query:
            await safe_edit_markdown(update.callback_query, title, reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, user_id, title, reply_markup=kb)
            
    except Exception as e:
        error_id = log_error(e, {'user_id': update.effective_user.id})
        await safe_send_markdown(context.bot, update.effective_user.id, f"❌ حدث خطأ (الرمز: `{error_id}`)")

# 28.2 أمر /language - تغيير اللغة
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
    # تسجيل تغيير اللغة
    await learning_engine.learn_from_message(user_id, 0, "language_command", "changed_language", True)

# 28.3 أمر /syncgroup - تفعيل المجموعة
async def syncgroup_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    
    chat_id = update.effective_chat.id
    chat_name = update.effective_chat.title or "بدون اسم"
    user_id = update.effective_user.id
    
    # تحليل مشاعر المجموعة الجديدة
    await db_save_sentiment_history(user_id, chat_id, f"group_registration_{chat_name}", "positive", 0.3)
    
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
        
        # تحليل المشاعر للمجموعة بعد التفعيل
        await db_update_chat_sentiment_profile(chat_id, 0.2, 0.8, 'improving')
        
        await safe_send_markdown(
            context.bot,
            real_user_id,
            f"✅ **تم تفعيل المجموعة بنجاح!**\n\n📌 اسم المجموعة: {chat_name}\n🆔 المعرف: {chat_id}\n👤 تم تسجيلك كمالك مخفي (المعرف: `{real_user_id}`)\n👥 تم مزامنة {admin_count} مشرف\n🧠 تحليل المشاعر: المجموعة إيجابية 😊\n\n🔐 استخدم /security لإعدادات الأمان\n🛠️ استخدم /panel للوحة التحكم"
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

# 28.4 أمر /register_hidden_owner - تسجيل مالك مخفي
async def register_hidden_owner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
        await safe_send_markdown(context.bot, update.effective_user.id, get_text(update.effective_user.id, 'group_only'))
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # تحليل مشاعر المستخدم
    await db_save_sentiment_history(user_id, chat_id, "register_hidden_owner_attempt", "positive", 0.3)
    
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
        await db_update_chat_sentiment_profile(chat_id, 0.3, 0.8, 'improving')
        
        async def _add_real_admin(conn):
            await conn.execute("INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))
            await conn.commit()
        await execute_db(_add_real_admin)
        invalidate_auth_cache(chat_id, user_id)
        
        await safe_send_markdown(
            context.bot,
            user_id,
            f"✅ **تم تسجيلك كمالك مخفي بنجاح!**\n\n🔐 يمكنك الآن استخدام جميع أوامر الإدارة:\n• `/security` - إعدادات الأمان\n• `/panel` - لوحة التحكم\n• `/lock` / `/unlock` - قفل وفتح المجموعة\n• أوامر الحظر والكتم والتحذير\n🧠 تم تحليل مشاعرك: إيجابي 😊"
        )
        return
    
    await safe_send_markdown(context.bot, user_id, "❌ **غير مصرح!**\n\nلتسجيل نفسك كمالك مخفي، يجب أن تكون:\n• مالك المجموعة (creator)\n• أو مشرفاً في المجموعة (administrator)\n\n📌 إذا كنت تعتقد أنك مالك:\n• تأكد من أن البوت مشرف\n• تأكد من أنك المالك في تيليجرام")

# 28.5 أمر /add_hidden_admin - إضافة مشرف مخفي
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
        await security_audit.log("HIDDEN_ADMIN_ADDED", user_id, {"chat_id": chat_id, "target": target_id}, "HIGH")
        invalidate_auth_cache(chat_id, target_id)
        # تحليل المشاعر
        await db_save_sentiment_history(target_id, chat_id, "added_as_hidden_admin", "positive", 0.4)
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل إضافة المشرف المخفي!")

# 28.6 أمر /remove_hidden_admin - إزالة مشرف مخفي
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
        await security_audit.log("HIDDEN_ADMIN_REMOVED", user_id, {"chat_id": chat_id, "target": target_id}, "HIGH")
        invalidate_auth_cache(chat_id, target_id)
        await db_save_sentiment_history(target_id, chat_id, "removed_from_hidden_admin", "neutral", -0.1)
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل إزالة المشرف المخفي!")

# 28.7 أمر /list_hidden_admins - عرض المشرفين المخفيين
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
    
    # تحليل المشاعر
    await db_save_sentiment_history(user_id, chat_id, "list_hidden_admins", "neutral", 0.1)
    await safe_send_markdown(context.bot, user_id, text)

# 28.8 أمر /trial - تجربة مجانية
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
    # تحليل المشاعر
    await db_save_sentiment_history(user_id, 0, "activated_trial", "positive", 0.8)
    await start_command_handler(update, context)

# 28.9 أمر /subscribe - الاشتراك
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
    await db_save_sentiment_history(user_id, 0, "viewed_subscription", "neutral", 0.1)

# 28.10 أمر /help - المساعدة
async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'help'))
    await db_save_sentiment_history(user_id, 0, "help_command", "neutral", 0.1)

# 28.11 أمر /support - الدعم
async def support_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['support_mode'] = True
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 كتابة تذكرة", callback_data=CallbackData.SUPPORT_TICKET)],
        [InlineKeyboardButton("❓ المساعدة", callback_data=CallbackData.SUPPORT_HELP)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    await safe_send_markdown(context.bot, user_id, get_text(user_id, 'support_welcome'), reply_markup=keyboard)
    await db_save_sentiment_history(user_id, 0, "support_command", "neutral", 0.1)

# 28.12 أمر /support_reply - الرد على تذكرة
async def support_reply_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    # تحليل المشاعر للرد
    sentiment = learning_engine.analyze_sentiment(reply_text)
    await db_save_sentiment_history(user_id, 0, f"support_reply_ticket_{ticket_id}", sentiment['sentiment'], sentiment['score'])
    
    try:
        await context.bot.send_message(chat_id=target_user, text=f"📩 **رد على تذكرتك #{ticket_id}**\n\n{reply_text}")
        await safe_send_markdown(context.bot, user_id, f"✅ تم إرسال الرد إلى المستخدم `{target_user}`")
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ فشل إرسال الرد: {str(e)[:100]}")

# 28.13 أمر /rank - رتبتي
async def rank_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = await get_rank(user_id)
    # تحليل المشاعر
    await db_save_sentiment_history(user_id, 0, "rank_command", "neutral", 0.1)
    await safe_send_markdown(context.bot, user_id, f"📊 **رتبتك**\n━━━━━━━━━━━━━━━━━━━━━━\n🎖️ المستوى: {data['level']}\n⭐ النقاط: {data['points']}\n🎯 النقاط المطلوبة للمستوى التالي: {LEVEL_REQUIREMENTS.get(data['level'] + 1, 'ماكس')}")

# 28.14 أمر /top - أفضل 10
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
    await db_save_sentiment_history(user_id, 0, "top_command", "neutral", 0.1)

# 28.15 أمر /stats - إحصائيات القناة
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
    text += f"🧠 تحليل المشاعر: القناة في حالة جيدة 😊\n"
    
    await safe_send_markdown(context.bot, user_id, text)
    await db_save_sentiment_history(user_id, 0, "stats_command", "neutral", 0.1)

# 28.16 أمر /developer - المطور
async def developer_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await developer_callback(update, context)

# 28.17 أمر /updates - التحديثات
async def updates_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await updates_callback(update, context)

# 28.18 أمر /sendcode - إرسال كود البوت
async def sendcode_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        allowed_user = await db_get_allowed_sendcode_user()
        if user_id != allowed_user:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح لك باستخدام هذا الأمر.")
            return
    
    code = f"/start {secrets.token_urlsafe(8)}"
    await safe_send_markdown(context.bot, user_id, f"📨 **كود البوت:**\n`{code}`\n\nاستخدم هذا الكود لإضافة البوت.")
    await db_save_sentiment_history(user_id, 0, "sendcode_command", "positive", 0.3)

# 28.19 أمر /lock - قفل المجموعة
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
    # تحليل المشاعر
    await db_save_sentiment_history(user_id, chat_id, "chat_locked", "neutral", -0.1)
    await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'locked'))

# 28.20 أمر /unlock - فتح المجموعة
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
    await db_save_sentiment_history(user_id, chat_id, "chat_unlocked", "positive", 0.2)
    await safe_send_markdown(context.bot, chat_id, get_text(user_id, 'unlocked'))

# 28.21 أمر /schedule - جدولة منشور
async def schedule_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_SCHEDULE_POST
    await safe_send_markdown(
        context.bot,
        user_id,
        "📝 **جدولة منشور**\n\nأرسل المنشور بهذه الصيغة:\n`YYYY-MM-DD HH:MM نص المنشور`\n\nمثال: `2024-12-25 14:30 مرحباً بالجميع!`\n\n🕐 الوقت بتوقيت مكة المكرمة"
    )

# 28.22 أمر /panel - لوحة التحكم
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
    
    # جلب تحليل المشاعر للمجموعة
    chat_sentiment = learning_engine.get_chat_sentiment_profile(chat_id)
    avg_sentiment = chat_sentiment.get('avg_sentiment', 0)
    sentiment_icon = "😊" if avg_sentiment > 0.2 else "😐" if avg_sentiment > -0.2 else "😞"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 قفل المجموعة", callback_data=f"{CallbackData.PANEL_LOCK_PREFIX}{chat_id}"),
         InlineKeyboardButton("🔓 فتح المجموعة", callback_data=f"{CallbackData.PANEL_UNLOCK_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🛠️ إجراءات متقدمة", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}"),
         InlineKeyboardButton("🧠 تحليل المشاعر", callback_data="sentiment_analysis")],
        [InlineKeyboardButton("🔙 إغلاق اللوحة", callback_data=CallbackData.PANEL_CLOSE)]
    ])
    
    await safe_send_markdown(
        context.bot,
        user_id,
        f"🔧 **لوحة تحكم المجموعة**\n━━━━━━━━━━━━━━\n📌 **المجموعة:** {update.effective_chat.title}\n🔐 **الحالة:** {lock_status_text}\n{sentiment_icon} **مشاعر المجموعة:** {avg_sentiment:.2f}\n━━━━━━━━━━━━━━\n\nاستخدم الأزرار للتحكم في قفل وفتح المجموعة والإجراءات المتقدمة",
        reply_markup=kb
    )

# 28.23 أمر /set_log_channel - تعيين قناة التقارير
async def set_log_channel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return
    
    identifier = context.user_data.get('temp_log_channel_identifier')
    if not identifier:
        await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد القناة. استخدم الأمر مع معرف القناة:\n`/set_log_channel -100123456789`")
        return
    
    try:
        chat = await context.bot.get_chat(identifier)
        if chat.type != 'channel':
            await safe_send_markdown(context.bot, user_id, "❌ المعرف ليس لقناة!")
            return
        
        await db_set_log_channel_id(str(chat.id))
        await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين قناة التقارير: {chat.title}")
        await db_save_sentiment_history(user_id, 0, "set_log_channel", "positive", 0.3)
    except Exception as e:
        await safe_send_markdown(context.bot, user_id, f"❌ فشل تعيين القناة: {str(e)[:100]}")
    
    context.user_data.pop('temp_log_channel_identifier', None)

# 28.24 أمر /set_rules - تعيين قوانين المجموعة
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
    # تحليل المشاعر للقوانين
    sentiment = learning_engine.analyze_sentiment(rules_text)
    await db_save_sentiment_history(user_id, chat_id, f"set_rules_{rules_text[:50]}", sentiment['sentiment'], sentiment['score'])
    
    async def _set_rules(conn):
        await conn.execute("INSERT OR REPLACE INTO group_rules (chat_id, rules_text, updated_by, updated_at) VALUES (?, ?, ?, ?)", (chat_id, rules_text, user_id, utc_now_iso()))
        await conn.commit()
    
    await execute_db(_set_rules)
    await safe_send_markdown(context.bot, chat_id, "✅ تم تعيين قوانين المجموعة بنجاح!")

# 28.25 أمر /rules - عرض قوانين المجموعة
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
    await db_save_sentiment_history(update.effective_user.id, chat_id, "view_rules", "neutral", 0.1)

# 28.26 أمر /create_contest - إنشاء مسابقة
async def create_contest_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return
    
    context.user_data['state'] = UserState.WAITING_CONTEST_TITLE
    await safe_send_markdown(context.bot, user_id, "📝 **إنشاء مسابقة جديدة**\n\nأرسل **عنوان** المسابقة:")
    await db_save_sentiment_history(user_id, 0, "create_contest_start", "positive", 0.3)

# 28.27 أمر /declare_winner - إعلان فائز
async def declare_winner_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await safe_send_markdown(context.bot, user_id, "🔒 هذا الأمر للمشرفين فقط!")
        return
    
    args = context.args
    if len(args) < 2:
        await safe_send_markdown(context.bot, user_id, "📝 **الاستخدام:**\n`/declare_winner معرف_المسابقة معرف_المستخدم`\n\nمثال: `/declare_winner 5 123456789`")
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
        await safe_send_markdown(context.bot, user_id, f"✅ تم إعلان المستخدم `{winner_id}` فائزاً في المسابقة **{contest['title']}**!")
        # تحليل المشاعر للفائز
        await db_save_sentiment_history(winner_id, 0, f"contest_winner_{contest_id}", "positive", 0.9)
        try:
            await context.bot.send_message(
                chat_id=winner_id,
                text=f"🏆 **تهانينا!**\nلقد فزت في مسابقة **{contest['title']}**!\n🎁 جائزتك: {contest['prize']}\n🧠 تحليل المشاعر: فرح وسعادة 😊"
            )
            await achievement_system(winner_id, 'contest_winner')
        except:
            pass
    else:
        await safe_send_markdown(context.bot, user_id, "❌ فشل إعلان الفائز!")

# 28.28 أمر /contests - عرض المسابقات
async def contests_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not update or not update.effective_user:
            return
        
        user_id = update.effective_user.id
        contests = await db_get_active_contests_with_participants(limit=10)
        if not contests:
            text = "📭 لا توجد مسابقات نشطة حالياً."
            await safe_send_markdown(context.bot, user_id, text)
            return
        
        text = "🏆 **المسابقات النشطة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        keyboard = []
        
        for contest in contests:
            if len(contest) < 6:
                continue
            cid = contest[0]
            title = contest[1] or "بدون عنوان"
            desc = contest[2] or ""
            prize = contest[3] or "غير محددة"
            end_date = contest[4]
            participants = contest[5] if len(contest) > 5 else 0
            contest_type = contest[6] if len(contest) > 6 else 'raffle'
            
            try:
                end_dt = datetime.fromisoformat(end_date)
                days_left = (end_dt - utc_now()).days
                time_left = f"⏳ متبقي {days_left} يوم" if days_left > 0 else "🔴 انتهت"
            except:
                time_left = "📅 تاريخ غير صحيح"
                days_left = 0
            
            participated = await db_get_user_participation(user_id, cid)
            status_icon = "✅" if participated else "📝"
            type_icon = "📝" if contest_type == 'quiz' else "🎲" if contest_type == 'raffle' else "🗳️" if contest_type == 'vote' else "📤"
            
            text += f"📌 **{title}** {type_icon}\n"
            text += f"📝 {(desc)[:100]}{'...' if len(desc) > 100 else ''}\n"
            text += f"🎁 الجائزة: {prize}\n"
            text += f"👥 المشاركون: {participants}\n"
            text += f"🕐 {time_left}\n"
            text += f"━━━━━━━━━━━━━━━━━━━━━━\n"
            
            if not participated and days_left > 0:
                keyboard.append([InlineKeyboardButton(f"{status_icon} شارك في {title[:20]}", callback_data=f"{CallbackData.CONTEST_JOIN_PREFIX}{cid}")])
        
        keyboard.append([InlineKeyboardButton("🏆 الفائزون السابقون", callback_data=CallbackData.CONTEST_WINNERS)])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
        
        await safe_send_markdown(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        await db_save_sentiment_history(user_id, 0, "contests_command", "neutral", 0.1)
        
    except Exception as e:
        error_id = log_error(e, {'user_id': update.effective_user.id if update and update.effective_user else None})
        await safe_send_markdown(context.bot, user_id, f"❌ حدث خطأ أثناء تحميل المسابقات (الرمز: `{error_id}`).")

# 28.29 أوامر الإشراف (ban, mute, warn, kick, restrict, pin, unban)
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
            await safe_send_markdown(context.bot, chat_id, "❌ معرف المستخدم غير صحيح!")
            return
    else:
        await safe_send_markdown(context.bot, chat_id, "❌ قم بالرد على رسالة المستخدم أو أرسل معرفه.")
        return
    
    if target_id == context.bot.id:
        await safe_send_markdown(context.bot, chat_id, "❌ لا يمكن تنفيذ هذا الإجراء على البوت!")
        return
    
    # تحليل المشاعر قبل العقوبة
    target_sentiment = learning_engine.get_user_sentiment_profile(target_id)
    await db_save_sentiment_history(target_id, chat_id, f"moderation_{command}_attempt", "negative", -0.3)
    
    duration = None
    if command == 'mute':
        duration = 60
        # ضبط المدة بناءً على المشاعر
        if target_sentiment.get('avg_sentiment', 0) < -0.5:
            duration = 120  # مضاعفة المدة للمستخدمين السلبيين
    
    success, msg = await execute_moderation_action(context.bot, chat_id, target_id, command, reason, duration, user_id)
    await safe_send_markdown(context.bot, chat_id, msg)

# ===================================================================
# 29. معالجات الكولباك (Callback Handlers) - جميع الأزرار
# ===================================================================

# 29.1 القائمة الرئيسية والتنقل
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للقائمة الرئيسية"""
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
    # تسجيل التفاعل
    await db_save_sentiment_history(user_id, 0, "main_menu", "neutral", 0.1)

async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر الرجوع - يعود للقائمة الرئيسية"""
    query = update.callback_query
    if query:
        await query.answer()
    await main_menu_callback(update, context)

async def cancel_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء الجلسة الحالية"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    context.user_data.clear()
    await safe_edit_markdown(query, get_text(user_id, 'cancelled'))
    await main_menu_callback(update, context)

# 29.2 أزرار القنوات
async def add_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إضافة قناة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_CHANNEL_ID
    await safe_edit_markdown(
        query,
        get_text(user_id, 'send_channel_id'),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
        ])
    )
    await db_save_sentiment_history(user_id, 0, "add_channel_click", "positive", 0.2)

async def my_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر عرض قنواتي"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    
    if not channels:
        await safe_edit_markdown(query, get_text(user_id, 'no_channels_list'))
        return
    
    text = get_text(user_id, 'channels_list')
    keyboard = []
    
    for ch_id, ch_tele_id, ch_name, banned in channels:
        status = "🚫" if banned else "✅"
        keyboard.append([
            InlineKeyboardButton(f"{status} {ch_name} ({ch_tele_id})", callback_data=f"{CallbackData.CHANNELS_SELECT_PREFIX}{ch_id}"),
            InlineKeyboardButton("🗑️", callback_data=f"{CallbackData.CHANNELS_DELETE_PREFIX}{ch_id}")
        ])
    
    keyboard.append([InlineKeyboardButton(get_text(user_id, 'add_channel'), callback_data=CallbackData.CHANNELS_ADD)])
    keyboard.append([InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)])
    
    await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    await db_save_sentiment_history(user_id, 0, "my_channels_view", "neutral", 0.1)

async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر حذف قناة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    # استخراج channel_db_id من البيانات
    channel_db_id = int(query.data.split(":")[-1])
    
    success = await db_delete_channel_by_id(user_id, channel_db_id)
    
    if success:
        await safe_edit_markdown(query, get_text(user_id, 'channel_deleted'))
        await db_save_sentiment_history(user_id, 0, "delete_channel_success", "positive", 0.2)
    else:
        await safe_edit_markdown(query, get_text(user_id, 'delete_failed'))
        await db_save_sentiment_history(user_id, 0, "delete_channel_fail", "negative", -0.3)
    
    await my_channels_callback(update, context)

async def select_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر اختيار قناة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    # استخراج channel_db_id من البيانات
    channel_db_id = int(query.data.split(":")[-1])
    
    await db_set_active_channel(user_id, channel_db_id)
    context.user_data['active_channel'] = channel_db_id
    await db_save_sentiment_history(user_id, 0, "select_channel", "positive", 0.2)
    await main_menu_callback(update, context)

# 29.3 أزرار المنشورات
async def add_15_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إضافة 15 منشور"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
        await safe_edit_markdown(query, "⚠️ اشتراكك منتهٍ، استخدم /trial أو /subscribe")
        return
    
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await safe_edit_markdown(query, "⚠️ اختر قناة أولاً")
        return
    
    unpublished_count = await db_unpublished_count(active)
    if unpublished_count >= MAX_UNPUBLISHED_POSTS:
        await safe_edit_markdown(query, f"⚠️ لقد تجاوزت الحد الأقصى للمنشورات غير المنشورة ({MAX_UNPUBLISHED_POSTS}).\nقم بنشر بعض المنشورات أولاً.")
        return
    
    # إعداد الجلسة
    target_count = min(15, MAX_UNPUBLISHED_POSTS - unpublished_count)
    context.user_data[f"session_{user_id}"] = []
    context.user_data[f"session_target_{user_id}"] = target_count
    context.user_data['state'] = UserState.ADDING_POSTS
    context.user_data['temp_channel'] = active
    
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=CallbackData.CANCEL_SESSION)]])
    msg = f"📥 أرسل المنشورات (نصوص أو صور أو فيديوهات أو مستندات)\nالحد الأقصى المسموح: {target_count} منشور"
    
    await safe_edit_markdown(query, msg, reply_markup=cancel_kb)
    await db_save_sentiment_history(user_id, 0, "add_posts_start", "positive", 0.3)

async def publish_one_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر نشر منشور واحد"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
        await safe_edit_markdown(query, "⚠️ اشتراكك منتهٍ، استخدم /trial أو /subscribe")
        return
    
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await safe_edit_markdown(query, "⚠️ اختر قناة أولاً")
        return
    
    post = await db_get_next_post(active)
    if not post:
        await safe_edit_markdown(query, get_text(user_id, 'no_posts'))
        return
    
    ch_info = await db_get_channel_info(active)
    channel_id = ch_info[0] if ch_info else None
    if not channel_id:
        await safe_edit_markdown(query, "❌ القناة غير صالحة")
        return
    
    # ترجمة المنشور إذا كانت مفعلة
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
        await db_save_sentiment_history(user_id, 0, "publish_one_success", "positive", 0.4)
        
        await safe_edit_markdown(query, "✅ تم نشر المنشور بنجاح!")
    except Exception as e:
        await db_increment_fail_count(post['id'])
        error_id = log_error(e, {'user_id': user_id, 'action': 'publish_one'})
        await db_save_sentiment_history(user_id, 0, "publish_one_fail", "negative", -0.4)
        await safe_edit_markdown(query, f"❌ فشل النشر (الرمز: `{error_id}`)")
    
    await main_menu_callback(update, context)

async def my_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر منشوراتي"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await safe_edit_markdown(query, "⚠️ اختر قناة أولاً")
        return
    
    posts = await db_get_user_posts_for_channel(active, limit=15)
    if not posts:
        await safe_edit_markdown(query, get_text(user_id, 'no_posts'))
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
    
    await safe_edit_markdown(query, msg, reply_markup=InlineKeyboardMarkup(kb_buttons))
    await db_save_sentiment_history(user_id, 0, "my_posts_view", "neutral", 0.1)

async def delete_single_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر حذف منشور فردي"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    parts = query.data.split(":")[-1].split("_")
    if len(parts) >= 2:
        post_id = int(parts[0])
        active = int(parts[1])
        
        if await db_delete_single_post(post_id, user_id, active):
            await db_save_sentiment_history(user_id, 0, "delete_post_success", "positive", 0.2)
            await safe_edit_markdown(query, "✅ تم حذف المنشور")
        else:
            await db_save_sentiment_history(user_id, 0, "delete_post_fail", "negative", -0.3)
            await safe_edit_markdown(query, "❌ فشل الحذف")
        
        await my_posts_callback(update, context)

async def confirm_clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تأكيد حذف جميع المنشورات"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    active = int(query.data.split(":")[-1])
    context.user_data['clear_all_posts_id'] = active
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم", callback_data=f"{CallbackData.POSTS_CLEAR_ALL_PREFIX}{active}"),
         InlineKeyboardButton("❌ لا", callback_data=CallbackData.BACK)]
    ])
    
    await safe_edit_markdown(query, get_text(user_id, 'confirm_delete'), reply_markup=kb)

async def clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر حذف جميع المنشورات (تأكيد)"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    active = int(query.data.split(":")[-1])
    
    async def _clear_posts(conn):
        await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (active,))
        await conn.commit()
    
    await execute_db(_clear_posts)
    await db_save_sentiment_history(user_id, 0, "clear_all_posts", "positive", 0.2)
    await safe_edit_markdown(query, get_text(user_id, 'deleted_all'))
    await main_menu_callback(update, context)

async def recycle_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إعادة تدوير المنشورات"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if active:
        await db_reset_posts_to_unpublished(active, user_id)
        await db_save_sentiment_history(user_id, 0, "recycle_posts", "positive", 0.3)
        await safe_edit_markdown(query, get_text(user_id, 'recycled'))
    else:
        await safe_edit_markdown(query, "⚠️ اختر قناة أولاً")
    
    await main_menu_callback(update, context)

# 29.4 أزرار الإحصائيات
async def pending_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إحصائيات المنشورات"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    unpublished = await db_get_user_unpublished_posts(user_id)
    total = await db_get_user_total_posts(user_id)
    text = get_text(user_id, 'pending_stats').format(unpublished, total)
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

async def full_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إحصائيات كاملة"""
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
    
    # إضافة تحليل المشاعر
    user_sentiment = learning_engine.get_user_sentiment_profile(user_id)
    text += f"\n🧠 تحليل مشاعرك: {user_sentiment.get('avg_sentiment', 0):.2f}"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]])
    await safe_edit_markdown(query, text, reply_markup=kb)

# 29.5 أزرار المجموعات
async def my_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر مجموعاتي"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except:
            pass
    
    uid = update.effective_user.id
    groups = await db_get_user_groups(uid)
    
    valid_groups = []
    for chat_id, chat_name, username, banned in groups:
        is_admin = await is_currently_admin_in_group(context.bot, chat_id, uid)
        if is_admin:
            valid_groups.append((chat_id, chat_name, username, banned))
        else:
            async def _remove_admin(conn):
                await conn.execute("DELETE FROM group_admins WHERE chat_id=? AND user_id=?", (chat_id, uid))
                await conn.commit()
            await execute_db(_remove_admin)
    
    if not valid_groups:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ أضف البوت", url=f"https://t.me/{BOT_USERNAME}?startgroup")],
            [InlineKeyboardButton("🔄 تحديث القائمة", callback_data=CallbackData.SECURITY_REFRESH_GROUPS)],
            [InlineKeyboardButton(get_text(uid, 'back'), callback_data=CallbackData.BACK)]
        ])
        msg = "📭 لا توجد مجموعات مسجلة\n\nأضف البوت إلى مجموعة وستظهر هنا."
        await safe_edit_markdown(query, msg, reply_markup=kb)
        return
    
    keyboard = []
    for chat_id, chat_name, username, banned in valid_groups:
        display_name = chat_name[:28] + "..." if len(chat_name) > 31 else chat_name
        status_icon = "⛔" if banned else "✅"
        
        # جلب تحليل المشاعر للمجموعة
        chat_sentiment = learning_engine.get_chat_sentiment_profile(chat_id)
        avg_sentiment = chat_sentiment.get('avg_sentiment', 0)
        sentiment_icon = "😊" if avg_sentiment > 0.2 else "😐" if avg_sentiment > -0.2 else "😞"
        
        keyboard.append([InlineKeyboardButton(f"{status_icon} {display_name} {sentiment_icon}", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")])
        keyboard.append([
            InlineKeyboardButton("🔐 الأمان", callback_data=f"{CallbackData.SECURITY_SELECT_GROUP}{chat_id}"),
            InlineKeyboardButton("📜 السجل", callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}"),
            InlineKeyboardButton("⚙️ متقدم", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")
        ])
        is_locked = await is_chat_locked(chat_id)
        lock_label = "🔒 قفل" if not is_locked else "🔓 فتح"
        lock_callback = f"{CallbackData.PANEL_LOCK_PREFIX}{chat_id}" if not is_locked else f"{CallbackData.PANEL_UNLOCK_PREFIX}{chat_id}"
        keyboard.append([
            InlineKeyboardButton(lock_label, callback_data=lock_callback),
            InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_group:{chat_id}")
        ])
        keyboard.append([InlineKeyboardButton("─" * 20, callback_data="noop")])
    
    keyboard.append([
        InlineKeyboardButton("🔄 تحديث القائمة", callback_data=CallbackData.SECURITY_REFRESH_GROUPS),
        InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = f"👥 **مجموعاتي**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر مجموعة للتحكم بها:\n\n✅ = نشطة  |  ⛔ = محظورة\n{sentiment_icon} = تحليل المشاعر"
    
    await safe_edit_markdown(query, text, reply_markup=reply_markup)

async def delete_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر حذف مجموعة"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, "❌ غير مصرح")
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
    await db_save_sentiment_history(uid, chat_id, "delete_group", "neutral", -0.1)
    await safe_edit_markdown(query, "✅ تم حذف المجموعة من قاعدة البيانات.")
    await my_groups_callback(update, context)

async def group_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إعدادات المجموعة"""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except:
            pass
    
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    # جلب إعدادات الأمان
    settings = await db_get_security_settings(chat_id)
    await _update_security_panel(query, chat_id, uid)

async def _update_security_panel(query, chat_id: int, user_id: int):
    """تحديث لوحة الأمان"""
    try:
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        
        # جلب تحليل المشاعر للمجموعة
        chat_sentiment = learning_engine.get_chat_sentiment_profile(chat_id)
        avg_sentiment = chat_sentiment.get('avg_sentiment', 0)
        sentiment_icon = "😊" if avg_sentiment > 0.2 else "😐" if avg_sentiment > -0.2 else "😞"
        
        text = _build_security_text(settings, avg_sentiment, sentiment_icon)
        keyboard = _build_security_keyboard(chat_id)
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        logger.info(f"✅ تم تحديث لوحة الأمان للمجموعة {chat_id}")
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            await query.answer("✅ الإعدادات محدثة", show_alert=False)
        else:
            raise
    except Exception as e:
        logger.error(f"خطأ في _update_security_panel: {e}")
        await query.answer("❌ حدث خطأ، حاول مرة أخرى", show_alert=True)

def _build_security_text(settings: dict, avg_sentiment: float = 0, sentiment_icon: str = "😐") -> str:
    """بناء نص لوحة الأمان مع تحليل المشاعر"""
    def st(val):
        return "✅" if val else "❌"
    
    text = f"""🔐 إعدادات الأمان للمجموعة
━━━━━━━━━━━━━━━━━━━━━━
🧠 تحليل المشاعر: {sentiment_icon} {avg_sentiment:.2f}
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
    """بناء أزرار لوحة الأمان مع دعم تحليل المشاعر"""
    return [
        [
            InlineKeyboardButton("🧠 تحليل المشاعر", callback_data="sentiment_analysis"),
            InlineKeyboardButton("📊 إحصائيات التعلم", callback_data="learning_stats")
        ],
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

# 29.6 أزرار الإعدادات العامة
async def settings_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر الإعدادات"""
    query = update.callback_query
    if query:
        await query.answer()
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
    
    text = f"⚙️ **الإعدادات**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإعداد المطلوب:"
    await safe_edit_markdown(query, text, reply_markup=keyboard)

async def toggle_auto_publish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تبديل النشر التلقائي"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    current = await db_auto_status(user_id)
    new_status = not current
    await db_set_auto(user_id, new_status)
    
    text = get_text(user_id, 'auto_toggled').format(get_text(user_id, 'auto_on') if new_status else get_text(user_id, 'auto_off'))
    await db_save_sentiment_history(user_id, 0, f"auto_publish_toggle_{new_status}", "positive" if new_status else "neutral", 0.2 if new_status else 0)
    await safe_edit_markdown(query, text)
    await settings_menu_callback(update, context)

async def toggle_auto_recycle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تبديل إعادة التدوير التلقائي"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    current = await db_get_auto_recycle(user_id)
    new_status = not current
    await db_set_auto_recycle(user_id, new_status)
    
    text = get_text(user_id, 'auto_toggled').format(get_text(user_id, 'auto_on') if new_status else get_text(user_id, 'auto_off'))
    await db_save_sentiment_history(user_id, 0, f"auto_recycle_toggle_{new_status}", "positive" if new_status else "neutral", 0.2 if new_status else 0)
    await safe_edit_markdown(query, text)
    await settings_menu_callback(update, context)

# 29.7 أزرار الجدولة
async def schedule_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر الجدولة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    ch_db_id = int(query.data.split(":")[-1])
    context.user_data['schedule_ch_id'] = ch_db_id
    
    schedule = await db_get_schedule(ch_db_id)
    schedule_type = schedule['type']
    schedule_info = ""
    
    if schedule_type == 'interval_minutes':
        schedule_info = get_text(user_id, 'interval_minutes').format(schedule['interval_minutes'])
    elif schedule_type == 'interval_hours':
        schedule_info = get_text(user_id, 'interval_hours').format(schedule['interval_hours'])
    elif schedule_type == 'interval_days':
        schedule_info = get_text(user_id, 'interval_days').format(schedule['interval_days'])
    elif schedule_type == 'days':
        days = parse_days_of_week_safe(schedule['days_of_week'])
        day_names = [get_text(user_id, 'sunday'), get_text(user_id, 'monday'), get_text(user_id, 'tuesday'), get_text(user_id, 'wednesday'), get_text(user_id, 'thursday'), get_text(user_id, 'friday'), get_text(user_id, 'saturday')]
        days_str = ', '.join([day_names[d] for d in days]) if days else get_text(user_id, 'nothing')
        schedule_info = get_text(user_id, 'days_week').format(days_str)
    elif schedule_type == 'dates':
        dates = parse_dates_safe(schedule['specific_dates'])
        dates_str = ', '.join(dates) if dates else get_text(user_id, 'nothing')
        schedule_info = get_text(user_id, 'specific_dates').format(dates_str)
    elif schedule_type == 'cron':
        schedule_info = f"CRON: {schedule['cron_expression']}"
    else:
        schedule_info = get_text(user_id, 'nothing')
    
    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'interval_minutes'), callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_MINUTES_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton(get_text(user_id, 'interval_hours'), callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_HOURS_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton(get_text(user_id, 'interval_days'), callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_DAYS_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton(get_text(user_id, 'days_week'), callback_data=f"{CallbackData.SCHEDULE_SET_DAYS_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton(get_text(user_id, 'specific_dates'), callback_data=f"{CallbackData.SCHEDULE_SET_DATES_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton(f"🕐 {get_text(user_id, 'send_time')}", callback_data=f"{CallbackData.SCHEDULE_SET_PUBLISH_TIME_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton("⏰ CRON", callback_data=f"schedule:set_cron:{ch_db_id}")],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ]
    
    text = get_text(user_id, 'schedule_settings').format(schedule_info)
    await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def set_interval_minutes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين الدقائق"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    
    context.user_data['state'] = UserState.WAITING_INTERVAL_MINUTES
    context.user_data['schedule_ch_id'] = ch_db_id
    await safe_edit_markdown(query, get_text(user_id, 'send_minutes'))

async def set_interval_hours_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين الساعات"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    
    context.user_data['state'] = UserState.WAITING_INTERVAL_HOURS
    context.user_data['schedule_ch_id'] = ch_db_id
    await safe_edit_markdown(query, get_text(user_id, 'send_hours'))

async def set_interval_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين الأيام"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    
    context.user_data['state'] = UserState.WAITING_INTERVAL_DAYS
    context.user_data['schedule_ch_id'] = ch_db_id
    await safe_edit_markdown(query, get_text(user_id, 'send_days'))

async def set_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين أيام الأسبوع"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    
    context.user_data['selected_days'] = []
    context.user_data['schedule_ch_id'] = ch_db_id
    context.user_data['state'] = UserState.SELECTING_DAYS
    
    keyboard = await build_days_keyboard(user_id, context)
    await safe_edit_markdown(query, get_text(user_id, 'days_week'), reply_markup=keyboard)

async def set_dates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين التواريخ"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    
    context.user_data['state'] = UserState.WAITING_DATES
    context.user_data['schedule_ch_id'] = ch_db_id
    await safe_edit_markdown(query, get_text(user_id, 'send_dates'))

async def set_publish_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين وقت النشر"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    
    context.user_data['state'] = UserState.WAITING_PUBLISH_TIME
    context.user_data['schedule_ch_id'] = ch_db_id
    await safe_edit_markdown(query, get_text(user_id, 'send_time'))

async def set_cron_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين CRON"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    
    context.user_data['state'] = UserState.WAITING_CRON
    context.user_data['schedule_ch_id'] = ch_db_id
    await safe_edit_markdown(query, "⏰ أرسل تعبير CRON (مثال: 0 12 * * 1)")

async def day_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر اختيار يوم من أيام الأسبوع"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    day_index = int(query.data.split(":")[-1])
    selected = context.user_data.get('selected_days', [])
    
    if day_index in selected:
        selected.remove(day_index)
    else:
        selected.append(day_index)
    
    context.user_data['selected_days'] = selected
    keyboard = await build_days_keyboard(user_id, context)
    await query.edit_message_reply_markup(reply_markup=keyboard)

async def save_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر حفظ أيام الأسبوع"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    ch_db_id = context.user_data.get('schedule_ch_id')
    if not ch_db_id:
        await safe_edit_markdown(query, "❌ لم يتم تحديد القناة")
        return
    
    selected = context.user_data.get('selected_days', [])
    await db_save_schedule(ch_db_id, 'days', days_of_week=json.dumps(selected))
    await db_set_next_publish_date(ch_db_id, None)
    
    context.user_data.pop('selected_days', None)
    context.user_data.pop('state', None)
    await db_save_sentiment_history(user_id, 0, "save_days_schedule", "positive", 0.2)
    await safe_edit_markdown(query, get_text(user_id, 'days_saved'))
    await schedule_menu_callback(update, context)

async def build_days_keyboard(uid, context):
    """بناء لوحة اختيار أيام الأسبوع"""
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
                row.append(InlineKeyboardButton(f"{mark}{name}", callback_data=f"{CallbackData.SCHEDULE_DAY_SELECT_PREFIX}{day_index}"))
        if row:
            kb_buttons.append(row)
    
    kb_buttons.append([
        InlineKeyboardButton("✔️ حفظ", callback_data=CallbackData.SCHEDULE_SAVE_DAYS),
        InlineKeyboardButton(get_text(uid, 'back'), callback_data=CallbackData.BACK)
    ])
    
    return InlineKeyboardMarkup(kb_buttons)

# 29.8 أزرار الأمان والكلمات المحظورة
async def security_banned_words_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر قائمة الكلمات المحظورة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['banned_words_chat_id'] = chat_id
    await safe_edit_markdown(
        query,
        "🚫 **الكلمات المحظورة**\nاختر الإجراء المطلوب:",
        reply_markup=get_group_banned_words_keyboard(chat_id)
    )

async def banned_words_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إضافة كلمة محظورة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_GROUP_BANNED_WORD
    context.user_data['banned_words_chat_id'] = chat_id
    await safe_edit_markdown(query, "✏️ أرسل الكلمة التي تريد إضافتها إلى قائمة المحظورات:")

async def banned_words_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر عرض الكلمات المحظورة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    words = await db_get_banned_words(chat_id)
    if not words:
        await safe_edit_markdown(query, "📭 لا توجد كلمات محظورة.")
        return
    
    text = "🚫 **الكلمات المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for word, added_by, added_at in words:
        text += f"• `{word}` (أضيف بواسطة {added_by})\n"
    
    # إضافة تحليل المشاعر
    text += f"\n🧠 عدد الكلمات المحظورة: {len(words)}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}{chat_id}")]
    ])
    await safe_edit_markdown(query, text, reply_markup=keyboard)

async def banned_words_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر حذف كلمة محظورة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_REMOVE_GROUP_BANNED_WORD
    context.user_data['banned_words_chat_id'] = chat_id
    await safe_edit_markdown(query, "✏️ أرسل الكلمة التي تريد حذفها من قائمة المحظورات:")

async def security_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إغلاق لوحة الأمان"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.delete()

# 29.9 أزرار العقوبات
async def penalty_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر قائمة العقوبات"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    context.user_data['penalty_chat_id'] = chat_id
    await safe_edit_markdown(query, "⚖️ **اختر العقوبة التلقائية**", reply_markup=penalty_keyboard(chat_id))

async def penalty_kick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين عقوبة الطرد"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    await db_set_security_settings(chat_id, auto_penalty='kick')
    await db_save_sentiment_history(user_id, chat_id, "set_penalty_kick", "neutral", 0)
    await safe_edit_markdown(query, "✅ تم تعيين عقوبة الطرد")
    await penalty_menu_callback(update, context)

async def penalty_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين عقوبة الحظر"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    await db_set_security_settings(chat_id, auto_penalty='ban')
    await db_save_sentiment_history(user_id, chat_id, "set_penalty_ban", "neutral", -0.1)
    await safe_edit_markdown(query, "✅ تم تعيين عقوبة الحظر")
    await penalty_menu_callback(update, context)

async def penalty_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين عقوبة الكتم"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    await db_set_security_settings(chat_id, auto_penalty='mute')
    await db_save_sentiment_history(user_id, chat_id, "set_penalty_mute", "neutral", -0.1)
    await safe_edit_markdown(query, "✅ تم تعيين عقوبة الكتم")
    await penalty_menu_callback(update, context)

async def penalty_warn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين عقوبة التحذير"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    await db_set_security_settings(chat_id, auto_penalty='warn')
    await db_save_sentiment_history(user_id, chat_id, "set_penalty_warn", "neutral", 0)
    await safe_edit_markdown(query, "✅ تم تعيين عقوبة التحذير")
    await penalty_menu_callback(update, context)

async def penalty_restrict_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين عقوبة التقييد"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    await db_set_security_settings(chat_id, auto_penalty='restrict')
    await db_save_sentiment_history(user_id, chat_id, "set_penalty_restrict", "neutral", -0.05)
    await safe_edit_markdown(query, "✅ تم تعيين عقوبة التقييد")
    await penalty_menu_callback(update, context)

async def penalty_none_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إلغاء العقوبة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    await db_set_security_settings(chat_id, auto_penalty='none')
    await db_save_sentiment_history(user_id, chat_id, "set_penalty_none", "positive", 0.1)
    await safe_edit_markdown(query, "✅ تم إلغاء العقوبة")
    await penalty_menu_callback(update, context)

# 29.10 أزرار مدة الكتم
async def mute_duration_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر قائمة مدة الكتم"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    await safe_edit_markdown(query, "🔇 **اختر مدة الكتم**", reply_markup=mute_duration_keyboard(chat_id))

async def penalty_mute_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تعيين مدة الكتم"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    
    parts = query.data.split(":")
    if len(parts) < 2:
        await safe_edit_markdown(query, "❌ بيانات غير صالحة")
        return
    
    duration_str = parts[0].split("_")[-1] if "_" in parts[0] else parts[1]
    
    if duration_str == "permanent":
        duration = -1
        duration_text = "دائم"
    else:
        try:
            duration = int(duration_str)
            if duration < 60:
                duration_text = f"{duration} دقيقة"
            elif duration < 1440:
                duration_text = f"{duration // 60} ساعة"
            else:
                duration_text = f"{duration // 1440} يوم"
        except ValueError:
            await safe_edit_markdown(query, "❌ مدة غير صالحة")
            return
    
    try:
        chat_id = int(parts[-1])
    except (ValueError, IndexError):
        await safe_edit_markdown(query, "❌ معرف المجموعة غير صالح")
        return
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await safe_edit_markdown(query, get_text(user_id, 'admin_only'))
        return
    
    await db_set_security_settings(chat_id, auto_penalty='mute', auto_mute_duration=duration if duration > 0 else 60)
    await db_save_sentiment_history(user_id, chat_id, f"set_mute_duration_{duration}", "neutral", 0)
    await safe_edit_markdown(query, f"✅ تم تعيين مدة الكتم إلى: {duration_text}")
    await penalty_menu_callback(update, context)

# 29.11 أزرار الإجراءات المتقدمة
async def advanced_actions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر الإجراءات المتقدمة"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    context.user_data['advanced_chat_id'] = chat_id
    msg = "🛠️ **الإجراءات المتقدمة للمجموعة**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإجراء المطلوب:"
    await safe_edit_markdown(query, msg, reply_markup=get_advanced_group_actions_keyboard(chat_id))

async def group_action_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر حظر مستخدم"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_BAN_USER
    context.user_data['advanced_chat_id'] = chat_id
    msg = "🚫 **حظر مستخدم**\n\nأرسل معرف المستخدم (user_id) أو قم بالرد على رسالة المستخدم ثم أرسل /ban\n\nيمكنك إضافة سبب بعد المعرف: `/ban 123456789 السبب`"
    await safe_edit_markdown(query, msg)

async def group_action_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر كتم مستخدم"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    msg = "🔇 **كتم مستخدم**\n\nاختر مدة الكتم:"
    await safe_edit_markdown(query, msg, reply_markup=get_advanced_mute_duration_keyboard(chat_id))

async def advanced_mute_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر اختيار مدة الكتم المتقدمة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    parts = query.data.split(":")
    if len(parts) == 3:
        minutes = int(parts[1])
        chat_id = int(parts[2])
        uid = update.effective_user.id
        
        if not await is_authorized_in_group(context.bot, chat_id, uid):
            await safe_edit_markdown(query, get_text(uid, 'admin_only'))
            return
        
        context.user_data['mute_minutes'] = minutes
        context.user_data['state'] = UserState.WAITING_MUTE_USER
        context.user_data['advanced_chat_id'] = chat_id
        
        if minutes == 0:
            msg = "🔇 **كتم دائم**\n\nأرسل معرف المستخدم (user_id) أو قم بالرد على رسالة المستخدم ثم أرسل /mute\n\nيمكنك إضافة سبب: `/mute 123456789 السبب`"
        elif minutes < 60:
            msg = f"🔇 **كتم {minutes} دقيقة**\n\nأرسل معرف المستخدم (user_id) أو قم بالرد على رسالة المستخدم ثم أرسل /mute\n\nيمكنك إضافة سبب: `/mute 123456789 السبب`"
        elif minutes < 1440:
            msg = f"🔇 **كتم {minutes // 60} ساعة**\n\nأرسل معرف المستخدم (user_id) أو قم بالرد على رسالة المستخدم ثم أرسل /mute\n\nيمكنك إضافة سبب: `/mute 123456789 السبب`"
        else:
            msg = f"🔇 **كتم {minutes // 1440} يوم**\n\nأرسل معرف المستخدم (user_id) أو قم بالرد على رسالة المستخدم ثم أرسل /mute\n\nيمكنك إضافة سبب: `/mute 123456789 السبب`"
        
        await safe_edit_markdown(query, msg)

async def group_action_warn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تحذير مستخدم"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_WARN_USER
    context.user_data['advanced_chat_id'] = chat_id
    msg = "⚠️ **تحذير مستخدم**\n\nأرسل معرف المستخدم (user_id) أو قم بالرد على رسالة المستخدم ثم أرسل /warn\n\nيمكنك إضافة سبب: `/warn 123456789 السبب`"
    await safe_edit_markdown(query, msg)

async def group_action_kick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر طرد مستخدم"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_KICK_USER
    context.user_data['advanced_chat_id'] = chat_id
    msg = "👢 **طرد مستخدم**\n\nأرسل معرف المستخدم (user_id) أو قم بالرد على رسالة المستخدم ثم أرسل /kick\n\nيمكنك إضافة سبب: `/kick 123456789 السبب`"
    await safe_edit_markdown(query, msg)

async def group_action_restrict_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تقييد مستخدم"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_RESTRICT_USER
    context.user_data['advanced_chat_id'] = chat_id
    msg = "🔒 **تقييد مستخدم**\n\nأرسل معرف المستخدم (user_id) أو قم بالرد على رسالة المستخدم ثم أرسل /restrict\n\nيمكنك إضافة سبب: `/restrict 123456789 السبب`"
    await safe_edit_markdown(query, msg)

async def group_action_pin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تثبيت رسالة"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_PIN_MESSAGE
    context.user_data['advanced_chat_id'] = chat_id
    msg = "📌 **تثبيت رسالة**\n\nقم بالرد على الرسالة التي تريد تثبيتها ثم أرسل /pin"
    await safe_edit_markdown(query, msg)

async def group_action_log_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر عرض سجل الإجراءات"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    log_text = await get_moderation_log(chat_id, limit=20)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.ADVANCED_ACTIONS}:{chat_id}")]])
    await safe_edit_markdown(query, log_text, reply_markup=keyboard)

async def group_action_unban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إلغاء حظر مستخدم"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    context.user_data['state'] = UserState.WAITING_UNBAN_USER
    context.user_data['advanced_chat_id'] = chat_id
    msg = "🔓 **إلغاء حظر مستخدم**\n\nأرسل معرف المستخدم (user_id):\nمثال: `/unban 123456789`"
    await safe_edit_markdown(query, msg)

# 29.12 أزرار لوحة التحكم (قفل/فتح)
async def panel_lock_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر قفل المجموعة"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    await db_set_chat_lock(chat_id, True, uid)
    await db_save_sentiment_history(uid, chat_id, "chat_locked_panel", "neutral", -0.1)
    await safe_edit_markdown(query, get_text(uid, 'locked'))
    await my_groups_callback(update, context)

async def panel_unlock_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر فتح المجموعة"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await safe_edit_markdown(query, get_text(uid, 'admin_only'))
        return
    
    await db_set_chat_lock(chat_id, False)
    await db_save_sentiment_history(uid, chat_id, "chat_unlocked_panel", "positive", 0.2)
    await safe_edit_markdown(query, get_text(uid, 'unlocked'))
    await my_groups_callback(update, context)

async def panel_close_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إغلاق لوحة التحكم"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.delete()
# ===================================================================
# 30. دوال المجموعات المتطورة (مع تحليل المشاعر والتعلم الذكي)
# ===================================================================

# 30.1 معالج الرسائل في المجموعات - فلتر متطور مع تحليل المشاعر
async def filter_messages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج متطور لفلترة رسائل المجموعات مع تحليل المشاعر والتعلم الذكي"""
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

    # ===== تحليل المشاعر للرسالة =====
    sentiment_result = learning_engine.analyze_sentiment(text) if text else {'sentiment': 'neutral', 'score': 0, 'confidence': 0.5}
    await db_save_sentiment_history(user_id, chat_id, text[:500] if text else "media_message", sentiment_result['sentiment'], sentiment_result['score'])

    # ===== التعلم من الرسالة =====
    await learning_engine.learn_from_message(user_id, chat_id, text[:200] if text else "media", None, True)

    # ===== التحقق من قفل المجموعة =====
    if await is_chat_locked(chat_id) and not await is_authorized_in_group(context.bot, chat_id, user_id):
        try:
            await message.delete()
            await context.bot.send_message(chat_id, "🔒 المجموعة مقفلة، لا يمكنك إرسال رسائل.")
        except:
            pass
        return

    # ===== التحقق من الوضع البطيء =====
    if not await db_check_slow_mode(chat_id, user_id):
        try:
            await message.delete()
            await context.bot.send_message(chat_id, "⏱️ الوضع البطيء مفعل، انتظر قبل إرسال رسالة أخرى.")
        except:
            pass
        return

    # ===== جلب إعدادات الأمان =====
    settings = await db_get_security_settings(chat_id)

    # ===== التحقق من الروابط =====
    if settings.get('links', False) and text and contains_link(text):
        await delete_and_penalize(update, context, "🚫 ممنوع إرسال الروابط!")
        # تسجيل التعلم
        await db_save_learning_pattern("link_violation", "negative", -0.3, 0.8)
        return

    # ===== التحقق من المعرفات =====
    if settings.get('mentions', False) and text and contains_mention(text):
        await delete_and_penalize(update, context, "🚫 ممنوع إرسال المعرفات (@username)!")
        await db_save_learning_pattern("mention_violation", "negative", -0.3, 0.8)
        return

    # ===== التحقق من الكلمات المحظورة =====
    if settings.get('delete_banned_words', False) and text:
        word = await db_contains_banned_word(text, chat_id)
        if word:
            await delete_and_penalize(update, context, f"🚫 كلمة محظورة: `{word}`")
            await db_save_learning_pattern(f"banned_word_{word}", "negative", -0.5, 0.9)
            return

    # ===== حذف أنواع الميديا حسب الإعدادات =====
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
            await context.bot.send_message(chat_id, f"🚫 ممنوع إرسال {media_type}!")
        except:
            pass
        penalty = settings.get('delete_penalty', settings.get('auto_penalty', 'none'))
        if penalty != 'none':
            duration = settings.get('delete_penalty_duration', settings.get('auto_mute_duration', 60))
            # ضبط المدة بناءً على المشاعر
            if sentiment_result['sentiment'] == 'negative' and sentiment_result['score'] < -0.5:
                duration = duration * 2
            await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, duration, f"إرسال {media_type} ممنوع")
        await db_save_learning_pattern(f"media_{media_type}_violation", "negative", -0.3, 0.8)
        return

    # ===== التحقق من طول الرسالة =====
    max_len = settings.get('max_message_length', 0)
    if max_len > 0 and text and len(text) > max_len:
        try:
            await message.delete()
            await context.bot.send_message(chat_id, f"📏 الرسالة طويلة جداً! الحد الأقصى {max_len} حرف.")
        except:
            pass
        await db_save_learning_pattern("max_length_violation", "negative", -0.2, 0.7)
        return

    # ===== التحقق من الفيضان =====
    if settings.get('antiflood_enabled', False) and await db_check_antiflood(chat_id, user_id):
        try:
            await message.delete()
            await context.bot.send_message(chat_id, "🌊 تم اكتشاف فيضان! يرجى التهدئة.")
        except:
            pass
        penalty = settings.get('antiflood_penalty', 'mute')
        # عقوبة أشد للمستخدمين السلبيين
        if sentiment_result['sentiment'] == 'negative' and sentiment_result['score'] < -0.5:
            penalty_duration = 120
        else:
            penalty_duration = 60
        await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, penalty_duration, "فيضان في الرسائل")
        await db_save_learning_pattern("flood_violation", "negative", -0.4, 0.85)
        return

    # ===== التحقق من الوضع الليلي =====
    if settings.get('night_mode_enabled', False):
        now = utc_now()
        try:
            start = datetime.strptime(settings['night_mode_start'], '%H:%M').time()
            end = datetime.strptime(settings['night_mode_end'], '%H:%M').time()
            current = now.time()
            is_night = False
            if start < end:
                is_night = start <= current <= end
            else:
                is_night = current >= start or current <= end
            if is_night:
                penalty = settings.get('night_mode_action', 'mute')
                if penalty != 'none':
                    await apply_penalty_with_duration(context.bot, chat_id, user_id, penalty, 60, "الوضع الليلي مفعل")
                    try:
                        await message.delete()
                        await context.bot.send_message(chat_id, "🌙 الوضع الليلي مفعل، يرجى الانتظار حتى الصباح.")
                    except:
                        pass
                    await db_save_learning_pattern("night_mode_violation", "negative", -0.2, 0.7)
                    return
        except:
            pass

    # ===== تحديث نقاط المستخدم =====
    if not user_id == context.bot.id:
        await add_points(user_id, update, context)

    # ===== الردود التلقائية (المدمجة + المتعلمة) =====
    if text:
        auto_reply_settings = await db_get_auto_reply_settings(chat_id)
        if auto_reply_settings.get('enabled', False):
            # التحقق من صلاحية المستخدم (مشرفين فقط أو الكل)
            if not (auto_reply_settings.get('only_admins', False) and not await is_authorized_in_group(context.bot, chat_id, user_id)):
                # تجاهل البوتات
                if not (auto_reply_settings.get('ignore_bots', True) and update.effective_user.is_bot):
                    # البحث عن رد مخصص في قاعدة البيانات
                    reply = await db_get_reply(f"{chat_id}:{text.lower()}")
                    if not reply:
                        reply = await db_get_reply(text.lower())
                    
                    # البحث في الردود المدمجة (200+ رد)
                    if not reply:
                        import re
                        for key, value in ALL_REPLIES.items():
                            if re.search(r'\b' + re.escape(key) + r'\b', text, re.IGNORECASE):
                                reply = value if isinstance(value, str) else random.choice(value) if isinstance(value, list) else value
                                break
                    
                    # البحث في الردود المتعلمة
                    if not reply:
                        learned_reply = await db_get_learned_response(text[:50])
                        if learned_reply:
                            reply = learned_reply
                    
                    # البحث عن رد ذكي بناءً على المشاعر
                    if not reply and LEARNING_ENABLED:
                        smart_reply = learning_engine.suggest_response(text, user_id, chat_id)
                        if smart_reply:
                            reply = smart_reply
                            # تسجيل التعلم
                            await db_save_response_learning(f"{text[:50]}_{reply[:50]}", True)
                    
                    if reply:
                        try:
                            await message.reply_text(reply)
                            # التعلم من نجاح الرد
                            await learning_engine.learn_from_message(user_id, chat_id, text, reply, True)
                            await db_save_sentiment_history(user_id, chat_id, f"auto_reply_sent", "positive", 0.2)
                        except Exception as e:
                            logger.error(f"فشل إرسال الرد التلقائي: {e}")
                            await db_save_response_learning(f"{text[:50]}_{reply[:50]}", False)

    # ===== تحليل اتجاه المشاعر للمجموعة وتحديث الملف الشخصي =====
    if random.random() < 0.05:  # تحديث دوري بنسبة 5%
        chat_sentiment = learning_engine.get_chat_sentiment_profile(chat_id)
        await db_update_chat_sentiment_profile(
            chat_id,
            chat_sentiment.get('avg_sentiment', 0),
            chat_sentiment.get('stability', 1),
            chat_sentiment.get('trend', 'stable')
        )

# 30.2 معالج الرسائل الخاصة - متطور مع تحليل المشاعر
async def message_handler_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل الخاصة المتطور مع تحليل المشاعر والتعلم"""
    if update.message is None or update.effective_user is None:
        return

    user_id = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""
    state = context.user_data.get('state')

    # تحليل المشاعر للرسالة
    if text:
        sentiment = learning_engine.analyze_sentiment(text)
        await db_save_sentiment_history(user_id, 0, text[:200], sentiment['sentiment'], sentiment['score'])
        await learning_engine.learn_from_message(user_id, 0, text[:200], None, True)

    # ===== حالة إضافة قناة =====
    if state == UserState.WAITING_CHANNEL_ID:
        channel_id = text.strip()
        if not (channel_id.startswith('@') or channel_id.lstrip('-').isdigit()):
            await safe_send_markdown(context.bot, user_id, "❌ صيغة المعرف غير صحيحة! استخدم @username أو المعرف الرقمي.")
            return

        try:
            chat = await context.bot.get_chat(channel_id)
            channel_name = chat.title or "بدون اسم"

            # التحقق من صلاحية البوت في القناة
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status not in ['administrator', 'creator']:
                    await safe_send_markdown(context.bot, user_id, f"❌ **البوت ليس مشرفاً في القناة `{channel_name}`!**\n\nيرجى إضافة البوت كمشرف في القناة ثم المحاولة مرة أخرى.")
                    context.user_data.pop('state', None)
                    return
                if not bot_member.can_post_messages:
                    await safe_send_markdown(context.bot, user_id, f"❌ **البوت لا يملك صلاحية النشر في القناة `{channel_name}`!**\n\nيرجى منح البوت صلاحية 'نشر الرسائل' في القناة.")
                    context.user_data.pop('state', None)
                    return
            except Exception as e:
                await safe_send_markdown(context.bot, user_id, f"❌ **لا يمكن الوصول إلى القناة:** {str(e)[:100]}\n\nتأكد من أن المعرف صحيح وأن القناة عامة أو البوت عضو فيها.")
                context.user_data.pop('state', None)
                return

            result = await db_add_channel(user_id, channel_id, channel_name)
            if result:
                await safe_send_markdown(context.bot, user_id, get_text(user_id, 'channel_added').format(channel_name))
                await db_register_channel(chat.id, channel_name, user_id)
                await db_save_sentiment_history(user_id, 0, f"channel_added_{channel_name}", "positive", 0.3)
                await my_channels_callback(update, context)
            else:
                await safe_send_markdown(context.bot, user_id, get_text(user_id, 'channel_exists'))

        except Exception as e:
            await safe_send_markdown(context.bot, user_id, f"❌ خطأ: {str(e)[:100]}\nتأكد من صحة المعرف.")

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
                await db_save_sentiment_history(user_id, 0, f"posts_added_{len(session_posts)}", "positive", 0.4)
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
                await db_save_sentiment_history(user_id, 0, f"posts_added_{len(session_posts)}", "positive", 0.4)
                await safe_send_markdown(context.bot, user_id, f"✅ تم حفظ {len(session_posts)} منشور!")
            else:
                await safe_send_markdown(context.bot, user_id, "⚠️ لم يتم تحديد قناة نشطة.")
            context.user_data.pop(f"session_{user_id}", None)
            context.user_data.pop(f"session_target_{user_id}", None)
            context.user_data.pop('state', None)
            await main_menu_callback(update, context)
        return

    # ===== حالات أخرى (فترات زمنية، إلخ) =====
    elif state == UserState.WAITING_INTERVAL_MINUTES:
        try:
            minutes = int(text)
            if minutes < 1 or minutes > 1440:
                await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال عدد بين 1 و 1440 دقيقة.")
                return
            ch_id = context.user_data.get('schedule_ch_id')
            if context.user_data.get('admin_interval'):
                await db_set_publish_interval_seconds(minutes * 60, user_id, True)
                await db_save_sentiment_history(user_id, 0, f"set_global_interval_{minutes}", "positive", 0.2)
                await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين وقت النشر العام إلى {minutes} دقيقة.")
                context.user_data.pop('admin_interval', None)
            else:
                if ch_id:
                    await db_save_schedule(ch_id, 'interval_minutes', interval_minutes=minutes)
                    await db_set_next_publish_date(ch_id, None)
                    await db_save_sentiment_history(user_id, 0, f"set_interval_minutes_{minutes}", "positive", 0.2)
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
                await db_save_sentiment_history(user_id, 0, f"set_interval_hours_{hours}", "positive", 0.2)
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
                await db_save_sentiment_history(user_id, 0, f"set_interval_days_{days}", "positive", 0.2)
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
                await db_save_sentiment_history(user_id, 0, f"set_dates_{len(valid_dates)}", "positive", 0.2)
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
                await db_save_sentiment_history(user_id, 0, f"set_publish_time_{text}", "positive", 0.2)
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
                await db_save_sentiment_history(user_id, 0, f"set_cron_{cron_expr[:20]}", "positive", 0.2)
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
                await db_save_sentiment_history(user_id, chat_id, f"set_max_length_{max_len}", "neutral", 0)
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
                await db_save_sentiment_history(user_id, chat_id, f"set_warn_count_{count}", "neutral", 0)
                await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين عدد التحذيرات إلى {count}.")
                await security_warn_settings_callback(update, context)
            else:
                await safe_send_markdown(context.bot, user_id, "❌ لم يتم تحديد المجموعة.")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال رقم صحيح.")
        context.user_data.pop('state', None)
        context.user_data.pop('security_chat_id', None)
        return

    # ===== حالات إدارة المشرفين =====
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
                    await db_save_sentiment_history(user_id, 0, f"add_bot_admin_{target_id}", "positive", 0.3)
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
                    await db_save_sentiment_history(user_id, 0, f"remove_bot_admin_{target_id}", "neutral", 0)
                    await safe_send_markdown(context.bot, user_id, f"✅ تم إزالة المستخدم `{target_id}` من المشرفين.")
                else:
                    await safe_send_markdown(context.bot, user_id, f"❌ فشل إزالة المشرف.")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ معرف غير صالح.")
        context.user_data.pop('state', None)
        await admin_panel_callback(update, context)
        return

    # ===== حالة البث (Broadcast) =====
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

    # ===== حالة إرسال تحديث =====
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
            await db_save_sentiment_history(user_id, 0, "send_update", "positive", 0.3)
            await safe_send_markdown(context.bot, user_id, f"✅ تم نشر التحديث في قناة @{channel}")
        except Exception as e:
            await safe_send_markdown(context.bot, user_id, f"❌ فشل النشر: {str(e)[:100]}")
        context.user_data.pop('state', None)
        await admin_updates_callback(update, context)
        return

    # ===== حالة تعيين قناة التحديثات =====
    elif state == UserState.WAITING_UPDATE_CHANNEL:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        channel = text.strip()
        if channel.startswith('@'):
            channel = channel[1:]
        if await db_set_updates_channel(channel):
            await db_save_sentiment_history(user_id, 0, f"set_updates_channel_{channel}", "positive", 0.2)
            await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين قناة التحديثات: @{channel}")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ فشل تعيين القناة.")
        context.user_data.pop('state', None)
        await admin_updates_callback(update, context)
        return

    # ===== حالة تعيين قناة الاشتراك الإجباري =====
    elif state == UserState.WAITING_FORCE_CHANNEL:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        channel = text.strip()
        if channel.startswith('@'):
            channel = channel[1:]
        await db_set_force_subscribe_channel(channel)
        await db_save_sentiment_history(user_id, 0, f"set_force_channel_{channel}", "positive", 0.2)
        await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين قناة الاشتراك الإجباري: @{channel}")
        context.user_data.pop('state', None)
        await admin_force_subscribe_callback(update, context)
        return

    # ===== حالة تعيين مستخدم /sendcode =====
    elif state == UserState.WAITING_SENDCODE_USER:
        if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        try:
            target_id = int(text.strip())
            await db_set_allowed_sendcode_user(target_id)
            await db_save_sentiment_history(user_id, 0, f"set_sendcode_user_{target_id}", "positive", 0.2)
            await safe_send_markdown(context.bot, user_id, f"✅ تم منح صلاحية /sendcode للمستخدم `{target_id}`")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ معرف غير صالح.")
        context.user_data.pop('state', None)
        await admin_panel_callback(update, context)
        return

    # ===== حالة تعيين قناة التقارير =====
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
            await db_save_sentiment_history(user_id, 0, f"set_log_channel_{chat.id}", "positive", 0.3)
            await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين قناة التقارير: {chat.title}")
        except Exception as e:
            await safe_send_markdown(context.bot, user_id, f"❌ فشل تعيين القناة: {str(e)[:100]}")
        context.user_data.pop('state', None)
        context.user_data.pop('temp_log_channel_identifier', None)
        await admin_panel_callback(update, context)
        return

    # ===== حالة إضافة كلمة محظورة للمجموعة =====
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
            await db_save_sentiment_history(user_id, chat_id, f"add_banned_word_{word}", "neutral", 0)
            await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة كلمة `{word}` إلى الكلمات المحظورة.")
        else:
            await safe_send_markdown(context.bot, user_id, f"⚠️ الكلمة `{word}` موجودة بالفعل.")
        context.user_data.pop('state', None)
        await security_banned_words_menu_callback(update, context)
        return

    # ===== حالة حذف كلمة محظورة من المجموعة =====
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
        await db_save_sentiment_history(user_id, chat_id, f"remove_banned_word_{word}", "neutral", 0)
        await safe_send_markdown(context.bot, user_id, f"✅ تم حذف كلمة `{word}` من الكلمات المحظورة.")
        context.user_data.pop('state', None)
        await security_banned_words_menu_callback(update, context)
        return

    # ===== حالة إضافة كلمة محظورة عامة =====
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
            await db_save_sentiment_history(user_id, 0, f"add_global_banned_word_{word}", "neutral", 0)
            await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة كلمة `{word}` إلى الكلمات المحظورة العامة.")
        else:
            await safe_send_markdown(context.bot, user_id, f"⚠️ الكلمة `{word}` موجودة بالفعل.")
        context.user_data.pop('state', None)
        await admin_banned_words_callback(update, context)
        return

    # ===== حالة حذف كلمة محظورة عامة =====
    elif state == UserState.WAITING_REMOVE_GLOBAL_BANNED_WORD:
        if not await is_bot_admin(user_id):
            await safe_send_markdown(context.bot, user_id, "🔒 غير مصرح")
            context.user_data.pop('state', None)
            return
        word = text.lower().strip()
        await db_remove_banned_word(word, -1)
        await db_save_sentiment_history(user_id, 0, f"remove_global_banned_word_{word}", "neutral", 0)
        await safe_send_markdown(context.bot, user_id, f"✅ تم حذف كلمة `{word}` من الكلمات المحظورة العامة.")
        context.user_data.pop('state', None)
        await admin_banned_words_callback(update, context)
        return

    # ===== حالة إضافة رد مخصص =====
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
                await db_save_sentiment_history(user_id, 0, f"delete_reply_{keyword}", "neutral", 0)
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
        await db_save_sentiment_history(user_id, 0, f"add_reply_{keyword}", "positive", 0.2)
        await safe_send_markdown(context.bot, user_id, f"✅ تم إضافة رد للكلمة `{keyword}`")
        context.user_data.pop('reply_keyword', None)
        context.user_data.pop('state', None)
        await admin_replies_callback(update, context)
        return

    # ===== حالة تعيين عدد أيام التذكير =====
    elif state == UserState.WAITING_REMINDER_DAYS:
        try:
            days = int(text)
            if days < 1 or days > 10:
                await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال عدد بين 1 و 10 أيام.")
                return
            await db_update_reminder_settings(user_id, reminder_days_before=days)
            await db_save_sentiment_history(user_id, 0, f"set_reminder_days_{days}", "positive", 0.2)
            await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين التذكير قبل {days} أيام من انتهاء الاشتراك.")
            context.user_data.pop('state', None)
            await reminder_menu_callback(update, context)
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال رقم صحيح.")
        return

    # ===== حالة جدولة منشور =====
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
                await db_save_sentiment_history(user_id, 0, f"schedule_post_{date_str}_{time_str}", "positive", 0.3)
                await safe_send_markdown(context.bot, user_id, f"✅ تم جدولة المنشور! 📅 {date_str} 🕐 {time_str} (بتوقيت مكة)")
                context.user_data.pop('state', None)
                await main_menu_callback(update, context)
            except ValueError:
                await safe_send_markdown(context.bot, user_id, "❌ صيغة التاريخ/الوقت غير صحيحة! استخدم YYYY-MM-DD HH:MM")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ الصيغة غير صحيحة! استخدم: YYYY-MM-DD HH:MM نص المنشور")
        return

    # ===== حالات الإجراءات الإشرافية (ban, mute, warn, kick, restrict, unban) =====
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
            # تسجيل التعلم
            await db_save_learning_pattern(f"moderation_{action}_{reason[:20] if reason else 'default'}", "negative", -0.2, 0.7)
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ معرف المستخدم غير صالح.")
        context.user_data.pop('state', None)
        context.user_data.pop('mute_minutes', None)
        return

    # ===== حالة تثبيت رسالة =====
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
            await db_save_sentiment_history(user_id, chat_id, "pin_message", "positive", 0.2)
            await safe_send_markdown(context.bot, user_id, msg)
        else:
            await safe_send_markdown(context.bot, user_id, "❌ قم بالرد على الرسالة التي تريد تثبيتها.")
        context.user_data.pop('state', None)
        return

    # ===== حالات إنشاء مسابقة =====
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
                await db_save_sentiment_history(user_id, 0, f"create_contest_{contest_id}", "positive", 0.5)
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

    # ===== حالة المشاركة في مسابقة (إجابة) =====
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
            await db_save_sentiment_history(user_id, 0, f"contest_join_{contest_id}", "positive", 0.3)
            await safe_send_markdown(context.bot, user_id, "✅ تم تسجيل مشاركتك في المسابقة بنجاح!")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ أنت مشترك بالفعل في هذه المسابقة!")
        context.user_data.pop('contest_join_id', None)
        context.user_data.pop('state', None)
        await contests_command_handler(update, context)
        return

    # ===== حالة تعيين نسبة NSFW =====
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
            await db_save_sentiment_history(user_id, 0, f"set_nsfw_threshold_{threshold}", "neutral", 0)
            await safe_send_markdown(context.bot, user_id, f"✅ تم تعيين نسبة الحساسية إلى {threshold}%")
        except ValueError:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال رقم صحيح.")
        context.user_data.pop('state', None)
        await nsfw_settings_callback(update, context)
        return

    # ===== وضع الدعم =====
    elif context.user_data.get('support_mode'):
        if text:
            ticket_num = await db_get_next_ticket_number() + 1
            async def _update_ticket_num(conn):
                await conn.execute("UPDATE settings SET value=? WHERE key='last_ticket_number'", (str(ticket_num),))
                await conn.commit()
            await execute_db(_update_ticket_num)
            username = update.effective_user.username or "بدون يوزر"
            await db_save_ticket(user_id, username, text, ticket_num)
            await db_save_sentiment_history(user_id, 0, f"support_ticket_{ticket_num}", "neutral", 0.1)
            await safe_send_markdown(context.bot, user_id, f"✅ تم إرسال تذكرتك رقم #{ticket_num}\nسيتم الرد عليك بأسرع وقت.")
            context.user_data.pop('support_mode', None)
            await security_audit.log("SUPPORT_TICKET_CREATED", user_id, {"ticket": ticket_num}, "INFO")
        else:
            await safe_send_markdown(context.bot, user_id, "❌ الرجاء إدخال نص الرسالة.")
        return

    # ===== رسائل عادية =====
    else:
        if update.message.text:
            reply = await db_get_reply(text.lower())
            if reply:
                try:
                    await update.message.reply_text(reply)
                    await db_save_sentiment_history(user_id, 0, f"custom_reply_{text[:20]}", "neutral", 0.1)
                except:
                    pass
            else:
                # ردود ذكية للمستخدمين
                if LEARNING_ENABLED and random.random() < 0.3:
                    smart_reply = learning_engine.suggest_response(text, user_id, 0)
                    if smart_reply:
                        try:
                            await update.message.reply_text(smart_reply)
                        except:
                            pass
        await main_menu_callback(update, context)

# ===================================================================
# 31. دوال المساعد (Helper Functions) المتطورة
# ===================================================================

# 31.1 دوال الاشتراك الإجباري
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

# 31.2 دوال النقاط والمستويات
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
            await db_save_sentiment_history(user_id, 0, f"level_up_{new_levels[-1]}", "positive", 0.8)
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

# 31.3 دوال كشف المالك وإشعار المشرفين
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

async def notify_group_admins(bot, chat_id: int, user_id: int, chat_name: str):
    try:
        admins = await bot.get_chat_administrators(chat_id)
        if not admins:
            await safe_send_markdown(bot, user_id, get_text(user_id, 'no_admins_found'))
            return
        for admin in admins:
            try:
                await bot.send_message(
                    chat_id=admin.user.id,
                    text=get_text(admin.user.id, 'activation_notification').format(user_id, chat_name, chat_id),
                    parse_mode="MarkdownV2"
                )
            except:
                pass
            await asyncio.sleep(0.3)
    except Exception as e:
        logger.error(f"فشل إشعار مشرفي المجموعة {chat_id}: {e}")

# 31.4 دوال خادم الويب
async def setup_unified_web_server(application, port: int):
    from aiohttp import web
    from telegram import Update
    import json

    if not hasattr(application, 'web_app') or application.web_app is None:
        application.web_app = web.Application()

    async def health_check(request):
        return web.Response(text="OK")

    async def index_handler(request):
        html = """
        <html>
            <head><title>ريلاكس مانيجر</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px; direction: rtl;">
                <h1>🌿 ريلاكس مانيجر</h1>
                <p>✅ البوت يعمل بكفاءة</p>
                <p>🧠 نظام التعلم الذكي مفعل</p>
                <p>📊 <a href="/health">التحقق من الصحة</a></p>
                <p>🤖 <a href="https://t.me/Reelaaaxbot">البوت على تيليجرام</a></p>
                <p style="color: #666; font-size: 12px;">الإصدار 22.0.0 - الذكي المتطور</p>
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

# ===================================================================
# 32. المهام الخلفية (Background Tasks) المتطورة
# ===================================================================

# 32.1 حلقة النشر التلقائي المتطورة
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
                    await db_save_sentiment_history(user_id, ch_db_id, "auto_recycle", "neutral", 0.1)
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
                        await db_save_sentiment_history(user_id, ch_db_id, "auto_recycle_no_posts", "neutral", 0.1)
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
                # تحليل المشاعر للناجح
                await db_save_sentiment_history(user_id, ch_db_id, f"auto_publish_success_{post['id']}", "positive", 0.4)
            else:
                await db_increment_fail_count(post['id'])
                logger.error(f"فشل دائم في نشر المنشور {post['id']} في القناة {ch_tele_id}")
                await db_save_sentiment_history(user_id, ch_db_id, f"auto_publish_fail_{post['id']}", "negative", -0.4)
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

# 32.2 حلقة النسخ الاحتياطي التلقائي
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

# 32.3 حلقة المنشورات المجدولة
async def run_scheduled_posts_loop_improved(bot):
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
                    await db_save_sentiment_history(chat_id, 0, f"scheduled_post_sent_{post_id}", "positive", 0.3)
                except Exception as e:
                    new_fail = fail_count + 1
                    await db_update_scheduled_post_fail(post_id, new_fail)
                    if new_fail >= 5:
                        await db_delete_scheduled_post(post_id)
                        logger.warning(f"🗑️ تم حذف المنشور المجدول {post_id} بعد 5 محاولات فاشلة")
        except:
            pass

# 32.4 حلقة التذكيرات الذكية
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
                    await db_save_sentiment_history(user_id, 0, f"reminder_sent_{days_left}_days", "neutral", 0.1)
                except:
                    pass
                user_language[user_id] = original_lang
        except:
            pass

# 32.5 حلقة التنظيف
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
            # تنظيف سجل المشاعر القديم
            async def _cleanup_sentiment(conn):
                cutoff = (utc_now() - timedelta(days=90)).isoformat()
                await conn.execute("DELETE FROM sentiment_history WHERE created_at < ?", (cutoff,))
                await conn.commit()
            await execute_db(_cleanup_sentiment)
            # تنظيف سجل الأمان القديم
            async def _cleanup_security(conn):
                cutoff = (utc_now() - timedelta(days=60)).isoformat()
                await conn.execute("DELETE FROM security_events WHERE created_at < ? AND severity != 'high'", (cutoff,))
                await conn.commit()
            await execute_db(_cleanup_security)
        except:
            pass

# 32.6 حلقة إحصائيات البث
async def broadcast_stats_periodically():
    while True:
        await asyncio.sleep(60)
        try:
            total, banned, posts, groups, channels = await db_stats()
            # جلب إحصائيات التعلم
            learning_stats = await db_get_learning_stats()
            logger.info(f"📊 إحصائيات: مستخدمين={total}, محظورين={banned}, منشورات={posts}, مجموعات={groups}, قنوات={channels}, أنماط تعلم={learning_stats.get('patterns',0)}")
            # إرسال للمطور إذا كان هناك زيادة كبيرة
            if hasattr(broadcast_stats_periodically, 'last_total'):
                if total - broadcast_stats_periodically.last_total > 50:
                    logger.info(f"📈 زيادة كبيرة في عدد المستخدمين: +{total - broadcast_stats_periodically.last_total}")
            broadcast_stats_periodically.last_total = total
        except:
            pass

# 32.7 حلقة إغلاق المسابقات التلقائي
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
                        await db_save_sentiment_history(winner_id, 0, f"contest_won_{contest_id}", "positive", 0.9)
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

# 32.8 حلقة مراقبة الذاكرة
async def memory_monitor():
    while True:
        try:
            ram = get_ram_usage()
            if ram['percent'] > 80:
                await memory_optimizer()
                logger.warning(f"⚠️ استخدام الذاكرة مرتفع: {ram['percent']}%")
            await asyncio.sleep(60)
        except:
            await asyncio.sleep(60)

# 32.9 حلقة تحديث صلاحيات المجموعة
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
                    # تحديث ملف تعريف المشاعر للمجموعة
                    chat_sentiment = learning_engine.get_chat_sentiment_profile(chat_id)
                    await db_update_chat_sentiment_profile(
                        chat_id,
                        chat_sentiment.get('avg_sentiment', 0),
                        chat_sentiment.get('stability', 1),
                        chat_sentiment.get('trend', 'stable')
                    )
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"فشل تحديث صلاحيات المجموعة {chat_id}: {e}")
            logger.info(f"✅ تم تحديث صلاحيات {len(groups)} مجموعة")
        except Exception as e:
            logger.error(f"خطأ في حلقة تحديث الصلاحيات: {e}")
        await asyncio.sleep(3600)

# 32.10 حلقة التحقق من الاتصال
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

# 32.11 حلقة تنظيف نقاط المستخدمين
async def cleanup_points_cache():
    while True:
        await asyncio.sleep(3600)
        user_points_last_hour.clear()

# 32.12 حلقة تحسين الذاكرة
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
        _failed_attempts_cache.clear()
        if len(_flood_cache) > 5000:
            keys = list(_flood_cache.keys())[:1000]
            for key in keys:
                _flood_cache.pop(key, None)
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

# 32.13 دوال النسخ الاحتياطي
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
        async def _get_new_learning(conn):
            cur = await conn.execute("SELECT * FROM learning_patterns WHERE last_used > ? LIMIT 500", (last_time.isoformat(),))
            return await cur.fetchall()
        new_learning = await execute_db(_get_new_learning)
        if new_learning:
            backup_data['learning'] = [dict(pat) for pat in new_learning]
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
            if 'learning' in data:
                for pat in data['learning']:
                    await conn.execute(
                        "INSERT OR IGNORE INTO learning_patterns (id, pattern, sentiment, score, frequency, last_used, confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (pat['id'], pat['pattern'], pat['sentiment'], pat['score'], pat['frequency'], pat['last_used'], pat['confidence'])
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
# 33. معالج الأخطاء العالمي المتطور
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
# ===================================================================
# 36. المفقودات - إضافات كاملة (توضع فوق دالة)
# ===================================================================

# ===================================================================
# 36.1 متغيرات NSFW والمتغيرات العامة المفقودة
# ===================================================================

NSFW_ENABLED = get_env_or_default("NSFW_ENABLED", False, bool)
NSFW_THRESHOLD = get_env_or_default("NSFW_THRESHOLD", 0.7, float)
NSFW_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 ميجابايت
NSFW_MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50 ميجابايت
CLOUD_BACKUP_ENABLED = get_env_or_default("CLOUD_BACKUP_ENABLED", False, bool)
start_time = time_module.time()

# ===================================================================
# 36.2 نظام Security Audit
# ===================================================================

class SecurityAudit:
    """نظام تدقيق أمني متطور"""
    
    def __init__(self):
        self.events = []
        self._lock = asyncio.Lock()
    
    async def log(self, event: str, user_id: int, details: dict = None, severity: str = "INFO"):
        """تسجيل حدث أمني مع تحليل المشاعر"""
        try:
            log_msg = f"[{severity}] {event} - User: {user_id}"
            if details:
                safe_details = {k: v for k, v in details.items() if k not in ['token', 'password', 'key', 'secret']}
                log_msg += f" - {json.dumps(safe_details, default=str)[:300]}"
            
            # تسجيل في السجل
            advanced_logger.log_security(event, user_id, details, severity)
            
            # تسجيل في قاعدة البيانات
            await log_security_event(
                event_type=event,
                chat_id=details.get('chat_id') if details else None,
                user_id=user_id,
                details=details,
                severity=severity.lower()
            )
            
            # تحليل المشاعر للحدث
            sentiment = learning_engine.analyze_sentiment(f"{event}_{str(details)[:100]}")
            await db_save_sentiment_history(user_id, 0, f"security_{event}", sentiment['sentiment'], sentiment['score'])
            
            # التعلم من الحدث الأمني
            if severity.upper() in ["HIGH", "CRITICAL"]:
                await db_save_learning_pattern(
                    f"security_{event}",
                    "negative",
                    -0.5,
                    0.9
                )
            
            # إرسال تنبيه للمطور إذا كان الحدث عالياً
            if severity.upper() in ["HIGH", "CRITICAL"] and PRIMARY_OWNER_ID:
                try:
                    from telegram import Bot
                    bot = Bot(token=TOKEN)
                    alert_text = f"🚨 **تنبيه أمني!**\n\n"
                    alert_text += f"📌 الحدث: `{event}`\n"
                    alert_text += f"👤 المستخدم: `{user_id}`\n"
                    alert_text += f"⚠️ الخطورة: `{severity}`\n"
                    if details:
                        alert_text += f"📝 التفاصيل: `{json.dumps(details, default=str)[:200]}`\n"
                    await bot.send_message(chat_id=PRIMARY_OWNER_ID, text=alert_text, parse_mode="MarkdownV2")
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"خطأ في نظام التدقيق الأمني: {e}")

security_audit = SecurityAudit()

# ===================================================================
# 36.3 دوال التذاكر (Support Tickets) المفقودة
# ===================================================================

async def db_get_all_tickets(limit: int = 20):
    """الحصول على جميع التذاكر"""
    async def _get(conn):
        cur = await conn.execute(
            "SELECT id, user_id, username, message, ticket_number, status, created_at FROM support_tickets ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        return await cur.fetchall()
    return await execute_db(_get)

async def db_delete_all_tickets():
    """حذف جميع التذاكر"""
    async def _delete(conn):
        await conn.execute("DELETE FROM support_tickets")
        await conn.commit()
    return await execute_db(_delete)

# ===================================================================
# 36.4 دوال الإحالات (Referrals) المفقودة
# ===================================================================

async def db_get_referral_settings():
    """الحصول على إعدادات الإحالات"""
    async def _get(conn):
        cur = await conn.execute("SELECT key, value FROM referral_settings")
        rows = await cur.fetchall()
        return {row[0]: row[1] for row in rows}
    return await execute_db(_get)

async def db_claim_referral_reward(user_id: int) -> int:
    """صرف مكافآت الإحالات"""
    async def _claim(conn):
        cur = await conn.execute(
            "SELECT total_reward_days, claimed_reward_days FROM referral_rewards WHERE user_id=?",
            (user_id,)
        )
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
        await conn.execute(
            "UPDATE users SET subscription_end=? WHERE user_id=?",
            (end_date, user_id)
        )
        await conn.execute(
            "UPDATE referral_rewards SET claimed_reward_days = claimed_reward_days + ? WHERE user_id=?",
            (available, user_id)
        )
        await conn.commit()
        return available
    return await execute_db(_claim)

# ===================================================================
# 36.5 دوال التذكيرات (Reminders) المفقودة
# ===================================================================

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

async def db_update_last_reminder_sent(user_id: int, reminder_type: str):
    """تحديث وقت آخر تذكير تم إرساله"""
    async def _update(conn):
        now_timestamp = int(time_module.time())
        await conn.execute(
            "UPDATE user_reminder_settings SET last_reminder_sent=? WHERE user_id=?",
            (now_timestamp, user_id)
        )
        await conn.commit()
    return await execute_db(_update)

# ===================================================================
# 36.6 دوال الترجمة (Translation) المفقودة
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
        await conn.execute(
            "INSERT OR REPLACE INTO user_translation (user_id, lang) VALUES (?, ?)",
            (user_id, lang)
        )
        await conn.commit()
    await execute_db(_set)

async def translate_text(text: str, target_lang: str) -> str:
    """ترجمة نص إلى اللغة المستهدفة"""
    if not text or target_lang == 'off' or target_lang == 'ar':
        return text
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='auto', target=target_lang)
        translated = translator.translate(text)
        if translated:
            return translated
    except Exception as e:
        logger.error(f"فشل الترجمة: {e}")
        # استخدام ترجمة ذكية بديلة
        try:
            from deep_translator import MyMemoryTranslator
            translator = MyMemoryTranslator(source='auto', target=target_lang)
            translated = translator.translate(text)
            if translated:
                return translated
        except:
            pass
    return text

# ===================================================================
# 36.7 دوال الأمان المتقدمة - المفقودة
# ===================================================================

async def security_toggle_setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل إعداد أمان معين في المجموعة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    parts = query.data.split(":")
    
    if len(parts) < 3:
        await query.edit_message_text("❌ بيانات غير صالحة")
        return
    
    action = parts[1]
    try:
        chat_id = int(parts[2])
    except ValueError:
        await query.edit_message_text("❌ معرف المجموعة غير صالح")
        return
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    settings = await db_get_security_settings(chat_id, force_refresh=True)
    
    # تبديل الإعداد المطلوب
    if action == "links":
        settings['links'] = 1 if settings.get('links', 0) == 0 else 0
        await db_set_security_settings(chat_id, links=settings['links'])
    elif action == "mentions":
        settings['mentions'] = 1 if settings.get('mentions', 0) == 0 else 0
        await db_set_security_settings(chat_id, mentions=settings['mentions'])
    elif action == "slow_mode":
        settings['slow_mode'] = 1 if settings.get('slow_mode', 0) == 0 else 0
        await db_set_security_settings(chat_id, slow_mode=settings['slow_mode'])
    elif action == "delete_videos":
        settings['delete_videos'] = 1 if settings.get('delete_videos', 0) == 0 else 0
        await db_set_security_settings(chat_id, delete_videos=settings['delete_videos'])
    elif action == "delete_service":
        settings['delete_service'] = 1 if settings.get('delete_service', 0) == 0 else 0
        await db_set_security_settings(chat_id, delete_service=settings['delete_service'])
    elif action == "delete_documents":
        settings['delete_documents'] = 1 if settings.get('delete_documents', 0) == 0 else 0
        await db_set_security_settings(chat_id, delete_documents=settings['delete_documents'])
    elif action == "delete_stickers":
        settings['delete_stickers'] = 1 if settings.get('delete_stickers', 0) == 0 else 0
        await db_set_security_settings(chat_id, delete_stickers=settings['delete_stickers'])
    elif action == "delete_audio":
        settings['delete_audio'] = 1 if settings.get('delete_audio', 0) == 0 else 0
        await db_set_security_settings(chat_id, delete_audio=settings['delete_audio'])
    elif action == "delete_animation":
        settings['delete_animation'] = 1 if settings.get('delete_animation', 0) == 0 else 0
        await db_set_security_settings(chat_id, delete_animation=settings['delete_animation'])
    elif action == "delete_forwarded":
        settings['delete_forwarded'] = 1 if settings.get('delete_forwarded', 0) == 0 else 0
        await db_set_security_settings(chat_id, delete_forwarded=settings['delete_forwarded'])
    elif action == "delete_polls":
        settings['delete_polls'] = 1 if settings.get('delete_polls', 0) == 0 else 0
        await db_set_security_settings(chat_id, delete_polls=settings['delete_polls'])
    elif action == "delete_games":
        settings['delete_games'] = 1 if settings.get('delete_games', 0) == 0 else 0
        await db_set_security_settings(chat_id, delete_games=settings['delete_games'])
    elif action == "delete_voice":
        settings['delete_voice'] = 1 if settings.get('delete_voice', 0) == 0 else 0
        await db_set_security_settings(chat_id, delete_voice=settings['delete_voice'])
    elif action == "delete_video_note":
        settings['delete_video_note'] = 1 if settings.get('delete_video_note', 0) == 0 else 0
        await db_set_security_settings(chat_id, delete_video_note=settings['delete_video_note'])
    elif action == "welcome_enabled":
        settings['welcome_enabled'] = 1 if settings.get('welcome_enabled', 0) == 0 else 0
        await db_set_security_settings(chat_id, welcome_enabled=settings['welcome_enabled'])
    elif action == "goodbye_enabled":
        settings['goodbye_enabled'] = 1 if settings.get('goodbye_enabled', 0) == 0 else 0
        await db_set_security_settings(chat_id, goodbye_enabled=settings['goodbye_enabled'])
    elif action == "antiflood":
        settings['antiflood_enabled'] = 1 if settings.get('antiflood_enabled', 0) == 0 else 0
        await db_set_security_settings(chat_id, antiflood_enabled=settings['antiflood_enabled'])
    elif action == "night_mode":
        settings['night_mode_enabled'] = 1 if settings.get('night_mode_enabled', 0) == 0 else 0
        await db_set_security_settings(chat_id, night_mode_enabled=settings['night_mode_enabled'])
    elif action == "max_length":
        context.user_data['state'] = UserState.WAITING_MAX_LENGTH
        context.user_data['security_chat_id'] = chat_id
        await query.edit_message_text("📏 أرسل الحد الأقصى لطول الرسالة (0 = غير محدود):")
        return
    elif action == "warn_settings":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔢 عدد التحذيرات", callback_data=f"warn_count:{chat_id}"),
             InlineKeyboardButton("⚖️ عقوبة التحذير", callback_data=f"warn_penalty:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
        ])
        await query.edit_message_text("⚠️ **إعدادات التحذير**\nاختر الإعداد المطلوب:", reply_markup=keyboard)
        return
    else:
        await query.edit_message_text("❌ إجراء غير معروف")
        return
    
    # تحديث اللوحة
    await _update_security_panel(query, chat_id, user_id)
    await db_save_sentiment_history(user_id, chat_id, f"security_toggle_{action}", "neutral", 0)

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
        
        # جلب تحليل المشاعر للمجموعة
        chat_sentiment = learning_engine.get_chat_sentiment_profile(chat_id)
        avg_sentiment = chat_sentiment.get('avg_sentiment', 0)
        sentiment_icon = "😊" if avg_sentiment > 0.2 else "😐" if avg_sentiment > -0.2 else "😞"
        
        keyboard.append([
            InlineKeyboardButton(f"{status_icon} {display_name} {sentiment_icon}", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")
        ])
    
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
# 36.8 دوال الاشتراك الإجباري - المفقودة
# ===================================================================

async def check_subscribe_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج زر التحقق من الاشتراك الإجباري"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    enabled = await db_get_force_subscribe_status()
    channel = await db_get_force_subscribe_channel()
    
    if not enabled or not channel:
        await query.edit_message_text("✅ لا توجد قناة اشتراك إجباري")
        return
    
    try:
        member = await context.bot.get_chat_member(f"@{channel}", user_id)
        if member.status in ['member', 'administrator', 'creator']:
            await query.edit_message_text("✅ **تم التحقق من اشتراكك!**\nيمكنك الآن استخدام البوت.")
            await db_save_sentiment_history(user_id, 0, "force_subscribe_verified", "positive", 0.4)
            await main_menu_callback(update, context)
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{channel}"),
                 InlineKeyboardButton("🔄 تأكد من الاشتراك", callback_data=CallbackData.CHECK_SUBSCRIBE)],
                [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
            ])
            await query.edit_message_text(f"❌ **لم تشترك بعد!**\n\nيرجى الاشتراك في القناة:\n👉 @{channel}\nثم اضغط على زر التحقق مرة أخرى.", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"خطأ في التحقق من الاشتراك: {e}")
        await query.edit_message_text(f"❌ **حدث خطأ أثناء التحقق.**\nيرجى المحاولة مرة أخرى.")

# ===================================================================
# 36.9 دوال NSFW - المفقودة
# ===================================================================

async def nsfw_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إعدادات NSFW"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    status = "🟢 مفعل" if NSFW_ENABLED else "🔴 معطل"
    threshold = NSFW_THRESHOLD * 100
    
    text = f"🔞 **إعدادات NSFW**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📌 الحالة: {status}\n"
    text += f"📊 نسبة الحساسية: {threshold}%\n"
    text += f"📁 الحد الأقصى للصور: {NSFW_MAX_FILE_SIZE // (1024*1024)} ميجابايت\n"
    text += f"📁 الحد الأقصى للفيديوهات: {NSFW_MAX_VIDEO_SIZE // (1024*1024)} ميجابايت\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'🔄 تعطيل' if NSFW_ENABLED else '✅ تفعيل'}", callback_data=CallbackData.NSFW_TOGGLE)],
        [InlineKeyboardButton("⚙️ تغيير النسبة", callback_data=CallbackData.NSFW_THRESHOLD_SET)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    if query:
        await query.edit_message_text(text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def nsfw_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل تفعيل NSFW"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    global NSFW_ENABLED
    NSFW_ENABLED = not NSFW_ENABLED
    os.environ["NSFW_ENABLED"] = str(NSFW_ENABLED)
    
    await db_save_sentiment_history(user_id, 0, f"nsfw_toggle_{NSFW_ENABLED}", "neutral", 0)
    await query.answer(f"✅ تم {'تفعيل' if NSFW_ENABLED else 'تعطيل'} NSFW")
    await nsfw_settings_callback(update, context)

async def nsfw_threshold_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين نسبة حساسية NSFW"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_NSFW_THRESHOLD
    await query.edit_message_text("⚙️ **تغيير نسبة حساسية NSFW**\n\nأرسل النسبة المطلوبة (0-100):\nمثال: 70")

# ===================================================================
# 36.10 دوال الردود التلقائية - المفقودة
# ===================================================================

async def admin_auto_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة المجموعات لإعدادات الردود التلقائية"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    groups = await db_get_user_groups(user_id)
    if not groups:
        await query.edit_message_text("📭 لا توجد مجموعات مسجلة.")
        return
    
    keyboard = []
    for chat_id, chat_name, username, banned in groups:
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            continue
        display_name = chat_name[:28] + "..." if len(chat_name) > 31 else chat_name
        keyboard.append([InlineKeyboardButton(f"📝 {display_name}", callback_data=f"{CallbackData.AUTO_REPLY_MENU_PREFIX}{chat_id}")])
    
    if not keyboard:
        await query.edit_message_text("🔒 لا تملك صلاحية على أي مجموعة.")
        return
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    await query.edit_message_text("📝 **اختر مجموعة لإعدادات الردود التلقائية:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def auto_reply_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة إدارة الردود التلقائية"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    
    settings = await db_get_auto_reply_settings(chat_id)
    replies = await db_get_replies_count(chat_id)
    
    text = f"📝 **إدارة الردود التلقائية**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📌 الحالة: {'🟢 مفعلة' if settings['enabled'] else '🔴 معطلة'}\n"
    text += f"👥 المستخدمون: {'👑 مشرفين فقط' if settings['only_admins'] else '👥 الجميع'}\n"
    text += f"📋 عدد الردود: {replies}\n"
    
    keyboard = [
        [
            InlineKeyboardButton(f"{'🟢 تفعيل' if not settings['enabled'] else '🔴 تعطيل'}", callback_data=f"{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}{chat_id}"),
            InlineKeyboardButton(f"{'👑 مشرفين' if settings['only_admins'] else '👥 الجميع'}", callback_data=f"{CallbackData.AUTO_REPLY_ADMINS_PREFIX}{chat_id}")
        ],
        [
            InlineKeyboardButton("➕ إضافة رد", callback_data=f"{CallbackData.ADMIN_ADD_REPLY}:{chat_id}"),
            InlineKeyboardButton("🗑️ حذف رد", callback_data=f"{CallbackData.ADMIN_DEL_REPLY}:{chat_id}")
        ],
        [
            InlineKeyboardButton("📋 عرض الكل", callback_data=f"{CallbackData.ADMIN_LIST_REPLIES}:{chat_id}"),
            InlineKeyboardButton("🔄 إعادة تعيين", callback_data=f"{CallbackData.AUTO_REPLY_RESET_PREFIX}{chat_id}")
        ],
        [
            InlineKeyboardButton("📊 إحصائيات", callback_data=f"{CallbackData.AUTO_REPLY_STATS_PREFIX}{chat_id}"),
            InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")
        ]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def auto_reply_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل حالة الردود التلقائية"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    
    new_status = await db_toggle_auto_reply(chat_id)
    await db_save_sentiment_history(user_id, chat_id, f"auto_reply_toggle_{new_status}", "neutral", 0)
    await query.answer(f"✅ تم {'تفعيل' if new_status else 'تعطيل'} الردود التلقائية")
    await auto_reply_menu_callback(update, context)

async def auto_reply_admins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل إعداد المشرفين فقط / الجميع"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    
    settings = await db_get_auto_reply_settings(chat_id)
    new_status = not settings['only_admins']
    await db_set_auto_reply_only_admins(chat_id, new_status)
    await db_save_sentiment_history(user_id, chat_id, f"auto_reply_admins_{new_status}", "neutral", 0)
    await query.answer(f"✅ تم {'تفعيل' if new_status else 'تعطيل'} الردود للمشرفين فقط")
    await auto_reply_menu_callback(update, context)

async def auto_reply_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب تأكيد إعادة تعيين جميع الردود التلقائية"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، إعادة تعيين", callback_data=f"{CallbackData.AUTO_REPLY_CONFIRM_RESET_PREFIX}{chat_id}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data=f"{CallbackData.AUTO_REPLY_CANCEL_PREFIX}{chat_id}")]
    ])
    
    await query.edit_message_text(
        "⚠️ **تأكيد إعادة تعيين الردود**\n\nسيتم حذف جميع الردود المخصصة لهذه المجموعة!",
        reply_markup=keyboard
    )

async def auto_reply_confirm_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد إعادة تعيين جميع الردود التلقائية"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    
    async def _reset_replies(conn):
        await conn.execute("DELETE FROM group_replies WHERE chat_id=?", (chat_id,))
        await conn.commit()
    await execute_db(_reset_replies)
    
    await db_save_sentiment_history(user_id, chat_id, "auto_reply_reset", "neutral", 0)
    await query.edit_message_text("✅ **تم حذف جميع الردود التلقائية** بنجاح")
    await auto_reply_menu_callback(update, context)

async def auto_reply_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء إعادة التعيين والعودة للقائمة"""
    query = update.callback_query
    await query.answer()
    await auto_reply_menu_callback(update, context)

async def auto_reply_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات الردود التلقائية"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer(get_text(user_id, 'admin_only'), show_alert=True)
        return
    
    replies = await db_get_replies(chat_id)
    settings = await db_get_auto_reply_settings(chat_id)
    
    text = "📊 **إحصائيات الردود التلقائية**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📝 عدد الردود: {len(replies)}\n"
    text += f"📌 الحالة: {'🟢 مفعلة' if settings['enabled'] else '🔴 معطلة'}\n"
    text += f"👥 المستهدف: {'👑 مشرفين فقط' if settings['only_admins'] else '👥 الجميع'}\n"
    
    if replies:
        keywords = [r['keyword'] for r in replies[:10]]
        text += f"\n📋 الكلمات المفتاحية:\n"
        for kw in keywords[:10]:
            text += f"• `{kw}`\n"
        if len(replies) > 10:
            text += f"... و{len(replies)-10} أخرى"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.AUTO_REPLY_MENU_PREFIX}{chat_id}")]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard)

async def db_get_replies_count(chat_id: int) -> int:
    """جلب عدد الردود التلقائية لمجموعة"""
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM auto_replies WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_get_replies(chat_id: int) -> List[Dict]:
    """جلب جميع الردود التلقائية لمجموعة"""
    async def _get(conn):
        cur = await conn.execute("SELECT keyword, reply, created_at FROM auto_replies WHERE chat_id=? ORDER BY keyword", (chat_id,))
        rows = await cur.fetchall()
        return [{'keyword': row[0], 'reply': row[1], 'created_at': row[2]} for row in rows]
    return await execute_db(_get)

# ===================================================================
# 36.11 دوال إدارة الردود المخصصة - المفقودة
# ===================================================================

async def admin_replies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة إدارة الردود"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    await query.edit_message_text("💬 **إدارة الردود**\nاختر الإجراء المطلوب:", reply_markup=get_replies_keyboard())

async def admin_add_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء إضافة رد مخصص"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_KEYWORD
    await query.edit_message_text("📝 أرسل الكلمة المفتاحية (مثال: مرحبا):")

async def admin_list_replies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع الردود المخصصة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    replies = await db_get_all_replies()
    if not replies:
        await query.edit_message_text("📭 لا توجد ردود.")
        return
    
    text = "💬 **قائمة الردود**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for keyword, reply in replies:
        text += f"• `{keyword}` → {reply[:50]}...\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_REPLIES)]
    ])
    await query.edit_message_text(text, reply_markup=keyboard)

async def admin_del_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف رد مخصص"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['admin_del_reply'] = True
    context.user_data['state'] = UserState.WAITING_REPLY
    await query.edit_message_text("🗑️ أرسل الكلمة المفتاحية التي تريد حذف ردها:")

# ===================================================================
# 36.12 دوال الكلمات المحظورة للأدمن - المفقودة
# ===================================================================

async def admin_banned_words_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة إدارة الكلمات المحظورة العامة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    await query.edit_message_text("🚫 **الكلمات المحظورة العامة**\nاختر الإجراء المطلوب:", reply_markup=get_banned_words_admin_keyboard())

async def admin_add_banned_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة كلمة محظورة عامة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_GLOBAL_BANNED_WORD
    await query.edit_message_text("✏️ أرسل الكلمة التي تريد إضافتها إلى قائمة المحظورات العامة:")

async def admin_list_banned_words_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الكلمات المحظورة العامة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    words = await db_get_banned_words(-1)
    if not words:
        await query.edit_message_text("📭 لا توجد كلمات محظورة عامة.")
        return
    
    text = "🚫 **الكلمات المحظورة العامة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for word, added_by, added_at in words:
        text += f"• `{word}` (أضيف بواسطة {added_by})\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_BANNED_WORDS)]
    ])
    await query.edit_message_text(text, reply_markup=keyboard)

async def admin_remove_banned_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف كلمة محظورة عامة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_REMOVE_GLOBAL_BANNED_WORD
    await query.edit_message_text("✏️ أرسل الكلمة التي تريد حذفها من قائمة المحظورات العامة:")

# ===================================================================
# 36.13 دوال المسابقات للأدمن - المفقودة
# ===================================================================

async def admin_create_contest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء مسابقة جديدة (للوحة الأدمن)"""
    await create_contest_command_handler(update, context)

async def admin_declare_winner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعلان فائز في مسابقة (للوحة الأدمن)"""
    await declare_winner_command_handler(update, context)

async def admin_del_contest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف مسابقة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    contest_id = int(query.data.split(":")[-1])
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    success = await db_delete_contest(contest_id, user_id)
    if success:
        await db_save_sentiment_history(user_id, 0, f"delete_contest_{contest_id}", "neutral", 0)
        await query.edit_message_text("✅ تم حذف المسابقة.")
    else:
        await query.edit_message_text("❌ فشل حذف المسابقة.")
    await admin_panel_callback(update, context)

# ===================================================================
# 36.14 دوال معالجة الأحداث الإضافية - المفقودة
# ===================================================================

async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأعضاء الجدد في المجموعة"""
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
                logger.info(f"🗑️ تم حذف رسالة دخول العضو {member.id} في المجموعة {chat_id}")
            except Exception as e:
                logger.error(f"❌ فشل حذف رسالة دخول العضو {member.id}: {e}")
        if settings.get('welcome_enabled', False):
            welcome_text = settings.get('welcome_text', "مرحباً {user} في {chat} 🤍")
            welcome_text = format_welcome_message(welcome_text, member.full_name or member.first_name or str(member.id), chat.title)
            try:
                await context.bot.send_message(chat_id, welcome_text)
                await db_save_sentiment_history(member.id, chat_id, "welcome_message", "positive", 0.3)
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
    if settings.get('goodbye_enabled', False):
        goodbye_text = settings.get('goodbye_text', "وداعاً {user} 👋")
        goodbye_text = goodbye_text.replace('{user}', left_member.full_name or left_member.first_name or str(left_member.id))
        goodbye_text = goodbye_text.replace('{chat}', chat.title)
        try:
            await context.bot.send_message(chat_id, goodbye_text)
            await db_save_sentiment_history(left_member.id, chat_id, "goodbye_message", "neutral", -0.1)
        except Exception as e:
            logger.error(f"❌ فشل إرسال رسالة وداع للعضو {left_member.id}: {e}")
    if left_member.id != context.bot.id:
        async def _clean_user_data(conn):
            await conn.execute("DELETE FROM user_warnings WHERE user_id=? AND chat_id=?", (left_member.id, chat_id))
            await conn.execute("DELETE FROM user_messages WHERE user_id=? AND chat_id=?", (left_member.id, chat_id))
            await conn.commit()
        await execute_db(_clean_user_data)

async def chat_join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج طلبات الانضمام إلى المجموعة"""
    join_request = update.chat_join_request
    if not join_request:
        return
    user = join_request.from_user
    chat = join_request.chat
    chat_id = chat.id
    user_id = user.id
    
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if not bot_member.can_invite_users:
            logger.warning(f"⚠️ البوت ليس لديه صلاحية دعوة المستخدمين في المجموعة {chat_id}")
            return
    except:
        return
    
    settings = await db_get_security_settings(chat_id)
    try:
        await join_request.approve()
        logger.info(f"✅ تم قبول طلب انضمام المستخدم {user_id} إلى المجموعة {chat_id}")
        await db_save_sentiment_history(user_id, chat_id, "chat_join_request_approved", "positive", 0.2)
        if settings.get('welcome_enabled', False):
            welcome_text = settings.get('welcome_text', "مرحباً {user} في {chat} 🤍")
            welcome_text = format_welcome_message(welcome_text, user.full_name or user.first_name or str(user_id), chat.title)
            try:
                await context.bot.send_message(chat_id, welcome_text)
            except:
                pass
    except Exception as e:
        logger.error(f"❌ فشل قبول طلب انضمام المستخدم {user_id} في المجموعة {chat_id}: {e}")

async def on_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج إضافة البوت إلى مجموعة"""
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
                invalidate_auth_cache(chat.id, added_by_id)
                logger.info(f"🔒 تم تسجيل المضيف {added_by_id} كمالك مخفي للمجموعة {chat.id}")
            else:
                logger.info(f"ℹ️ المضيف {added_by_id} ليس مشرفاً في {chat.id}، لن يتم تسجيله كمالك مخفي.")
            await db_sync_group_admins(chat.id, context.bot)
            owner_info = await detect_owner_type(context.bot, chat.id)
            if owner_info.get('user_id') and owner_info['user_id'] != added_by_id:
                await db_register_hidden_owner_group(chat.id, owner_info['user_id'])
                invalidate_auth_cache(chat.id, owner_info['user_id'])
                logger.info(f"👑 تم تسجيل المالك الحقيقي {owner_info['user_id']} أيضاً كمالك مخفي للمجموعة {chat.id}")
            await send_addition_report_to_all_admins(context.bot, chat, inviter, chat_type_name)
            try:
                if is_admin:
                    msg = "✅ **تم تفعيل البوت في المجموعة**\n🔒 **تم تسجيلك كمالك مخفي تلقائياً**\n\n📌 استخدم /panel للوحة التحكم\n📌 استخدم /security لإعدادات الأمان"
                else:
                    msg = "✅ **تم إضافة البوت إلى المجموعة!**\n📌 استخدم /help لمعرفة الأوامر المتاحة.\n📌 إذا كنت مشرفاً، استخدم `/register_hidden_owner` لتسجيل نفسك."
                await safe_send_markdown(context.bot, chat.id, msg)
            except:
                pass
            break

async def track_chat_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج تتبع تغييرات عضوية البوت"""
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
                try:
                    await context.bot.send_message(
                        chat_id=adder.id,
                        text=f"✅ **تم إضافة البوت إلى القناة**\n\n📌 الاسم: {chat.title}\n🆔 المعرف: {chat.id}",
                        parse_mode="MarkdownV2"
                    )
                except:
                    pass
            elif chat.type in ['group', 'supergroup']:
                await send_addition_report_to_all_admins(context.bot, chat, adder, "مجموعة" if chat.type == 'group' else "سوبر جروب")
                await db_register_group(chat.id, chat.title or "بدون اسم", adder.id, chat.username)
                await db_register_hidden_owner_group(chat.id, adder.id)
                invalidate_auth_cache(chat.id, adder.id)
                await db_sync_group_admins(chat.id, context.bot, adder.id)
                owner_info = await detect_owner_type(context.bot, chat.id)
                if owner_info.get('user_id') and owner_info['user_id'] != adder.id:
                    await db_register_hidden_owner_group(chat.id, owner_info['user_id'])
                    invalidate_auth_cache(chat.id, owner_info['user_id'])
            else:
                return

async def pre_checkout_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج طلبات الدفع"""
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
    await db_save_sentiment_history(user_id, 0, f"payment_success_{days}_days", "positive", 0.9)
    await safe_send_markdown(context.bot, user_id, f"✅ **تم تفعيل اشتراكك لمدة {days} يوماً!**\nشكراً لدعمك ❤️")

async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج حذف رسائل الخدمة"""
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

# ===================================================================
# 36.15 دوال إضافية - المفقودة
# ===================================================================

async def handle_text_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الكولباك النصية"""
    query = update.callback_query
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

async def developer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات المطور"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    text = "👨‍💻 **المطور**\n\nريلاكس مانيجر\nالإصدار 22.0.0 - الذكي المتطور\n\n📌 المطور: @RelaxMgr\n📌 القناة: @RelaxMgrr\n🧠 نظام التعلم الذكي مفعل\n📊 تحليل المشاعر مفعل"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def updates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض التحديثات"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    channel = await db_get_updates_channel()
    if channel:
        text = get_text(user_id, 'updates_text')
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 القناة", url=f"https://t.me/{channel}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        if query:
            await safe_edit_markdown(query, text, reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
    else:
        text = "📢 لا توجد قناة تحديثات محددة."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        if query:
            await safe_edit_markdown(query, text, reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

# ===================================================================
# 36.16 دوال النسخ الاحتياطي المتقدمة - المفقودة
# ===================================================================

async def confirm_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد استعادة النسخة الاحتياطية"""
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
        await db_save_sentiment_history(user_id, 0, f"restore_backup_{backup_name}", "positive", 0.4)
        await query.edit_message_text("✅ تم استعادة النسخة الاحتياطية بنجاح!")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل الاستعادة: {str(e)[:200]}")
    
    await admin_panel_callback(update, context)

# ===================================================================
# 36.17 دوال تحليل المشاعر المتقدمة - المفقودة
# ===================================================================

async def sentiment_analysis_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تحليل المشاعر للمجموعة أو المستخدم"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    chat_id = None
    
    # محاولة استخراج chat_id من البيانات
    parts = query.data.split(":")
    if len(parts) >= 2:
        try:
            chat_id = int(parts[1])
        except:
            chat_id = update.effective_chat.id if update.effective_chat else None
    
    if not chat_id:
        chat_id = update.effective_chat.id if update.effective_chat else 0
    
    # جلب تحليل المشاعر
    user_sentiment = learning_engine.get_user_sentiment_profile(user_id)
    chat_sentiment = learning_engine.get_chat_sentiment_profile(chat_id) if chat_id else None
    
    text = "🧠 **تحليل المشاعر**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"👤 **مشاعرك:**\n"
    text += f"📊 المتوسط: {user_sentiment.get('avg_sentiment', 0):.3f}\n"
    text += f"📈 الاستقرار: {user_sentiment.get('stability', 0):.3f}\n"
    text += f"📊 الاتجاه: {user_sentiment.get('trend', 'stable')}\n"
    text += f"📝 الرسائل: {user_sentiment.get('messages', 0)}\n"
    
    if chat_sentiment:
        text += f"\n💬 **مشاعر المجموعة:**\n"
        text += f"📊 المتوسط: {chat_sentiment.get('avg_sentiment', 0):.3f}\n"
        text += f"📈 الاستقرار: {chat_sentiment.get('stability', 0):.3f}\n"
        text += f"📊 الاتجاه: {chat_sentiment.get('trend', 'stable')}\n"
        text += f"📝 الرسائل: {chat_sentiment.get('messages', 0)}\n"
    
    # إضافة إحصائيات التعلم
    learning_stats = await db_get_learning_stats()
    text += f"\n🧠 **إحصائيات التعلم:**\n"
    text += f"📝 الأنماط المتعلمة: {learning_stats.get('patterns', 0)}\n"
    text += f"📊 سجل المشاعر: {learning_stats.get('sentiment_history', 0)}\n"
    text += f"👤 ملفات المستخدمين: {learning_stats.get('users_with_profile', 0)}\n"
    text += f"💬 ملفات المجموعات: {learning_stats.get('chats_with_profile', 0)}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard)

async def learning_dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لوحة التعلم الذكي"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    learning_stats = await db_get_learning_stats()
    total_users = len(learning_engine.user_patterns)
    total_chats = len(learning_engine.chat_patterns)
    
    text = "🧠 **لوحة التعلم الذكي**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📝 أنماط التعلم: {learning_stats.get('patterns', 0)}\n"
    text += f"📊 سجل المشاعر: {learning_stats.get('sentiment_history', 0)}\n"
    text += f"👤 مستخدمون متعلمون: {learning_stats.get('users_with_profile', 0)}\n"
    text += f"💬 مجموعات متعلمة: {learning_stats.get('chats_with_profile', 0)}\n"
    text += f"🎯 استجابات متعلمة: {learning_stats.get('learned_responses', 0)}\n"
    text += f"👥 مستخدمين في الذاكرة: {total_users}\n"
    text += f"💬 مجموعات في الذاكرة: {total_chats}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 تحليل المشاعر", callback_data="sentiment_analysis")],
        [InlineKeyboardButton("🔄 تحديث", callback_data="learning_dashboard")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard)

# ===================================================================
# 36.18 دوال اللغة - المفقودة
# ===================================================================

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج تغيير اللغة"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    lang_code = query.data.split("_")[-1]
    await set_user_language(user_id, lang_code)
    await db_set_user_language(user_id, lang_code)
    await db_save_sentiment_history(user_id, 0, f"language_changed_{lang_code}", "neutral", 0.1)
    kb, title, active = await get_main_keyboard(user_id)
    if query:
        await safe_edit_markdown(query, title, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, title, reply_markup=kb)

# ===================================================================
# 36.19 دوال الاشتراك - المفقودة
# ===================================================================

async def trial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج التجربة المجانية"""
    await trial_command_handler(update, context)

async def subscribe_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج قائمة الاشتراكات"""
    await subscribe_command_handler(update, context)

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
    """شراء اشتراك 30 يوم"""
    if update.callback_query:
        await update.callback_query.answer()
    await buy_subscription_callback(update, context, 30, 50, "اشتراك شهر")

async def buy_subscription_90_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شراء اشتراك 90 يوم"""
    if update.callback_query:
        await update.callback_query.answer()
    await buy_subscription_callback(update, context, 90, 120, "اشتراك 3 أشهر")

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

# ===================================================================
# 36.20 دوال الأمان الإضافية - المفقودة
# ===================================================================

async def security_warn_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعدادات التحذير"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    settings = await db_get_security_settings(chat_id)
    max_warnings = settings.get('max_warnings', 3)
    warn_penalty = settings.get('warn_penalty', 'ban')
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔢 عدد التحذيرات: {max_warnings}", callback_data=f"warn_count:{chat_id}"),
         InlineKeyboardButton(f"⚖️ العقوبة: {warn_penalty}", callback_data=f"warn_penalty:{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])
    
    await query.edit_message_text(
        f"⚠️ **إعدادات التحذير**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 عدد التحذيرات: {max_warnings}\n"
        f"⚖️ عقوبة الوصول للحد الأقصى: {warn_penalty}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"اختر الإعداد المطلوب:",
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )

async def security_warn_count_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين عدد التحذيرات"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    context.user_data['state'] = "WAITING_WARN_COUNT"
    context.user_data['security_chat_id'] = chat_id
    await query.edit_message_text("🔢 أرسل عدد التحذيرات المسموح بها (1-10):\nمثال: 3")

async def set_warn_penalty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين عقوبة التحذير"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.edit_message_text("❌ بيانات غير صالحة")
        return
    penalty = parts[1]
    chat_id = int(parts[2])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    await db_set_security_settings(chat_id, warn_penalty=penalty)
    await db_save_sentiment_history(user_id, chat_id, f"set_warn_penalty_{penalty}", "neutral", 0)
    await query.answer(f"✅ تم تعيين عقوبة التحذير إلى: {penalty}")
    await security_warn_settings_callback(update, context)

async def security_delete_penalty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين عقوبة الحذف"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👢 طرد", callback_data=f"set_delete_penalty:kick:{chat_id}"),
         InlineKeyboardButton("🛑 حظر", callback_data=f"set_delete_penalty:ban:{chat_id}")],
        [InlineKeyboardButton("🔇 كتم", callback_data=f"set_delete_penalty:mute:{chat_id}"),
         InlineKeyboardButton("⚠️ تحذير", callback_data=f"set_delete_penalty:warn:{chat_id}")],
        [InlineKeyboardButton("❌ لا شيء", callback_data=f"set_delete_penalty:none:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])
    await query.edit_message_text("⚖️ **اختر عقوبة الحذف التلقائي**", reply_markup=keyboard)

async def set_delete_penalty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين عقوبة الحذف"""
    query = update.callback_query
    if query:
        await query.answer()
    parts = query.data.split(":")
    if len(parts) == 3:
        penalty = parts[1]
        chat_id = int(parts[2])
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("🔒 غير مصرح", show_alert=True)
            return
        await db_set_security_settings(chat_id, delete_penalty=penalty, delete_penalty_duration=60)
        await db_save_sentiment_history(user_id, chat_id, f"set_delete_penalty_{penalty}", "neutral", 0)
        await query.answer(f"✅ تم تعيين عقوبة الحذف إلى: {penalty}")
        await _update_security_panel(query, chat_id, user_id)

async def security_enable_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تفعيل الكل"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، تفعيل الكل", callback_data=f"confirm_enable_all:{chat_id}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])
    await query.edit_message_text("⚠️ **تأكيد تفعيل الكل**\n\nسيتم تفعيل جميع أنواع الحذف:\n• الفيديوهات\n• الصوتيات\n• المتحركات\n• رسائل الخدمة\n• الملفات\n• الملصقات\n\nهل أنت متأكد؟", reply_markup=keyboard, parse_mode="Markdown")

async def confirm_enable_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد تفعيل الكل"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    keys = ['delete_videos', 'delete_audio', 'delete_animation', 'delete_service', 'delete_documents', 'delete_stickers']
    settings = await db_get_security_settings(chat_id, force_refresh=True)
    for key in keys:
        settings[key] = 1
    await db_set_security_settings(chat_id, **{k: settings[k] for k in keys})
    await db_save_sentiment_history(user_id, chat_id, "enable_all_security", "neutral", 0)
    await query.answer("✅ تم تفعيل جميع خيارات الحذف")
    await _update_security_panel(query, chat_id, user_id)

async def security_disable_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعطيل الكل"""
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    keys = ['delete_videos', 'delete_audio', 'delete_animation', 'delete_service', 'delete_documents', 'delete_stickers']
    settings = await db_get_security_settings(chat_id, force_refresh=True)
    for key in keys:
        settings[key] = 0
    await db_set_security_settings(chat_id, **{k: settings[k] for k in keys})
    await db_save_sentiment_history(user_id, chat_id, "disable_all_security", "neutral", 0)
    await query.answer("✅ تم تعطيل الكل")
    await _update_security_panel(query, chat_id, user_id)

# ===================================================================
# 36.21 دوال الأزرار الإضافية - المفقودة
# ===================================================================

async def channel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات القناة"""
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
    
    # جلب تحليل المشاعر
    chat_sentiment = learning_engine.get_chat_sentiment_profile(ch_db_id)
    avg_sentiment = chat_sentiment.get('avg_sentiment', 0)
    sentiment_icon = "😊" if avg_sentiment > 0.2 else "😐" if avg_sentiment > -0.2 else "😞"
    
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
    text += f"{sentiment_icon} تحليل المشاعر: {avg_sentiment:.2f}\n"
    
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
    """عرض نمو القناة"""
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

async def publish_all_channels_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نشر في جميع القنوات"""
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    if not await db_has_active_subscription(uid) and not await db_has_used_trial(uid):
        await query.edit_message_text("⚠️ اشتراكك منتهٍ، استخدم /trial أو /subscribe")
        return
    channels = await db_get_channels(uid)
    if not channels:
        if query:
            await query.edit_message_text("📭 لا توجد قنوات للنشر فيها.")
        else:
            await safe_send_markdown(context.bot, uid, "📭 لا توجد قنوات للنشر فيها.")
        return
    if query:
        await query.edit_message_text("📤 جاري النشر في جميع القنوات...")
    else:
        await safe_send_markdown(context.bot, uid, "📤 جاري النشر في جميع القنوات...")
    results = []
    success_count = 0
    fail_count = 0
    no_posts_count = 0
    for ch_db_id, ch_tele_id, ch_name, banned in channels:
        if banned:
            results.append(f"⛔ {ch_name}: قناة محظورة")
            continue
        post = await db_get_next_post(ch_db_id)
        if not post:
            results.append(f"📭 {ch_name}: لا توجد منشورات")
            no_posts_count += 1
            continue
        translation_lang = await get_user_translation_language(uid)
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
            results.append(f"✅ {ch_name}: تم النشر بنجاح")
            success_count += 1
            await db_save_sentiment_history(uid, ch_db_id, f"publish_all_success_{ch_name}", "positive", 0.3)
        except Exception as e:
            results.append(f"❌ {ch_name}: {str(e)[:50]}")
            fail_count += 1
            await db_save_sentiment_history(uid, ch_db_id, f"publish_all_fail_{ch_name}", "negative", -0.3)
        await asyncio.sleep(1)
    summary = f"📊 **نتائج النشر في جميع القنوات**\n━━━━━━━━━━━━━━━━━━━━━━\n✅ نجح: {success_count}\n❌ فشل: {fail_count}\n📭 لا توجد منشورات: {no_posts_count}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    result_text = summary + "\n".join(results[:20])
    if len(results) > 20:
        result_text += f"\n\n... و {len(results)-20} نتيجة أخرى"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(uid, 'back'), callback_data=CallbackData.BACK)]
    ])
    if query:
        await safe_edit_markdown(query, result_text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, uid, result_text, reply_markup=keyboard)

# ===================================================================
# 36.22 دوال TaskManager - المفقودة
# ===================================================================

class TaskManager:
    """مدير المهام الخلفية المتطور"""
    
    def __init__(self, max_tasks=50, max_concurrent=10):
        self.tasks = set()
        self._lock = asyncio.Lock()
        self.max_tasks = max_tasks
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.task_names = {}
    
    def create_task(self, coro: Awaitable, name: str = None) -> asyncio.Task:
        """إنشاء مهمة خلفية جديدة"""
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
        
        # تنظيف المهام المكتملة
        self._cleanup_tasks()
        
        task = asyncio.create_task(_wrapped())
        if name:
            task.set_name(name)
            self.task_names[task] = name
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task
    
    def _cleanup_tasks(self):
        """تنظيف المهام المكتملة"""
        done = {t for t in self.tasks if t.done()}
        for t in done:
            self.tasks.discard(t)
            self.task_names.pop(t, None)
    
    async def cancel_all(self):
        """إلغاء جميع المهام"""
        for task in list(self.tasks):
            if not task.done():
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        self.task_names.clear()
    
    def get_task_count(self) -> int:
        """عدد المهام النشطة"""
        self._cleanup_tasks()
        return len(self.tasks)
    
    def get_task_names(self) -> List[str]:
        """الحصول على أسماء المهام النشطة"""
        return [self.task_names.get(t, 'غير مسماة') for t in self.tasks if not t.done()]

task_manager = TaskManager(max_concurrent=10)

# ===================================================================
# 36.23 دوال safe_loop - المفقودة
# ===================================================================

async def safe_loop(coro_func, name: str = "background_loop"):
    """تشغيل حلقة خلفية آمنة مع معالجة الأخطاء وإعادة التشغيل التلقائي"""
    consecutive_errors = 0
    backoff = 5
    max_backoff = 300
    
    while True:
        try:
            # تنفيذ الدالة
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
    """تشغيل polling مع معالجة الأخطاء وإعادة التشغيل التلقائي"""
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
# دالة تهيئة جدول الأمان (إصدار متطور)
# ===================================================================

async def init_security_table():
    """
    تهيئة جدول إعدادات الأمان للمجموعات مع دعم الترقية التلقائية.
    """
    try:
        async def _init(conn):
            # التحقق من وجود الجدول
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS group_security_settings (
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
                    captcha_enabled INTEGER DEFAULT 0,
                    captcha_timeout INTEGER DEFAULT 60,
                    max_links_per_message INTEGER DEFAULT 0,
                    max_mentions_per_message INTEGER DEFAULT 0,
                    allowed_domains TEXT DEFAULT '[]',
                    ban_on_links INTEGER DEFAULT 0,
                    warn_on_links INTEGER DEFAULT 0,
                    auto_delete_after_minutes INTEGER DEFAULT 0
                )
            """)
            
            # التحقق من وجود الأعمدة وإضافتها إذا كانت مفقودة
            cur = await conn.execute("PRAGMA table_info(group_security_settings)")
            columns = [row[1] for row in await cur.fetchall()]
            
            # قائمة الأعمدة المطلوبة مع قيمها الافتراضية
            required_columns = {
                'captcha_enabled': 'INTEGER DEFAULT 0',
                'captcha_timeout': 'INTEGER DEFAULT 60',
                'max_links_per_message': 'INTEGER DEFAULT 0',
                'max_mentions_per_message': 'INTEGER DEFAULT 0',
                'allowed_domains': 'TEXT DEFAULT \'[]\'',
                'ban_on_links': 'INTEGER DEFAULT 0',
                'warn_on_links': 'INTEGER DEFAULT 0',
                'auto_delete_after_minutes': 'INTEGER DEFAULT 0'
            }
            
            # إضافة الأعمدة المفقودة
            for col_name, col_type in required_columns.items():
                if col_name not in columns:
                    try:
                        await conn.execute(f"ALTER TABLE group_security_settings ADD COLUMN {col_name} {col_type}")
                        logger.info(f"✅ تم إضافة العمود {col_name} إلى group_security_settings")
                    except Exception as e:
                        logger.warning(f"⚠️ فشل إضافة العمود {col_name}: {e}")
            
            # إنشاء فهارس
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_group_security_chat ON group_security_settings(chat_id)")
            
            await conn.commit()
            logger.info("✅ جدول group_security_settings جاهز ومحدث")
            
        await execute_db(_init)
        
    except Exception as e:
        logger.error(f"❌ فشل تهيئة جدول الأمان: {e}")
        raise
# ===================================================================
# دالة إصلاح الأعمدة المفقودة في قاعدة البيانات
# ===================================================================

async def fix_missing_columns():
    """
    إصلاح الأعمدة المفقودة في الجداول الرئيسية وإضافة الجداول الناقصة.
    """
    try:
        async def _fix(conn):
            # ===================================================================
            # 1. إصلاح جدول users
            # ===================================================================
            cur = await conn.execute("PRAGMA table_info(users)")
            existing_columns = [row[1] for row in await cur.fetchall()]
            
            required_columns = {
                'level': 'INTEGER DEFAULT 1',
                'achievements': 'TEXT DEFAULT \'[]\'',
                'last_daily_reward': 'TEXT',
                'last_weekly_reward': 'TEXT',
                'referred_by': 'INTEGER',
                'points': 'INTEGER DEFAULT 0',
                'warning_count': 'INTEGER DEFAULT 0',
                'last_activity': 'TEXT',
                'is_verified': 'INTEGER DEFAULT 0',
                'twofa_secret': 'TEXT',
                'twofa_enabled': 'INTEGER DEFAULT 0'
            }
            
            for col_name, col_type in required_columns.items():
                if col_name not in existing_columns:
                    try:
                        await conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                        logger.info(f"✅ تم إضافة العمود {col_name} إلى users")
                    except Exception as e:
                        logger.warning(f"⚠️ فشل إضافة {col_name}: {e}")
            
            # ===================================================================
            # 2. إصلاح جدول posts
            # ===================================================================
            cur = await conn.execute("PRAGMA table_info(posts)")
            existing_posts = [row[1] for row in await cur.fetchall()]
            
            posts_columns = {
                'sentiment_score': 'REAL DEFAULT 0',
                'sentiment_label': 'TEXT DEFAULT \'neutral\'',
                'is_scheduled': 'INTEGER DEFAULT 0',
                'scheduled_for': 'TEXT',
                'is_edited': 'INTEGER DEFAULT 0',
                'edited_at': 'TEXT'
            }
            
            for col_name, col_type in posts_columns.items():
                if col_name not in existing_posts:
                    try:
                        await conn.execute(f"ALTER TABLE posts ADD COLUMN {col_name} {col_type}")
                        logger.info(f"✅ تم إضافة العمود {col_name} إلى posts")
                    except Exception as e:
                        logger.warning(f"⚠️ فشل إضافة {col_name}: {e}")
            
            # ===================================================================
            # 3. إصلاح جدول bot_groups
            # ===================================================================
            cur = await conn.execute("PRAGMA table_info(bot_groups)")
            existing_groups = [row[1] for row in await cur.fetchall()]
            
            groups_columns = {
                'members_count': 'INTEGER DEFAULT 0',
                'admins_count': 'INTEGER DEFAULT 0',
                'last_activity': 'TEXT',
                'is_active': 'INTEGER DEFAULT 1'
            }
            
            for col_name, col_type in groups_columns.items():
                if col_name not in existing_groups:
                    try:
                        await conn.execute(f"ALTER TABLE bot_groups ADD COLUMN {col_name} {col_type}")
                        logger.info(f"✅ تم إضافة العمود {col_name} إلى bot_groups")
                    except Exception as e:
                        logger.warning(f"⚠️ فشل إضافة {col_name}: {e}")
            
            # ===================================================================
            # 4. إصلاح جدول schedule
            # ===================================================================
            cur = await conn.execute("PRAGMA table_info(schedule)")
            existing_schedule = [row[1] for row in await cur.fetchall()]
            
            schedule_columns = {
                'last_executed': 'TEXT',
                'is_paused': 'INTEGER DEFAULT 0'
            }
            
            for col_name, col_type in schedule_columns.items():
                if col_name not in existing_schedule:
                    try:
                        await conn.execute(f"ALTER TABLE schedule ADD COLUMN {col_name} {col_type}")
                        logger.info(f"✅ تم إضافة العمود {col_name} إلى schedule")
                    except Exception as e:
                        logger.warning(f"⚠️ فشل إضافة {col_name}: {e}")
            
            # ===================================================================
            # 5. إصلاح جدول group_security
            # ===================================================================
            cur = await conn.execute("PRAGMA table_info(group_security)")
            existing_security = [row[1] for row in await cur.fetchall()]
            
            security_columns = {
                'captcha_enabled': 'INTEGER DEFAULT 0',
                'captcha_timeout': 'INTEGER DEFAULT 60',
                'max_links_per_message': 'INTEGER DEFAULT 0',
                'max_mentions_per_message': 'INTEGER DEFAULT 0',
                'allowed_domains': 'TEXT DEFAULT \'[]\''
            }
            
            for col_name, col_type in security_columns.items():
                if col_name not in existing_security:
                    try:
                        await conn.execute(f"ALTER TABLE group_security ADD COLUMN {col_name} {col_type}")
                        logger.info(f"✅ تم إضافة العمود {col_name} إلى group_security")
                    except Exception as e:
                        logger.warning(f"⚠️ فشل إضافة {col_name}: {e}")
            
            # ===================================================================
            # 6. إنشاء الجداول المفقودة
            # ===================================================================
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_levels (
                    user_id INTEGER PRIMARY KEY,
                    points INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    total_points INTEGER DEFAULT 0,
                    rank INTEGER DEFAULT 0,
                    last_updated TEXT
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS group_rules (
                    chat_id INTEGER PRIMARY KEY,
                    rules_text TEXT,
                    updated_by INTEGER,
                    updated_at TEXT,
                    version INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1
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
                    status TEXT DEFAULT 'pending',
                    sent_count INTEGER DEFAULT 0,
                    is_global INTEGER DEFAULT 0,
                    target_users TEXT DEFAULT '[]'
                )
            """)
            
            # ===================================================================
            # 7. إنشاء الفهارس الإضافية
            # ===================================================================
            
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_banned ON users(banned)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_groups_chat_name ON bot_groups(chat_name)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_groups_banned ON bot_groups(banned)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_auto_replies_chat ON auto_replies(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_auto_replies_keyword ON auto_replies(keyword)")
            
            # ===================================================================
            # 8. تحديث إصدار قاعدة البيانات
            # ===================================================================
            
            await conn.execute("""
                INSERT OR REPLACE INTO settings (key, value) VALUES ('db_version', '2.1.1')
            """)
            
            await conn.commit()
            logger.info("✅ تم إصلاح جميع الأعمدة المفقودة بنجاح (الإصدار 2.1.1)")
            
        await execute_db(_fix)
        
    except Exception as e:
        logger.error(f"❌ فشل إصلاح الأعمدة المفقودة: {e}")
        raise
# ===================================================================
# دوال تحميل اللغات والكلمات المحظورة (بدون محتوى حساس)
# ===================================================================

def load_banned_words_from_file(file_path: Path) -> List[str]:
    """
    تحميل الكلمات المحظورة من ملف نصي.
    إذا كان الملف غير موجود، يتم إنشاؤه بقائمة افتراضية (بدون محتوى حساس).
    """
    words = []
    if not file_path.exists():
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("# قائمة الكلمات المحظورة - كل كلمة في سطر منفصل\n")
                f.write("# ابدأ السطر بـ # للتعليق\n\n")
                # تم إزالة الكلمات الحساسة
                f.write("# أضف الكلمات المحظورة هنا\n")
                f.write("كلمة1\nكلمة2\n")
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


def load_all_languages():
    """
    تحميل جميع ملفات اللغة من مجلد lang/.
    إذا لم تكن موجودة، يتم إنشاء الملفات الافتراضية.
    """
    global _lang_data

    LANG_PATH.mkdir(parents=True, exist_ok=True)

    create_default_lang_files()

    loaded_count = 0
    for lang_file in LANG_PATH.glob("*.json"):
        lang = lang_file.stem
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                _lang_data[lang] = json.load(f)
            loaded_count += 1
        except Exception as e:
            print(f"⚠️ فشل تحميل {lang_file}: {e}")

    if not _lang_data:
        print("⚠️ لم يتم تحميل أي ملف لغة، استخدام العربية كافتراضية")
        _lang_data['ar'] = {
            "welcome": "🌿 مرحباً بك في البوت",
            "back": "🔙 رجوع",
            "error": "⚠️ حدث خطأ",
            "admin_only": "🔒 هذا الأمر للمشرفين فقط!",
            "group_only": "🔒 هذا الأمر يعمل فقط في المجموعات!",
            "help": "❓ المساعدة",
            "settings": "⚙️ الإعدادات",
            "no_channels": "لا توجد قنوات",
            "add_channel": "➕ إضافة قناة",
            "my_channels": "📡 قنواتي",
            "channel_added": "✅ تم إضافة القناة {0}",
            "channel_exists": "⚠️ القناة موجودة مسبقاً",
            "channel_deleted": "✅ تم حذف القناة",
            "delete_failed": "❌ فشل الحذف",
            "no_posts": "📭 لا توجد منشورات",
            "my_posts_title": "📋 منشوراتي غير المنشورة",
            "recycled": "♻️ تم إعادة تدوير جميع المنشورات",
            "deleted_all": "✅ تم حذف جميع المنشورات",
            "confirm_delete": "⚠️ هل أنت متأكد من حذف جميع المنشورات؟",
            "locked": "🔒 تم قفل المجموعة",
            "unlocked": "🔓 تم فتح المجموعة",
            "cancelled": "❌ تم الإلغاء",
            "error": "⚠️ حدث خطأ، حاول مرة أخرى"
        }

    print(f"✅ تم تحميل {loaded_count} ملف لغة")
    return _lang_data


# ===================================================================
# متغيرات اللغة العالمية
# ===================================================================

# قاموس تخزين بيانات اللغة
_lang_data = {}
_lang_cache_time = {}
LANG_CACHE_TTL = 300
_lang_lock = asyncio.Lock()
user_language = {}


# ===================================================================
# دوال تحميل اللغات والكلمات المحظورة
# ===================================================================

def load_banned_words_from_file(file_path: Path) -> List[str]:
    """
    تحميل الكلمات المحظورة من ملف نصي.
    """
    words = []
    if not file_path.exists():
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("# قائمة الكلمات المحظورة - كل كلمة في سطر منفصل\n")
                f.write("# ابدأ السطر بـ # للتعليق\n\n")
                f.write("# أضف الكلمات المحظورة هنا\n")
                f.write("كلمة1\nكلمة2\n")
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


def load_all_languages():
    """
    تحميل جميع ملفات اللغة من مجلد lang/.
    """
    global _lang_data
    
    # التأكد من وجود مجلد اللغات
    LANG_PATH.mkdir(parents=True, exist_ok=True)
    
    # إنشاء ملفات اللغة الافتراضية إذا لم تكن موجودة
    create_default_lang_files()
    
    loaded_count = 0
    for lang_file in LANG_PATH.glob("*.json"):
        lang = lang_file.stem
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                _lang_data[lang] = json.load(f)
            loaded_count += 1
        except Exception as e:
            print(f"⚠️ فشل تحميل {lang_file}: {e}")
    
    # إذا لم يتم تحميل أي لغة، استخدام العربية كافتراضية
    if not _lang_data:
        print("⚠️ لم يتم تحميل أي ملف لغة، استخدام العربية كافتراضية")
        _lang_data['ar'] = {
            "welcome": "🌿 مرحباً بك في البوت",
            "back": "🔙 رجوع",
            "error": "⚠️ حدث خطأ",
            "admin_only": "🔒 هذا الأمر للمشرفين فقط!",
            "group_only": "🔒 هذا الأمر يعمل فقط في المجموعات!",
            "help": "❓ المساعدة",
            "settings": "⚙️ الإعدادات",
            "no_channels": "لا توجد قنوات",
            "add_channel": "➕ إضافة قناة",
            "my_channels": "📡 قنواتي",
            "channel_added": "✅ تم إضافة القناة {0}",
            "channel_exists": "⚠️ القناة موجودة مسبقاً",
            "channel_deleted": "✅ تم حذف القناة",
            "delete_failed": "❌ فشل الحذف",
            "no_posts": "📭 لا توجد منشورات",
            "my_posts_title": "📋 منشوراتي غير المنشورة",
            "recycled": "♻️ تم إعادة تدوير جميع المنشورات",
            "deleted_all": "✅ تم حذف جميع المنشورات",
            "confirm_delete": "⚠️ هل أنت متأكد من حذف جميع المنشورات؟",
            "locked": "🔒 تم قفل المجموعة",
            "unlocked": "🔓 تم فتح المجموعة",
            "cancelled": "❌ تم الإلغاء",
            "error": "⚠️ حدث خطأ، حاول مرة أخرى"
        }
    
    print(f"✅ تم تحميل {loaded_count} ملف لغة")
    return _lang_data


def create_default_lang_files():
    """
    إنشاء ملفات اللغة الافتراضية إذا لم تكن موجودة.
    """
    LANG_PATH.mkdir(parents=True, exist_ok=True)

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
            try:
                with open(lang_file, 'w', encoding='utf-8') as f:
                    json.dump(texts, f, ensure_ascii=False, indent=2)
                print(f"✅ تم إنشاء ملف اللغة: {lang}.json")
            except Exception as e:
                print(f"⚠️ فشل إنشاء {lang_file}: {e}")
# ===================================================================
# معالج زر المساعدة
# ===================================================================

# ===================================================================
# 36.22 معالج زر المساعدة (help_callback)
# ===================================================================

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض قائمة المساعدة الكاملة مع الأوامر المتاحة.
    يتم استدعاؤها عند الضغط على زر المساعدة أو عبر الأمر /help.
    """
    # 1. التعامل مع الاستعلام (CallbackQuery)
    query = update.callback_query
    user_id = update.effective_user.id
    
    if query:
        try:
            await query.answer()
        except Exception as e:
            logger.debug(f"فشل الرد على الاستعلام: {e}")
    
    # 2. الحصول على النص المترجم
    text = get_text(user_id, 'help')
    
    # 3. التأكد من وجود النص (إذا كان مفقوداً، استخدام النص الافتراضي)
    if not text or text == 'help':
        text = """
❓ **المساعدة**
━━━━━━━━━━━━━━━━━━━━━━
📌 **الأوامر المتاحة:**

🔹 **الأساسية:**
/start - القائمة الرئيسية
/help - هذه المساعدة
/language - تغيير اللغة

🔹 **الاشتراك والتجربة:**
/trial - تجربة مجانية (30 يوم)
/subscribe - الاشتراك

🔹 **إدارة القنوات:**
/add_channel - إضافة قناة
/my_channels - عرض قنواتي
/add_posts - إضافة منشورات
/publish - نشر منشور

🔹 **إدارة المجموعات:**
/syncgroup - تفعيل المجموعة
/security - إعدادات الأمان
/panel - لوحة التحكم
/lock - قفل المجموعة
/unlock - فتح المجموعة

🔹 **الإشراف:**
/ban - حظر مستخدم
/mute - كتم مستخدم
/warn - تحذير مستخدم
/kick - طرد مستخدم
/unban - إلغاء حظر

🔹 **المشرفين المخفيين:**
/register_hidden_owner - تسجيل مالك مخفي
/add_hidden_admin - إضافة مشرف مخفي
/remove_hidden_admin - إزالة مشرف مخفي
/list_hidden_admins - عرض المشرفين المخفيين

🔹 **أخرى:**
/rank - رتبتك
/top - أفضل 10
/stats - إحصائيات القناة
/schedule - جدولة منشور
/contests - المسابقات
/support - مركز الدعم
/developer - المطور
/updates - التحديثات
/sendcode - كود الدعوة (للمشرفين)
/set_log_channel - تعيين قناة التقارير (للمشرفين)
/set_rules - تعيين قوانين المجموعة
/rules - عرض قوانين المجموعة
        """
    
    # 4. بناء لوحة المفاتيح
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    
    # 5. إرسال أو تعديل الرسالة
    try:
        if query:
            await safe_edit_markdown(query, text, reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
    except Exception as e:
        # 6. محاولة إرسال نص عادي في حالة فشل Markdown
        try:
            plain_text = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', text)
            if query:
                await query.edit_message_text(plain_text, reply_markup=keyboard)
            else:
                await context.bot.send_message(chat_id=user_id, text=plain_text, reply_markup=keyboard)
        except Exception as e2:
            logger.error(f"فشل عرض المساعدة: {e2}")
    
    # 7. تسجيل الحدث في سجل المشاعر
    try:
        await db_save_sentiment_history(user_id, 0, "help_viewed", "neutral", 0.1)
    except Exception as e:
        logger.debug(f"فشل تسجيل سجل المشاعر: {e}")
    
    # 8. تسجيل التعلم
    try:
        await learning_engine.learn_from_message(user_id, 0, "help_command", "help_displayed", True)
    except Exception as e:
        logger.debug(f"فشل تسجيل التعلم: {e}")
# ===================================================================
# دوال الدعم (Support Callbacks)
# ===================================================================

async def support_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الدعم الرئيسية"""
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
    
    await db_save_sentiment_history(user_id, 0, "support_menu_viewed", "neutral", 0.1)


async def support_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مساعدة الدعم"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    text = get_text(user_id, 'support_help')
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.SUPPORT_MENU)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
    
    await db_save_sentiment_history(user_id, 0, "support_help_viewed", "neutral", 0.1)


async def support_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء تذكرة دعم جديدة"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    context.user_data['support_mode'] = True
    
    text = "📝 **كتابة تذكرة دعم**\n\nأرسل رسالتك بالتفصيل وسنرد عليك بأسرع وقت.\n\n📌 **ملاحظة:** سيتم إرسال تذكرة برقم خاص بك."
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 إلغاء", callback_data=CallbackData.SUPPORT_MENU)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
    
    await db_save_sentiment_history(user_id, 0, "support_ticket_started", "neutral", 0.1)


async def support_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة من الدعم إلى القائمة الرئيسية"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    context.user_data.pop('support_mode', None)
    
    await main_menu_callback(update, context)
# ===================================================================
# دوال الإحالات (Referral Callbacks)
# ===================================================================

async def referral_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض قائمة الإحالات الرئيسية.
    تعرض رابط الإحالة الخاص بالمستخدم، عدد المحالين، والمكافآت المتاحة.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. الحصول على كود الإحالة
    ref_code = await db_get_referral_code(user_id)
    if not ref_code:
        ref_code = await db_generate_referral_code(user_id)
    
    # 2. الحصول على إحصائيات الإحالات
    stats = await db_get_referral_stats(user_id)
    
    # 3. الحصول على إعدادات الإحالات
    settings = await db_get_referral_settings()
    reward_per_ref = int(settings.get('reward_days_per_referral', '3'))
    welcome_bonus = int(settings.get('welcome_bonus_points', '10'))
    
    # 4. بناء النص
    text = get_text(user_id, 'referral_title').format(
        ref_code,
        BOT_USERNAME,
        user_id,
        stats['total_referrals'],
        stats['available_days'],
        reward_per_ref,
        welcome_bonus
    )
    
    # 5. بناء لوحة المفاتيح
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'copy_link'), callback_data=f"{CallbackData.REFERRAL_COPY_LINK_PREFIX}{ref_code}")],
        [InlineKeyboardButton(get_text(user_id, 'claim_reward'), callback_data=CallbackData.REFERRAL_CLAIM_REWARD)],
        [InlineKeyboardButton(get_text(user_id, 'referral_list'), callback_data=CallbackData.REFERRAL_LIST)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    
    # 6. إرسال أو تعديل الرسالة
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
    
    # 7. تسجيل الحدث في سجل المشاعر
    await db_save_sentiment_history(user_id, 0, "referral_menu_viewed", "neutral", 0.1)


async def referral_copy_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نسخ رابط الإحالة.
    يعرض الرابط بشكل منسق مع شرح بسيط.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    ref_code = query.data.split(":")[-1]
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{ref_code}"
    
    text = f"🔗 **رابط الإحالة الخاص بك:**\n\n`{link}`\n\n📌 **كيفية الاستخدام:**\n"
    text += "1️⃣ انسخ الرابط\n"
    text += "2️⃣ أرسله لأصدقائك\n"
    text += "3️⃣ عند تسجيلهم عبر الرابط، ستحصل على مكافآت 🎁\n\n"
    text += "📊 **مكافأة كل إحالة:** 3 أيام اشتراك إضافي"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.REFERRAL_MENU)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")
    
    await db_save_sentiment_history(user_id, 0, "referral_link_copied", "positive", 0.3)


async def referral_claim_reward_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    صرف مكافآت الإحالات المتاحة.
    يتم إضافة الأيام إلى اشتراك المستخدم.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. محاولة صرف المكافآت
    days = await db_claim_referral_reward(user_id)
    
    if days > 0:
        text = get_text(user_id, 'reward_claimed').format(days)
        await db_save_sentiment_history(user_id, 0, f"referral_reward_claimed_{days}", "positive", 0.7)
    else:
        text = get_text(user_id, 'no_reward_available')
        await db_save_sentiment_history(user_id, 0, "referral_reward_claim_failed", "neutral", 0)
    
    # 2. عرض النتيجة
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.REFERRAL_MENU)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def referral_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض قائمة المستخدمين الذين سجلوا عبر رابط الإحالة.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. جلب قائمة المحالين
    async def _get_referrals(conn):
        cur = await conn.execute(
            "SELECT referred_id, created_at FROM referrals WHERE referrer_id=? ORDER BY created_at DESC LIMIT 20",
            (user_id,)
        )
        return await cur.fetchall()
    
    referrals = await execute_db(_get_referrals)
    
    if not referrals:
        text = get_text(user_id, 'no_referrals')
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.REFERRAL_MENU)]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")
        return
    
    # 2. بناء النص
    text = "📋 **قائمة المحالين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for ref_id, ref_at in referrals:
        try:
            user = await context.bot.get_chat(ref_id)
            name = user.first_name or str(ref_id)
        except:
            name = str(ref_id)
        # تنسيق التاريخ
        try:
            dt = datetime.fromisoformat(ref_at)
            date_str = dt.strftime("%Y-%m-%d")
        except:
            date_str = ref_at[:10] if ref_at else "?"
        text += f"• {name} (`{ref_id}`) - {date_str}\n"
    
    text += f"\n📊 إجمالي المحالين: {len(referrals)}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.REFERRAL_MENU)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")
    
    await db_save_sentiment_history(user_id, 0, "referral_list_viewed", "neutral", 0.1)


# ===================================================================
# دوال قاعدة بيانات الإحالات (إذا كانت مفقودة)
# ===================================================================

async def db_get_referral_code(user_id: int) -> str:
    """
    الحصول على كود الإحالة للمستخدم من قاعدة البيانات.
    """
    async def _get(conn):
        cur = await conn.execute("SELECT referral_code FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row and row[0] else None
    return await execute_db(_get)


async def db_generate_referral_code(user_id: int) -> str:
    """
    إنشاء كود إحالة فريد للمستخدم وحفظه في قاعدة البيانات.
    """
    async def _generate(conn):
        # إنشاء كود فريد باستخدام hash من معرف المستخدم والوقت
        code_hash = hashlib.md5(f"{user_id}{time_module.time()}".encode()).hexdigest()[:8]
        referral_code = f"REF{code_hash.upper()}"
        
        # تحديث كود الإحالة في قاعدة البيانات
        await conn.execute(
            "UPDATE users SET referral_code=? WHERE user_id=?",
            (referral_code, user_id)
        )
        await conn.commit()
        return referral_code
    return await execute_db(_generate)


async def db_get_referral_stats(user_id: int) -> dict:
    """
    الحصول على إحصائيات الإحالات للمستخدم.
    تشمل: عدد الإحالات، إجمالي المكافآت، المكافآت المصروفة، المتاحة.
    """
    async def _get(conn):
        # عدد الإحالات
        cur = await conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=?",
            (user_id,)
        )
        total_referrals = (await cur.fetchone())[0] or 0
        
        # مكافآت الإحالات
        cur = await conn.execute(
            "SELECT referral_count, total_reward_days, claimed_reward_days FROM referral_rewards WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        
        if row:
            referral_count = row[0] or 0
            total_reward_days = row[1] or 0
            claimed_reward_days = row[2] or 0
        else:
            referral_count = 0
            total_reward_days = 0
            claimed_reward_days = 0
        
        available_days = max(0, total_reward_days - claimed_reward_days)
        
        return {
            'total_referrals': total_referrals,
            'referral_count': referral_count,
            'total_reward_days': total_reward_days,
            'claimed_reward_days': claimed_reward_days,
            'available_days': available_days
        }
    return await execute_db(_get)


async def db_claim_referral_reward(user_id: int) -> int:
    """
    صرف مكافآت الإحالات المتاحة.
    تعيد عدد الأيام التي تمت إضافتها إلى الاشتراك.
    """
    async def _claim(conn):
        # الحصول على المكافآت المتاحة
        cur = await conn.execute(
            "SELECT total_reward_days, claimed_reward_days FROM referral_rewards WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            return 0
        
        total = row[0] or 0
        claimed = row[1] or 0
        available = max(0, total - claimed)
        
        if available <= 0:
            return 0
        
        # إضافة الأيام إلى اشتراك المستخدم
        current_sub = await db_get_subscription_days_left(user_id)
        new_sub_days = current_sub + available
        end_date = (utc_now() + timedelta(days=new_sub_days)).isoformat()
        
        await conn.execute(
            "UPDATE users SET subscription_end=? WHERE user_id=?",
            (end_date, user_id)
        )
        
        # تحديث المكافآت المصروفة
        await conn.execute(
            "UPDATE referral_rewards SET claimed_reward_days = claimed_reward_days + ? WHERE user_id=?",
            (available, user_id)
        )
        await conn.commit()
        
        return available
    return await execute_db(_claim)


async def db_get_referral_settings() -> dict:
    """
    الحصول على إعدادات نظام الإحالات من قاعدة البيانات.
    """
    async def _get(conn):
        cur = await conn.execute("SELECT key, value FROM referral_settings")
        rows = await cur.fetchall()
        return {row[0]: row[1] for row in rows}
    return await execute_db(_get)
# ===================================================================
# دوال التذكيرات (Reminder Callbacks) - كاملة ومتطورة
# ===================================================================

async def reminder_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض قائمة إعدادات التذكيرات الرئيسية.
    تعرض حالة التذكيرات (الاشتراك، اليومي، الأسبوعي) مع أزرار التحكم.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. الحصول على إعدادات التذكيرات
    settings = await db_get_user_reminder_settings(user_id)
    
    # 2. بناء النص
    sub_status = "✅ مفعل" if settings.get('subscription_reminder', True) else "❌ معطل"
    daily_status = "✅ مفعل" if settings.get('daily_stats_reminder', False) else "❌ معطل"
    weekly_status = "✅ مفعل" if settings.get('weekly_report', True) else "❌ معطل"
    days_before = settings.get('reminder_days_before', 3)
    lang = settings.get('notification_lang', 'ar')
    
    text = get_text(user_id, 'reminder_title').format(sub_status, daily_status, weekly_status, days_before)
    
    # 3. بناء لوحة المفاتيح
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(get_text(user_id, 'reminder_sub'), callback_data=CallbackData.REMINDER_TOGGLE_SUB)],
        [InlineKeyboardButton(get_text(user_id, 'reminder_daily'), callback_data=CallbackData.REMINDER_TOGGLE_DAILY)],
        [InlineKeyboardButton(get_text(user_id, 'reminder_weekly'), callback_data=CallbackData.REMINDER_TOGGLE_WEEKLY)],
        [InlineKeyboardButton(get_text(user_id, 'reminder_days_btn'), callback_data=CallbackData.REMINDER_SET_DAYS)],
        [InlineKeyboardButton(get_text(user_id, 'reminder_lang_btn'), callback_data=CallbackData.REMINDER_SET_LANG)],
        [InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)]
    ])
    
    # 4. إرسال أو تعديل الرسالة
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
    
    # 5. تسجيل الحدث
    await db_save_sentiment_history(user_id, 0, "reminder_menu_viewed", "neutral", 0.1)


async def reminder_toggle_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تبديل حالة تذكير انتهاء الاشتراك (تفعيل/تعطيل).
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. الحصول على الإعدادات الحالية
    settings = await db_get_user_reminder_settings(user_id)
    new_status = not settings.get('subscription_reminder', True)
    
    # 2. تحديث الإعدادات
    await db_update_reminder_settings(user_id, subscription_reminder=new_status)
    
    # 3. تسجيل الحدث
    await db_save_sentiment_history(user_id, 0, f"reminder_sub_toggle_{new_status}", "neutral", 0.1)
    
    # 4. العودة إلى القائمة
    await reminder_menu_callback(update, context)


async def reminder_toggle_daily_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تبديل حالة التقرير اليومي (تفعيل/تعطيل).
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. الحصول على الإعدادات الحالية
    settings = await db_get_user_reminder_settings(user_id)
    new_status = not settings.get('daily_stats_reminder', False)
    
    # 2. تحديث الإعدادات
    await db_update_reminder_settings(user_id, daily_stats_reminder=new_status)
    
    # 3. تسجيل الحدث
    await db_save_sentiment_history(user_id, 0, f"reminder_daily_toggle_{new_status}", "neutral", 0.1)
    
    # 4. العودة إلى القائمة
    await reminder_menu_callback(update, context)


async def reminder_toggle_weekly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تبديل حالة التقرير الأسبوعي (تفعيل/تعطيل).
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. الحصول على الإعدادات الحالية
    settings = await db_get_user_reminder_settings(user_id)
    new_status = not settings.get('weekly_report', True)
    
    # 2. تحديث الإعدادات
    await db_update_reminder_settings(user_id, weekly_report=new_status)
    
    # 3. تسجيل الحدث
    await db_save_sentiment_history(user_id, 0, f"reminder_weekly_toggle_{new_status}", "neutral", 0.1)
    
    # 4. العودة إلى القائمة
    await reminder_menu_callback(update, context)


async def reminder_set_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تعيين عدد الأيام قبل انتهاء الاشتراك لإرسال التذكير.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. تعيين حالة الانتظار
    context.user_data['state'] = UserState.WAITING_REMINDER_DAYS
    
    # 2. إرسال رسالة طلب الإدخال
    text = "⏰ أرسل عدد الأيام قبل انتهاء الاشتراك (1-10):\n\nمثال: `3`"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 إلغاء", callback_data=CallbackData.REMINDER_MENU)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def reminder_set_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض قائمة اللغات المتاحة لإشعارات التذكيرات.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. الحصول على اللغة الحالية
    settings = await db_get_user_reminder_settings(user_id)
    current_lang = settings.get('notification_lang', 'ar')
    
    # 2. بناء لوحة المفاتيح
    keyboard = [
        [
            InlineKeyboardButton("🇸🇦 العربية" + (" ✅" if current_lang == 'ar' else ""), callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}ar"),
            InlineKeyboardButton("🇬🇧 English" + (" ✅" if current_lang == 'en' else ""), callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}en")
        ],
        [
            InlineKeyboardButton("🇫🇷 Français" + (" ✅" if current_lang == 'fr' else ""), callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}fr"),
            InlineKeyboardButton("🇹🇷 Türkçe" + (" ✅" if current_lang == 'tr' else ""), callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}tr")
        ],
        [
            InlineKeyboardButton("🇪🇸 Español" + (" ✅" if current_lang == 'es' else ""), callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}es"),
            InlineKeyboardButton("🇩🇪 Deutsch" + (" ✅" if current_lang == 'de' else ""), callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}de")
        ],
        [
            InlineKeyboardButton("🇷🇺 Русский" + (" ✅" if current_lang == 'ru' else ""), callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}ru"),
            InlineKeyboardButton("🇨🇳 中文" + (" ✅" if current_lang == 'zh' else ""), callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}zh")
        ],
        [
            InlineKeyboardButton("🇯🇵 日本語" + (" ✅" if current_lang == 'ja' else ""), callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}ja"),
            InlineKeyboardButton("🇰🇷 한국어" + (" ✅" if current_lang == 'ko' else ""), callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}ko")
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.REMINDER_MENU)
        ]
    ]
    
    text = "🌐 **اختر لغة إشعارات التذكيرات:**\n\nاللغة الحالية: " + SUPPORTED_LANGUAGES.get(current_lang, 'العربية')
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="MarkdownV2")


async def reminder_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تعيين لغة إشعارات التذكيرات.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    lang = query.data.split(":")[-1]
    
    # 1. تحديث اللغة
    await db_update_reminder_settings(user_id, notification_lang=lang)
    
    # 2. تسجيل الحدث
    await db_save_sentiment_history(user_id, 0, f"reminder_lang_changed_{lang}", "neutral", 0.1)
    
    # 3. العودة إلى القائمة
    await reminder_menu_callback(update, context)


# ===================================================================
# دوال قاعدة بيانات التذكيرات (إذا كانت مفقودة)
# ===================================================================

async def db_get_user_reminder_settings(user_id: int) -> dict:
    """
    الحصول على إعدادات التذكيرات للمستخدم من قاعدة البيانات.
    """
    async def _get(conn):
        cur = await conn.execute("""
            SELECT subscription_reminder, daily_stats_reminder, weekly_report,
                   reminder_days_before, last_reminder_sent, notification_lang
            FROM user_reminder_settings WHERE user_id=?
        """, (user_id,))
        row = await cur.fetchone()
        
        if row:
            return {
                'subscription_reminder': row[0] == 1 if row[0] is not None else True,
                'daily_stats_reminder': row[1] == 1 if row[1] is not None else False,
                'weekly_report': row[2] == 1 if row[2] is not None else True,
                'reminder_days_before': row[3] if row[3] is not None else 3,
                'last_reminder_sent': row[4] if row[4] is not None else 0,
                'notification_lang': row[5] if row[5] is not None else 'ar'
            }
        else:
            # إنشاء إعدادات افتراضية
            await conn.execute("""
                INSERT INTO user_reminder_settings 
                (user_id, subscription_reminder, daily_stats_reminder, weekly_report, 
                 reminder_days_before, last_reminder_sent, notification_lang)
                VALUES (?, 1, 0, 1, 3, 0, 'ar')
            """, (user_id,))
            await conn.commit()
            return {
                'subscription_reminder': True,
                'daily_stats_reminder': False,
                'weekly_report': True,
                'reminder_days_before': 3,
                'last_reminder_sent': 0,
                'notification_lang': 'ar'
            }
    return await execute_db(_get)


async def db_update_reminder_settings(user_id: int, **kwargs):
    """
    تحديث إعدادات التذكيرات للمستخدم.
    """
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
            logger.info(f"✅ تم تحديث إعدادات التذكيرات للمستخدم {user_id}: {kwargs}")
    return await execute_db(_update)


async def db_update_last_reminder_sent(user_id: int, reminder_type: str):
    """
    تحديث وقت آخر تذكير تم إرساله للمستخدم.
    """
    async def _update(conn):
        now_timestamp = int(time_module.time())
        await conn.execute("""
            UPDATE user_reminder_settings 
            SET last_reminder_sent = ? 
            WHERE user_id = ?
        """, (now_timestamp, user_id))
        await conn.commit()
        logger.debug(f"✅ تم تحديث آخر تذكير للمستخدم {user_id} ({reminder_type})")
    return await execute_db(_update)


async def db_get_users_needing_reminder() -> list:
    """
    الحصول على قائمة المستخدمين الذين يحتاجون تذكير.
    تعيد قائمة تحتوي على user_id, days_left, notification_lang.
    """
    async def _get(conn):
        now = utc_now()
        users = []
        
        # جلب المستخدمين الذين تنتهي اشتراكاتهم خلال 10 أيام
        cutoff_date = (now + timedelta(days=10)).isoformat()
        cur = await conn.execute("""
            SELECT user_id, subscription_end 
            FROM users 
            WHERE subscription_end IS NOT NULL 
              AND subscription_end <= ? 
              AND banned = 0
        """, (cutoff_date,))
        
        rows = await cur.fetchall()
        
        for user_id, subscription_end_str in rows:
            try:
                end_date = datetime.fromisoformat(subscription_end_str)
                days_left = (end_date - now).days
                
                if days_left < 0:
                    continue
                
                # الحصول على إعدادات التذكيرات للمستخدم
                settings = await db_get_user_reminder_settings(user_id)
                
                # التحقق من تفعيل تذكير الاشتراك
                if not settings.get('subscription_reminder', True):
                    continue
                
                reminder_days = settings.get('reminder_days_before', 3)
                last_sent = settings.get('last_reminder_sent', 0)
                now_timestamp = int(time_module.time())
                
                # تحديد ما إذا كان يحتاج تذكير
                need_reminder = False
                if 0 < days_left <= reminder_days:
                    if last_sent == 0:
                        need_reminder = True
                    elif (now_timestamp - last_sent) > (3 * 24 * 60 * 60):  # 3 أيام
                        need_reminder = True
                
                if need_reminder:
                    users.append({
                        'user_id': user_id,
                        'days_left': days_left,
                        'notification_lang': settings.get('notification_lang', 'ar')
                    })
            except Exception as e:
                logger.debug(f"خطأ في معالجة المستخدم {user_id}: {e}")
                continue
        
        return users
    return await execute_db(_get)
# ===================================================================
# دوال الترجمة (Translation Callbacks) - كاملة ومتطورة
# ===================================================================

async def translation_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض قائمة إعدادات الترجمة.
    تعرض اللغة الحالية مع أزرار لاختيار لغة جديدة أو إيقاف الترجمة.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. الحصول على اللغة الحالية
    current_lang = await get_user_translation_language(user_id)
    
    # 2. بناء النص
    if current_lang == 'off':
        status_text = get_text(user_id, 'translation_status_off')
    else:
        lang_name = SUPPORTED_LANGUAGES.get(current_lang, current_lang)
        status_text = get_text(user_id, 'translation_status_on').format(lang_name)
    
    text = f"🌐 **{get_text(user_id, 'translation_settings')}**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📌 الحالة: {status_text}\n\n"
    text += get_text(user_id, 'translation_how_it_works')
    text += "\n\n**اختر لغة الترجمة:**"
    
    # 3. بناء لوحة المفاتيح
    keyboard = []
    
    # إضافة أزرار اللغات (3 في كل صف)
    lang_list = list(SUPPORTED_LANGUAGES.items())
    for i in range(0, len(lang_list), 3):
        row = []
        for j in range(3):
            if i + j < len(lang_list):
                code, name = lang_list[i + j]
                # إضافة علامة ✅ بجانب اللغة الحالية
                label = f"{name} ✅" if code == current_lang else name
                row.append(InlineKeyboardButton(
                    label,
                    callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}{code}"
                ))
        if row:
            keyboard.append(row)
    
    # إضافة زر إيقاف الترجمة
    keyboard.append([
        InlineKeyboardButton(
            "🚫 " + get_text(user_id, 'translation_off'),
            callback_data=CallbackData.TRANSLATION_OFF
        )
    ])
    
    # إضافة زر الرجوع
    keyboard.append([
        InlineKeyboardButton(get_text(user_id, 'back'), callback_data=CallbackData.BACK)
    ])
    
    # 4. إرسال أو تعديل الرسالة
    if query:
        await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    # 5. تسجيل الحدث
    await db_save_sentiment_history(user_id, 0, "translation_menu_viewed", "neutral", 0.1)


async def translation_off_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    إيقاف الترجمة التلقائية.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. إيقاف الترجمة
    await set_user_translation_language(user_id, 'off')
    
    # 2. تسجيل الحدث
    await db_save_sentiment_history(user_id, 0, "translation_disabled", "neutral", 0.1)
    
    # 3. عرض رسالة التأكيد
    text = get_text(user_id, 'translation_disabled')
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.TRANSLATION_MENU)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def translation_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تعيين لغة الترجمة المختارة.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    lang = query.data.split(":")[-1]
    
    # 1. التحقق من صحة اللغة
    if lang not in SUPPORTED_LANGUAGES:
        await query.answer("❌ لغة غير مدعومة!", show_alert=True)
        return
    
    # 2. تعيين اللغة
    await set_user_translation_language(user_id, lang)
    
    # 3. تسجيل الحدث
    lang_name = SUPPORTED_LANGUAGES.get(lang, lang)
    await db_save_sentiment_history(user_id, 0, f"translation_enabled_{lang}", "positive", 0.3)
    
    # 4. عرض رسالة التأكيد
    text = get_text(user_id, 'translation_enabled').format(lang_name)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.TRANSLATION_MENU)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


# ===================================================================
# دوال قاعدة بيانات الترجمة (إذا كانت مفقودة)
# ===================================================================

async def get_user_translation_language(user_id: int) -> str:
    """
    الحصول على لغة الترجمة للمستخدم من قاعدة البيانات.
    """
    async def _get(conn):
        cur = await conn.execute(
            "SELECT lang FROM user_translation WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] if row and row[0] else 'off'
    lang = await execute_db(_get)
    return lang


async def set_user_translation_language(user_id: int, lang: str):
    """
    تعيين لغة الترجمة للمستخدم في قاعدة البيانات.
    """
    async def _set(conn):
        await conn.execute("""
            INSERT OR REPLACE INTO user_translation (user_id, lang)
            VALUES (?, ?)
        """, (user_id, lang))
        await conn.commit()
        logger.info(f"✅ تم تعيين لغة الترجمة للمستخدم {user_id} إلى {lang}")
    await execute_db(_set)


async def translate_text(text: str, target_lang: str) -> str:
    """
    ترجمة نص إلى اللغة المستهدفة باستخدام Google Translate.
    """
    if not text or target_lang == 'off' or target_lang == 'ar':
        return text
    
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='auto', target=target_lang)
        translated = translator.translate(text)
        if translated:
            return translated
    except Exception as e:
        logger.error(f"فشل الترجمة إلى {target_lang}: {e}")
        # محاولة استخدام MyMemory كبديل
        try:
            from deep_translator import MyMemoryTranslator
            translator = MyMemoryTranslator(source='auto', target=target_lang)
            translated = translator.translate(text)
            if translated:
                return translated
        except Exception as e2:
            logger.error(f"فشل الترجمة عبر MyMemory: {e2}")
    
    return text


# ===================================================================
# دوال الاشتراك والتجربة (إذا كانت مفقودة)
# ===================================================================

async def trial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تفعيل التجربة المجانية للمستخدم (30 يوم).
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. التحقق من استخدام التجربة سابقاً
    if await db_has_used_trial(user_id):
        text = get_text(user_id, 'trial_used')
        await query.edit_message_text(text, parse_mode="MarkdownV2")
        return
    
    # 2. التحقق من وجود اشتراك فعال
    if await db_has_active_subscription(user_id):
        text = get_text(user_id, 'already_subscribed')
        await query.edit_message_text(text, parse_mode="MarkdownV2")
        return
    
    # 3. تفعيل التجربة
    await db_activate_trial(user_id)
    
    # 4. تسجيل الحدث
    await db_save_sentiment_history(user_id, 0, "trial_activated", "positive", 0.9)
    
    # 5. عرض رسالة التأكيد
    text = get_text(user_id, 'trial')
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def subscribe_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض قائمة الاشتراكات المتاحة.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. التحقق من وجود اشتراك فعال
    if await db_has_active_subscription(user_id):
        days = await db_get_subscription_days_left(user_id)
        text = f"✅ اشتراكك مفعل، متبقي **{days}** يوم\nشكراً لدعمك ❤️"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")
        return
    
    # 2. عرض خطط الاشتراك
    text = get_text(user_id, 'subscribe')
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐ 1 يوم - 5 نجوم", callback_data=CallbackData.BUY_SUBSCRIPTION_1),
            InlineKeyboardButton("⭐ 2 يوم - 9 نجوم", callback_data=CallbackData.BUY_SUBSCRIPTION_2)
        ],
        [
            InlineKeyboardButton("⭐ شهر (30 يوم) - 50 نجمة", callback_data=CallbackData.BUY_SUBSCRIPTION_30),
            InlineKeyboardButton("⭐ 3 أشهر (90 يوم) - 120 نجمة", callback_data=CallbackData.BUY_SUBSCRIPTION_90)
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")
    await db_save_sentiment_history(user_id, 0, "subscribe_menu_viewed", "neutral", 0.1)


async def buy_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, days: int, price: int, title: str):
    """
    شراء اشتراك عبر الدفع بالنجوم.
    """
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
        await db_save_sentiment_history(user_id, 0, f"subscription_payment_started_{days}", "positive", 0.4)
    except Exception as e:
        error_msg = str(e).lower()
        if "stars" in error_msg or "currency" in error_msg:
            text = "❌ الدفع بالنجوم غير مفعل حالياً.\n\n💡 **بدائل:**\n• استخدم `/trial` للحصول على 30 يوم مجاناً\n• تواصل مع المطور لتفعيل الدفع"
            await query.edit_message_text(text, parse_mode="MarkdownV2")
        else:
            await query.edit_message_text(f"❌ خطأ: {str(e)[:200]}", parse_mode="MarkdownV2")


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
    """شراء اشتراك شهر (30 يوم)"""
    if update.callback_query:
        await update.callback_query.answer()
    await buy_subscription_callback(update, context, 30, 50, "اشتراك شهر")


async def buy_subscription_90_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شراء اشتراك 3 أشهر (90 يوم)"""
    if update.callback_query:
        await update.callback_query.answer()
    await buy_subscription_callback(update, context, 90, 120, "اشتراك 3 أشهر")


# ===================================================================
# دوال المطور والتحديثات
# ===================================================================

async def developer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض معلومات المطور.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    text = """👨‍💻 **المطور**
━━━━━━━━━━━━━━━━━━━━━━

**ريلاكس مانيجر** - الإصدار 22.0.0

📌 **المطور:** @RelaxMgr
📌 **القناة:** @RelaxMgrr
📌 **المجموعة:** @RelaxMgrGroup

🧠 **ميزات البوت:**
• نظام تعلم ذكي (AI Learning)
• تحليل مشاعر متقدم
• إدارة القنوات والمجموعات
• نظام إحالات ومكافآت
• نظام مسابقات
• دعم 15 لغة

🔧 **تقنيات مستخدمة:**
• Python 3.12
• python-telegram-bot v22
• SQLite + AIOSQLite
• Argon2 + Fernet (تشفير)

📊 **إحصائيات البوت:**
• تم تطويره بالكامل بواسطة @RelaxMgr
• أكثر من 35+ جدول في قاعدة البيانات
• أكثر من 200 رد تلقائي مدمج
• أكثر من 180 زر تفاعلي

💡 **للتواصل:**
• @RelaxMgr (خاص)
• @RelaxMgrr (قناة التحديثات)

شكراً لاستخدامك البوت! ❤️"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)


async def updates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض آخر التحديثات وقناة التحديثات.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    channel = await db_get_updates_channel()
    
    if channel:
        text = get_text(user_id, 'updates_text')
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 القناة", url=f"https://t.me/{channel}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        if query:
            await safe_edit_markdown(query, text, reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
    else:
        text = "📢 **لا توجد قناة تحديثات محددة.**\n\nيمكن للمشرف تعيين قناة التحديثات باستخدام الأمر:\n`/set_update_channel @channel`"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        if query:
            await safe_edit_markdown(query, text, reply_markup=keyboard)
        else:
            await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
    
    await db_save_sentiment_history(user_id, 0, "updates_viewed", "neutral", 0.1)
# ===================================================================
# دوال المسابقات (Contests Callbacks) - كاملة ومتطورة
# ===================================================================

async def contests_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض قائمة المسابقات النشطة.
    تعرض جميع المسابقات المتاحة للمشاركة مع أزرار الانضمام.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. جلب المسابقات النشطة
    contests = await db_get_active_contests_with_participants(limit=10)
    
    if not contests:
        text = "📭 **لا توجد مسابقات نشطة حالياً.**\n\nتابع القناة لمعرفة المسابقات القادمة 📢"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏆 الفائزون السابقون", callback_data=CallbackData.CONTEST_WINNERS)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        await safe_edit_markdown(query, text, reply_markup=keyboard)
        return
    
    # 2. بناء النص
    text = "🏆 **المسابقات النشطة**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    keyboard = []
    
    for contest in contests:
        if len(contest) < 6:
            continue
        
        cid = contest[0]
        title = contest[1] or "بدون عنوان"
        desc = contest[2] or ""
        prize = contest[3] or "غير محددة"
        end_date = contest[4]
        participants = contest[5] if len(contest) > 5 else 0
        contest_type = contest[6] if len(contest) > 6 else 'raffle'
        
        # حساب الوقت المتبقي
        try:
            end_dt = datetime.fromisoformat(end_date)
            days_left = (end_dt - utc_now()).days
            if days_left > 0:
                time_left = f"⏳ متبقي {days_left} يوم"
            else:
                time_left = "🔴 انتهت"
        except:
            time_left = "📅 تاريخ غير صحيح"
            days_left = 0
        
        # التحقق من مشاركة المستخدم
        participated = await db_get_user_participation(user_id, cid)
        status_icon = "✅" if participated else "📝"
        
        # أيقونة حسب نوع المسابقة
        type_icon = {
            'quiz': '📝',
            'raffle': '🎲',
            'vote': '🗳️',
            'survey': '📊'
        }.get(contest_type, '📤')
        
        # عرض المسابقة
        text += f"📌 **{title}** {type_icon}\n"
        text += f"📝 {(desc)[:100]}{'...' if len(desc) > 100 else ''}\n"
        text += f"🎁 الجائزة: {prize}\n"
        text += f"👥 المشاركون: {participants}\n"
        text += f"🕐 {time_left}\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        
        # إضافة زر المشاركة إذا كانت المسابقة نشطة والمستخدم غير مشارك
        if not participated and days_left > 0:
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_icon} شارك في {title[:20]}",
                    callback_data=f"{CallbackData.CONTEST_JOIN_PREFIX}{cid}"
                )
            ])
    
    # 3. أزرار إضافية
    keyboard.append([
        InlineKeyboardButton("🏆 الفائزون السابقون", callback_data=CallbackData.CONTEST_WINNERS)
    ])
    keyboard.append([
        InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)
    ])
    
    # 4. إرسال أو تعديل الرسالة
    await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    await db_save_sentiment_history(user_id, 0, "contests_menu_viewed", "neutral", 0.1)


async def contest_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    المشاركة في مسابقة.
    للمسابقات من نوع quiz، تطلب إجابة من المستخدم.
    للمسابقات من نوع raffle، تسجل المشاركة مباشرة.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    contest_id = int(query.data.split(":")[-1])
    
    # 1. جلب معلومات المسابقة
    contest = await db_get_contest(contest_id)
    if not contest:
        await query.edit_message_text("❌ المسابقة غير موجودة!")
        return
    
    # 2. التحقق من حالة المسابقة
    if contest['status'] != 'active':
        await query.edit_message_text("❌ هذه المسابقة انتهت!")
        return
    
    # 3. التحقق من المشاركة المسبقة
    if await db_get_user_participation(user_id, contest_id):
        await query.answer("❌ أنت مشترك بالفعل!", show_alert=True)
        return
    
    # 4. معالجة أنواع المسابقات المختلفة
    if contest.get('contest_type') == 'quiz':
        # مسابقة اختبارية - تطلب إجابة
        context.user_data['contest_join_id'] = contest_id
        context.user_data['state'] = UserState.WAITING_CONTEST_ANSWER
        
        text = f"📝 **{contest['title']}**\n\n"
        text += f"{contest['description']}\n\n"
        text += "✏️ أرسل إجابتك، أو اكتب `/skip` للتخطي.\n"
        text += f"⏳ الوقت المتبقي: {_get_time_left(contest['end_date'])}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data=CallbackData.CONTESTS_MENU)]
        ])
        
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")
    else:
        # مسابقة سحب/تصويت - تسجيل مباشر
        success = await db_participate_in_contest(user_id, contest_id, "")
        
        if success:
            await db_save_sentiment_history(user_id, contest_id, f"contest_joined_{contest_id}", "positive", 0.5)
            text = f"✅ **تم تسجيل مشاركتك في المسابقة بنجاح!**\n\n"
            text += f"📌 {contest['title']}\n"
            text += f"🎁 الجائزة: {contest['prize']}\n"
            text += f"🍀 حظاً موفقاً!"
        else:
            text = "❌ فشل التسجيل في المسابقة. يرجى المحاولة مرة أخرى."
        
        await query.edit_message_text(text, parse_mode="MarkdownV2")
        await contests_menu_callback(update, context)


async def contest_winners_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض الفائزين السابقين في المسابقات.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. جلب الفائزين السابقين
    winners = await db_get_contest_winners(limit=10)
    
    if not winners:
        text = "📭 **لا توجد فائزين سابقين.**\n\nكن أول من يفوز في مسابقة! 🏆"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.CONTESTS_MENU)]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")
        return
    
    # 2. بناء النص
    text = "🏆 **الفائزون السابقون**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for idx, winner in enumerate(winners, 1):
        try:
            user = await context.bot.get_chat(winner['winner_id'])
            name = user.first_name or str(winner['winner_id'])
        except:
            name = str(winner['winner_id'])
        
        # تنسيق التاريخ
        try:
            dt = datetime.fromisoformat(winner['announced_at'])
            date_str = dt.strftime("%Y-%m-%d")
        except:
            date_str = "?"
        
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        text += f"{medal} **{winner['title']}**\n"
        text += f"👤 {name}\n"
        text += f"🎁 {winner['prize']}\n"
        text += f"📅 {date_str}\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.CONTESTS_MENU)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")
    await db_save_sentiment_history(user_id, 0, "contest_winners_viewed", "neutral", 0.1)


async def contests_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    العودة من المسابقات إلى القائمة الرئيسية.
    """
    await main_menu_callback(update, context)


# ===================================================================
# دوال المسابقات للأدمن (Admin Contest Callbacks)
# ===================================================================

async def admin_create_contest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    إنشاء مسابقة جديدة من لوحة الأدمن.
    """
    await create_contest_command_handler(update, context)


async def admin_declare_winner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    إعلان فائز في مسابقة من لوحة الأدمن.
    """
    await declare_winner_command_handler(update, context)


async def admin_del_contest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    حذف مسابقة من لوحة الأدمن.
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    contest_id = int(query.data.split(":")[-1])
    
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    success = await db_delete_contest(contest_id, user_id)
    if success:
        await db_save_sentiment_history(user_id, 0, f"delete_contest_{contest_id}", "neutral", 0)
        await query.edit_message_text("✅ تم حذف المسابقة.")
    else:
        await query.edit_message_text("❌ فشل حذف المسابقة.")
    
    await admin_panel_callback(update, context)


# ===================================================================
# دوال قاعدة بيانات المسابقات (إذا كانت مفقودة)
# ===================================================================

async def db_get_active_contests_with_participants(limit: int = 10) -> list:
    """
    جلب المسابقات النشطة مع عدد المشاركين.
    """
    async def _get(conn):
        now = utc_now().isoformat()
        cur = await conn.execute("""
            SELECT 
                c.id, 
                c.title, 
                c.description, 
                c.prize, 
                c.end_date,
                COALESCE((SELECT COUNT(*) FROM contest_participants cp WHERE cp.contest_id = c.id), 0) as participants,
                c.contest_type
            FROM contests c
            WHERE c.status = 'active' AND c.end_date > ?
            ORDER BY c.end_date ASC
            LIMIT ?
        """, (now, limit))
        return await cur.fetchall()
    return await execute_db(_get)


async def db_get_user_participation(user_id: int, contest_id: int) -> Optional[dict]:
    """
    التحقق من مشاركة المستخدم في مسابقة معينة.
    """
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


async def db_get_contest(contest_id: int) -> Optional[dict]:
    """
    جلب معلومات مسابقة معينة.
    """
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT 
                id, title, description, prize, end_date, 
                status, winner_id, creator_id, created_at, contest_type
            FROM contests 
            WHERE id = ?
        """, (contest_id,))
        row = await cur.fetchone()
        if row:
            return dict(row)
        return None
    return await execute_db(_get)


async def db_participate_in_contest(user_id: int, contest_id: int, answer: str = "") -> bool:
    """
    تسجيل مشاركة مستخدم في مسابقة.
    """
    async def _participate(conn):
        try:
            await conn.execute("""
                INSERT INTO contest_participants (user_id, contest_id, answer, joined_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, contest_id, answer, utc_now_iso()))
            await conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    return await execute_db(_participate)


async def db_get_contest_winners(limit: int = 10) -> list:
    """
    جلب الفائزين السابقين.
    """
    async def _get(conn):
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT 
                c.id, 
                c.title, 
                c.prize, 
                cw.winner_id, 
                cw.announced_at
            FROM contest_winners cw
            JOIN contests c ON cw.contest_id = c.id
            ORDER BY cw.announced_at DESC 
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in await cur.fetchall()]
    return await execute_db(_get)


async def db_delete_contest(contest_id: int, user_id: int) -> bool:
    """
    حذف مسابقة.
    """
    async def _delete(conn):
        # التحقق من صلاحية المستخدم
        cur = await conn.execute(
            "SELECT creator_id FROM contests WHERE id = ?",
            (contest_id,)
        )
        row = await cur.fetchone()
        if row and (row[0] == user_id or await is_bot_admin(user_id)):
            # حذف المشاركين أولاً
            await conn.execute(
                "DELETE FROM contest_participants WHERE contest_id = ?",
                (contest_id,)
            )
            # حذف المسابقة
            await conn.execute(
                "DELETE FROM contests WHERE id = ?",
                (contest_id,)
            )
            await conn.commit()
            return True
        return False
    return await execute_db(_delete)


async def db_get_random_participant(contest_id: int) -> Optional[int]:
    """
    الحصول على مشارك عشوائي في مسابقة (للسحب العشوائي).
    """
    async def _get(conn):
        cur = await conn.execute(
            "SELECT user_id FROM contest_participants WHERE contest_id = ? ORDER BY RANDOM() LIMIT 1",
            (contest_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)


async def db_set_contest_winner(contest_id: int, winner_id: int) -> bool:
    """
    تعيين فائز في مسابقة.
    """
    async def _set(conn):
        await conn.execute("""
            UPDATE contests 
            SET status = 'finished', winner_id = ?, updated_at = ?
            WHERE id = ?
        """, (winner_id, utc_now_iso(), contest_id))
        
        await conn.execute("""
            INSERT INTO contest_winners (contest_id, winner_id, announced_at)
            VALUES (?, ?, ?)
        """, (contest_id, winner_id, utc_now_iso()))
        
        await conn.commit()
        return True
    return await execute_db(_set)


def _get_time_left(end_date_str: str) -> str:
    """
    حساب الوقت المتبقي حتى تاريخ معين (دالة مساعدة).
    """
    try:
        end_date = datetime.fromisoformat(end_date_str)
        now = utc_now()
        diff = end_date - now
        
        if diff.total_seconds() <= 0:
            return "انتهت 🕐"
        
        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        
        if days > 0:
            return f"{days} يوم و {hours} ساعة"
        elif hours > 0:
            return f"{hours} ساعة و {minutes} دقيقة"
        else:
            return f"{minutes} دقيقة"
    except:
        return "غير محدد"
# ===================================================================
# دوال لوحة الأدمن (Admin Panel Callbacks) - كاملة ومتطورة
# ===================================================================

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    عرض لوحة تحكم الأدمن الرئيسية.
    تعرض جميع خيارات الإدارة المتاحة للمشرفين.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    # 1. التحقق من صلاحية المستخدم
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    # 2. بناء لوحة المفاتيح
    keyboard = get_admin_keyboard(user_id)
    
    # 3. إضافة إحصائيات سريعة
    total_users, banned_users, total_posts, total_groups, total_channels = await db_stats()
    
    text = f"""👑 **لوحة تحكم الأدمن**
━━━━━━━━━━━━━━━━━━━━━━
📊 **إحصائيات سريعة:**
👥 المستخدمين: {total_users}
⛔ المحظورين: {banned_users}
📝 المنشورات: {total_posts}
👥 المجموعات: {total_groups}
📡 القنوات: {total_channels}
━━━━━━━━━━━━━━━━━━━━━━
📌 اختر الإجراء المطلوب:"""
    
    # 4. إرسال أو تعديل الرسالة
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)
    
    await db_save_sentiment_history(user_id, 0, "admin_panel_viewed", "neutral", 0.1)


# ===================================================================
# دوال إدارة المستخدمين
# ===================================================================

async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة جميع المستخدمين"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    users = await db_get_all_users()
    
    text = "👥 **قائمة المستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    if not users:
        text += "📭 لا يوجد مستخدمين."
    else:
        for uid, banned, username, first_name in users[:50]:
            try:
                name = first_name or username or str(uid)
            except:
                name = str(uid)
            status = "⛔ محظور" if banned else "✅ نشط"
            text += f"• {name} (`{uid}`) - {status}\n"
        if len(users) > 50:
            text += f"\n... و {len(users)-50} مستخدمين آخرين"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_banned_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة المستخدمين المحظورين"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    users = await db_get_all_users()
    banned_users = [u for u in users if u[1] == 1]
    
    text = "⛔ **المستخدمين المحظورين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    if not banned_users:
        text += "📭 لا يوجد مستخدمين محظورين."
    else:
        for uid, banned, username, first_name in banned_users:
            try:
                name = first_name or username or str(uid)
            except:
                name = str(uid)
            text += f"• {name} (`{uid}`)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ إلغاء حظر الكل", callback_data=CallbackData.ADMIN_UNBAN_ALL_USERS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_unban_all_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء حظر جميع المستخدمين"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    async def _unban_all(conn):
        await conn.execute("UPDATE users SET banned=0")
        await conn.commit()
    
    await execute_db(_unban_all)
    await db_save_sentiment_history(user_id, 0, "unban_all_users", "positive", 0.3)
    await query.edit_message_text("✅ تم إلغاء حظر جميع المستخدمين.")
    await admin_panel_callback(update, context)


# ===================================================================
# دوال إدارة القنوات
# ===================================================================

async def admin_all_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع قنوات المستخدمين"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    channels = await db_all_users_channels(limit=100)
    
    text = "📡 **جميع قنوات المستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    if not channels:
        text += "📭 لا توجد قنوات."
    else:
        for ch_user_id, ch_id, ch_tele_id, ch_name, banned in channels:
            status = "⛔ محظورة" if banned else "✅ نشطة"
            text += f"• {ch_name} (`{ch_tele_id}`) - المستخدم: {ch_user_id} - {status}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_banned_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القنوات المحظورة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    channels = await db_all_users_channels(only_banned=True, limit=100)
    
    text = "⛔ **القنوات المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    if not channels:
        text += "📭 لا توجد قنوات محظورة."
    else:
        for ch_user_id, ch_id, ch_tele_id, ch_name, banned in channels:
            text += f"• {ch_name} (`{ch_tele_id}`) - المستخدم: {ch_user_id}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❤️ تنشيط الكل", callback_data=CallbackData.ADMIN_ACTIVATE_ALL_CHANNELS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_activate_all_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنشيط جميع القنوات المحظورة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    async def _activate_all(conn):
        await conn.execute("UPDATE user_channels SET banned=0")
        await conn.commit()
    
    await execute_db(_activate_all)
    await db_save_sentiment_history(user_id, 0, "activate_all_channels", "positive", 0.3)
    await query.edit_message_text("✅ تم تنشيط جميع القنوات.")
    await admin_panel_callback(update, context)


# ===================================================================
# دوال إدارة المجموعات
# ===================================================================

async def admin_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع المجموعات"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    groups = await db_get_all_groups()
    
    text = "👥 **جميع المجموعات**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    if not groups:
        text += "📭 لا توجد مجموعات."
    else:
        for gid, gname, username, added_by, added_at, banned in groups:
            status = "⛔ محظورة" if banned else "✅ نشطة"
            text += f"• {gname} (`{gid}`) - {status}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_banned_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المجموعات المحظورة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    groups = await db_get_all_groups(only_banned=True)
    
    text = "⛔ **المجموعات المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    if not groups:
        text += "📭 لا توجد مجموعات محظورة."
    else:
        for gid, gname, username, added_by, added_at, banned in groups:
            text += f"• {gname} (`{gid}`)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ إلغاء حظر الكل", callback_data=CallbackData.ADMIN_UNBAN_ALL_GROUPS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_unban_all_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء حظر جميع المجموعات"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    async def _unban_all(conn):
        await conn.execute("UPDATE bot_groups SET banned=0")
        await conn.commit()
    
    await execute_db(_unban_all)
    await db_save_sentiment_history(user_id, 0, "unban_all_groups", "positive", 0.3)
    await query.edit_message_text("✅ تم إلغاء حظر جميع المجموعات.")
    await admin_panel_callback(update, context)


# ===================================================================
# دوال إدارة قنوات البوت
# ===================================================================

async def admin_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قنوات البوت"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    channels = await db_get_all_bot_channels()
    
    text = "📢 **قنوات البوت**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    if not channels:
        text += "📭 لا توجد قنوات بوت."
    else:
        for cid, cname, added_by, added_at, banned in channels:
            status = "⛔ محظورة" if banned else "✅ نشطة"
            text += f"• {cname} (`{cid}`) - {status}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_banned_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قنوات البوت المحظورة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    channels = await db_get_all_bot_channels(only_banned=True)
    
    text = "⛔ **قنوات البوت المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    if not channels:
        text += "📭 لا توجد قنوات بوت محظورة."
    else:
        for cid, cname, added_by, added_at, banned in channels:
            text += f"• {cname} (`{cid}`)\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ إلغاء حظر الكل", callback_data=CallbackData.ADMIN_UNBAN_ALL_BOT_CHANNELS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_unban_all_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء حظر جميع قنوات البوت"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    async def _unban_all(conn):
        await conn.execute("UPDATE bot_channels SET banned=0")
        await conn.commit()
    
    await execute_db(_unban_all)
    await db_save_sentiment_history(user_id, 0, "unban_all_bot_channels", "positive", 0.3)
    await query.edit_message_text("✅ تم إلغاء حظر جميع قنوات البوت.")
    await admin_panel_callback(update, context)


# ===================================================================
# دوال مراقبة وإدارة المشرفين
# ===================================================================

async def admin_monitor_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مراقبة المستخدمين"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    users = await db_get_all_users()
    active_users = [u for u in users if u[1] == 0]
    
    text = f"📊 **مراقبة المستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"👥 إجمالي المستخدمين: {len(users)}\n"
    text += f"✅ النشطاء: {len(active_users)}\n"
    text += f"⛔ المحظورين: {len(users) - len(active_users)}\n"
    
    # جلب إحصائيات التعلم
    learning_stats = await db_get_learning_stats()
    text += f"\n🧠 **إحصائيات التعلم:**\n"
    text += f"📝 أنماط التعلم: {learning_stats.get('patterns', 0)}\n"
    text += f"📊 سجل المشاعر: {learning_stats.get('sentiment_history', 0)}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_add_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة مشرف بوت جديد"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_ADMIN_ID_ADD
    await query.edit_message_text("📝 **إضافة مشرف بوت**\n\nأرسل معرف المستخدم (user_id) لإضافته كمشرف:\nمثال: `123456789`", parse_mode="MarkdownV2")


async def admin_remove_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إزالة مشرف بوت"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_ADMIN_ID_REMOVE
    await query.edit_message_text("📝 **إزالة مشرف بوت**\n\nأرسل معرف المستخدم (user_id) لإزالته من المشرفين:\nمثال: `123456789`", parse_mode="MarkdownV2")


# ===================================================================
# دوال النظام والإحصائيات
# ===================================================================

async def admin_ram_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض حالة الذاكرة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    ram = get_ram_usage()
    
    text = f"🖥️ **حالة الرام**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📊 الإجمالي: {ram['total']} جيجابايت\n"
    text += f"📊 المستخدم: {ram['used']} جيجابايت\n"
    text += f"📊 المتاح: {ram.get('available', 0)} جيجابايت\n"
    text += f"📊 النسبة: {ram['percent']}%\n"
    
    # إضافة حالة البوت
    text += f"\n🤖 **حالة البوت:**\n"
    text += f"⏱️ وقت التشغيل: {int(time_module.time() - start_time)} ثانية\n"
    text += f"🔄 المهام النشطة: {task_manager.get_task_count() if hasattr(task_manager, 'get_task_count') else '?'}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات عامة"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    total, banned, posts, groups, channels = await db_stats()
    
    text = f"📊 **إحصائيات عامة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"👥 المستخدمين: {total}\n"
    text += f"⛔ المحظورين: {banned}\n"
    text += f"📝 المنشورات غير المنشورة: {posts}\n"
    text += f"👥 المجموعات: {groups}\n"
    text += f"📡 القنوات: {channels}\n"
    
    # جلب إحصائيات التعلم
    learning_stats = await db_get_learning_stats()
    text += f"\n🧠 **نظام التعلم:**\n"
    text += f"📝 أنماط متعلمة: {learning_stats.get('patterns', 0)}\n"
    text += f"📊 سجل المشاعر: {learning_stats.get('sentiment_history', 0)}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_metrics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض مقاييس الأداء"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    ram = get_ram_usage()
    
    text = f"📈 **مقاييس الأداء**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"⏱️ وقت التشغيل: {int(time_module.time() - start_time)} ثانية\n"
    text += f"💾 استخدام الذاكرة: {ram['percent']}%\n"
    
    # عدد المستخدمين النشطين في آخر ساعة
    active_users = len(user_points_last_hour)
    text += f"👤 مستخدمين نشطين (آخر ساعة): {active_users}\n"
    
    # حجم قاعدة البيانات
    try:
        db_size = os.path.getsize(DB_PATH) / (1024 * 1024)
        text += f"📁 حجم قاعدة البيانات: {db_size:.2f} ميجابايت\n"
    except:
        pass
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


# ===================================================================
# دوال النسخ الاحتياطي
# ===================================================================

async def admin_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء نسخة احتياطية"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    await query.edit_message_text("⏳ جاري إنشاء نسخة احتياطية...")
    
    try:
        backup_file = await create_backup()
        await db_save_sentiment_history(user_id, 0, "admin_backup_created", "positive", 0.3)
        await query.edit_message_text(f"✅ **تم إنشاء النسخة الاحتياطية:**\n\n📁 `{backup_file.name}`\n📅 {mecca_now().strftime('%Y-%m-%d %H:%M')}")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل إنشاء النسخة: {str(e)[:200]}")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    await query.edit_message_reply_markup(reply_markup=keyboard)


async def admin_restore_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استعادة نسخة احتياطية"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    backups = await list_backups()
    if not backups:
        await query.edit_message_text("📭 لا توجد نسخ احتياطية.")
        return
    
    keyboard = []
    for backup in backups[:10]:
        keyboard.append([
            InlineKeyboardButton(
                backup.name,
                callback_data=f"{CallbackData.ADMIN_RESTORE_BACKUP_SELECT_PREFIX}{backup.name}"
            )
        ])
    keyboard.append([
        InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)
    ])
    
    await query.edit_message_text("🔄 **اختر النسخة للاستعادة:**", reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_restore_backup_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اختيار نسخة احتياطية للاستعادة"""
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
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، استعادة", callback_data=f"confirm_restore:{backup_name}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data=CallbackData.ADMIN_RESTORE_BACKUP)]
    ])
    
    await query.edit_message_text(
        f"⚠️ **تأكيد الاستعادة**\n\nالملف: `{backup_name}`\nسيتم استبدال قاعدة البيانات الحالية!\nهل أنت متأكد؟",
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )


async def admin_backup_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعدادات النسخ الاحتياطي"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    auto_backup = await db_get_auto_backup()
    status = "🟢 مفعل" if auto_backup else "🔴 معطل"
    
    text = f"⚙️ **إعدادات النسخ الاحتياطي**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📌 النسخ التلقائي: {status}\n"
    text += f"📁 عدد النسخ المحفوظة: {MAX_BACKUPS}\n"
    text += f"☁️ التخزين السحابي: {'🟢 مفعل' if CLOUD_BACKUP_ENABLED else '🔴 معطل'}\n"
    
    # آخر نسخ احتياطي
    last_backup = await db_get_last_backup_time()
    if last_backup:
        try:
            dt = datetime.fromisoformat(last_backup)
            text += f"🕐 آخر نسخ: {dt.strftime('%Y-%m-%d %H:%M')}\n"
        except:
            pass
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'🔄 تعطيل' if auto_backup else '✅ تفعيل'} التلقائي", callback_data=CallbackData.ADMIN_TOGGLE_AUTO_BACKUP)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_toggle_auto_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تبديل حالة النسخ الاحتياطي التلقائي"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    current = await db_get_auto_backup()
    new_status = not current
    await db_set_auto_backup(new_status)
    
    await db_save_sentiment_history(user_id, 0, f"auto_backup_toggle_{new_status}", "neutral", 0.1)
    await query.answer(f"✅ تم {'تفعيل' if new_status else 'تعطيل'} النسخ التلقائي")
    await admin_backup_settings_callback(update, context)


async def admin_change_interval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغيير وقت النشر العام"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['admin_interval'] = True
    context.user_data['state'] = UserState.WAITING_INTERVAL_MINUTES
    await query.edit_message_text("⏱️ **تغيير وقت النشر العام**\n\nأرسل الوقت بالدقائق:\nمثال: `12` (يعني كل 12 دقيقة)", parse_mode="MarkdownV2")


# ===================================================================
# دوال التحديثات والإعلانات
# ===================================================================

async def admin_send_update_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نشر تحديث في قناة التحديثات"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_UPDATE_TEXT
    await query.edit_message_text("📢 **نشر تحديث**\n\nأرسل نص التحديث الذي تريد نشره في قناة التحديثات:")


async def admin_set_update_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين قناة التحديثات"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_UPDATE_CHANNEL
    await query.edit_message_text("📢 **تعيين قناة التحديثات**\n\nأرسل معرف القناة:\nمثال: `@my_channel` أو `-100123456789`")


async def admin_show_update_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قناة التحديثات الحالية"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    channel = await db_get_updates_channel()
    if channel:
        text = f"📢 **قناة التحديثات الحالية:**\n\n@{channel}"
        try:
            chat = await context.bot.get_chat(f"@{channel}")
            text += f"\n📌 الاسم: {chat.title}"
        except:
            pass
    else:
        text = "📢 **لا توجد قناة تحديثات محددة.**"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_UPDATES)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_updates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لوحة التحديثات"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    text = "🔄 **لوحة التحديثات**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإجراء المطلوب:"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 نشر تحديث", callback_data=CallbackData.ADMIN_SEND_UPDATE)],
        [InlineKeyboardButton("⚙️ تعيين قناة التحديثات", callback_data=CallbackData.ADMIN_SET_UPDATE_CHANNEL)],
        [InlineKeyboardButton("📢 عرض القناة الحالية", callback_data=CallbackData.ADMIN_SHOW_UPDATE_CHANNEL)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


# ===================================================================
# دوال الاشتراك الإجباري
# ===================================================================

async def admin_force_subscribe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعدادات الاشتراك الإجباري"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    enabled = await db_get_force_subscribe_status()
    channel = await db_get_force_subscribe_channel()
    
    status = "🟢 مفعل" if enabled else "🔴 معطل"
    channel_text = f"@{channel}" if channel else "غير محدد"
    
    text = f"🔒 **الاشتراك الإجباري**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📌 الحالة: {status}\n"
    text += f"📢 القناة: {channel_text}\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'🔄 تعطيل' if enabled else '✅ تفعيل'}", callback_data=CallbackData.ADMIN_FORCE_SUBSCRIBE)],
        [InlineKeyboardButton("⚙️ تعيين القناة", callback_data=CallbackData.ADMIN_SET_FORCE_CHANNEL)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_set_force_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين قناة الاشتراك الإجباري"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_FORCE_CHANNEL
    await query.edit_message_text("📢 **تعيين قناة الاشتراك الإجباري**\n\nأرسل معرف القناة:\nمثال: `@my_channel`")


# ===================================================================
# دوال البث والإرسال
# ===================================================================

async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة لجميع المستخدمين"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_BROADCAST
    await query.edit_message_text("📨 **إرسال رسالة لجميع المستخدمين**\n\nأرسل الرسالة التي تريد إرسالها:")


async def admin_confirm_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد إرسال البث"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    broadcast_text = context.user_data.get('broadcast_text')
    if not broadcast_text:
        await query.edit_message_text("❌ لا توجد رسالة للإرسال.")
        return
    
    users = await db_get_all_users()
    active_users = [u[0] for u in users if u[1] == 0]
    
    if not active_users:
        await query.edit_message_text("📭 لا يوجد مستخدمين نشطين.")
        return
    
    await query.edit_message_text(f"⏳ جاري إرسال الرسالة إلى {len(active_users)} مستخدم...")
    
    success = 0
    failed = 0
    for uid in active_users:
        try:
            await context.bot.send_message(chat_id=uid, text=broadcast_text)
            success += 1
        except:
            failed += 1
        await asyncio.sleep(0.1)
    
    await db_save_sentiment_history(user_id, 0, f"broadcast_sent_{success}", "positive", 0.4)
    await query.edit_message_text(
        f"📨 **نتائج الإرسال**\n━━━━━━━━━━━━━━━━━━━━━━\n✅ نجح: {success}\n❌ فشل: {failed}"
    )
    context.user_data.pop('broadcast_text', None)
    await admin_panel_callback(update, context)


# ===================================================================
# دوال التذاكر (دعم)
# ===================================================================

async def admin_support_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تذاكر الدعم"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    tickets = await db_get_all_tickets(limit=20)
    
    if not tickets:
        await query.edit_message_text("📭 لا توجد تذاكر.")
        return
    
    text = "📋 **تذاكر الدعم**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for tid, uid, username, msg, ticket_num, status, created_at in tickets:
        text += f"• #{ticket_num} - المستخدم: {uid}\n"
        text += f"  الحالة: {status}\n"
        text += f"  الرسالة: {msg[:50]}...\n"
        text += f"  🕐 {created_at[:16]}\n\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ حذف جميع التذاكر", callback_data=CallbackData.ADMIN_DELETE_ALL_TICKETS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_delete_all_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب تأكيد حذف جميع التذاكر"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم، حذف الكل", callback_data=CallbackData.ADMIN_CONFIRM_DELETE_TICKETS)],
        [InlineKeyboardButton("❌ إلغاء", callback_data=CallbackData.ADMIN_SUPPORT_TICKETS)]
    ])
    
    await query.edit_message_text(
        "⚠️ **تأكيد حذف جميع التذاكر**\n\nسيتم حذف جميع تذاكر الدعم نهائياً!\nهل أنت متأكد؟",
        reply_markup=keyboard,
        parse_mode="MarkdownV2"
    )


async def admin_confirm_delete_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تأكيد حذف جميع التذاكر"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    await db_delete_all_tickets()
    await db_save_sentiment_history(user_id, 0, "delete_all_tickets", "neutral", 0)
    await query.edit_message_text("✅ تم حذف جميع التذاكر.")
    await admin_panel_callback(update, context)


# ===================================================================
# دوال إدارة صلاحية /sendcode
# ===================================================================

async def admin_manage_sendcode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة صلاحية /sendcode"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    current_user = await db_get_allowed_sendcode_user()
    
    text = f"📁 **صلاحية /sendcode**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    text += f"📌 المستخدم الحالي: `{current_user}`\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ تعيين مستخدم", callback_data=CallbackData.ADMIN_SET_SENDCODE_USER)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_set_sendcode_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين مستخدم صلاحية /sendcode"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_SENDCODE_USER
    await query.edit_message_text("📝 **تعيين مستخدم /sendcode**\n\nأرسل معرف المستخدم (user_id):\nمثال: `123456789`", parse_mode="MarkdownV2")


# ===================================================================
# دوال قناة التقارير
# ===================================================================

async def admin_show_log_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قناة التقارير الحالية"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    channel_id = await db_get_log_channel_id()
    if channel_id:
        try:
            chat = await context.bot.get_chat(channel_id)
            text = f"📋 **قناة التقارير الحالية:**\n\n📌 الاسم: {chat.title}\n🆔 المعرف: `{channel_id}`"
        except:
            text = f"📋 **قناة التقارير الحالية:**\n\n🆔 المعرف: `{channel_id}`\n⚠️ لا يمكن الوصول إلى القناة"
    else:
        text = "📋 **لا توجد قناة تقارير محددة.**"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="MarkdownV2")


async def admin_set_log_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين قناة التقارير"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await query.answer("🔒 غير مصرح", show_alert=True)
        return
    
    context.user_data['state'] = UserState.WAITING_LOG_CHANNEL
    await query.edit_message_text("📝 **تعيين قناة التقارير**\n\nأرسل معرف القناة:\nمثال: `-100123456789` أو `@my_channel`\n\n📌 **ملاحظة:** يجب أن يكون البوت مشرفاً في القناة.")
# ===================================================================
# دوال الردود التلقائية للمستخدم (User Auto Reply)
# ===================================================================

async def user_auto_reply_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تبديل حالة الردود التلقائية للمستخدم (في الخاص).
    يتم استدعاؤها عند الضغط على زر تبديل الردود التلقائية في الإعدادات الشخصية.
    """
    query = update.callback_query
    if query:
        await query.answer()
    
    # 1. استخراج user_id من البيانات
    try:
        user_id = int(query.data.split(":")[-1])
    except (ValueError, IndexError):
        await query.answer("❌ بيانات غير صالحة!", show_alert=True)
        return
    
    # 2. التحقق من أن المستخدم يضغط على زر خاص به
    if user_id != update.effective_user.id:
        await query.answer("🔒 هذا الإعداد خاص بك فقط!", show_alert=True)
        return
    
    # 3. الحصول على الحالة الحالية
    current_status = await db_get_user_auto_reply_status(user_id)
    new_status = not current_status
    
    # 4. تحديث الحالة في قاعدة البيانات
    await db_set_user_auto_reply_status(user_id, new_status)
    
    # 5. تسجيل الحدث
    await db_save_sentiment_history(
        user_id, 
        0, 
        f"user_auto_reply_toggle_{new_status}", 
        "positive" if new_status else "neutral", 
        0.2 if new_status else 0
    )
    
    # 6. بناء رسالة التأكيد
    status_text = "🟢 مفعلة" if new_status else "🔴 معطلة"
    text = f"✅ **تم {'تفعيل' if new_status else 'تعطيل'} الردود التلقائية**\n\n"
    text += f"📌 الحالة: {status_text}\n"
    text += f"💡 سيتم الرد على رسائلك تلقائياً في المجموعات."
    
    # 7. عرض لوحة المفاتيح المحدثة
    keyboard = get_user_auto_reply_keyboard(user_id, new_status)
    
    await safe_edit_markdown(query, text, reply_markup=keyboard)


# ===================================================================
# دوال قاعدة البيانات المساعدة (إذا كانت مفقودة)
# ===================================================================

async def db_get_user_auto_reply_status(user_id: int) -> bool:
    """
    الحصول على حالة الردود التلقائية للمستخدم من قاعدة البيانات.
    """
    async def _get(conn):
        cur = await conn.execute(
            "SELECT auto_reply_enabled FROM users WHERE user_id=?",
            (user_id,)
        )
        row = await cur.fetchone()
        return row[0] == 1 if row and row[0] is not None else True  # افتراضي True
    return await execute_db(_get)


async def db_set_user_auto_reply_status(user_id: int, enabled: bool):
    """
    تحديث حالة الردود التلقائية للمستخدم في قاعدة البيانات.
    """
    async def _set(conn):
        await conn.execute(
            "UPDATE users SET auto_reply_enabled=? WHERE user_id=?",
            (1 if enabled else 0, user_id)
        )
        await conn.commit()
        logger.info(f"✅ تم {'تفعيل' if enabled else 'تعطيل'} الردود التلقائية للمستخدم {user_id}")
    return await execute_db(_set)


# ===================================================================
# دوال الكيبوردات المساعدة
# ===================================================================

def get_user_auto_reply_keyboard(user_id: int, enabled: bool) -> InlineKeyboardMarkup:
    """
    بناء لوحة مفاتيح الردود التلقائية للمستخدم.
    """
    status_text = "🟢 مفعل" if enabled else "🔴 معطل"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"📝 الردود التلقائية: {status_text}",
                callback_data=f"{CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX}{user_id}"
            )
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
# ===================================================================
# 11. دوال مساعدة
# ===================================================================
# ===================================================================
# دوال مساعدة - الوقت
# ===================================================================

def utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)

def mecca_now():
    return utc_now() + timedelta(hours=3)

def utc_now_iso():
    return utc_now().isoformat()

def mecca_now_iso():
    return mecca_now().isoformat()


# ===================================================================
# دوال الإرسال الآمن
# ===================================================================

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

async def safe_send_markdown(bot, chat_id: int, text: str, reply_markup=None, **kwargs):
    if not text:
        return None
    clean_text = sanitize_text(text)
    MAX_LEN = 4096
    try:
        escaped = escape_markdown_v2(clean_text)
        if len(escaped) > MAX_LEN:
            cut_point = MAX_LEN - 3
            while cut_point > 0 and escaped[cut_point - 1] in ('\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'):
                cut_point -= 1
            escaped = escaped[:cut_point] + "..."
        return await bot.send_message(chat_id=chat_id, text=escaped, parse_mode='MarkdownV2', reply_markup=reply_markup, **kwargs)
    except BadRequest as e:
        if "can't parse entities" in str(e) or "parse" in str(e):
            try:
                html_text = clean_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html_text)
                html_text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html_text)
                html_text = re.sub(r'__(.+?)__', r'<u>\1</u>', html_text)
                html_text = re.sub(r'`(.+?)`', r'<code>\1</code>', html_text)
                if len(html_text) > MAX_LEN:
                    html_text = html_text[:MAX_LEN-3] + "..."
                return await bot.send_message(chat_id=chat_id, text=html_text, parse_mode='HTML', reply_markup=reply_markup, **kwargs)
            except:
                pass
        if "bot can't initiate conversation" in str(e).lower() or "user_bot_to_bot_disabled" in str(e).lower():
            logger.warning(f"⚠️ لا يمكن بدء محادثة مع المستخدم {chat_id}")
            return None
        try:
            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', clean_text)
            if len(plain) > MAX_LEN:
                plain = plain[:MAX_LEN-3] + "..."
            return await bot.send_message(chat_id=chat_id, text=plain, reply_markup=reply_markup, **kwargs)
        except:
            raise
    except Forbidden as e:
        if "bot can't initiate conversation" in str(e).lower():
            logger.warning(f"⚠️ لا يمكن بدء محادثة مع المستخدم {chat_id}")
            return None
        raise
    except Exception as e:
        try:
            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', clean_text)
            if len(plain) > MAX_LEN:
                plain = plain[:MAX_LEN-3] + "..."
            return await bot.send_message(chat_id=chat_id, text=plain, reply_markup=reply_markup, **kwargs)
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
            while cut_point > 0 and escaped[cut_point - 1] in ('\\', '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'):
                cut_point -= 1
            escaped = escaped[:cut_point] + "..."
        return await query.edit_message_text(text=escaped, parse_mode='MarkdownV2', reply_markup=reply_markup, **kwargs)
    except BadRequest as e:
        if "can't parse entities" in str(e) or "parse" in str(e):
            try:
                html_text = clean_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', html_text)
                html_text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', html_text)
                html_text = re.sub(r'__(.+?)__', r'<u>\1</u>', html_text)
                html_text = re.sub(r'`(.+?)`', r'<code>\1</code>', html_text)
                if len(html_text) > MAX_LEN:
                    html_text = html_text[:MAX_LEN-3] + "..."
                return await query.edit_message_text(text=html_text, parse_mode='HTML', reply_markup=reply_markup, **kwargs)
            except:
                pass
        try:
            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', clean_text)
            if len(plain) > MAX_LEN:
                plain = plain[:MAX_LEN-3] + "..."
            return await query.edit_message_text(text=plain, reply_markup=reply_markup, **kwargs)
        except:
            raise
    except Exception as e:
        try:
            plain = re.sub(r'[*_`\[\]()~>#+\-=|{}.!\\]', '', clean_text)
            if len(plain) > MAX_LEN:
                plain = plain[:MAX_LEN-3] + "..."
            return await query.edit_message_text(text=plain, reply_markup=reply_markup, **kwargs)
        except:
            raise


# ===================================================================
# دوال قاعدة البيانات - الإعدادات
# ===================================================================

async def db_get_publish_interval_seconds() -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key='publish_interval'")
        row = await cur.fetchone()
        return int(row[0]) if row else DEFAULT_PUBLISH_INTERVAL_SECONDS
    return await execute_db(_get)
# ===================================================================
# إصلاح start_command_handler وجميع دوالها المساعدة
# ===================================================================

# ===================================================================
# دوال اللغة (إذا كانت مفقودة)
# ===================================================================

_lang_data = {}
user_language = {}

def get_text(user_id: int, key: str) -> str:
    lang = user_language.get(user_id, 'ar')
    texts = _lang_data.get(lang, {})
    if key not in texts:
        en_texts = _lang_data.get('en', {})
        if key in en_texts:
            return en_texts[key]
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
# دوال قاعدة البيانات المفقودة
# ===================================================================

async def db_has_active_subscription(user_id: int) -> bool:
    try:
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
    except:
        return False

async def db_auto_status(user_id: int) -> bool:
    try:
        async def _get(conn):
            cur = await conn.execute("SELECT auto_publish FROM users WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
            return row and row[0] == 1
        return await execute_db(_get)
    except:
        return True

async def db_get_updates_channel():
    try:
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
    except:
        return None

async def is_bot_admin(user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID:
        return True
    try:
        async def _check(conn):
            cur = await conn.execute("SELECT 1 FROM bot_admins WHERE user_id=?", (user_id,))
            return await cur.fetchone() is not None
        return await execute_db(_check)
    except:
        return False

async def db_get_user_groups_count(user_id: int) -> int:
    try:
        async def _get(conn):
            cur = await conn.execute("""
                SELECT COUNT(DISTINCT chat_id) FROM (
                    SELECT chat_id FROM hidden_owner_groups WHERE owner_id=?
                    UNION
                    SELECT chat_id FROM hidden_admins WHERE admin_id=?
                    UNION
                    SELECT chat_id FROM group_admins WHERE user_id=?
                )
            """, (user_id, user_id, user_id))
            row = await cur.fetchone()
            return row[0] if row else 0
        return await execute_db(_get)
    except:
        return 0

async def db_get_user_channels_count(user_id: int) -> int:
    try:
        async def _get(conn):
            cur = await conn.execute("SELECT COUNT(*) FROM user_channels WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
            return row[0] if row else 0
        return await execute_db(_get)
    except:
        return 0

async def db_get_user_total_posts(user_id: int) -> int:
    try:
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
    except:
        return 0

async def db_get_user_unpublished_posts(user_id: int) -> int:
    try:
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
    except:
        return 0

async def db_unpublished_count(channel_db_id: int) -> int:
    try:
        async def _count(conn):
            cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=0", (channel_db_id,))
            row = await cur.fetchone()
            return row[0] if row else 0
        return await execute_db(_count)
    except:
        return 0


# ===================================================================
# دالة get_main_keyboard (نسخة كاملة وآمنة)
# ===================================================================

async def get_main_keyboard(user_id: int):
    """بناء القائمة الرئيسية - نسخة آمنة"""
    try:
        # جلب القنوات
        channels = await db_get_channels(user_id) or []
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
        
        # جلب المجموعات
        my_groups = await db_get_user_groups_count(user_id) or 0
        
        # جلب الاشتراك
        has_sub = await db_has_active_subscription(user_id) or False
        sub_text = get_text(user_id, 'subscribed') if has_sub else get_text(user_id, 'not_subscribed')
        
        # جلب النشر التلقائي
        auto_status = await db_auto_status(user_id) or False
        auto_text = get_text(user_id, 'auto_on') if auto_status else get_text(user_id, 'auto_off')
        
        # بناء العنوان
        title = get_text(user_id, 'main_title').format(
            BOT_NAME, user_id, my_groups, sub_text, ch_display, cnt, auto_status
        )
        
        # جلب قناة التحديثات
        updates_channel = await db_get_updates_channel()
        updates_url = f"https://t.me/{updates_channel}" if updates_channel else None
        
        # بناء الأزرار
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
        
        try:
            is_admin = (user_id == PRIMARY_OWNER_ID) or (await is_bot_admin(user_id))
            if is_admin:
                keyboard.append([
                    InlineKeyboardButton(get_text(user_id, 'admin_panel'), callback_data=CallbackData.ADMIN_PANEL)
                ])
        except:
            pass
        
        # تنظيف الأزرار
        valid_keyboard = []
        for row in keyboard:
            if row and all(isinstance(btn, InlineKeyboardButton) for btn in row):
                valid_keyboard.append(row)
        if not valid_keyboard:
            valid_keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
        
        return InlineKeyboardMarkup(valid_keyboard), title, active
        
    except Exception as e:
        error_id = log_error(e, {'user_id': user_id, 'function': 'get_main_keyboard'})
        # رسالة خطأ بسيطة
        error_text = f"⚠️ حدث خطأ في تحميل القائمة (الرمز: `{error_id}`)"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]])
        return keyboard, error_text, None
# ===================================================================
# معالج الأخطاء المتطور - يعرض تفاصيل الخطأ للمستخدم
# ===================================================================

async def global_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    معالج أخطاء متطور يعرض تفاصيل دقيقة عن أي خطأ يحدث.
    """
    try:
        # 1. استخراج معلومات الخطأ
        error = context.error
        error_type = type(error).__name__
        error_message = str(error)
        
        # 2. استخراج معلومات المستخدم والرسالة
        user_id = update.effective_user.id if update and update.effective_user else "غير معروف"
        chat_id = update.effective_chat.id if update and update.effective_chat else "غير معروف"
        message_text = update.effective_message.text if update and update.effective_message else "غير معروف"
        
        # 3. إنشاء معرف فريد للخطأ
        error_id = secrets.token_hex(4)
        
        # 4. تحديد سبب الخطأ بناءً على نوعه
        cause = "غير معروف"
        solution = "يرجى إعادة المحاولة أو التواصل مع المطور."
        
        if isinstance(error, NameError):
            cause = f"دالة أو متغير غير معرف: `{error_message}`"
            solution = "تأكد من تعريف الدالة أو المتغير المطلوب."
        elif isinstance(error, AttributeError):
            cause = f"خاصية غير موجودة: `{error_message}`"
            solution = "تأكد من وجود الخاصية في الكائن المطلوب."
        elif isinstance(error, KeyError):
            cause = f"مفتاح غير موجود في القاموس: `{error_message}`"
            solution = "تأكد من وجود المفتاح المطلوب."
        elif isinstance(error, ValueError):
            cause = f"قيمة غير صالحة: `{error_message}`"
            solution = "تأكد من إدخال قيمة صحيحة."
        elif isinstance(error, TypeError):
            cause = f"نوع بيانات غير صحيح: `{error_message}`"
            solution = "تأكد من استخدام النوع الصحيح للبيانات."
        elif isinstance(error, sqlite3.OperationalError):
            cause = f"خطأ في قاعدة البيانات: `{error_message}`"
            solution = "تأكد من صحة استعلام SQL أو وجود الجداول المطلوبة."
        elif isinstance(error, BadRequest):
            cause = f"طلب غير صحيح إلى Telegram API: `{error_message}`"
            if "message is not modified" in error_message.lower():
                solution = "لا تحاول تعديل رسالة بنفس المحتوى."
            elif "user is not a member" in error_message.lower():
                solution = "تأكد من أن المستخدم عضو في المجموعة."
            elif "bot is not a member" in error_message.lower():
                solution = "تأكد من أن البوت عضو في المجموعة."
            else:
                solution = "تحقق من صحة البيانات المرسلة."
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
        else:
            cause = f"خطأ غير معروف: `{error_message}`"
            solution = "راجع سجلات البوت (logs) لمعرفة التفاصيل."
        
        # 5. بناء رسالة الخطأ المفصلة
        error_text = f"""🚨 **خطأ في البوت**
━━━━━━━━━━━━━━━━━━━━━━
🆔 **معرف الخطأ:** `{error_id}`
📌 **نوع الخطأ:** `{error_type}`
📝 **الرسالة:** `{error_message}`

📋 **السبب:**
{cause}

🔧 **الحل المقترح:**
{solution}
━━━━━━━━━━━━━━━━━━━━━━
👤 **المستخدم:** `{user_id}`
💬 **المجموعة:** `{chat_id}`
📝 **الرسالة:** `{message_text[:100]}`
🕐 **الوقت:** {mecca_now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━━
📌 **حالة الخطأ:** ⚠️ قيد المعالجة"""

        # 6. إرسال التفاصيل إلى المستخدم (إذا كان موجوداً)
        if update and update.effective_user:
            try:
                await safe_send_markdown(
                    context.bot,
                    user_id,
                    error_text
                )
            except Exception as e:
                # إذا فشل إرسال التفاصيل، أرسل رسالة مبسطة
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"❌ حدث خطأ (الرمز: `{error_id}`)\nنوع الخطأ: `{error_type}`"
                    )
                except:
                    pass
        
        # 7. إرسال إلى قناة التقارير (إذا كانت محددة)
        log_channel_id = await db_get_log_channel_id()
        if log_channel_id:
            try:
                await context.bot.send_message(
                    chat_id=log_channel_id,
                    text=error_text,
                    parse_mode="MarkdownV2"
                )
            except:
                pass
        
        # 8. تسجيل في سجل الأخطاء
        advanced_logger.log_error(
            f"خطأ في التحديث ({error_id})",
            error,
            {
                'user_id': user_id,
                'chat_id': chat_id,
                'message': message_text[:200],
                'error_id': error_id
            }
        )
        
        # 9. إرسال إشعار للمطور الأساسي (للأخطاء الحرجة)
        if isinstance(error, (Forbidden, Conflict, sqlite3.OperationalError)):
            try:
                await context.bot.send_message(
                    chat_id=PRIMARY_OWNER_ID,
                    text=f"🚨 **خطأ حرج في البوت**\n\n🆔 `{error_id}`\n📌 `{error_type}`\n📝 `{error_message[:200]}`\n👤 المستخدم: `{user_id}`",
                    parse_mode="MarkdownV2"
                )
            except:
                pass
        
        return True
        
    except Exception as e:
        # معالج الطوارئ - في حالة فشل معالج الأخطاء نفسه
        logger.error(f"فشل معالج الأخطاء نفسه: {e}")
        try:
            if update and update.effective_user:
                await context.bot.send_message(
                    chat_id=update.effective_user.id,
                    text="❌ حدث خطأ غير متوقع. تم إبلاغ المطور."
                )
        except:
            pass
        return True


# ===================================================================
# دالة مساعدة لاختبار معالج الأخطاء (للتأكد من عمله)
# ===================================================================

async def test_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    أمر اختبار لإنشاء خطأ متعمد والتحقق من عمل معالج الأخطاء.
    """
    # هذا سيخلق خطأ NameError متعمداً
    undefined_variable = some_undefined_variable  # خطأ متعمد
    await update.message.reply_text("هذا النص لن يظهر")

# ===================================================================
# 34. دالة main() النهائية
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
                        await conn.execute("INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?, ?, ?, ?)", (word, -1, PRIMARY_OWNER_ID, utc_now_iso()))
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
    
    # تسجيل معالجات الأوامر
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
    application.add_handler(CommandHandler("support_reply", support_reply_command_handler))
    application.add_handler(CommandHandler("rank", rank_command_handler))
    application.add_handler(CommandHandler("top", top_command_handler))
    application.add_handler(CommandHandler("developer", developer_command_handler))
    application.add_handler(CommandHandler("updates", updates_command_handler))
    application.add_handler(CommandHandler("stats", stats_command_handler))
    application.add_handler(CommandHandler("sendcode", sendcode_command_handler))
    application.add_handler(CommandHandler("lock", lock_chat_command_handler))
    application.add_handler(CommandHandler("unlock", unlock_chat_command_handler))
    application.add_handler(CommandHandler("schedule", schedule_command_handler))
    application.add_handler(CommandHandler("panel", panel_command_handler))
    application.add_handler(CommandHandler("set_log_channel", set_log_channel_command_handler))
    application.add_handler(CommandHandler("ban", handle_moderation_commands))
    application.add_handler(CommandHandler("mute", handle_moderation_commands))
    application.add_handler(CommandHandler("warn", handle_moderation_commands))
    application.add_handler(CommandHandler("kick", handle_moderation_commands))
    application.add_handler(CommandHandler("restrict", handle_moderation_commands))
    application.add_handler(CommandHandler("pin", handle_moderation_commands))
    application.add_handler(CommandHandler("unban", handle_moderation_commands))
    application.add_handler(CommandHandler("contests", contests_command_handler))
    application.add_handler(CommandHandler("create_contest", create_contest_command_handler))
    application.add_handler(CommandHandler("declare_winner", declare_winner_command_handler))
    application.add_handler(CommandHandler("set_rules", set_rules_command_handler))
    application.add_handler(CommandHandler("rules", rules_command_handler))
    
    # تسجيل معالجات الكولباك - الأساسية
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern=f"^{CallbackData.MAIN_MENU}$"))
    application.add_handler(CallbackQueryHandler(back_callback, pattern=f"^{CallbackData.BACK}$"))
    application.add_handler(CallbackQueryHandler(cancel_session_callback, pattern=f"^{CallbackData.CANCEL_SESSION}$"))
    
    # تسجيل معالجات الكولباك - القنوات
    application.add_handler(CallbackQueryHandler(add_channel_callback, pattern=f"^{CallbackData.CHANNELS_ADD}$"))
    application.add_handler(CallbackQueryHandler(my_channels_callback, pattern=f"^{CallbackData.CHANNELS_MY}$"))
    application.add_handler(CallbackQueryHandler(delete_channel_callback, pattern=f"^{CallbackData.CHANNELS_DELETE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(select_channel_callback, pattern=f"^{CallbackData.CHANNELS_SELECT_PREFIX}"))
    
    # تسجيل معالجات الكولباك - المنشورات
    application.add_handler(CallbackQueryHandler(add_15_posts_callback, pattern=f"^{CallbackData.POSTS_ADD_15}$"))
    application.add_handler(CallbackQueryHandler(publish_one_callback, pattern=f"^{CallbackData.POSTS_PUBLISH_ONE}$"))
    application.add_handler(CallbackQueryHandler(my_posts_callback, pattern=f"^{CallbackData.POSTS_MY}$"))
    application.add_handler(CallbackQueryHandler(recycle_posts_callback, pattern=f"^{CallbackData.POSTS_RECYCLE}$"))
    application.add_handler(CallbackQueryHandler(delete_single_post_callback, pattern=f"^{CallbackData.POSTS_DELETE_SINGLE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(confirm_clear_all_posts_callback, pattern=f"^{CallbackData.POSTS_CONFIRM_CLEAR_ALL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(clear_all_posts_callback, pattern=f"^{CallbackData.POSTS_CLEAR_ALL_PREFIX}"))
    
    # تسجيل معالجات الكولباك - الإحصائيات
    application.add_handler(CallbackQueryHandler(pending_stats_callback, pattern=f"^{CallbackData.STATS_PENDING}$"))
    application.add_handler(CallbackQueryHandler(full_stats_callback, pattern=f"^{CallbackData.STATS_FULL}$"))
    
    # تسجيل معالجات الكولباك - المجموعات
    application.add_handler(CallbackQueryHandler(my_groups_callback, pattern=f"^{CallbackData.GROUPS_MY}$"))
    application.add_handler(CallbackQueryHandler(group_settings_callback, pattern=f"^{CallbackData.GROUPS_SETTINGS_PREFIX}"))
    
    # تسجيل معالجات الكولباك - الإعدادات
    application.add_handler(CallbackQueryHandler(settings_menu_callback, pattern=f"^{CallbackData.SETTINGS_MENU}$"))
    application.add_handler(CallbackQueryHandler(toggle_auto_publish_callback, pattern=f"^{CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH}$"))
    application.add_handler(CallbackQueryHandler(toggle_auto_recycle_callback, pattern=f"^{CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE}$"))
    
    # تسجيل معالجات الكولباك - الجدولة
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
    
    # تسجيل معالجات الكولباك - الأمان
    application.add_handler(CallbackQueryHandler(security_toggle_setting_callback, pattern=r"^security:(links|mentions|slow_mode|delete_videos|delete_service|delete_documents|delete_stickers|delete_audio|delete_animation|delete_forwarded|delete_polls|delete_games|delete_voice|delete_video_note|welcome_enabled|goodbye_enabled|antiflood|night_mode|max_length|warn_settings):[0-9-]+$"))
    application.add_handler(CallbackQueryHandler(security_banned_words_menu_callback, pattern=f"^{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}"))
    application.add_handler(CallbackQueryHandler(banned_words_add_callback, pattern=f"^{CallbackData.BANNED_WORDS_ADD_PREFIX}"))
    application.add_handler(CallbackQueryHandler(banned_words_list_callback, pattern=f"^{CallbackData.BANNED_WORDS_LIST_PREFIX}"))
    application.add_handler(CallbackQueryHandler(banned_words_remove_callback, pattern=f"^{CallbackData.BANNED_WORDS_REMOVE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(security_delete_penalty_callback, pattern=f"^{CallbackData.SECURITY_DELETE_PENALTY_PREFIX}"))
    application.add_handler(CallbackQueryHandler(set_delete_penalty_callback, pattern="^set_delete_penalty:"))
    application.add_handler(CallbackQueryHandler(security_warn_settings_callback, pattern="^security:warn_settings:"))
    application.add_handler(CallbackQueryHandler(security_warn_count_callback, pattern="^warn_count:"))
    application.add_handler(CallbackQueryHandler(set_warn_penalty_callback, pattern="^warn_penalty:"))
    application.add_handler(CallbackQueryHandler(security_enable_all_callback, pattern=f"^{CallbackData.SECURITY_ENABLE_ALL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(confirm_enable_all_callback, pattern="^confirm_enable_all:"))
    application.add_handler(CallbackQueryHandler(security_disable_all_callback, pattern=f"^{CallbackData.SECURITY_DISABLE_ALL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(security_close_callback, pattern=f"^{CallbackData.SECURITY_CLOSE}$"))
    
    # تسجيل معالجات الكولباك - اختيار المجموعة للأمان
    application.add_handler(CallbackQueryHandler(security_select_group_callback, pattern=f"^{CallbackData.SECURITY_SELECT_GROUP}"))
    application.add_handler(CallbackQueryHandler(security_refresh_groups_callback, pattern=f"^{CallbackData.SECURITY_REFRESH_GROUPS}$"))
    
    # تسجيل معالجات الكولباك - العقوبات
    application.add_handler(CallbackQueryHandler(penalty_menu_callback, pattern=f"^{CallbackData.PENALTY_MENU}:"))
    application.add_handler(CallbackQueryHandler(penalty_kick_callback, pattern=f"^{CallbackData.PENALTY_KICK}:"))
    application.add_handler(CallbackQueryHandler(penalty_ban_callback, pattern=f"^{CallbackData.PENALTY_BAN}:"))
    application.add_handler(CallbackQueryHandler(penalty_mute_callback, pattern=f"^{CallbackData.PENALTY_MUTE}:"))
    application.add_handler(CallbackQueryHandler(penalty_warn_callback, pattern="^penalty:warn:"))
    application.add_handler(CallbackQueryHandler(penalty_restrict_callback, pattern="^penalty:restrict:"))
    application.add_handler(CallbackQueryHandler(penalty_none_callback, pattern="^penalty:none:"))
    application.add_handler(CallbackQueryHandler(mute_duration_menu_callback, pattern="^mute_duration_menu:"))
    application.add_handler(CallbackQueryHandler(penalty_mute_duration_callback, pattern="^mute_duration:"))
    
    # تسجيل معالجات الكولباك - الإجراءات المتقدمة
    application.add_handler(CallbackQueryHandler(advanced_actions_callback, pattern=f"^{CallbackData.ADVANCED_ACTIONS}"))
    application.add_handler(CallbackQueryHandler(group_action_ban_callback, pattern=f"^{CallbackData.GROUP_ACTION_BAN}"))
    application.add_handler(CallbackQueryHandler(group_action_mute_callback, pattern=f"^{CallbackData.GROUP_ACTION_MUTE}"))
    application.add_handler(CallbackQueryHandler(advanced_mute_duration_callback, pattern="^adv_mute_duration:"))
    application.add_handler(CallbackQueryHandler(group_action_warn_callback, pattern=f"^{CallbackData.GROUP_ACTION_WARN}"))
    application.add_handler(CallbackQueryHandler(group_action_kick_callback, pattern=f"^{CallbackData.GROUP_ACTION_KICK}"))
    application.add_handler(CallbackQueryHandler(group_action_restrict_callback, pattern=f"^{CallbackData.GROUP_ACTION_RESTRICT}"))
    application.add_handler(CallbackQueryHandler(group_action_pin_callback, pattern=f"^{CallbackData.GROUP_ACTION_PIN}"))
    application.add_handler(CallbackQueryHandler(group_action_log_callback, pattern=f"^{CallbackData.GROUP_ACTION_LOG}"))
    application.add_handler(CallbackQueryHandler(group_action_unban_callback, pattern=f"^{CallbackData.GROUP_ACTION_UNBAN}"))
    
    # تسجيل معالجات الكولباك - لوحة التحكم
    application.add_handler(CallbackQueryHandler(panel_lock_callback_handler, pattern=f"^{CallbackData.PANEL_LOCK_PREFIX}"))
    application.add_handler(CallbackQueryHandler(panel_unlock_callback_handler, pattern=f"^{CallbackData.PANEL_UNLOCK_PREFIX}"))
    application.add_handler(CallbackQueryHandler(panel_close_callback_handler, pattern=f"^{CallbackData.PANEL_CLOSE}$"))
    
    # تسجيل معالجات الكولباك - المساعدة والدعم
    application.add_handler(CallbackQueryHandler(help_callback, pattern=f"^{CallbackData.HELP}$"))
    application.add_handler(CallbackQueryHandler(support_menu_callback, pattern=f"^{CallbackData.SUPPORT_MENU}$"))
    application.add_handler(CallbackQueryHandler(support_help_callback, pattern=f"^{CallbackData.SUPPORT_HELP}$"))
    application.add_handler(CallbackQueryHandler(support_ticket_callback, pattern=f"^{CallbackData.SUPPORT_TICKET}$"))
    application.add_handler(CallbackQueryHandler(support_back_callback, pattern=f"^{CallbackData.SUPPORT_BACK}$"))
    
    # تسجيل معالجات الكولباك - التجربة والاشتراك
    application.add_handler(CallbackQueryHandler(trial_callback, pattern=f"^{CallbackData.TRIAL}$"))
    application.add_handler(CallbackQueryHandler(subscribe_menu_callback, pattern=f"^{CallbackData.SUBSCRIBE_MENU}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_1_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_1}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_2_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_2}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_30_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_30}$"))
    application.add_handler(CallbackQueryHandler(buy_subscription_90_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_90}$"))
    
    # تسجيل معالجات الكولباك - المطور والتحديثات
    application.add_handler(CallbackQueryHandler(developer_callback, pattern=f"^{CallbackData.DEVELOPER}$"))
    application.add_handler(CallbackQueryHandler(updates_callback, pattern=f"^{CallbackData.UPDATES}$"))
    
    # تسجيل معالجات الكولباك - الإحالات
    application.add_handler(CallbackQueryHandler(referral_menu_callback, pattern=f"^{CallbackData.REFERRAL_MENU}$"))
    application.add_handler(CallbackQueryHandler(referral_copy_link_callback, pattern=f"^{CallbackData.REFERRAL_COPY_LINK_PREFIX}"))
    application.add_handler(CallbackQueryHandler(referral_claim_reward_callback, pattern=f"^{CallbackData.REFERRAL_CLAIM_REWARD}$"))
    application.add_handler(CallbackQueryHandler(referral_list_callback, pattern=f"^{CallbackData.REFERRAL_LIST}$"))
    
    # تسجيل معالجات الكولباك - التذكيرات
    application.add_handler(CallbackQueryHandler(reminder_menu_callback, pattern=f"^{CallbackData.REMINDER_MENU}$"))
    application.add_handler(CallbackQueryHandler(reminder_toggle_sub_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_SUB}$"))
    application.add_handler(CallbackQueryHandler(reminder_toggle_daily_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_DAILY}$"))
    application.add_handler(CallbackQueryHandler(reminder_toggle_weekly_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_WEEKLY}$"))
    application.add_handler(CallbackQueryHandler(reminder_set_days_callback, pattern=f"^{CallbackData.REMINDER_SET_DAYS}$"))
    application.add_handler(CallbackQueryHandler(reminder_set_lang_callback, pattern=f"^{CallbackData.REMINDER_SET_LANG}$"))
    application.add_handler(CallbackQueryHandler(reminder_lang_callback, pattern=f"^{CallbackData.REMINDER_LANG_PREFIX}"))
    
    # تسجيل معالجات الكولباك - الترجمة
    application.add_handler(CallbackQueryHandler(translation_menu_callback, pattern=f"^{CallbackData.TRANSLATION_MENU}$"))
    application.add_handler(CallbackQueryHandler(translation_off_callback, pattern=f"^{CallbackData.TRANSLATION_OFF}$"))
    application.add_handler(CallbackQueryHandler(translation_set_callback, pattern=f"^{CallbackData.TRANSLATION_SET_PREFIX}"))
    
    # تسجيل معالجات الكولباك - المسابقات
    application.add_handler(CallbackQueryHandler(contests_menu_callback, pattern=f"^{CallbackData.CONTESTS_MENU}$"))
    application.add_handler(CallbackQueryHandler(contest_join_callback, pattern=f"^{CallbackData.CONTEST_JOIN_PREFIX}"))
    application.add_handler(CallbackQueryHandler(contest_winners_callback, pattern=f"^{CallbackData.CONTEST_WINNERS}$"))
    application.add_handler(CallbackQueryHandler(contests_back_callback, pattern=f"^{CallbackData.CONTESTS_BACK}$"))
    
    # تسجيل معالجات الكولباك - إحصائيات القنوات والنشر الشامل
    application.add_handler(CallbackQueryHandler(channel_stats_callback, pattern=f"^{CallbackData.CHANNEL_STATS}:"))
    application.add_handler(CallbackQueryHandler(channel_growth_callback, pattern=f"^{CallbackData.CHANNEL_GROWTH}:"))
    application.add_handler(CallbackQueryHandler(channel_stats_refresh_callback, pattern=f"^{CallbackData.CHANNEL_STATS_REFRESH}:"))
    application.add_handler(CallbackQueryHandler(my_channel_stats_callback, pattern=f"^{CallbackData.MY_CHANNEL_STATS}$"))
    application.add_handler(CallbackQueryHandler(publish_all_channels_callback_handler, pattern=f"^{CallbackData.PUBLISH_ALL_CHANNELS}$"))
    
    # تسجيل معالجات الكولباك - NSFW
    application.add_handler(CallbackQueryHandler(nsfw_settings_callback, pattern=f"^{CallbackData.NSFW_SETTINGS}$"))
    application.add_handler(CallbackQueryHandler(nsfw_toggle_callback, pattern=f"^{CallbackData.NSFW_TOGGLE}$"))
    application.add_handler(CallbackQueryHandler(nsfw_threshold_set_callback, pattern=f"^{CallbackData.NSFW_THRESHOLD_SET}$"))
    
    # تسجيل معالجات الكولباك - اشتراك إجباري
    application.add_handler(CallbackQueryHandler(check_subscribe_callback_handler, pattern=f"^{CallbackData.CHECK_SUBSCRIBE}$"))
    
    # تسجيل معالجات الكولباك - اللغة والأوامر النصية
    application.add_handler(CallbackQueryHandler(language_callback, pattern=r"^lang_"))
    application.add_handler(CallbackQueryHandler(handle_text_callbacks, pattern="^(rank|top|schedule_post|language)$"))
    
    # تسجيل معالجات الكولباك - لوحة الأدمن
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
    
    # تسجيل معالجات الكولباك - إدارة الردود والكلمات المحظورة
    application.add_handler(CallbackQueryHandler(admin_replies_callback, pattern=f"^{CallbackData.ADMIN_REPLIES}$"))
    application.add_handler(CallbackQueryHandler(admin_add_reply_callback, pattern=f"^{CallbackData.ADMIN_ADD_REPLY}$"))
    application.add_handler(CallbackQueryHandler(admin_list_replies_callback, pattern=f"^{CallbackData.ADMIN_LIST_REPLIES}$"))
    application.add_handler(CallbackQueryHandler(admin_del_reply_callback, pattern=f"^{CallbackData.ADMIN_DEL_REPLY}$"))
    application.add_handler(CallbackQueryHandler(admin_banned_words_callback, pattern=f"^{CallbackData.ADMIN_BANNED_WORDS}$"))
    application.add_handler(CallbackQueryHandler(admin_add_banned_word_callback, pattern=f"^{CallbackData.ADMIN_ADD_BANNED_WORD}$"))
    application.add_handler(CallbackQueryHandler(admin_list_banned_words_callback, pattern=f"^{CallbackData.ADMIN_LIST_BANNED_WORDS}$"))
    application.add_handler(CallbackQueryHandler(admin_remove_banned_word_callback, pattern=f"^{CallbackData.ADMIN_REMOVE_BANNED_WORD}$"))
    
    # تسجيل معالجات الكولباك - المسابقات (أدمن)
    application.add_handler(CallbackQueryHandler(admin_create_contest_callback, pattern=f"^{CallbackData.ADMIN_CREATE_CONTEST}$"))
    application.add_handler(CallbackQueryHandler(admin_declare_winner_callback, pattern=f"^{CallbackData.ADMIN_DECLARE_WINNER}$"))
    application.add_handler(CallbackQueryHandler(admin_del_contest_callback, pattern=f"^{CallbackData.ADMIN_DEL_CONTEST_PREFIX}"))
    
    # تسجيل معالجات الكولباك - الردود التلقائية
    application.add_handler(CallbackQueryHandler(admin_auto_reply_callback, pattern=f"^{CallbackData.ADMIN_AUTO_REPLY}$"))
    application.add_handler(CallbackQueryHandler(auto_reply_menu_callback, pattern=f"^{CallbackData.AUTO_REPLY_MENU_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_toggle_callback, pattern=f"^{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_admins_callback, pattern=f"^{CallbackData.AUTO_REPLY_ADMINS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_reset_callback, pattern=f"^{CallbackData.AUTO_REPLY_RESET_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_confirm_reset_callback, pattern=f"^{CallbackData.AUTO_REPLY_CONFIRM_RESET_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_cancel_callback, pattern=f"^{CallbackData.AUTO_REPLY_CANCEL_PREFIX}"))
    application.add_handler(CallbackQueryHandler(auto_reply_stats_callback, pattern=f"^{CallbackData.AUTO_REPLY_STATS_PREFIX}"))
    application.add_handler(CallbackQueryHandler(user_auto_reply_toggle_callback, pattern=f"^{CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX}"))
    
    # تسجيل معالجات الرسائل
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler))
    application.add_handler(MessageHandler(filters.CAPTION & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, message_handler_main))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.AUDIO & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.VOICE & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.ANIMATION & filters.ChatType.PRIVATE, message_handler_main))
    application.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, message_handler_main))
    
    # تسجيل معالجات الأحداث الإضافية
    application.add_handler(ChatJoinRequestHandler(chat_join_request_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_chat_member_handler))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback_handler))
    application.add_handler(ChatMemberHandler(track_chat_add, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER, delete_service_messages))
    
    # تعيين أوامر البوت
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
    ]
    await application.bot.set_my_commands(commands)
    
    # تشغيل المهام الخلفية
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
    
    # بدء خادم الويب
    port = int(os.getenv("PORT", "10000"))
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("HEROKU_APP_NAME")
    
    try:
        await setup_unified_web_server(application, port)
        logger.info(f"✅ خادم الويب يعمل على المنفذ {port}")
    except Exception as e:
        logger.error(f"❌ فشل بدء خادم الويب: {e}")
        raise
    
    if hostname:
        # بيئة سحابية: Webhook
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
        # بيئة محلية: Polling
        logger.info("🔄 استخدام Polling (بدون Webhook)")
        await application.bot.delete_webhook()
        await run_polling_safe(application)

# ===================================================================
# 35. تشغيل البوت النهائي
# ===================================================================
if __name__ == "__main__":
    try:
        os.environ["WEB_CONCURRENCY"] = "1"
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 تم إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {e}")
        traceback.print_exc()
        sys.exit(1)

