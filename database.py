#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
database.py - قاعدة البيانات المتكاملة للبوت
=============================================
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

from config import PATHS, CONFIG

logger = logging.getLogger(__name__)


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
    def safe_parse_iso(date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str)
        except ValueError:
            return None


class Database:
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls) -> 'Database':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @asynccontextmanager
    async def _get_connection(self):
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
        async with self._get_connection() as conn:
            await self._create_tables(conn)
            await self._create_indexes(conn)
            await self._init_default_data(conn)
            await self._import_banned_words(conn)
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")

    async def _create_tables(self, conn) -> None:
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
                publish_time TEXT DEFAULT '00:00',
                next_publish_date TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS last_publish (
                channel_db_id INTEGER PRIMARY KEY,
                last_publish_time TEXT
            )
        """)
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_security (
                chat_id INTEGER PRIMARY KEY,
                delete_links INTEGER DEFAULT 0,
                mentions INTEGER DEFAULT 0,
                slow_mode INTEGER DEFAULT 0,
                welcome_enabled INTEGER DEFAULT 0,
                welcome_text TEXT DEFAULT 'مرحباً {user} في {chat} 🤍',
                goodbye_enabled INTEGER DEFAULT 0,
                goodbye_text TEXT DEFAULT 'وداعاً {user} 👋',
                delete_banned_words INTEGER DEFAULT 0,
                auto_penalty TEXT DEFAULT 'none',
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
                antiflood_seconds INTEGER DEFAULT 10,
                max_warnings INTEGER DEFAULT 3,
                warn_penalty TEXT DEFAULT 'ban',
                max_message_length INTEGER DEFAULT 0,
                night_mode_enabled INTEGER DEFAULT 0,
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_replies (
                chat_id INTEGER,
                keyword TEXT,
                reply TEXT,
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
                ignore_bots INTEGER DEFAULT 1
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                message TEXT,
                ticket_number INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TEXT
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
        await conn.execute("INSERT OR IGNORE INTO settings VALUES ('publish_interval', '720')")
        await conn.execute("INSERT OR IGNORE INTO settings VALUES ('auto_backup', '1')")
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
                claimed_reward_days INTEGER DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_reminder_settings (
                user_id INTEGER PRIMARY KEY,
                subscription_reminder INTEGER DEFAULT 1,
                daily_stats_reminder INTEGER DEFAULT 0,
                weekly_report INTEGER DEFAULT 1,
                reminder_days_before INTEGER DEFAULT 3
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
                created_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contest_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER,
                user_id INTEGER,
                answer TEXT,
                joined_at TEXT,
                UNIQUE(contest_id, user_id)
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
            CREATE TABLE IF NOT EXISTS user_messages (
                user_id INTEGER,
                chat_id INTEGER,
                message_time TEXT,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                description TEXT,
                price INTEGER,
                duration_days INTEGER,
                max_channels INTEGER,
                max_posts INTEGER,
                is_active INTEGER DEFAULT 1
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
                created_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number TEXT UNIQUE,
                user_id INTEGER,
                plan_id INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TEXT
            )
        """)
        await conn.commit()

    async def _create_indexes(self, conn) -> None:
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_banned ON users(banned)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_uc_user ON user_channels(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_banned ON bot_groups(banned)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_banned_words_chat ON banned_words(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ar_chat ON auto_replies(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_inv_user ON invoices(user_id)")
        await conn.commit()

    async def _init_default_data(self, conn) -> None:
        default_plans = [
            ("يوم", "باقة يوم واحد", 5, 1, 1, 50),
            ("أسبوع", "باقة 7 أيام", 25, 7, 3, 300),
            ("شهر", "باقة 30 يوم", 75, 30, 10, 1500),
            ("3 أشهر", "باقة 90 يوم", 200, 90, 999, 99999),
        ]
        for name, desc, price, days, max_ch, max_p in default_plans:
            await conn.execute(
                "INSERT OR IGNORE INTO plans (name, description, price, duration_days, max_channels, max_posts) VALUES (?,?,?,?,?,?)",
                (name, desc, price, days, max_ch, max_p)
            )
        await conn.commit()

    async def _import_banned_words(self, conn) -> None:
        try:
            from banned_words import BANNED_WORDS
            for word in BANNED_WORDS:
                await conn.execute(
                    "INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?,?,?,?)",
                    (word.strip().lower(), -1, CONFIG.PRIMARY_OWNER_ID, TimeUtils.utc_iso())
                )
            logger.info(f"✅ تم استيراد {len(BANNED_WORDS)} كلمة محظورة")
        except ImportError:
            pass

    # ========== دوال المستخدمين ==========

    async def register_user(self, user_id: int, username: str = "", first_name: str = "") -> bool:
        try:
            row = await self.fetchone("SELECT user_id FROM users WHERE user_id=?", (user_id,))
            if row:
                await self.execute("UPDATE users SET username=?, first_name=?, updated_at=? WHERE user_id=?",
                                   (username, first_name, TimeUtils.utc_iso(), user_id))
                return True
            code = secrets.token_urlsafe(6)
            await self.execute(
                "INSERT INTO users (user_id, username, first_name, referral_code, trial_used, created_at, updated_at) VALUES (?,?,?,?,0,?,?)",
                (user_id, username, first_name, code, TimeUtils.utc_iso(), TimeUtils.utc_iso())
            )
            return True
        except Exception as e:
            logger.error(f"❌ register_user: {e}")
            return False

    async def get_user(self, user_id: int) -> Optional[Dict]:
        row = await self.fetchone("SELECT * FROM users WHERE user_id=?", (user_id,))
        return dict(row) if row else None

    async def get_user_language(self, user_id: int) -> str:
        row = await self.fetchone("SELECT language FROM users WHERE user_id=?", (user_id,))
        return row[0] if row else 'ar'

    async def set_user_language(self, user_id: int, lang: str) -> None:
        await self.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))

    async def get_auto_publish_status(self, user_id: int) -> bool:
        row = await self.fetchone("SELECT auto_publish FROM users WHERE user_id=?", (user_id,))
        return row[0] == 1 if row else True

    async def set_auto_publish(self, user_id: int, status: bool) -> None:
        await self.execute("UPDATE users SET auto_publish=? WHERE user_id=?", (1 if status else 0, user_id))

    async def get_auto_recycle_status(self, user_id: int) -> bool:
        row = await self.fetchone("SELECT auto_recycle FROM users WHERE user_id=?", (user_id,))
        return row[0] == 1 if row else True

    async def set_auto_recycle(self, user_id: int, status: bool) -> None:
        await self.execute("UPDATE users SET auto_recycle=? WHERE user_id=?", (1 if status else 0, user_id))

    async def is_user_banned(self, user_id: int) -> bool:
        row = await self.fetchone("SELECT banned FROM users WHERE user_id=?", (user_id,))
        return row[0] == 1 if row else False

    async def get_all_users(self) -> List[Tuple[int, int]]:
        rows = await self.fetchall("SELECT user_id, banned FROM users")
        return [(r[0], r[1]) for r in rows]

    async def get_user_stats(self) -> Dict:
        total = await self.fetchval("SELECT COUNT(*) FROM users") or 0
        banned = await self.fetchval("SELECT COUNT(*) FROM users WHERE banned=1") or 0
        return {'users': total, 'banned': banned}

    async def has_active_subscription(self, user_id: int) -> bool:
        row = await self.fetchone("SELECT subscription_end FROM users WHERE user_id=? AND subscription_end > datetime('now')", (user_id,))
        return row is not None

    async def has_used_trial(self, user_id: int) -> bool:
        row = await self.fetchone("SELECT trial_used FROM users WHERE user_id=?", (user_id,))
        return row[0] == 1 if row else False

    async def activate_trial(self, user_id: int) -> int:
        end_date = (TimeUtils.utc_now() + timedelta(days=30)).isoformat()
        await self.execute("UPDATE users SET trial_used=1, subscription_end=? WHERE user_id=?", (end_date, user_id))
        return 30

    async def get_referral_code(self, user_id: int) -> str:
        row = await self.fetchone("SELECT referral_code FROM users WHERE user_id=?", (user_id,))
        return row[0] if row else f"ref_{user_id}"

    async def get_user_by_referral_code(self, code: str) -> Optional[int]:
        row = await self.fetchone("SELECT user_id FROM users WHERE referral_code=?", (code,))
        return row[0] if row else None

    # ========== دوال القنوات ==========

    async def add_channel(self, user_id: int, channel_id: int, channel_name: str) -> Optional[int]:
        try:
            row = await self.fetchone("SELECT id FROM user_channels WHERE user_id=? AND channel_id=?", (user_id, channel_id))
            if row:
                return row[0]
            async with self._get_connection() as conn:
                cur = await conn.execute(
                    "INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) VALUES (?,?,?,?)",
                    (user_id, channel_id, channel_name, TimeUtils.utc_iso())
                )
                ch_db_id = cur.lastrowid
                await conn.execute(
                    "INSERT OR IGNORE INTO schedule (channel_db_id, next_publish_date) VALUES (?,?)",
                    (ch_db_id, (TimeUtils.utc_now() + timedelta(seconds=720)).isoformat())
                )
                await conn.commit()
                return ch_db_id
        except Exception as e:
            logger.error(f"❌ add_channel: {e}")
            return None

    async def get_user_channels(self, user_id: int) -> List[Dict]:
        rows = await self.fetchall("SELECT id, channel_id, channel_name, banned FROM user_channels WHERE user_id=? ORDER BY created_at DESC", (user_id,))
        return [dict(r) for r in rows]

    async def get_active_channel(self, user_id: int) -> Optional[int]:
        row = await self.fetchone("SELECT active_channel FROM users WHERE user_id=?", (user_id,))
        if row and row[0]:
            return row[0]
        row2 = await self.fetchone("SELECT id FROM user_channels WHERE user_id=? AND banned=0 ORDER BY id LIMIT 1", (user_id,))
        return row2[0] if row2 else None

    async def set_active_channel(self, user_id: int, channel_id: int) -> None:
        await self.execute("UPDATE users SET active_channel=? WHERE user_id=?", (channel_id, user_id))

    async def get_channel_info(self, channel_id: int) -> Optional[Dict]:
        row = await self.fetchone("SELECT * FROM user_channels WHERE id=?", (channel_id,))
        return dict(row) if row else None

    async def delete_channel(self, user_id: int, channel_id: int) -> None:
        await self.execute("DELETE FROM user_channels WHERE id=? AND user_id=?", (channel_id, user_id))

    # ========== دوال المنشورات ==========

    async def add_posts(self, channel_id: int, posts: List[Tuple[str, str, str]]) -> int:
        vals = [(channel_id, (t or "")[:4096], m, f, TimeUtils.utc_iso()) for t, m, f in posts]
        await self.executemany("INSERT INTO posts (channel_db_id, text, media_type, media_file_id, created_at) VALUES (?,?,?,?,?)", vals)
        return len(vals)

    async def get_unpublished_posts_count(self, channel_id: int) -> int:
        return await self.fetchval("SELECT COUNT(*) FROM posts WHERE channel_db_id=? AND published=0", (channel_id,)) or 0

    async def get_next_post(self, channel_id: int) -> Optional[Dict]:
        row = await self.fetchone("SELECT id, text, media_type, media_file_id FROM posts WHERE channel_db_id=? AND published=0 ORDER BY created_at ASC LIMIT 1", (channel_id,))
        return dict(row) if row else None

    async def get_user_posts(self, channel_id: int, limit: int = 10) -> List[Dict]:
        rows = await self.fetchall("SELECT id, text FROM posts WHERE channel_db_id=? AND published=0 LIMIT ?", (channel_id, limit))
        return [dict(r) for r in rows]

    async def mark_post_published(self, post_id: int) -> None:
        await self.execute("UPDATE posts SET published=1, published_at=? WHERE id=?", (TimeUtils.utc_iso(), post_id))

    async def increment_post_fail(self, post_id: int) -> None:
        await self.execute("UPDATE posts SET fail_count = fail_count + 1 WHERE id=?", (post_id,))

    async def reset_posts(self, channel_id: int) -> int:
        await self.execute("UPDATE posts SET published=0 WHERE channel_db_id=?", (channel_id,))
        return await self.get_unpublished_posts_count(channel_id)

    # ========== دوال المجموعات ==========

    async def register_group(self, chat_id: int, chat_name: str, user_id: int, username: str = None) -> None:
        row = await self.fetchone("SELECT chat_id FROM bot_groups WHERE chat_id=?", (chat_id,))
        if row:
            await self.execute("UPDATE bot_groups SET chat_name=?, username=?, updated_at=? WHERE chat_id=?", (chat_name, username, TimeUtils.utc_iso(), chat_id))
        else:
            await self.execute("INSERT INTO bot_groups (chat_id, chat_name, username, added_by, added_at) VALUES (?,?,?,?,?)", (chat_id, chat_name, username, user_id, TimeUtils.utc_iso()))

    async def get_user_groups(self, user_id: int) -> List[Tuple[int, str, str, int]]:
        rows = await self.fetchall("""
            SELECT DISTINCT bg.chat_id, bg.chat_name, bg.username, bg.banned
            FROM bot_groups bg
            LEFT JOIN user_groups_link l ON bg.chat_id = l.chat_id AND l.user_id=?
            LEFT JOIN hidden_owner_groups h ON bg.chat_id = h.chat_id AND h.owner_id=?
            LEFT JOIN hidden_admins ha ON bg.chat_id = ha.chat_id AND ha.admin_id=?
            WHERE l.user_id IS NOT NULL OR h.owner_id IS NOT NULL OR ha.admin_id IS NOT NULL
        """, (user_id, user_id, user_id))
        return [(r[0], r[1], r[2] or "", r[3]) for r in rows]

    async def sync_group_admins(self, chat_id: int, admin_ids: List[int]) -> int:
        await self.execute("DELETE FROM group_admins WHERE chat_id=?", (chat_id,))
        if admin_ids:
            await self.executemany("INSERT OR IGNORE INTO group_admins VALUES (?,?)", [(chat_id, aid) for aid in admin_ids])
        return len(admin_ids)

    # ========== دوال المخفيين ==========

    async def add_hidden_owner(self, chat_id: int, owner_id: int) -> None:
        await self.execute("INSERT OR IGNORE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,1)", (chat_id, owner_id))

    async def remove_hidden_owner(self, chat_id: int, owner_id: int) -> None:
        await self.execute("DELETE FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, owner_id))

    async def get_hidden_owners(self, chat_id: int) -> List[int]:
        rows = await self.fetchall("SELECT owner_id FROM hidden_owner_groups WHERE chat_id=?", (chat_id,))
        return [r[0] for r in rows]

    async def is_hidden_owner(self, chat_id: int, user_id: int) -> bool:
        row = await self.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
        return row is not None

    async def add_hidden_admin(self, chat_id: int, admin_id: int, added_by: int) -> None:
        await self.execute("INSERT OR IGNORE INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?,?,?,?)", (chat_id, admin_id, added_by, TimeUtils.utc_iso()))

    async def remove_hidden_admin(self, chat_id: int, admin_id: int) -> None:
        await self.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))

    async def get_hidden_admins(self, chat_id: int) -> List[Dict]:
        rows = await self.fetchall("SELECT admin_id, added_by, added_at FROM hidden_admins WHERE chat_id=?", (chat_id,))
        return [dict(r) for r in rows]

    async def is_hidden_admin(self, chat_id: int, user_id: int) -> bool:
        row = await self.fetchone("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, user_id))
        return row is not None

    # ========== دوال الأمان ==========

    async def get_security_settings(self, chat_id: int) -> Dict:
        row = await self.fetchone("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
        if row:
            return dict(row)
        await self.execute("INSERT INTO group_security (chat_id) VALUES (?)", (chat_id,))
        row = await self.fetchone("SELECT * FROM group_security WHERE chat_id=?", (chat_id,))
        return dict(row) if row else {}

    async def update_security_settings(self, chat_id: int, **kwargs) -> None:
        updates = [f"{k}=?" for k in kwargs]
        vals = list(kwargs.values()) + [chat_id]
        await self.execute(f"UPDATE group_security SET {', '.join(updates)} WHERE chat_id=?", vals)

    async def get_banned_words(self, chat_id: int) -> List[str]:
        rows = await self.fetchall("SELECT word FROM banned_words WHERE chat_id=? OR chat_id=-1", (chat_id,))
        return [r[0] for r in rows]

    async def add_banned_word(self, word: str, chat_id: int, added_by: int) -> Tuple[bool, bool]:
        try:
            await self.execute("INSERT INTO banned_words (word, chat_id, added_by, added_at) VALUES (?,?,?,?)", (word.lower(), chat_id, added_by, TimeUtils.utc_iso()))
            return True, False
        except sqlite3.IntegrityError:
            return False, True

    async def remove_banned_word(self, word: str, chat_id: int) -> None:
        await self.execute("DELETE FROM banned_words WHERE word=? AND chat_id=?", (word.lower(), chat_id))

    # ========== دوال الردود ==========

    async def get_auto_reply_settings(self, chat_id: int) -> Dict:
        row = await self.fetchone("SELECT * FROM auto_reply_settings WHERE chat_id=?", (chat_id,))
        if row:
            return dict(row)
        await self.execute("INSERT INTO auto_reply_settings (chat_id) VALUES (?)", (chat_id,))
        return {'enabled': 0, 'only_admins': 0, 'ignore_bots': 1}

    async def update_auto_reply_settings(self, chat_id: int, **kwargs) -> None:
        updates = [f"{k}=?" for k in kwargs]
        vals = list(kwargs.values()) + [chat_id]
        await self.execute(f"UPDATE auto_reply_settings SET {', '.join(updates)} WHERE chat_id=?", vals)

    async def add_auto_reply(self, chat_id: int, keyword: str, reply: str) -> None:
        await self.execute("INSERT OR REPLACE INTO auto_replies (chat_id, keyword, reply, created_at) VALUES (?,?,?,?)", (chat_id, keyword.lower(), reply, TimeUtils.utc_iso()))

    async def remove_auto_reply(self, chat_id: int, keyword: str) -> None:
        await self.execute("DELETE FROM auto_replies WHERE chat_id=? AND keyword=?", (chat_id, keyword.lower()))

    async def get_auto_reply(self, keyword: str, chat_id: int) -> Optional[Dict]:
        row = await self.fetchone("SELECT reply FROM auto_replies WHERE chat_id=? AND keyword=? AND is_active=1", (chat_id, keyword.lower()))
        return dict(row) if row else None

    async def reset_auto_replies(self, chat_id: int) -> None:
        await self.execute("DELETE FROM auto_replies WHERE chat_id=?", (chat_id,))

    # ========== دوال التذاكر ==========

    async def create_ticket(self, user_id: int, username: str, message: str) -> int:
        next_num = (await self.fetchval("SELECT COALESCE(MAX(ticket_number), 0) + 1 FROM support_tickets")) or 1
        await self.execute("INSERT INTO support_tickets (user_id, username, message, ticket_number, created_at) VALUES (?,?,?,?,?)", (user_id, username, message, next_num, TimeUtils.utc_iso()))
        return next_num

    async def get_tickets(self) -> List[Dict]:
        rows = await self.fetchall("SELECT * FROM support_tickets WHERE status='pending' ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def delete_all_tickets(self) -> None:
        await self.execute("DELETE FROM support_tickets")

    # ========== دوال الإحالات ==========

    async def add_referral(self, referrer_id: int, referred_id: int) -> bool:
        try:
            await self.execute("INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?,?,?)", (referrer_id, referred_id, TimeUtils.utc_iso()))
            await self.execute("INSERT INTO referral_rewards (user_id, referral_count, total_reward_days) VALUES (?,1,3) ON CONFLICT(user_id) DO UPDATE SET referral_count=referral_count+1, total_reward_days=total_reward_days+3", (referrer_id,))
            return True
        except sqlite3.IntegrityError:
            return False

    async def get_referral_stats(self, user_id: int) -> Dict:
        total = await self.fetchval("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,)) or 0
        claimed = await self.fetchval("SELECT claimed_reward_days FROM referral_rewards WHERE user_id=?", (user_id,)) or 0
        available = await self.fetchval("SELECT total_reward_days - claimed_reward_days FROM referral_rewards WHERE user_id=?", (user_id,)) or 0
        return {'total': total, 'claimed': claimed, 'available': max(0, available)}

    async def claim_referral_reward(self, user_id: int) -> int:
        stats = await self.get_referral_stats(user_id)
        av = stats['available']
        if av <= 0:
            return 0
        await self.execute("UPDATE referral_rewards SET claimed_reward_days = claimed_reward_days + ? WHERE user_id=?", (av, user_id))
        return av

    async def get_referrals_list(self, user_id: int) -> List[int]:
        rows = await self.fetchall("SELECT referred_id FROM referrals WHERE referrer_id=?", (user_id,))
        return [r[0] for r in rows]

    # ========== دوال التذكيرات ==========

    async def get_reminder_settings(self, user_id: int) -> Dict:
        row = await self.fetchone("SELECT * FROM user_reminder_settings WHERE user_id=?", (user_id,))
        if row:
            return dict(row)
        await self.execute("INSERT INTO user_reminder_settings (user_id) VALUES (?)", (user_id,))
        return {'subscription_reminder': 1, 'daily_stats_reminder': 0, 'weekly_report': 1, 'reminder_days_before': 3}

    async def update_reminder_settings(self, user_id: int, **kwargs) -> None:
        updates = [f"{k}=?" for k in kwargs]
        vals = list(kwargs.values()) + [user_id]
        await self.execute(f"UPDATE user_reminder_settings SET {', '.join(updates)} WHERE user_id=?", vals)

    # ========== دوال المسابقات ==========

    async def create_contest(self, creator_id: int, title: str, description: str, prize: str, end_date: str) -> int:
        async with self._get_connection() as conn:
            cur = await conn.execute("INSERT INTO contests (creator_id, title, description, prize, end_date, created_at) VALUES (?,?,?,?,?,?)", (creator_id, title, description, prize, end_date, TimeUtils.utc_iso()))
            await conn.commit()
            return cur.lastrowid

    async def get_active_contests(self, limit: int = 10) -> List[Dict]:
        rows = await self.fetchall("SELECT * FROM contests WHERE status='active' AND end_date > datetime('now') LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    async def join_contest(self, contest_id: int, user_id: int, answer: str = "") -> bool:
        try:
            await self.execute("INSERT INTO contest_participants (contest_id, user_id, answer, joined_at) VALUES (?,?,?,?)", (contest_id, user_id, answer, TimeUtils.utc_iso()))
            return True
        except sqlite3.IntegrityError:
            return False

    async def declare_winner(self, contest_id: int, winner_id: int) -> None:
        await self.execute("UPDATE contests SET status='closed', winner_id=? WHERE id=?", (winner_id, contest_id))
        await self.execute("INSERT INTO contest_winners (contest_id, winner_id, announced_at) VALUES (?,?,?)", (contest_id, winner_id, TimeUtils.utc_iso()))

    async def get_contest_winners(self, limit: int = 10) -> List[Dict]:
        rows = await self.fetchall("SELECT c.title, c.winner_id, cw.announced_at FROM contest_winners cw JOIN contests c ON cw.contest_id=c.id ORDER BY cw.announced_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # ========== دوال الإعدادات ==========

    async def get_setting(self, key: str, default: str = None) -> Optional[str]:
        row = await self.fetchone("SELECT value FROM settings WHERE key=?", (key,))
        return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))

    async def get_force_subscribe_channel(self) -> Optional[str]:
        return await self.get_setting('force_subscribe_channel')

    async def get_updates_channel(self) -> Optional[str]:
        return await self.get_setting('updates_channel')

    async def get_log_channel(self) -> Optional[str]:
        return await self.get_setting('log_channel_id')

    async def get_publish_interval(self) -> int:
        v = await self.get_setting('publish_interval', '720')
        return int(v) if v else 720

    async def get_auto_backup(self) -> bool:
        v = await self.get_setting('auto_backup', '1')
        return v == '1'

    # ========== دوال الباقات والاشتراكات ==========

    async def get_plan_by_name(self, name: str) -> Optional[Dict]:
        row = await self.fetchone("SELECT * FROM plans WHERE name=?", (name,))
        return dict(row) if row else None

    async def get_plan_by_id(self, plan_id: int) -> Optional[Dict]:
        row = await self.fetchone("SELECT * FROM plans WHERE id=?", (plan_id,))
        return dict(row) if row else None

    async def get_all_plans(self) -> List[Dict]:
        rows = await self.fetchall("SELECT * FROM plans WHERE is_active=1 ORDER BY price")
        return [dict(r) for r in rows]

    async def create_subscription(self, user_id: int, plan_id: int) -> None:
        plan = await self.get_plan_by_id(plan_id)
        if not plan:
            return
        end = (TimeUtils.utc_now() + timedelta(days=plan['duration_days'])).isoformat()
        await self.execute("INSERT INTO subscriptions (user_id, plan_id, start_date, end_date, created_at) VALUES (?,?,?,?,?)", (user_id, plan_id, TimeUtils.utc_iso(), end, TimeUtils.utc_iso()))
        await self.execute("UPDATE users SET subscription_end=? WHERE user_id=?", (end, user_id))

    async def get_active_subscription(self, user_id: int) -> Optional[Dict]:
        row = await self.fetchone("SELECT * FROM subscriptions WHERE user_id=? AND status='active' AND end_date > datetime('now') ORDER BY end_date DESC LIMIT 1", (user_id,))
        return dict(row) if row else None

    async def expire_expired_subscriptions(self) -> None:
        await self.execute("UPDATE subscriptions SET status='expired' WHERE status='active' AND end_date < datetime('now')")

    # ========== دوال الفواتير ==========

    async def create_invoice(self, user_id: int, plan_id: int, amount: int) -> str:
        number = f"INV-{TimeUtils.utc_now().strftime('%Y%m')}-{secrets.token_hex(4).upper()}"
        await self.execute("INSERT INTO invoices (number, user_id, plan_id, amount, created_at) VALUES (?,?,?,?,?)", (number, user_id, plan_id, amount, TimeUtils.utc_iso()))
        return number

    async def get_user_invoices(self, user_id: int, limit: int = 10) -> List[Dict]:
        rows = await self.fetchall("SELECT * FROM invoices WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, limit))
        return [dict(r) for r in rows]


# ========== إنشاء الكائن ==========
DB = Database()

async def initialize_db() -> None:
    await DB.initialize()
