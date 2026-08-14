#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
database.py - قاعدة البيانات المتكاملة للبوت
=============================================
تستخدم SQLite مع aiosqlite للتعامل غير المتزامن
تحتوي على جميع الجداول والفهارس والدوال اللازمة للبوت
مع تفعيل النسخة التجريبية التلقائية للمستخدمين الجدد
"""

import sqlite3
import json
import logging
import secrets
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from contextlib import asynccontextmanager

import aiosqlite

from config import PATHS

logger = logging.getLogger(__name__)

# =====================================================================
# 1. أدوات الوقت
# =====================================================================

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
            return None

# =====================================================================
# 2. كلاس قاعدة البيانات الرئيسي
# =====================================================================

class Database:
    """إدارة قاعدة البيانات SQLite مع دعم غير متزامن"""
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls) -> 'Database':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @asynccontextmanager
    async def _get_connection(self):
        """الحصول على اتصال بقاعدة البيانات"""
        async with aiosqlite.connect(
            str(PATHS.DB),
            timeout=30,
            check_same_thread=False
        ) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            yield conn

    async def execute(self, query: str, params: tuple = ()) -> None:
        """تنفيذ استعلام دون إرجاع نتائج"""
        async with self._get_connection() as conn:
            await conn.execute(query, params)
            await conn.commit()

    async def fetchone(self, query: str, params: tuple = ()):
        """تنفيذ استعلام وإرجاع صف واحد"""
        async with self._get_connection() as conn:
            async with conn.execute(query, params) as cur:
                return await cur.fetchone()

    async def fetchall(self, query: str, params: tuple = ()):
        """تنفيذ استعلام وإرجاع جميع الصفوف"""
        async with self._get_connection() as conn:
            async with conn.execute(query, params) as cur:
                return await cur.fetchall()

    async def fetchval(self, query: str, params: tuple = ()):
        """تنفيذ استعلام وإرجاع قيمة واحدة"""
        row = await self.fetchone(query, params)
        return row[0] if row else None

    async def executemany(self, query: str, params: list) -> None:
        """تنفيذ استعلام متعدد مع بارامترات"""
        if not params:
            return
        async with self._get_connection() as conn:
            await conn.executemany(query, params)
            await conn.commit()

    # ================================================================
    # 3. تهيئة قاعدة البيانات
    # ================================================================

    async def initialize(self) -> None:
        """تهيئة قاعدة البيانات: إنشاء الجداول والفهارس والبيانات الافتراضية"""
        async with self._get_connection() as conn:
            await self._create_tables(conn)
            await self._create_indexes(conn)
            await self._init_default_data(conn)
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")

    async def _create_tables(self, conn) -> None:
        """إنشاء جميع الجداول"""
        
        # === جداول المستخدمين والقنوات والمنشورات ===
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
                created_at TEXT
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
        
        # === جداول المجموعات والإدارة ===
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
        
        # === جداول الأمان والقفل ===
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
                nsfw_threshold REAL DEFAULT 0.7
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
        
        # === جداول الردود التلقائية ===
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
        
        # === جداول الدعم والاشتراكات ===
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
        
        # الإعدادات الافتراضية
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('publish_interval', '720')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_backup', '1')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_ticket_number', '0')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_backup', '')")
        
        # === جداول الإحالات والتذكيرات ===
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
        
        # === جداول المسابقات ===
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
        
        # === جداول السجلات والتحذيرات ===
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
        
        # === جداول الباقات والاشتراكات والدفع ===
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
        
        await conn.commit()

    async def _create_indexes(self, conn) -> None:
        """إنشاء الفهارس لتحسين الأداء"""
        
        # فهارس المستخدمين
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_banned ON users(banned)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_language ON users(language)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_subscription ON users(subscription_end)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_updated ON users(updated_at)")
        
        # فهارس القنوات والمنشورات
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_uc_user ON user_channels(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_uc_active ON user_channels(banned)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_fail ON posts(fail_count)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sched_next ON schedule(next_publish_date)")
        
        # فهارس المجموعات
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_banned ON bot_groups(banned)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_group_admins_user ON group_admins(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_group_admins_chat ON group_admins(chat_id)")
        
        # فهارس الأمان
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_chat ON group_security(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_banned_words_chat ON banned_words(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_banned_words_word ON banned_words(word)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_warnings_user ON user_warnings(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_warnings_chat ON user_warnings(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_chat ON admin_logs(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_admin ON admin_logs(admin_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_logs_created ON admin_logs(created_at)")
        
        # فهارس الردود التلقائية
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ar_chat ON auto_replies(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ar_keyword ON auto_replies(keyword)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_auto_replies_lookup ON auto_replies(chat_id, keyword, is_active)")
        
        # فهارس التذاكر
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_user ON support_tickets(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status)")
        
        # فهارس الاشتراكات
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_status ON subscriptions(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_end ON subscriptions(end_date)")
        
        # فهارس الفواتير
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_user ON invoices(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_status ON invoices(status)")
        
        # فهارس الإحالات
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id)")
        
        # فهارس المسابقات
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contests_end ON contests(end_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contest_participants_contest ON contest_participants(contest_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contest_participants_user ON contest_participants(user_id)")
        
        # فهارس التذكيرات
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_user ON user_reminder_settings(user_id)")
        
        await conn.commit()

    async def _init_default_data(self, conn) -> None:
        """إدراج البيانات الافتراضية (الباقات)"""
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
                    INSERT INTO plans (name, description, price, currency, duration_days, max_channels, max_posts, features, is_active, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    plan["name"], plan["description"], plan["price"], "XTR",
                    plan["duration_days"], plan["max_channels"], plan["max_posts"],
                    plan["features"], 1, TimeUtils.utc_iso()
                ))
        
        await conn.commit()

    # ================================================================
    # 4. دوال المستخدمين (مع تفعيل تجربة تلقائية)
    # ================================================================

    async def register_user(self, user_id: int, username: str = "", first_name: str = "") -> bool:
        """
        تسجيل مستخدم جديد أو تحديثه
        مع تفعيل نسخة تجريبية تلقائية للمستخدمين الجدد (30 يوم)
        """
        try:
            row = await self.fetchone("SELECT user_id FROM users WHERE user_id=?", (user_id,))
            if row:
                await self.execute(
                    "UPDATE users SET username=?, first_name=?, updated_at=? WHERE user_id=?",
                    (username, first_name, TimeUtils.utc_iso(), user_id)
                )
                return True
            code = secrets.token_urlsafe(6)
            # تفعيل تجربة 30 يوم تلقائياً للمستخدمين الجدد
            trial_end = (TimeUtils.utc_now() + timedelta(days=30)).isoformat()
            await self.execute(
                """INSERT INTO users 
                   (user_id, username, first_name, referral_code, subscription_end, trial_used, created_at, updated_at) 
                   VALUES (?,?,?,?,?,?,?,?)""",
                (user_id, username, first_name, code, trial_end, 1, TimeUtils.utc_iso(), TimeUtils.utc_iso())
            )
            logger.info(f"✅ تم تسجيل مستخدم جديد {user_id} مع تجربة 30 يوم")
            return True
        except Exception as e:
            logger.error(f"Error in register_user: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[Dict]:
        """الحصول على معلومات المستخدم"""
        row = await self.fetchone("SELECT * FROM users WHERE user_id=?", (user_id,))
        return dict(row) if row else None

    async def get_user_language(self, user_id: int) -> str:
        """الحصول على لغة المستخدم"""
        row = await self.fetchone("SELECT language FROM users WHERE user_id=?", (user_id,))
        return row[0] if row else 'ar'

    async def set_user_language(self, user_id: int, lang: str) -> bool:
        """تعيين لغة المستخدم"""
        await self.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))
        return True

    async def get_auto_publish_status(self, user_id: int) -> bool:
        """الحصول على حالة النشر التلقائي"""
        row = await self.fetchone("SELECT auto_publish FROM users WHERE user_id=?", (user_id,))
        return row and row[0] == 1

    async def set_auto_publish(self, user_id: int, status: bool) -> bool:
        """تعيين حالة النشر التلقائي"""
        await self.execute("UPDATE users SET auto_publish=? WHERE user_id=?", (1 if status else 0, user_id))
        return True

    async def is_user_banned(self, user_id: int) -> bool:
        """التحقق من حظر المستخدم"""
        row = await self.fetchone("SELECT banned FROM users WHERE user_id=?", (user_id,))
        return row and row[0] == 1

    async def ban_user(self, user_id: int) -> bool:
        """حظر مستخدم"""
        await self.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
        return True

    async def unban_user(self, user_id: int) -> bool:
        """إلغاء حظر مستخدم"""
        await self.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
        return True

    async def get_all_users(self) -> List[Tuple[int, int]]:
        """الحصول على جميع المستخدمين"""
        rows = await self.fetchall("SELECT user_id, banned FROM users")
        return [(row[0], row[1]) for row in rows]

    async def get_user_stats(self) -> Dict:
        """الحصول على إحصائيات المستخدمين"""
        total = (await self.fetchone("SELECT COUNT(*) FROM users"))[0]
        banned = (await self.fetchone("SELECT COUNT(*) FROM users WHERE banned=1"))[0]
        return {'users': total, 'banned': banned}

    async def has_active_subscription(self, user_id: int) -> bool:
        """التحقق من وجود اشتراك نشط"""
        row = await self.fetchone(
            "SELECT subscription_end FROM users WHERE user_id=? AND subscription_end > datetime('now')",
            (user_id,)
        )
        return row is not None

    async def has_used_trial(self, user_id: int) -> bool:
        """التحقق من استخدام النسخة التجريبية"""
        row = await self.fetchone("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        return row and row[0] == 1

    async def activate_trial(self, user_id: int) -> int:
        """تفعيل النسخة التجريبية (30 يوم)"""
        end_date = (TimeUtils.utc_now() + timedelta(days=30)).isoformat()
        await self.execute(
            "UPDATE users SET trial_used=1, subscription_end=? WHERE user_id=?",
            (end_date, user_id)
        )
        return 30

    async def get_referral_code(self, user_id: int) -> str:
        """الحصول على كود الإحالة"""
        row = await self.fetchone("SELECT referral_code FROM users WHERE user_id=?", (user_id,))
        return row[0] if row else f"ref_{user_id}"

    async def get_user_by_referral_code(self, code: str) -> Optional[int]:
        """الحصول على مستخدم عن طريق كود الإحالة"""
        row = await self.fetchone("SELECT user_id FROM users WHERE referral_code=?", (code,))
        return row[0] if row else None

    async def get_active_plan(self, user_id: int) -> Optional[Dict]:
        """الحصول على الباقة النشطة للمستخدم"""
        sub = await self.get_active_subscription(user_id)
        if sub:
            return await self.get_plan(sub['plan_id'])
        return None

    # ================================================================
    # 5. دوال القنوات
    # ================================================================

    async def add_channel(self, user_id: int, channel_id: int, channel_name: str) -> Optional[int]:
        """إضافة قناة جديدة"""
        try:
            row = await self.fetchone(
                "SELECT id FROM user_channels WHERE user_id=? AND channel_id=?",
                (user_id, channel_id)
            )
            if row:
                return row[0]
            result = await self.fetchone(
                "INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) VALUES (?,?,?,?) RETURNING id",
                (user_id, channel_id, channel_name, TimeUtils.utc_iso())
            )
            if not result:
                return None
            ch_db_id = result[0]
            interval = 720
            next_date = TimeUtils.utc_now() + timedelta(seconds=interval)
            await self.execute(
                "INSERT OR IGNORE INTO schedule (channel_db_id, next_publish_date) VALUES (?,?)",
                (ch_db_id, next_date.isoformat())
            )
            return ch_db_id
        except Exception as e:
            logger.error(f"Error in add_channel: {e}")
            return None

    async def get_user_channels(self, user_id: int) -> List[Dict]:
        """الحصول على قنوات المستخدم"""
        rows = await self.fetchall(
            "SELECT id, channel_id, channel_name, banned FROM user_channels WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)
        )
        return [dict(row) for row in rows]

    async def get_active_channel(self, user_id: int) -> Optional[int]:
        """الحصول على القناة النشطة"""
        row = await self.fetchone(
            "SELECT active_channel FROM users WHERE user_id=?",
            (user_id,)
        )
        if row and row[0]:
            banned = await self.fetchone("SELECT banned FROM user_channels WHERE id=?", (row[0],))
            if banned and banned[0] == 0:
                return row[0]
        row2 = await self.fetchone(
            "SELECT id FROM user_channels WHERE user_id=? AND banned=0 ORDER BY id LIMIT 1",
            (user_id,)
        )
        return row2[0] if row2 else None

    async def set_active_channel(self, user_id: int, channel_id: int) -> bool:
        """تعيين القناة النشطة"""
        await self.execute("UPDATE users SET active_channel=? WHERE user_id=?", (channel_id, user_id))
        return True

    async def delete_channel(self, user_id: int, channel_id: int) -> bool:
        """حذف قناة"""
        await self.execute("DELETE FROM user_channels WHERE id=? AND user_id=?", (channel_id, user_id))
        return True

    async def get_channel_info(self, channel_id: int) -> Optional[Dict]:
        """الحصول على معلومات القناة"""
        row = await self.fetchone("SELECT * FROM user_channels WHERE id=?", (channel_id,))
        return dict(row) if row else None

    async def get_channel_stats(self, channel_id: int) -> Dict:
        """الحصول على إحصائيات القناة"""
        total = (await self.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (channel_id,)))[0]
        published = (await self.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=1", (channel_id,)))[0]
        return {'total': total, 'published': published, 'unpublished': total - published}

    # ================================================================
    # 6. دوال المنشورات
    # ================================================================

    async def add_posts(self, channel_id: int, posts: List[Tuple[str, str, str]]) -> int:
        """إضافة منشورات متعددة"""
        try:
            from utils import TextUtils
            vals = [(channel_id, TextUtils.sanitize(t), m, f, TimeUtils.utc_iso()) for t, m, f in posts]
        except:
            vals = [(channel_id, t[:4096], m, f, TimeUtils.utc_iso()) for t, m, f in posts]
        await self.executemany(
            "INSERT INTO posts (channel_db_id, text, media_type, media_file_id, created_at) VALUES (?,?,?,?,?)",
            vals
        )
        return len(vals)

    async def get_unpublished_posts_count(self, channel_id: int) -> int:
        """عدد المنشورات غير المنشورة"""
        row = await self.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=0", (channel_id,))
        return row[0] if row else 0

    async def get_user_unpublished_count(self, user_id: int) -> int:
        """عدد المنشورات غير المنشورة للمستخدم"""
        row = await self.fetchone(
            "SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=? AND p.published=0",
            (user_id,)
        )
        return row[0] if row else 0

    async def get_user_total_posts(self, user_id: int) -> int:
        """إجمالي منشورات المستخدم"""
        row = await self.fetchone(
            "SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id=uc.id WHERE uc.user_id=?",
            (user_id,)
        )
        return row[0] if row else 0

    async def get_next_post(self, channel_id: int) -> Optional[Dict]:
        """الحصول على المنشور التالي للنشر"""
        row = await self.fetchone(
            "SELECT id, text, media_type, media_file_id FROM posts WHERE channel_db_id=? AND published=0 AND (fail_count IS NULL OR fail_count < 3) ORDER BY created_at ASC LIMIT 1",
            (channel_id,)
        )
        return dict(row) if row else None

    async def get_user_posts(self, channel_id: int, limit: int = 15) -> List[Dict]:
        """الحصول على منشورات المستخدم"""
        rows = await self.fetchall(
            "SELECT id, text, media_type, media_file_id FROM posts WHERE channel_db_id=? AND published=0 ORDER BY created_at ASC LIMIT ?",
            (channel_id, limit)
        )
        return [dict(row) for row in rows]

    async def mark_post_published(self, post_id: int) -> bool:
        """تحديد منشور كـ منشور"""
        await self.execute("UPDATE posts SET published=1, published_at=? WHERE id=?", (TimeUtils.utc_iso(), post_id))
        return True

    async def increment_post_fail(self, post_id: int) -> bool:
        """زيادة عدد محاولات الفشل"""
        await self.execute("UPDATE posts SET fail_count = fail_count + 1 WHERE id=?", (post_id,))
        return True

    async def delete_post(self, post_id: int, user_id: int, channel_id: int) -> bool:
        """حذف منشور"""
        row = await self.fetchone("SELECT 1 FROM user_channels WHERE id=? AND user_id=?", (channel_id, user_id))
        if not row:
            return False
        await self.execute("DELETE FROM posts WHERE id=? AND channel_db_id=?", (post_id, channel_id))
        return True

    async def reset_posts(self, channel_id: int) -> bool:
        """إعادة تعيين جميع المنشورات (جعلها غير منشورة)"""
        await self.execute("UPDATE posts SET published=0 WHERE channel_db_id=?", (channel_id,))
        return True

    # ================================================================
    # 7. دوال المجموعات
    # ================================================================

    async def register_group(self, chat_id: int, chat_name: str, user_id: int, username: str = None) -> bool:
        """تسجيل مجموعة جديدة"""
        try:
            row = await self.fetchone("SELECT chat_id FROM bot_groups WHERE chat_id=?", (chat_id,))
            if row:
                await self.execute(
                    "UPDATE bot_groups SET chat_name=?, username=?, updated_at=? WHERE chat_id=?",
                    (chat_name, username, TimeUtils.utc_iso(), chat_id)
                )
            else:
                await self.execute(
                    "INSERT INTO bot_groups (chat_id, chat_name, username, added_by, added_at) VALUES (?,?,?,?,?)",
                    (chat_id, chat_name, username, user_id, TimeUtils.utc_iso())
                )
            return True
        except Exception as e:
            logger.error(f"Error in register_group: {e}")
            return False

    async def get_user_groups(self, user_id: int) -> List[Tuple[int, str, str, int]]:
        """الحصول على مجموعات المستخدم"""
        try:
            rows = await self.fetchall("""
                SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned
                FROM bot_groups bg
                LEFT JOIN user_groups_link l ON bg.chat_id = l.chat_id AND l.user_id=?
                LEFT JOIN hidden_owner_groups h ON bg.chat_id = h.chat_id AND h.owner_id=?
                LEFT JOIN hidden_admins ha ON bg.chat_id = ha.chat_id AND ha.admin_id=?
                LEFT JOIN group_admins ga ON bg.chat_id = ga.chat_id AND ga.user_id=?
                WHERE l.user_id IS NOT NULL OR h.owner_id IS NOT NULL OR ha.admin_id IS NOT NULL OR ga.user_id IS NOT NULL
            """, (user_id, user_id, user_id, user_id))
            return [(row[0], row[1], row[2] or "", row[3]) for row in rows]
        except Exception as e:
            logger.error(f"Error in get_user_groups: {e}")
            return []

    async def sync_group_admins(self, chat_id: int, admin_ids: List[int]) -> int:
        """مزامنة مشرفي المجموعة"""
        await self.execute("DELETE FROM group_admins WHERE chat_id=?", (chat_id,))
        if admin_ids:
            await self.executemany(
                "INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?,?)",
                [(chat_id, uid) for uid in admin_ids]
            )
        return len(admin_ids)

    async def add_hidden_admin(self, chat_id: int, admin_id: int, added_by: int) -> bool:
        """إضافة مشرف مخفي"""
        await self.execute(
            "INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,1)",
            (chat_id, admin_id)
        )
        await self.execute(
            "INSERT OR IGNORE INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?,?,?,?)",
            (chat_id, admin_id, added_by, TimeUtils.utc_iso())
        )
        return True

    async def remove_hidden_admin(self, chat_id: int, admin_id: int) -> bool:
        """إزالة مشرف مخفي"""
        await self.execute("DELETE FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, admin_id))
        await self.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
        return True

    async def get_hidden_admins(self, chat_id: int) -> List[Dict]:
        """الحصول على المشرفين المخفيين"""
        rows = await self.fetchall(
            "SELECT admin_id, added_by, added_at FROM hidden_admins WHERE chat_id=? ORDER BY added_at DESC",
            (chat_id,)
        )
        return [dict(row) for row in rows]

    # ================================================================
    # 8. دوال الأمان
    # ================================================================

    async def get_security_settings(self, chat_id: int) -> Dict:
        """الحصول على إعدادات الأمان"""
        row = await self.fetchone("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
        if row:
            return dict(row)
        await self.execute("INSERT INTO group_security (chat_id) VALUES (?)", (chat_id,))
        row = await self.fetchone("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
        return dict(row) if row else {}

    async def update_security_settings(self, chat_id: int, **kwargs) -> bool:
        """تحديث إعدادات الأمان"""
        updates = [f"{k}=?" for k in kwargs]
        vals = list(kwargs.values()) + [chat_id]
        await self.execute(f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id=?", vals)
        return True

    async def get_banned_words(self, chat_id: int) -> List[str]:
        """الحصول على الكلمات المحظورة"""
        rows = await self.fetchall(
            "SELECT word FROM banned_words WHERE chat_id=? OR chat_id=-1",
            (chat_id,)
        )
        return [row[0] for row in rows]

    async def add_banned_word(self, word: str, chat_id: int, added_by: int) -> bool:
        """إضافة كلمة محظورة"""
        try:
            await self.execute(
                "INSERT INTO banned_words (word, chat_id, added_by, added_at) VALUES (?,?,?,?)",
                (word.strip().lower(), chat_id, added_by, TimeUtils.utc_iso())
            )
            return True
        except sqlite3.IntegrityError:
            return False

    async def remove_banned_word(self, word: str, chat_id: int) -> bool:
        """حذف كلمة محظورة"""
        await self.execute("DELETE FROM banned_words WHERE word=? AND chat_id=?", (word.strip().lower(), chat_id))
        return True

    async def get_user_warnings(self, user_id: int, chat_id: int) -> int:
        """الحصول على عدد تحذيرات المستخدم"""
        row = await self.fetchone("SELECT warnings FROM user_warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        return row[0] if row else 0

    async def add_user_warning(self, user_id: int, chat_id: int) -> int:
        """إضافة تحذير للمستخدم"""
        await self.execute(
            "INSERT OR REPLACE INTO user_warnings (user_id, chat_id, warnings) VALUES (?,?,COALESCE((SELECT warnings FROM user_warnings WHERE user_id=? AND chat_id=?),0)+1)",
            (user_id, chat_id, user_id, chat_id)
        )
        return await self.get_user_warnings(user_id, chat_id)

    async def reset_user_warnings(self, user_id: int, chat_id: int) -> bool:
        """إعادة تعيين تحذيرات المستخدم"""
        await self.execute("UPDATE user_warnings SET warnings=0 WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        return True

    async def add_admin_log(self, chat_id: int, admin_id: int, action: str, target_id: int = None, reason: str = "") -> bool:
        """إضافة سجل إداري"""
        await self.execute(
            "INSERT INTO admin_logs (chat_id, admin_id, action, target_id, reason, created_at) VALUES (?,?,?,?,?,?)",
            (chat_id, admin_id, action, target_id, reason, TimeUtils.utc_iso())
        )
        return True

    async def get_admin_logs(self, chat_id: int, limit: int = 20) -> List[Dict]:
        """الحصول على سجل الإجراءات الإدارية"""
        rows = await self.fetchall(
            "SELECT admin_id, action, target_id, reason, created_at FROM admin_logs WHERE chat_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        )
        return [dict(row) for row in rows]

    # ================================================================
    # 9. دوال الردود التلقائية
    # ================================================================

    async def get_auto_reply_settings(self, chat_id: int) -> Dict:
        """الحصول على إعدادات الردود التلقائية"""
        row = await self.fetchone("SELECT * FROM auto_reply_settings WHERE chat_id=?", (chat_id,))
        if row:
            return dict(row)
        await self.execute("INSERT INTO auto_reply_settings (chat_id) VALUES (?)", (chat_id,))
        row = await self.fetchone("SELECT * FROM auto_reply_settings WHERE chat_id=?", (chat_id,))
        return dict(row) if row else {'enabled': 0, 'only_admins': 0, 'ignore_bots': 1}

    async def update_auto_reply_settings(self, chat_id: int, **kwargs) -> bool:
        """تحديث إعدادات الردود التلقائية"""
        updates = [f"{k}=?" for k in kwargs]
        vals = list(kwargs.values()) + [chat_id]
        await self.execute(f"UPDATE auto_reply_settings SET {', '.join(updates)} WHERE chat_id=?", vals)
        return True

    async def add_auto_reply(self, chat_id: int, keyword: str, reply: str,
                             reply_type: str = 'text', media_id: str = None,
                             buttons: str = None) -> bool:
        """إضافة رد تلقائي"""
        try:
            await self.execute(
                "INSERT INTO auto_replies (chat_id, keyword, reply, reply_type, reply_media_id, reply_buttons, created_at) VALUES (?,?,?,?,?,?,?)",
                (chat_id, keyword.lower(), reply, reply_type, media_id, buttons, TimeUtils.utc_iso())
            )
            return True
        except sqlite3.IntegrityError:
            await self.execute(
                "UPDATE auto_replies SET reply=?, reply_type=?, reply_media_id=?, reply_buttons=?, created_at=? WHERE chat_id=? AND keyword=?",
                (reply, reply_type, media_id, buttons, TimeUtils.utc_iso(), chat_id, keyword.lower())
            )
            return True

    async def remove_auto_reply(self, chat_id: int, keyword: str) -> bool:
        """حذف رد تلقائي"""
        await self.execute("DELETE FROM auto_replies WHERE chat_id=? AND keyword=?", (chat_id, keyword.lower()))
        return True

    async def get_auto_reply(self, keyword: str, chat_id: int) -> Optional[Dict]:
        """الحصول على رد تلقائي"""
        row = await self.fetchone(
            "SELECT reply, reply_type, reply_media_id, reply_buttons FROM auto_replies WHERE chat_id=? AND keyword=? AND is_active=1",
            (chat_id, keyword.lower())
        )
        if row:
            await self.execute(
                "UPDATE auto_replies SET usage_count = usage_count + 1 WHERE chat_id=? AND keyword=?",
                (chat_id, keyword.lower())
            )
            return dict(row)
        row = await self.fetchone(
            "SELECT reply, reply_type, reply_media_id, reply_buttons FROM auto_replies WHERE chat_id=-1 AND keyword=? AND is_active=1",
            (keyword.lower(),)
        )
        return dict(row) if row else None

    async def get_auto_reply_stats(self, chat_id: int, limit: int = 20) -> List[Tuple[str, int]]:
        """الحصول على إحصائيات الردود التلقائية"""
        rows = await self.fetchall(
            "SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? ORDER BY usage_count DESC LIMIT ?",
            (chat_id, limit)
        )
        return [(row[0], row[1]) for row in rows]

    async def reset_auto_replies(self, chat_id: int) -> bool:
        """إعادة تعيين الردود التلقائية"""
        await self.execute("DELETE FROM auto_replies WHERE chat_id=?", (chat_id,))
        return True

    # ================================================================
    # 10. دوال الجدولة
    # ================================================================

    async def get_schedule(self, channel_id: int) -> Dict:
        """الحصول على إعدادات الجدولة"""
        row = await self.fetchone("SELECT * FROM schedule WHERE channel_db_id=?", (channel_id,))
        if row:
            return dict(row)
        await self.execute(
            "INSERT INTO schedule (channel_db_id, schedule_type, interval_minutes) VALUES (?, 'interval_minutes', 60)",
            (channel_id,)
        )
        row = await self.fetchone("SELECT * FROM schedule WHERE channel_db_id=?", (channel_id,))
        return dict(row) if row else {}

    async def update_schedule(self, channel_id: int, **kwargs) -> bool:
        """تحديث إعدادات الجدولة"""
        updates = [f"{k}=?" for k in kwargs]
        vals = list(kwargs.values()) + [channel_id]
        await self.execute(f"UPDATE schedule SET {', '.join(updates)} WHERE channel_db_id=?", vals)
        return True

    async def update_next_publish(self, channel_id: int) -> bool:
        """تحديث موعد النشر التالي"""
        sched = await self.get_schedule(channel_id)
        last_pub = await self.fetchone("SELECT last_publish_time FROM last_publish WHERE channel_db_id=?", (channel_id,))
        last_time = TimeUtils.safe_parse_iso(last_pub[0]) if last_pub and last_pub[0] else TimeUtils.utc_now()
        st = sched.get('schedule_type', 'interval_minutes')
        if st == 'interval_minutes':
            interval = sched.get('interval_minutes', 12)
            next_date = last_time + timedelta(minutes=interval)
        elif st == 'interval_hours':
            interval = sched.get('interval_hours', 1)
            next_date = last_time + timedelta(hours=interval)
        elif st == 'interval_days':
            interval = sched.get('interval_days', 1)
            next_date = last_time + timedelta(days=interval)
        else:
            next_date = last_time + timedelta(minutes=12)
        while next_date <= TimeUtils.utc_now():
            if st == 'interval_minutes':
                next_date += timedelta(minutes=sched.get('interval_minutes', 12))
            elif st == 'interval_hours':
                next_date += timedelta(hours=sched.get('interval_hours', 1))
            elif st == 'interval_days':
                next_date += timedelta(days=sched.get('interval_days', 1))
            else:
                next_date += timedelta(minutes=12)
        await self.execute("UPDATE schedule SET next_publish_date=? WHERE channel_db_id=?", (next_date.isoformat(), channel_id))
        return True

    async def update_last_publish(self, channel_id: int) -> bool:
        """تحديث وقت آخر نشر"""
        await self.execute(
            "INSERT OR REPLACE INTO last_publish (channel_db_id, last_publish_time) VALUES (?,?)",
            (channel_id, TimeUtils.utc_iso())
        )
        return True

    async def get_channels_to_publish(self, limit: int = 20) -> List[Dict]:
        """الحصول على القنوات التي تحتاج للنشر"""
        rows = await self.fetchall("""
            SELECT uc.id, uc.channel_id, uc.user_id, u.auto_publish
            FROM user_channels uc
            JOIN users u ON uc.user_id = u.user_id
            LEFT JOIN schedule s ON uc.id = s.channel_db_id
            WHERE uc.banned = 0 AND u.banned = 0 AND u.auto_publish = 1
            AND (s.next_publish_date IS NULL OR s.next_publish_date <= ?)
            AND EXISTS (
                SELECT 1 FROM posts p
                WHERE p.channel_db_id = uc.id AND p.published = 0
                AND (p.fail_count IS NULL OR p.fail_count < 3)
            )
            ORDER BY COALESCE(s.next_publish_date, '1970-01-01') ASC
            LIMIT ?
        """, (TimeUtils.utc_iso(), limit))
        return [dict(row) for row in rows]

    # ================================================================
    # 11. دوال التذاكر
    # ================================================================

    async def create_ticket(self, user_id: int, username: str, content: str,
                            media_type: str = None, media_file_id: str = None) -> int:
        """إنشاء تذكرة دعم"""
        next_num = (await self.fetchone("SELECT COALESCE(MAX(ticket_number), 0) + 1 FROM support_tickets"))[0]
        await self.execute(
            "INSERT INTO support_tickets (user_id, username, message, media_type, media_file_id, ticket_number, created_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, username, content, media_type, media_file_id, next_num, TimeUtils.utc_iso())
        )
        return next_num

    async def get_tickets(self) -> List[Dict]:
        """الحصول على جميع التذاكر"""
        rows = await self.fetchall(
            "SELECT id, user_id, username, ticket_number, message, status, created_at FROM support_tickets WHERE status='pending' ORDER BY created_at DESC"
        )
        return [dict(row) for row in rows]

    async def close_ticket(self, ticket_id: int) -> bool:
        """إغلاق تذكرة"""
        await self.execute("UPDATE support_tickets SET status='closed' WHERE id=?", (ticket_id,))
        return True

    async def delete_all_tickets(self) -> bool:
        """حذف جميع التذاكر"""
        await self.execute("DELETE FROM support_tickets")
        return True

    # ================================================================
    # 12. دوال الإحالات
    # ================================================================

    async def add_referral(self, referrer_id: int, referred_id: int) -> bool:
        """إضافة إحالة جديدة"""
        if referrer_id == referred_id:
            return False
        try:
            await self.execute(
                "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?,?,?)",
                (referrer_id, referred_id, TimeUtils.utc_iso())
            )
            await self.execute(
                "INSERT INTO referral_rewards (user_id, referral_count, total_reward_days, claimed_reward_days, last_referral_date) VALUES (?,1,3,0,?) ON CONFLICT(user_id) DO UPDATE SET referral_count=referral_count+1, total_reward_days=total_reward_days+3, last_referral_date=?",
                (referrer_id, TimeUtils.utc_iso(), TimeUtils.utc_iso())
            )
            return True
        except sqlite3.IntegrityError:
            return False

    async def get_referral_stats(self, user_id: int) -> Dict:
        """الحصول على إحصائيات الإحالات"""
        total = (await self.fetchone("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,)))[0]
        claimed = (await self.fetchone("SELECT COALESCE(SUM(claimed_reward_days),0) FROM referral_rewards WHERE user_id=?", (user_id,)))[0]
        available = (await self.fetchone("SELECT total_reward_days - claimed_reward_days FROM referral_rewards WHERE user_id=?", (user_id,)))[0] or 0
        return {'total': total, 'claimed': claimed, 'available': available}

    async def claim_referral_reward(self, user_id: int) -> int:
        """صرف مكافأة الإحالات"""
        stats = await self.get_referral_stats(user_id)
        av = stats['available']
        if av <= 0:
            return 0
        await self.execute(
            "UPDATE referral_rewards SET claimed_reward_days = claimed_reward_days + ? WHERE user_id=?",
            (av, user_id)
        )
        await self.execute(
            "UPDATE users SET subscription_end = datetime(COALESCE(subscription_end, ?), '+' || ? || ' days') WHERE user_id=?",
            (TimeUtils.utc_iso(), av, user_id)
        )
        return av

    async def get_referrals_list(self, user_id: int) -> List[int]:
        """الحصول على قائمة الإحالات"""
        rows = await self.fetchall("SELECT referred_id FROM referrals WHERE referrer_id=? ORDER BY created_at DESC", (user_id,))
        return [row[0] for row in rows]

    # ================================================================
    # 13. دوال التذكيرات
    # ================================================================

    async def get_reminder_settings(self, user_id: int) -> Dict:
        """الحصول على إعدادات التذكيرات"""
        row = await self.fetchone("SELECT * FROM user_reminder_settings WHERE user_id=?", (user_id,))
        if row:
            return dict(row)
        await self.execute("INSERT INTO user_reminder_settings (user_id) VALUES (?)", (user_id,))
        row = await self.fetchone("SELECT * FROM user_reminder_settings WHERE user_id=?", (user_id,))
        return dict(row) if row else {}

    async def update_reminder_settings(self, user_id: int, **kwargs) -> bool:
        """تحديث إعدادات التذكيرات"""
        updates = [f"{k}=?" for k in kwargs]
        vals = list(kwargs.values()) + [user_id]
        await self.execute(f"UPDATE user_reminder_settings SET {', '.join(updates)} WHERE user_id=?", vals)
        return True

    async def get_users_for_reminder(self) -> List[Dict]:
        """الحصول على المستخدمين الذين يحتاجون تذكير"""
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
        """, (TimeUtils.utc_iso(), TimeUtils.utc_iso(), TimeUtils.utc_iso(), TimeUtils.utc_iso()))
        return [dict(row) for row in rows]

    # ================================================================
    # 14. دوال المسابقات
    # ================================================================

    async def create_contest(self, creator_id: int, title: str, description: str,
                             prize: str, end_date: str) -> int:
        """إنشاء مسابقة جديدة"""
        result = await self.fetchone(
            "INSERT INTO contests (creator_id, title, description, prize, end_date, created_at) VALUES (?,?,?,?,?,?) RETURNING id",
            (creator_id, title, description, prize, end_date, TimeUtils.utc_iso())
        )
        return result[0] if result else 0

    async def get_active_contests(self, limit: int = 10) -> List[Dict]:
        """الحصول على المسابقات النشطة"""
        rows = await self.fetchall("""
            SELECT c.*,
                   (SELECT COUNT(*) FROM contest_participants WHERE contest_id = c.id) as participants
            FROM contests c
            WHERE c.status = 'active' AND datetime(c.end_date) > datetime(?)
            ORDER BY c.end_date ASC LIMIT ?
        """, (TimeUtils.utc_iso(), limit))
        return [dict(row) for row in rows]

    async def join_contest(self, contest_id: int, user_id: int, answer: str = "") -> bool:
        """المشاركة في مسابقة"""
        try:
            await self.execute(
                "INSERT INTO contest_participants (contest_id, user_id, answer, joined_at) VALUES (?,?,?,?)",
                (contest_id, user_id, answer, TimeUtils.utc_iso())
            )
            return True
        except sqlite3.IntegrityError:
            return False

    async def declare_winner(self, contest_id: int, winner_id: int) -> bool:
        """إعلان الفائز في مسابقة"""
        await self.execute("UPDATE contests SET status='closed', winner_id=? WHERE id=?", (winner_id, contest_id))
        await self.execute(
            "INSERT INTO contest_winners (contest_id, winner_id, announced_at) VALUES (?,?,?)",
            (contest_id, winner_id, TimeUtils.utc_iso())
        )
        return True

    async def get_contest_winners(self, limit: int = 10) -> List[Dict]:
        """الحصول على الفائزين في المسابقات"""
        rows = await self.fetchall("""
            SELECT c.title, c.winner_id, u.username, cw.announced_at
            FROM contest_winners cw
            JOIN contests c ON cw.contest_id = c.id
            JOIN users u ON cw.winner_id = u.user_id
            ORDER BY cw.announced_at DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in rows]

    async def delete_contest(self, contest_id: int, user_id: int) -> bool:
        """حذف مسابقة"""
        row = await self.fetchone("SELECT creator_id FROM contests WHERE id=?", (contest_id,))
        if row and (row[0] == user_id):
            await self.execute("DELETE FROM contest_participants WHERE contest_id=?", (contest_id,))
            await self.execute("DELETE FROM contests WHERE id=?", (contest_id,))
            return True
        return False

    # ================================================================
    # 15. دوال الإعدادات العامة
    # ================================================================

    async def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """الحصول على إعداد عام"""
        row = await self.fetchone("SELECT value FROM settings WHERE key=?", (key,))
        return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> bool:
        """تعيين إعداد عام"""
        await self.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
        return True

    async def get_force_subscribe_channel(self) -> Optional[str]:
        """الحصول على قناة الاشتراك الإجباري"""
        return await self.get_setting('force_subscribe_channel')

    async def get_updates_channel(self) -> Optional[str]:
        """الحصول على قناة التحديثات"""
        return await self.get_setting('updates_channel')

    async def get_log_channel(self) -> Optional[str]:
        """الحصول على قناة السجلات"""
        return await self.get_setting('log_channel_id')

    async def get_publish_interval(self) -> int:
        """الحصول على فترة النشر الافتراضية"""
        v = await self.get_setting('publish_interval', '60')
        try:
            return int(v)
        except:
            return 60

    async def get_auto_backup(self) -> bool:
        """التحقق من تفعيل النسخ الاحتياطي التلقائي"""
        v = await self.get_setting('auto_backup', 'true')
        return v.lower() == 'true'

    # ================================================================
    # 16. دوال الباقات والاشتراكات
    # ================================================================

    async def get_plan(self, plan_id: int) -> Optional[Dict]:
        """الحصول على باقة"""
        row = await self.fetchone("SELECT * FROM plans WHERE id=?", (plan_id,))
        return dict(row) if row else None

    async def get_plan_by_name(self, name: str) -> Optional[Dict]:
        """الحصول على باقة بالاسم"""
        row = await self.fetchone("SELECT * FROM plans WHERE name=?", (name,))
        return dict(row) if row else None

    async def get_all_plans(self) -> List[Dict]:
        """الحصول على جميع الباقات النشطة"""
        rows = await self.fetchall("SELECT * FROM plans WHERE is_active=1 ORDER BY price")
        return [dict(row) for row in rows]

    async def create_subscription(self, user_id: int, plan_id: int, provider: str = 'xtr',
                                   provider_sub_id: str = None) -> int:
        """إنشاء اشتراك جديد"""
        plan = await self.get_plan(plan_id)
        if not plan:
            return 0
        result = await self.fetchone(
            "INSERT INTO subscriptions (user_id, plan_id, status, start_date, end_date, auto_renew, provider, provider_subscription_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?) RETURNING id",
            (user_id, plan_id, 'active', TimeUtils.utc_iso(),
             (TimeUtils.utc_now() + timedelta(days=plan['duration_days'])).isoformat(),
             0, provider, provider_sub_id, TimeUtils.utc_iso(), TimeUtils.utc_iso())
        )
        return result[0] if result else 0

    async def get_active_subscription(self, user_id: int) -> Optional[Dict]:
        """الحصول على الاشتراك النشط"""
        row = await self.fetchone("""
            SELECT s.*, p.name, p.duration_days, p.max_channels, p.max_posts, p.features
            FROM subscriptions s JOIN plans p ON s.plan_id = p.id
            WHERE s.user_id=? AND s.status='active' AND s.end_date > datetime('now')
            ORDER BY s.end_date DESC LIMIT 1
        """, (user_id,))
        return dict(row) if row else None

    async def expire_expired_subscriptions(self) -> None:
        """تحديث الاشتراكات المنتهية"""
        await self.execute("UPDATE subscriptions SET status='expired' WHERE status='active' AND end_date < datetime('now')")

    # ================================================================
    # 17. دوال الفواتير والدفع
    # ================================================================

    async def create_invoice(self, user_id: int, plan_id: int, amount: int,
                              currency: str = 'XTR', provider: str = 'xtr') -> str:
        """إنشاء فاتورة جديدة"""
        number = f"INV-{TimeUtils.utc_now().strftime('%Y%m')}-{secrets.token_hex(4).upper()}"
        await self.execute(
            "INSERT INTO invoices (number, user_id, plan_id, amount, currency, status, provider, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (number, user_id, plan_id, amount, currency, 'pending', provider, TimeUtils.utc_iso())
        )
        return number

    async def mark_invoice_paid(self, invoice_number: str, payment_id: str) -> None:
        """تحديد فاتورة كمدفوعة"""
        await self.execute(
            "UPDATE invoices SET status='paid', provider_payment_id=?, paid_at=? WHERE number=?",
            (payment_id, TimeUtils.utc_iso(), invoice_number)
        )

    async def get_invoice(self, number: str) -> Optional[Dict]:
        """الحصول على فاتورة برقمها"""
        row = await self.fetchone("SELECT * FROM invoices WHERE number=?", (number,))
        return dict(row) if row else None

    async def get_user_invoices(self, user_id: int, limit: int = 20) -> List[Dict]:
        """الحصول على فواتير المستخدم"""
        rows = await self.fetchall(
            "SELECT * FROM invoices WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        return [dict(row) for row in rows]

    async def add_payment_log(self, user_id: int, provider: str, event_type: str, data: dict) -> None:
        """إضافة سجل دفع"""
        await self.execute(
            "INSERT INTO payment_logs (user_id, provider, event_type, data, created_at) VALUES (?,?,?,?,?)",
            (user_id, provider, event_type, json.dumps(data), TimeUtils.utc_iso())
        )


# =====================================================================
# 18. إنشاء كائن قاعدة البيانات (Singleton)
# =====================================================================

DB = Database()

# =====================================================================
# 19. دوال مساعدة للوصول السريع
# =====================================================================

async def get_db() -> Database:
    """الحصول على كائن قاعدة البيانات"""
    return DB

async def initialize_db() -> None:
    """تهيئة قاعدة البيانات (يجب استدعاؤها عند بدء التشغيل)"""
    await DB.initialize()


# =====================================================================
# 20. اختبار سريع (إذا تم تشغيل الملف مباشرة)
# =====================================================================

if __name__ == "__main__":
    import asyncio

    async def test():
        print("🚀 اختبار قاعدة البيانات...")
        await DB.initialize()

        # اختبار إضافة مستخدم مع تجربة تلقائية
        await DB.register_user(123456789, "test_user", "Test")
        print("✅ تم إضافة مستخدم مع تجربة 30 يوم")

        # اختبار جلب المستخدم
        user = await DB.get_user(123456789)
        print(f"✅ معلومات المستخدم: {user}")

        # اختبار الباقات
        plans = await DB.fetchall("SELECT * FROM plans")
        print(f"✅ عدد الباقات: {len(plans)}")
        for p in plans:
            print(f"   - {p['name']}: {p['price']} نجوم")

        print("✅ جميع الاختبارات اجتازت بنجاح!")

    asyncio.run(test())

