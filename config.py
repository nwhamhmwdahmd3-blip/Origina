#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
config.py - إعدادات البوت
=========================
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

# تحميل المتغيرات من ملف .env
load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    # ========== الإعدادات الأساسية ==========
    TOKEN: str = os.getenv("BOT_TOKEN", "")
    PRIMARY_OWNER_ID: int = int(os.getenv("MAIN_ADMIN_ID", "0"))
    DEVELOPER_IDS: List[int] = field(default_factory=lambda: [
        int(id.strip()) for id in os.getenv("DEVELOPER_IDS", "").split(",") if id.strip()
    ])
    BOT_NAME: str = os.getenv("BOT_NAME", "ريلاكس مانيجر")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "Reelaaaxbot")
    
    # ========== الإعدادات التقنية ==========
    USE_PROXY: bool = os.getenv("USE_PROXY", "false").lower() in ['true', '1']
    PROXY_URL: str = os.getenv("PROXY_URL", "http://127.0.0.1:10809")
    WEB_PORT: int = int(os.getenv("PORT", "10000"))
    MAX_CONNECTIONS: int = 20
    
    # ========== حدود النظام ==========
    MAX_BACKUPS: int = 20
    DEFAULT_PUBLISH_INTERVAL: int = 720
    MAX_CHANNELS_PER_CYCLE: int = 20
    PUBLISH_RETRY_DELAY: int = 300
    MAX_UNPUBLISHED_POSTS: int = 1000
    DB_TIMEOUT: int = 30
    MAX_DAILY_REFERRALS: int = 5
    MAX_GLOBAL_BANNED_WORDS: int = 100
    
    # ========== إعدادات إضافية ==========
    CACHE_TTL: int = 30
    XTR_CURRENCY: str = "XTR"
    HEARTBEAT_INTERVAL: int = 300
    ENABLE_SELF_PING: bool = os.getenv("ENABLE_SELF_PING", "true").lower() in ['true', '1']
    
    # ========== كاش الصلاحيات ==========
    AUTH_CACHE_SIZE: int = 2000
    AUTH_CACHE_TTL: int = 15
    
    # ========== معرف المشرف المجهول ==========
    ANONYMOUS_ADMIN_ID: int = 1087968824

    # ========== دوال التحقق ==========
    def is_developer(self, user_id: int) -> bool:
        """هل المستخدم مطور؟"""
        return user_id == self.PRIMARY_OWNER_ID or user_id in self.DEVELOPER_IDS

    def is_owner(self, user_id: int) -> bool:
        """هل المستخدم المالك الأساسي؟"""
        return user_id == self.PRIMARY_OWNER_ID


class PathManager:
    """إدارة المسارات"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_paths()
        return cls._instance

    def _init_paths(self):
        self.BASE = Path(__file__).parent.resolve()
        self.DATA = self.BASE / "data"
        self.BACKUPS = self.BASE / "backups"
        self.LOGS = self.BASE / "logs"
        self.DB = self.DATA / "bot_data.db"
        self.LOG_FILE = self.LOGS / "bot.log"
        
        for d in [self.DATA, self.BACKUPS, self.LOGS]:
            d.mkdir(parents=True, exist_ok=True)


# ========== الكائنات الجاهزة ==========
CONFIG = AppConfig()
PATHS = PathManager()
