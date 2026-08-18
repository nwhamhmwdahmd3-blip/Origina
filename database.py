#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
database.py - قاعدة البيانات المتكاملة للبوت (النسخة النهائية الكاملة)
- جميع الإصلاحات السابقة مدمجة
- إصلاح مشكلة تجاوز حدود الخطط لمستخدمي التجربة والإحالات
- إضافة خطط افتراضية للتجربة والإحالة وربطها بالاشتراكات
- تحسين الأداء والذرية
- تنظيف الاشتراكات المنتهية وتحديث users.subscription_end
"""

import sqlite3
import json
import logging
import secrets
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from contextlib import asynccontextmanager

import aiosqlite

from config import PATHS, CONFIG

logger = logging.getLogger(__name__)

# =====================================================================
# قوائم بيضاء للأعمدة المسموحة (لمنع SQL Injection)
# =====================================================================

ALLOWED_SECURITY_COLUMNS = {
    'delete_links', 'mentions', 'slow_mode', 'slow_mode_seconds',
    'welcome_enabled', 'welcome_text', 'goodbye_enabled', 'goodbye_text',
    'delete_banned_words', 'auto_penalty', 'auto_mute_duration',
    'delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
    'delete_documents', 'delete_stickers', 'delete_penalty', 'delete_penalty_duration',
    'antiflood_enabled', 'antiflood_messages', 'antiflood_seconds', 'antiflood_penalty',
    'max_warnings', 'warn_penalty', 'max_message_length',
    'night_mode_enabled', 'night_mode_start', 'night_mode_end', 'night_mode_action',
    'nsfw_enabled', 'nsfw_threshold', 'auto_approve_join', 'auto_reject_join',
    'delete_forwarded', 'delete_polls', 'delete_games', 'delete_voice', 'delete_video_note'
}

ALLOWED_AUTO_REPLY_SETTINGS_COLUMNS = {
    'enabled', 'only_admins', 'ignore_bots'
}

ALLOWED_SCHEDULE_COLUMNS = {
    'schedule_type', 'interval_minutes', 'interval_hours', 'interval_days',
    'days_of_week', 'specific_dates', 'publish_time', 'cron_expression',
    'next_publish_date'
}

ALLOWED_USER_COLUMNS = {
    'language', 'auto_publish', 'auto_recycle', 'banned', 'trial_used',
    'subscription_end', 'active_channel'
}

ALLOWED_REMINDER_SETTINGS_COLUMNS = {
    'subscription_reminder', 'daily_stats_reminder', 'weekly_report',
    'reminder_days_before', 'last_reminder_sent', 'notification_lang'
}


class TimeUtils:
    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def mecca_now() -> datetime:
        return TimeUtils.utc_now() + timedelta(hours=3)

    @staticmethod
    def utc_iso() -> str:
        return TimeUtils.utc_now().isoformat()

    @staticmethod
    def mecca_iso() -> str:
        return TimeUtils.mecca_now().isoformat()

    @staticmethod
    def sql_iso() -> str:
        return TimeUtils.utc_now().strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def mecca_to_utc(dt: datetime) -> datetime:
        return dt - timedelta(hours=3) if dt else None

    @staticmethod
    def utc_to_mecca(dt: datetime) -> datetime:
        return dt + timedelta(hours=3) if dt else None

    @staticmethod
    def safe_parse_iso(date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return None


class Database:
    _instance = None
    _lock = None  # initialized later

    def __new__(cls) -> 'Database':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_lock()
        return cls._instance

    def _init_lock(self):
        if not hasattr(self, '_lock') or self._lock is None:
            self._lock = asyncio.Lock()

    @asynccontextmanager
    async def _get_connection(self):
        async with aiosqlite.connect(
            str(PATHS.DB),
            timeout=60,
            check_same_thread=False
        ) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            yield conn

    async def execute(self, query: str, params: tuple = ()) -> None:
        async with self._get_connection() as conn:
            await conn.execute(query, params)
            await conn.commit()

    async def fetchone(self, query: str, params: tuple = ()):
        async with self._get_connection() as conn:
            async with conn.execute(query, params) as cur:
                return await cur.fetchone()

    async def fetchall(self, query: str, params: tuple = ()):
        async with self._get_connection() as conn:
            async with conn.execute(query, params) as cur:
                return await cur.fetchall()

    async def fetchval(self, query: str, params: tuple = ()):
        row = await self.fetchone(query, params)
        return row[0] if row else None

    async def executemany(self, query: str, params: list) -> None:
        if not params:
            return
        async with self._get_connection() as conn:
            await conn.executemany(query, params)
            await conn.commit()

    async def initialize(self) -> None:
        async with self._lock:
            async with self._get_connection() as conn:
                await self._create_tables(conn)
                await self._create_indexes(conn)
                await self._init_default_data(conn)
                await self._import_banned_words(conn)
            logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")

    async def _create_tables(self, conn) -> None:
        # ===================== جداول المستخدمين =====================
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
                published_at TEXT
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
                next_publish_date TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS last_publish (
                channel_db_id INTEGER PRIMARY KEY,
                last_publish_time TEXT
            )
        """)

        # ===================== جداول المجموعات =====================
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
            CREATE TABLE IF NOT EXISTS user_groups_link (
                user_id INTEGER,
                chat_id INTEGER,
                PRIMARY KEY (user_id, chat_id)
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
                chat_id INTEGER,
                owner_id INTEGER,
                is_hidden INTEGER DEFAULT 1,
                PRIMARY KEY (chat_id, owner_id)
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

        # ===================== جداول الأمان =====================
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
                nsfw_enabled INTEGER DEFAULT 0,
                nsfw_threshold REAL DEFAULT 0.7,
                auto_approve_join INTEGER DEFAULT 0,
                auto_reject_join INTEGER DEFAULT 0
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
            CREATE TABLE IF NOT EXISTS banned_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT,
                chat_id INTEGER,
                added_by INTEGER,
                added_at TEXT,
                UNIQUE(word, chat_id)
            )
        """)

        # ===================== جداول الردود التلقائية =====================
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_reply_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                only_admins INTEGER DEFAULT 0,
                ignore_bots INTEGER DEFAULT 1,
                updated_at TEXT
            )
        """)

        # ===================== جداول الدعم =====================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                message TEXT,
                media_type TEXT,
                media_file_id TEXT,
                ticket_number INTEGER UNIQUE,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                replied INTEGER DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('publish_interval', '720')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_backup', '1')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_ticket_number', '0')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_backup', '')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('min_publish_interval', '12')")

        # ===================== جداول الإحالات =====================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                created_at TEXT,
                UNIQUE(referrer_id, referred_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referral_rewards (
                user_id INTEGER PRIMARY KEY,
                referral_count INTEGER DEFAULT 0,
                total_reward_days INTEGER DEFAULT 0,
                claimed_reward_days INTEGER DEFAULT 0,
                last_referral_date TEXT
            )
        """)

        # ===================== جداول التذكيرات =====================
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_translation (
                user_id INTEGER PRIMARY KEY,
                lang TEXT DEFAULT 'off'
            )
        """)

        # ===================== جداول المسابقات =====================
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

        # ===================== جداول السجلات والإدارة =====================
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_warnings (
                user_id INTEGER,
                chat_id INTEGER,
                warnings INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, chat_id)
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
            CREATE TABLE IF NOT EXISTS user_messages (
                user_id INTEGER,
                chat_id INTEGER,
                message_time TEXT,
                PRIMARY KEY (user_id, chat_id)
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

        # ===================== جداول الباقات والاشتراكات =====================
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
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            )
        """)
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
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            )
        """)
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

        # ===================== جداول الهدايا (Gift Codes) =====================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gift_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                days INTEGER NOT NULL,
                price INTEGER NOT NULL,
                currency TEXT DEFAULT 'XTR',
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gift_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                days INTEGER NOT NULL,
                plan_id INTEGER,
                created_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                used_by INTEGER DEFAULT NULL,
                used_at TEXT DEFAULT NULL,
                is_used INTEGER DEFAULT 0,
                FOREIGN KEY (plan_id) REFERENCES gift_plans(id)
            )
        """)

        await conn.commit()

    async def _create_indexes(self, conn) -> None:
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_banned ON users(banned)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_language ON users(language)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_subscription ON users(subscription_end)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_updated ON users(updated_at)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_uc_user ON user_channels(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_uc_active ON user_channels(banned)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_fail ON posts(fail_count)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sched_next ON schedule(next_publish_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_banned ON bot_groups(banned)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_group_admins_user ON group_admins(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_group_admins_chat ON group_admins(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_chat ON group_security(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_banned_words_chat ON banned_words(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_banned_words_word ON banned_words(word)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_warnings_user ON user_warnings(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_warnings_chat ON user_warnings(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_chat ON admin_logs(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_admin ON admin_logs(admin_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_created ON admin_logs(created_at)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ar_chat ON auto_replies(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ar_keyword ON auto_replies(keyword)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_auto_replies_lookup ON auto_replies(chat_id, keyword, is_active)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_user ON support_tickets(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status)")
        await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tickets_number ON support_tickets(ticket_number)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_status ON subscriptions(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_end ON subscriptions(end_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_user_status_end ON subscriptions(user_id, status, end_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_user ON invoices(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_status ON invoices(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_plans_is_gift ON plans(is_gift)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contests_end ON contests(end_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contest_participants_contest ON contest_participants(contest_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contest_participants_user ON contest_participants(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_user ON user_reminder_settings(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_gift_codes_code ON gift_codes(code)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_gift_codes_used ON gift_codes(is_used)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_gift_codes_created ON gift_codes(created_by)")
        await conn.commit()

    async def _init_default_data(self, conn) -> None:
        default_plans = [
            {"name": "يوم", "description": "باقة يوم واحد", "price": 5, "duration_days": 1, "max_channels": 1, "max_posts": 50, "features": '{"auto_publish":true}'},
            {"name": "أسبوع", "description": "باقة 7 أيام", "price": 25, "duration_days": 7, "max_channels": 3, "max_posts": 300, "features": '{"auto_publish":true,"security":true}'},
            {"name": "شهر", "description": "باقة 30 يوم", "price": 75, "duration_days": 30, "max_channels": 10, "max_posts": 1500, "features": '{"auto_publish":true,"security":true,"support":true}'},
            {"name": "3 أشهر", "description": "باقة 90 يوم", "price": 200, "duration_days": 90, "max_channels": 999, "max_posts": 99999, "features": '{"auto_publish":true,"security":true,"support":true,"analytics":true}'},
        ]
        for plan in default_plans:
            row = await conn.execute("SELECT id FROM plans WHERE name=?", (plan["name"],))
            if not await row.fetchone():
                await conn.execute("""
                    INSERT INTO plans (name, description, price, currency, duration_days, max_channels, max_posts, features, is_active, is_gift, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (plan["name"], plan["description"], plan["price"], "XTR", plan["duration_days"], plan["max_channels"], plan["max_posts"], plan["features"], 1, 0, TimeUtils.sql_iso()))

        # خطة التجربة (is_active=0 حتى لا تظهر في الشراء)
        trial_plan = await conn.execute("SELECT id FROM plans WHERE name='تجربة'")
        if not await trial_plan.fetchone():
            await conn.execute(
                """INSERT INTO plans 
                   (name, description, price, currency, duration_days, max_channels, max_posts, features, is_active, is_gift, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                ("تجربة", "خطة التجربة المجانية", 0, "XTR", 30, 1, 50,
                 '{"auto_publish":true}', 0, 0, TimeUtils.sql_iso())
            )

        # خطة الإحالة (is_active=0)
        referral_plan = await conn.execute("SELECT id FROM plans WHERE name='إحالة'")
        if not await referral_plan.fetchone():
            await conn.execute(
                """INSERT INTO plans 
                   (name, description, price, currency, duration_days, max_channels, max_posts, features, is_active, is_gift, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                ("إحالة", "خطة مكافآت الإحالة", 0, "XTR", 0, 2, 100,
                 '{"auto_publish":true}', 0, 0, TimeUtils.sql_iso())
            )

        # خطة الهدايا الافتراضية في جدول plans (is_gift=1)
        gift_plan_row = await conn.execute("SELECT id FROM plans WHERE is_gift=1")
        if not await gift_plan_row.fetchone():
            await conn.execute(
                "INSERT INTO plans (name, description, price, currency, duration_days, max_channels, max_posts, features, is_active, is_gift, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("هدية", "خطة للهدايا المستردة", 0, "XTR", 0, 999, 99999, '{"auto_publish":true,"security":true,"support":true}', 1, 1, TimeUtils.sql_iso())
            )

        # خطط الهدايا في gift_plans
        default_gift_plans = [
            {"days": 7, "price": 50},
            {"days": 30, "price": 150},
            {"days": 90, "price": 400},
        ]
        for plan in default_gift_plans:
            row = await conn.execute("SELECT id FROM gift_plans WHERE days=? AND price=?", (plan["days"], plan["price"]))
            if not await row.fetchone():
                await conn.execute(
                    "INSERT INTO gift_plans (days, price, currency, is_active, created_at) VALUES (?,?,?,?,?)",
                    (plan["days"], plan["price"], "XTR", 1, TimeUtils.sql_iso())
                )
                logger.info(f"✅ تم إضافة خطة هدية: {plan['days']} يوم - {plan['price']} ⭐")

        await conn.commit()

    async def _import_banned_words(self, conn) -> None:
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
            await conn.commit()
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
            code = secrets.token_urlsafe(6)
            await self.execute(
                """INSERT INTO users 
                   (user_id, username, first_name, referral_code, trial_used, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       username = excluded.username,
                       first_name = excluded.first_name,
                       updated_at = excluded.updated_at""",
                (user_id, username, first_name, code, 0, TimeUtils.sql_iso(), TimeUtils.sql_iso())
            )
            return True
        except Exception as e:
            logger.error(f"❌ Error in register_user: {e}", exc_info=True)
            return False

    async def get_user(self, user_id: int) -> Optional[Dict]:
        try:
            row = await self.fetchone("SELECT * FROM users WHERE user_id=?", (user_id,))
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Error in get_user: {e}", exc_info=True)
            return None

    async def get_user_language(self, user_id: int) -> str:
        try:
            row = await self.fetchone("SELECT language FROM users WHERE user_id=?", (user_id,))
            return row[0] if row else 'ar'
        except Exception as e:
            logger.error(f"❌ Error in get_user_language: {e}", exc_info=True)
            return 'ar'

    async def set_user_language(self, user_id: int, lang: str) -> bool:
        try:
            await self.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))
            return True
        except Exception as e:
            logger.error(f"❌ Error in set_user_language: {e}", exc_info=True)
            return False

    async def get_auto_publish_status(self, user_id: int) -> bool:
        try:
            row = await self.fetchone("SELECT auto_publish FROM users WHERE user_id=?", (user_id,))
            return row and row[0] == 1
        except Exception as e:
            logger.error(f"❌ Error in get_auto_publish_status: {e}", exc_info=True)
            return False

    async def set_auto_publish(self, user_id: int, status: bool) -> bool:
        try:
            await self.execute("UPDATE users SET auto_publish=? WHERE user_id=?", (1 if status else 0, user_id))
            return True
        except Exception as e:
            logger.error(f"❌ Error in set_auto_publish: {e}", exc_info=True)
            return False

    async def get_auto_recycle_status(self, user_id: int) -> bool:
        try:
            row = await self.fetchone("SELECT auto_recycle FROM users WHERE user_id=?", (user_id,))
            return row and row[0] == 1
        except Exception as e:
            logger.error(f"❌ Error in get_auto_recycle_status: {e}", exc_info=True)
            return False

    async def set_auto_recycle(self, user_id: int, status: bool) -> bool:
        try:
            await self.execute("UPDATE users SET auto_recycle=? WHERE user_id=?", (1 if status else 0, user_id))
            return True
        except Exception as e:
            logger.error(f"❌ Error in set_auto_recycle: {e}", exc_info=True)
            return False

    async def is_user_banned(self, user_id: int) -> bool:
        try:
            row = await self.fetchone("SELECT banned FROM users WHERE user_id=?", (user_id,))
            return row and row[0] == 1
        except Exception as e:
            logger.error(f"❌ Error in is_user_banned: {e}", exc_info=True)
            return False

    async def ban_user(self, user_id: int) -> bool:
        try:
            await self.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
            return True
        except Exception as e:
            logger.error(f"❌ Error in ban_user: {e}", exc_info=True)
            return False

    async def unban_user(self, user_id: int) -> bool:
        try:
            await self.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
            return True
        except Exception as e:
            logger.error(f"❌ Error in unban_user: {e}", exc_info=True)
            return False

    async def get_all_users(self) -> List[Tuple[int, int]]:
        try:
            rows = await self.fetchall("SELECT user_id, banned FROM users")
            return [(row[0], row[1]) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_all_users: {e}", exc_info=True)
            return []

    async def get_user_stats(self) -> Dict:
        try:
            total = (await self.fetchone("SELECT COUNT(*) FROM users"))[0]
            banned = (await self.fetchone("SELECT COUNT(*) FROM users WHERE banned=1"))[0]
            return {'users': total, 'banned': banned}
        except Exception as e:
            logger.error(f"❌ Error in get_user_stats: {e}", exc_info=True)
            return {'users': 0, 'banned': 0}

    async def has_active_subscription(self, user_id: int) -> bool:
        try:
            # نعتمد على subscriptions أولاً ثم users كاحتياطي
            sub = await self.get_active_subscription(user_id)
            if sub:
                return True
            row = await self.fetchone(
                "SELECT subscription_end FROM users WHERE user_id=? AND subscription_end > datetime('now')",
                (user_id,)
            )
            return row is not None
        except Exception as e:
            logger.error(f"❌ Error in has_active_subscription: {e}", exc_info=True)
            return False

    async def has_used_trial(self, user_id: int) -> bool:
        try:
            row = await self.fetchone("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
            return row and row[0] == 1
        except Exception as e:
            logger.error(f"❌ Error in has_used_trial: {e}", exc_info=True)
            return False

    async def activate_trial(self, user_id: int) -> int:
        try:
            async with self._get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                cur = await conn.execute("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
                row = await cur.fetchone()
                if row and row[0] == 1:
                    await conn.rollback()
                    return 0

                trial_plan_id = await self._get_or_create_trial_plan_id(conn)
                await self._grant_subscription_days_conn(conn, user_id, days=30, plan_id=trial_plan_id, provider='trial')
                await conn.execute("UPDATE users SET trial_used=1 WHERE user_id=?", (user_id,))
                await conn.commit()
                return 30
        except Exception as e:
            logger.error(f"❌ Error in activate_trial: {e}", exc_info=True)
            return 0

    async def get_referral_code(self, user_id: int) -> str:
        try:
            row = await self.fetchone("SELECT referral_code FROM users WHERE user_id=?", (user_id,))
            return row[0] if row else f"ref_{user_id}"
        except Exception as e:
            logger.error(f"❌ Error in get_referral_code: {e}", exc_info=True)
            return f"ref_{user_id}"

    async def get_user_by_referral_code(self, code: str) -> Optional[int]:
        try:
            row = await self.fetchone("SELECT user_id FROM users WHERE referral_code=?", (code,))
            return row[0] if row else None
        except Exception as e:
            logger.error(f"❌ Error in get_user_by_referral_code: {e}", exc_info=True)
            return None

    async def get_active_plan(self, user_id: int) -> Optional[Dict]:
        try:
            sub = await self.get_active_subscription(user_id)
            if sub and sub['plan_id'] is not None:
                return await self.get_plan(sub['plan_id'])
            return None
        except Exception as e:
            logger.error(f"❌ Error in get_active_plan: {e}", exc_info=True)
            return None

    # =====================================================================
    # دوال مساعدة داخلية للخطط
    # =====================================================================

    async def _get_or_create_trial_plan_id(self, conn) -> int:
        row = await (await conn.execute("SELECT id FROM plans WHERE name='تجربة'")).fetchone()
        if row:
            return row[0]
        await conn.execute(
            """INSERT INTO plans 
               (name, description, price, currency, duration_days, max_channels, max_posts, features, is_active, is_gift, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            ("تجربة", "خطة التجربة المجانية", 0, "XTR", 30, 1, 50,
             '{"auto_publish":true}', 0, 0, TimeUtils.sql_iso())
        )
        return (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

    async def _get_or_create_referral_plan_id(self, conn) -> int:
        row = await (await conn.execute("SELECT id FROM plans WHERE name='إحالة'")).fetchone()
        if row:
            return row[0]
        await conn.execute(
            """INSERT INTO plans 
               (name, description, price, currency, duration_days, max_channels, max_posts, features, is_active, is_gift, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            ("إحالة", "خطة مكافآت الإحالة", 0, "XTR", 0, 2, 100,
             '{"auto_publish":true}', 0, 0, TimeUtils.sql_iso())
        )
        return (await (await conn.execute("SELECT last_insert_rowid()")).fetchone())[0]

    async def _get_active_plan_conn(self, conn, user_id: int) -> Optional[Dict]:
        row = await (await conn.execute("""
            SELECT p.* FROM subscriptions s
            JOIN plans p ON s.plan_id = p.id
            WHERE s.user_id=? AND s.status='active' AND s.end_date > datetime('now')
            ORDER BY s.end_date DESC LIMIT 1
        """, (user_id,))).fetchone()
        if row:
            return dict(row)
        return None

    # =====================================================================
    # دوال القنوات
    # =====================================================================

    async def add_channel(self, user_id: int, channel_id: int, channel_name: str) -> Optional[int]:
        try:
            channel_id = int(channel_id)
            async with self._get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                cur = await conn.execute(
                    "SELECT id, banned FROM user_channels WHERE user_id=? AND channel_id=?",
                    (user_id, channel_id)
                )
                existing = await cur.fetchone()
                if existing:
                    ch_db_id, banned = existing
                    if banned:
                        await conn.rollback()
                        logger.warning(f"⚠️ محاولة إضافة قناة محظورة: {channel_id} للمستخدم {user_id}")
                        return None
                    await conn.commit()
                    return ch_db_id

                # التحقق من حد القنوات (فقط للمستخدمين غير المالك)
                if user_id != CONFIG.PRIMARY_OWNER_ID:
                    plan = await self._get_active_plan_conn(conn, user_id)
                    if plan and plan.get('max_channels') is not None:
                        cur = await conn.execute(
                            "SELECT COUNT(*) FROM user_channels WHERE user_id=? AND banned=0",
                            (user_id,)
                        )
                        count = (await cur.fetchone())[0]
                        if count >= plan['max_channels']:
                            await conn.rollback()
                            logger.warning(f"⚠️ المستخدم {user_id} تجاوز حد القنوات المسموح ({plan['max_channels']})")
                            return None

                await conn.execute(
                    "INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) VALUES (?,?,?,?)",
                    (user_id, channel_id, channel_name, TimeUtils.sql_iso())
                )
                cur = await conn.execute("SELECT id FROM user_channels WHERE user_id=? AND channel_id=?", (user_id, channel_id))
                row = await cur.fetchone()
                ch_db_id = row[0] if row else None

                cur = await conn.execute("SELECT value FROM settings WHERE key='min_publish_interval'")
                row = await cur.fetchone()
                min_interval = int(row[0]) if row and row[0] else 12
                next_date = (TimeUtils.utc_now() + timedelta(minutes=min_interval)).strftime('%Y-%m-%d %H:%M:%S')
                await conn.execute(
                    "INSERT OR IGNORE INTO schedule (channel_db_id, interval_minutes, next_publish_date) VALUES (?,?,?)",
                    (ch_db_id, min_interval, next_date)
                )
                await conn.commit()
                return ch_db_id
        except Exception as e:
            logger.error(f"❌ Error in add_channel: {e}", exc_info=True)
            return None

    async def get_user_channels(self, user_id: int) -> List[Dict]:
        try:
            rows = await self.fetchall(
                "SELECT id, channel_id, channel_name, banned, created_at FROM user_channels WHERE user_id=? ORDER BY created_at DESC",
                (user_id,)
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_user_channels: {e}", exc_info=True)
            return []

    async def get_active_channel(self, user_id: int) -> Optional[int]:
        try:
            row = await self.fetchone("SELECT active_channel FROM users WHERE user_id=?", (user_id,))
            if row and row[0]:
                banned = await self.fetchone("SELECT banned FROM user_channels WHERE id=?", (row[0],))
                if banned and banned[0] == 0:
                    return row[0]
            row2 = await self.fetchone(
                "SELECT id FROM user_channels WHERE user_id=? AND banned=0 ORDER BY id LIMIT 1",
                (user_id,)
            )
            return row2[0] if row2 else None
        except Exception as e:
            logger.error(f"❌ Error in get_active_channel: {e}", exc_info=True)
            return None

    async def set_active_channel(self, user_id: int, channel_id: int) -> bool:
        try:
            row = await self.fetchone(
                "SELECT 1 FROM user_channels WHERE id=? AND user_id=? AND banned=0",
                (channel_id, user_id)
            )
            if not row:
                logger.warning(f"⚠️ محاولة تعيين قناة غير مملوكة أو محظورة: {channel_id} للمستخدم {user_id}")
                return False
            await self.execute("UPDATE users SET active_channel=? WHERE user_id=?", (channel_id, user_id))
            return True
        except Exception as e:
            logger.error(f"❌ Error in set_active_channel: {e}", exc_info=True)
            return False

    async def delete_channel(self, user_id: int, channel_id: int) -> bool:
        try:
            async with self._get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                cur = await conn.execute("SELECT id FROM user_channels WHERE id=? AND user_id=?", (channel_id, user_id))
                row = await cur.fetchone()
                if not row:
                    await conn.rollback()
                    return False
                channel_db_id = row[0]
                await conn.execute("DELETE FROM user_channels WHERE id=?", (channel_db_id,))
                await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (channel_db_id,))
                await conn.execute("DELETE FROM schedule WHERE channel_db_id=?", (channel_db_id,))
                await conn.execute("DELETE FROM last_publish WHERE channel_db_id=?", (channel_db_id,))
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ Error in delete_channel: {e}", exc_info=True)
            return False

    async def get_channel_info(self, channel_id: int) -> Optional[Dict]:
        try:
            row = await self.fetchone("SELECT * FROM user_channels WHERE id=?", (channel_id,))
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Error in get_channel_info: {e}", exc_info=True)
            return None

    async def get_channel_stats(self, channel_id: int) -> Dict:
        try:
            total = (await self.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_id,)))[0]
            published = (await self.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=1", (channel_id,)))[0]
            return {'total': total, 'published': published, 'unpublished': total - published}
        except Exception as e:
            logger.error(f"❌ Error in get_channel_stats: {e}", exc_info=True)
            return {'total': 0, 'published': 0, 'unpublished': 0}

    # =====================================================================
    # دوال المنشورات
    # =====================================================================

    async def add_posts(self, channel_id: int, posts: List[Tuple[str, str, str]]) -> int:
        try:
            channel_info = await self.get_channel_info(channel_id)
            if not channel_info:
                return 0
            user_id = channel_info['user_id']
            if user_id != CONFIG.PRIMARY_OWNER_ID:
                plan = await self.get_active_plan(user_id)
                if plan and plan.get('max_posts') is not None:
                    row = await self.fetchone(
                        "SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=?",
                        (user_id,)
                    )
                    current_total = row[0] if row else 0
                    new_count = len(posts)
                    if current_total + new_count > plan['max_posts']:
                        logger.warning(f"⚠️ المستخدم {user_id} تجاوز حد المنشورات المسموح ({plan['max_posts']})")
                        return 0

            total = 0
            for i in range(0, len(posts), 100):
                batch = posts[i:i+100]
                vals = [(channel_id, (t or "")[:4096], m, f, TimeUtils.sql_iso()) for t, m, f in batch]
                await self.executemany(
                    "INSERT INTO posts (channel_db_id, text, media_type, media_file_id, created_at) VALUES (?,?,?,?,?)",
                    vals
                )
                total += len(vals)
            return total
        except Exception as e:
            logger.error(f"❌ Error in add_posts: {e}", exc_info=True)
            return 0

    async def get_unpublished_posts_count(self, channel_id: int) -> int:
        try:
            row = await self.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=0", (channel_id,))
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"❌ Error in get_unpublished_posts_count: {e}", exc_info=True)
            return 0

    async def get_user_unpublished_count(self, user_id: int) -> int:
        try:
            row = await self.fetchone(
                "SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=? AND p.published=0",
                (user_id,)
            )
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"❌ Error in get_user_unpublished_count: {e}", exc_info=True)
            return 0

    async def get_user_total_posts(self, user_id: int) -> int:
        try:
            row = await self.fetchone(
                "SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=?",
                (user_id,)
            )
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"❌ Error in get_user_total_posts: {e}", exc_info=True)
            return 0

    async def get_next_post(self, channel_id: int) -> Optional[Dict]:
        try:
            row = await self.fetchone(
                "SELECT id, text, media_type, media_file_id FROM posts WHERE channel_db_id=? AND published=0 AND (fail_count IS NULL OR fail_count < 3) ORDER BY created_at ASC LIMIT 1",
                (channel_id,)
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Error in get_next_post: {e}", exc_info=True)
            return None

    async def get_user_posts(self, channel_id: int, limit: int = 15) -> List[Dict]:
        try:
            rows = await self.fetchall(
                "SELECT id, text, media_type, media_file_id FROM posts WHERE channel_db_id=? AND published=0 ORDER BY created_at ASC LIMIT ?",
                (channel_id, limit)
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_user_posts: {e}", exc_info=True)
            return []

    async def mark_post_published(self, post_id: int) -> bool:
        try:
            await self.execute("UPDATE posts SET published=1, published_at=? WHERE id=?", (TimeUtils.sql_iso(), post_id))
            return True
        except Exception as e:
            logger.error(f"❌ Error in mark_post_published: {e}", exc_info=True)
            return False

    async def increment_post_fail(self, post_id: int) -> bool:
        try:
            await self.execute("UPDATE posts SET fail_count = fail_count + 1 WHERE id=?", (post_id,))
            return True
        except Exception as e:
            logger.error(f"❌ Error in increment_post_fail: {e}", exc_info=True)
            return False

    async def delete_post(self, post_id: int, user_id: int, channel_id: int) -> bool:
        try:
            row = await self.fetchone("SELECT 1 FROM user_channels WHERE id=? AND user_id=?", (channel_id, user_id))
            if not row:
                return False
            await self.execute("DELETE FROM posts WHERE id=? AND channel_db_id=?", (post_id, channel_id))
            return True
        except Exception as e:
            logger.error(f"❌ Error in delete_post: {e}", exc_info=True)
            return False

    async def reset_posts(self, channel_id: int) -> int:
        try:
            await self.execute("UPDATE posts SET published=0 WHERE channel_db_id=?", (channel_id,))
            return await self.get_unpublished_posts_count(channel_id)
        except Exception as e:
            logger.error(f"❌ Error in reset_posts: {e}", exc_info=True)
            return 0

    # =====================================================================
    # دوال المجموعات
    # =====================================================================

    async def register_group(self, chat_id: int, chat_name: str, user_id: int, username: str = None) -> bool:
        try:
            await self.execute(
                "INSERT OR IGNORE INTO bot_groups (chat_id, chat_name, username, added_by, added_at) VALUES (?,?,?,?,?)",
                (chat_id, chat_name, username, user_id, TimeUtils.sql_iso())
            )
            await self.execute(
                "UPDATE bot_groups SET chat_name=?, username=?, updated_at=? WHERE chat_id=?",
                (chat_name, username, TimeUtils.sql_iso(), chat_id)
            )
            return True
        except Exception as e:
            logger.error(f"❌ Error in register_group: {e}", exc_info=True)
            return False

    async def get_user_groups(self, user_id: int) -> List[Tuple[int, str, str, int]]:
        try:
            rows = await self.fetchall("""
                SELECT chat_id, chat_name, username, banned FROM bot_groups
                WHERE chat_id IN (
                    SELECT chat_id FROM user_groups_link WHERE user_id=?
                    UNION
                    SELECT chat_id FROM hidden_owner_groups WHERE owner_id=?
                    UNION
                    SELECT chat_id FROM hidden_admins WHERE admin_id=?
                    UNION
                    SELECT chat_id FROM group_admins WHERE user_id=?
                )
            """, (user_id, user_id, user_id, user_id))
            return [(row[0], row[1], row[2] or "", row[3]) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_user_groups: {e}", exc_info=True)
            return []

    async def sync_group_admins(self, chat_id: int, admin_ids: List[int]) -> int:
        try:
            async with self._get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                await conn.execute("DELETE FROM group_admins WHERE chat_id=?", (chat_id,))
                if admin_ids:
                    await conn.executemany(
                        "INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?,?)",
                        [(chat_id, uid) for uid in admin_ids]
                    )
                await conn.commit()
                return len(admin_ids)
        except Exception as e:
            logger.error(f"❌ Error in sync_group_admins: {e}", exc_info=True)
            return 0

    async def add_hidden_admin(self, chat_id: int, admin_id: int, added_by: int) -> bool:
        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,1)",
                    (chat_id, admin_id)
                )
                await conn.execute(
                    "INSERT OR IGNORE INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?,?,?,?)",
                    (chat_id, admin_id, added_by, TimeUtils.sql_iso())
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ Error in add_hidden_admin: {e}", exc_info=True)
            return False

    async def remove_hidden_admin(self, chat_id: int, admin_id: int) -> bool:
        try:
            async with self._get_connection() as conn:
                await conn.execute("DELETE FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, admin_id))
                await conn.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ Error in remove_hidden_admin: {e}", exc_info=True)
            return False

    async def get_hidden_admins(self, chat_id: int) -> List[Dict]:
        try:
            rows = await self.fetchall(
                "SELECT admin_id, added_by, added_at FROM hidden_admins WHERE chat_id=? ORDER BY added_at DESC",
                (chat_id,)
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_hidden_admins: {e}", exc_info=True)
            return []

    # =====================================================================
    # دوال الأمان (مع التحقق من القائمة البيضاء)
    # =====================================================================

    async def get_security_settings(self, chat_id: int) -> Dict:
        try:
            row = await self.fetchone("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
            if row:
                return dict(row)
            await self.execute("INSERT OR IGNORE INTO group_security (chat_id) VALUES (?)", (chat_id,))
            row = await self.fetchone("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
            return dict(row) if row else {}
        except Exception as e:
            logger.error(f"❌ Error in get_security_settings: {e}", exc_info=True)
            return {}

    async def update_security_settings(self, chat_id: int, **kwargs) -> bool:
        try:
            if not kwargs:
                return True
            for key in kwargs:
                if key not in ALLOWED_SECURITY_COLUMNS:
                    raise ValueError(f"عمود غير صالح: {key}")
            updates = [f"{k}=?" for k in kwargs]
            vals = list(kwargs.values()) + [chat_id]
            await self.execute(f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id=?", vals)
            return True
        except Exception as e:
            logger.error(f"❌ Error in update_security_settings: {e}", exc_info=True)
            return False

    async def get_banned_words(self, chat_id: int) -> List[str]:
        try:
            rows = await self.fetchall(
                "SELECT word FROM banned_words WHERE chat_id=? OR chat_id=-1",
                (chat_id,)
            )
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_banned_words: {e}", exc_info=True)
            return []

    async def add_banned_word(self, word: str, chat_id: int, added_by: int) -> Tuple[bool, bool]:
        try:
            word = word.strip().lower()
            await self.execute(
                "INSERT INTO banned_words (word, chat_id, added_by, added_at) VALUES (?,?,?,?)",
                (word, chat_id, added_by, TimeUtils.sql_iso())
            )
            return True, False
        except sqlite3.IntegrityError:
            return False, True
        except Exception as e:
            logger.error(f"❌ Error in add_banned_word: {e}", exc_info=True)
            return False, False

    async def remove_banned_word(self, word: str, chat_id: int) -> bool:
        try:
            word = word.strip().lower()
            await self.execute("DELETE FROM banned_words WHERE word=? AND chat_id=?", (word, chat_id))
            return True
        except Exception as e:
            logger.error(f"❌ Error in remove_banned_word: {e}", exc_info=True)
            return False

    async def get_user_warnings(self, user_id: int, chat_id: int) -> int:
        try:
            row = await self.fetchone("SELECT warnings FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"❌ Error in get_user_warnings: {e}", exc_info=True)
            return 0

    async def add_user_warning(self, user_id: int, chat_id: int) -> int:
        try:
            await self.execute(
                "INSERT INTO user_warnings (user_id, chat_id, warnings) VALUES (?,?,1) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET warnings = warnings + 1",
                (user_id, chat_id)
            )
            return await self.get_user_warnings(user_id, chat_id)
        except Exception as e:
            logger.error(f"❌ Error in add_user_warning: {e}", exc_info=True)
            return 0

    async def reset_user_warnings(self, user_id: int, chat_id: int) -> bool:
        try:
            await self.execute("UPDATE user_warnings SET warnings=0 WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            return True
        except Exception as e:
            logger.error(f"❌ Error in reset_user_warnings: {e}", exc_info=True)
            return False

    async def add_admin_log(self, chat_id: int, admin_id: int, action: str, target_id: int = None, reason: str = "") -> bool:
        try:
            await self.execute(
                "INSERT INTO admin_logs (chat_id, admin_id, action, target_id, reason, created_at) VALUES (?,?,?,?,?,?)",
                (chat_id, admin_id, action, target_id, reason, TimeUtils.sql_iso())
            )
            return True
        except Exception as e:
            logger.error(f"❌ Error in add_admin_log: {e}", exc_info=True)
            return False

    async def get_admin_logs(self, chat_id: int, limit: int = 20) -> List[Dict]:
        try:
            rows = await self.fetchall(
                "SELECT admin_id, action, target_id, reason, created_at FROM admin_logs WHERE chat_id=? ORDER BY id DESC LIMIT ?",
                (chat_id, limit)
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_admin_logs: {e}", exc_info=True)
            return []

    # =====================================================================
    # دوال الردود التلقائية (مع التحقق من القائمة البيضاء)
    # =====================================================================

    async def get_auto_reply_settings(self, chat_id: int) -> Dict:
        try:
            row = await self.fetchone("SELECT * FROM auto_reply_settings WHERE chat_id=?", (chat_id,))
            if row:
                return dict(row)
            await self.execute("INSERT OR IGNORE INTO auto_reply_settings (chat_id) VALUES (?)", (chat_id,))
            row = await self.fetchone("SELECT * FROM auto_reply_settings WHERE chat_id=?", (chat_id,))
            return dict(row) if row else {'enabled': 0, 'only_admins': 0, 'ignore_bots': 1}
        except Exception as e:
            logger.error(f"❌ Error in get_auto_reply_settings: {e}", exc_info=True)
            return {'enabled': 0, 'only_admins': 0, 'ignore_bots': 1}

    async def update_auto_reply_settings(self, chat_id: int, **kwargs) -> bool:
        try:
            if not kwargs:
                return True
            for key in kwargs:
                if key not in ALLOWED_AUTO_REPLY_SETTINGS_COLUMNS:
                    raise ValueError(f"عمود غير صالح: {key}")
            updates = [f"{k}=?" for k in kwargs]
            vals = list(kwargs.values()) + [chat_id]
            await self.execute(f"UPDATE auto_reply_settings SET {', '.join(updates)} WHERE chat_id=?", vals)
            return True
        except Exception as e:
            logger.error(f"❌ Error in update_auto_reply_settings: {e}", exc_info=True)
            return False

    async def add_auto_reply(self, chat_id: int, keyword: str, reply: str,
                             reply_type: str = 'text', media_id: str = None,
                             buttons: str = None) -> bool:
        try:
            keyword = keyword.lower().strip()
            await self.execute(
                """INSERT INTO auto_replies 
                   (chat_id, keyword, reply, reply_type, reply_media_id, reply_buttons, created_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(chat_id, keyword) DO UPDATE SET
                       reply = excluded.reply,
                       reply_type = excluded.reply_type,
                       reply_media_id = excluded.reply_media_id,
                       reply_buttons = excluded.reply_buttons,
                       created_at = excluded.created_at""",
                (chat_id, keyword, reply, reply_type, media_id, buttons, TimeUtils.sql_iso())
            )
            return True
        except Exception as e:
            logger.error(f"❌ Error in add_auto_reply: {e}", exc_info=True)
            return False

    async def remove_auto_reply(self, chat_id: int, keyword: str) -> bool:
        try:
            keyword = keyword.lower().strip()
            await self.execute("DELETE FROM auto_replies WHERE chat_id=? AND keyword=?", (chat_id, keyword))
            return True
        except Exception as e:
            logger.error(f"❌ Error in remove_auto_reply: {e}", exc_info=True)
            return False

    async def get_auto_reply(self, keyword: str, chat_id: int) -> Optional[Dict]:
        try:
            keyword = keyword.lower().strip()
            async with self._get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                cur = await conn.execute(
                    "SELECT reply, reply_type, reply_media_id, reply_buttons FROM auto_replies WHERE chat_id=? AND keyword=? AND is_active=1",
                    (chat_id, keyword)
                )
                row = await cur.fetchone()
                if row:
                    await conn.execute(
                        "UPDATE auto_replies SET usage_count = usage_count + 1 WHERE chat_id=? AND keyword=?",
                        (chat_id, keyword)
                    )
                    await conn.commit()
                    return dict(row)
                cur = await conn.execute(
                    "SELECT reply, reply_type, reply_media_id, reply_buttons FROM auto_replies WHERE chat_id=-1 AND keyword=? AND is_active=1",
                    (keyword,)
                )
                row = await cur.fetchone()
                if row:
                    await conn.execute(
                        "UPDATE auto_replies SET usage_count = usage_count + 1 WHERE chat_id=-1 AND keyword=?",
                        (keyword,)
                    )
                    await conn.commit()
                    return dict(row)
                await conn.commit()
                return None
        except Exception as e:
            logger.error(f"❌ Error in get_auto_reply: {e}", exc_info=True)
            return None

    async def get_auto_reply_stats(self, chat_id: int, limit: int = 20) -> List[Tuple[str, int]]:
        try:
            rows = await self.fetchall(
                "SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? ORDER BY usage_count DESC LIMIT ?",
                (chat_id, limit)
            )
            return [(row[0], row[1]) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_auto_reply_stats: {e}", exc_info=True)
            return []

    async def reset_auto_replies(self, chat_id: int) -> bool:
        try:
            await self.execute("DELETE FROM auto_replies WHERE chat_id=?", (chat_id,))
            return True
        except Exception as e:
            logger.error(f"❌ Error in reset_auto_replies: {e}", exc_info=True)
            return False

    # =====================================================================
    # دوال الجدولة (مع التحقق من القائمة البيضاء)
    # =====================================================================

    async def get_schedule(self, channel_id: int) -> Dict:
        try:
            row = await self.fetchone("SELECT * FROM schedule WHERE channel_db_id=?", (channel_id,))
            if row:
                return dict(row)
            min_interval = await self.get_min_publish_interval_setting()
            next_date = (TimeUtils.utc_now() + timedelta(minutes=min_interval)).strftime('%Y-%m-%d %H:%M:%S')
            await self.execute(
                "INSERT OR IGNORE INTO schedule (channel_db_id, schedule_type, interval_minutes, next_publish_date) VALUES (?, 'interval_minutes', ?, ?)",
                (channel_id, min_interval, next_date)
            )
            row = await self.fetchone("SELECT * FROM schedule WHERE channel_db_id=?", (channel_id,))
            return dict(row) if row else {}
        except Exception as e:
            logger.error(f"❌ Error in get_schedule: {e}", exc_info=True)
            return {}

    async def update_schedule(self, channel_id: int, **kwargs) -> bool:
        try:
            if not kwargs:
                return True
            for key in kwargs:
                if key not in ALLOWED_SCHEDULE_COLUMNS:
                    raise ValueError(f"عمود غير صالح: {key}")
            updates = [f"{k}=?" for k in kwargs]
            vals = list(kwargs.values()) + [channel_id]
            await self.execute(f"UPDATE schedule SET {', '.join(updates)} WHERE channel_db_id=?", vals)
            return True
        except Exception as e:
            logger.error(f"❌ Error in update_schedule: {e}", exc_info=True)
            return False

    async def get_min_publish_interval_setting(self, conn=None) -> int:
        try:
            if conn:
                cur = await conn.execute("SELECT value FROM settings WHERE key='min_publish_interval'")
                row = await cur.fetchone()
                if row and row[0]:
                    int_val = int(row[0])
                    if int_val > 0:
                        return int_val
            else:
                val = await self.get_setting('min_publish_interval')
                if val is not None:
                    int_val = int(val)
                    if int_val > 0:
                        return int_val
        except (ValueError, TypeError):
            pass
        return 12

    async def update_next_publish(self, channel_id: int) -> bool:
        try:
            async with self._get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                cur = await conn.execute("SELECT * FROM schedule WHERE channel_db_id=?", (channel_id,))
                sched_row = await cur.fetchone()
                if not sched_row:
                    min_interval = await self.get_min_publish_interval_setting(conn)
                    next_date = (TimeUtils.utc_now() + timedelta(minutes=min_interval)).strftime('%Y-%m-%d %H:%M:%S')
                    await conn.execute(
                        "INSERT OR IGNORE INTO schedule (channel_db_id, schedule_type, interval_minutes, next_publish_date) VALUES (?, 'interval_minutes', ?, ?)",
                        (channel_id, min_interval, next_date)
                    )
                    await conn.commit()
                    return True
                sched = dict(sched_row)
                cur = await conn.execute("SELECT last_publish_time FROM last_publish WHERE channel_db_id=?", (channel_id,))
                last_pub_row = await cur.fetchone()
                last_time = TimeUtils.safe_parse_iso(last_pub_row[0]) if last_pub_row and last_pub_row[0] else TimeUtils.utc_now()
                
                min_interval_minutes = await self.get_min_publish_interval_setting(conn)
                st = sched.get('schedule_type', 'interval_minutes')
                
                interval_minutes = min_interval_minutes
                interval_hours = 1.0
                interval_days = 1.0
                
                if st == 'interval_minutes':
                    interval_minutes = max(min_interval_minutes, sched.get('interval_minutes', min_interval_minutes))
                    next_date = last_time + timedelta(minutes=interval_minutes)
                elif st == 'interval_hours':
                    min_interval_hours = min_interval_minutes / 60.0
                    interval_hours = max(min_interval_hours, sched.get('interval_hours', 1))
                    next_date = last_time + timedelta(hours=interval_hours)
                elif st == 'interval_days':
                    min_interval_days = min_interval_minutes / (60 * 24)
                    interval_days = max(min_interval_days, sched.get('interval_days', 1))
                    next_date = last_time + timedelta(days=interval_days)
                else:
                    logger.warning(f"⚠️ نوع جدولة غير مدعوم: {st}، سيتم استخدام interval_minutes")
                    interval_minutes = min_interval_minutes
                    next_date = last_time + timedelta(minutes=interval_minutes)

                counter = 0
                while next_date <= TimeUtils.utc_now() and counter < 100:
                    if st == 'interval_minutes':
                        next_date += timedelta(minutes=interval_minutes)
                    elif st == 'interval_hours':
                        next_date += timedelta(hours=interval_hours)
                    elif st == 'interval_days':
                        next_date += timedelta(days=interval_days)
                    else:
                        next_date += timedelta(minutes=min_interval_minutes)
                    counter += 1
                await conn.execute(
                    "UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?",
                    (next_date.strftime('%Y-%m-%d %H:%M:%S'), channel_id)
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ Error in update_next_publish: {e}", exc_info=True)
            return False

    async def update_last_publish(self, channel_id: int) -> bool:
        try:
            await self.execute(
                "INSERT OR REPLACE INTO last_publish (channel_db_id, last_publish_time) VALUES (?,?)",
                (channel_id, TimeUtils.sql_iso())
            )
            return True
        except Exception as e:
            logger.error(f"❌ Error in update_last_publish: {e}", exc_info=True)
            return False

    async def get_channels_to_publish(self, limit: int = 20) -> List[Dict]:
        try:
            owner_id = CONFIG.PRIMARY_OWNER_ID
            rows = await self.fetchall("""
                SELECT uc.id, uc.channel_id, uc.user_id, u.auto_publish
                FROM user_channels uc
                JOIN users u ON uc.user_id = u.user_id
                LEFT JOIN schedule s ON uc.id = s.channel_db_id
                WHERE uc.banned = 0
                  AND u.banned = 0
                  AND u.auto_publish = 1
                  AND (
                      u.user_id = ?
                      OR EXISTS (
                          SELECT 1 FROM subscriptions sub
                          WHERE sub.user_id = u.user_id
                            AND sub.status = 'active'
                            AND sub.end_date > datetime('now')
                      )
                  )
                  AND (s.next_publish_date IS NULL OR s.next_publish_date <= ?)
                  AND EXISTS (
                      SELECT 1 FROM posts p
                      WHERE p.channel_db_id = uc.id
                        AND p.published = 0
                        AND (p.fail_count IS NULL OR p.fail_count < 3)
                  )
                ORDER BY COALESCE(s.next_publish_date, '1970-01-01 00:00:00') ASC
                LIMIT ?
            """, (owner_id, TimeUtils.sql_iso(), limit))
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_channels_to_publish: {e}", exc_info=True)
            return []

    # =====================================================================
    # دوال التذاكر
    # =====================================================================

    async def create_ticket(self, user_id: int, username: str, content: str,
                            media_type: str = None, media_file_id: str = None) -> int:
        try:
            async with self._get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                cur = await conn.execute("SELECT value FROM settings WHERE key='last_ticket_number'")
                row = await cur.fetchone()
                last_num = int(row[0]) if row and row[0] else 0
                next_num = last_num + 1
                await conn.execute(
                    "UPDATE settings SET value=? WHERE key='last_ticket_number'",
                    (str(next_num),)
                )
                await conn.execute(
                    "INSERT INTO support_tickets (user_id, username, message, media_type, media_file_id, ticket_number, created_at) VALUES (?,?,?,?,?,?,?)",
                    (user_id, username, content, media_type, media_file_id, next_num, TimeUtils.sql_iso())
                )
                await conn.commit()
                return next_num
        except Exception as e:
            logger.error(f"❌ Error in create_ticket: {e}", exc_info=True)
            return 0

    async def get_tickets(self) -> List[Dict]:
        try:
            rows = await self.fetchall(
                "SELECT id, user_id, username, ticket_number, message, status, created_at FROM support_tickets WHERE status='pending' ORDER BY created_at DESC"
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_tickets: {e}", exc_info=True)
            return []

    async def close_ticket(self, ticket_id: int) -> bool:
        try:
            await self.execute("UPDATE support_tickets SET status='closed' WHERE id=?", (ticket_id,))
            return True
        except Exception as e:
            logger.error(f"❌ Error in close_ticket: {e}", exc_info=True)
            return False

    async def delete_all_tickets(self) -> bool:
        try:
            await self.execute("DELETE FROM support_tickets")
            return True
        except Exception as e:
            logger.error(f"❌ Error in delete_all_tickets: {e}", exc_info=True)
            return False

    # =====================================================================
    # دوال الإحالات
    # =====================================================================

    async def add_referral(self, referrer_id: int, referred_id: int) -> bool:
        if referrer_id == referred_id:
            return False
        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?,?,?)",
                    (referrer_id, referred_id, TimeUtils.sql_iso())
                )
                await conn.execute(
                    "INSERT INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days, last_referral_date) "
                    "VALUES (?,1,3,0,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET referral_count=referral_count+1, "
                    "total_reward_days=total_reward_days+3, last_referral_date=?",
                    (referrer_id, TimeUtils.sql_iso(), TimeUtils.sql_iso())
                )
                await conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"❌ Error in add_referral: {e}", exc_info=True)
            return False

    async def get_referral_stats(self, user_id: int) -> Dict:
        try:
            total = (await self.fetchone("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,)))[0]
            row = await self.fetchone("SELECT claimed_reward_days, total_reward_days FROM referral_rewards WHERE user_id=?", (user_id,))
            if row:
                claimed = row[0] or 0
                total_reward = row[1] or 0
            else:
                claimed = 0
                total_reward = 0
            available = total_reward - claimed
            return {'total': total, 'claimed': claimed, 'available': available}
        except Exception as e:
            logger.error(f"❌ Error in get_referral_stats: {e}", exc_info=True)
            return {'total': 0, 'claimed': 0, 'available': 0}

    async def claim_referral_reward(self, user_id: int) -> int:
        try:
            async with self._get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                row = await (await conn.execute(
                    "SELECT total_reward_days, claimed_reward_days FROM referral_rewards WHERE user_id=?",
                    (user_id,)
                )).fetchone()
                if not row:
                    await conn.rollback()
                    return 0
                total_reward, claimed = row[0], row[1]
                available = total_reward - claimed
                if available <= 0:
                    await conn.rollback()
                    return 0

                await conn.execute(
                    "UPDATE referral_rewards SET claimed_reward_days = claimed_reward_days + ? WHERE user_id=?",
                    (available, user_id)
                )

                referral_plan_id = await self._get_or_create_referral_plan_id(conn)
                await self._grant_subscription_days_conn(conn, user_id, days=available, plan_id=referral_plan_id, provider='referral')

                await conn.commit()
                return available
        except Exception as e:
            logger.error(f"❌ Error in claim_referral_reward: {e}", exc_info=True)
            return 0

    async def get_referrals_list(self, user_id: int) -> List[int]:
        try:
            rows = await self.fetchall("SELECT referred_id FROM referrals WHERE referrer_id=? ORDER BY created_at DESC", (user_id,))
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_referrals_list: {e}", exc_info=True)
            return []

    # =====================================================================
    # دوال التذكيرات
    # =====================================================================

    async def get_reminder_settings(self, user_id: int) -> Dict:
        try:
            row = await self.fetchone("SELECT * FROM user_reminder_settings WHERE user_id=?", (user_id,))
            if row:
                return dict(row)
            await self.execute("INSERT OR IGNORE INTO user_reminder_settings (user_id) VALUES (?)", (user_id,))
            row = await self.fetchone("SELECT * FROM user_reminder_settings WHERE user_id=?", (user_id,))
            return dict(row) if row else {}
        except Exception as e:
            logger.error(f"❌ Error in get_reminder_settings: {e}", exc_info=True)
            return {}

    async def update_reminder_settings(self, user_id: int, **kwargs) -> bool:
        try:
            if not kwargs:
                return True
            for key in kwargs:
                if key not in ALLOWED_REMINDER_SETTINGS_COLUMNS:
                    raise ValueError(f"عمود غير صالح: {key}")
            updates = [f"{k}=?" for k in kwargs]
            vals = list(kwargs.values()) + [user_id]
            await self.execute(f"UPDATE user_reminder_settings SET {', '.join(updates)} WHERE user_id=?", vals)
            return True
        except Exception as e:
            logger.error(f"❌ Error in update_reminder_settings: {e}", exc_info=True)
            return False

    async def get_users_for_reminder(self) -> List[Dict]:
        try:
            now_sql = TimeUtils.sql_iso()
            rows = await self.fetchall("""
                SELECT u.user_id, u.language, r.reminder_days_before,
                       julianday(subscription_end) - julianday(?) as days_left,
                       r.last_reminder_sent
                FROM users u
                JOIN user_reminder_settings r ON u.user_id = r.user_id
                WHERE r.subscription_reminder = 1
                AND u.subscription_end IS NOT NULL
                AND julianday(subscription_end) - julianday(?) <= r.reminder_days_before
                AND julianday(subscription_end) - julianday(?) > 0
                AND (r.last_reminder_sent IS NULL OR
                     julianday(?) - julianday(r.last_reminder_sent) >= 1)
            """, (now_sql, now_sql, now_sql, now_sql))
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_users_for_reminder: {e}", exc_info=True)
            return []

    # =====================================================================
    # دوال المسابقات
    # =====================================================================

    async def create_contest(self, creator_id: int, title: str, description: str,
                             prize: str, end_date: str) -> int:
        try:
            async with self._get_connection() as conn:
                await conn.execute(
                    "INSERT INTO contests (creator_id, title, description, prize, end_date, created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (creator_id, title, description, prize, end_date, TimeUtils.sql_iso())
                )
                cur = await conn.execute("SELECT last_insert_rowid()")
                row = await cur.fetchone()
                await conn.commit()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"❌ Error in create_contest: {e}", exc_info=True)
            return 0

    async def get_active_contests(self, limit: int = 10) -> List[Dict]:
        try:
            now_sql = TimeUtils.sql_iso()
            rows = await self.fetchall("""
                SELECT c.*,
                       (SELECT COUNT(*) FROM contest_participants WHERE contest_id = c.id) as participants
                FROM contests c
                WHERE c.status = 'active' AND datetime(c.end_date) > datetime(?)
                ORDER BY c.end_date ASC LIMIT ?
            """, (now_sql, limit))
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_active_contests: {e}", exc_info=True)
            return []

    async def join_contest(self, contest_id: int, user_id: int, answer: str = "") -> bool:
        try:
            await self.execute(
                "INSERT INTO contest_participants (contest_id, user_id, answer, joined_at) VALUES (?,?,?,?)",
                (contest_id, user_id, answer, TimeUtils.sql_iso())
            )
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"❌ Error in join_contest: {e}", exc_info=True)
            return False

    async def declare_winner(self, contest_id: int, winner_id: int) -> bool:
        try:
            async with self._get_connection() as conn:
                await conn.execute("UPDATE contests SET status='closed', winner_id=? WHERE id=?", (winner_id, contest_id))
                await conn.execute(
                    "INSERT INTO contest_winners (contest_id, winner_id, announced_at) VALUES (?,?,?)",
                    (contest_id, winner_id, TimeUtils.sql_iso())
                )
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ Error in declare_winner: {e}", exc_info=True)
            return False

    async def get_contest_winners(self, limit: int = 10) -> List[Dict]:
        try:
            rows = await self.fetchall("""
                SELECT c.title, c.winner_id, u.username, cw.announced_at
                FROM contest_winners cw
                JOIN contests c ON cw.contest_id = c.id
                JOIN users u ON cw.winner_id = u.user_id
                ORDER BY cw.announced_at DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_contest_winners: {e}", exc_info=True)
            return []

    async def delete_contest(self, contest_id: int, user_id: int) -> bool:
        try:
            async with self._get_connection() as conn:
                cur = await conn.execute("SELECT creator_id FROM contests WHERE id=?", (contest_id,))
                row = await cur.fetchone()
                if row and (row[0] == user_id):
                    await conn.execute("DELETE FROM contest_participants WHERE contest_id=?", (contest_id,))
                    await conn.execute("DELETE FROM contests WHERE id=?", (contest_id,))
                    await conn.commit()
                    return True
                return False
        except Exception as e:
            logger.error(f"❌ Error in delete_contest: {e}", exc_info=True)
            return False

    # =====================================================================
    # دوال الإعدادات العامة
    # =====================================================================

    async def get_setting(self, key: str, default: str = None) -> Optional[str]:
        try:
            row = await self.fetchone("SELECT value FROM settings WHERE key=?", (key,))
            return row[0] if row else default
        except Exception as e:
            logger.error(f"❌ Error in get_setting: {e}", exc_info=True)
            return default

    async def set_setting(self, key: str, value: str) -> bool:
        try:
            await self.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
            return True
        except Exception as e:
            logger.error(f"❌ Error in set_setting: {e}", exc_info=True)
            return False

    async def get_force_subscribe_channel(self) -> Optional[str]:
        return await self.get_setting('force_subscribe_channel')

    async def get_updates_channel(self) -> Optional[str]:
        return await self.get_setting('updates_channel')

    async def get_log_channel(self) -> Optional[str]:
        return await self.get_setting('log_channel_id')

    async def get_publish_interval(self) -> int:
        try:
            v = await self.get_setting('publish_interval', '60')
            return int(v) if v else 60
        except:
            return 60

    async def get_auto_backup(self) -> bool:
        try:
            v = await self.get_setting('auto_backup', 'true')
            if v is None:
                return True
            return v.lower() in ('1', 'true', 'yes', 'on')
        except:
            return True

    # =====================================================================
    # دوال الباقات والاشتراكات
    # =====================================================================

    async def get_plan(self, plan_id: int) -> Optional[Dict]:
        try:
            row = await self.fetchone("SELECT * FROM plans WHERE id=?", (plan_id,))
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Error in get_plan: {e}", exc_info=True)
            return None

    async def get_plan_by_name(self, name: str) -> Optional[Dict]:
        try:
            row = await self.fetchone("SELECT * FROM plans WHERE name=?", (name,))
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Error in get_plan_by_name: {e}", exc_info=True)
            return None

    async def get_all_plans(self) -> List[Dict]:
        try:
            rows = await self.fetchall(
                "SELECT * FROM plans WHERE is_active=1 AND is_gift=0 ORDER BY price"
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_all_plans: {e}", exc_info=True)
            return []

    async def create_subscription(self, user_id: int, plan_id: int, provider: str = 'xtr',
                                   provider_sub_id: str = None) -> int:
        try:
            plan = await self.get_plan(plan_id)
            if not plan or not plan.get('is_active') or plan.get('is_gift'):
                logger.warning(f"❌ محاولة اشتراك بخطة غير موجودة أو غير نشطة أو خطة هدية: {plan_id}")
                return 0

            async with self._get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                cur = await conn.execute("""
                    SELECT MAX(end_date) FROM subscriptions
                    WHERE user_id=? AND status='active' AND end_date > datetime('now')
                """, (user_id,))
                row = await cur.fetchone()
                base = row[0] if row and row[0] else None
                if not base:
                    cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
                    user_row = await cur.fetchone()
                    base = user_row[0] if user_row else None
                base_dt = TimeUtils.safe_parse_iso(base) if base else TimeUtils.utc_now()
                if base_dt < TimeUtils.utc_now():
                    base_dt = TimeUtils.utc_now()
                new_end = base_dt + timedelta(days=plan['duration_days'])
                end_date = new_end.strftime('%Y-%m-%d %H:%M:%S')
                start_date = TimeUtils.sql_iso()

                await conn.execute(
                    "INSERT INTO subscriptions (user_id, plan_id, status, start_date, end_date, auto_renew, provider, provider_subscription_id, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (user_id, plan_id, 'active', start_date, end_date, 0, provider, provider_sub_id, start_date, start_date)
                )
                cur = await conn.execute("SELECT last_insert_rowid()")
                sub_row = await cur.fetchone()
                await conn.execute(
                    "UPDATE users SET subscription_end=? WHERE user_id=?",
                    (end_date, user_id)
                )
                await conn.commit()
                return sub_row[0] if sub_row else 0
        except Exception as e:
            logger.error(f"❌ Error in create_subscription: {e}", exc_info=True)
            return 0

    async def get_active_subscription(self, user_id: int) -> Optional[Dict]:
        try:
            row = await self.fetchone("""
                SELECT s.*, p.name, p.duration_days, p.max_channels, p.max_posts, p.features
                FROM subscriptions s
                LEFT JOIN plans p ON s.plan_id = p.id
                WHERE s.user_id=? AND s.status='active' AND s.end_date > datetime('now')
                ORDER BY s.end_date DESC LIMIT 1
            """, (user_id,))
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Error in get_active_subscription: {e}", exc_info=True)
            return None

    async def expire_expired_subscriptions(self) -> None:
        try:
            async with self._get_connection() as conn:
                await conn.execute("""
                    UPDATE subscriptions SET status='expired'
                    WHERE status='active' AND end_date < datetime('now')
                """)
                await conn.execute("""
                    UPDATE users
                    SET subscription_end = (
                        SELECT MAX(s.end_date)
                        FROM subscriptions s
                        WHERE s.user_id = users.user_id
                          AND s.status = 'active'
                          AND s.end_date > datetime('now')
                    )
                    WHERE EXISTS (
                        SELECT 1 FROM subscriptions s2
                        WHERE s2.user_id = users.user_id
                          AND s2.status = 'active'
                          AND s2.end_date > datetime('now')
                    )
                """)
                # تنظيف المستخدمين الذين لا يملكون أي اشتراك نشط
                await conn.execute("""
                    UPDATE users SET subscription_end = NULL
                    WHERE user_id NOT IN (
                        SELECT DISTINCT user_id FROM subscriptions
                        WHERE status='active' AND end_date > datetime('now')
                    )
                    AND subscription_end IS NOT NULL
                """)
                await conn.commit()
        except Exception as e:
            logger.error(f"❌ Error in expire_expired_subscriptions: {e}", exc_info=True)

    # =====================================================================
    # دالة موحدة لمنح أيام اشتراك
    # =====================================================================

    async def grant_subscription_days(self, user_id: int, days: int, plan_id: Optional[int] = None, provider: str = 'manual') -> bool:
        try:
            async with self._get_connection() as conn:
                await self._grant_subscription_days_conn(conn, user_id, days, plan_id, provider)
                await conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ Error in grant_subscription_days: {e}", exc_info=True)
            return False

    async def _grant_subscription_days_conn(self, conn, user_id: int, days: int, plan_id: Optional[int], provider: str) -> None:
        """تنفيذ منح الأيام داخل اتصال مفتوح (يجب أن يكون داخل معاملة)."""
        if days <= 0:
            return
        cur = await conn.execute("""
            SELECT MAX(end_date) FROM subscriptions
            WHERE user_id=? AND status='active' AND end_date > datetime('now')
        """, (user_id,))
        row = await cur.fetchone()
        base = row[0] if row and row[0] else None
        if not base:
            cur = await conn.execute("SELECT subscription_end FROM users WHERE user_id=?", (user_id,))
            user_row = await cur.fetchone()
            base = user_row[0] if user_row else None
        base_dt = TimeUtils.safe_parse_iso(base) if base else TimeUtils.utc_now()
        if base_dt < TimeUtils.utc_now():
            base_dt = TimeUtils.utc_now()
        new_end = base_dt + timedelta(days=days)
        end_date = new_end.strftime('%Y-%m-%d %H:%M:%S')
        start_date = TimeUtils.sql_iso()

        await conn.execute(
            "INSERT INTO subscriptions (user_id, plan_id, status, start_date, end_date, auto_renew, provider, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, plan_id, 'active', start_date, end_date, 0, provider, start_date, start_date)
        )
        await conn.execute(
            "UPDATE users SET subscription_end=? WHERE user_id=?",
            (end_date, user_id)
        )

    # =====================================================================
    # دوال الفواتير والدفع
    # =====================================================================

    async def create_invoice(self, user_id: int, plan_id: int, amount: int,
                              currency: str = 'XTR', provider: str = 'xtr') -> str:
        try:
            number = f"INV-{TimeUtils.utc_now().strftime('%Y%m')}-{secrets.token_hex(4).upper()}"
            await self.execute(
                "INSERT INTO invoices (number, user_id, plan_id, amount, currency, status, provider, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (number, user_id, plan_id, amount, currency, 'pending', provider, TimeUtils.sql_iso())
            )
            return number
        except Exception as e:
            logger.error(f"❌ Error in create_invoice: {e}", exc_info=True)
            return ""

    async def mark_invoice_paid(self, invoice_number: str, payment_id: str) -> None:
        try:
            await self.execute(
                "UPDATE invoices SET status='paid', provider_payment_id=?, paid_at=? WHERE number=?",
                (payment_id, TimeUtils.sql_iso(), invoice_number)
            )
        except Exception as e:
            logger.error(f"❌ Error in mark_invoice_paid: {e}", exc_info=True)

    async def get_invoice(self, number: str) -> Optional[Dict]:
        try:
            row = await self.fetchone("SELECT * FROM invoices WHERE number=?", (number,))
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Error in get_invoice: {e}", exc_info=True)
            return None

    async def get_user_invoices(self, user_id: int, limit: int = 20) -> List[Dict]:
        try:
            rows = await self.fetchall(
                "SELECT * FROM invoices WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_user_invoices: {e}", exc_info=True)
            return []

    async def add_payment_log(self, user_id: int, provider: str, event_type: str, data: dict) -> None:
        try:
            await self.execute(
                "INSERT INTO payment_logs (user_id, provider, event_type, data, created_at) VALUES (?,?,?,?,?)",
                (user_id, provider, event_type, json.dumps(data), TimeUtils.sql_iso())
            )
        except Exception as e:
            logger.error(f"❌ Error in add_payment_log: {e}", exc_info=True)

    # =====================================================================
    # دوال الهدايا (Gift Codes)
    # =====================================================================

    async def get_gift_plans(self) -> List[Dict]:
        try:
            rows = await self.fetchall("SELECT * FROM gift_plans WHERE is_active=1 ORDER BY price")
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_gift_plans: {e}", exc_info=True)
            return []

    async def get_gift_plan(self, plan_id: int) -> Optional[Dict]:
        try:
            row = await self.fetchone("SELECT * FROM gift_plans WHERE id=?", (plan_id,))
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Error in get_gift_plan: {e}", exc_info=True)
            return None

    async def generate_gift_code(self, user_id: int, days: int, plan_id: int) -> str:
        try:
            if days <= 0:
                logger.warning("❌ عدد أيام غير صالح لتوليد كود هدية")
                return ""
            plan = await self.get_gift_plan(plan_id)
            if not plan:
                logger.warning(f"❌ خطة هدية غير موجودة: {plan_id}")
                return ""

            max_attempts = 100
            for _ in range(max_attempts):
                code = secrets.token_urlsafe(8).upper()
                try:
                    await self.execute(
                        "INSERT INTO gift_codes (code, days, plan_id, created_by, created_at) VALUES (?,?,?,?,?)",
                        (code, days, plan_id, user_id, TimeUtils.sql_iso())
                    )
                    logger.info(f"✅ تم إنشاء كود هدية: {code} لمستخدم {user_id}")
                    return code
                except sqlite3.IntegrityError:
                    continue
            logger.error("❌ فشل توليد كود هدية فريد بعد محاولات عديدة")
            return ""
        except Exception as e:
            logger.error(f"❌ Error in generate_gift_code: {e}", exc_info=True)
            return ""

    async def redeem_gift_code(self, user_id: int, code: str) -> Tuple[bool, int]:
        try:
            code = code.strip().upper()
            async with self._get_connection() as conn:
                await conn.execute("BEGIN IMMEDIATE")
                cur = await conn.execute(
                    "SELECT id, days, plan_id FROM gift_codes WHERE code=? AND is_used=0",
                    (code,)
                )
                row = await cur.fetchone()
                if not row:
                    await conn.rollback()
                    return False, 0
                gift_id, days, gift_plan_id = row
                if days <= 0:
                    await conn.rollback()
                    return False, 0

                cur = await conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
                if not await cur.fetchone():
                    await conn.rollback()
                    return False, -2

                cur = await conn.execute("SELECT created_by FROM gift_codes WHERE id=?", (gift_id,))
                creator_row = await cur.fetchone()
                if creator_row and creator_row[0] == user_id:
                    await conn.rollback()
                    return False, -1

                # الحصول على معرّف خطة الهدية من plans (is_gift=1)
                cur = await conn.execute("SELECT id FROM plans WHERE is_gift=1 LIMIT 1")
                plan_row = await cur.fetchone()
                if not plan_row:
                    await conn.rollback()
                    logger.error("❌ لا توجد خطة هدية معرفة في جدول plans")
                    return False, 0
                gift_plan_id = plan_row[0]

                await self._grant_subscription_days_conn(conn, user_id, days, gift_plan_id, provider='gift')

                await conn.execute(
                    "UPDATE gift_codes SET used_by=?, used_at=?, is_used=1 WHERE id=? AND is_used=0",
                    (user_id, TimeUtils.sql_iso(), gift_id)
                )
                await conn.commit()
                logger.info(f"✅ تم استرداد كود هدية {code} بواسطة {user_id} (+{days} يوم)")
                return True, days
        except Exception as e:
            logger.error(f"❌ Error in redeem_gift_code: {e}", exc_info=True)
            return False, 0

    async def get_gift_code_info(self, code: str) -> Optional[Dict]:
        try:
            row = await self.fetchone(
                """SELECT gc.*, u.username as creator_name 
                   FROM gift_codes gc 
                   LEFT JOIN users u ON gc.created_by = u.user_id 
                   WHERE gc.code=?""",
                (code.upper(),)
            )
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Error in get_gift_code_info: {e}", exc_info=True)
            return None

    async def get_user_gift_codes(self, user_id: int) -> List[Dict]:
        try:
            rows = await self.fetchall(
                "SELECT * FROM gift_codes WHERE created_by=? ORDER BY created_at DESC",
                (user_id,)
            )
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"❌ Error in get_user_gift_codes: {e}", exc_info=True)
            return []


# =====================================================================
# إنشاء كائن قاعدة البيانات
# =====================================================================

DB = Database()

async def get_db() -> Database:
    return DB

async def initialize_db() -> None:
    await DB.initialize()
