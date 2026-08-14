import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from contextlib import contextmanager

from config import PATHS

logger = logging.getLogger(__name__)

# =====================================================================
# 1. إدارة قاعدة البيانات الرئيسية
# =====================================================================

class Database:
    """إدارة قاعدة البيانات SQLite"""
    _instance = None
    _db_path: Path = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._db_path is None:
            self._db_path = PATHS.DB
            self._initialize_db()
    
    @contextmanager
    def get_connection(self):
        """الحصول على اتصال بقاعدة البيانات"""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _initialize_db(self):
        """إنشاء الجداول والفهارس إذا لم تكن موجودة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # =============================================================
            # 1. إنشاء الجداول
            # =============================================================
            
            # جدول المستخدمين
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    banned INTEGER DEFAULT 0,
                    auto_publish INTEGER DEFAULT 0,
                    language TEXT DEFAULT 'ar',
                    trial_used INTEGER DEFAULT 0,
                    subscription_end TEXT,
                    referral_code TEXT UNIQUE,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # جدول القنوات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT,
                    active INTEGER DEFAULT 0,
                    banned INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # جدول المنشورات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_db_id INTEGER,
                    text TEXT,
                    media_type TEXT DEFAULT 'text',
                    media_file_id TEXT,
                    published INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    published_at TEXT,
                    FOREIGN KEY (channel_db_id) REFERENCES channels(id)
                )
            ''')
            
            # جدول المجموعات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS groups (
                    chat_id INTEGER PRIMARY KEY,
                    chat_name TEXT,
                    username TEXT,
                    banned INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # جدول مشرفي المجموعات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS group_admins (
                    chat_id INTEGER,
                    user_id INTEGER,
                    is_hidden INTEGER DEFAULT 0,
                    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, user_id),
                    FOREIGN KEY (chat_id) REFERENCES groups(chat_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # جدول مالكي المجموعات المخفيين
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS hidden_owners (
                    chat_id INTEGER,
                    owner_id INTEGER,
                    is_hidden INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, owner_id),
                    FOREIGN KEY (chat_id) REFERENCES groups(chat_id),
                    FOREIGN KEY (owner_id) REFERENCES users(user_id)
                )
            ''')
            
            # جدول إعدادات الأمان
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS security_settings (
                    chat_id INTEGER PRIMARY KEY,
                    delete_links INTEGER DEFAULT 0,
                    mentions INTEGER DEFAULT 0,
                    delete_videos INTEGER DEFAULT 0,
                    delete_audio INTEGER DEFAULT 0,
                    delete_animation INTEGER DEFAULT 0,
                    delete_voice INTEGER DEFAULT 0,
                    delete_video_note INTEGER DEFAULT 0,
                    delete_stickers INTEGER DEFAULT 0,
                    delete_documents INTEGER DEFAULT 0,
                    delete_forwarded INTEGER DEFAULT 0,
                    delete_polls INTEGER DEFAULT 0,
                    delete_games INTEGER DEFAULT 0,
                    delete_service INTEGER DEFAULT 0,
                    welcome_enabled INTEGER DEFAULT 0,
                    goodbye_enabled INTEGER DEFAULT 0,
                    slow_mode INTEGER DEFAULT 0,
                    slow_mode_seconds INTEGER DEFAULT 5,
                    max_message_length INTEGER DEFAULT 0,
                    night_mode_enabled INTEGER DEFAULT 0,
                    max_warnings INTEGER DEFAULT 3,
                    delete_penalty TEXT DEFAULT 'none',
                    auto_penalty TEXT DEFAULT 'none',
                    antiflood_enabled INTEGER DEFAULT 0,
                    warn_penalty TEXT DEFAULT 'ban',
                    welcome_text TEXT DEFAULT 'مرحباً {user} في {chat} 🤍',
                    goodbye_text TEXT DEFAULT 'وداعاً {user} 👋',
                    FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
                )
            ''')
            
            # جدول الكلمات المحظورة
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS banned_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL,
                    chat_id INTEGER,
                    added_by INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(word, chat_id),
                    FOREIGN KEY (chat_id) REFERENCES groups(chat_id),
                    FOREIGN KEY (added_by) REFERENCES users(user_id)
                )
            ''')
            
            # جدول تحذيرات المستخدمين
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_warnings (
                    user_id INTEGER,
                    chat_id INTEGER,
                    warnings INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, chat_id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
                )
            ''')
            
            # جدول سجل الإجراءات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    admin_id INTEGER,
                    action TEXT,
                    target_id INTEGER,
                    reason TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES groups(chat_id),
                    FOREIGN KEY (admin_id) REFERENCES users(user_id)
                )
            ''')
            
            # جدول الردود التلقائية
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS auto_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    keyword TEXT NOT NULL,
                    reply TEXT NOT NULL,
                    reply_type TEXT DEFAULT 'text',
                    media_id TEXT,
                    buttons TEXT,
                    usage_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(keyword, chat_id),
                    FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
                )
            ''')
            
            # جدول إعدادات الردود التلقائية
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS auto_reply_settings (
                    chat_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    only_admins INTEGER DEFAULT 0,
                    ignore_bots INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
                )
            ''')
            
            # جدول الإشتراكات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    plan_id INTEGER,
                    duration_days INTEGER,
                    start_date TEXT,
                    end_date TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # جدول الباقات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    description TEXT,
                    duration_days INTEGER,
                    price INTEGER,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # جدول التذاكر
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    ticket_number INTEGER UNIQUE,
                    content TEXT,
                    media_type TEXT,
                    media_file_id TEXT,
                    status TEXT DEFAULT 'open',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # جدول الإحالات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER,
                    referred_id INTEGER UNIQUE,
                    reward_days INTEGER DEFAULT 1,
                    claimed INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                    FOREIGN KEY (referred_id) REFERENCES users(user_id)
                )
            ''')
            
            # جدول التذكيرات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    user_id INTEGER PRIMARY KEY,
                    subscription_reminder INTEGER DEFAULT 0,
                    daily_stats_reminder INTEGER DEFAULT 0,
                    weekly_report INTEGER DEFAULT 0,
                    reminder_days_before INTEGER DEFAULT 3,
                    notification_lang TEXT DEFAULT 'ar',
                    last_reminder_sent TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # جدول المسابقات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS contests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creator_id INTEGER,
                    title TEXT,
                    description TEXT,
                    prize TEXT,
                    end_date TEXT,
                    status TEXT DEFAULT 'active',
                    winner_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (creator_id) REFERENCES users(user_id),
                    FOREIGN KEY (winner_id) REFERENCES users(user_id)
                )
            ''')
            
            # جدول مشاركات المسابقات
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS contest_participants (
                    contest_id INTEGER,
                    user_id INTEGER,
                    answer TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (contest_id, user_id),
                    FOREIGN KEY (contest_id) REFERENCES contests(id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # جدول الجدولة
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schedules (
                    channel_db_id INTEGER PRIMARY KEY,
                    schedule_type TEXT DEFAULT 'interval_minutes',
                    interval_minutes INTEGER DEFAULT 60,
                    interval_hours INTEGER DEFAULT 0,
                    interval_days INTEGER DEFAULT 0,
                    publish_time TEXT,
                    last_publish TEXT,
                    next_publish_date TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (channel_db_id) REFERENCES channels(id)
                )
            ''')
            
            # جدول الإعدادات العامة
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # =============================================================
            # 2. الفهارس (Indexes) لتحسين الأداء
            # =============================================================
            
            # فهارس المستخدمين
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_banned ON users(banned)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_language ON users(language)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_subscription ON users(subscription_end)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_updated ON users(updated_at)')
            
            # فهارس القنوات
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_channels_user ON channels(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_channels_active ON channels(active)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_channels_banned ON channels(banned)')
            
            # فهارس المنشورات
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_fail ON posts(fail_count)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)')
            
            # فهارس المجموعات
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_groups_banned ON groups(banned)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_group_admins_user ON group_admins(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_group_admins_chat ON group_admins(chat_id)')
            
            # فهارس الأمان
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_security_chat ON security_settings(chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_banned_words_chat ON banned_words(chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_banned_words_word ON banned_words(word)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_warnings_user ON user_warnings(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_warnings_chat ON user_warnings(chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_admin_logs_chat ON admin_logs(chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_admin_logs_admin ON admin_logs(admin_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_admin_logs_created ON admin_logs(created_at)')
            
            # فهارس الردود التلقائية
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_auto_replies_chat ON auto_replies(chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_auto_replies_keyword ON auto_replies(keyword)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_auto_replies_usage ON auto_replies(usage_count)')
            
            # فهارس الاشتراكات
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_end ON subscriptions(end_date)')
            
            # فهارس التذاكر
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tickets_created ON tickets(created_at)')
            
            # فهارس الإحالات
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_referrals_claimed ON referrals(claimed)')
            
            # فهارس التذكيرات
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id)')
            
            # فهارس المسابقات
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_contests_status ON contests(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_contests_end ON contests(end_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_contest_participants_contest ON contest_participants(contest_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_contest_participants_user ON contest_participants(user_id)')
            
            # فهارس الجدولة
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedules_channel ON schedules(channel_db_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_schedules_next ON schedules(next_publish_date)')
            
            # فهارس الإعدادات
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key)')
            
            conn.commit()
            logger.info("✅ تم تهيئة قاعدة البيانات والفهارس بنجاح")
    
    # =====================================================================
    # 3. عمليات المستخدمين
    # =====================================================================
    
    async def register_user(self, user_id: int, username: str = "", first_name: str = "") -> bool:
        """تسجيل مستخدم جديد"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            if cursor.fetchone():
                cursor.execute('''
                    UPDATE users 
                    SET username = ?, first_name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (username, first_name, user_id))
                conn.commit()
                return True
            
            referral_code = f"ref_{user_id}"
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, referral_code)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, referral_code))
            conn.commit()
            return True
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """الحصول على معلومات المستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    async def get_user_language(self, user_id: int) -> str:
        """الحصول على لغة المستخدم"""
        user = await self.get_user(user_id)
        return user.get('language', 'ar') if user else 'ar'
    
    async def set_user_language(self, user_id: int, lang: str) -> bool:
        """تعيين لغة المستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET language = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (lang, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    async def get_auto_publish_status(self, user_id: int) -> bool:
        """الحصول على حالة النشر التلقائي"""
        user = await self.get_user(user_id)
        return bool(user.get('auto_publish', False)) if user else False
    
    async def set_auto_publish(self, user_id: int, status: bool) -> bool:
        """تعيين حالة النشر التلقائي"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET auto_publish = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (1 if status else 0, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    async def is_user_banned(self, user_id: int) -> bool:
        """التحقق من حظر المستخدم"""
        user = await self.get_user(user_id)
        return bool(user.get('banned', False)) if user else False
    
    async def ban_user(self, user_id: int) -> bool:
        """حظر مستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET banned = 1, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    async def unban_user(self, user_id: int) -> bool:
        """إلغاء حظر مستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET banned = 0, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    async def get_all_users(self) -> List[Tuple[int, int]]:
        """الحصول على جميع المستخدمين"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, banned FROM users')
            return [(row['user_id'], row['banned']) for row in cursor.fetchall()]
    
    async def get_user_stats(self) -> Dict:
        """الحصول على إحصائيات المستخدمين"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as total FROM users')
            total = cursor.fetchone()['total']
            cursor.execute('SELECT COUNT(*) as banned FROM users WHERE banned = 1')
            banned = cursor.fetchone()['banned']
            return {'users': total, 'banned': banned}
    
    async def has_active_subscription(self, user_id: int) -> bool:
        """التحقق من وجود اشتراك نشط"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT end_date FROM subscriptions 
                WHERE user_id = ? AND status = 'active' 
                ORDER BY end_date DESC LIMIT 1
            ''', (user_id,))
            row = cursor.fetchone()
            if row:
                end_date = datetime.fromisoformat(row['end_date'])
                return end_date > datetime.utcnow()
            return False
    
    async def has_used_trial(self, user_id: int) -> bool:
        """التحقق من استخدام النسخة التجريبية"""
        user = await self.get_user(user_id)
        return bool(user.get('trial_used', False)) if user else False
    
    async def activate_trial(self, user_id: int) -> int:
        """تفعيل النسخة التجريبية"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            end_date = (datetime.utcnow() + timedelta(days=3)).isoformat()
            cursor.execute('''
                UPDATE users SET trial_used = 1, subscription_end = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (end_date, user_id))
            conn.commit()
            return 3
    
    async def get_referral_code(self, user_id: int) -> str:
        """الحصول على كود الإحالة"""
        user = await self.get_user(user_id)
        return user.get('referral_code', f"ref_{user_id}") if user else f"ref_{user_id}"
    
    async def get_user_by_referral_code(self, code: str) -> Optional[int]:
        """الحصول على مستخدم عن طريق كود الإحالة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE referral_code = ?', (code,))
            row = cursor.fetchone()
            return row['user_id'] if row else None
    
    # =====================================================================
    # 4. عمليات القنوات
    # =====================================================================
    
    async def add_channel(self, user_id: int, channel_id: str, channel_name: str) -> int:
        """إضافة قناة جديدة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id FROM channels WHERE user_id = ? AND channel_id = ?
            ''', (user_id, channel_id))
            existing = cursor.fetchone()
            if existing:
                return existing['id']
            
            cursor.execute('''
                INSERT INTO channels (user_id, channel_id, channel_name)
                VALUES (?, ?, ?)
            ''', (user_id, channel_id, channel_name))
            conn.commit()
            
            cursor.execute('''
                SELECT id FROM channels WHERE user_id = ? AND active = 1
            ''', (user_id,))
            if not cursor.fetchone():
                cursor.execute('''
                    UPDATE channels SET active = 1 WHERE id = ?
                ''', (cursor.lastrowid,))
                conn.commit()
            
            return cursor.lastrowid
    
    async def get_user_channels(self, user_id: int) -> List[Dict]:
        """الحصول على قنوات المستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, channel_id, channel_name, active, banned
                FROM channels WHERE user_id = ?
                ORDER BY created_at DESC
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    async def get_active_channel(self, user_id: int) -> Optional[int]:
        """الحصول على القناة النشطة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM channels 
                WHERE user_id = ? AND active = 1 AND banned = 0
            ''', (user_id,))
            row = cursor.fetchone()
            return row['id'] if row else None
    
    async def set_active_channel(self, user_id: int, channel_id: int) -> bool:
        """تعيين القناة النشطة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE channels SET active = 0 WHERE user_id = ?', (user_id,))
            cursor.execute('''
                UPDATE channels SET active = 1 WHERE id = ? AND user_id = ?
            ''', (channel_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    async def delete_channel(self, user_id: int, channel_id: int) -> bool:
        """حذف قناة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM channels WHERE id = ? AND user_id = ?
            ''', (channel_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    async def get_channel_info(self, channel_id: int) -> Optional[Dict]:
        """الحصول على معلومات القناة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, channel_id, channel_name, user_id, active, banned
                FROM channels WHERE id = ?
            ''', (channel_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    async def get_channel_stats(self, channel_id: int) -> Dict:
        """الحصول على إحصائيات القناة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as total FROM posts WHERE channel_db_id = ?', (channel_id,))
            total = cursor.fetchone()['total']
            cursor.execute('SELECT COUNT(*) as published FROM posts WHERE channel_db_id = ? AND published = 1', (channel_id,))
            published = cursor.fetchone()['published']
            cursor.execute('SELECT COUNT(*) as unpublished FROM posts WHERE channel_db_id = ? AND published = 0', (channel_id,))
            unpublished = cursor.fetchone()['unpublished']
            return {'total': total, 'published': published, 'unpublished': unpublished}
    
    # =====================================================================
    # 5. عمليات المنشورات
    # =====================================================================
    
    async def add_posts(self, channel_id: int, posts: List[Tuple[str, str, str]]) -> int:
        """إضافة منشورات متعددة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            count = 0
            for text, media_type, media_file_id in posts:
                cursor.execute('''
                    INSERT INTO posts (channel_db_id, text, media_type, media_file_id)
                    VALUES (?, ?, ?, ?)
                ''', (channel_id, text, media_type, media_file_id))
                count += 1
            conn.commit()
            return count
    
    async def get_unpublished_posts_count(self, channel_id: int) -> int:
        """عدد المنشورات غير المنشورة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as count FROM posts 
                WHERE channel_db_id = ? AND published = 0
            ''', (channel_id,))
            return cursor.fetchone()['count']
    
    async def get_user_unpublished_count(self, user_id: int) -> int:
        """عدد المنشورات غير المنشورة للمستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as count FROM posts p
                JOIN channels c ON p.channel_db_id = c.id
                WHERE c.user_id = ? AND p.published = 0
            ''', (user_id,))
            return cursor.fetchone()['count']
    
    async def get_user_total_posts(self, user_id: int) -> int:
        """إجمالي منشورات المستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as count FROM posts p
                JOIN channels c ON p.channel_db_id = c.id
                WHERE c.user_id = ?
            ''', (user_id,))
            return cursor.fetchone()['count']
    
    async def get_next_post(self, channel_id: int) -> Optional[Dict]:
        """الحصول على المنشور التالي للنشر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, text, media_type, media_file_id
                FROM posts 
                WHERE channel_db_id = ? AND published = 0 AND (fail_count IS NULL OR fail_count < 3)
                ORDER BY created_at ASC LIMIT 1
            ''', (channel_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    async def get_user_posts(self, channel_id: int, limit: int = 15) -> List[Dict]:
        """الحصول على منشورات المستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, text, media_type, media_file_id, published, fail_count, created_at
                FROM posts 
                WHERE channel_db_id = ?
                ORDER BY created_at DESC LIMIT ?
            ''', (channel_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    async def mark_post_published(self, post_id: int) -> bool:
        """تحديد منشور كـ منشور"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE posts SET published = 1, published_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (post_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    async def increment_post_fail(self, post_id: int) -> bool:
        """زيادة عدد محاولات الفشل"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE posts SET fail_count = COALESCE(fail_count, 0) + 1
                WHERE id = ?
            ''', (post_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    async def delete_post(self, post_id: int, user_id: int, channel_id: int) -> bool:
        """حذف منشور"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM posts 
                WHERE id = ? AND channel_db_id = ? 
                AND channel_db_id IN (SELECT id FROM channels WHERE user_id = ?)
            ''', (post_id, channel_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    async def reset_posts(self, channel_id: int) -> bool:
        """إعادة تعيين جميع المنشورات (جعلها غير منشورة)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE posts SET published = 0, published_at = NULL
                WHERE channel_db_id = ?
            ''', (channel_id,))
            conn.commit()
            return True
    
    # =====================================================================
    # 6. عمليات المجموعات
    # =====================================================================
    
    async def register_group(self, chat_id: int, chat_name: str, user_id: int, username: str = None) -> bool:
        """تسجيل مجموعة جديدة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO groups (chat_id, chat_name, username)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    chat_name = excluded.chat_name,
                    username = excluded.username
            ''', (chat_id, chat_name, username))
            
            cursor.execute('''
                INSERT OR IGNORE INTO group_admins (chat_id, user_id)
                VALUES (?, ?)
            ''', (chat_id, user_id))
            
            conn.commit()
            return True
    
    async def get_user_groups(self, user_id: int) -> List[Tuple[int, str, str, int]]:
        """الحصول على مجموعات المستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT g.chat_id, g.chat_name, g.username, g.banned
                FROM groups g
                JOIN group_admins ga ON g.chat_id = ga.chat_id
                WHERE ga.user_id = ?
                ORDER BY g.chat_name ASC
            ''', (user_id,))
            return [(row['chat_id'], row['chat_name'], row['username'] or '', row['banned']) for row in cursor.fetchall()]
    
    async def sync_group_admins(self, chat_id: int, admin_ids: List[int]) -> int:
        """مزامنة مشرفي المجموعة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM group_admins WHERE chat_id = ?', (chat_id,))
            
            count = 0
            for admin_id in admin_ids:
                cursor.execute('''
                    INSERT INTO group_admins (chat_id, user_id)
                    VALUES (?, ?)
                ''', (chat_id, admin_id))
                count += 1
            
            conn.commit()
            return count
    
    async def add_hidden_admin(self, chat_id: int, admin_id: int, added_by: int) -> bool:
        """إضافة مشرف مخفي"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO hidden_owners (chat_id, owner_id, is_hidden)
                VALUES (?, ?, 1)
            ''', (chat_id, admin_id))
            
            cursor.execute('''
                INSERT OR IGNORE INTO group_admins (chat_id, user_id, is_hidden)
                VALUES (?, ?, 1)
            ''', (chat_id, admin_id))
            
            conn.commit()
            return True
    
    async def remove_hidden_admin(self, chat_id: int, admin_id: int) -> bool:
        """إزالة مشرف مخفي"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM hidden_owners WHERE chat_id = ? AND owner_id = ?
            ''', (chat_id, admin_id))
            cursor.execute('''
                DELETE FROM group_admins WHERE chat_id = ? AND user_id = ? AND is_hidden = 1
            ''', (chat_id, admin_id))
            conn.commit()
            return True
    
    async def get_hidden_admins(self, chat_id: int) -> List[Dict]:
        """الحصول على المشرفين المخفيين"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT owner_id, created_at
                FROM hidden_owners
                WHERE chat_id = ?
                ORDER BY created_at DESC
            ''', (chat_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    # =====================================================================
    # 7. عمليات الأمان
    # =====================================================================
    
    async def get_security_settings(self, chat_id: int) -> Dict:
        """الحصول على إعدادات الأمان"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM security_settings WHERE chat_id = ?', (chat_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            cursor.execute('''
                INSERT INTO security_settings (chat_id)
                VALUES (?)
            ''', (chat_id,))
            conn.commit()
            
            cursor.execute('SELECT * FROM security_settings WHERE chat_id = ?', (chat_id,))
            return dict(cursor.fetchone())
    
    async def update_security_settings(self, chat_id: int, **kwargs) -> bool:
        """تحديث إعدادات الأمان"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
            values = list(kwargs.values()) + [chat_id]
            
            cursor.execute(f'''
                UPDATE security_settings 
                SET {set_clause}
                WHERE chat_id = ?
            ''', values)
            conn.commit()
            return cursor.rowcount > 0
    
    async def get_banned_words(self, chat_id: int) -> List[str]:
        """الحصول على الكلمات المحظورة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT word FROM banned_words WHERE chat_id = ? OR chat_id IS NULL', (chat_id,))
            return [row['word'] for row in cursor.fetchall()]
    
    async def add_banned_word(self, word: str, chat_id: int, added_by: int) -> bool:
        """إضافة كلمة محظورة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO banned_words (word, chat_id, added_by)
                    VALUES (?, ?, ?)
                ''', (word.lower(), chat_id, added_by))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    async def remove_banned_word(self, word: str, chat_id: int) -> bool:
        """حذف كلمة محظورة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM banned_words 
                WHERE word = ? AND (chat_id = ? OR chat_id IS NULL)
            ''', (word.lower(), chat_id))
            conn.commit()
            return cursor.rowcount > 0
    
    async def get_user_warnings(self, user_id: int, chat_id: int) -> int:
        """الحصول على عدد تحذيرات المستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT warnings FROM user_warnings 
                WHERE user_id = ? AND chat_id = ?
            ''', (user_id, chat_id))
            row = cursor.fetchone()
            return row['warnings'] if row else 0
    
    async def add_user_warning(self, user_id: int, chat_id: int) -> int:
        """إضافة تحذير للمستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_warnings (user_id, chat_id, warnings)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                    warnings = warnings + 1,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, chat_id))
            conn.commit()
            
            cursor.execute('''
                SELECT warnings FROM user_warnings 
                WHERE user_id = ? AND chat_id = ?
            ''', (user_id, chat_id))
            return cursor.fetchone()['warnings']
    
    async def reset_user_warnings(self, user_id: int, chat_id: int) -> bool:
        """إعادة تعيين تحذيرات المستخدم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE user_warnings SET warnings = 0, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND chat_id = ?
            ''', (user_id, chat_id))
            conn.commit()
            return cursor.rowcount > 0
    
    async def add_admin_log(self, chat_id: int, admin_id: int, action: str, target_id: int = None, reason: str = "") -> bool:
        """إضافة سجل إداري"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO admin_logs (chat_id, admin_id, action, target_id, reason)
                VALUES (?, ?, ?, ?, ?)
            ''', (chat_id, admin_id, action, target_id, reason))
            conn.commit()
            return True
    
    async def get_admin_logs(self, chat_id: int, limit: int = 20) -> List[Dict]:
        """الحصول على سجل الإجراءات الإدارية"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT admin_id, action, target_id, reason, created_at
                FROM admin_logs
                WHERE chat_id = ?
                ORDER BY id DESC LIMIT ?
            ''', (chat_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    # =====================================================================
    # 8. عمليات الردود التلقائية
    # =====================================================================
    
    async def get_auto_reply_settings(self, chat_id: int) -> Dict:
        """الحصول على إعدادات الردود التلقائية"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM auto_reply_settings WHERE chat_id = ?', (chat_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            cursor.execute('''
                INSERT INTO auto_reply_settings (chat_id)
                VALUES (?)
            ''', (chat_id,))
            conn.commit()
            
            cursor.execute('SELECT * FROM auto_reply_settings WHERE chat_id = ?', (chat_id,))
            return dict(cursor.fetchone())
    
    async def update_auto_reply_settings(self, chat_id: int, **kwargs) -> bool:
        """تحديث إعدادات الردود التلقائية"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
            values = list(kwargs.values()) + [chat_id]
            
            cursor.execute(f'''
                UPDATE auto_reply_settings 
                SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = ?
            ''', values)
            conn.commit()
            return cursor.rowcount > 0
    
    async def add_auto_reply(self, chat_id: int, keyword: str, reply: str, 
                            reply_type: str = 'text', media_id: str = None, 
                            buttons: str = None) -> bool:
        """إضافة رد تلقائي"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO auto_replies (chat_id, keyword, reply, reply_type, media_id, buttons)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (chat_id, keyword.lower(), reply, reply_type, media_id, buttons))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                cursor.execute('''
                    UPDATE auto_replies 
                    SET reply = ?, reply_type = ?, media_id = ?, buttons = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ? AND keyword = ?
                ''', (reply, reply_type, media_id, buttons, chat_id, keyword.lower()))
                conn.commit()
                return cursor.rowcount > 0
    
    async def remove_auto_reply(self, chat_id: int, keyword: str) -> bool:
        """حذف رد تلقائي"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM auto_replies 
                WHERE chat_id = ? AND keyword = ?
            ''', (chat_id, keyword.lower()))
            conn.commit()
            return cursor.rowcount > 0
    
    async def get_auto_reply(self, keyword: str, chat_id: int) -> Optional[Dict]:
        """الحصول على رد تلقائي"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT keyword, reply, reply_type, media_id, buttons
                FROM auto_replies 
                WHERE chat_id = ? AND keyword = ?
            ''', (chat_id, keyword.lower()))
            row = cursor.fetchone()
            if row:
                cursor.execute('''
                    UPDATE auto_replies SET usage_count = usage_count + 1
                    WHERE chat_id = ? AND keyword = ?
                ''', (chat_id, keyword.lower()))
                conn.commit()
                return dict(row)
            
            cursor.execute('''
                SELECT keyword, reply, reply_type, media_id, buttons
                FROM auto_replies 
                WHERE chat_id = -1 AND keyword = ?
            ''', (keyword.lower(),))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    async def get_auto_reply_stats(self, chat_id: int, limit: int = 20) -> List[Tuple[str, int]]:
        """الحصول على إحصائيات الردود التلقائية"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT keyword, usage_count
                FROM auto_replies 
                WHERE chat_id = ?
                ORDER BY usage_count DESC LIMIT ?
            ''', (chat_id, limit))
            return [(row['keyword'], row['usage_count']) for row in cursor.fetchall()]
    
    async def reset_auto_replies(self, chat_id: int) -> bool:
        """إعادة تعيين الردود التلقائية"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM auto_replies WHERE chat_id = ?', (chat_id,))
            conn.commit()
            return True
    
    # =====================================================================
    # 9. عمليات الجدولة
    # =====================================================================
    
    async def get_schedule(self, channel_id: int) -> Dict:
        """الحصول على إعدادات الجدولة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM schedules WHERE channel_db_id = ?', (channel_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            cursor.execute('''
                INSERT INTO schedules (channel_db_id, schedule_type, interval_minutes)
                VALUES (?, 'interval_minutes', 60)
            ''', (channel_id,))
            conn.commit()
            
            cursor.execute('SELECT * FROM schedules WHERE channel_db_id = ?', (channel_id,))
            return dict(cursor.fetchone())
    
    async def update_schedule(self, channel_id: int, **kwargs) -> bool:
        """تحديث إعدادات الجدولة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
            values = list(kwargs.values()) + [channel_id]
            
            cursor.execute(f'''
                UPDATE schedules 
                SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE channel_db_id = ?
            ''', values)
            conn.commit()
            return cursor.rowcount > 0
    
    async def update_next_publish(self, channel_id: int) -> bool:
        """تحديث موعد النشر التالي"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            schedule = await self.get_schedule(channel_id)
            
            next_date = datetime.utcnow()
            if schedule.get('schedule_type') == 'interval_minutes':
                minutes = schedule.get('interval_minutes', 60)
                next_date += timedelta(minutes=minutes)
            elif schedule.get('schedule_type') == 'interval_hours':
                hours = schedule.get('interval_hours', 1)
                next_date += timedelta(hours=hours)
            elif schedule.get('schedule_type') == 'interval_days':
                days = schedule.get('interval_days', 1)
                next_date += timedelta(days=days)
            else:
                next_date += timedelta(minutes=60)
            
            cursor.execute('''
                UPDATE schedules 
                SET next_publish_date = ?, updated_at = CURRENT_TIMESTAMP
                WHERE channel_db_id = ?
            ''', (next_date.isoformat(), channel_id))
            conn.commit()
            return cursor.rowcount > 0
    
    async def update_last_publish(self, channel_id: int) -> bool:
        """تحديث وقت آخر نشر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE schedules 
                SET last_publish = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE channel_db_id = ?
            ''', (channel_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    async def get_channels_to_publish(self, limit: int = 20) -> List[Dict]:
        """الحصول على القنوات التي تحتاج للنشر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.id, c.channel_id, c.user_id, u.auto_publish
                FROM channels c
                JOIN users u ON c.user_id = u.user_id
                LEFT JOIN schedules s ON c.id = s.channel_db_id
                WHERE c.banned = 0 
                AND u.banned = 0 
                AND u.auto_publish = 1
                AND (s.next_publish_date IS NULL OR s.next_publish_date <= CURRENT_TIMESTAMP)
                AND EXISTS (
                    SELECT 1 FROM posts p 
                    WHERE p.channel_db_id = c.id 
                    AND p.published = 0 
                    AND (p.fail_count IS NULL OR p.fail_count < 3)
                )
                ORDER BY COALESCE(s.next_publish_date, '1970-01-01') ASC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    # =====================================================================
    # 10. عمليات التذاكر
    # =====================================================================
    
    async def create_ticket(self, user_id: int, username: str, content: str, 
                           media_type: str = None, media_file_id: str = None) -> int:
        """إنشاء تذكرة دعم"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT COALESCE(MAX(ticket_number), 0) + 1 as next_num FROM tickets')
            next_num = cursor.fetchone()['next_num']
            
            cursor.execute('''
                INSERT INTO tickets (user_id, username, ticket_number, content, media_type, media_file_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, next_num, content, media_type, media_file_id))
            conn.commit()
            return next_num
    
    async def get_tickets(self) -> List[Dict]:
        """الحصول على جميع التذاكر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, user_id, username, ticket_number, content, status, created_at
                FROM tickets 
                WHERE status = 'open'
                ORDER BY created_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    async def close_ticket(self, ticket_id: int) -> bool:
        """إغلاق تذكرة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE tickets SET status = 'closed', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (ticket_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    async def delete_all_tickets(self) -> bool:
        """حذف جميع التذاكر"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM tickets')
            conn.commit()
            return True
    
    # =====================================================================
    # 11. عمليات الإحالات
    # =====================================================================
    
    async def add_referral(self, referrer_id: int, referred_id: int) -> bool:
        """إضافة إحالة جديدة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO referrals (referrer_id, referred_id)
                    VALUES (?, ?)
                ''', (referrer_id, referred_id))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    async def get_referral_stats(self, user_id: int) -> Dict:
        """الحصول على إحصائيات الإحالات"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as total FROM referrals WHERE referrer_id = ?
            ''', (user_id,))
            total = cursor.fetchone()['total']
            
            cursor.execute('''
                SELECT COUNT(*) as claimed FROM referrals 
                WHERE referrer_id = ? AND claimed = 1
            ''', (user_id,))
            claimed = cursor.fetchone()['claimed']
            
            available = total - claimed
            
            return {'total': total, 'claimed': claimed, 'available': available}
    
    async def claim_referral_reward(self, user_id: int) -> int:
        """صرف مكافأة الإحالات"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, reward_days FROM referrals 
                WHERE referrer_id = ? AND claimed = 0
                LIMIT 1
            ''', (user_id,))
            row = cursor.fetchone()
            
            if not row:
                return 0
            
            cursor.execute('''
                UPDATE referrals SET claimed = 1
                WHERE id = ?
            ''', (row['id'],))
            
            days = row['reward_days']
            cursor.execute('''
                UPDATE users 
                SET subscription_end = datetime(
                    COALESCE(subscription_end, CURRENT_TIMESTAMP),
                    '+' || ? || ' days'
                )
                WHERE user_id = ?
            ''', (days, user_id))
            
            conn.commit()
            return days
    
    async def get_referrals_list(self, user_id: int) -> List[int]:
        """الحصول على قائمة الإحالات"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT referred_id FROM referrals 
                WHERE referrer_id = ?
                ORDER BY created_at DESC
            ''', (user_id,))
            return [row['referred_id'] for row in cursor.fetchall()]
    
    # =====================================================================
    # 12. عمليات التذكيرات
    # =====================================================================
    
    async def get_reminder_settings(self, user_id: int) -> Dict:
        """الحصول على إعدادات التذكيرات"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM reminders WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            cursor.execute('''
                INSERT INTO reminders (user_id)
                VALUES (?)
            ''', (user_id,))
            conn.commit()
            
            cursor.execute('SELECT * FROM reminders WHERE user_id = ?', (user_id,))
            return dict(cursor.fetchone())
    
    async def update_reminder_settings(self, user_id: int, **kwargs) -> bool:
        """تحديث إعدادات التذكيرات"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
            values = list(kwargs.values()) + [user_id]
            
            cursor.execute(f'''
                UPDATE reminders 
                SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', values)
            conn.commit()
            return cursor.rowcount > 0
    
    async def get_users_for_reminder(self) -> List[Dict]:
        """الحصول على المستخدمين الذين يحتاجون تذكير"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.user_id, u.language, r.reminder_days_before,
                       julianday(subscription_end) - julianday(CURRENT_TIMESTAMP) as days_left,
                       r.last_reminder_sent
                FROM users u
                JOIN reminders r ON u.user_id = r.user_id
                WHERE r.subscription_reminder = 1
                AND u.subscription_end IS NOT NULL
                AND julianday(subscription_end) - julianday(CURRENT_TIMESTAMP) <= r.reminder_days_before
                AND julianday(subscription_end) - julianday(CURRENT_TIMESTAMP) > 0
                AND (r.last_reminder_sent IS NULL OR 
                     julianday(CURRENT_TIMESTAMP) - julianday(r.last_reminder_sent) >= 1)
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    # =====================================================================
    # 13. عمليات المسابقات
    # =====================================================================
    
    async def create_contest(self, creator_id: int, title: str, description: str, 
                            prize: str, end_date: str) -> int:
        """إنشاء مسابقة جديدة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO contests (creator_id, title, description, prize, end_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (creator_id, title, description, prize, end_date))
            conn.commit()
            return cursor.lastrowid
    
    async def get_active_contests(self, limit: int = 10) -> List[Dict]:
        """الحصول على المسابقات النشطة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.*, 
                       (SELECT COUNT(*) FROM contest_participants WHERE contest_id = c.id) as participants
                FROM contests c
                WHERE c.status = 'active' AND datetime(c.end_date) > datetime(CURRENT_TIMESTAMP)
                ORDER BY c.end_date ASC LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    async def join_contest(self, contest_id: int, user_id: int, answer: str = "") -> bool:
        """المشاركة في مسابقة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO contest_participants (contest_id, user_id, answer)
                    VALUES (?, ?, ?)
                ''', (contest_id, user_id, answer))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    async def declare_winner(self, contest_id: int, winner_id: int) -> bool:
        """إعلان الفائز في مسابقة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE contests 
                SET status = 'closed', winner_id = ?
                WHERE id = ?
            ''', (winner_id, contest_id))
            conn.commit()
            return cursor.rowcount > 0
    
    async def get_contest_winners(self, limit: int = 10) -> List[Dict]:
        """الحصول على الفائزين في المسابقات"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.title, c.winner_id, u.username, c.created_at
                FROM contests c
                JOIN users u ON c.winner_id = u.user_id
                WHERE c.status = 'closed' AND c.winner_id IS NOT NULL
                ORDER BY c.created_at DESC LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    async def delete_contest(self, contest_id: int, user_id: int) -> bool:
        """حذف مسابقة"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM contests 
                WHERE id = ? AND creator_id = ?
            ''', (contest_id, user_id))
            conn.commit()
            return cursor.rowcount > 0
    
    # =====================================================================
    # 14. عمليات الإعدادات العامة
    # =====================================================================
    
    async def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """الحصول على إعداد عام"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row['value'] if row else default
    
    async def set_setting(self, key: str, value: str) -> bool:
        """تعيين إعداد عام"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
            ''', (key, value))
            conn.commit()
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
        value = await self.get_setting('publish_interval', '60')
        try:
            return int(value)
        except:
            return 60
    
    async def get_auto_backup(self) -> bool:
        """التحقق من تفعيل النسخ الاحتياطي التلقائي"""
        value = await self.get_setting('auto_backup', 'true')
        return value.lower() == 'true'

# =====================================================================
# 15. إنشاء كائن القاعدة البيانات
# =====================================================================

db = Database()

# دالة مساعدة للوصول السريع
async def get_db():
    return db
