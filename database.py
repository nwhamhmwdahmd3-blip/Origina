#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
database.py - قاعدة البيانات المتكاملة للبوت (النسخة النهائية المصححة)
- ✅ توحيد وحدات الوقت إلى دقائق في الإعدادات
- ✅ إضافة حد يومي للإحالات
- ✅ إضافة حد أقصى للكلمات المحظورة العامة
- ✅ تحسينات في الأداء (استخدام asyncio.to_thread)
- ✅ جميع الجداول والدوال الأساسية
- ✅ إصلاح دوال الإحالات للتعامل مع عدم وجود بيانات
- ✅ إصلاح get_channels_to_publish لدعم إعادة التدوير التلقائي
- ✅ إعادة تدوير مباشرة عند نفاد المنشورات
- ✅ إضافة جدول user_violations ودوال التصعيد التلقائي
- ✅ استكمال الأعمدة الناقصة في group_security
- ✅ إضافة جدول anonymous_admins ودوال المشرفين المجهولين
- ✅ زيادة طول رموز الإحالة إلى 16 حرف
- ✅ إعادة تعيين عداد الفشل تلقائياً
- ✅ إصلاحات شاملة للأخطاء والاستثناءات
- ✅ إضافة دوال الإدارة والتحقق المطلوبة من handlers_message.py
- ✅ إصلاح مشكلة Deadlock الحرجة
- ✅ إضافة دوال helper للعمل داخل connection موجود
- ✅ تحديث VALID_PENALTY_TYPES لتشمل kick و warn
- ✅ إضافة دالة get_general_stats للوحة الأدمن
- ✅ إضافة خطة تجربة منفصلة
"""

import sqlite3
import json
import logging
import secrets
import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from contextlib import asynccontextmanager

import aiosqlite

from config import PATHS, CONFIG

logger = logging.getLogger(__name__)


class TimeUtils:
    """أدوات الوقت الموحدة"""

    @staticmethod
    def utc_now() -> datetime:
        """الوقت الحالي UTC"""
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def mecca_now() -> datetime:
        """الوقت الحالي بتوقيت مكة"""
        return TimeUtils.utc_now() + timedelta(hours=3)

    @staticmethod
    def utc_iso() -> str:
        """صيغة ISO للوقت UTC"""
        return TimeUtils.utc_now().isoformat()

    @staticmethod
    def mecca_iso() -> str:
        """صيغة ISO للوقت مكة"""
        return TimeUtils.mecca_now().isoformat()

    @staticmethod
    def sql_iso() -> str:
        """صيغة متوافقة مع SQLite للمقارنات"""
        return TimeUtils.utc_now().strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def mecca_to_utc(dt: Optional[datetime]) -> Optional[datetime]:
        """تحويل من مكة إلى UTC"""
        return dt - timedelta(hours=3) if dt else None

    @staticmethod
    def utc_to_mecca(dt: Optional[datetime]) -> Optional[datetime]:
        """تحويل من UTC إلى مكة"""
        return dt + timedelta(hours=3) if dt else None

    @staticmethod
    def safe_parse_iso(date_str: Optional[str]) -> Optional[datetime]:
        """تحويل آمن من نص إلى datetime"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                return dt
            except (ValueError, TypeError):
                return None


