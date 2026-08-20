#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
config.py - إعدادات البوت الأساسية (نسخة مُصحَّحة)
====================================================
- تحويل آمن للأرقام من متغيرات البيئة
- تحميل .env من المسار الصحيح
- إنشاء مجلدات وملف السجل تلقائيًا
- جميع المتغيرات المطلوبة للمشروع
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

# تحميل ملف .env من نفس مجلد المشروع
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)

# دالة تحويل آمنة للأرقام
def safe_int(value: str, default: int = 0) -> int:
    """تحويل قيمة نصية إلى رقم صحيح مع إرجاع القيمة الافتراضية عند الخطأ"""
    try:
        return int(value.strip())
    except (ValueError, AttributeError, TypeError):
        return default

@dataclass(frozen=True)
class AppConfig:
    # ========== المتغيرات الأساسية (مطلوبة) ==========
    TOKEN: str = os.getenv("BOT_TOKEN", "")
    PRIMARY_OWNER_ID: int = safe_int(os.getenv("MAIN_ADMIN_ID", "0"))
    DEVELOPER_IDS: List[int] = field(default_factory=lambda: [
        safe_int(id) for id in os.getenv("DEVELOPER_IDS", "").split(",") if id.strip()
    ])

    # ========== معلومات البوت ==========
    BOT_NAME: str = os.getenv("BOT_NAME", "ريلاكس مانيجر")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "Reelaaaxbot").lstrip('@')

    # ========== الشبكة والبروكسي ==========
    USE_PROXY: bool = os.getenv("USE_PROXY", "false").lower() in ['true', '1']
    PROXY_URL: str = os.getenv("PROXY_URL", "http://127.0.0.1:10809")
    WEB_PORT: int = safe_int(os.getenv("PORT", "10000"))
    MAX_CONNECTIONS: int = 20

    # ========== النسخ الاحتياطي ==========
    MAX_BACKUPS: int = 20

    # ========== النشر التلقائي ==========
    DEFAULT_PUBLISH_INTERVAL: int = 720          # الثواني الافتراضية بين المنشورات
    MAX_CHANNELS_PER_CYCLE: int = 20             # عدد القنوات في كل دورة نشر
    PUBLISH_RETRY_DELAY: int = 300               # تأخير إعادة المحاولة بعد الفشل
    MAX_UNPUBLISHED_POSTS: int = 1000            # الحد الأقصى للمنشورات غير المنشورة للقناة
    MAX_POSTS_PER_CHANNEL: int = 30              # حد افتراضي إذا لم توجد خطة
    MIN_PUBLISH_INTERVAL: int = 5                # الحد الأدنى للفاصل الزمني (دقائق)

    # ========== قاعدة البيانات ==========
    DB_TIMEOUT: int = 30

    # ========== الإحالات ==========
    MAX_DAILY_REFERRALS: int = 5
    MAX_GLOBAL_BANNED_WORDS: int = 100

    # ========== الكاش ==========
    CACHE_TTL: int = 30
    AUTH_CACHE_SIZE: int = 2000
    AUTH_CACHE_TTL: int = 15

    # ========== العملة والدفع ==========
    XTR_CURRENCY: str = "XTR"

    # ========== النبض والخلفية ==========
    HEARTBEAT_INTERVAL: int = 300
    ENABLE_SELF_PING: bool = os.getenv("ENABLE_SELF_PING", "true").lower() in ['true', '1']

    # ========== المشرف المجهول ==========
    ANONYMOUS_ADMIN_ID: int = safe_int(os.getenv("ANONYMOUS_ADMIN_ID", "1087968824"))

    # ========== ميزات جديدة ==========
    GIFT_PLANS_ENABLED: bool = os.getenv("GIFT_PLANS_ENABLED", "true").lower() in ['true', '1']
    PENALTY_SYSTEM_ENABLED: bool = os.getenv("PENALTY_SYSTEM_ENABLED", "true").lower() in ['true', '1']
    ENABLE_BANNED_WORDS_CACHE: bool = os.getenv("ENABLE_BANNED_WORDS_CACHE", "true").lower() in ['true', '1']
    BANNED_WORDS_CACHE_TTL: int = safe_int(os.getenv("BANNED_WORDS_CACHE_TTL", "60"))

    def validate(self) -> None:
        """التحقق من القيم المطلوبة"""
        if not self.TOKEN:
            raise ValueError("❌ BOT_TOKEN غير موجود في .env")
        if self.PRIMARY_OWNER_ID == 0:
            raise ValueError("❌ MAIN_ADMIN_ID غير موجود في .env")
        if self.WEB_PORT < 1 or self.WEB_PORT > 65535:
            raise ValueError(f"❌ WEB_PORT غير صالح: {self.WEB_PORT}")

    def is_developer(self, user_id: int) -> bool:
        return user_id == self.PRIMARY_OWNER_ID or user_id in self.DEVELOPER_IDS

    def is_owner(self, user_id: int) -> bool:
        return user_id == self.PRIMARY_OWNER_ID


class PathManager:
    _instance = None

    def __new__(cls):
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

# تحذيرات مبكرة
if not CONFIG.TOKEN:
    logger.warning("⚠️ BOT_TOKEN غير محدد في .env")
if CONFIG.PRIMARY_OWNER_ID == 0:
    logger.warning("⚠️ MAIN_ADMIN_ID غير محدد في .env")

logger.info(f"✅ تم تحميل الإعدادات: {CONFIG.BOT_NAME} (@{CONFIG.BOT_USERNAME})")
logger.info(f"📁 قاعدة البيانات: {PATHS.DB}")

