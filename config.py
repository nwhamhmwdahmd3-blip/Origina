#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
config.py - إعدادات البوت الأساسية (نسخة نهائية محسّنة)
====================================================
- تحميل .env من المسار الصحيح
- تحويل آمن للأرقام والمنطقية
- إنشاء المجلدات تلقائياً
- التحقق من صحة الإعدادات
- دعم المشرف المجهول افتراضياً
- تنظيف التوكن من المسافات (إصلاح 1)
- التحقق من العلاقة بين فترات النشر (إصلاح 2)
"""

import os
import sys
import json
import logging
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any
from dotenv import load_dotenv

# تحميل ملف .env من نفس مجلد المشروع
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)


def safe_int(value: str, default: int = 0) -> int:
    """تحويل قيمة نصية إلى رقم صحيح مع إرجاع القيمة الافتراضية عند الخطأ"""
    try:
        return int(value.strip())
    except (ValueError, AttributeError, TypeError):
        return default


def safe_bool(value: str, default: bool = False) -> bool:
    """تحويل قيمة نصية إلى منطقية"""
    if value is None:
        return default
    return value.lower() in ['true', '1', 'yes', 'on']


@dataclass(frozen=True)
class AppConfig:
    # ========== المتغيرات الأساسية (مطلوبة) ==========
    TOKEN: str = os.getenv("BOT_TOKEN", "").strip()  # إصلاح: تنظيف التوكن
    PRIMARY_OWNER_ID: int = safe_int(os.getenv("MAIN_ADMIN_ID", "0"))
    DEVELOPER_IDS: List[int] = field(default_factory=lambda: [
        id for id in [
            safe_int(x) for x in os.getenv("DEVELOPER_IDS", "").split(",") if x.strip()
        ] if id > 0
    ])

    # ========== معلومات البوت ==========
    BOT_NAME: str = os.getenv("BOT_NAME", "ريلاكس مانيجر")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "Reelaaaxbot").lstrip('@')

    # ========== الشبكة والبروكسي ==========
    USE_PROXY: bool = safe_bool(os.getenv("USE_PROXY", "false"))
    PROXY_URL: str = os.getenv("PROXY_URL", "http://127.0.0.1:10809")
    WEB_PORT: int = safe_int(os.getenv("PORT", "10000"))
    MAX_CONNECTIONS: int = safe_int(os.getenv("MAX_CONNECTIONS", "20"))

    # ========== النسخ الاحتياطي ==========
    MAX_BACKUPS: int = safe_int(os.getenv("MAX_BACKUPS", "20"))

    # ========== النشر التلقائي ==========
    DEFAULT_PUBLISH_INTERVAL: int = safe_int(os.getenv("DEFAULT_PUBLISH_INTERVAL", "12"))
    MAX_CHANNELS_PER_CYCLE: int = safe_int(os.getenv("MAX_CHANNELS_PER_CYCLE", "20"))
    PUBLISH_RETRY_DELAY: int = safe_int(os.getenv("PUBLISH_RETRY_DELAY", "5"))
    MAX_UNPUBLISHED_POSTS: int = safe_int(os.getenv("MAX_UNPUBLISHED_POSTS", "1000"))
    MAX_POSTS_PER_CHANNEL: int = safe_int(os.getenv("MAX_POSTS_PER_CHANNEL", "30"))
    MIN_PUBLISH_INTERVAL: int = safe_int(os.getenv("MIN_PUBLISH_INTERVAL", "5"))

    # ========== قاعدة البيانات ==========
    DB_TIMEOUT: int = safe_int(os.getenv("DB_TIMEOUT", "30"))

    # ========== الإحالات ==========
    MAX_DAILY_REFERRALS: int = safe_int(os.getenv("MAX_DAILY_REFERRALS", "5"))
    MAX_GLOBAL_BANNED_WORDS: int = safe_int(os.getenv("MAX_GLOBAL_BANNED_WORDS", "100"))

    # ========== الكاش ==========
    CACHE_TTL: int = safe_int(os.getenv("CACHE_TTL", "30"))
    AUTH_CACHE_SIZE: int = safe_int(os.getenv("AUTH_CACHE_SIZE", "2000"))
    AUTH_CACHE_TTL: int = safe_int(os.getenv("AUTH_CACHE_TTL", "15"))

    # ========== العملة والدفع ==========
    XTR_CURRENCY: str = os.getenv("XTR_CURRENCY", "XTR")

    # ========== النبض والخلفية ==========
    HEARTBEAT_INTERVAL: int = safe_int(os.getenv("HEARTBEAT_INTERVAL", "300"))
    ENABLE_SELF_PING: bool = safe_bool(os.getenv("ENABLE_SELF_PING", "true"))

    # ========== المشرف المجهول ==========
    ANONYMOUS_ADMIN_ID: int = safe_int(os.getenv("ANONYMOUS_ADMIN_ID", "1087968824"))

    # ========== ميزات جديدة ==========
    GIFT_PLANS_ENABLED: bool = safe_bool(os.getenv("GIFT_PLANS_ENABLED", "true"))
    PENALTY_SYSTEM_ENABLED: bool = safe_bool(os.getenv("PENALTY_SYSTEM_ENABLED", "true"))
    ENABLE_BANNED_WORDS_CACHE: bool = safe_bool(os.getenv("ENABLE_BANNED_WORDS_CACHE", "true"))
    BANNED_WORDS_CACHE_TTL: int = safe_int(os.getenv("BANNED_WORDS_CACHE_TTL", "60"))

    # ========== إعدادات إضافية ==========
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    DEBUG_MODE: bool = safe_bool(os.getenv("DEBUG_MODE", "false"))
    DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "ar")

    def validate(self) -> None:
        """التحقق من القيم المطلوبة مع رسائل خطأ واضحة"""
        errors = []

        if not self.TOKEN:
            errors.append("BOT_TOKEN غير موجود في .env")
        elif len(self.TOKEN) < 20:
            errors.append("BOT_TOKEN يبدو غير صالح (قصير جداً)")

        if self.PRIMARY_OWNER_ID == 0:
            errors.append("MAIN_ADMIN_ID غير موجود في .env")
        elif self.PRIMARY_OWNER_ID < 0:
            errors.append("MAIN_ADMIN_ID يجب أن يكون رقماً موجباً")

        if self.WEB_PORT < 1 or self.WEB_PORT > 65535:
            errors.append(f"WEB_PORT غير صالح: {self.WEB_PORT}")

        if self.MAX_BACKUPS < 1:
            errors.append("MAX_BACKUPS يجب أن يكون أكبر من 0")

        if self.MIN_PUBLISH_INTERVAL < 1:
            errors.append("MIN_PUBLISH_INTERVAL يجب أن يكون أكبر من 0")

        # إصلاح: التحقق من العلاقة بين الفترات
        if self.DEFAULT_PUBLISH_INTERVAL < self.MIN_PUBLISH_INTERVAL:
            errors.append(
                f"DEFAULT_PUBLISH_INTERVAL ({self.DEFAULT_PUBLISH_INTERVAL}) "
                f"يجب أن يكون أكبر من أو يساوي MIN_PUBLISH_INTERVAL ({self.MIN_PUBLISH_INTERVAL})"
            )

        if errors:
            error_msg = "\n".join(f"  • {e}" for e in errors)
            raise ValueError(f"❌ أخطاء في الإعدادات:\n{error_msg}")

    def is_developer(self, user_id: int) -> bool:
        return user_id == self.PRIMARY_OWNER_ID or user_id in self.DEVELOPER_IDS

    def is_owner(self, user_id: int) -> bool:
        return user_id == self.PRIMARY_OWNER_ID


class PathManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_paths()
            return cls._instance

    def _init_paths(self):
        self.BASE = Path(__file__).resolve().parent
        self.DATA = self.BASE / "data"
        self.BACKUPS = self.BASE / "backups"
        self.LOGS = self.BASE / "logs"
        self.DB = self.DATA / "bot_data.db"
        self.LOG_FILE = self.LOGS / "bot.log"

        # إنشاء المجلدات اللازمة
        for d in [self.DATA, self.BACKUPS, self.LOGS]:
            d.mkdir(parents=True, exist_ok=True)

        # إنشاء ملف السجل إذا لم يكن موجودًا
        if not self.LOG_FILE.exists():
            self.LOG_FILE.touch(exist_ok=True)


# إنشاء الكائنات
CONFIG = AppConfig()
PATHS = PathManager()

# استدعاء التحقق من الإعدادات
try:
    CONFIG.validate()
except ValueError as e:
    logger.error(f"❌ {e}")
    raise SystemExit(1)

logger.info(f"✅ تم تحميل الإعدادات: {CONFIG.BOT_NAME} (@{CONFIG.BOT_USERNAME})")
logger.info(f"📁 قاعدة البيانات: {PATHS.DB}")