class Database:
    """قاعدة البيانات الرئيسية مع Singleton"""

    _instance = None
    _lock = asyncio.Lock()
    _connection_lock = asyncio.Lock()
    _last_violation_cleanup = 0

    VALID_PENALTY_TYPES = {'mute', 'ban', 'restrict', 'kick', 'warn'}
    VALID_REPLY_TYPES = {'text', 'photo', 'video', 'animation', 'document', 'sticker', 'voice', 'video_note'}

    def __new__(cls) -> 'Database':
        """تطبيق Singleton"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @asynccontextmanager
    async def _get_connection(self):
        """الحصول على اتصال بقاعدة البيانات مع الإعدادات"""
        async with self._connection_lock:
            async with aiosqlite.connect(
                str(PATHS.DB),
                timeout=60,
                check_same_thread=False
            ) as conn:
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA foreign_keys=ON")
                await conn.execute("PRAGMA busy_timeout=5000")
                try:
                    yield conn
                    await conn.commit()
                except Exception as e:
                    await conn.rollback()
                    logger.error(f"❌ Database error: {e}", exc_info=True)
                    raise

    # =====================================================================
    # Helper methods للعمل داخل connection موجود (بدون قفل)
    # =====================================================================

    @staticmethod
    async def _execute_in_conn(conn: aiosqlite.Connection, query: str, params: tuple = ()) -> bool:
        """تنفيذ استعلام داخل connection موجود (بدون قفل)"""
        try:
            await conn.execute(query, params)
            return True
        except Exception as e:
            logger.error(f"❌ _execute_in_conn error: {e}", exc_info=True)
            return False

    @staticmethod
    async def _fetchone_in_conn(conn: aiosqlite.Connection, query: str, params: tuple = ()) -> Optional[Dict]:
        """جلب صف واحد من connection موجود (بدون قفل)"""
        try:
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ _fetchone_in_conn error: {e}", exc_info=True)
            return None

    @staticmethod
    async def _fetchall_in_conn(conn: aiosqlite.Connection, query: str, params: tuple = ()) -> List[Dict]:
        """جلب جميع الصفوف من connection موجود (بدون قفل)"""
        try:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ _fetchall_in_conn error: {e}", exc_info=True)
            return []

    @staticmethod
    async def _fetchval_in_conn(conn: aiosqlite.Connection, query: str, params: tuple = (), default: Any = None) -> Any:
        """جلب قيمة واحدة من connection موجود (بدون قفل)"""
        try:
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            return row[0] if row else default
        except Exception as e:
            logger.error(f"❌ _fetchval_in_conn error: {e}", exc_info=True)
            return default

    # =====================================================================
    # الدوال العامة للاستعلامات
    # =====================================================================

    async def execute(self, query: str, params: tuple = ()) -> bool:
        """تنفيذ استعلام بدون نتيجة"""
        try:
            async with self._get_connection() as conn:
                await conn.execute(query, params)
            return True
        except Exception as e:
            logger.error(f"❌ Execute error: {e}\nQuery: {query[:200]}", exc_info=True)
            return False

    async def fetchone(self, query: str, params: tuple = ()) -> Optional[Dict]:
        """جلب صف واحد"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(query, params) as cur:
                    row = await cur.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Fetchone error: {e}\nQuery: {query[:200]}", exc_info=True)
            return None

    async def fetchall(self, query: str, params: tuple = ()) -> List[Dict]:
        """جلب جميع الصفوف"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(query, params) as cur:
                    rows = await cur.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Fetchall error: {e}\nQuery: {query[:200]}", exc_info=True)
            return []

    async def fetchval(self, query: str, params: tuple = (), default: Any = None) -> Any:
        """جلب قيمة واحدة"""
        try:
            async with self._get_connection() as conn:
                async with conn.execute(query, params) as cur:
                    row = await cur.fetchone()
                    return row[0] if row else default
        except Exception as e:
            logger.error(f"❌ Fetchval error: {e}\nQuery: {query[:200]}", exc_info=True)
            return default

    async def executemany(self, query: str, params: List[tuple]) -> bool:
        """تنفيذ استعلامات متعددة"""
        if not params:
            return True
        try:
            async with self._get_connection() as conn:
                await conn.executemany(query, params)
            return True
        except Exception as e:
            logger.error(f"❌ Executemany error: {e}\nQuery: {query[:200]}", exc_info=True)
            return False

    async def initialize(self) -> bool:
        """تهيئة قاعدة البيانات"""
        try:
            async with self._get_connection() as conn:
                await self._create_tables(conn)
                await self._create_indexes(conn)
                await self._init_default_data(conn)
                await self._import_banned_words(conn)
            logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")
            return True
        except Exception as e:
            logger.error(f"❌ فشل تهيئة قاعدة البيانات: {e}", exc_info=True)
            return False

    async def _create_tables(self, conn: aiosqlite.Connection) -> None:
        """إنشاء جميع الجداول"""

        # جدول المستخدمين
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
                referral_code TEXT UNIQUE,
                created_at TEXT,
                updated_at TEXT,
                active_channel INTEGER
            )
        """)

        # جدول قنوات المستخدمين
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id INTEGER,
                channel_name TEXT,
                banned INTEGER DEFAULT 0,
                created_at TEXT,
                UNIQUE(user_id, channel_id)
            )
        """)

        # جدول المنشورات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_db_id INTEGER,
                text TEXT,
                media_type TEXT,
                media_file_id TEXT,
                published INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                created_at TEXT,
                published_at TEXT,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id) ON DELETE CASCADE
            )
        """)

        # جدول الجدولة
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
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id) ON DELETE CASCADE
            )
        """)

        # جدول آخر نشر
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS last_publish (
                channel_db_id INTEGER PRIMARY KEY,
                last_publish_time TEXT,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id) ON DELETE CASCADE
            )
        """)

        # جدول مجموعات البوت
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

        # جدول ربط المستخدمين بالمجموعات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_groups_link (
                user_id INTEGER,
                chat_id INTEGER,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # جدول مشرفي المجموعات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_admins (
                chat_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        # جدول الملاك المخفيين
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_owner_groups (
                chat_id INTEGER,
                owner_id INTEGER,
                is_hidden INTEGER DEFAULT 1,
                PRIMARY KEY (chat_id, owner_id)
            )
        """)

        # جدول المشرفين المخفيين
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_admins (
                chat_id INTEGER,
                admin_id INTEGER,
                added_by INTEGER,
                added_at TEXT,
                PRIMARY KEY (chat_id, admin_id)
            )
        """)

        # جدول المشرفين المجهولين
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS anonymous_admins (
                chat_id INTEGER NOT NULL,
                anonymous_id INTEGER NOT NULL,
                added_by INTEGER,
                added_at TEXT,
                PRIMARY KEY (chat_id, anonymous_id)
            )
        """)

        # جدول إعدادات الأمان للمجموعات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_security (
                chat_id INTEGER PRIMARY KEY,
                delete_links INTEGER DEFAULT 0,
                mentions INTEGER DEFAULT 0,
                slow_mode INTEGER DEFAULT 0,
                slow_mode_seconds INTEGER DEFAULT 5,
                welcome_enabled INTEGER DEFAULT 0,
                welcome_text TEXT DEFAULT 'مرحباً {user} في {chat} 🤍',
                goodbye_enabled INTEGER DEFAULT 0,
                goodbye_text TEXT DEFAULT 'وداعاً {user} 👋',
                delete_banned_words INTEGER DEFAULT 0,
                auto_penalty TEXT DEFAULT 'none',
                auto_mute_duration INTEGER DEFAULT 3600,
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
                delete_photos INTEGER DEFAULT 0,
                delete_penalty TEXT DEFAULT 'none',
                delete_penalty_duration INTEGER DEFAULT 0,
                delete_penalty_messages INTEGER DEFAULT 0,
                antiflood_enabled INTEGER DEFAULT 0,
                antiflood_messages INTEGER DEFAULT 5,
                antiflood_seconds INTEGER DEFAULT 10,
                antiflood_penalty TEXT DEFAULT 'mute',
                max_warnings INTEGER DEFAULT 3,
                warn_penalty TEXT DEFAULT 'ban',
                warn_enabled INTEGER DEFAULT 0,
                max_message_length INTEGER DEFAULT 0,
                night_mode_enabled INTEGER DEFAULT 0,
                night_mode_start TEXT DEFAULT '23:00',
                night_mode_end TEXT DEFAULT '06:00',
                night_mode_action TEXT DEFAULT 'mute',
                nsfw_enabled INTEGER DEFAULT 0,
                nsfw_threshold REAL DEFAULT 0.7,
                nsfw_filter INTEGER DEFAULT 0,
                auto_approve_join INTEGER DEFAULT 0,
                auto_reject_join INTEGER DEFAULT 0,
                mute_default_duration INTEGER DEFAULT 3600,
                ban_default_duration INTEGER DEFAULT 0,
                warn_default_duration INTEGER DEFAULT 0,
                restrict_default_duration INTEGER DEFAULT 1800,
                enable_timed_penalties INTEGER DEFAULT 1,
                auto_remove_penalties INTEGER DEFAULT 1,
                violation_strikes INTEGER DEFAULT 3,
                violation_duration INTEGER DEFAULT 60
            )
        """)

        # جدول قفل الدردشات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_locks (
                chat_id INTEGER PRIMARY KEY,
                locked INTEGER DEFAULT 0,
                locked_at TEXT,
                locked_by INTEGER
            )
        """)

        # جدول الكلمات المحظورة
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

        # جدول الردود التلقائية
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_replies (
                chat_id INTEGER,
                keyword TEXT,
                reply TEXT,
                reply_type TEXT DEFAULT 'text',
                reply_media_id TEXT,
                reply_buttons TEXT,
                created_at TEXT,
                is_active INTEGER DEFAULT 1,
                usage_count INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, keyword)
            )
        """)

        # جدول إعدادات الردود التلقائية
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_reply_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                only_admins INTEGER DEFAULT 0,
                ignore_bots INTEGER DEFAULT 1,
                updated_at TEXT
            )
        """)

        # جدول تذاكر الدعم
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                message TEXT,
                media_type TEXT,
                media_file_id TEXT,
                ticket_number INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                replied INTEGER DEFAULT 0
            )
        """)

        # جدول مشرفي البوت
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TEXT
            )
        """)

        # جدول الإعدادات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # إعدادات افتراضية
        default_settings = [
            ('publish_interval', '12'),
            ('auto_backup', '1'),
            ('last_ticket_number', '0'),
            ('last_backup', ''),
        ]
        for key, value in default_settings:
            await conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )

        # جدول الإحالات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                created_at TEXT,
                UNIQUE(referrer_id, referred_id)
            )
        """)

        # جدول مكافآت الإحالات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_rewards (
                user_id INTEGER PRIMARY KEY,
                referral_count INTEGER DEFAULT 0,
                total_reward_days INTEGER DEFAULT 0,
                claimed_reward_days INTEGER DEFAULT 0,
                last_referral_date TEXT
            )
        """)

        # جدول إعدادات التذكير
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_reminder_settings (
                user_id INTEGER PRIMARY KEY,
                subscription_reminder INTEGER DEFAULT 1,
                daily_stats_reminder INTEGER DEFAULT 0,
                weekly_report INTEGER DEFAULT 1,
                reminder_days_before INTEGER DEFAULT 3,
                last_reminder_sent TEXT,
                notification_lang TEXT DEFAULT 'ar'
            )
        """)

        # جدول الترجمة
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_translation (
                user_id INTEGER PRIMARY KEY,
                lang TEXT DEFAULT 'off'
            )
        """)

        # جدول المسابقات
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

        # جدول مشاركي المسابقات
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

        # جدول فائزي المسابقات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contest_winners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER,
                winner_id INTEGER,
                announced_at TEXT
            )
        """)

        # جدول سجلات المشرفين
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                admin_id INTEGER,
                action TEXT,
                target_id INTEGER,
                reason TEXT,
                created_at TEXT
            )
        """)

        # جدول تحذيرات المستخدمين
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_warnings (
                user_id INTEGER,
                chat_id INTEGER,
                warnings INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # جدول تتبع المخالفات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_violations (
                user_id INTEGER,
                chat_id INTEGER,
                violation_count INTEGER DEFAULT 0,
                last_violation_time TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # جدول قواعد المجموعات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_rules (
                chat_id INTEGER PRIMARY KEY,
                rules_text TEXT,
                updated_by INTEGER,
                updated_at TEXT
            )
        """)

        # جدول رسائل المستخدمين
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_messages (
                user_id INTEGER,
                chat_id INTEGER,
                message_time TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)

        # جدول المنشورات المجدولة
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                text TEXT,
                publish_time TEXT,
                fail_count INTEGER DEFAULT 0
            )
        """)

        # جدول سجل المشاعر
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                text_encrypted BLOB,
                sentiment TEXT,
                score REAL,
                created_at TEXT
            )
        """)

        # جدول الباقات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                price INTEGER,
                currency TEXT DEFAULT 'XTR',
                duration_days INTEGER,
                max_channels INTEGER,
                max_posts INTEGER,
                features TEXT,
                is_active INTEGER DEFAULT 1,
                is_gift INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)

        # جدول الاشتراكات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                plan_id INTEGER,
                status TEXT DEFAULT 'active',
                start_date TEXT,
                end_date TEXT,
                auto_renew INTEGER DEFAULT 0,
                provider TEXT DEFAULT 'xtr',
                provider_subscription_id TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            )
        """)

        # جدول الفواتير
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT UNIQUE,
                user_id INTEGER,
                plan_id INTEGER,
                amount INTEGER,
                currency TEXT DEFAULT 'XTR',
                status TEXT DEFAULT 'pending',
                provider TEXT DEFAULT 'xtr',
                provider_payment_id TEXT,
                paid_at TEXT,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            )
        """)

        # جدول سجلات الدفع
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payment_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                provider TEXT DEFAULT 'xtr',
                event_type TEXT,
                data TEXT,
                created_at TEXT
            )
        """)

        # جدول عقوبات المستخدمين
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_penalties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                penalty_type TEXT,
                duration INTEGER,
                start_time TEXT,
                end_time TEXT,
                reason TEXT,
                issued_by INTEGER,
                status TEXT DEFAULT 'active',
                created_at TEXT
            )
        """)

        # جدول قواعد العقوبات للمخالفات
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS violation_penalties (
                chat_id INTEGER NOT NULL,
                violation_type TEXT NOT NULL,
                penalty_type TEXT NOT NULL DEFAULT 'mute',
                duration_seconds INTEGER DEFAULT 3600,
                PRIMARY KEY (chat_id, violation_type)
            )
        """)

        # جدول أكواد الهدايا
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gift_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                plan_id INTEGER,
                creator_id INTEGER,
                used_by INTEGER,
                used_at TEXT,
                created_at TEXT,
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            )
        """)

        # جدول نقاط المستخدمين
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_points (
                user_id INTEGER PRIMARY KEY,
                points INTEGER DEFAULT 0,
                last_updated TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)

    async def _create_indexes(self, conn: aiosqlite.Connection) -> None:
        """إنشاء جميع الفهارس"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_banned ON users(banned)",
            "CREATE INDEX IF NOT EXISTS idx_users_language ON users(language)",
            "CREATE INDEX IF NOT EXISTS idx_users_subscription ON users(subscription_end)",
            "CREATE INDEX IF NOT EXISTS idx_users_updated ON users(updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_users_referral ON users(referral_code)",
            "CREATE INDEX IF NOT EXISTS idx_uc_user ON user_channels(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_uc_active ON user_channels(banned)",
            "CREATE INDEX IF NOT EXISTS idx_uc_channel_id ON user_channels(channel_id)",
            "CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)",
            "CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)",
            "CREATE INDEX IF NOT EXISTS idx_posts_fail ON posts(fail_count)",
            "CREATE INDEX IF NOT EXISTS idx_posts_channel_published ON posts(channel_db_id, published)",
            "CREATE INDEX IF NOT EXISTS idx_sched_next ON schedule(next_publish_date)",
            "CREATE INDEX IF NOT EXISTS idx_groups_banned ON bot_groups(banned)",
            "CREATE INDEX IF NOT EXISTS idx_group_admins_user ON group_admins(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_group_admins_chat ON group_admins(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_security_chat ON group_security(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_banned_words_chat ON banned_words(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_banned_words_word ON banned_words(word)",
            "CREATE INDEX IF NOT EXISTS idx_user_warnings_user ON user_warnings(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_warnings_chat ON user_warnings(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_violations_user ON user_violations(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_violations_chat ON user_violations(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_admin_logs_chat ON admin_logs(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_admin_logs_admin ON admin_logs(admin_id)",
            "CREATE INDEX IF NOT EXISTS idx_admin_logs_created ON admin_logs(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_ar_chat ON auto_replies(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_ar_keyword ON auto_replies(keyword)",
            "CREATE INDEX IF NOT EXISTS idx_auto_replies_lookup ON auto_replies(chat_id, keyword, is_active)",
            "CREATE INDEX IF NOT EXISTS idx_tickets_user ON support_tickets(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status)",
            "CREATE INDEX IF NOT EXISTS idx_tickets_number ON support_tickets(ticket_number)",
            "CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_sub_status ON subscriptions(status)",
            "CREATE INDEX IF NOT EXISTS idx_sub_end ON subscriptions(end_date)",
            "CREATE INDEX IF NOT EXISTS idx_sub_user_status_end ON subscriptions(user_id, status, end_date)",
            "CREATE INDEX IF NOT EXISTS idx_inv_user ON invoices(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_inv_status ON invoices(status)",
            "CREATE INDEX IF NOT EXISTS idx_inv_number ON invoices(number)",
            "CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)",
            "CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id)",
            "CREATE INDEX IF NOT EXISTS idx_referrals_created ON referrals(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status)",
            "CREATE INDEX IF NOT EXISTS idx_contests_end ON contests(end_date)",
            "CREATE INDEX IF NOT EXISTS idx_contest_participants_contest ON contest_participants(contest_id)",
            "CREATE INDEX IF NOT EXISTS idx_contest_participants_user ON contest_participants(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_reminders_user ON user_reminder_settings(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_penalties_user ON user_penalties(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_penalties_chat ON user_penalties(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_penalties_status ON user_penalties(status)",
            "CREATE INDEX IF NOT EXISTS idx_penalties_user_chat_status ON user_penalties(user_id, chat_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_penalties_chat_status ON user_penalties(chat_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_penalties_end_time ON user_penalties(end_time)",
            "CREATE INDEX IF NOT EXISTS idx_points_user ON user_points(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_anonymous_admins_chat ON anonymous_admins(chat_id)",
        ]
        for query in indexes:
            try:
                await conn.execute(query)
            except Exception as e:
                logger.warning(f"⚠️ فشل إنشاء فهرس: {e}")

    async def _init_default_data(self, conn: aiosqlite.Connection) -> None:
        """تهيئة البيانات الافتراضية"""
        default_plans = [
            {"name": "تجربة", "description": "تجربة مجانية لمدة 30 يوم", "price": 0, "duration_days": 30, "max_channels": 3, "max_posts": 200, "features": '{"auto_publish":true,"security":true}', "is_gift": 0},
            {"name": "يوم", "description": "باقة يوم واحد", "price": 5, "duration_days": 1, "max_channels": 1, "max_posts": 50, "features": '{"auto_publish":true}', "is_gift": 0},
            {"name": "أسبوع", "description": "باقة 7 أيام", "price": 25, "duration_days": 7, "max_channels": 3, "max_posts": 300, "features": '{"auto_publish":true,"security":true}', "is_gift": 0},
            {"name": "شهر", "description": "باقة 30 يوم", "price": 75, "duration_days": 30, "max_channels": 10, "max_posts": 1500, "features": '{"auto_publish":true,"security":true,"support":true}', "is_gift": 0},
            {"name": "3 أشهر", "description": "باقة 90 يوم", "price": 200, "duration_days": 90, "max_channels": 25, "max_posts": 5000, "features": '{"auto_publish":true,"security":true,"support":true,"analytics":true}', "is_gift": 0},
            {"name": "سنة", "description": "باقة 365 يوم", "price": 700, "duration_days": 365, "max_channels": 100, "max_posts": 99999, "features": '{"auto_publish":true,"security":true,"support":true,"analytics":true,"priority":true}', "is_gift": 0},
            {"name": "هدية شهر", "description": "كود هدية لمدة 30 يوم", "price": 75, "duration_days": 30, "max_channels": 10, "max_posts": 1500, "features": '{}', "is_gift": 1},
        ]
        for plan in default_plans:
            cursor = await conn.execute("SELECT id FROM plans WHERE name = ?", (plan["name"],))
            existing = await cursor.fetchone()
            if not existing:
                await conn.execute(
                    """INSERT INTO plans 
                       (name, description, price, currency, duration_days, max_channels, max_posts, features, is_active, is_gift, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (plan["name"], plan["description"], plan["price"], "XTR",
                     plan["duration_days"], plan["max_channels"], plan["max_posts"],
                     plan["features"], 1, plan["is_gift"], TimeUtils.sql_iso())
                )

    async def _import_banned_words(self, conn: aiosqlite.Connection) -> None:
        """استيراد الكلمات المحظورة من الملف"""
        try:
            from banned_words import BANNED_WORDS
            if not BANNED_WORDS:
                return
            imported = 0
            for word in BANNED_WORDS:
                word = str(word).strip().lower()
                if len(word) < 2:
                    continue
                await conn.execute(
                    "INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?,?,?,?)",
                    (word, -1, CONFIG.PRIMARY_OWNER_ID, TimeUtils.sql_iso())
                )
                imported += 1
            logger.info(f"✅ تم استيراد {imported} كلمة محظورة من ملف banned_words.py")
        except ImportError:
            logger.info("ℹ️ لا يوجد ملف banned_words.py، سيتم تخطي استيراد الكلمات المحظورة")
        except Exception as e:
            logger.error(f"❌ خطأ في استيراد الكلمات المحظورة: {e}")

    # =====================================================================
    # دوال المستخدمين
    # =====================================================================

    async def register_user(self, user_id: int, username: str = "", first_name: str = "") -> bool:
        try:
            code = secrets.token_urlsafe(16)
            async with self._get_connection() as conn:
                await conn.execute(
                    """INSERT INTO users 
                       (user_id, username, first_name, referral_code, trial_used, created_at, updated_at) 
                       VALUES (?,?,?,?,0,?,?)
                       ON CONFLICT(user_id) DO UPDATE SET
                           username = CASE WHEN excluded.username != '' THEN excluded.username ELSE users.username END,
                           first_name = CASE WHEN excluded.first_name != '' THEN excluded.first_name ELSE users.first_name END,
                           updated_at = excluded.updated_at""",
                    (user_id, username, first_name, code, TimeUtils.sql_iso(), TimeUtils.sql_iso())
                )
                await conn.execute("INSERT OR IGNORE INTO user_points (user_id, points, last_updated) VALUES (?,0,?)", (user_id, TimeUtils.sql_iso()))
                await conn.execute("INSERT OR IGNORE INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days, last_referral_date) VALUES (?, 0, 0, 0, NULL)", (user_id,))
            return True
        except Exception as e:
            logger.error(f"❌ Error in register_user: {e}", exc_info=True)
            return False

    async def get_user(self, user_id: int) -> Optional[Dict]:
        return await self.fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))

    async def get_user_language(self, user_id: int) -> str:
        result = await self.fetchval("SELECT language FROM users WHERE user_id = ?", (user_id,), default='ar')
        return result if result else 'ar'

    async def set_user_language(self, user_id: int, lang: str) -> bool:
        return await self.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))

    async def get_auto_publish_status(self, user_id: int) -> bool:
        result = await self.fetchval("SELECT auto_publish FROM users WHERE user_id = ?", (user_id,), default=1)
        return result == 1

    async def set_auto_publish(self, user_id: int, status: bool) -> bool:
        return await self.execute("UPDATE users SET auto_publish = ? WHERE user_id = ?", (1 if status else 0, user_id))

    async def get_auto_recycle_status(self, user_id: int) -> bool:
        result = await self.fetchval("SELECT auto_recycle FROM users WHERE user_id = ?", (user_id,), default=1)
        return result == 1

    async def set_auto_recycle(self, user_id: int, status: bool) -> bool:
        return await self.execute("UPDATE users SET auto_recycle = ? WHERE user_id = ?", (1 if status else 0, user_id))

    async def is_user_banned(self, user_id: int) -> bool:
        result = await self.fetchval("SELECT banned FROM users WHERE user_id = ?", (user_id,), default=0)
        return result == 1

    async def ban_user(self, user_id: int) -> bool:
        return await self.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (user_id,))

    async def unban_user(self, user_id: int) -> bool:
        return await self.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (user_id,))

    async def get_all_users(self) -> List[Dict]:
        return await self.fetchall("SELECT user_id, banned FROM users ORDER BY user_id")

    async def get_user_stats(self) -> Dict:
        total = await self.fetchval("SELECT COUNT(*) FROM users", default=0)
        banned = await self.fetchval("SELECT COUNT(*) FROM users WHERE banned = 1", default=0)
        return {'users': total, 'banned': banned}

    async def has_active_subscription(self, user_id: int) -> bool:
        result = await self.fetchval(
            "SELECT 1 FROM subscriptions WHERE user_id = ? AND status = 'active' AND end_date > datetime('now') LIMIT 1",
            (user_id,)
        )
        return result is not None

    async def has_used_trial(self, user_id: int) -> bool:
        result = await self.fetchval("SELECT trial_used FROM users WHERE user_id = ?", (user_id,), default=0)
        return result == 1

    async def activate_trial(self, user_id: int) -> int:
        try:
            async with self._lock:
                now = TimeUtils.utc_now()
                trial_end = now + timedelta(days=30)
                
                # البحث عن خطة التجربة
                trial_plan_id = await self.fetchval("SELECT id FROM plans WHERE name = 'تجربة' AND is_active = 1", default=1)
                
                async with self._get_connection() as conn:
                    current_end = await self._fetchval_in_conn(
                        conn,
                        "SELECT MAX(end_date) FROM subscriptions WHERE user_id = ? AND status = 'active' AND end_date > datetime('now')",
                        (user_id,)
                    )
                    current_end_dt = TimeUtils.safe_parse_iso(current_end) if current_end else None
                    
                    if current_end_dt and current_end_dt > trial_end:
                        new_end = current_end_dt
                        days_granted = 0
                    else:
                        new_end = trial_end
                        days_granted = 30
                    
                    if days_granted > 0:
                        await conn.execute(
                            "UPDATE users SET trial_used = 1, subscription_end = ? WHERE user_id = ?",
                            (new_end.strftime('%Y-%m-%d %H:%M:%S'), user_id)
                        )
                        await conn.execute(
                            """INSERT INTO subscriptions 
                               (user_id, plan_id, status, start_date, end_date, provider, created_at, updated_at)
                               VALUES (?,?,?,?,?,?,?,?)""",
                            (user_id, trial_plan_id, 'active', TimeUtils.sql_iso(), new_end.strftime('%Y-%m-%d %H:%M:%S'), 'trial', TimeUtils.sql_iso(), TimeUtils.sql_iso())
                        )
                    else:
                        await conn.execute(
                            "UPDATE users SET subscription_end = ? WHERE user_id = ?",
                            (current_end_dt.strftime('%Y-%m-%d %H:%M:%S'), user_id)
                        )
                return days_granted
        except Exception as e:
            logger.error(f"❌ Error in activate_trial: {e}", exc_info=True)
            return 0

    async def get_referral_code(self, user_id: int) -> str:
        result = await self.fetchval("SELECT referral_code FROM users WHERE user_id = ?", (user_id,), default=f"ref_{user_id}")
        return result if result else f"ref_{user_id}"

    async def get_user_by_referral_code(self, code: str) -> Optional[int]:
        return await self.fetchval("SELECT user_id FROM users WHERE referral_code = ?", (code,))

    async def get_active_subscription(self, user_id: int) -> Optional[Dict]:
        return await self.fetchone(
            """SELECT s.*, p.name, p.duration_days, p.max_channels, p.max_posts, p.features
               FROM subscriptions s
               JOIN plans p ON s.plan_id = p.id AND p.is_active = 1
               WHERE s.user_id = ? AND s.status = 'active' AND s.end_date > datetime('now')
               ORDER BY p.max_channels DESC, p.max_posts DESC, s.end_date DESC
               LIMIT 1""",
            (user_id,)
        )

    async def get_active_plan(self, user_id: int) -> Optional[Dict]:
        sub = await self.get_active_subscription(user_id)
        if sub:
            return await self.get_plan(sub['plan_id'])
        return None

    async def get_subscription_end(self, user_id: int) -> Optional[datetime]:
        result = await self.fetchval("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
        return TimeUtils.safe_parse_iso(result) if result else None

    # =====================================================================
    # دوال القنوات
    # =====================================================================

    async def add_channel(self, user_id: int, channel_id: int, channel_name: str) -> Optional[int]:
        try:
            channel_id = int(channel_id)
            async with self._lock:
                async with self._get_connection() as conn:
                    cursor = await conn.execute(
                        """SELECT p.max_channels
                           FROM subscriptions s
                           JOIN plans p ON s.plan_id = p.id
                           WHERE s.user_id = ? AND s.status = 'active' AND s.end_date > datetime('now')
                           ORDER BY p.max_channels DESC, p.max_posts DESC, s.end_date DESC
                           LIMIT 1""",
                        (user_id,)
                    )
                    plan_row = await cursor.fetchone()
                    if not plan_row:
                        return None
                    if plan_row['max_channels'] is not None:
                        cursor = await conn.execute("SELECT COUNT(*) FROM user_channels WHERE user_id = ? AND banned = 0", (user_id,))
                        count_row = await cursor.fetchone()
                        if count_row[0] >= plan_row['max_channels']:
                            return None
                    cursor = await conn.execute("SELECT id FROM user_channels WHERE user_id = ? AND channel_id = ?", (user_id, channel_id))
                    existing = await cursor.fetchone()
                    is_new = existing is None
                    if is_new:
                        cursor = await conn.execute(
                            "INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) VALUES (?,?,?,?)",
                            (user_id, channel_id, channel_name, TimeUtils.sql_iso())
                        )
                        ch_db_id = cursor.lastrowid
                    else:
                        ch_db_id = existing['id']
                        await conn.execute("UPDATE user_channels SET channel_name = ?, banned = 0 WHERE id = ?", (channel_name, ch_db_id))
                    await conn.execute(
                        """INSERT INTO schedule (channel_db_id, schedule_type, interval_minutes, next_publish_date)
                           VALUES (?, 'interval_minutes', 12, ?)
                           ON CONFLICT(channel_db_id) DO NOTHING""",
                        (ch_db_id, (TimeUtils.utc_now() + timedelta(minutes=12)).strftime('%Y-%m-%d %H:%M:%S'))
                    )
                    if is_new:
                        await conn.execute(
                            """INSERT INTO user_points (user_id, points, last_updated)
                               VALUES (?, 10, ?)
                               ON CONFLICT(user_id) DO UPDATE SET points = points + 10, last_updated = ?""",
                            (user_id, TimeUtils.sql_iso(), TimeUtils.sql_iso())
                        )
                    return ch_db_id
        except Exception as e:
            logger.error(f"❌ Error in add_channel: {e}", exc_info=True)
            return None

    async def get_user_channels(self, user_id: int) -> List[Dict]:
        return await self.fetchall("SELECT id, channel_id, channel_name, banned, created_at FROM user_channels WHERE user_id = ? ORDER BY created_at DESC", (user_id,))

    async def get_active_channel(self, user_id: int) -> Optional[int]:
        result = await self.fetchval("SELECT active_channel FROM users WHERE user_id = ?", (user_id,))
        if result:
            banned = await self.fetchval("SELECT banned FROM user_channels WHERE id = ? AND user_id = ?", (result, user_id), default=1)
            if banned == 0:
                return result
        return await self.fetchval("SELECT id FROM user_channels WHERE user_id = ? AND banned = 0 ORDER BY id LIMIT 1", (user_id,))

    async def set_active_channel(self, user_id: int, channel_db_id: int) -> bool:
        exists = await self.fetchval("SELECT 1 FROM user_channels WHERE id = ? AND user_id = ? AND banned = 0", (channel_db_id, user_id))
        if not exists:
            return False
        return await self.execute("UPDATE users SET active_channel = ? WHERE user_id = ?", (channel_db_id, user_id))

    async def delete_channel(self, user_id: int, channel_db_id: int) -> bool:
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("DELETE FROM user_channels WHERE id = ? AND user_id = ?", (channel_db_id, user_id))
                if cursor.rowcount > 0:
                    await conn.execute("UPDATE users SET active_channel = NULL WHERE user_id = ? AND active_channel = ?", (user_id, channel_db_id))
                    return True
                return False
        except Exception as e:
            logger.error(f"❌ Error in delete_channel: {e}", exc_info=True)
            return False

    async def get_channel_info(self, user_id: int, channel_db_id: int) -> Optional[Dict]:
        return await self.fetchone("SELECT * FROM user_channels WHERE id = ? AND user_id = ?", (channel_db_id, user_id))

    async def get_channel_stats(self, user_id: int, channel_db_id: int) -> Dict:
        exists = await self.fetchval("SELECT 1 FROM user_channels WHERE id = ? AND user_id = ?", (channel_db_id, user_id))
        if not exists:
            return {'total': 0, 'published': 0, 'unpublished': 0}
        total = await self.fetchval("SELECT COUNT(*) FROM posts WHERE channel_db_id = ?", (channel_db_id,), default=0)
        published = await self.fetchval("SELECT COUNT(*) FROM posts WHERE channel_db_id = ? AND published = 1", (channel_db_id,), default=0)
        return {'total': total, 'published': published, 'unpublished': total - published}

    async def get_channel_by_user(self, user_id: int, channel_id: int) -> Optional[Dict]:
        return await self.fetchone("SELECT * FROM user_channels WHERE user_id = ? AND channel_id = ?", (user_id, channel_id))

    # =====================================================================
    # دوال المنشورات
    # =====================================================================

    async def add_posts(self, user_id: int, channel_db_id: int, posts: List[Tuple[str, str, str]]) -> int:
        try:
            if not posts:
                return 0
            async with self._lock:
                async with self._get_connection() as conn:
                    cursor = await conn.execute("SELECT 1 FROM user_channels WHERE id = ? AND user_id = ? AND banned = 0", (channel_db_id, user_id))
                    if not await cursor.fetchone():
                        return 0
                    cursor = await conn.execute(
                        """SELECT p.max_posts
                           FROM subscriptions s
                           JOIN plans p ON s.plan_id = p.id
                           WHERE s.user_id = ? AND s.status = 'active' AND s.end_date > datetime('now')
                           ORDER BY p.max_channels DESC, p.max_posts DESC, s.end_date DESC
                           LIMIT 1""",
                        (user_id,)
                    )
                    plan_row = await cursor.fetchone()
                    if not plan_row:
                        return 0
                    if plan_row['max_posts'] is not None:
                        cursor = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id = ?", (channel_db_id,))
                        count_row = await cursor.fetchone()
                        if count_row[0] + len(posts) > plan_row['max_posts']:
                            return 0
                    total = 0
                    for i in range(0, len(posts), 100):
                        batch = posts[i:i+100]
                        vals = [(channel_db_id, (t or "")[:4096], m, f, TimeUtils.sql_iso()) for t, m, f in batch]
                        await conn.executemany(
                            "INSERT INTO posts (channel_db_id, text, media_type, media_file_id, created_at) VALUES (?,?,?,?,?)",
                            vals
                        )
                        total += len(vals)
                    return total
        except Exception as e:
            logger.error(f"❌ Error in add_posts: {e}", exc_info=True)
            return 0

    async def get_next_post(self, channel_db_id: int) -> Optional[Dict]:
        post = await self.fetchone(
            """SELECT p.id, p.text, p.media_type, p.media_file_id, p.fail_count
               FROM posts p
               JOIN user_channels uc ON p.channel_db_id = uc.id
               WHERE p.channel_db_id = ? AND p.published = 0
                 AND (p.fail_count IS NULL OR p.fail_count < 3)
                 AND uc.banned = 0
               ORDER BY p.created_at ASC LIMIT 1""",
            (channel_db_id,)
        )
        if post:
            if post.get('fail_count', 0) > 0:
                await self.execute("UPDATE posts SET fail_count = 0 WHERE id = ?", (post['id'],))
            return post
        auto_recycle = await self.fetchval(
            """SELECT u.auto_recycle FROM users u
               JOIN user_channels uc ON u.user_id = uc.user_id
               WHERE uc.id = ?""",
            (channel_db_id,),
            default=1
        )
        if auto_recycle != 1:
            return None
        await self.execute("UPDATE posts SET published = 0, published_at = NULL, fail_count = 0 WHERE channel_db_id = ? AND published = 1", (channel_db_id,))
        post = await self.fetchone(
            "SELECT p.id, p.text, p.media_type, p.media_file_id, p.fail_count FROM posts p WHERE p.channel_db_id = ? AND p.published = 0 ORDER BY p.created_at ASC LIMIT 1",
            (channel_db_id,)
        )
        if post and post.get('fail_count', 0) > 0:
            await self.execute("UPDATE posts SET fail_count = 0 WHERE id = ?", (post['id'],))
        return post

    async def mark_post_published(self, post_id: int) -> bool:
        return await self.execute("UPDATE posts SET published = 1, published_at = ? WHERE id = ?", (TimeUtils.sql_iso(), post_id))

    async def increment_post_fail(self, post_id: int) -> bool:
        return await self.execute("UPDATE posts SET fail_count = fail_count + 1 WHERE id = ?", (post_id,))

    async def delete_post(self, user_id: int, post_id: int, channel_db_id: int) -> bool:
        exists = await self.fetchval("SELECT 1 FROM user_channels WHERE id = ? AND user_id = ?", (channel_db_id, user_id))
        if not exists:
            return False
        return await self.execute("DELETE FROM posts WHERE id = ? AND channel_db_id = ?", (post_id, channel_db_id))

    async def reset_posts(self, user_id: int, channel_db_id: int) -> int:
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("SELECT 1 FROM user_channels WHERE id = ? AND user_id = ? AND banned = 0", (channel_db_id, user_id))
                if not await cursor.fetchone():
                    return 0
                await conn.execute("UPDATE posts SET published = 0, fail_count = 0 WHERE channel_db_id = ?", (channel_db_id,))
                cursor = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id = ? AND published = 0", (channel_db_id,))
                row = await cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"❌ Error in reset_posts: {e}", exc_info=True)
            return 0

    # =====================================================================
    # دوال المجموعات
    # =====================================================================

    async def register_group(self, chat_id: int, chat_name: str, user_id: int, username: str = None) -> bool:
        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    """INSERT INTO bot_groups (chat_id, chat_name, username, added_by, added_at)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(chat_id) DO UPDATE SET
                           chat_name = excluded.chat_name,
                           username = excluded.username,
                           updated_at = ?""",
                    (chat_id, chat_name, username, user_id, TimeUtils.sql_iso(), TimeUtils.sql_iso())
                )
                await conn.execute("INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?,?)", (user_id, chat_id))
                logger.info(f"✅ تم تسجيل المجموعة {chat_id} بواسطة المستخدم {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error in register_group: {e}", exc_info=True)
            return False

    async def get_user_groups(self, user_id: int) -> List[Dict]:
        return await self.fetchall(
            """SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned
               FROM bot_groups bg
               WHERE bg.added_by = ?
                  OR bg.chat_id IN (
                      SELECT chat_id FROM user_groups_link WHERE user_id = ?
                      UNION
                      SELECT chat_id FROM hidden_owner_groups WHERE owner_id = ?
                      UNION
                      SELECT chat_id FROM hidden_admins WHERE admin_id = ?
                      UNION
                      SELECT chat_id FROM group_admins WHERE user_id = ?
                      UNION
                      SELECT chat_id FROM anonymous_admins WHERE anonymous_id = ?
                  )""",
            (user_id, user_id, user_id, user_id, user_id, user_id)
        )

    async def sync_group_admins(self, chat_id: int, admin_ids: List[int]) -> int:
        try:
            async with self._get_connection() as conn:
                await conn.execute("DELETE FROM group_admins WHERE chat_id = ?", (chat_id,))
                if admin_ids:
                    await conn.executemany("INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?,?)", [(chat_id, uid) for uid in admin_ids])
            return len(admin_ids)
        except Exception as e:
            logger.error(f"❌ Error in sync_group_admins: {e}", exc_info=True)
            return 0

    async def add_hidden_admin(self, chat_id: int, admin_id: int, added_by: int) -> bool:
        return await self.execute("INSERT OR IGNORE INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?,?,?,?)", (chat_id, admin_id, added_by, TimeUtils.sql_iso()))

    async def remove_hidden_admin(self, chat_id: int, admin_id: int) -> bool:
        try:
            async with self._get_connection() as conn:
                await conn.execute("DELETE FROM hidden_owner_groups WHERE chat_id = ? AND owner_id = ?", (chat_id, admin_id))
                await conn.execute("DELETE FROM hidden_admins WHERE chat_id = ? AND admin_id = ?", (chat_id, admin_id))
            return True
        except Exception as e:
            logger.error(f"❌ Error in remove_hidden_admin: {e}", exc_info=True)
            return False

    async def get_hidden_admins(self, chat_id: int) -> List[Dict]:
        return await self.fetchall("SELECT admin_id, added_by, added_at FROM hidden_admins WHERE chat_id = ? ORDER BY added_at DESC", (chat_id,))

    # =====================================================================
    # دوال المشرفين المجهولين
    # =====================================================================

    async def add_anonymous_admin(self, chat_id: int, anonymous_id: int, added_by: int = None) -> bool:
        return await self.execute("INSERT OR IGNORE INTO anonymous_admins (chat_id, anonymous_id, added_by, added_at) VALUES (?,?,?,?)", (chat_id, anonymous_id, added_by, TimeUtils.sql_iso()))

    async def remove_anonymous_admin(self, chat_id: int, anonymous_id: int) -> bool:
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("DELETE FROM anonymous_admins WHERE chat_id = ? AND anonymous_id = ?", (chat_id, anonymous_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Error in remove_anonymous_admin: {e}", exc_info=True)
            return False

    async def get_anonymous_admins(self, chat_id: int) -> List[Dict]:
        return await self.fetchall("SELECT anonymous_id, added_by, added_at FROM anonymous_admins WHERE chat_id = ? ORDER BY added_at DESC", (chat_id,))

    async def is_anonymous_admin(self, chat_id: int, user_id: int) -> bool:
        result = await self.fetchval("SELECT 1 FROM anonymous_admins WHERE chat_id = ? AND anonymous_id = ?", (chat_id, user_id))
        return result is not None

    async def sync_anonymous_admins(self, chat_id: int, anonymous_ids: List[int], added_by: int = None) -> int:
        try:
            async with self._lock:
                async with self._get_connection() as conn:
                    await conn.execute("DELETE FROM anonymous_admins WHERE chat_id = ?", (chat_id,))
                    if anonymous_ids:
                        await conn.executemany("INSERT OR IGNORE INTO anonymous_admins (chat_id, anonymous_id, added_by, added_at) VALUES (?,?,?,?)", [(chat_id, anon_id, added_by, TimeUtils.sql_iso()) for anon_id in anonymous_ids])
            return len(anonymous_ids)
        except Exception as e:
            logger.error(f"❌ Error in sync_anonymous_admins: {e}", exc_info=True)
            return 0

    # =====================================================================
    # دوال الأمان
    # =====================================================================

    async def get_security_settings(self, chat_id: int) -> Dict:
        settings = await self.fetchone("SELECT * FROM group_security WHERE chat_id = ?", (chat_id,))
        if settings:
            return settings
        await self.execute("INSERT OR IGNORE INTO group_security (chat_id) VALUES (?)", (chat_id,))
        settings = await self.fetchone("SELECT * FROM group_security WHERE chat_id = ?", (chat_id,))
        return settings if settings else {}

    async def update_security_settings(self, chat_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        allowed_columns = {
            'delete_links', 'mentions', 'slow_mode', 'slow_mode_seconds',
            'welcome_enabled', 'welcome_text', 'goodbye_enabled', 'goodbye_text',
            'delete_banned_words', 'auto_penalty', 'auto_mute_duration',
            'delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
            'delete_documents', 'delete_stickers', 'delete_forwarded', 'delete_polls',
            'delete_games', 'delete_voice', 'delete_video_note', 'delete_photos',
            'delete_penalty', 'delete_penalty_duration', 'delete_penalty_messages',
            'antiflood_enabled', 'antiflood_messages', 'antiflood_seconds', 'antiflood_penalty',
            'max_warnings', 'warn_penalty', 'warn_enabled', 'max_message_length',
            'night_mode_enabled', 'night_mode_start', 'night_mode_end', 'night_mode_action',
            'nsfw_enabled', 'nsfw_threshold', 'nsfw_filter',
            'auto_approve_join', 'auto_reject_join',
            'mute_default_duration', 'ban_default_duration', 'warn_default_duration', 'restrict_default_duration',
            'enable_timed_penalties', 'auto_remove_penalties',
            'violation_strikes', 'violation_duration'
        }
        for key in kwargs:
            if key not in allowed_columns:
                logger.error(f"❌ Invalid column: {key}")
                return False
        updates = [f"{key} = ?" for key in kwargs]
        values = list(kwargs.values()) + [chat_id]
        query = f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id = ?"
        return await self.execute(query, tuple(values))

    async def get_banned_words(self, chat_id: int) -> List[str]:
        words = await self.fetchall("SELECT word FROM banned_words WHERE chat_id = ? OR chat_id = -1", (chat_id,))
        return [word['word'] for word in words]

    async def add_banned_word(self, word: str, chat_id: int, added_by: int) -> Tuple[bool, bool]:
        try:
            word = word.strip().lower()
            if not word:
                return False, False
            if chat_id == -1:
                count = await self.fetchval("SELECT COUNT(*) FROM banned_words WHERE chat_id = -1", default=0)
                if count >= getattr(CONFIG, 'MAX_GLOBAL_BANNED_WORDS', 500):
                    return False, False
            result = await self.execute("INSERT INTO banned_words (word, chat_id, added_by, added_at) VALUES (?,?,?,?)", (word, chat_id, added_by, TimeUtils.sql_iso()))
            return result, False
        except aiosqlite.IntegrityError:
            return False, True
        except Exception as e:
            logger.error(f"❌ Error in add_banned_word: {e}", exc_info=True)
            return False, False

    async def remove_banned_word(self, word: str, chat_id: int) -> bool:
        word = word.strip().lower()
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("DELETE FROM banned_words WHERE word = ? AND chat_id = ?", (word, chat_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Error in remove_banned_word: {e}", exc_info=True)
            return False

    async def get_user_warnings(self, user_id: int, chat_id: int) -> int:
        return await self.fetchval("SELECT warnings FROM user_warnings WHERE user_id = ? AND chat_id = ?", (user_id, chat_id), default=0)

    async def add_user_warning(self, user_id: int, chat_id: int) -> int:
        await self.execute(
            """INSERT INTO user_warnings (user_id, chat_id, warnings)
               VALUES (?,?,1)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET warnings = warnings + 1""",
            (user_id, chat_id)
        )
        return await self.get_user_warnings(user_id, chat_id)

    async def reset_user_warnings(self, user_id: int, chat_id: int) -> bool:
        return await self.execute("UPDATE user_warnings SET warnings = 0 WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))

    async def add_admin_log(self, chat_id: int, admin_id: int, action: str, target_id: int = None, reason: str = "") -> bool:
        return await self.execute("INSERT INTO admin_logs (chat_id, admin_id, action, target_id, reason, created_at) VALUES (?,?,?,?,?,?)", (chat_id, admin_id, action, target_id, reason, TimeUtils.sql_iso()))

    async def get_admin_logs(self, chat_id: int, limit: int = 20) -> List[Dict]:
        return await self.fetchall("SELECT admin_id, action, target_id, reason, created_at FROM admin_logs WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit))

    # =====================================================================
    # دوال الردود التلقائية
    # =====================================================================

    async def get_auto_reply_settings(self, chat_id: int) -> Dict:
        settings = await self.fetchone("SELECT * FROM auto_reply_settings WHERE chat_id = ?", (chat_id,))
        if settings:
            return settings
        await self.execute("INSERT OR IGNORE INTO auto_reply_settings (chat_id) VALUES (?)", (chat_id,))
        settings = await self.fetchone("SELECT * FROM auto_reply_settings WHERE chat_id = ?", (chat_id,))
        return settings if settings else {'enabled': 0, 'only_admins': 0, 'ignore_bots': 1}

    async def update_auto_reply_settings(self, chat_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        allowed_columns = {'enabled', 'only_admins', 'ignore_bots', 'updated_at'}
        for key in kwargs:
            if key not in allowed_columns:
                logger.error(f"❌ Invalid column: {key}")
                return False
        if 'updated_at' not in kwargs:
            kwargs['updated_at'] = TimeUtils.sql_iso()
        updates = [f"{key} = ?" for key in kwargs]
        values = list(kwargs.values()) + [chat_id]
        query = f"UPDATE auto_reply_settings SET {', '.join(updates)} WHERE chat_id = ?"
        return await self.execute(query, tuple(values))

    async def add_auto_reply(self, chat_id: int, keyword: str, reply: str, reply_type: str = 'text', media_id: str = None, buttons: str = None) -> bool:
        keyword = keyword.lower().strip()
        if reply_type not in self.VALID_REPLY_TYPES:
            logger.error(f"❌ Invalid reply_type: {reply_type}")
            return False
        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    "INSERT INTO auto_replies (chat_id, keyword, reply, reply_type, reply_media_id, reply_buttons, created_at) VALUES (?,?,?,?,?,?,?)",
                    (chat_id, keyword, reply, reply_type, media_id, buttons, TimeUtils.sql_iso())
                )
            return True
        except aiosqlite.IntegrityError:
            return await self.execute(
                "UPDATE auto_replies SET reply = ?, reply_type = ?, reply_media_id = ?, reply_buttons = ?, created_at = ? WHERE chat_id = ? AND keyword = ?",
                (reply, reply_type, media_id, buttons, TimeUtils.sql_iso(), chat_id, keyword)
            )
        except Exception as e:
            logger.error(f"❌ Error in add_auto_reply: {e}", exc_info=True)
            return False

    async def remove_auto_reply(self, chat_id: int, keyword: str) -> bool:
        keyword = keyword.lower().strip()
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("DELETE FROM auto_replies WHERE chat_id = ? AND keyword = ?", (chat_id, keyword))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Error in remove_auto_reply: {e}", exc_info=True)
            return False

    async def get_auto_reply(self, keyword: str, chat_id: int) -> Optional[Dict]:
        keyword = keyword.lower().strip()
        reply = await self.fetchone("SELECT reply, reply_type, reply_media_id, reply_buttons FROM auto_replies WHERE chat_id = ? AND keyword = ? AND is_active = 1", (chat_id, keyword))
        if reply:
            await self.execute("UPDATE auto_replies SET usage_count = usage_count + 1 WHERE chat_id = ? AND keyword = ?", (chat_id, keyword))
            return reply
        reply = await self.fetchone("SELECT reply, reply_type, reply_media_id, reply_buttons FROM auto_replies WHERE chat_id = -1 AND keyword = ? AND is_active = 1", (keyword,))
        if reply:
            await self.execute("UPDATE auto_replies SET usage_count = usage_count + 1 WHERE chat_id = -1 AND keyword = ?", (keyword,))
            return reply
        return None

    async def get_auto_reply_stats(self, chat_id: int, limit: int = 20) -> List[Dict]:
        return await self.fetchall(
            """SELECT keyword, usage_count, CASE WHEN chat_id = -1 THEN 'global' ELSE 'group' END as source
               FROM auto_replies
               WHERE chat_id = ? OR chat_id = -1
               ORDER BY usage_count DESC
               LIMIT ?""",
            (chat_id, limit)
        )

    async def reset_auto_replies(self, chat_id: int) -> bool:
        return await self.execute("DELETE FROM auto_replies WHERE chat_id = ?", (chat_id,))

    # =====================================================================
    # دوال الجدولة
    # =====================================================================

    async def get_schedule(self, channel_db_id: int) -> Dict:
        schedule = await self.fetchone("SELECT * FROM schedule WHERE channel_db_id = ?", (channel_db_id,))
        if schedule:
            return schedule
        await self.execute("INSERT OR IGNORE INTO schedule (channel_db_id, schedule_type, interval_minutes) VALUES (?, 'interval_minutes', 12)", (channel_db_id,))
        schedule = await self.fetchone("SELECT * FROM schedule WHERE channel_db_id = ?", (channel_db_id,))
        return schedule if schedule else {}

    async def update_schedule(self, channel_db_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        allowed_columns = {'schedule_type', 'interval_minutes', 'interval_hours', 'interval_days', 'days_of_week', 'specific_dates', 'publish_time', 'cron_expression', 'next_publish_date'}
        for key in kwargs:
            if key not in allowed_columns:
                logger.error(f"❌ Invalid column: {key}")
                return False
        updates = [f"{key} = ?" for key in kwargs]
        values = list(kwargs.values()) + [channel_db_id]
        query = f"UPDATE schedule SET {', '.join(updates)} WHERE channel_db_id = ?"
        return await self.execute(query, tuple(values))

    async def update_next_publish(self, channel_db_id: int) -> bool:
        schedule = await self.get_schedule(channel_db_id)
        last_publish = await self.fetchval("SELECT last_publish_time FROM last_publish WHERE channel_db_id = ?", (channel_db_id,))
        last_time = TimeUtils.safe_parse_iso(last_publish) if last_publish else TimeUtils.utc_now()
        schedule_type = schedule.get('schedule_type', 'interval_minutes')
        if schedule_type == 'interval_minutes':
            interval = max(1, schedule.get('interval_minutes', 12))
            next_date = last_time + timedelta(minutes=interval)
        elif schedule_type == 'interval_hours':
            interval = max(1, schedule.get('interval_hours', 1))
            next_date = last_time + timedelta(hours=interval)
        elif schedule_type == 'interval_days':
            interval = max(1, schedule.get('interval_days', 1))
            next_date = last_time + timedelta(days=interval)
        else:
            interval = 12
            next_date = last_time + timedelta(minutes=interval)
        counter = 0
        while next_date <= TimeUtils.utc_now() and counter < 100:
            if schedule_type == 'interval_minutes':
                next_date += timedelta(minutes=interval)
            elif schedule_type == 'interval_hours':
                next_date += timedelta(hours=interval)
            elif schedule_type == 'interval_days':
                next_date += timedelta(days=interval)
            else:
                next_date += timedelta(minutes=12)
            counter += 1
        return await self.execute("UPDATE schedule SET next_publish_date = ? WHERE channel_db_id = ?", (next_date.strftime('%Y-%m-%d %H:%M:%S'), channel_db_id))

    async def update_last_publish(self, channel_db_id: int) -> bool:
        return await self.execute("INSERT OR REPLACE INTO last_publish (channel_db_id, last_publish_time) VALUES (?,?)", (channel_db_id, TimeUtils.sql_iso()))

    async def get_channels_to_publish(self, limit: int = 20) -> List[Dict]:
        return await self.fetchall(
            """WITH active_subs AS (
                   SELECT s.user_id, s.plan_id, p.max_channels, p.max_posts
                   FROM subscriptions s
                   JOIN plans p ON s.plan_id = p.id
                   WHERE s.status = 'active' AND s.end_date > datetime('now')
                   AND s.id = (
                       SELECT id FROM subscriptions
                       WHERE user_id = s.user_id AND status = 'active' AND end_date > datetime('now')
                       ORDER BY (SELECT max_channels FROM plans WHERE id = subscriptions.plan_id) DESC,
                                (SELECT max_posts FROM plans WHERE id = subscriptions.plan_id) DESC,
                                end_date DESC
                       LIMIT 1
                   )
               )
               SELECT uc.id, uc.channel_id, uc.user_id, u.auto_publish, u.auto_recycle
               FROM user_channels uc
               JOIN users u ON uc.user_id = u.user_id
               LEFT JOIN schedule s ON uc.id = s.channel_db_id
               LEFT JOIN active_subs a ON uc.user_id = a.user_id
               WHERE uc.banned = 0 
                 AND u.banned = 0 
                 AND u.auto_publish = 1
                 AND (s.next_publish_date IS NULL OR s.next_publish_date <= ?)
                 AND (
                     EXISTS (SELECT 1 FROM posts p WHERE p.channel_db_id = uc.id AND p.published = 0 AND (p.fail_count IS NULL OR p.fail_count < 3))
                     OR (u.auto_recycle = 1 AND EXISTS (SELECT 1 FROM posts p WHERE p.channel_db_id = uc.id AND p.published = 1))
                 )
                 AND a.user_id IS NOT NULL
                 AND (a.max_channels IS NULL OR (SELECT COUNT(*) FROM user_channels WHERE user_id = uc.user_id AND banned = 0) <= a.max_channels)
                 AND (a.max_posts IS NULL OR (SELECT COUNT(*) FROM posts WHERE channel_db_id = uc.id) <= a.max_posts)
               ORDER BY COALESCE(s.next_publish_date, '1970-01-01 00:00:00') ASC
               LIMIT ?""",
            (TimeUtils.sql_iso(), limit)
        )

    # =====================================================================
    # دوال التذاكر
    # =====================================================================

    async def create_ticket(self, user_id: int, username: str, content: str, media_type: str = None, media_file_id: str = None) -> int:
        try:
            async with self._lock:
                next_num = await self.fetchval("SELECT COALESCE(MAX(ticket_number), 0) + 1 FROM support_tickets", default=1)
                result = await self.execute(
                    "INSERT INTO support_tickets (user_id, username, message, media_type, media_file_id, ticket_number, created_at) VALUES (?,?,?,?,?,?,?)",
                    (user_id, username, content, media_type, media_file_id, next_num, TimeUtils.sql_iso())
                )
                return next_num if result else 0
        except Exception as e:
            logger.error(f"❌ Error in create_ticket: {e}", exc_info=True)
            return 0

    async def get_tickets(self) -> List[Dict]:
        return await self.fetchall("SELECT id, user_id, username, ticket_number, message, status, created_at FROM support_tickets WHERE status = 'pending' ORDER BY created_at DESC")

    async def close_ticket(self, ticket_id: int) -> bool:
        return await self.execute("UPDATE support_tickets SET status = 'closed' WHERE id = ?", (ticket_id,))

    async def delete_all_tickets(self) -> bool:
        return await self.execute("DELETE FROM support_tickets")

    # =====================================================================
    # دوال الإحالات (مصححة - بدون Deadlock)
    # =====================================================================

    async def add_referral(self, referrer_id: int, referred_id: int) -> bool:
        if referrer_id == referred_id:
            return False
        try:
            async with self._get_connection() as conn:
                today = TimeUtils.utc_now().strftime('%Y-%m-%d')
                count = await self._fetchval_in_conn(
                    conn,
                    "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND date(created_at) = ?",
                    (referrer_id, today),
                    default=0
                )
                if count >= getattr(CONFIG, 'MAX_DAILY_REFERRALS', 10):
                    logger.warning(f"⚠️ User {referrer_id} reached daily referral limit")
                    return False
                cursor = await conn.execute(
                    "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?,?,?)",
                    (referrer_id, referred_id, TimeUtils.sql_iso())
                )
                if cursor.rowcount > 0:
                    await conn.execute(
                        """INSERT INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days, last_referral_date)
                           VALUES (?,1,3,0,?)
                           ON CONFLICT(user_id) DO UPDATE SET 
                               referral_count = referral_count + 1,
                               total_reward_days = total_reward_days + 3,
                               last_referral_date = ?""",
                        (referrer_id, TimeUtils.sql_iso(), TimeUtils.sql_iso())
                    )
                    await conn.execute(
                        """INSERT INTO user_points (user_id, points, last_updated)
                           VALUES (?,5,?)
                           ON CONFLICT(user_id) DO UPDATE SET 
                               points = points + 5, 
                               last_updated = ?""",
                        (referrer_id, TimeUtils.sql_iso(), TimeUtils.sql_iso())
                    )
                    return True
                return False
        except aiosqlite.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"❌ Error in add_referral: {e}", exc_info=True)
            return False

    async def get_referral_stats(self, user_id: int) -> Dict:
        try:
            async with self._get_connection() as conn:
                await conn.execute("INSERT OR IGNORE INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days, last_referral_date) VALUES (?, 0, 0, 0, NULL)", (user_id,))
                total = await self._fetchval_in_conn(conn, "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,), default=0)
                reward = await self._fetchone_in_conn(conn, "SELECT COALESCE(total_reward_days, 0) as total_reward, COALESCE(claimed_reward_days, 0) as claimed FROM referral_rewards WHERE user_id = ?", (user_id,))
                total_reward = reward['total_reward'] if reward else 0
                claimed = reward['claimed'] if reward else 0
            return {'total': total, 'claimed': claimed, 'available': max(0, total_reward - claimed)}
        except Exception as e:
            logger.error(f"❌ Error in get_referral_stats: {e}", exc_info=True)
            return {'total': 0, 'claimed': 0, 'available': 0}

    async def claim_referral_reward(self, user_id: int) -> int:
        try:
            async with self._lock:
                async with self._get_connection() as conn:
                    await conn.execute("INSERT OR IGNORE INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days, last_referral_date) VALUES (?, 0, 0, 0, NULL)", (user_id,))
                    reward = await self._fetchone_in_conn(
                        conn,
                        "SELECT COALESCE(total_reward_days, 0) as total_reward, COALESCE(claimed_reward_days, 0) as claimed FROM referral_rewards WHERE user_id = ?",
                        (user_id,)
                    )
                    if not reward:
                        return 0
                    total_reward = reward['total_reward'] or 0
                    claimed = reward['claimed'] or 0
                    available = max(0, total_reward - claimed)
                    if available <= 0:
                        return 0
                    await conn.execute(
                        "UPDATE referral_rewards SET claimed_reward_days = claimed_reward_days + ? WHERE user_id = ?",
                        (available, user_id)
                    )
                    current_end = await self._fetchval_in_conn(
                        conn,
                        "SELECT MAX(end_date) FROM subscriptions WHERE user_id = ? AND status = 'active' AND end_date > datetime('now')",
                        (user_id,)
                    )
                    current_end = TimeUtils.safe_parse_iso(current_end) if current_end else None
                    now = TimeUtils.utc_now()
                    base = current_end if current_end and current_end > now else now
                    new_end = base + timedelta(days=available)
                    await conn.execute(
                        """INSERT INTO subscriptions 
                           (user_id, plan_id, status, start_date, end_date, provider, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (user_id, 1, 'active', TimeUtils.sql_iso(), new_end.strftime('%Y-%m-%d %H:%M:%S'), 'referral', TimeUtils.sql_iso(), TimeUtils.sql_iso())
                    )
                    await self._refresh_user_subscription_end(conn, user_id)
                    return available
        except Exception as e:
            logger.error(f"❌ Error in claim_referral_reward: {e}", exc_info=True)
            return 0

    async def get_referrals_list(self, user_id: int) -> List[int]:
        referrals = await self.fetchall("SELECT referred_id FROM referrals WHERE referrer_id = ? ORDER BY created_at DESC", (user_id,))
        return [ref['referred_id'] for ref in referrals]

    # =====================================================================
    # دوال التذكيرات
    # =====================================================================

    async def get_reminder_settings(self, user_id: int) -> Dict:
        settings = await self.fetchone("SELECT * FROM user_reminder_settings WHERE user_id = ?", (user_id,))
        if settings:
            return settings
        await self.execute("INSERT OR IGNORE INTO user_reminder_settings (user_id) VALUES (?)", (user_id,))
        settings = await self.fetchone("SELECT * FROM user_reminder_settings WHERE user_id = ?", (user_id,))
        return settings if settings else {}

    async def update_reminder_settings(self, user_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        allowed_columns = {'subscription_reminder', 'daily_stats_reminder', 'weekly_report', 'reminder_days_before', 'last_reminder_sent', 'notification_lang'}
        for key in kwargs:
            if key not in allowed_columns:
                logger.error(f"❌ Invalid column: {key}")
                return False
        updates = [f"{key} = ?" for key in kwargs]
        values = list(kwargs.values()) + [user_id]
        query = f"UPDATE user_reminder_settings SET {', '.join(updates)} WHERE user_id = ?"
        return await self.execute(query, tuple(values))

    async def get_users_for_reminder(self) -> List[Dict]:
        return await self.fetchall(
            """SELECT u.user_id, u.language, r.reminder_days_before,
                      CAST(julianday(MAX(s.end_date)) - julianday(?) AS INTEGER) as days_left,
                      r.last_reminder_sent
               FROM users u
               JOIN user_reminder_settings r ON u.user_id = r.user_id
               JOIN subscriptions s ON u.user_id = s.user_id AND s.status = 'active' AND s.end_date > datetime('now')
               WHERE r.subscription_reminder = 1
               GROUP BY u.user_id, u.language, r.reminder_days_before, r.last_reminder_sent
               HAVING days_left <= r.reminder_days_before
                  AND days_left > 0
                  AND (r.last_reminder_sent IS NULL OR julianday(?) - julianday(r.last_reminder_sent) >= 1)""",
            (TimeUtils.sql_iso(), TimeUtils.sql_iso())
        )

    # =====================================================================
    # دوال المسابقات
    # =====================================================================

    async def create_contest(self, creator_id: int, title: str, description: str, prize: str, end_date: str) -> int:
        try:
            dt = datetime.fromisoformat(end_date)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            end_date_sql = dt.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            logger.error(f"❌ Invalid end_date format: {end_date}")
            return 0
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute(
                    "INSERT INTO contests (creator_id, title, description, prize, end_date, created_at) VALUES (?,?,?,?,?,?)",
                    (creator_id, title, description, prize, end_date_sql, TimeUtils.sql_iso())
                )
                return cursor.lastrowid if cursor.lastrowid else 0
        except Exception as e:
            logger.error(f"❌ Error in create_contest: {e}", exc_info=True)
            return 0

    async def get_active_contests(self, limit: int = 10) -> List[Dict]:
        return await self.fetchall(
            """SELECT c.*, (SELECT COUNT(*) FROM contest_participants WHERE contest_id = c.id) as participants
               FROM contests c
               WHERE c.status = 'active' AND datetime(c.end_date) > datetime(?)
               ORDER BY c.end_date ASC LIMIT ?""",
            (TimeUtils.sql_iso(), limit)
        )

    async def join_contest(self, contest_id: int, user_id: int, answer: str = "") -> bool:
        try:
            async with self._get_connection() as conn:
                contest = await self._fetchone_in_conn(conn, "SELECT status, end_date FROM contests WHERE id = ?", (contest_id,))
                if not contest or contest['status'] != 'active':
                    return False
                end_date = TimeUtils.safe_parse_iso(contest['end_date'])
                if end_date and end_date < TimeUtils.utc_now():
                    return False
                await conn.execute("INSERT INTO contest_participants (contest_id, user_id, answer, joined_at) VALUES (?,?,?,?)", (contest_id, user_id, answer, TimeUtils.sql_iso()))
                return True
        except aiosqlite.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"❌ Error in join_contest: {e}", exc_info=True)
            return False

    async def declare_winner(self, contest_id: int, winner_id: int) -> bool:
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("SELECT 1 FROM contest_participants WHERE contest_id = ? AND user_id = ?", (contest_id, winner_id))
                if not await cursor.fetchone():
                    return False
                cursor = await conn.execute("SELECT status FROM contests WHERE id = ?", (contest_id,))
                contest = await cursor.fetchone()
                if not contest or contest['status'] != 'active':
                    return False
                await conn.execute("UPDATE contests SET status = 'closed', winner_id = ? WHERE id = ?", (winner_id, contest_id))
                await conn.execute("INSERT INTO contest_winners (contest_id, winner_id, announced_at) VALUES (?,?,?)", (contest_id, winner_id, TimeUtils.sql_iso()))
                return True
        except Exception as e:
            logger.error(f"❌ Error in declare_winner: {e}", exc_info=True)
            return False

    async def get_contest_winners(self, limit: int = 10) -> List[Dict]:
        return await self.fetchall(
            """SELECT c.title, c.winner_id, u.username, cw.announced_at
               FROM contest_winners cw
               JOIN contests c ON cw.contest_id = c.id
               JOIN users u ON cw.winner_id = u.user_id
               ORDER BY cw.announced_at DESC LIMIT ?""",
            (limit,)
        )

    async def delete_contest(self, contest_id: int, user_id: int) -> bool:
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("SELECT creator_id FROM contests WHERE id = ?", (contest_id,))
                contest = await cursor.fetchone()
                if not contest or contest['creator_id'] != user_id:
                    return False
                await conn.execute("DELETE FROM contest_participants WHERE contest_id = ?", (contest_id,))
                await conn.execute("DELETE FROM contest_winners WHERE contest_id = ?", (contest_id,))
                await conn.execute("DELETE FROM contests WHERE id = ?", (contest_id,))
                return True
        except Exception as e:
            logger.error(f"❌ Error in delete_contest: {e}", exc_info=True)
            return False

    # =====================================================================
    # دوال الإعدادات العامة
    # =====================================================================

    async def get_setting(self, key: str, default: str = None) -> Optional[str]:
        result = await self.fetchval("SELECT value FROM settings WHERE key = ?", (key,), default=default)
        return result if result is not None else default

    async def set_setting(self, key: str, value: str) -> bool:
        return await self.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))

    async def get_force_subscribe_channel(self) -> Optional[str]:
        return await self.get_setting('force_subscribe_channel')

    async def get_updates_channel(self) -> Optional[str]:
        return await self.get_setting('updates_channel')

    async def get_log_channel(self) -> Optional[str]:
        return await self.get_setting('log_channel_id')

    async def get_publish_interval(self) -> int:
        value = await self.get_setting('publish_interval', '12')
        try:
            interval = int(value)
            return max(1, interval)
        except (ValueError, TypeError):
            return 12

    async def get_auto_backup(self) -> bool:
        value = await self.get_setting('auto_backup', '1')
        return value in ('1', 'true', 'True', 'yes', 'on')

    # =====================================================================
    # دوال الباقات والاشتراكات
    # =====================================================================

    async def get_plan(self, plan_id: int) -> Optional[Dict]:
        return await self.fetchone("SELECT * FROM plans WHERE id = ? AND is_active = 1", (plan_id,))

    async def get_plan_by_name(self, name: str) -> Optional[Dict]:
        return await self.fetchone("SELECT * FROM plans WHERE name = ? AND is_active = 1", (name,))

    async def get_all_plans(self) -> List[Dict]:
        return await self.fetchall("SELECT * FROM plans WHERE is_active = 1 AND is_gift = 0 ORDER BY price")

    async def get_gift_plans(self) -> List[Dict]:
        return await self.fetchall("SELECT id, name, description, price, duration_days AS days FROM plans WHERE is_active = 1 AND is_gift = 1 ORDER BY price")

    async def get_gift_plan(self, plan_id: int) -> Optional[Dict]:
        return await self.fetchone("SELECT id, name, description, price, duration_days AS days FROM plans WHERE id = ? AND is_gift = 1 AND is_active = 1", (plan_id,))

    async def redeem_gift_code(self, user_id: int, code: str) -> tuple:
        try:
            code = code.strip()
            async with self._lock:
                async with self._get_connection() as conn:
                    cursor = await conn.execute("SELECT * FROM gift_codes WHERE code = ?", (code,))
                    gift_code = await cursor.fetchone()
                    if not gift_code:
                        return False, 0
                    if gift_code['used_by']:
                        return False, 0
                    if gift_code['creator_id'] == user_id:
                        return False, -1
                    cursor = await conn.execute("SELECT id, name, description, price, duration_days AS days FROM plans WHERE id = ? AND is_gift = 1 AND is_active = 1", (gift_code['plan_id'],))
                    plan = await cursor.fetchone()
                    if not plan:
                        return False, 0
                    await conn.execute("UPDATE gift_codes SET used_by = ?, used_at = ? WHERE id = ?", (user_id, TimeUtils.sql_iso(), gift_code['id']))
                    current_end = await self._fetchval_in_conn(
                        conn,
                        "SELECT MAX(end_date) FROM subscriptions WHERE user_id = ? AND status = 'active' AND end_date > datetime('now')",
                        (user_id,)
                    )
                    current_end = TimeUtils.safe_parse_iso(current_end) if current_end else None
                    now = TimeUtils.utc_now()
                    base = current_end if current_end and current_end > now else now
                    new_end = base + timedelta(days=plan['days'])
                    await conn.execute(
                        """INSERT INTO subscriptions 
                           (user_id, plan_id, status, start_date, end_date, provider, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (user_id, gift_code['plan_id'], 'active', TimeUtils.sql_iso(), new_end.strftime('%Y-%m-%d %H:%M:%S'), 'gift', TimeUtils.sql_iso(), TimeUtils.sql_iso())
                    )
                    await self._refresh_user_subscription_end(conn, user_id)
                    return True, plan['days']
        except Exception as e:
            logger.error(f"❌ Error in redeem_gift_code: {e}", exc_info=True)
            return False, 0

    async def grant_subscription_days(self, user_id: int, days: int, plan_id: int = None, provider: str = 'manual') -> bool:
        try:
            if days <= 0:
                return False
            async with self._lock:
                async with self._get_connection() as conn:
                    exists = await self._fetchval_in_conn(conn, "SELECT 1 FROM users WHERE user_id = ?", (user_id,))
                    if not exists:
                        return False
                    current_end = await self._fetchval_in_conn(
                        conn,
                        "SELECT MAX(end_date) FROM subscriptions WHERE user_id = ? AND status = 'active' AND end_date > datetime('now')",
                        (user_id,)
                    )
                    current_end = TimeUtils.safe_parse_iso(current_end) if current_end else None
                    now = TimeUtils.utc_now()
                    base = current_end if current_end and current_end > now else now
                    new_end = base + timedelta(days=days)
                    final_plan_id = plan_id if plan_id else 1
                    await conn.execute(
                        """INSERT INTO subscriptions 
                           (user_id, plan_id, status, start_date, end_date, provider, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (user_id, final_plan_id, 'active', TimeUtils.sql_iso(), new_end.strftime('%Y-%m-%d %H:%M:%S'), provider, TimeUtils.sql_iso(), TimeUtils.sql_iso())
                    )
                    await self._refresh_user_subscription_end(conn, user_id)
                    return True
        except Exception as e:
            logger.error(f"❌ Error in grant_subscription_days: {e}", exc_info=True)
            return False

    async def create_subscription(self, user_id: int, plan_id: int, provider: str = 'xtr', provider_sub_id: str = None) -> int:
        try:
            plan = await self.get_plan(plan_id)
            if not plan:
                return 0
            async with self._lock:
                async with self._get_connection() as conn:
                    current_end = await self._fetchval_in_conn(
                        conn,
                        "SELECT MAX(end_date) FROM subscriptions WHERE user_id = ? AND status = 'active' AND end_date > datetime('now')",
                        (user_id,)
                    )
                    current_end = TimeUtils.safe_parse_iso(current_end) if current_end else None
                    now = TimeUtils.utc_now()
                    base = current_end if current_end and current_end > now else now
                    new_end = base + timedelta(days=plan['duration_days'])
                    cursor = await conn.execute(
                        """INSERT INTO subscriptions 
                           (user_id, plan_id, status, start_date, end_date, auto_renew, provider, provider_subscription_id, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (user_id, plan_id, 'active', TimeUtils.sql_iso(), new_end.strftime('%Y-%m-%d %H:%M:%S'), 0, provider, provider_sub_id, TimeUtils.sql_iso(), TimeUtils.sql_iso())
                    )
                    await self._refresh_user_subscription_end(conn, user_id)
                    return cursor.lastrowid if cursor.lastrowid else 0
        except Exception as e:
            logger.error(f"❌ Error in create_subscription: {e}", exc_info=True)
            return 0

    async def expire_expired_subscriptions(self) -> None:
        try:
            async with self._get_connection() as conn:
                await conn.execute("UPDATE subscriptions SET status = 'expired' WHERE status = 'active' AND end_date <= ?", (TimeUtils.sql_iso(),))
                cursor = await conn.execute("SELECT DISTINCT user_id FROM subscriptions WHERE status = 'expired'")
                users = await cursor.fetchall()
                for user in users:
                    await self._refresh_user_subscription_end(conn, user['user_id'])
        except Exception as e:
            logger.error(f"❌ Error in expire_expired_subscriptions: {e}", exc_info=True)

    async def _refresh_user_subscription_end(self, conn: aiosqlite.Connection, user_id: int) -> None:
        cursor = await conn.execute("SELECT MAX(end_date) FROM subscriptions WHERE user_id = ? AND status = 'active' AND end_date > datetime('now')", (user_id,))
        row = await cursor.fetchone()
        end = row[0] if row and row[0] else None
        await conn.execute("UPDATE users SET subscription_end = ? WHERE user_id = ?", (end, user_id))

    # =====================================================================
    # دوال الفواتير والدفع
    # =====================================================================

    async def create_invoice(self, user_id: int, plan_id: int, amount: int, currency: str = 'XTR', provider: str = 'xtr') -> str:
        number = f"INV-{TimeUtils.utc_now().strftime('%Y%m')}-{secrets.token_hex(4).upper()}"
        result = await self.execute(
            "INSERT INTO invoices (number, user_id, plan_id, amount, currency, status, provider, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (number, user_id, plan_id, amount, currency, 'pending', provider, TimeUtils.sql_iso())
        )
        return number if result else ""

    async def mark_invoice_paid(self, invoice_number: str, payment_id: str) -> bool:
        return await self.execute("UPDATE invoices SET status = 'paid', provider_payment_id = ?, paid_at = ? WHERE number = ?", (payment_id, TimeUtils.sql_iso(), invoice_number))

    async def get_invoice(self, number: str) -> Optional[Dict]:
        return await self.fetchone("SELECT * FROM invoices WHERE number = ?", (number,))

    async def get_user_invoices(self, user_id: int, limit: int = 20) -> List[Dict]:
        return await self.fetchall("SELECT * FROM invoices WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit))

    async def add_payment_log(self, user_id: int, provider: str, event_type: str, data: dict) -> bool:
        return await self.execute("INSERT INTO payment_logs (user_id, provider, event_type, data, created_at) VALUES (?,?,?,?,?)", (user_id, provider, event_type, json.dumps(data), TimeUtils.sql_iso()))

    async def activate_subscription_with_payment(self, user_id: int, invoice_number: str, payment_id: str, plan_id: int) -> bool:
        try:
            async with self._lock:
                async with self._get_connection() as conn:
                    cursor = await conn.execute("SELECT * FROM invoices WHERE number = ? AND user_id = ? AND status = 'pending'", (invoice_number, user_id))
                    invoice = await cursor.fetchone()
                    if not invoice:
                        logger.error(f"❌ Invoice not found or not pending: {invoice_number}")
                        return False
                    if invoice['plan_id'] != plan_id:
                        logger.error(f"❌ Plan mismatch: invoice plan {invoice['plan_id']} vs {plan_id}")
                        return False
                    cursor = await conn.execute("SELECT * FROM plans WHERE id = ? AND is_active = 1", (plan_id,))
                    plan = await cursor.fetchone()
                    if not plan:
                        return False
                    await conn.execute("UPDATE invoices SET status = 'paid', provider_payment_id = ?, paid_at = ? WHERE number = ?", (payment_id, TimeUtils.sql_iso(), invoice_number))
                    current_end = await self._fetchval_in_conn(
                        conn,
                        "SELECT MAX(end_date) FROM subscriptions WHERE user_id = ? AND status = 'active' AND end_date > datetime('now')",
                        (user_id,)
                    )
                    current_end = TimeUtils.safe_parse_iso(current_end) if current_end else None
                    now = TimeUtils.utc_now()
                    base = current_end if current_end and current_end > now else now
                    new_end = base + timedelta(days=plan['duration_days'])
                    await conn.execute(
                        """INSERT INTO subscriptions 
                           (user_id, plan_id, status, start_date, end_date, auto_renew, provider, provider_subscription_id, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (user_id, plan_id, 'active', TimeUtils.sql_iso(), new_end.strftime('%Y-%m-%d %H:%M:%S'), 0, 'xtr', payment_id, TimeUtils.sql_iso(), TimeUtils.sql_iso())
                    )
                    await self._refresh_user_subscription_end(conn, user_id)
                    return True
        except Exception as e:
            logger.error(f"❌ Error in activate_subscription_with_payment: {e}", exc_info=True)
            return False

    async def create_gift_code(self, plan_id: int, creator_id: int) -> Optional[str]:
        try:
            code = secrets.token_urlsafe(8)
            result = await self.execute("INSERT INTO gift_codes (code, plan_id, creator_id, created_at) VALUES (?,?,?,?)", (code, plan_id, creator_id, TimeUtils.sql_iso()))
            return code if result else None
        except Exception as e:
            logger.error(f"❌ Error in create_gift_code: {e}", exc_info=True)
            return None

    # =====================================================================
    # دوال العقوبات
    # =====================================================================

    async def add_penalty(self, user_id: int, chat_id: int, penalty_type: str, duration: int = 0, reason: str = "", issued_by: int = None) -> Optional[int]:
        try:
            if penalty_type not in self.VALID_PENALTY_TYPES:
                logger.error(f"❌ Invalid penalty_type: {penalty_type}")
                return None
            if duration < 0:
                duration = 0
            async with self._get_connection() as conn:
                await conn.execute("UPDATE user_penalties SET status = 'removed' WHERE user_id = ? AND chat_id = ? AND penalty_type = ? AND status = 'active'", (user_id, chat_id, penalty_type))
                start_time = TimeUtils.sql_iso()
                end_time = None
                if duration > 0:
                    end_time = (TimeUtils.utc_now() + timedelta(seconds=duration)).strftime('%Y-%m-%d %H:%M:%S')
                cursor = await conn.execute(
                    """INSERT INTO user_penalties 
                       (user_id, chat_id, penalty_type, duration, start_time, end_time, reason, issued_by, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (user_id, chat_id, penalty_type, duration, start_time, end_time, reason, issued_by, start_time)
                )
                if issued_by:
                    await conn.execute("INSERT INTO admin_logs (chat_id, admin_id, action, target_id, reason, created_at) VALUES (?,?,?,?,?,?)", (chat_id, issued_by, f"penalty_{penalty_type}", user_id, reason, start_time))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"❌ Error in add_penalty: {e}", exc_info=True)
            return None

    async def remove_penalty(self, penalty_id: int) -> bool:
        return await self.execute("UPDATE user_penalties SET status = 'removed' WHERE id = ?", (penalty_id,))

    async def remove_penalties_for_user(self, user_id: int, chat_id: int, penalty_type: str = None) -> int:
        try:
            async with self._get_connection() as conn:
                query = "UPDATE user_penalties SET status = 'removed' WHERE user_id = ? AND chat_id = ? AND status = 'active'"
                params = [user_id, chat_id]
                if penalty_type:
                    query += " AND penalty_type = ?"
                    params.append(penalty_type)
                cursor = await conn.execute(query, tuple(params))
                return cursor.rowcount
        except Exception as e:
            logger.error(f"❌ Error in remove_penalties_for_user: {e}", exc_info=True)
            return 0

    async def get_active_penalties(self, user_id: int, chat_id: int = None) -> List[Dict]:
        query = "SELECT * FROM user_penalties WHERE user_id = ? AND status = 'active'"
        params = [user_id]
        if chat_id:
            query += " AND chat_id = ?"
            params.append(chat_id)
        query += " ORDER BY end_time ASC"
        return await self.fetchall(query, tuple(params))

    async def get_penalty_settings(self, chat_id: int) -> Dict:
        await self.execute("INSERT OR IGNORE INTO group_security (chat_id) VALUES (?)", (chat_id,))
        return await self.fetchone(
            """SELECT mute_default_duration, ban_default_duration, 
                      warn_default_duration, restrict_default_duration,
                      enable_timed_penalties, auto_remove_penalties
               FROM group_security WHERE chat_id = ?""",
            (chat_id,)
        ) or {}

    async def update_penalty_settings(self, chat_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        allowed_columns = {'mute_default_duration', 'ban_default_duration', 'warn_default_duration', 'restrict_default_duration', 'enable_timed_penalties', 'auto_remove_penalties'}
        for key in kwargs:
            if key not in allowed_columns:
                logger.error(f"❌ Invalid column: {key}")
                return False
        updates = [f"{key} = ?" for key in kwargs]
        values = list(kwargs.values()) + [chat_id]
        query = f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id = ?"
        return await self.execute(query, tuple(values))

    async def expire_penalties(self) -> int:
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("UPDATE user_penalties SET status = 'expired' WHERE status = 'active' AND end_time IS NOT NULL AND end_time <= ?", (TimeUtils.sql_iso(),))
                expired_count = cursor.rowcount
                await conn.execute("DELETE FROM user_penalties WHERE status IN ('expired', 'removed') AND julianday(?) - julianday(created_at) > 30", (TimeUtils.sql_iso(),))
                return expired_count
        except Exception as e:
            logger.error(f"❌ Error in expire_penalties: {e}", exc_info=True)
            return 0

    async def get_user_penalty_count(self, user_id: int, chat_id: int, penalty_type: str = None) -> int:
        query = "SELECT COUNT(*) FROM user_penalties WHERE user_id = ? AND chat_id = ? AND status = 'active'"
        params = [user_id, chat_id]
        if penalty_type:
            query += " AND penalty_type = ?"
            params.append(penalty_type)
        return await self.fetchval(query, tuple(params), default=0)

    async def get_all_active_penalties(self) -> List[Dict]:
        return await self.fetchall("SELECT * FROM user_penalties WHERE status = 'active'")

    # =====================================================================
    # دوال قواعد العقوبات للمخالفات
    # =====================================================================

    async def get_violation_penalty(self, chat_id: int, violation_type: str) -> Optional[Dict]:
        return await self.fetchone("SELECT penalty_type, duration_seconds FROM violation_penalties WHERE chat_id = ? AND violation_type = ?", (chat_id, violation_type))

    async def set_violation_penalty(self, chat_id: int, violation_type: str, penalty_type: str, duration_seconds: int) -> bool:
        if penalty_type not in self.VALID_PENALTY_TYPES:
            logger.error(f"❌ Invalid penalty_type: {penalty_type}")
            return False
        if duration_seconds < 0:
            duration_seconds = 0
        return await self.execute(
            """INSERT OR REPLACE INTO violation_penalties 
               (chat_id, violation_type, penalty_type, duration_seconds)
               VALUES (?,?,?,?)""",
            (chat_id, violation_type, penalty_type, duration_seconds)
        )

    async def get_all_violation_penalties(self, chat_id: int) -> Dict[str, Dict]:
        penalties = await self.fetchall("SELECT violation_type, penalty_type, duration_seconds FROM violation_penalties WHERE chat_id = ?", (chat_id,))
        result = {}
        for penalty in penalties:
            result[penalty['violation_type']] = {'penalty_type': penalty['penalty_type'], 'duration_seconds': penalty['duration_seconds']}
        return result

    # =====================================================================
    # دوال تتبع المخالفات
    # =====================================================================

    async def get_violation_count(self, user_id: int, chat_id: int) -> int:
        violation = await self.fetchone("SELECT violation_count, last_violation_time FROM user_violations WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        if not violation:
            return 0
        last_time = TimeUtils.safe_parse_iso(violation['last_violation_time'])
        if last_time:
            if TimeUtils.utc_now() - last_time > timedelta(hours=24):
                await self.execute("UPDATE user_violations SET violation_count = 0 WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
                return 0
        return violation['violation_count']

    async def increment_violation_count(self, user_id: int, chat_id: int) -> int:
        current = await self.get_violation_count(user_id, chat_id)
        new_count = current + 1
        await self.execute(
            """INSERT INTO user_violations (user_id, chat_id, violation_count, last_violation_time)
               VALUES (?,?,?,?)
               ON CONFLICT(user_id, chat_id) DO UPDATE SET
                   violation_count = excluded.violation_count,
                   last_violation_time = excluded.last_violation_time""",
            (user_id, chat_id, new_count, TimeUtils.sql_iso())
        )
        return new_count

    async def reset_violation_count(self, user_id: int, chat_id: int) -> bool:
        return await self.execute("UPDATE user_violations SET violation_count = 0, last_violation_time = NULL WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))

    # =====================================================================
    # دوال النقاط
    # =====================================================================

    async def add_points(self, user_id: int, points: int) -> int:
        await self.execute(
            """INSERT INTO user_points (user_id, points, last_updated)
               VALUES (?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET 
                   points = points + ?,
                   last_updated = ?""",
            (user_id, points, TimeUtils.sql_iso(), points, TimeUtils.sql_iso())
        )
        return await self.get_user_points(user_id)

    async def get_user_points(self, user_id: int) -> int:
        return await self.fetchval("SELECT points FROM user_points WHERE user_id = ?", (user_id,), default=0)

    async def get_user_level(self, user_id: int) -> int:
        points = await self.get_user_points(user_id)
        return (points // 100) + 1

    async def get_top_users(self, limit: int = 10) -> List[Dict]:
        return await self.fetchall(
            """SELECT u.user_id, u.username, u.first_name, COALESCE(up.points, 0) as points
               FROM users u
               LEFT JOIN user_points up ON u.user_id = up.user_id
               ORDER BY points DESC
               LIMIT ?""",
            (limit,)
        )

    # =====================================================================
    # دوال إحصائيات شاملة
    # =====================================================================

    async def get_bot_stats(self) -> Dict:
        stats = {}
        stats['users'] = await self.fetchval("SELECT COUNT(*) FROM users", default=0)
        stats['channels'] = await self.fetchval("SELECT COUNT(*) FROM user_channels", default=0)
        stats['groups'] = await self.fetchval("SELECT COUNT(*) FROM bot_groups", default=0)
        stats['posts'] = await self.fetchval("SELECT COUNT(*) FROM posts", default=0)
        stats['published'] = await self.fetchval("SELECT COUNT(*) FROM posts WHERE published = 1", default=0)
        stats['active_subs'] = await self.fetchval("SELECT COUNT(*) FROM subscriptions WHERE status = 'active' AND end_date > datetime('now')", default=0)
        stats['tickets'] = await self.fetchval("SELECT COUNT(*) FROM support_tickets WHERE status = 'pending'", default=0)
        return stats

    async def get_general_stats(self) -> Dict:
        """إحصائيات عامة للوحة الأدمن"""
        stats = await self.get_bot_stats()
        stats['invoices'] = await self.fetchval("SELECT COUNT(*) FROM invoices", default=0)
        stats['active_penalties'] = await self.fetchval("SELECT COUNT(*) FROM user_penalties WHERE status='active'", default=0)
        return stats

    # =====================================================================
    # دوال النسخ الاحتياطي
    # =====================================================================

    async def backup_auto_replies(self) -> int:
        replies = await self.fetchall("SELECT * FROM auto_replies")
        if not replies:
            return 0
        timestamp = TimeUtils.utc_now().strftime('%Y%m%d_%H%M%S')
        backup_file = PATHS.BACKUPS / f"auto_replies_backup_{timestamp}.json"
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        def _write_json():
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(replies, f, ensure_ascii=False, indent=2)
        await asyncio.to_thread(_write_json)
        return len(replies)

    # =====================================================================
    # دوال إضافية مطلوبة من handlers_message.py
    # =====================================================================

    async def add_admin(self, admin_id: int, added_by: int) -> bool:
        """إضافة مشرف للبوت"""
        return await self.execute(
            "INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)",
            (admin_id, added_by, TimeUtils.sql_iso())
        )

    async def remove_admin(self, admin_id: int) -> bool:
        """إزالة مشرف من البوت"""
        try:
            async with self._get_connection() as conn:
                cursor = await conn.execute("DELETE FROM bot_admins WHERE user_id = ?", (admin_id,))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Error in remove_admin: {e}", exc_info=True)
            return False

    async def get_admin_list(self) -> List[Dict]:
        """جلب قائمة مشرفي البوت"""
        return await self.fetchall("SELECT user_id, added_by, added_at FROM bot_admins ORDER BY added_at DESC")

    async def mark_users_as_blocked(self, user_ids: List[int]) -> int:
        """تحديث حالة المستخدمين كمحظورين"""
        if not user_ids:
            return 0
        try:
            async with self._get_connection() as conn:
                await conn.executemany("UPDATE users SET banned = 1 WHERE user_id = ?", [(uid,) for uid in user_ids])
            return len(user_ids)
        except Exception as e:
            logger.error(f"❌ Error in mark_users_as_blocked: {e}", exc_info=True)
            return 0

    async def check_contest_joined(self, contest_id: int, user_id: int) -> bool:
        """التحقق من أن المستخدم مشترك في المسابقة"""
        result = await self.fetchval("SELECT 1 FROM contest_participants WHERE contest_id = ? AND user_id = ?", (contest_id, user_id))
        return result is not None

    async def get_channel_by_id(self, user_id: int, channel_id: int) -> Optional[Dict]:
        """جلب قناة بواسطة معرف القناة (Telegram ID)"""
        return await self.fetchone("SELECT * FROM user_channels WHERE user_id = ? AND channel_id = ?", (user_id, channel_id))

    async def delete_group(self, chat_id: int) -> bool:
        """حذف مجموعة من قاعدة البيانات"""
        try:
            async with self._get_connection() as conn:
                await conn.execute("DELETE FROM bot_groups WHERE chat_id = ?", (chat_id,))
                await conn.execute("DELETE FROM user_groups_link WHERE chat_id = ?", (chat_id,))
            return True
        except Exception as e:
            logger.error(f"❌ Error in delete_group: {e}", exc_info=True)
            return False

    async def is_channel_owner(self, user_id: int, channel_db_id: int) -> bool:
        """التحقق من أن المستخدم يملك القناة"""
        result = await self.fetchval("SELECT 1 FROM user_channels WHERE id = ? AND user_id = ?", (channel_db_id, user_id))
        return result is not None

    async def count_user_posts(self, user_id: int, channel_db_id: int) -> int:
        """عدد منشورات المستخدم في قناة معينة"""
        return await self.fetchval("SELECT COUNT(*) FROM posts WHERE channel_db_id = ?", (channel_db_id,), default=0)

    async def get_contest_by_id(self, contest_id: int) -> Optional[Dict]:
        """جلب مسابقة بواسطة المعرف"""
        return await self.fetchone("SELECT * FROM contests WHERE id = ?", (contest_id,))


# =====================================================================
# إنشاء كائن قاعدة البيانات
# =====================================================================

DB = Database()


async def get_db() -> Database:
    """الحصول على كائن قاعدة البيانات"""
    return DB


async def initialize_db() -> bool:
    """تهيئة قاعدة البيانات"""
    return await DB.initialize()
