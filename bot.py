#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ريلاكس مانيجر - بوت متكامل لإدارة القنوات والمجموعات
الإصدار: 22.8.0 - النسخة النهائية الكاملة
"""

import os
import sys
import asyncio
import logging
import traceback
from pathlib import Path
from datetime import datetime, timedelta
import json
import random
import time
import re
import shutil
import gc
from typing import Optional, List, Dict, Any, Tuple, Awaitable
from contextlib import asynccontextmanager
from collections import defaultdict

try:
    import aiosqlite
    import httpx
    from telegram import (
        Update, InlineKeyboardButton, InlineKeyboardMarkup,
        BotCommand, ChatMember, ChatJoinRequest, PreCheckoutQuery,
        SuccessfulPayment, ChatPermissions
    )
    from telegram.ext import (
        Application, CommandHandler, MessageHandler, CallbackQueryHandler,
        ChatMemberHandler, ChatJoinRequestHandler, PreCheckoutQueryHandler,
        ContextTypes, filters
    )
    from telegram.request import HTTPXRequest
except ImportError as e:
    print(f"❌ خطأ في استيراد المكتبات: {e}")
    print("تأكد من تثبيت: pip install python-telegram-bot==22.8 aiosqlite httpx")
    sys.exit(1)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")
PRIMARY_OWNER_ID = int(os.getenv("PRIMARY_OWNER_ID", "0"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "Reelaaaxbot")

DB_PATH = Path("bot_data.db")
BACKUP_DIR = Path("backups")
LANG_DIR = Path("lang")
BACKUP_DIR.mkdir(exist_ok=True)
LANG_DIR.mkdir(exist_ok=True)

DEFAULT_PUBLISH_INTERVAL = int(os.getenv("PUBLISH_INTERVAL", "300"))
MAX_UNPUBLISHED_POSTS = int(os.getenv("MAX_UNPUBLISHED_POSTS", "50"))
MAX_CHANNELS_PER_CYCLE = int(os.getenv("MAX_CHANNELS_PER_CYCLE", "20"))
PUBLISH_RETRY_DELAY = int(os.getenv("PUBLISH_RETRY_DELAY", "300"))
AUTO_BACKUP_SLEEP = int(os.getenv("AUTO_BACKUP_SLEEP", "86400"))
MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", "10"))
SCHEDULED_POSTS_SLEEP = int(os.getenv("SCHEDULED_POSTS_SLEEP", "60"))
REMINDERS_SLEEP = int(os.getenv("REMINDERS_SLEEP", "3600"))
CLEANUP_SLEEP = int(os.getenv("CLEANUP_SLEEP", "86400"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))
MEMORY_LIMIT_PERCENT = int(os.getenv("MEMORY_LIMIT_PERCENT", "80"))
USE_PROXY = os.getenv("USE_PROXY", "false").lower() == "true"
PROXY_URL = os.getenv("PROXY_URL", "http://proxy.example.com:8080")
MAX_CONNECTIONS = int(os.getenv("MAX_CONNECTIONS", "10"))
DB_TIMEOUT = int(os.getenv("DB_TIMEOUT", "30"))

class CallbackData:
    MAIN_MENU = "main_menu"
    BACK = "back"
    CANCEL_SESSION = "cancel_session"
    CHANNELS_ADD = "channels_add"
    CHANNELS_MY = "channels_my"
    CHANNELS_DELETE_PREFIX = "channels_delete:"
    CHANNELS_SELECT_PREFIX = "channels_select:"
    POSTS_ADD_15 = "posts_add_15"
    POSTS_PUBLISH_ONE = "posts_publish_one"
    POSTS_MY = "posts_my"
    POSTS_RECYCLE = "posts_recycle"
    POSTS_DELETE_SINGLE_PREFIX = "posts_delete_single:"
    POSTS_CONFIRM_CLEAR_ALL_PREFIX = "posts_confirm_clear_all:"
    POSTS_CLEAR_ALL_PREFIX = "posts_clear_all:"
    STATS_PENDING = "stats_pending"
    STATS_FULL = "stats_full"
    GROUPS_MY = "groups_my"
    GROUPS_SETTINGS_PREFIX = "groups_settings:"
    SETTINGS_MENU = "settings_menu"
    SETTINGS_TOGGLE_AUTO_PUBLISH = "settings_toggle_auto_publish"
    SETTINGS_TOGGLE_AUTO_RECYCLE = "settings_toggle_auto_recycle"
    SCHEDULE_MENU_PREFIX = "schedule_menu:"
    SCHEDULE_SET_INTERVAL_MINUTES_PREFIX = "schedule_set_interval_minutes:"
    SCHEDULE_SET_INTERVAL_HOURS_PREFIX = "schedule_set_interval_hours:"
    SCHEDULE_SET_INTERVAL_DAYS_PREFIX = "schedule_set_interval_days:"
    SCHEDULE_SET_DAYS_PREFIX = "schedule_set_days:"
    SCHEDULE_SET_DATES_PREFIX = "schedule_set_dates:"
    SCHEDULE_SET_PUBLISH_TIME_PREFIX = "schedule_set_publish_time:"
    SCHEDULE_DAY_SELECT_PREFIX = "schedule_day_select:"
    SCHEDULE_SAVE_DAYS = "schedule_save_days"
    SECURITY_ENABLE_ALL_PREFIX = "security_enable_all:"
    SECURITY_DISABLE_ALL_PREFIX = "security_disable_all:"
    SECURITY_DELETE_PENALTY_PREFIX = "security_delete_penalty:"
    SECURITY_CLOSE = "security_close"
    SECURITY_SELECT_GROUP = "security_select_group"
    SECURITY_REFRESH_GROUPS = "security_refresh_groups"
    SECURITY_BANNED_WORDS_MENU_PREFIX = "security_banned_words_menu:"
    BANNED_WORDS_ADD_PREFIX = "banned_words_add:"
    BANNED_WORDS_LIST_PREFIX = "banned_words_list:"
    BANNED_WORDS_REMOVE_PREFIX = "banned_words_remove:"
    PENALTY_MENU = "penalty_menu"
    PENALTY_KICK = "penalty_kick"
    PENALTY_BAN = "penalty_ban"
    PENALTY_MUTE = "penalty_mute"
    GROUP_MUTE_DURATION_5 = "group_mute_duration_5"
    GROUP_MUTE_DURATION_30 = "group_mute_duration_30"
    GROUP_MUTE_DURATION_60 = "group_mute_duration_60"
    GROUP_MUTE_DURATION_720 = "group_mute_duration_720"
    GROUP_MUTE_DURATION_1440 = "group_mute_duration_1440"
    GROUP_MUTE_DURATION_10080 = "group_mute_duration_10080"
    GROUP_MUTE_DURATION_PERMANENT = "group_mute_duration_permanent"
    ADVANCED_ACTIONS = "advanced_actions"
    GROUP_ACTION_BAN = "group_action_ban"
    GROUP_ACTION_MUTE = "group_action_mute"
    GROUP_ACTION_WARN = "group_action_warn"
    GROUP_ACTION_KICK = "group_action_kick"
    GROUP_ACTION_RESTRICT = "group_action_restrict"
    GROUP_ACTION_PIN = "group_action_pin"
    GROUP_ACTION_LOG = "group_action_log"
    GROUP_ACTION_UNBAN = "group_action_unban"
    PANEL_LOCK_PREFIX = "panel_lock:"
    PANEL_UNLOCK_PREFIX = "panel_unlock:"
    PANEL_CLOSE = "panel_close"
    HELP = "help"
    SUPPORT_MENU = "support_menu"
    SUPPORT_HELP = "support_help"
    SUPPORT_TICKET = "support_ticket"
    SUPPORT_BACK = "support_back"
    TRIAL = "trial"
    SUBSCRIBE_MENU = "subscribe_menu"
    BUY_SUBSCRIPTION_1 = "buy_subscription_1"
    BUY_SUBSCRIPTION_2 = "buy_subscription_2"
    BUY_SUBSCRIPTION_30 = "buy_subscription_30"
    BUY_SUBSCRIPTION_90 = "buy_subscription_90"
    DEVELOPER = "developer"
    UPDATES = "updates"
    REFERRAL_MENU = "referral_menu"
    REFERRAL_COPY_LINK_PREFIX = "referral_copy_link:"
    REFERRAL_CLAIM_REWARD = "referral_claim_reward"
    REFERRAL_LIST = "referral_list"
    REMINDER_MENU = "reminder_menu"
    REMINDER_TOGGLE_SUB = "reminder_toggle_sub"
    REMINDER_TOGGLE_DAILY = "reminder_toggle_daily"
    REMINDER_TOGGLE_WEEKLY = "reminder_toggle_weekly"
    REMINDER_SET_DAYS = "reminder_set_days"
    REMINDER_SET_LANG = "reminder_set_lang"
    REMINDER_LANG_PREFIX = "reminder_lang:"
    TRANSLATION_MENU = "translation_menu"
    TRANSLATION_OFF = "translation_off"
    TRANSLATION_SET_PREFIX = "translation_set:"
    CONTESTS_MENU = "contests_menu"
    CONTEST_JOIN_PREFIX = "contest_join:"
    CONTEST_WINNERS = "contest_winners"
    CONTESTS_BACK = "contests_back"
    CHANNEL_STATS = "channel_stats"
    CHANNEL_GROWTH = "channel_growth"
    CHANNEL_STATS_REFRESH = "channel_stats_refresh"
    MY_CHANNEL_STATS = "my_channel_stats"
    PUBLISH_ALL_CHANNELS = "publish_all_channels"
    NSFW_SETTINGS = "nsfw_settings"
    NSFW_TOGGLE = "nsfw_toggle"
    NSFW_THRESHOLD_SET = "nsfw_threshold_set"
    CHECK_SUBSCRIBE = "check_subscribe"
    ADMIN_PANEL = "admin_panel"
    ADMIN_USERS = "admin_users"
    ADMIN_BANNED_USERS = "admin_banned_users"
    ADMIN_UNBAN_ALL_USERS = "admin_unban_all_users"
    ADMIN_ALL_CHANNELS = "admin_all_channels"
    ADMIN_BANNED_CHANNELS = "admin_banned_channels"
    ADMIN_ACTIVATE_ALL_CHANNELS = "admin_activate_all_channels"
    ADMIN_GROUPS = "admin_groups"
    ADMIN_BANNED_GROUPS = "admin_banned_groups"
    ADMIN_UNBAN_ALL_GROUPS = "admin_unban_all_groups"
    ADMIN_BOT_CHANNELS = "admin_bot_channels"
    ADMIN_BANNED_BOT_CHANNELS = "admin_banned_bot_channels"
    ADMIN_UNBAN_ALL_BOT_CHANNELS = "admin_unban_all_bot_channels"
    ADMIN_MONITOR_USERS = "admin_monitor_users"
    ADMIN_ADD_ADMIN = "admin_add_admin"
    ADMIN_REMOVE_ADMIN = "admin_remove_admin"
    ADMIN_RAM = "admin_ram"
    ADMIN_STATS = "admin_stats"
    ADMIN_METRICS = "admin_metrics"
    ADMIN_BACKUP = "admin_backup"
    ADMIN_RESTORE_BACKUP = "admin_restore_backup"
    ADMIN_RESTORE_BACKUP_SELECT_PREFIX = "admin_restore_backup_select:"
    ADMIN_BACKUP_SETTINGS = "admin_backup_settings"
    ADMIN_TOGGLE_AUTO_BACKUP = "admin_toggle_auto_backup"
    ADMIN_CHANGE_INTERVAL = "admin_change_interval"
    ADMIN_SEND_UPDATE = "admin_send_update"
    ADMIN_SET_UPDATE_CHANNEL = "admin_set_update_channel"
    ADMIN_SHOW_UPDATE_CHANNEL = "admin_show_update_channel"
    ADMIN_UPDATES = "admin_updates"
    ADMIN_FORCE_SUBSCRIBE = "admin_force_subscribe"
    ADMIN_SET_FORCE_CHANNEL = "admin_set_force_channel"
    ADMIN_BROADCAST = "admin_broadcast"
    ADMIN_CONFIRM_BROADCAST = "admin_confirm_broadcast"
    ADMIN_SUPPORT_TICKETS = "admin_support_tickets"
    ADMIN_DELETE_ALL_TICKETS = "admin_delete_all_tickets"
    ADMIN_CONFIRM_DELETE_TICKETS = "admin_confirm_delete_tickets"
    ADMIN_MANAGE_SENDCODE = "admin_manage_sendcode"
    ADMIN_SET_SENDCODE_USER = "admin_set_sendcode_user"
    ADMIN_SHOW_LOG_CHANNEL = "admin_show_log_channel"
    ADMIN_SET_LOG_CHANNEL = "admin_set_log_channel"
    ADMIN_REPLIES = "admin_replies"
    ADMIN_ADD_REPLY = "admin_add_reply"
    ADMIN_LIST_REPLIES = "admin_list_replies"
    ADMIN_DEL_REPLY = "admin_del_reply"
    ADMIN_BANNED_WORDS = "admin_banned_words"
    ADMIN_ADD_BANNED_WORD = "admin_add_banned_word"
    ADMIN_LIST_BANNED_WORDS = "admin_list_banned_words"
    ADMIN_REMOVE_BANNED_WORD = "admin_remove_banned_word"
    ADMIN_CREATE_CONTEST = "admin_create_contest"
    ADMIN_DECLARE_WINNER = "admin_declare_winner"
    ADMIN_DEL_CONTEST_PREFIX = "admin_del_contest:"
    ADMIN_AUTO_REPLY = "admin_auto_reply"
    AUTO_REPLY_MENU_PREFIX = "auto_reply_menu:"
    AUTO_REPLY_TOGGLE_PREFIX = "auto_reply_toggle:"
    AUTO_REPLY_ADMINS_PREFIX = "auto_reply_admins:"
    AUTO_REPLY_RESET_PREFIX = "auto_reply_reset:"
    AUTO_REPLY_CONFIRM_RESET_PREFIX = "auto_reply_confirm_reset:"
    AUTO_REPLY_CANCEL_PREFIX = "auto_reply_cancel:"
    AUTO_REPLY_STATS_PREFIX = "auto_reply_stats:"
    USER_AUTO_REPLY_TOGGLE_PREFIX = "user_auto_reply_toggle:"

class UserState:
    WAITING_CHANNEL_ID = 1
    ADDING_POSTS = 2
    WAITING_INTERVAL_MINUTES = 3
    WAITING_INTERVAL_HOURS = 4
    WAITING_INTERVAL_DAYS = 5
    SELECTING_DAYS = 6
    WAITING_DATES = 7
    WAITING_PUBLISH_TIME = 8
    WAITING_CRON = 9
    WAITING_BAN_USER = 10
    WAITING_MUTE_USER = 11
    WAITING_WARN_USER = 12
    WAITING_KICK_USER = 13
    WAITING_RESTRICT_USER = 14
    WAITING_PIN_MESSAGE = 15
    WAITING_UNBAN_USER = 16
    WAITING_REMINDER_DAYS = 17
    WAITING_CONTEST_ANSWER = 18
    WAITING_NSFW_THRESHOLD = 19
    WAITING_GROUP_BANNED_WORD = 20
    WAITING_REMOVE_GROUP_BANNED_WORD = 21
    WAITING_ADD_ADMIN = 22
    WAITING_REMOVE_ADMIN = 23
    WAITING_BACKUP_INTERVAL = 24
    WAITING_UPDATE_TEXT = 25
    WAITING_UPDATE_CHANNEL = 26
    WAITING_FORCE_CHANNEL = 27
    WAITING_BROADCAST_TEXT = 28
    WAITING_SENDCODE_USER = 29
    WAITING_LOG_CHANNEL = 30
    WAITING_ADD_REPLY = 31
    WAITING_DEL_REPLY = 32
    WAITING_ADD_BANNED_WORD = 33
    WAITING_REMOVE_BANNED_WORD = 34
    WAITING_CONTEST_DETAILS = 35
    WAITING_TICKET_MESSAGE = 36

SUPPORTED_LANGUAGES = {"ar": "العربية", "en": "English", "fr": "Français"}
user_language = {}
_translation_cache = {}
_admin_cache = {}
_security_cache = {}
_auth_cache = {}
_user_points_last_hour = {}
NSFW_CACHE = {}

def utc_now():
    return datetime.utcnow()
def utc_now_iso():
    return utc_now().isoformat()
def mecca_now():
    return utc_now() + timedelta(hours=3)

async def execute_db(func, *args, **kwargs):
    async with aiosqlite.connect(str(DB_PATH), timeout=DB_TIMEOUT) as conn:
        return await func(conn, *args, **kwargs)

async def init_db_improved():
    async with aiosqlite.connect(str(DB_PATH), timeout=DB_TIMEOUT) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                auto_publish INTEGER DEFAULT 1,
                banned INTEGER DEFAULT 0,
                trial_used INTEGER DEFAULT 0,
                subscription_end TEXT,
                referral_code TEXT,
                referred_by INTEGER,
                active_channel INTEGER,
                auto_reply_enabled INTEGER DEFAULT 1,
                auto_recycle INTEGER DEFAULT 1,
                last_daily_reward TEXT,
                last_weekly_reward TEXT,
                achievements TEXT DEFAULT '[]'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id TEXT,
                channel_name TEXT,
                banned INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
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
                views_count INTEGER DEFAULT 0,
                last_view_time TEXT,
                created_at TEXT,
                FOREIGN KEY(channel_db_id) REFERENCES user_channels(id)
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
                next_publish_date TEXT,
                FOREIGN KEY(channel_db_id) REFERENCES user_channels(id)
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
            CREATE TABLE IF NOT EXISTS group_admins (
                chat_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY(chat_id, user_id)
            )
        """)
        # الجدول المفقود: group_security_settings
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS group_security_settings (
                chat_id INTEGER PRIMARY KEY,
                links INTEGER DEFAULT 0,
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
                night_mode_action TEXT DEFAULT 'mute'
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
            CREATE TABLE IF NOT EXISTS group_replies (
                keyword TEXT PRIMARY KEY,
                reply TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_reply_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                only_admins INTEGER DEFAULT 0,
                ignore_bots INTEGER DEFAULT 1,
                updated_at TEXT
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
                created_at TEXT,
                replied INTEGER DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                referred_at TEXT DEFAULT CURRENT_TIMESTAMP,
                is_rewarded INTEGER DEFAULT 0,
                UNIQUE(referred_id)
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
                reminder_days_before INTEGER DEFAULT 3,
                last_reminder_sent INTEGER DEFAULT 0,
                notification_lang TEXT DEFAULT 'ar'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_translation (
                user_id INTEGER PRIMARY KEY,
                lang TEXT DEFAULT 'off'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_levels (
                user_id INTEGER PRIMARY KEY,
                points INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1
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
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS moderation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                action TEXT,
                duration_minutes INTEGER,
                moderator_id INTEGER,
                reason TEXT,
                created_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_warnings (
                user_id INTEGER,
                chat_id INTEGER,
                warnings INTEGER DEFAULT 0,
                PRIMARY KEY(user_id, chat_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS allowed_sendcode_user (
                id INTEGER PRIMARY KEY,
                user_id INTEGER
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
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                chat_id INTEGER,
                user_id INTEGER,
                details TEXT,
                severity TEXT DEFAULT 'info',
                created_at TEXT NOT NULL
            )
        """)
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('publish_interval', ?)", 
                          (str(DEFAULT_PUBLISH_INTERVAL),))
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_backup', '0')")
        await conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('backup_interval', ?)", 
                          (str(AUTO_BACKUP_SLEEP),))
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_channel ON posts(channel_db_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_security_events_type ON security_events(event_type)")
        await conn.commit()
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح (بما في ذلك group_security_settings)")

async def db_create_user(user_id: int):
    async def _create(conn):
        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await conn.execute("INSERT OR IGNORE INTO user_reminder_settings (user_id) VALUES (?)", (user_id,))
        await conn.execute("INSERT OR IGNORE INTO user_translation (user_id) VALUES (?)", (user_id,))
        await conn.execute("INSERT OR IGNORE INTO user_levels (user_id) VALUES (?)", (user_id,))
        await conn.commit()
    return await execute_db(_create)

async def db_get_all_users():
    async def _get(conn):
        cur = await conn.execute("SELECT user_id FROM users ORDER BY user_id")
        return [row[0] for row in await cur.fetchall()]
    return await execute_db(_get)

async def db_get_banned_users():
    async def _get(conn):
        cur = await conn.execute("SELECT user_id FROM users WHERE banned = 1")
        return [row[0] for row in await cur.fetchall()]
    return await execute_db(_get)

async def db_unban_all_users():
    async def _unban(conn):
        await conn.execute("UPDATE users SET banned = 0")
        await conn.commit()
    return await execute_db(_unban)

async def db_get_channels(user_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT id, channel_id, channel_name, banned FROM user_channels WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_get_channel_info(ch_db_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT channel_id, channel_name FROM user_channels WHERE id = ?", (ch_db_id,))
        return await cur.fetchone()
    return await execute_db(_get)

async def db_add_channel(user_id: int, channel_id: str, channel_name: str = None):
    if not channel_name:
        channel_name = channel_id
    async def _add(conn):
        cur = await conn.execute(
            "INSERT INTO user_channels (user_id, channel_id, channel_name, created_at) VALUES (?, ?, ?, ?)",
            (user_id, channel_id, channel_name, utc_now_iso())
        )
        ch_id = cur.lastrowid
        await conn.execute("INSERT OR IGNORE INTO schedule (channel_db_id) VALUES (?)", (ch_id,))
        await conn.commit()
        return ch_id
    return await execute_db(_add)

async def db_delete_channel_by_id(user_id: int, ch_db_id: int):
    async def _delete(conn):
        await conn.execute("DELETE FROM posts WHERE channel_db_id = ?", (ch_db_id,))
        await conn.execute("DELETE FROM schedule WHERE channel_db_id = ?", (ch_db_id,))
        await conn.execute("DELETE FROM user_channels WHERE id = ? AND user_id = ?", (ch_db_id, user_id))
        await conn.commit()
        return True
    return await execute_db(_delete)

async def db_set_active_channel(user_id: int, ch_db_id: int):
    async def _set(conn):
        await conn.execute("UPDATE users SET active_channel = ? WHERE user_id = ?", (ch_db_id, user_id))
        await conn.commit()
    return await execute_db(_set)

async def db_get_active_channel(user_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT active_channel FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None
    return await execute_db(_get)

async def db_add_post(ch_db_id: int, text: str, media_type: str = "text", media_file_id: str = None):
    async def _add(conn):
        cur = await conn.execute(
            "INSERT INTO posts (channel_db_id, text, media_type, media_file_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (ch_db_id, text, media_type, media_file_id, utc_now_iso())
        )
        await conn.commit()
        return cur.lastrowid
    return await execute_db(_add)

async def db_get_next_post(ch_db_id: int):
    async def _get(conn):
        cur = await conn.execute(
            "SELECT id, text, media_type, media_file_id FROM posts WHERE channel_db_id = ? AND published = 0 ORDER BY id ASC LIMIT 1",
            (ch_db_id,)
        )
        row = await cur.fetchone()
        if row:
            return {"id": row[0], "text": row[1], "media_type": row[2], "media_file_id": row[3]}
        return None
    return await execute_db(_get)

async def db_mark_published(post_id: int):
    async def _mark(conn):
        await conn.execute("UPDATE posts SET published = 1, last_view_time = ? WHERE id = ?", (utc_now_iso(), post_id))
        await conn.commit()
    return await execute_db(_mark)

async def db_get_posts_count(ch_db_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id = ?", (ch_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_get_published_count(ch_db_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id = ? AND published = 1", (ch_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_unpublished_count(ch_db_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM posts WHERE channel_db_id = ? AND published = 0", (ch_db_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_get_user_posts_for_channel(ch_db_id: int, limit: int = 15):
    async def _get(conn):
        cur = await conn.execute("SELECT id, text, media_type FROM posts WHERE channel_db_id = ? ORDER BY id DESC LIMIT ?", (ch_db_id, limit))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_delete_single_post(post_id: int, user_id: int, ch_db_id: int) -> bool:
    async def _delete(conn):
        cur = await conn.execute("SELECT user_id FROM user_channels WHERE id = ?", (ch_db_id,))
        row = await cur.fetchone()
        if not row or row[0] != user_id:
            return False
        await conn.execute("DELETE FROM posts WHERE id = ? AND channel_db_id = ?", (post_id, ch_db_id))
        await conn.commit()
        return True
    return await execute_db(_delete)

async def db_reset_posts_to_unpublished(ch_db_id: int, user_id: int):
    async def _reset(conn):
        await conn.execute("UPDATE posts SET published = 0 WHERE channel_db_id = ?", (ch_db_id,))
        await conn.commit()
    return await execute_db(_reset)

async def db_reset_all_posts_to_unpublished(ch_db_id: int):
    async def _reset(conn):
        await conn.execute("UPDATE posts SET published = 0 WHERE channel_db_id = ?", (ch_db_id,))
        await conn.commit()
    return await execute_db(_reset)

async def db_get_user_unpublished_posts(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("""
            SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id = uc.id WHERE uc.user_id = ? AND p.published = 0
        """, (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_get_user_total_posts(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("""
            SELECT COUNT(*) FROM posts p JOIN user_channels uc ON p.channel_db_id = uc.id WHERE uc.user_id = ?
        """, (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_get_schedule(ch_db_id: int):
    async def _get(conn):
        cur = await conn.execute(
            "SELECT schedule_type, interval_minutes, interval_hours, interval_days, days_of_week, specific_dates, publish_time, cron_expression, next_publish_date FROM schedule WHERE channel_db_id = ?",
            (ch_db_id,)
        )
        row = await cur.fetchone()
        if row:
            return {"type": row[0], "interval_minutes": row[1], "interval_hours": row[2], "interval_days": row[3], 
                    "days_of_week": row[4], "specific_dates": row[5], "publish_time": row[6], "cron_expression": row[7], 
                    "next_publish_date": row[8]}
        return {"type": "interval_minutes", "interval_minutes": 12, "interval_hours": 0, "interval_days": 0,
                "days_of_week": "[]", "specific_dates": "[]", "publish_time": "00:00", "cron_expression": None, "next_publish_date": None}
    return await execute_db(_get)

async def db_save_schedule(ch_db_id: int, schedule_type: str, **kwargs):
    async def _save(conn):
        fields = ["schedule_type = ?"]
        values = [schedule_type]
        if schedule_type == "interval_minutes":
            fields.append("interval_minutes = ?"); values.append(kwargs.get("interval_minutes", 12))
        elif schedule_type == "interval_hours":
            fields.append("interval_hours = ?"); values.append(kwargs.get("interval_hours", 1))
        elif schedule_type == "interval_days":
            fields.append("interval_days = ?"); values.append(kwargs.get("interval_days", 1))
        elif schedule_type == "days":
            fields.append("days_of_week = ?"); values.append(kwargs.get("days_of_week", "[]"))
        elif schedule_type == "dates":
            fields.append("specific_dates = ?"); values.append(kwargs.get("specific_dates", "[]"))
        elif schedule_type == "cron":
            fields.append("cron_expression = ?"); values.append(kwargs.get("cron_expression", "0 12 * * *"))
        fields.append("publish_time = ?"); values.append(kwargs.get("publish_time", "00:00"))
        values.append(ch_db_id)
        query = f"UPDATE schedule SET {', '.join(fields)} WHERE channel_db_id = ?"
        await conn.execute(query, values)
        await conn.commit()
    return await execute_db(_save)

async def db_set_next_publish_date(ch_db_id: int, next_date: datetime):
    async def _set(conn):
        await conn.execute("UPDATE schedule SET next_publish_date = ? WHERE channel_db_id = ?", 
                          (next_date.isoformat() if next_date else None, ch_db_id))
        await conn.commit()
    return await execute_db(_set)

async def db_update_next_publish_date(ch_db_id: int):
    schedule = await db_get_schedule(ch_db_id)
    schedule_type = schedule['type']
    now = utc_now()
    next_date = None
    if schedule_type == "interval_minutes":
        next_date = now + timedelta(minutes=schedule.get('interval_minutes', 12))
    elif schedule_type == "interval_hours":
        next_date = now + timedelta(hours=schedule.get('interval_hours', 1))
    elif schedule_type == "interval_days":
        next_date = now + timedelta(days=schedule.get('interval_days', 1))
    else:
        next_date = now + timedelta(minutes=12)
    await db_set_next_publish_date(ch_db_id, next_date)

async def db_auto_status(user_id: int) -> bool:
    async def _get(conn):
        cur = await conn.execute("SELECT auto_publish FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_get)

async def db_set_auto(user_id: int, status: bool):
    async def _set(conn):
        await conn.execute("UPDATE users SET auto_publish = ? WHERE user_id = ?", (1 if status else 0, user_id))
        await conn.commit()
    return await execute_db(_set)

async def db_get_auto_recycle(user_id: int) -> bool:
    async def _get(conn):
        cur = await conn.execute("SELECT auto_recycle FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_get)

async def db_set_auto_recycle(user_id: int, status: bool):
    async def _set(conn):
        await conn.execute("UPDATE users SET auto_recycle = ? WHERE user_id = ?", (1 if status else 0, user_id))
        await conn.commit()
    return await execute_db(_set)

async def db_get_publish_interval_seconds() -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT value FROM settings WHERE key = 'publish_interval'")
        row = await cur.fetchone()
        return int(row[0]) if row else DEFAULT_PUBLISH_INTERVAL
    return await execute_db(_get)

async def db_set_last_publish(ch_db_id: int, publish_time: datetime):
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO last_publish (channel_db_id, last_publish_time) VALUES (?, ?)",
                          (ch_db_id, publish_time.isoformat()))
        await conn.commit()
    return await execute_db(_set)

async def db_add_group(chat_id: int, chat_name: str, username: str = None, added_by: int = None):
    async def _add(conn):
        await conn.execute("INSERT OR REPLACE INTO bot_groups (chat_id, chat_name, username, added_by, added_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                          (chat_id, chat_name, username, added_by, utc_now_iso(), utc_now_iso()))
        await conn.commit()
    return await execute_db(_add)

async def db_get_user_groups(user_id: int):
    async def _get(conn):
        cur = await conn.execute("""
            SELECT bg.chat_id, bg.chat_name, bg.username, bg.banned
            FROM bot_groups bg JOIN user_groups_link ugl ON bg.chat_id = ugl.chat_id
            WHERE ugl.user_id = ? ORDER BY bg.chat_name
        """, (user_id,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_get_user_groups_count(user_id: int) -> int:
    async def _get(conn):
        cur = await conn.execute("SELECT COUNT(*) FROM user_groups_link WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else 0
    return await execute_db(_get)

async def db_get_security_settings(chat_id: int, force_refresh: bool = False) -> dict:
    if not force_refresh and chat_id in _security_cache:
        return _security_cache[chat_id]
    async def _get(conn):
        cur = await conn.execute("SELECT * FROM group_security_settings WHERE chat_id = ?", (chat_id,))
        row = await cur.fetchone()
        if row:
            columns = [desc[0] for desc in cur.description]
            result = dict(zip(columns, row))
            _security_cache[chat_id] = result
            return result
        defaults = {
            'chat_id': chat_id,
            'links': 0, 'mentions': 0, 'slow_mode': 0, 'slow_mode_seconds': 5,
            'welcome_enabled': 0, 'welcome_text': 'مرحباً {user} في {chat} 🤍',
            'goodbye_enabled': 0, 'goodbye_text': 'وداعاً {user} 👋',
            'delete_banned_words': 0, 'auto_penalty': 'none', 'auto_mute_duration': 60,
            'delete_videos': 0, 'delete_audio': 0, 'delete_animation': 0,
            'delete_service': 0, 'delete_documents': 0, 'delete_stickers': 0,
            'delete_forwarded': 0, 'delete_polls': 0, 'delete_games': 0,
            'delete_voice': 0, 'delete_video_note': 0,
            'delete_penalty': 'none', 'delete_penalty_duration': 0,
            'antiflood_enabled': 0, 'antiflood_messages': 5, 'antiflood_seconds': 10,
            'antiflood_penalty': 'mute', 'max_warnings': 3, 'warn_penalty': 'ban',
            'max_message_length': 0, 'night_mode_enabled': 0,
            'night_mode_start': '23:00', 'night_mode_end': '06:00', 'night_mode_action': 'mute'
        }
        columns = ', '.join(defaults.keys())
        placeholders = ', '.join(['?' for _ in defaults])
        await conn.execute(
            f"INSERT OR IGNORE INTO group_security_settings ({columns}) VALUES ({placeholders})",
            tuple(defaults.values())
        )
        await conn.commit()
        _security_cache[chat_id] = defaults
        return defaults
    return await execute_db(_get)

async def db_set_security_settings(chat_id: int, **kwargs):
    async def _update(conn):
        await conn.execute("INSERT OR IGNORE INTO group_security_settings (chat_id) VALUES (?)", (chat_id,))
        if kwargs:
            set_parts = [f"{key} = ?" for key in kwargs.keys()]
            values = list(kwargs.values()) + [chat_id]
            await conn.execute(
                f"UPDATE group_security_settings SET {', '.join(set_parts)} WHERE chat_id = ?",
                tuple(values)
            )
            await conn.commit()
            logger.info(f"✅ تم تحديث: {kwargs} للمجموعة {chat_id}")
            if chat_id in _security_cache:
                _security_cache[chat_id].update(kwargs)
    return await execute_db(_update)

async def db_set_security_setting(chat_id: int, key: str, value):
    await db_set_security_settings(chat_id, **{key: 1 if value else 0})

async def db_set_chat_lock(chat_id: int, locked: bool, locked_by: int = None):
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?, ?, ?, ?)",
                          (chat_id, 1 if locked else 0, utc_now_iso() if locked else None, locked_by if locked else None))
        await conn.commit()
    return await execute_db(_set)

async def is_chat_locked(chat_id: int) -> bool:
    async def _check(conn):
        cur = await conn.execute("SELECT locked FROM chat_locks WHERE chat_id = ?", (chat_id,))
        row = await cur.fetchone()
        return row and row[0] == 1
    return await execute_db(_check)

async def db_get_banned_words(chat_id: int):
    async def _get(conn):
        cur = await conn.execute("SELECT word, added_by, added_at FROM banned_words WHERE chat_id = ? OR chat_id = -1 ORDER BY word", (chat_id,))
        return await cur.fetchall()
    return await execute_db(_get)

async def db_add_banned_word(chat_id: int, word: str, added_by: int):
    async def _add(conn):
        try:
            await conn.execute("INSERT INTO banned_words (word, chat_id, added_by, added_at) VALUES (?, ?, ?, ?)",
                              (word.lower(), chat_id, added_by, utc_now_iso()))
            await conn.commit()
            return True
        except:
            return False
    return await execute_db(_add)

async def db_remove_banned_word(chat_id: int, word: str):
    async def _remove(conn):
        await conn.execute("DELETE FROM banned_words WHERE word = ? AND (chat_id = ? OR chat_id = -1)", (word.lower(), chat_id))
        await conn.commit()
    return await execute_db(_remove)

async def db_get_global_banned_words():
    async def _get(conn):
        cur = await conn.execute("SELECT word FROM banned_words WHERE chat_id = -1 ORDER BY word")
        return [row[0] for row in await cur.fetchall()]
    return await execute_db(_get)

async def db_get_all_groups():
    async def _get(conn):
        cur = await conn.execute("SELECT chat_id, chat_name, username, banned FROM bot_groups ORDER BY chat_name")
        rows = await cur.fetchall()
        return [{"id": r[0], "name": r[1], "username": r[2], "banned": r[3]} for r in rows]
    return await execute_db(_get)

async def db_get_all_channels():
    async def _get(conn):
        cur = await conn.execute("SELECT id, channel_id, channel_name, user_id FROM user_channels WHERE banned = 0")
        rows = await cur.fetchall()
        return [{"id": r[0], "channel_id": r[1], "name": r[2], "user_id": r[3]} for r in rows]
    return await execute_db(_get)

async def db_stats():
    async def _get(conn):
        total = (await conn.execute("SELECT COUNT(*) FROM users")).fetchone()[0]
        banned = (await conn.execute("SELECT COUNT(*) FROM users WHERE banned = 1")).fetchone()[0]
        posts = (await conn.execute("SELECT COUNT(*) FROM posts")).fetchone()[0]
        groups = (await conn.execute("SELECT COUNT(*) FROM bot_groups")).fetchone()[0]
        channels = (await conn.execute("SELECT COUNT(*) FROM user_channels")).fetchone()[0]
        return total, banned, posts, groups, channels
    return await execute_db(_get)

async def is_authorized_in_group(bot, chat_id: int, user_id: int) -> bool:
    cache_key = f"{chat_id}_{user_id}"
    if cache_key in _auth_cache:
        return _auth_cache[cache_key]
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        is_admin = member.status in ['administrator', 'creator']
        _auth_cache[cache_key] = is_admin
        return is_admin
    except:
        return False

def invalidate_auth_cache(chat_id: int, user_id: int = None):
    if user_id:
        cache_key = f"{chat_id}_{user_id}"
        if cache_key in _auth_cache:
            del _auth_cache[cache_key]
    else:
        keys = [k for k in _auth_cache if k.startswith(f"{chat_id}_")]
        for k in keys:
            del _auth_cache[k]

async def is_bot_admin(user_id: int) -> bool:
    if user_id == PRIMARY_OWNER_ID:
        return True
    async def _check(conn):
        cur = await conn.execute("SELECT 1 FROM bot_admins WHERE user_id = ?", (user_id,))
        return await cur.fetchone() is not None
    return await execute_db(_check)

async def is_currently_admin_in_group(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def db_sync_group_admins(chat_id: int, bot):
    try:
        admins = await bot.get_chat_administrators(chat_id)
        async def _sync(conn):
            await conn.execute("DELETE FROM group_admins WHERE chat_id = ?", (chat_id,))
            for admin in admins:
                await conn.execute("INSERT OR IGNORE INTO group_admins (chat_id, user_id) VALUES (?, ?)", (chat_id, admin.user.id))
            await conn.commit()
        await execute_db(_sync)
        return True
    except:
        return False

def load_all_languages():
    global _language_cache
    _language_cache = {}
    if not LANG_DIR.exists():
        LANG_DIR.mkdir(exist_ok=True)
    for lang_file in LANG_DIR.glob("*.json"):
        lang_code = lang_file.stem
        try:
            with open(lang_file, 'r', encoding='utf-8') as f:
                _language_cache[lang_code] = json.load(f)
        except:
            _language_cache[lang_code] = {}

def get_text(user_id: int, key: str, **kwargs) -> str:
    lang = user_language.get(user_id, 'ar')
    texts = _language_cache.get(lang, {})
    if key in texts:
        text = texts[key]
    else:
        ar_texts = _language_cache.get('ar', {})
        text = ar_texts.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except:
            pass
    return text

async def set_user_language(user_id: int, lang_code: str):
    if lang_code in SUPPORTED_LANGUAGES:
        user_language[user_id] = lang_code
        return True
    return False

async def get_user_translation_language(user_id: int) -> str:
    async def _get(conn):
        cur = await conn.execute("SELECT lang FROM user_translation WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else "off"
    return await execute_db(_get)

async def set_user_translation_language(user_id: int, lang: str):
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO user_translation (user_id, lang) VALUES (?, ?)", (user_id, lang))
        await conn.commit()
    return await execute_db(_set)

async def translate_text(text: str, target_lang: str) -> str:
    if target_lang == 'off' or not text:
        return text
    cache_key = f"{text[:100]}_{target_lang}"
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]
    try:
        if target_lang == 'en':
            result = f"[EN] {text}"
        elif target_lang == 'fr':
            result = f"[FR] {text}"
        else:
            result = text
        _translation_cache[cache_key] = result
        return result
    except:
        return text

_banned_patterns = None

async def rebuild_banned_patterns():
    global _banned_patterns
    words = await db_get_global_banned_words()
    if words:
        pattern = r'\b(' + '|'.join(re.escape(w) for w in words) + r')\b'
        _banned_patterns = re.compile(pattern, re.IGNORECASE)
    else:
        _banned_patterns = None

def contains_banned_word(text: str) -> bool:
    if not _banned_patterns or not text:
        return False
    return bool(_banned_patterns.search(text))

def load_banned_words_from_file(filepath: str) -> List[str]:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return [line.strip().lower() for line in f if line.strip()]
    except:
        return []

def get_ram_usage():
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {"total": mem.total // (1024**2), "used": mem.used // (1024**2), 
                "free": mem.free // (1024**2), "percent": mem.percent}
    except:
        return {"total": 0, "used": 0, "free": 0, "percent": 0}

async def safe_send_markdown(bot, chat_id: int, text: str, **kwargs):
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", **kwargs)
    except:
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=None, **kwargs)
        except Exception as e:
            logger.error(f"فشل إرسال الرسالة: {e}")

async def safe_edit_markdown(query, text: str, **kwargs):
    try:
        await query.edit_message_text(text=text, parse_mode="Markdown", **kwargs)
    except:
        try:
            await query.edit_message_text(text=text, parse_mode=None, **kwargs)
        except Exception as e:
            logger.error(f"فشل تعديل الرسالة: {e}")

def parse_days_of_week_safe(days_json: str) -> List[int]:
    try:
        return json.loads(days_json)
    except:
        return []

def parse_dates_safe(dates_json: str) -> List[str]:
    try:
        return json.loads(dates_json)
    except:
        return []

async def get_main_keyboard(user_id: int):
    channels = await db_get_channels(user_id)
    active = await db_get_active_channel(user_id)
    keyboard = []
    if active:
        ch_info = await db_get_channel_info(active)
        if ch_info:
            ch_name = ch_info[1] or ch_info[0]
            keyboard.append([InlineKeyboardButton(f"📡 {ch_name} (نشطة)", callback_data=f"{CallbackData.CHANNELS_SELECT_PREFIX}{active}")])
    keyboard.append([InlineKeyboardButton("📢 قنواتي", callback_data=CallbackData.CHANNELS_MY)])
    keyboard.append([InlineKeyboardButton("➕ إضافة 15 منشور", callback_data=CallbackData.POSTS_ADD_15),
                     InlineKeyboardButton("📤 نشر واحد", callback_data=CallbackData.POSTS_PUBLISH_ONE)])
    keyboard.append([InlineKeyboardButton("📝 منشوراتي", callback_data=CallbackData.POSTS_MY),
                     InlineKeyboardButton("♻️ إعادة تدوير", callback_data=CallbackData.POSTS_RECYCLE)])
    keyboard.append([InlineKeyboardButton("📊 معلقة", callback_data=CallbackData.STATS_PENDING),
                     InlineKeyboardButton("📈 كاملة", callback_data=CallbackData.STATS_FULL)])
    keyboard.append([InlineKeyboardButton("👥 مجموعاتي", callback_data=CallbackData.GROUPS_MY),
                     InlineKeyboardButton("⚙️ إعدادات", callback_data=CallbackData.SETTINGS_MENU)])
    keyboard.append([InlineKeyboardButton("📊 إحصائيات قنواتي", callback_data=CallbackData.MY_CHANNEL_STATS),
                     InlineKeyboardButton("📤 نشر الكل", callback_data=CallbackData.PUBLISH_ALL_CHANNELS)])
    keyboard.append([InlineKeyboardButton("🔄 الإحالات", callback_data=CallbackData.REFERRAL_MENU),
                     InlineKeyboardButton("⏰ تذكيرات", callback_data=CallbackData.REMINDER_MENU)])
    keyboard.append([InlineKeyboardButton("🌐 ترجمة", callback_data=CallbackData.TRANSLATION_MENU),
                     InlineKeyboardButton("🏆 مسابقات", callback_data=CallbackData.CONTESTS_MENU)])
    keyboard.append([InlineKeyboardButton("❓ مساعدة", callback_data=CallbackData.HELP),
                     InlineKeyboardButton("💬 دعم", callback_data=CallbackData.SUPPORT_MENU)])
    if await is_bot_admin(user_id) or user_id == PRIMARY_OWNER_ID:
        keyboard.append([InlineKeyboardButton("🛠️ لوحة الأدمن", callback_data=CallbackData.ADMIN_PANEL)])
    title = "🌿 **مرحباً بك في ريلاكس مانيجر**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإجراء المناسب:"
    return InlineKeyboardMarkup(keyboard), title, active

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu_callback(update, context)

async def cancel_session_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    context.user_data.pop(f"session_{user_id}", None)
    context.user_data.pop(f"session_target_{user_id}", None)
    context.user_data.pop('state', None)
    if query:
        await query.edit_message_text("✅ تم الإلغاء.")
    else:
        await safe_send_markdown(context.bot, user_id, "✅ تم الإلغاء.")
    await main_menu_callback(update, context)

async def add_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_CHANNEL_ID
    msg = "📢 أرسل معرف القناة (مثال: @my_channel أو -100123456789)"
    if query:
        await query.edit_message_text(msg)
    else:
        await safe_send_markdown(context.bot, user_id, msg)

async def my_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels:
        msg = "📭 لا توجد قنوات مسجلة."
        if query:
            await query.edit_message_text(msg)
        else:
            await safe_send_markdown(context.bot, user_id, msg)
        return
    kb = []
    for ch in channels:
        ch_db_id, ch_tele_id, ch_name, banned = ch
        display = ch_name if ch_name != ch_tele_id else ch_tele_id
        kb.append([
            InlineKeyboardButton(f"📢 {display}", callback_data=f"{CallbackData.CHANNELS_SELECT_PREFIX}{ch_db_id}"),
            InlineKeyboardButton("📊 إحصائيات", callback_data=f"{CallbackData.CHANNEL_STATS}:{ch_db_id}"),
            InlineKeyboardButton("🗑️ حذف", callback_data=f"{CallbackData.CHANNELS_DELETE_PREFIX}{ch_db_id}")
        ])
    kb.append([InlineKeyboardButton("➕ إضافة قناة", callback_data=CallbackData.CHANNELS_ADD)])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    if query:
        await query.edit_message_text("📢 **قنواتي**", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await safe_send_markdown(context.bot, user_id, "📢 **قنواتي**", reply_markup=InlineKeyboardMarkup(kb))

async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1]) if query else context.user_data.get('delete_channel_id')
    if not ch_db_id:
        return
    if await db_delete_channel_by_id(user_id, ch_db_id):
        if query:
            await query.edit_message_text("✅ تم حذف القناة.")
        else:
            await safe_send_markdown(context.bot, user_id, "✅ تم حذف القناة.")
        await my_channels_callback(update, context)
    else:
        if query:
            await query.answer("❌ فشل الحذف", show_alert=True)
        else:
            await safe_send_markdown(context.bot, user_id, "❌ فشل الحذف")

async def select_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    await db_set_active_channel(user_id, ch_db_id)
    context.user_data['active_channel'] = ch_db_id
    await main_menu_callback(update, context)

async def add_15_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
        await query.edit_message_text("⚠️ اشتراكك منتهٍ، استخدم /trial أو /subscribe")
        return
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    unpublished_count = await db_unpublished_count(active)
    if unpublished_count >= MAX_UNPUBLISHED_POSTS:
        if query:
            await query.edit_message_text(f"⚠️ لقد تجاوزت الحد الأقصى للمنشورات غير المنشورة ({MAX_UNPUBLISHED_POSTS}).")
        else:
            await safe_send_markdown(context.bot, user_id, f"⚠️ لقد تجاوزت الحد الأقصى للمنشورات غير المنشورة ({MAX_UNPUBLISHED_POSTS}).")
        return
    context.user_data[f"session_{user_id}"] = []
    context.user_data[f"session_target_{user_id}"] = min(15, MAX_UNPUBLISHED_POSTS - unpublished_count)
    context.user_data['state'] = UserState.ADDING_POSTS
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data=CallbackData.CANCEL_SESSION)]])
    msg = f"📥 أرسل المنشورات (نصوص أو صور أو فيديوهات أو مستندات)\nالحد الأقصى المسموح: {MAX_UNPUBLISHED_POSTS - unpublished_count} منشور"
    if query:
        await query.edit_message_text(msg, reply_markup=cancel_kb)
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=cancel_kb)

async def publish_one_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
        await query.edit_message_text("⚠️ اشتراكك منتهٍ، استخدم /trial أو /subscribe")
        return
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    post = await db_get_next_post(active)
    if not post:
        if query:
            await query.edit_message_text("📭 لا توجد منشورات غير منشورة.")
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد منشورات غير منشورة.")
        return
    ch_info = await db_get_channel_info(active)
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
            await context.bot.send_photo(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'video' and post['media_file_id']:
            await context.bot.send_video(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'document' and post['media_file_id']:
            await context.bot.send_document(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'audio' and post['media_file_id']:
            await context.bot.send_audio(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'voice' and post['media_file_id']:
            await context.bot.send_voice(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        elif post['media_type'] == 'animation' and post['media_file_id']:
            await context.bot.send_animation(ch_info[0], post['media_file_id'], caption=final_text if final_text else None)
        else:
            await context.bot.send_message(ch_info[0], final_text, parse_mode=None)
        await db_mark_published(post['id'])
        await db_set_last_publish(active, utc_now())
        await db_update_next_publish_date(active)
        if query:
            await query.edit_message_text("✅ تم نشر المنشور بنجاح!")
        else:
            await safe_send_markdown(context.bot, user_id, "✅ تم نشر المنشور بنجاح!")
    except Exception as e:
        logger.error(f"خطأ في النشر: {e}")
        if query:
            await query.edit_message_text(f"❌ فشل النشر: {str(e)[:200]}")
        else:
            await safe_send_markdown(context.bot, user_id, f"❌ فشل النشر: {str(e)[:200]}")
    await main_menu_callback(update, context)

async def my_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    posts = await db_get_user_posts_for_channel(active, limit=15)
    if not posts:
        if query:
            await query.edit_message_text("📭 لا توجد منشورات.")
        else:
            await safe_send_markdown(context.bot, user_id, "📭 لا توجد منشورات.")
        return
    msg = "📝 **منشوراتي**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    kb_buttons = []
    for idx, (pid, ptext, media_type) in enumerate(posts[:10], 1):
        short = re.sub('<[^>]+>', '', ptext)[:80]
        media_icon = "🖼️" if media_type == 'photo' else "🎬" if media_type == 'video' else "📝" if media_type == 'text' else "📄"
        msg += f"{idx}. {media_icon} {short}...\n🆔 {pid}\n\n"
        kb_buttons.append([InlineKeyboardButton(f"🗑️ حذف #{pid}", callback_data=f"{CallbackData.POSTS_DELETE_SINGLE_PREFIX}{pid}_{active}")])
    kb_buttons.append([InlineKeyboardButton("🗑️ حذف الكل", callback_data=f"{CallbackData.POSTS_CONFIRM_CLEAR_ALL_PREFIX}{active}")])
    kb_buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    if query:
        await safe_edit_markdown(query, msg, reply_markup=InlineKeyboardMarkup(kb_buttons))
    else:
        await safe_send_markdown(context.bot, user_id, msg, reply_markup=InlineKeyboardMarkup(kb_buttons))

async def delete_single_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")[-1].split("_") if query else context.user_data.get('delete_post_data', '').split("_")
    if len(parts) >= 2:
        post_id = int(parts[0])
        active = int(parts[1])
        if await db_delete_single_post(post_id, user_id, active):
            if query:
                await query.answer("✅ تم حذف المنشور", show_alert=True)
            else:
                await safe_send_markdown(context.bot, user_id, "✅ تم حذف المنشور")
            await my_posts_callback(update, context)
        else:
            if query:
                await query.answer("❌ فشل الحذف", show_alert=True)
            else:
                await safe_send_markdown(context.bot, user_id, "❌ فشل الحذف")

async def confirm_clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = int(query.data.split(":")[-1]) if query else context.user_data.get('clear_all_posts_id')
    if not active:
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ نعم", callback_data=f"{CallbackData.POSTS_CLEAR_ALL_PREFIX}{active}"),
                               InlineKeyboardButton("❌ لا", callback_data=CallbackData.BACK)]])
    if query:
        await query.edit_message_text("⚠️ هل أنت متأكد من حذف جميع المنشورات؟", reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, "⚠️ هل أنت متأكد من حذف جميع المنشورات؟", reply_markup=kb)

async def clear_all_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = int(query.data.split(":")[-1]) if query else context.user_data.get('clear_all_posts_id')
    if not active:
        return
    async def _clear_posts(conn):
        await conn.execute("DELETE FROM posts WHERE channel_db_id=?", (active,))
        await conn.commit()
    await execute_db(_clear_posts)
    if query:
        await query.answer("✅ تم حذف جميع المنشورات", show_alert=True)
    else:
        await safe_send_markdown(context.bot, user_id, "✅ تم حذف جميع المنشورات")
    await main_menu_callback(update, context)

async def recycle_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if active:
        await db_reset_posts_to_unpublished(active, user_id)
        if query:
            await query.edit_message_text("♻️ تم إعادة تدوير المنشورات.")
        else:
            await safe_send_markdown(context.bot, user_id, "♻️ تم إعادة تدوير المنشورات.")
    else:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
    await main_menu_callback(update, context)

async def pending_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    unpublished = await db_get_user_unpublished_posts(user_id)
    total = await db_get_user_total_posts(user_id)
    text = f"📊 **إحصائيات المنشورات**\n━━━━━━━━━━━━━━━━━━━━━━\n⏳ غير منشورة: {unpublished}\n📝 إجمالي: {total}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]])
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def full_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    channels = len(await db_get_channels(user_id))
    total = await db_get_user_total_posts(user_id)
    unpublished = await db_get_user_unpublished_posts(user_id)
    groups = await db_get_user_groups_count(user_id)
    auto = "مفعل" if await db_auto_status(user_id) else "معطل"
    text = f"📊 **الإحصائيات الكاملة**\n━━━━━━━━━━━━━━━━━━━━━━\n📡 القنوات: {channels}\n📝 إجمالي المنشورات: {total}\n⏳ غير منشورة: {unpublished}\n👥 المجموعات: {groups}\n⚙️ النشر التلقائي: {auto}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]])
    if query:
        await safe_edit_markdown(query, text, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=kb)

async def my_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
        msg = "📭 لا توجد مجموعات مسجلة\n\nأضف البوت إلى مجموعة وستظهر هنا."
        if query:
            try:
                await safe_edit_markdown(query, msg, reply_markup=kb)
            except:
                await query.edit_message_text(msg, reply_markup=kb)
        else:
            await safe_send_markdown(context.bot, uid, msg, reply_markup=kb)
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
    text = "👥 **مجموعاتي**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر مجموعة للتحكم بها:\n\n✅ = نشطة  |  ⛔ = محظورة"
    if query:
        try:
            await safe_edit_markdown(query, text, reply_markup=reply_markup)
        except:
            try:
                await query.edit_message_text(text, reply_markup=reply_markup)
            except:
                pass
    else:
        await safe_send_markdown(context.bot, uid, text, reply_markup=reply_markup)

async def delete_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('delete_group_id')
    if not chat_id:
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        if query:
            await query.answer("❌ غير مصرح", show_alert=True)
        else:
            await safe_send_markdown(context.bot, uid, "❌ غير مصرح")
        return
    async def _delete_group(conn):
        await conn.execute("DELETE FROM bot_groups WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM user_groups_link WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM group_security_settings WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM chat_locks WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM moderation_log WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM group_admins WHERE chat_id = ?", (chat_id,))
        await conn.execute("DELETE FROM group_rules WHERE chat_id = ?", (chat_id,))
        await conn.commit()
    await execute_db(_delete_group)
    invalidate_auth_cache(chat_id)
    if query:
        await query.edit_message_text("✅ تم حذف المجموعة.")
    else:
        await safe_send_markdown(context.bot, uid, "✅ تم حذف المجموعة.")
    await my_groups_callback(update, context)

async def group_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except:
            pass
    uid = update.effective_user.id
    chat_id = None
    try:
        if query and query.data:
            try:
                chat_id = int(query.data.split(":")[-1])
            except (ValueError, IndexError):
                await query.edit_message_text("❌ بيانات غير صالحة")
                return
        else:
            chat_id = context.user_data.get('group_chat_id')
        if not chat_id:
            if query:
                await query.edit_message_text("❌ لم يتم تحديد المجموعة")
            else:
                await safe_send_markdown(context.bot, uid, "❌ لم يتم تحديد المجموعة")
            return
        if not await is_authorized_in_group(context.bot, chat_id, uid):
            if query:
                await query.edit_message_text("⚠️ يجب أن تكون مشرفاً")
            else:
                await safe_send_markdown(context.bot, uid, "⚠️ يجب أن تكون مشرفاً")
            return
        await _update_security_panel(query, chat_id, uid)
    except Exception as e:
        logger.error(f"خطأ في group_settings: {e}")
        try:
            if query:
                await query.edit_message_text(f"❌ حدث خطأ: {str(e)[:200]}")
        except:
            pass

async def _update_security_panel(query, chat_id, user_id):
    try:
        settings = await db_get_security_settings(chat_id, force_refresh=True)
        text = _build_security_text(settings)
        keyboard = _build_security_keyboard(chat_id)
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.delete()
        except:
            pass
        await query.message.chat.send_message(text=text, reply_markup=reply_markup, parse_mode="HTML")
        logger.info(f"✅ تم تحديث لوحة الأمان للمجموعة {chat_id}")
    except Exception as e:
        logger.error(f"خطأ في _update_security_panel: {e}")

def _build_security_text(settings):
    def st(val):
        return "✅" if val else "❌"
    lines = ["🔐 إعدادات الأمان للمجموعة", "━━━━━━━━━━━━━━━━━━━━━━"]
    items = [
        ("🔗 الروابط", settings.get('links')),
        ("@ المعرفات", settings.get('mentions')),
        ("⏱️ البطيء", settings.get('slow_mode'), f" ({settings.get('slow_mode_seconds', 5)}ث)" if settings.get('slow_mode') else ""),
        ("🎯 الترحيب", settings.get('welcome_enabled')),
        ("👋 الوداع", settings.get('goodbye_enabled')),
        ("🎬 فيديوهات", settings.get('delete_videos')),
        ("🎵 صوتيات", settings.get('delete_audio')),
        ("🎞️ متحركات", settings.get('delete_animation')),
        ("🛠️ الخدمة", settings.get('delete_service')),
        ("📄 ملفات", settings.get('delete_documents')),
        ("🖼️ ملصقات", settings.get('delete_stickers')),
        ("📨 المُعاد", settings.get('delete_forwarded')),
        ("📊 استطلاعات", settings.get('delete_polls')),
        ("🎮 ألعاب", settings.get('delete_games')),
        ("🎤 صوتيات", settings.get('delete_voice')),
        ("🎥 فيديو نوت", settings.get('delete_video_note')),
        ("🌊 مضاد الفيضان", settings.get('antiflood_enabled')),
        ("🌙 ليلي", settings.get('night_mode_enabled')),
    ]
    for item in items:
        name, value, *extra = item
        extra_text = extra[0] if extra else ""
        lines.append(f"{name}: {st(value)}{extra_text}")
    max_len = settings.get('max_message_length', 0)
    length_str = str(max_len) if max_len else "غير محدود"
    penalty = settings.get('delete_penalty', 'لا شيء')
    lines.append(f"📏 الطول: {length_str}")
    lines.append(f"⚖️ العقوبة: {penalty}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📌 اختر الإعداد:")
    return "\n".join(lines)

def _build_security_keyboard(chat_id):
    return [
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

async def security_toggle_setting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await query.answer("⚠️ يجب أن تكون مشرفاً", show_alert=True)
        return
    settings = await db_get_security_settings(chat_id, force_refresh=True)
    current = settings.get(action, False)
    new_value = not current
    await db_set_security_settings(chat_id, **{action: 1 if new_value else 0})
    await _update_security_panel(query, chat_id, user_id)

async def security_enable_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('security_chat_id')
    if not chat_id or not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ غير مصرح", show_alert=True)
        return
    keys = ['delete_videos', 'delete_audio', 'delete_animation', 'delete_service', 'delete_documents', 'delete_stickers']
    for key in keys:
        await db_set_security_settings(chat_id, **{key: 1})
    await query.answer("✅ تم تفعيل الكل")
    await _update_security_panel(query, chat_id, user_id)

async def security_disable_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('security_chat_id')
    if not chat_id or not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ غير مصرح", show_alert=True)
        return
    keys = ['delete_videos', 'delete_audio', 'delete_animation', 'delete_service', 'delete_documents', 'delete_stickers']
    for key in keys:
        await db_set_security_settings(chat_id, **{key: 0})
    await query.answer("✅ تم تعطيل الكل")
    await _update_security_panel(query, chat_id, user_id)

async def security_delete_penalty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('security_chat_id')
    if not chat_id or not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ غير مصرح", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 طرد", callback_data=f"set_delete_penalty:kick:{chat_id}"),
         InlineKeyboardButton("🛑 حظر", callback_data=f"set_delete_penalty:ban:{chat_id}")],
        [InlineKeyboardButton("🔇 كتم", callback_data=f"set_delete_penalty:mute:{chat_id}"),
         InlineKeyboardButton("⚠️ تحذير", callback_data=f"set_delete_penalty:warn:{chat_id}")],
        [InlineKeyboardButton("❌ لا شيء", callback_data=f"set_delete_penalty:none:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])
    await query.edit_message_text("⚖️ **اختر عقوبة الحذف التلقائي**", reply_markup=keyboard)

async def set_delete_penalty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    parts = query.data.split(":")
    if len(parts) == 3:
        penalty = parts[1]
        chat_id = int(parts[2])
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("⚠️ غير مصرح", show_alert=True)
            return
        await db_set_security_settings(chat_id, delete_penalty=penalty)
        await query.answer(f"✅ تم تعيين عقوبة الحذف: {penalty}")
        await _update_security_panel(query, chat_id, user_id)

async def security_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.delete()

async def security_select_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    if query:
        await query.answer()
    if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
        groups = await db_get_user_groups(user_id)
        if not groups:
            if query:
                await query.edit_message_text("📭 لا توجد مجموعات مسجلة.")
            else:
                await safe_send_markdown(context.bot, user_id, "📭 لا توجد مجموعات مسجلة.")
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
        keyboard.append([InlineKeyboardButton(f"{status_icon} {display_name}", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")])
    if not keyboard:
        if query:
            await query.edit_message_text("🔒 لا توجد مجموعات لديك صلاحية عليها.")
        else:
            await safe_send_markdown(context.bot, user_id, "🔒 لا توجد مجموعات لديك صلاحية عليها.")
        return
    keyboard.append([InlineKeyboardButton("🔄 تحديث", callback_data=CallbackData.SECURITY_REFRESH_GROUPS), 
                     InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    if query:
        await query.edit_message_text("🔐 **اختر مجموعة لإعدادات الأمان:**", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_send_markdown(context.bot, user_id, "🔐 **اختر مجموعة لإعدادات الأمان:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def security_refresh_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await security_select_group_callback(update, context)

async def penalty_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('penalty_chat_id')
    if not chat_id:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ يجب أن تكون مشرفاً", show_alert=True)
        return
    context.user_data['penalty_chat_id'] = chat_id
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👢 طرد", callback_data=f"{CallbackData.PENALTY_KICK}:{chat_id}"),
         InlineKeyboardButton("🛑 حظر", callback_data=f"{CallbackData.PENALTY_BAN}:{chat_id}")],
        [InlineKeyboardButton("🔇 كتم", callback_data=f"{CallbackData.PENALTY_MUTE}:{chat_id}"),
         InlineKeyboardButton("⚠️ تحذير", callback_data=f"penalty:warn:{chat_id}")],
        [InlineKeyboardButton("❌ لا شيء", callback_data=f"penalty:none:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])
    await query.edit_message_text("⚖️ **اختر العقوبة التلقائية**", reply_markup=keyboard)

async def penalty_kick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('penalty_chat_id')
    if not chat_id:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ غير مصرح", show_alert=True)
        return
    await db_set_security_settings(chat_id, auto_penalty='kick')
    await query.answer("✅ تم تعيين عقوبة الطرد")
    await group_settings_callback(update, context)

async def penalty_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('penalty_chat_id')
    if not chat_id:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ غير مصرح", show_alert=True)
        return
    await db_set_security_settings(chat_id, auto_penalty='ban')
    await query.answer("✅ تم تعيين عقوبة الحظر")
    await group_settings_callback(update, context)

async def penalty_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('penalty_chat_id')
    if not chat_id:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ غير مصرح", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("5 دقائق", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_5}:{chat_id}"),
         InlineKeyboardButton("30 دقيقة", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_30}:{chat_id}")],
        [InlineKeyboardButton("ساعة", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_60}:{chat_id}"),
         InlineKeyboardButton("12 ساعة", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_720}:{chat_id}")],
        [InlineKeyboardButton("يوم", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_1440}:{chat_id}"),
         InlineKeyboardButton("7 أيام", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_10080}:{chat_id}")],
        [InlineKeyboardButton("دائم", callback_data=f"{CallbackData.GROUP_MUTE_DURATION_PERMANENT}:{chat_id}"),
         InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.PENALTY_MENU}:{chat_id}")]
    ])
    await query.edit_message_text("🔇 **اختر مدة الكتم**", reply_markup=keyboard)

async def penalty_mute_duration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data
    duration_map = {
        CallbackData.GROUP_MUTE_DURATION_5: 5,
        CallbackData.GROUP_MUTE_DURATION_30: 30,
        CallbackData.GROUP_MUTE_DURATION_60: 60,
        CallbackData.GROUP_MUTE_DURATION_720: 720,
        CallbackData.GROUP_MUTE_DURATION_1440: 1440,
        CallbackData.GROUP_MUTE_DURATION_10080: 10080,
        CallbackData.GROUP_MUTE_DURATION_PERMANENT: -1
    }
    duration = duration_map.get(data.split(":")[0], 60)
    chat_id = int(data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ غير مصرح", show_alert=True)
        return
    await db_set_security_settings(chat_id, auto_penalty='mute', auto_mute_duration=duration)
    duration_text = "دائم" if duration == -1 else f"{duration} دقيقة"
    await query.answer(f"✅ تم تعيين مدة الكتم: {duration_text}")
    await group_settings_callback(update, context)

async def advanced_actions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('advanced_chat_id')
    if chat_id == 0:
        if query:
            await query.edit_message_text("⚠️ يرجى اختيار مجموعة أولاً")
        else:
            await safe_send_markdown(context.bot, uid, "⚠️ يرجى اختيار مجموعة أولاً")
        return
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        if query:
            await query.answer("⚠️ يجب أن تكون مشرفاً", show_alert=True)
        else:
            await safe_send_markdown(context.bot, uid, "⚠️ يجب أن تكون مشرفاً")
        return
    keyboard = [
        [InlineKeyboardButton("🚫 حظر", callback_data=f"{CallbackData.GROUP_ACTION_BAN}:{chat_id}"),
         InlineKeyboardButton("🔇 كتم", callback_data=f"{CallbackData.GROUP_ACTION_MUTE}:{chat_id}")],
        [InlineKeyboardButton("⚠️ تحذير", callback_data=f"{CallbackData.GROUP_ACTION_WARN}:{chat_id}"),
         InlineKeyboardButton("👢 طرد", callback_data=f"{CallbackData.GROUP_ACTION_KICK}:{chat_id}")],
        [InlineKeyboardButton("🔒 تقييد", callback_data=f"{CallbackData.GROUP_ACTION_RESTRICT}:{chat_id}"),
         InlineKeyboardButton("📌 تثبيت", callback_data=f"{CallbackData.GROUP_ACTION_PIN}:{chat_id}")],
        [InlineKeyboardButton("📜 سجل", callback_data=f"{CallbackData.GROUP_ACTION_LOG}:{chat_id}"),
         InlineKeyboardButton("🔓 إلغاء حظر", callback_data=f"{CallbackData.GROUP_ACTION_UNBAN}:{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ]
    msg = "🛠️ **الإجراءات المتقدمة للمجموعة**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإجراء المطلوب:"
    if query:
        await safe_edit_markdown(query, msg, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_send_markdown(context.bot, uid, msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def settings_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    auto_status = await db_auto_status(user_id)
    auto_recycle = await db_get_auto_recycle(user_id)
    auto_text = "مفعل" if auto_status else "معطل"
    recycle_text = "مفعل" if auto_recycle else "معطل"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⚙️ النشر التلقائي: {auto_text}", callback_data=CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH)],
        [InlineKeyboardButton(f"♻️ إعادة تدوير تلقائي: {recycle_text}", callback_data=CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    text = "⚙️ **الإعدادات**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإعداد المطلوب:"
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def toggle_auto_publish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    current = await db_auto_status(user_id)
    new_status = not current
    await db_set_auto(user_id, new_status)
    if query:
        await safe_edit_markdown(query, f"✅ تم {'تفعيل' if new_status else 'تعطيل'} النشر التلقائي.")
    else:
        await safe_send_markdown(context.bot, user_id, f"✅ تم {'تفعيل' if new_status else 'تعطيل'} النشر التلقائي.")
    await settings_menu_callback(update, context)

async def toggle_auto_recycle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    current = await db_get_auto_recycle(user_id)
    new_status = not current
    await db_set_auto_recycle(user_id, new_status)
    if query:
        await safe_edit_markdown(query, f"✅ تم {'تفعيل' if new_status else 'تعطيل'} إعادة التدوير التلقائي.")
    else:
        await safe_send_markdown(context.bot, user_id, f"✅ تم {'تفعيل' if new_status else 'تعطيل'} إعادة التدوير التلقائي.")
    await settings_menu_callback(update, context)

async def schedule_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1]) if query else context.user_data.get('schedule_ch_id')
    if not ch_db_id:
        ch_db_id = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not ch_db_id:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    schedule = await db_get_schedule(ch_db_id)
    context.user_data['schedule_ch_id'] = ch_db_id
    schedule_type = schedule['type']
    schedule_info = ""
    if schedule_type == "interval_minutes":
        schedule_info = f"كل {schedule['interval_minutes']} دقيقة"
    elif schedule_type == "interval_hours":
        schedule_info = f"كل {schedule['interval_hours']} ساعة"
    elif schedule_type == "interval_days":
        schedule_info = f"كل {schedule['interval_days']} يوم"
    elif schedule_type == "days":
        days = parse_days_of_week_safe(schedule['days_of_week'])
        day_names = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت']
        days_str = ', '.join([day_names[d] for d in days]) if days else 'لا شيء'
        schedule_info = f"أيام: {days_str}"
    elif schedule_type == "dates":
        dates = parse_dates_safe(schedule['specific_dates'])
        dates_str = ', '.join(dates) if dates else 'لا شيء'
        schedule_info = f"تواريخ: {dates_str}"
    elif schedule_type == "cron":
        schedule_info = f"CRON: {schedule['cron_expression']}"
    else:
        schedule_info = 'لا شيء'
    keyboard = [
        [InlineKeyboardButton("⏱️ دقائق", callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_MINUTES_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton("⏱️ ساعات", callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_HOURS_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton("⏱️ أيام", callback_data=f"{CallbackData.SCHEDULE_SET_INTERVAL_DAYS_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton("📅 أيام الأسبوع", callback_data=f"{CallbackData.SCHEDULE_SET_DAYS_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton("📅 تواريخ محددة", callback_data=f"{CallbackData.SCHEDULE_SET_DATES_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton("🕐 وقت النشر", callback_data=f"{CallbackData.SCHEDULE_SET_PUBLISH_TIME_PREFIX}{ch_db_id}")],
        [InlineKeyboardButton("⏰ CRON", callback_data=f"schedule:set_cron:{ch_db_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ]
    text = f"⚙️ **إعدادات الجدولة**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 الجدول الحالي: {schedule_info}\n\nاختر نوع الجدولة:"
    if query:
        await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def set_interval_minutes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_INTERVAL_MINUTES
    context.user_data['schedule_ch_id'] = ch_db_id
    await query.edit_message_text("⏱️ أرسل عدد الدقائق (مثال: 30)")

async def set_interval_hours_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_INTERVAL_HOURS
    context.user_data['schedule_ch_id'] = ch_db_id
    await query.edit_message_text("⏱️ أرسل عدد الساعات (مثال: 2)")

async def set_interval_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_INTERVAL_DAYS
    context.user_data['schedule_ch_id'] = ch_db_id
    await query.edit_message_text("⏱️ أرسل عدد الأيام (مثال: 3)")

async def set_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    context.user_data['selected_days'] = []
    context.user_data['schedule_ch_id'] = ch_db_id
    context.user_data['state'] = UserState.SELECTING_DAYS
    keyboard = await build_days_keyboard(user_id, context)
    await query.edit_message_text("📅 اختر أيام النشر:", reply_markup=keyboard)

async def set_dates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_DATES
    context.user_data['schedule_ch_id'] = ch_db_id
    await query.edit_message_text("📅 أرسل التواريخ المطلوبة (YYYY-MM-DD) مفصولة بفواصل:\nمثال: 2025-01-01, 2025-01-15")

async def set_publish_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_PUBLISH_TIME
    context.user_data['schedule_ch_id'] = ch_db_id
    await query.edit_message_text("🕐 أرسل وقت النشر (HH:MM):\nمثال: 14:30")

async def set_cron_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = int(query.data.split(":")[-1])
    context.user_data['state'] = UserState.WAITING_CRON
    context.user_data['schedule_ch_id'] = ch_db_id
    await query.edit_message_text("⏰ أرسل تعبير CRON (مثال: 0 12 * * 1)")

async def day_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ch_db_id = context.user_data.get('schedule_ch_id')
    if not ch_db_id:
        return
    selected = context.user_data.get('selected_days', [])
    await db_save_schedule(ch_db_id, 'days', days_of_week=json.dumps(selected))
    await db_set_next_publish_date(ch_db_id, None)
    context.user_data.pop('selected_days', None)
    context.user_data.pop('state', None)
    await query.edit_message_text("✅ تم حفظ الأيام")
    await schedule_menu_callback(update, context)

async def build_days_keyboard(uid, context):
    selected = context.user_data.get('selected_days', [])
    day_names = ['الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
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
    kb_buttons.append([InlineKeyboardButton("✔️ حفظ", callback_data=CallbackData.SCHEDULE_SAVE_DAYS), 
                       InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    return InlineKeyboardMarkup(kb_buttons)

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    text = f"""❓ **المساعدة**
━━━━━━━━━━━━━━━━━━━━━━

📌 **الأوامر الأساسية:**
• /start - بدء البوت
• /trial - تجربة مجانية
• /subscribe - الاشتراك
• /help - هذه الرسالة

📌 **إدارة القنوات:**
• أضف قناة من القائمة الرئيسية
• أضف منشورات وانشرها

📌 **إدارة المجموعات:**
• /syncgroup - تفعيل المجموعة
• /security - إعدادات الأمان

📌 **الإجراءات:**
• /ban - حظر مستخدم
• /mute - كتم مستخدم
• /warn - تحذير مستخدم

🔗 للمزيد: @{BOT_USERNAME}"""
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def support_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    text = "💬 **مركز الدعم**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإجراء:"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 إنشاء تذكرة", callback_data=CallbackData.SUPPORT_TICKET)],
        [InlineKeyboardButton("❓ الأسئلة الشائعة", callback_data=CallbackData.SUPPORT_HELP)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def support_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    text = f"""❓ **الأسئلة الشائعة**
━━━━━━━━━━━━━━━━━━━━━━

❓ كيف أضيف قناة؟
• استخدم /start ثم اختر "إضافة قناة"
• أرسل معرف القناة (مثال: @my_channel)

❓ كيف أنشر منشوراً؟
• أضف القناة أولاً
• اختر "إضافة 15 منشور"
• أرسل المنشورات المطلوبة

❓ كيف أضبط النشر التلقائي؟
• اذهب إلى الإعدادات
• فعّل "النشر التلقائي"

🔗 للمزيد: @{BOT_USERNAME}"""
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.SUPPORT_MENU)]])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def support_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_TICKET_MESSAGE
    await query.edit_message_text("✏️ أرسل رسالتك وسيتم إنشاء تذكرة دعم.")

async def support_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu_callback(update, context)

async def referral_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    ref_code = await db_get_referral_code(user_id)
    if not ref_code:
        ref_code = await db_generate_referral_code(user_id)
    stats = await db_get_referral_stats(user_id)
    settings = await db_get_referral_settings()
    reward_per_ref = int(settings.get('reward_days_per_referral', '3'))
    text = f"🔄 **الإحالات**\n━━━━━━━━━━━━━━━━━━━━━━\n🔗 كود الإحالة: `{ref_code}`\n📊 إجمالي المحالين: {stats['total_referrals']}\n🎁 أيام متاحة: {stats['available_days']}\n💎 مكافأة كل إحالة: {reward_per_ref} يوم"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 نسخ الرابط", callback_data=f"{CallbackData.REFERRAL_COPY_LINK_PREFIX}{ref_code}")],
        [InlineKeyboardButton("🎁 مطالبة المكافأة", callback_data=CallbackData.REFERRAL_CLAIM_REWARD)],
        [InlineKeyboardButton("📋 قائمة المحالين", callback_data=CallbackData.REFERRAL_LIST)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def referral_copy_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    ref_code = query.data.split(":")[-1]
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{ref_code}"
    await query.edit_message_text(f"🔗 **رابط الإحالة:**\n\n`{link}`\n\nانسخه وشاركه مع أصدقائك.")
    await referral_menu_callback(update, context)

async def referral_claim_reward_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    days = await db_claim_referral_reward(user_id)
    if days > 0:
        await query.edit_message_text(f"✅ تمت المطالبة! تم إضافة {days} يوم اشتراك.")
    else:
        await query.edit_message_text("❌ لا توجد مكافآت متاحة.")
    await referral_menu_callback(update, context)

async def referral_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    async def _get_referrals(conn):
        cur = await conn.execute("SELECT referred_id, referred_at FROM referrals WHERE referrer_id=? ORDER BY referred_at DESC LIMIT 20", (user_id,))
        return await cur.fetchall()
    referrals = await execute_db(_get_referrals)
    if not referrals:
        await query.edit_message_text("📭 لا يوجد محالين.")
        await referral_menu_callback(update, context)
        return
    text = "📋 **قائمة المحالين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for ref_id, ref_at in referrals:
        try:
            user = await context.bot.get_chat(ref_id)
            name = user.first_name or str(ref_id)
        except:
            name = str(ref_id)
        text += f"• {name} (`{ref_id}`) - {ref_at[:10]}\n"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.REFERRAL_MENU)]])
    await query.edit_message_text(text, reply_markup=keyboard)

async def reminder_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    settings = await db_get_user_reminder_settings(user_id)
    sub_status = "✅ مفعل" if settings['subscription_reminder'] else "❌ معطل"
    daily_status = "✅ مفعل" if settings['daily_stats_reminder'] else "❌ معطل"
    weekly_status = "✅ مفعل" if settings['weekly_report'] else "❌ معطل"
    days_before = settings['reminder_days_before']
    lang = settings['notification_lang']
    lang_name = SUPPORTED_LANGUAGES.get(lang, 'العربية')
    text = f"⏰ **التذكيرات**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 تذكير الاشتراك: {sub_status}\n📌 تذكير يومي: {daily_status}\n📌 تقرير أسبوعي: {weekly_status}\n⏱️ أيام قبل الانتهاء: {days_before}\n🌐 لغة الإشعارات: {lang_name}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 تبديل تذكير الاشتراك", callback_data=CallbackData.REMINDER_TOGGLE_SUB)],
        [InlineKeyboardButton("🔄 تبديل التذكير اليومي", callback_data=CallbackData.REMINDER_TOGGLE_DAILY)],
        [InlineKeyboardButton("🔄 تبديل التقرير الأسبوعي", callback_data=CallbackData.REMINDER_TOGGLE_WEEKLY)],
        [InlineKeyboardButton("⏱️ تعيين أيام التذكير", callback_data=CallbackData.REMINDER_SET_DAYS)],
        [InlineKeyboardButton("🌐 تعيين لغة الإشعارات", callback_data=CallbackData.REMINDER_SET_LANG)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def reminder_toggle_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    settings = await db_get_user_reminder_settings(user_id)
    new_status = not settings['subscription_reminder']
    await db_update_reminder_settings(user_id, subscription_reminder=new_status)
    await reminder_menu_callback(update, context)

async def reminder_toggle_daily_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    settings = await db_get_user_reminder_settings(user_id)
    new_status = not settings['daily_stats_reminder']
    await db_update_reminder_settings(user_id, daily_stats_reminder=new_status)
    await reminder_menu_callback(update, context)

async def reminder_toggle_weekly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    settings = await db_get_user_reminder_settings(user_id)
    new_status = not settings['weekly_report']
    await db_update_reminder_settings(user_id, weekly_report=new_status)
    await reminder_menu_callback(update, context)

async def reminder_set_days_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    context.user_data['state'] = UserState.WAITING_REMINDER_DAYS
    await query.edit_message_text("⏰ أرسل عدد الأيام قبل انتهاء الاشتراك (1-10):")

async def reminder_set_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇸🇦 العربية", callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}ar"),
         InlineKeyboardButton("🇬🇧 English", callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}en")],
        [InlineKeyboardButton("🇫🇷 Français", callback_data=f"{CallbackData.REMINDER_LANG_PREFIX}fr"),
         InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.REMINDER_MENU)]
    ])
    await query.edit_message_text("🌐 اختر لغة الإشعارات:", reply_markup=keyboard)

async def reminder_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    lang = query.data.split(":")[-1]
    await db_update_reminder_settings(user_id, notification_lang=lang)
    await reminder_menu_callback(update, context)

async def translation_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    current = await get_user_translation_language(user_id)
    text = f"🌐 **إعدادات الترجمة**\n━━━━━━━━━━━━━━━━━━━━━━\n📌 اللغة الحالية: {SUPPORTED_LANGUAGES.get(current, 'معطلة')}\n\nاختر لغة الترجمة:"
    keyboard = []
    for code, name in SUPPORTED_LANGUAGES.items():
        if code == current:
            name = f"✅ {name}"
        keyboard.append([InlineKeyboardButton(name, callback_data=f"{CallbackData.TRANSLATION_SET_PREFIX}{code}")])
    keyboard.append([InlineKeyboardButton("🚫 إيقاف الترجمة", callback_data=CallbackData.TRANSLATION_OFF)])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)])
    if query:
        await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def translation_off_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    await set_user_translation_language(user_id, 'off')
    await query.edit_message_text("✅ تم إيقاف الترجمة.")
    await translation_menu_callback(update, context)

async def translation_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    lang = query.data.split(":")[-1]
    await set_user_translation_language(user_id, lang)
    await query.edit_message_text(f"✅ تم تعيين لغة الترجمة: {SUPPORTED_LANGUAGES.get(lang, lang)}")
    await translation_menu_callback(update, context)

async def contests_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    contests = await db_get_active_contests()
    if not contests:
        await query.edit_message_text("📭 لا توجد مسابقات نشطة.")
        return
    text = "🏆 **المسابقات النشطة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for c in contests:
        text += f"📌 {c['title']}\n"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 اشترك الآن", callback_data=f"{CallbackData.CONTEST_JOIN_PREFIX}{c['id']}")],
            [InlineKeyboardButton("🏆 الفائزون السابقون", callback_data=CallbackData.CONTEST_WINNERS)],
            [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
        ])
    await query.edit_message_text(text, reply_markup=keyboard)

async def contest_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    contest_id = int(query.data.split(":")[-1])
    contest = await db_get_contest(contest_id)
    if not contest:
        await query.edit_message_text("❌ المسابقة غير موجودة!")
        return
    if contest['status'] != 'active':
        await query.edit_message_text("❌ هذه المسابقة انتهت!")
        return
    if await db_get_user_participation(user_id, contest_id):
        await query.answer("❌ أنت مشترك بالفعل!", show_alert=True)
        return
    if contest.get('contest_type') == 'quiz':
        context.user_data['contest_join_id'] = contest_id
        context.user_data['state'] = UserState.WAITING_CONTEST_ANSWER
        await query.edit_message_text(f"📝 **{contest['title']}**\n\n{contest['description']}\n\nأرسل إجابتك، أو اكتب /skip للتخطي.")
    else:
        success = await db_participate_in_contest(user_id, contest_id, "")
        if success:
            await query.edit_message_text("✅ تم تسجيل مشاركتك!")
        else:
            await query.edit_message_text("❌ فشل التسجيل.")
        await contests_menu_callback(update, context)

async def contest_winners_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    async def _get_winners(conn):
        cur = await conn.execute("SELECT c.title, cw.winner_id FROM contest_winners cw JOIN contests c ON cw.contest_id = c.id ORDER BY cw.announced_at DESC LIMIT 10")
        return await cur.fetchall()
    winners = await execute_db(_get_winners)
    if not winners:
        await query.edit_message_text("📭 لا توجد فائزين.")
        return
    text = "🏆 **الفائزون السابقون**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for title, winner_id in winners:
        try:
            user = await context.bot.get_chat(winner_id)
            name = user.first_name or str(winner_id)
        except:
            name = str(winner_id)
        text += f"📌 {title} - {name} 🎉\n"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.CONTESTS_MENU)]])
    await query.edit_message_text(text, reply_markup=keyboard)

async def contests_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu_callback(update, context)

async def channel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    ch_db_id = int(parts[1]) if len(parts) >= 2 else context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not ch_db_id:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    ch_info = await db_get_channel_info(ch_db_id)
    channel_name = ch_info[1] if ch_info else "القناة"
    total = await db_get_posts_count(ch_db_id)
    published = await db_get_published_count(ch_db_id)
    unpublished = await db_unpublished_count(ch_db_id)
    text = f"📊 **إحصائيات {channel_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n📝 إجمالي المنشورات: {total}\n✅ المنشورة: {published}\n⏳ غير المنشورة: {unpublished}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 تحديث", callback_data=f"{CallbackData.CHANNEL_STATS_REFRESH}:{ch_db_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def channel_growth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    parts = query.data.split(":")
    ch_db_id = int(parts[1]) if len(parts) >= 2 else context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not ch_db_id:
        if query:
            await query.edit_message_text("⚠️ اختر قناة أولاً")
        else:
            await safe_send_markdown(context.bot, user_id, "⚠️ اختر قناة أولاً")
        return
    ch_info = await db_get_channel_info(ch_db_id)
    channel_name = ch_info[1] if ch_info else "القناة"
    text = f"📈 **نمو {channel_name}**\n━━━━━━━━━━━━━━━━━━━━━━\n🚧 هذه الميزة قيد التطوير."
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def channel_stats_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await channel_stats_callback(update, context)

async def my_channel_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    channels = await db_get_channels(user_id)
    if not channels:
        await query.edit_message_text("📭 لا توجد قنوات.")
        return
    total_posts = 0
    total_unpublished = 0
    for ch in channels:
        ch_db_id = ch[0]
        total_posts += await db_get_posts_count(ch_db_id)
        total_unpublished += await db_unpublished_count(ch_db_id)
    text = f"📊 **ملخص قنواتي**\n━━━━━━━━━━━━━━━━━━━━━━\n📡 عدد القنوات: {len(channels)}\n📝 إجمالي المنشورات: {total_posts}\n⏳ غير المنشورة: {total_unpublished}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]])
    await query.edit_message_text(text, reply_markup=keyboard)

async def publish_all_channels_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    if not await db_has_active_subscription(uid) and not await db_has_used_trial(uid):
        await query.edit_message_text("⚠️ اشتراكك منتهٍ.")
        return
    channels = await db_get_channels(uid)
    if not channels:
        if query:
            await query.edit_message_text("📭 لا توجد قنوات.")
        else:
            await safe_send_markdown(context.bot, uid, "📭 لا توجد قنوات.")
        return
    if query:
        await query.edit_message_text("📤 جاري النشر في جميع القنوات...")
    else:
        await safe_send_markdown(context.bot, uid, "📤 جاري النشر...")
    results = []
    success_count = 0
    fail_count = 0
    no_posts_count = 0
    for ch_db_id, ch_tele_id, ch_name, banned in channels:
        if banned:
            results.append(f"⛔ {ch_name}: محظورة")
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
            results.append(f"✅ {ch_name}: تم النشر")
            success_count += 1
        except Exception as e:
            results.append(f"❌ {ch_name}: {str(e)[:50]}")
            fail_count += 1
        await asyncio.sleep(1)
    summary = f"📊 **نتائج النشر**\n━━━━━━━━━━━━━━━━━━━━━━\n✅ نجح: {success_count}\n❌ فشل: {fail_count}\n📭 لا توجد منشورات: {no_posts_count}\n\n"
    result_text = summary + "\n".join(results[:20])
    if len(results) > 20:
        result_text += f"\n\n... و {len(results)-20} نتيجة أخرى"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]])
    if query:
        await safe_edit_markdown(query, result_text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, uid, result_text, reply_markup=keyboard)

async def trial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    if await db_has_used_trial(user_id):
        await query.edit_message_text("❌ لقد استخدمت التجربة المجانية بالفعل.")
        return
    await db_use_trial(user_id)
    await query.edit_message_text("✅ تم تفعيل التجربة المجانية لمدة 3 أيام!")

async def subscribe_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    text = "💎 **الاشتراك**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر خطة الاشتراك:"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 يوم واحد - $1", callback_data=CallbackData.BUY_SUBSCRIPTION_1)],
        [InlineKeyboardButton("📅 يومين - $2", callback_data=CallbackData.BUY_SUBSCRIPTION_2)],
        [InlineKeyboardButton("📅 30 يوم - $15", callback_data=CallbackData.BUY_SUBSCRIPTION_30)],
        [InlineKeyboardButton("📅 90 يوم - $40", callback_data=CallbackData.BUY_SUBSCRIPTION_90)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def buy_subscription_1_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    await db_add_subscription_days(user_id, 1)
    await query.edit_message_text("✅ تم إضافة يوم واحد إلى اشتراكك!")

async def buy_subscription_2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    await db_add_subscription_days(user_id, 2)
    await query.edit_message_text("✅ تم إضافة يومين إلى اشتراكك!")

async def buy_subscription_30_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    await db_add_subscription_days(user_id, 30)
    await query.edit_message_text("✅ تم إضافة 30 يوم إلى اشتراكك!")

async def buy_subscription_90_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    await db_add_subscription_days(user_id, 90)
    await query.edit_message_text("✅ تم إضافة 90 يوم إلى اشتراكك!")

async def developer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    text = "👨‍💻 **المطور**\n━━━━━━━━━━━━━━━━━━━━━━\n🌿 ريلاكس مانيجر\n📌 الإصدار: 22.8.0\n👤 المطور: @RelaxTeam"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def updates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    text = "📢 **آخر التحديثات**\n━━━━━━━━━━━━━━━━━━━━━━\n✅ تحديث 22.8.0\n• تحسينات في الأداء\n• إصلاح أخطاء\n• إضافة ميزات جديدة"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]])
    if query:
        await safe_edit_markdown(query, text, reply_markup=keyboard)
    else:
        await safe_send_markdown(context.bot, user_id, text, reply_markup=keyboard)

async def panel_lock_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('panel_chat_id')
    if not chat_id:
        return
    if await is_authorized_in_group(context.bot, chat_id, uid):
        await db_set_chat_lock(chat_id, True, uid)
        if query:
            await safe_edit_markdown(query, "🔒 تم قفل المجموعة.")
        else:
            await safe_send_markdown(context.bot, uid, "🔒 تم قفل المجموعة.")
    else:
        if query:
            await query.answer("⚠️ غير مصرح", show_alert=True)
        else:
            await safe_send_markdown(context.bot, uid, "⚠️ غير مصرح")

async def panel_unlock_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('panel_chat_id')
    if not chat_id:
        return
    if await is_authorized_in_group(context.bot, chat_id, uid):
        await db_set_chat_lock(chat_id, False)
        if query:
            await safe_edit_markdown(query, "🔓 تم فتح المجموعة.")
        else:
            await safe_send_markdown(context.bot, uid, "🔓 تم فتح المجموعة.")
    else:
        if query:
            await query.answer("⚠️ غير مصرح", show_alert=True)
        else:
            await safe_send_markdown(context.bot, uid, "⚠️ غير مصرح")

async def panel_close_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.message.delete()

async def check_subscribe_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    enabled = await db_get_force_subscribe_status()
    channel = await db_get_force_subscribe_channel()
    if enabled and channel:
        if await is_user_subscribed(context.bot, uid, channel):
            if query:
                await safe_edit_markdown(query, "✅ تم التحقق! أنت مشترك الآن.")
            else:
                await safe_send_markdown(context.bot, uid, "✅ تم التحقق!")
            await main_menu_callback(update, context)
        else:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 اشترك", url=f"https://t.me/{channel.lstrip('@')}"),
                 InlineKeyboardButton("🔄 تأكد", callback_data=CallbackData.CHECK_SUBSCRIBE),
                 InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
            ])
            if query:
                await safe_edit_markdown(query, f"❌ لم تشترك في @{channel.lstrip('@')}", reply_markup=kb)
            else:
                await safe_send_markdown(context.bot, uid, f"❌ لم تشترك في @{channel.lstrip('@')}", reply_markup=kb)
    else:
        if query:
            await safe_edit_markdown(query, "⚠️ الاشتراك الإجباري غير مفعل")
        else:
            await safe_send_markdown(context.bot, uid, "⚠️ الاشتراك الإجباري غير مفعل")

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    lang_code = query.data.split("_")[-1] if query else context.user_data.get('lang_code', 'ar')
    await set_user_language(user_id, lang_code)
    kb, title, active = await get_main_keyboard(user_id)
    if query:
        await safe_edit_markdown(query, title, reply_markup=kb)
    else:
        await safe_send_markdown(context.bot, user_id, title, reply_markup=kb)

async def handle_text_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        if query:
            await query.edit_message_text("🔒 هذه اللوحة للمشرفين فقط.")
        else:
            await update.message.reply_text("🔒 هذه اللوحة للمشرفين فقط.")
        return
    text = "🛠️ **لوحة تحكم الأدمن**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإجراء المطلوب:"
    keyboard = [
        [InlineKeyboardButton("👥 المستخدمين", callback_data=CallbackData.ADMIN_USERS),
         InlineKeyboardButton("🚫 المحظورين", callback_data=CallbackData.ADMIN_BANNED_USERS)],
        [InlineKeyboardButton("📡 القنوات", callback_data=CallbackData.ADMIN_ALL_CHANNELS),
         InlineKeyboardButton("⛔ قنوات محظورة", callback_data=CallbackData.ADMIN_BANNED_CHANNELS)],
        [InlineKeyboardButton("👥 المجموعات", callback_data=CallbackData.ADMIN_GROUPS),
         InlineKeyboardButton("⛔ مجموعات محظورة", callback_data=CallbackData.ADMIN_BANNED_GROUPS)],
        [InlineKeyboardButton("🤖 قنوات البوت", callback_data=CallbackData.ADMIN_BOT_CHANNELS),
         InlineKeyboardButton("⛔ قنوات بوت محظورة", callback_data=CallbackData.ADMIN_BANNED_BOT_CHANNELS)],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data=CallbackData.ADMIN_STATS),
         InlineKeyboardButton("💾 الذاكرة", callback_data=CallbackData.ADMIN_RAM)],
        [InlineKeyboardButton("📈 المقاييس", callback_data=CallbackData.ADMIN_METRICS),
         InlineKeyboardButton("💾 النسخ الاحتياطي", callback_data=CallbackData.ADMIN_BACKUP)],
        [InlineKeyboardButton("⚙️ إعدادات النسخ", callback_data=CallbackData.ADMIN_BACKUP_SETTINGS),
         InlineKeyboardButton("📢 التحديثات", callback_data=CallbackData.ADMIN_UPDATES)],
        [InlineKeyboardButton("📢 الاشتراك الإجباري", callback_data=CallbackData.ADMIN_FORCE_SUBSCRIBE),
         InlineKeyboardButton("📨 البث العام", callback_data=CallbackData.ADMIN_BROADCAST)],
        [InlineKeyboardButton("🎫 التذاكر", callback_data=CallbackData.ADMIN_SUPPORT_TICKETS),
         InlineKeyboardButton("📝 إدارة الردود", callback_data=CallbackData.ADMIN_REPLIES)],
        [InlineKeyboardButton("🚫 الكلمات المحظورة", callback_data=CallbackData.ADMIN_BANNED_WORDS),
         InlineKeyboardButton("🏆 المسابقات", callback_data=CallbackData.ADMIN_CREATE_CONTEST)],
        [InlineKeyboardButton("🤖 الرد التلقائي", callback_data=CallbackData.ADMIN_AUTO_REPLY),
         InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.BACK)]
    ]
    if query:
        await safe_edit_markdown(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_send_markdown(context.bot, uid, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    users = await db_get_all_users()
    if not users:
        await query.edit_message_text("📭 لا يوجد مستخدمون.")
        return
    text = "👥 **قائمة المستخدمين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for u in users[:50]:
        text += f"• `{u}`\n"
    if len(users) > 50:
        text += f"\n... و {len(users)-50} آخرين"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_banned_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    banned = await db_get_banned_users()
    if not banned:
        await query.edit_message_text("📭 لا يوجد مستخدمون محظورون.")
        return
    text = "🚫 **المستخدمون المحظورون**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for u in banned[:50]:
        text += f"• `{u}`\n"
    keyboard = [
        [InlineKeyboardButton("✅ إلغاء حظر الكل", callback_data=CallbackData.ADMIN_UNBAN_ALL_USERS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_unban_all_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    await db_unban_all_users()
    await query.edit_message_text("✅ تم إلغاء حظر جميع المستخدمين.")
    await admin_panel_callback(update, context)

async def admin_all_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    channels = await db_get_all_channels()
    if not channels:
        await query.edit_message_text("📭 لا توجد قنوات.")
        return
    text = "📡 **جميع القنوات**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for ch in channels[:50]:
        text += f"• {ch['name']} (ID: `{ch['id']}`)\n"
    keyboard = [
        [InlineKeyboardButton("✅ تفعيل الكل", callback_data=CallbackData.ADMIN_ACTIVATE_ALL_CHANNELS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_banned_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    banned = await db_get_banned_channels()
    if not banned:
        await query.edit_message_text("📭 لا توجد قنوات محظورة.")
        return
    text = "⛔ **القنوات المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for ch in banned[:50]:
        text += f"• {ch['name']} (ID: `{ch['id']}`)\n"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_activate_all_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    await db_activate_all_channels()
    await query.edit_message_text("✅ تم تفعيل جميع القنوات.")
    await admin_panel_callback(update, context)

async def admin_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    groups = await db_get_all_groups()
    if not groups:
        await query.edit_message_text("📭 لا توجد مجموعات.")
        return
    text = "👥 **جميع المجموعات**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for g in groups[:50]:
        text += f"• {g['name']} (ID: `{g['id']}`)\n"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_banned_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    banned = await db_get_banned_groups()
    if not banned:
        await query.edit_message_text("📭 لا توجد مجموعات محظورة.")
        return
    text = "⛔ **المجموعات المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for g in banned[:50]:
        text += f"• {g['name']} (ID: `{g['id']}`)\n"
    keyboard = [
        [InlineKeyboardButton("✅ إلغاء حظر الكل", callback_data=CallbackData.ADMIN_UNBAN_ALL_GROUPS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_unban_all_groups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    await db_unban_all_groups()
    await query.edit_message_text("✅ تم إلغاء حظر جميع المجموعات.")
    await admin_panel_callback(update, context)

async def admin_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    channels = await db_get_bot_channels()
    if not channels:
        await query.edit_message_text("📭 لا توجد قنوات بوت.")
        return
    text = "🤖 **قنوات البوت**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for ch in channels[:50]:
        text += f"• {ch['name']} (ID: `{ch['id']}`)\n"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_banned_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    banned = await db_get_banned_bot_channels()
    if not banned:
        await query.edit_message_text("📭 لا توجد قنوات بوت محظورة.")
        return
    text = "⛔ **قنوات البوت المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for ch in banned[:50]:
        text += f"• {ch['name']} (ID: `{ch['id']}`)\n"
    keyboard = [
        [InlineKeyboardButton("✅ إلغاء حظر الكل", callback_data=CallbackData.ADMIN_UNBAN_ALL_BOT_CHANNELS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_unban_all_bot_channels_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    await db_unban_all_bot_channels()
    await query.edit_message_text("✅ تم إلغاء حظر جميع قنوات البوت.")
    await admin_panel_callback(update, context)

async def admin_monitor_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🚧 قيد التطوير.")

async def admin_add_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 فقط المالك يمكنه إضافة مشرفين.")
        return
    context.user_data['state'] = UserState.WAITING_ADD_ADMIN
    await query.edit_message_text("✏️ أرسل معرف المستخدم (user_id) لإضافته كمشرف:")

async def admin_remove_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 فقط المالك يمكنه إزالة مشرفين.")
        return
    context.user_data['state'] = UserState.WAITING_REMOVE_ADMIN
    await query.edit_message_text("✏️ أرسل معرف المستخدم (user_id) لإزالته من المشرفين:")

async def admin_ram_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    ram = get_ram_usage()
    text = f"💾 **حالة الذاكرة**\n━━━━━━━━━━━━━━━━━━━━━━\n📊 المستخدم: {ram['used']} / {ram['total']} ({ram['percent']}%)\n🟢 المتاح: {ram['free']}"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    total, banned, posts, groups, channels = await db_stats()
    text = f"📊 **إحصائيات عامة**\n━━━━━━━━━━━━━━━━━━━━━━\n👥 المستخدمون: {total}\n🚫 المحظورون: {banned}\n📝 المنشورات: {posts}\n👥 المجموعات: {groups}\n📡 القنوات: {channels}"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_metrics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🚧 قيد التطوير.")

async def admin_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    backups = await list_backups()
    if not backups:
        await query.edit_message_text("📭 لا توجد نسخ احتياطية.")
        return
    text = "💾 **النسخ الاحتياطية**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for b in backups[:10]:
        text += f"• {b.name} ({b.stat().st_size // 1024} كيلوبايت)\n"
    keyboard = [
        [InlineKeyboardButton("📤 إنشاء نسخة", callback_data=CallbackData.ADMIN_BACKUP_SETTINGS)],
        [InlineKeyboardButton("📥 استعادة", callback_data=CallbackData.ADMIN_RESTORE_BACKUP)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_restore_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    backups = await list_backups()
    if not backups:
        await query.edit_message_text("📭 لا توجد نسخ للاستعادة.")
        return
    keyboard = []
    for b in backups[:10]:
        keyboard.append([InlineKeyboardButton(b.name, callback_data=f"{CallbackData.ADMIN_RESTORE_BACKUP_SELECT_PREFIX}{b.name}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_BACKUP)])
    await query.edit_message_text("📥 **اختر النسخة للاستعادة:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_restore_backup_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    backup_name = query.data.split(":")[-1]
    backup_path = BACKUP_DIR / backup_name
    if not backup_path.exists():
        await query.edit_message_text("❌ الملف غير موجود.")
        return
    try:
        await restore_backup(backup_path)
        await query.edit_message_text("✅ تم استعادة النسخة بنجاح!")
    except Exception as e:
        await query.edit_message_text(f"❌ فشل الاستعادة: {e}")

async def admin_backup_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    auto_backup = await db_get_auto_backup()
    interval = await db_get_backup_interval()
    status = "✅ مفعل" if auto_backup else "❌ معطل"
    text = f"⚙️ **إعدادات النسخ الاحتياطي**\n━━━━━━━━━━━━━━━━━━━━━━\n🔄 النسخ التلقائي: {status}\n⏱️ الفاصل: {interval // 3600} ساعة"
    keyboard = [
        [InlineKeyboardButton(f"{'🔄 إيقاف' if auto_backup else '▶️ تفعيل'} التلقائي", callback_data=CallbackData.ADMIN_TOGGLE_AUTO_BACKUP)],
        [InlineKeyboardButton("⏱️ تغيير الفاصل", callback_data=CallbackData.ADMIN_CHANGE_INTERVAL)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_BACKUP)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_toggle_auto_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    current = await db_get_auto_backup()
    await db_set_auto_backup(not current)
    await query.edit_message_text(f"✅ تم {'تفعيل' if not current else 'تعطيل'} النسخ التلقائي.")
    await admin_backup_settings_callback(update, context)

async def admin_change_interval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_BACKUP_INTERVAL
    await query.edit_message_text("⏱️ أرسل الفاصل الزمني بالساعات (مثال: 6)")

async def admin_send_update_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_UPDATE_TEXT
    await query.edit_message_text("📢 أرسل نص التحديث لإرساله للمستخدمين:")

async def admin_set_update_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_UPDATE_CHANNEL
    await query.edit_message_text("📢 أرسل معرف القناة (مثال: @my_channel) لتعيينها كقناة تحديثات:")

async def admin_show_update_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    await query.edit_message_text("📢 قناة التحديثات: غير محددة")

async def admin_updates_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    text = "📢 **إدارة التحديثات**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإجراء:"
    keyboard = [
        [InlineKeyboardButton("📤 إرسال تحديث", callback_data=CallbackData.ADMIN_SEND_UPDATE)],
        [InlineKeyboardButton("📌 تعيين قناة", callback_data=CallbackData.ADMIN_SET_UPDATE_CHANNEL)],
        [InlineKeyboardButton("👁️ عرض القناة", callback_data=CallbackData.ADMIN_SHOW_UPDATE_CHANNEL)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_force_subscribe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    status = await db_get_force_subscribe_status()
    channel = await db_get_force_subscribe_channel()
    text = f"📢 **الاشتراك الإجباري**\n━━━━━━━━━━━━━━━━━━━━━━\nالحالة: {'✅ مفعل' if status else '❌ معطل'}\nالقناة: {channel if channel else 'غير محددة'}"
    keyboard = [
        [InlineKeyboardButton(f"{'🔄 تعطيل' if status else '▶️ تفعيل'}", callback_data="toggle_force_subscribe")],
        [InlineKeyboardButton("📌 تعيين قناة", callback_data=CallbackData.ADMIN_SET_FORCE_CHANNEL)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_set_force_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_FORCE_CHANNEL
    await query.edit_message_text("📢 أرسل معرف القناة (مثال: @my_channel) للاشتراك الإجباري:")

async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_BROADCAST_TEXT
    await query.edit_message_text("📨 أرسل نص البث العام (سيُرسل لجميع المستخدمين):")

async def admin_confirm_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

async def admin_support_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    tickets = await db_get_support_tickets()
    if not tickets:
        await query.edit_message_text("📭 لا توجد تذاكر دعم.")
        return
    text = "🎫 **تذاكر الدعم**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for t in tickets[:20]:
        text += f"• #{t['id']} من {t['username']} - {t['status']}\n"
    keyboard = [
        [InlineKeyboardButton("🗑️ حذف الكل", callback_data=CallbackData.ADMIN_DELETE_ALL_TICKETS)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_delete_all_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    keyboard = [
        [InlineKeyboardButton("✅ نعم", callback_data=CallbackData.ADMIN_CONFIRM_DELETE_TICKETS)],
        [InlineKeyboardButton("❌ لا", callback_data=CallbackData.ADMIN_SUPPORT_TICKETS)]
    ]
    await query.edit_message_text("⚠️ هل أنت متأكد من حذف جميع التذاكر؟", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_confirm_delete_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    await db_delete_all_tickets()
    await query.edit_message_text("✅ تم حذف جميع التذاكر.")
    await admin_panel_callback(update, context)

async def admin_manage_sendcode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    users = await db_get_sendcode_users()
    text = "📝 **مستخدمي كود الإرسال**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    if users:
        for u in users:
            text += f"• `{u}`\n"
    else:
        text += "لا يوجد مستخدمون."
    keyboard = [
        [InlineKeyboardButton("➕ إضافة مستخدم", callback_data=CallbackData.ADMIN_SET_SENDCODE_USER)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_set_sendcode_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_SENDCODE_USER
    await query.edit_message_text("✏️ أرسل معرف المستخدم (user_id) لإضافته إلى قائمة الإرسال:")

async def admin_show_log_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    channel = await db_get_log_channel()
    text = f"📋 قناة التقارير: {channel if channel else 'غير محددة'}"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_set_log_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_LOG_CHANNEL
    await query.edit_message_text("📋 أرسل معرف القناة (مثال: @logs) لتعيينها كقناة تقارير:")

async def admin_replies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    text = "📝 **إدارة الردود التلقائية**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإجراء:"
    keyboard = [
        [InlineKeyboardButton("➕ إضافة رد", callback_data=CallbackData.ADMIN_ADD_REPLY)],
        [InlineKeyboardButton("📋 عرض الردود", callback_data=CallbackData.ADMIN_LIST_REPLIES)],
        [InlineKeyboardButton("🗑️ حذف رد", callback_data=CallbackData.ADMIN_DEL_REPLY)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_add_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_ADD_REPLY
    await query.edit_message_text("✏️ أرسل الكلمة المفتاحية أولاً، ثم في سطر جديد الرد:\nمثال:\n`مرحباً`\n`أهلاً بك في البوت`")

async def admin_list_replies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    replies = await db_get_all_replies()
    if not replies:
        await query.edit_message_text("📭 لا توجد ردود.")
        return
    text = "📋 **الردود التلقائية**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for r in replies[:50]:
        text += f"• `{r['keyword']}` → {r['reply'][:30]}...\n"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_REPLIES)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_del_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_DEL_REPLY
    await query.edit_message_text("✏️ أرسل الكلمة المفتاحية للرد المراد حذفه:")

async def admin_banned_words_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    text = "🚫 **إدارة الكلمات المحظورة (عامة)**\n━━━━━━━━━━━━━━━━━━━━━━\nاختر الإجراء:"
    keyboard = [
        [InlineKeyboardButton("➕ إضافة كلمة", callback_data=CallbackData.ADMIN_ADD_BANNED_WORD)],
        [InlineKeyboardButton("📋 عرض الكلمات", callback_data=CallbackData.ADMIN_LIST_BANNED_WORDS)],
        [InlineKeyboardButton("🗑️ حذف كلمة", callback_data=CallbackData.ADMIN_REMOVE_BANNED_WORD)],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_add_banned_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_ADD_BANNED_WORD
    await query.edit_message_text("✏️ أرسل الكلمة التي تريد إضافتها إلى القائمة العامة:")

async def admin_list_banned_words_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    words = await db_get_global_banned_words()
    if not words:
        await query.edit_message_text("📭 لا توجد كلمات محظورة عامة.")
        return
    text = "🚫 **الكلمات المحظورة (عامة)**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for w in words:
        text += f"• `{w}`\n"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_BANNED_WORDS)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_remove_banned_word_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_REMOVE_BANNED_WORD
    await query.edit_message_text("✏️ أرسل الكلمة التي تريد حذفها من القائمة العامة:")

async def admin_create_contest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_CONTEST_DETAILS
    await query.edit_message_text("🏆 **إنشاء مسابقة**\n\nأرسل تفاصيل المسابقة بهذا التنسيق:\n`العنوان|الوصف|الجائزة|عدد الأيام`\nمثال:\n`مسابقة الربيع|شارك واربح|هدية 100$|3`")

async def admin_declare_winner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    contests = await db_get_active_contests()
    if not contests:
        await query.edit_message_text("📭 لا توجد مسابقات نشطة.")
        return
    keyboard = []
    for c in contests:
        keyboard.append([InlineKeyboardButton(f"🏆 {c['title']}", callback_data=f"{CallbackData.ADMIN_DEL_CONTEST_PREFIX}{c['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)])
    await query.edit_message_text("🏆 **اختر مسابقة لإعلان الفائز:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_del_contest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    contest_id = int(query.data.split(":")[-1])
    await db_delete_contest(contest_id)
    await query.edit_message_text("✅ تم حذف المسابقة.")
    await admin_panel_callback(update, context)

async def admin_auto_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    groups = await db_get_all_groups()
    if not groups:
        await query.edit_message_text("📭 لا توجد مجموعات.")
        return
    keyboard = []
    for g in groups[:20]:
        settings = await db_get_auto_reply_settings(g['id'])
        status = "✅" if settings.get('enabled', False) else "❌"
        keyboard.append([InlineKeyboardButton(f"{status} {g['name']}", callback_data=f"{CallbackData.AUTO_REPLY_MENU_PREFIX}{g['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_PANEL)])
    await query.edit_message_text("🤖 **إعدادات الرد التلقائي للمجموعات**\nاختر مجموعة:", reply_markup=InlineKeyboardMarkup(keyboard))

async def auto_reply_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    chat_id = int(query.data.split(":")[-1])
    settings = await db_get_auto_reply_settings(chat_id)
    enabled = settings.get('enabled', False)
    only_admins = settings.get('only_admins', False)
    ignore_bots = settings.get('ignore_bots', True)
    
    text = f"🤖 **الرد التلقائي للمجموعة `{chat_id}`**\n━━━━━━━━━━━━━━━━━━━━━━\nالحالة: {'✅ مفعل' if enabled else '❌ معطل'}\nالمشرفون فقط: {'✅' if only_admins else '❌'}\nتجاهل البوتات: {'✅' if ignore_bots else '❌'}"
    
    keyboard = [
        [InlineKeyboardButton(f"{'🔄 تعطيل' if enabled else '▶️ تفعيل'}", callback_data=f"{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}{chat_id}")],
        [InlineKeyboardButton(f"{'🔒 المشرفون فقط' if only_admins else '👥 الجميع'}", callback_data=f"{CallbackData.AUTO_REPLY_ADMINS_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🗑️ إعادة ضبط", callback_data=f"{CallbackData.AUTO_REPLY_RESET_PREFIX}{chat_id}")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data=f"{CallbackData.AUTO_REPLY_STATS_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=CallbackData.ADMIN_AUTO_REPLY)]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def auto_reply_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    chat_id = int(query.data.split(":")[-1])
    settings = await db_get_auto_reply_settings(chat_id)
    new_val = not settings.get('enabled', False)
    await db_set_auto_reply_settings(chat_id, enabled=new_val)
    await query.edit_message_text(f"✅ تم {'تفعيل' if new_val else 'تعطيل'} الرد التلقائي.")
    await auto_reply_menu_callback(update, context)

async def auto_reply_admins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    chat_id = int(query.data.split(":")[-1])
    settings = await db_get_auto_reply_settings(chat_id)
    new_val = not settings.get('only_admins', False)
    await db_set_auto_reply_settings(chat_id, only_admins=new_val)
    await query.edit_message_text(f"✅ تم {'تفعيل' if new_val else 'تعطيل'} خاصية المشرفين فقط.")
    await auto_reply_menu_callback(update, context)

async def auto_reply_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    chat_id = int(query.data.split(":")[-1])
    keyboard = [
        [InlineKeyboardButton("✅ نعم", callback_data=f"{CallbackData.AUTO_REPLY_CONFIRM_RESET_PREFIX}{chat_id}")],
        [InlineKeyboardButton("❌ لا", callback_data=f"{CallbackData.AUTO_REPLY_CANCEL_PREFIX}{chat_id}")]
    ]
    await query.edit_message_text("⚠️ هل أنت متأكد من إعادة ضبط الإعدادات؟", reply_markup=InlineKeyboardMarkup(keyboard))

async def auto_reply_confirm_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    chat_id = int(query.data.split(":")[-1])
    await db_reset_auto_reply_settings(chat_id)
    await query.edit_message_text("✅ تم إعادة ضبط الإعدادات.")
    await auto_reply_menu_callback(update, context)

async def auto_reply_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await auto_reply_menu_callback(update, context)

async def auto_reply_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not await is_bot_admin(uid) and uid != PRIMARY_OWNER_ID:
        await query.edit_message_text("🔒 غير مصرح.")
        return
    chat_id = int(query.data.split(":")[-1])
    stats = await db_get_auto_reply_stats(chat_id)
    text = f"📊 **إحصائيات الرد التلقائي**\n━━━━━━━━━━━━━━━━━━━━━━\nإجمالي الردود: {stats.get('total_replies', 0)}\nآخر رد: {stats.get('last_reply_time', 'لا يوجد')}"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.AUTO_REPLY_MENU_PREFIX}{chat_id}")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def user_auto_reply_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    current = await db_get_user_auto_reply(uid)
    new_val = not current
    await db_set_user_auto_reply(uid, new_val)
    await query.edit_message_text(f"✅ تم {'تفعيل' if new_val else 'تعطيل'} الرد التلقائي.")
    await settings_menu_callback(update, context)

async def security_banned_words_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('banned_words_chat_id')
    if not chat_id:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ يجب أن تكون مشرفاً", show_alert=True)
        return
    context.user_data['banned_words_chat_id'] = chat_id
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كلمة", callback_data=f"{CallbackData.BANNED_WORDS_ADD_PREFIX}{chat_id}")],
        [InlineKeyboardButton("📋 عرض الكلمات", callback_data=f"{CallbackData.BANNED_WORDS_LIST_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🗑️ حذف كلمة", callback_data=f"{CallbackData.BANNED_WORDS_REMOVE_PREFIX}{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ])
    await query.edit_message_text("🚫 **الكلمات المحظورة**\nاختر الإجراء:", reply_markup=keyboard)

async def banned_words_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('banned_words_chat_id')
    if not chat_id:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ يجب أن تكون مشرفاً", show_alert=True)
        return
    context.user_data['state'] = UserState.WAITING_GROUP_BANNED_WORD
    context.user_data['banned_words_chat_id'] = chat_id
    await query.edit_message_text("✏️ أرسل الكلمة التي تريد إضافتها:")

async def banned_words_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('banned_words_chat_id')
    if not chat_id:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ يجب أن تكون مشرفاً", show_alert=True)
        return
    words = await db_get_banned_words(chat_id)
    if not words:
        await query.edit_message_text("📭 لا توجد كلمات محظورة.")
        return
    text = "🚫 **الكلمات المحظورة**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for word, added_by, added_at in words:
        text += f"• `{word}` (أضيف بواسطة {added_by})\n"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}{chat_id}")]])
    await query.edit_message_text(text, reply_markup=keyboard)

async def banned_words_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    user_id = update.effective_user.id
    chat_id = int(query.data.split(":")[-1]) if query else context.user_data.get('banned_words_chat_id')
    if not chat_id:
        return
    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("⚠️ يجب أن تكون مشرفاً", show_alert=True)
        return
    context.user_data['state'] = UserState.WAITING_REMOVE_GROUP_BANNED_WORD
    context.user_data['banned_words_chat_id'] = chat_id
    await query.edit_message_text("✏️ أرسل الكلمة التي تريد حذفها:")

async def security_warn_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    chat_id = int(query.data.split(":")[-1])
    if not await is_authorized_in_group(context.bot, chat_id, uid):
        await query.answer("⚠️ يجب أن تكون مشرفاً", show_alert=True)
        return
    settings = await db_get_security_settings(chat_id, force_refresh=True)
    max_warnings = settings.get('max_warnings', 3)
    warn_penalty = settings.get('warn_penalty', 'ban')
    
    text = f"⚠️ **إعدادات التحذير**\n━━━━━━━━━━━━━━━━━━━━━━\nعدد التحذيرات: {max_warnings}\nالعقوبة بعد التحذير: {warn_penalty}"
    keyboard = [
        [InlineKeyboardButton("🔢 تغيير العدد", callback_data=f"set_max_warnings:{chat_id}")],
        [InlineKeyboardButton("⚖️ تغيير العقوبة", callback_data=f"set_warn_penalty:{chat_id}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CallbackData.GROUPS_SETTINGS_PREFIX}{chat_id}")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def security_advanced_actions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await advanced_actions_callback(update, context)

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await db_create_user(user_id)
    enabled = await db_get_force_subscribe_status()
    channel = await db_get_force_subscribe_channel()
    if enabled and channel:
        if not await is_user_subscribed(context.bot, user_id, channel):
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 اشترك", url=f"https://t.me/{channel.lstrip('@')}"),
                 InlineKeyboardButton("🔄 تأكد", callback_data=CallbackData.CHECK_SUBSCRIBE)]
            ])
            await update.message.reply_text(f"❌ يرجى الاشتراك في @{channel.lstrip('@')} أولاً", reply_markup=kb)
            return
    await main_menu_callback(update, context)

async def language_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"),
         InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr")]
    ])
    await update.message.reply_text("🌐 اختر اللغة:", reply_markup=keyboard)

async def syncgroup_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("⚠️ هذا الأمر يعمل فقط في المجموعات.")
        return
    try:
        member = await context.bot.get_chat_member(chat.id, user_id)
        if member.status not in ['administrator', 'creator']:
            await update.message.reply_text("⚠️ يجب أن تكون مشرفاً في المجموعة.")
            return
    except:
        await update.message.reply_text("⚠️ فشل التحقق من صلاحياتك.")
        return
    await db_add_group(chat.id, chat.title, chat.username or "", user_id)
    await db_sync_group_admins(chat.id, context.bot)
    async def _add_link(conn):
        await conn.execute("INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?, ?)", (user_id, chat.id))
        await conn.commit()
    await execute_db(_add_link)
    await update.message.reply_text("✅ تم مزامنة المجموعة بنجاح!")

async def trial_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await db_has_used_trial(user_id):
        await update.message.reply_text("❌ لقد استخدمت التجربة المجانية بالفعل.")
        return
    await db_use_trial(user_id)
    await update.message.reply_text("✅ تم تفعيل التجربة المجانية لمدة 3 أيام!")

async def subscribe_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await subscribe_menu_callback(update, context)

async def help_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await help_callback(update, context)

async def support_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await support_menu_callback(update, context)

async def support_reply_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
        await update.message.reply_text("🔒 غير مصرح.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("📝 استخدم: /support_reply <ticket_id> <الرد>")
        return
    ticket_id = int(args[0])
    reply_text = " ".join(args[1:])
    ticket = await db_get_ticket(ticket_id)
    if not ticket:
        await update.message.reply_text("❌ التذكرة غير موجودة.")
        return
    await db_reply_ticket(ticket_id, reply_text)
    try:
        await context.bot.send_message(ticket['user_id'], f"📩 **رد على تذكرتك #{ticket['ticket_number']}**\n\n{reply_text}")
    except:
        pass
    await update.message.reply_text(f"✅ تم الرد على التذكرة #{ticket['ticket_number']}")

async def rank_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚧 هذه الميزة قيد التطوير.")

async def top_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚧 هذه الميزة قيد التطوير.")

async def developer_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await developer_callback(update, context)

async def updates_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await updates_callback(update, context)

async def stats_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await full_stats_callback(update, context)

async def sendcode_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_sendcode_user(user_id) and user_id != PRIMARY_OWNER_ID:
        await update.message.reply_text("🔒 غير مصرح.")
        return
    await update.message.reply_text("🚧 هذه الميزة قيد التطوير.")

async def lock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("⚠️ هذا الأمر يعمل فقط في المجموعات.")
        return
    if not await is_authorized_in_group(context.bot, chat.id, user_id):
        await update.message.reply_text("⚠️ يجب أن تكون مشرفاً.")
        return
    await db_set_chat_lock(chat.id, True, user_id)
    await update.message.reply_text("🔒 تم قفل المجموعة.")

async def unlock_chat_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("⚠️ هذا الأمر يعمل فقط في المجموعات.")
        return
    if not await is_authorized_in_group(context.bot, chat.id, user_id):
        await update.message.reply_text("⚠️ يجب أن تكون مشرفاً.")
        return
    await db_set_chat_lock(chat.id, False)
    await update.message.reply_text("🔓 تم فتح المجموعة.")

async def schedule_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
    if not active:
        await update.message.reply_text("⚠️ اختر قناة أولاً من القائمة الرئيسية.")
        return
    await schedule_menu_callback(update, context)

async def panel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await is_bot_admin(user_id) or user_id == PRIMARY_OWNER_ID:
        await admin_panel_callback(update, context)
    else:
        await update.message.reply_text("🔒 غير مصرح.")

async def set_log_channel_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID and not await is_bot_admin(user_id):
        await update.message.reply_text("🔒 غير مصرح.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("📝 استخدم: /set_log_channel @channel")
        return
    channel = context.args[0]
    await db_set_log_channel(channel)
    await update.message.reply_text(f"✅ تم تعيين قناة التقارير: {channel}")

async def register_hidden_owner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != PRIMARY_OWNER_ID:
        await update.message.reply_text("🔒 غير مصرح.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("📝 استخدم: /register_hidden_owner <user_id>")
        return
    owner_id = int(context.args[0])
    chat = update.effective_chat
    async def _add(conn):
        await conn.execute("INSERT OR IGNORE INTO hidden_owner_groups (chat_id, owner_id) VALUES (?, ?)", (chat.id, owner_id))
        await conn.commit()
    await execute_db(_add)
    await update.message.reply_text(f"✅ تم تسجيل المالك المخفي {owner_id}")

async def add_hidden_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
        await update.message.reply_text("🔒 غير مصرح.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("📝 استخدم: /add_hidden_admin <user_id>")
        return
    admin_id = int(context.args[0])
    chat = update.effective_chat
    async def _add(conn):
        await conn.execute("INSERT OR IGNORE INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?, ?, ?, ?)",
                          (chat.id, admin_id, user_id, utc_now_iso()))
        await conn.commit()
    await execute_db(_add)
    await update.message.reply_text(f"✅ تم إضافة المشرف المخفي {admin_id}")

async def remove_hidden_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
        await update.message.reply_text("🔒 غير مصرح.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("📝 استخدم: /remove_hidden_admin <user_id>")
        return
    admin_id = int(context.args[0])
    chat = update.effective_chat
    async def _remove(conn):
        await conn.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat.id, admin_id))
        await conn.commit()
    await execute_db(_remove)
    await update.message.reply_text(f"✅ تم إزالة المشرف المخفي {admin_id}")

async def list_hidden_admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
        await update.message.reply_text("🔒 غير مصرح.")
        return
    chat = update.effective_chat
    async def _get(conn):
        cur = await conn.execute("SELECT admin_id FROM hidden_admins WHERE chat_id=?", (chat.id,))
        return [row[0] for row in await cur.fetchall()]
    admins = await execute_db(_get)
    if not admins:
        await update.message.reply_text("📭 لا يوجد مشرفين مخفيين.")
        return
    text = "👤 **المشرفين المخفيين**\n━━━━━━━━━━━━━━━━━━━━━━\n"
    for admin in admins:
        text += f"• `{admin}`\n"
    await update.message.reply_text(text)

async def handle_moderation_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("⚠️ هذا الأمر يعمل فقط في المجموعات.")
        return
    if not await is_authorized_in_group(context.bot, chat.id, user_id):
        await update.message.reply_text("⚠️ يجب أن تكون مشرفاً.")
        return
    command = update.message.text.split()[0].lower()[1:]
    args = context.args
    
    if command == "ban" and len(args) >= 1:
        target_id = int(args[0])
        reason = " ".join(args[1:]) if len(args) > 1 else "لا يوجد سبب"
        try:
            await context.bot.ban_chat_member(chat.id, target_id)
            await update.message.reply_text(f"✅ تم حظر المستخدم {target_id}\nسبب: {reason}")
            async def _log(conn):
                await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                                  (chat.id, target_id, "ban", user_id, reason, utc_now_iso()))
                await conn.commit()
            await execute_db(_log)
        except Exception as e:
            await update.message.reply_text(f"❌ فشل الحظر: {e}")
    
    elif command == "mute" and len(args) >= 1:
        target_id = int(args[0])
        duration = 60
        if len(args) >= 2 and args[1].isdigit():
            duration = int(args[1])
        reason = " ".join(args[2:]) if len(args) > 2 else "لا يوجد سبب"
        until_date = utc_now() + timedelta(minutes=duration)
        try:
            await context.bot.restrict_chat_member(chat.id, target_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date)
            await update.message.reply_text(f"✅ تم كتم المستخدم {target_id} لمدة {duration} دقيقة\nسبب: {reason}")
            async def _log(conn):
                await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, duration_minutes, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                  (chat.id, target_id, "mute", duration, user_id, reason, utc_now_iso()))
                await conn.commit()
            await execute_db(_log)
        except Exception as e:
            await update.message.reply_text(f"❌ فشل الكتم: {e}")
    
    elif command == "warn" and len(args) >= 1:
        target_id = int(args[0])
        reason = " ".join(args[1:]) if len(args) > 1 else "لا يوجد سبب"
        async def _warn(conn):
            await conn.execute("INSERT OR IGNORE INTO user_warnings (user_id, chat_id) VALUES (?, ?)", (target_id, chat.id))
            await conn.execute("UPDATE user_warnings SET warnings = warnings + 1 WHERE user_id = ? AND chat_id = ?", (target_id, chat.id))
            await conn.commit()
            cur = await conn.execute("SELECT warnings FROM user_warnings WHERE user_id = ? AND chat_id = ?", (target_id, chat.id))
            return (await cur.fetchone())[0]
        warnings = await execute_db(_warn)
        await update.message.reply_text(f"⚠️ تم تحذير المستخدم {target_id} (التحذير {warnings})\nسبب: {reason}")
        async def _log(conn):
            await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                              (chat.id, target_id, "warn", user_id, reason, utc_now_iso()))
            await conn.commit()
        await execute_db(_log)
    
    elif command == "kick" and len(args) >= 1:
        target_id = int(args[0])
        reason = " ".join(args[1:]) if len(args) > 1 else "لا يوجد سبب"
        try:
            await context.bot.ban_chat_member(chat.id, target_id)
            await context.bot.unban_chat_member(chat.id, target_id)
            await update.message.reply_text(f"✅ تم طرد المستخدم {target_id}\nسبب: {reason}")
            async def _log(conn):
                await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                                  (chat.id, target_id, "kick", user_id, reason, utc_now_iso()))
                await conn.commit()
            await execute_db(_log)
        except Exception as e:
            await update.message.reply_text(f"❌ فشل الطرد: {e}")
    
    elif command == "restrict" and len(args) >= 1:
        target_id = int(args[0])
        reason = " ".join(args[1:]) if len(args) > 1 else "لا يوجد سبب"
        try:
            await context.bot.restrict_chat_member(chat.id, target_id,
                permissions=ChatPermissions(can_send_messages=False, can_send_media=False))
            await update.message.reply_text(f"✅ تم تقييد المستخدم {target_id}\nسبب: {reason}")
            async def _log(conn):
                await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                                  (chat.id, target_id, "restrict", user_id, reason, utc_now_iso()))
                await conn.commit()
            await execute_db(_log)
        except Exception as e:
            await update.message.reply_text(f"❌ فشل التقييد: {e}")
    
    elif command == "pin":
        if update.message.reply_to_message:
            try:
                await context.bot.pin_chat_message(chat.id, update.message.reply_to_message.message_id)
                await update.message.reply_text("📌 تم تثبيت الرسالة.")
            except Exception as e:
                await update.message.reply_text(f"❌ فشل التثبيت: {e}")
        else:
            await update.message.reply_text("⚠️ قم بالرد على الرسالة التي تريد تثبيتها.")
    
    elif command == "unban" and len(args) >= 1:
        target_id = int(args[0])
        try:
            await context.bot.unban_chat_member(chat.id, target_id)
            await update.message.reply_text(f"✅ تم إلغاء حظر المستخدم {target_id}")
            async def _log(conn):
                await conn.execute("INSERT INTO moderation_log (chat_id, user_id, action, moderator_id, created_at) VALUES (?, ?, ?, ?, ?)",
                                  (chat.id, target_id, "unban", user_id, utc_now_iso()))
                await conn.commit()
            await execute_db(_log)
        except Exception as e:
            await update.message.reply_text(f"❌ فشل إلغاء الحظر: {e}")
    else:
        await update.message.reply_text("⚠️ استخدم:\n/ban <user_id> [سبب]\n/mute <user_id> [دقائق] [سبب]\n/warn <user_id> [سبب]\n/kick <user_id> [سبب]\n/restrict <user_id> [سبب]\n/pin (بالرد على رسالة)\n/unban <user_id>")

async def contests_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await contests_menu_callback(update, context)

async def create_contest_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
        await update.message.reply_text("🔒 غير مصرح.")
        return
    context.user_data['state'] = UserState.WAITING_CONTEST_DETAILS
    await update.message.reply_text("🏆 **إنشاء مسابقة**\n\nأرسل تفاصيل المسابقة بهذا التنسيق:\n`العنوان|الوصف|الجائزة|عدد الأيام`")

async def declare_winner_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_bot_admin(user_id) and user_id != PRIMARY_OWNER_ID:
        await update.message.reply_text("🔒 غير مصرح.")
        return
    await admin_declare_winner_callback(update, context)

async def set_rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("⚠️ هذا الأمر يعمل فقط في المجموعات.")
        return
    if not await is_authorized_in_group(context.bot, chat.id, user_id):
        await update.message.reply_text("⚠️ يجب أن تكون مشرفاً.")
        return
    if not context.args:
        await update.message.reply_text("📝 استخدم: /set_rules <النص>")
        return
    rules_text = " ".join(context.args)
    async def _set(conn):
        await conn.execute("INSERT OR REPLACE INTO group_rules (chat_id, rules_text, updated_by, updated_at) VALUES (?, ?, ?, ?)",
                          (chat.id, rules_text, user_id, utc_now_iso()))
        await conn.commit()
    await execute_db(_set)
    await update.message.reply_text("✅ تم تعيين قوانين المجموعة.")

async def rules_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("⚠️ هذا الأمر يعمل فقط في المجموعات.")
        return
    async def _get(conn):
        cur = await conn.execute("SELECT rules_text FROM group_rules WHERE chat_id=?", (chat.id,))
        row = await cur.fetchone()
        return row[0] if row else None
    rules = await execute_db(_get)
    if rules:
        await update.message.reply_text(f"📜 **قوانين المجموعة**\n━━━━━━━━━━━━━━━━━━━━━━\n{rules}")
    else:
        await update.message.reply_text("📜 لا توجد قوانين مسجلة.")

async def message_handler_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.effective_message
    state = context.user_data.get('state')
    
    if state == UserState.ADDING_POSTS:
        session = context.user_data.get(f"session_{user_id}", [])
        target = context.user_data.get(f"session_target_{user_id}", 15)
        media_type = "text"
        media_file_id = None
        if message.photo:
            media_type = "photo"
            media_file_id = message.photo[-1].file_id
        elif message.video:
            media_type = "video"
            media_file_id = message.video.file_id
        elif message.document:
            media_type = "document"
            media_file_id = message.document.file_id
        elif message.audio:
            media_type = "audio"
            media_file_id = message.audio.file_id
        elif message.voice:
            media_type = "voice"
            media_file_id = message.voice.file_id
        elif message.animation:
            media_type = "animation"
            media_file_id = message.animation.file_id
        else:
            if not message.text:
                await update.message.reply_text("⚠️ أرسل نصاً أو ملف وسائط صالحاً.")
                return
        active = context.user_data.get('active_channel') or await db_get_active_channel(user_id)
        if not active:
            await update.message.reply_text("⚠️ لم يتم تحديد قناة نشطة.")
            return
        text = message.text or message.caption or ""
        post_id = await db_add_post(active, text, media_type, media_file_id)
        session.append(post_id)
        context.user_data[f"session_{user_id}"] = session
        remaining = target - len(session)
        if remaining <= 0:
            context.user_data.pop(f"session_{user_id}", None)
            context.user_data.pop(f"session_target_{user_id}", None)
            context.user_data.pop('state', None)
            await update.message.reply_text(f"✅ تم حفظ {len(session)} منشوراً بنجاح!")
            await main_menu_callback(update, context)
        else:
            await update.message.reply_text(f"✅ تم حفظ منشور ({len(session)}/{target})\nأرسل المزيد أو انتهِ.")
        return
    
    elif state == UserState.WAITING_CHANNEL_ID:
        channel_id = message.text.strip()
        if not channel_id.startswith('@') and not channel_id.lstrip('-').isdigit():
            await update.message.reply_text("⚠️ أرسل معرف قناة صحيح (مثال: @my_channel)")
            return
        if channel_id.startswith('@'):
            try:
                chat = await context.bot.get_chat(channel_id)
                channel_name = chat.title or channel_id
                channel_id = str(chat.id)
            except:
                await update.message.reply_text("⚠️ لا يمكن الوصول إلى القناة. تأكد من وجود البوت مشرفاً فيها.")
                return
        else:
            channel_name = channel_id
        ch_db_id = await db_add_channel(user_id, channel_id, channel_name)
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم إضافة القناة {channel_name} بنجاح!")
        await main_menu_callback(update, context)
        return
    
    elif state == UserState.WAITING_INTERVAL_MINUTES:
        try:
            minutes = int(message.text.strip())
            if minutes < 1:
                raise ValueError
            ch_db_id = context.user_data.get('schedule_ch_id')
            if ch_db_id:
                await db_save_schedule(ch_db_id, 'interval_minutes', interval_minutes=minutes)
                await db_set_next_publish_date(ch_db_id, None)
                context.user_data.pop('state', None)
                await update.message.reply_text(f"✅ تم تعيين الفاصل إلى {minutes} دقيقة.")
                await schedule_menu_callback(update, context)
        except:
            await update.message.reply_text("⚠️ أرسل عدداً صحيحاً موجباً.")
        return
    
    elif state == UserState.WAITING_INTERVAL_HOURS:
        try:
            hours = int(message.text.strip())
            if hours < 1:
                raise ValueError
            ch_db_id = context.user_data.get('schedule_ch_id')
            if ch_db_id:
                await db_save_schedule(ch_db_id, 'interval_hours', interval_hours=hours)
                await db_set_next_publish_date(ch_db_id, None)
                context.user_data.pop('state', None)
                await update.message.reply_text(f"✅ تم تعيين الفاصل إلى {hours} ساعة.")
                await schedule_menu_callback(update, context)
        except:
            await update.message.reply_text("⚠️ أرسل عدداً صحيحاً موجباً.")
        return
    
    elif state == UserState.WAITING_INTERVAL_DAYS:
        try:
            days = int(message.text.strip())
            if days < 1:
                raise ValueError
            ch_db_id = context.user_data.get('schedule_ch_id')
            if ch_db_id:
                await db_save_schedule(ch_db_id, 'interval_days', interval_days=days)
                await db_set_next_publish_date(ch_db_id, None)
                context.user_data.pop('state', None)
                await update.message.reply_text(f"✅ تم تعيين الفاصل إلى {days} يوم.")
                await schedule_menu_callback(update, context)
        except:
            await update.message.reply_text("⚠️ أرسل عدداً صحيحاً موجباً.")
        return
    
    elif state == UserState.WAITING_DATES:
        dates_text = message.text.strip()
        dates = [d.strip() for d in dates_text.split(',')]
        valid_dates = []
        for d in dates:
            try:
                datetime.strptime(d, '%Y-%m-%d')
                valid_dates.append(d)
            except:
                pass
        if not valid_dates:
            await update.message.reply_text("⚠️ أرسل تواريخ صحيحة بصيغة YYYY-MM-DD مفصولة بفواصل.")
            return
        ch_db_id = context.user_data.get('schedule_ch_id')
        if ch_db_id:
            await db_save_schedule(ch_db_id, 'dates', specific_dates=json.dumps(valid_dates))
            await db_set_next_publish_date(ch_db_id, None)
            context.user_data.pop('state', None)
            await update.message.reply_text("✅ تم حفظ التواريخ.")
            await schedule_menu_callback(update, context)
        return
    
    elif state == UserState.WAITING_PUBLISH_TIME:
        time_text = message.text.strip()
        try:
            datetime.strptime(time_text, '%H:%M')
            ch_db_id = context.user_data.get('schedule_ch_id')
            if ch_db_id:
                await db_save_schedule(ch_db_id, 'interval_minutes', publish_time=time_text)
                context.user_data.pop('state', None)
                await update.message.reply_text(f"✅ تم تعيين وقت النشر إلى {time_text}.")
                await schedule_menu_callback(update, context)
        except:
            await update.message.reply_text("⚠️ أرسل وقتاً صحيحاً بصيغة HH:MM")
        return
    
    elif state == UserState.WAITING_CRON:
        cron_exp = message.text.strip()
        if len(cron_exp.split()) != 5:
            await update.message.reply_text("⚠️ أرسل تعبير CRON صحيح (5 أجزاء).")
            return
        ch_db_id = context.user_data.get('schedule_ch_id')
        if ch_db_id:
            await db_save_schedule(ch_db_id, 'cron', cron_expression=cron_exp)
            await db_set_next_publish_date(ch_db_id, None)
            context.user_data.pop('state', None)
            await update.message.reply_text(f"✅ تم تعيين CRON: {cron_exp}")
            await schedule_menu_callback(update, context)
        return
    
    elif state == UserState.WAITING_REMINDER_DAYS:
        try:
            days = int(message.text.strip())
            if 1 <= days <= 10:
                await db_update_reminder_settings(user_id, reminder_days_before=days)
                context.user_data.pop('state', None)
                await update.message.reply_text(f"✅ تم تعيين أيام التذكير إلى {days}.")
                await reminder_menu_callback(update, context)
            else:
                await update.message.reply_text("⚠️ أرسل عدداً بين 1 و 10.")
        except:
            await update.message.reply_text("⚠️ أرسل عدداً صحيحاً.")
        return
    
    elif state == UserState.WAITING_ADD_ADMIN:
        try:
            admin_id = int(message.text.strip())
            await db_add_bot_admin(admin_id)
            context.user_data.pop('state', None)
            await update.message.reply_text(f"✅ تم إضافة المستخدم {admin_id} كمشرف.")
            await admin_panel_callback(update, context)
        except:
            await update.message.reply_text("⚠️ أرسل معرف مستخدم صحيح.")
        return
    
    elif state == UserState.WAITING_REMOVE_ADMIN:
        try:
            admin_id = int(message.text.strip())
            await db_remove_bot_admin(admin_id)
            context.user_data.pop('state', None)
            await update.message.reply_text(f"✅ تم إزالة المستخدم {admin_id} من المشرفين.")
            await admin_panel_callback(update, context)
        except:
            await update.message.reply_text("⚠️ أرسل معرف مستخدم صحيح.")
        return
    
    elif state == UserState.WAITING_BACKUP_INTERVAL:
        try:
            hours = int(message.text.strip())
            if hours < 1:
                raise ValueError
            await db_set_backup_interval(hours * 3600)
            context.user_data.pop('state', None)
            await update.message.reply_text(f"✅ تم تعيين فاصل النسخ الاحتياطي إلى {hours} ساعة.")
            await admin_backup_settings_callback(update, context)
        except:
            await update.message.reply_text("⚠️ أرسل عدداً صحيحاً موجباً.")
        return
    
    elif state == UserState.WAITING_UPDATE_TEXT:
        text = message.text.strip()
        users = await db_get_all_users()
        sent = 0
        for uid in users[:100]:
            try:
                await context.bot.send_message(uid, f"📢 **تحديث جديد**\n\n{text}")
                sent += 1
                await asyncio.sleep(0.1)
            except:
                pass
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم إرسال التحديث لـ {sent} مستخدم.")
        await admin_panel_callback(update, context)
        return
    
    elif state == UserState.WAITING_UPDATE_CHANNEL:
        channel = message.text.strip()
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم تعيين قناة التحديثات: {channel}")
        await admin_panel_callback(update, context)
        return
    
    elif state == UserState.WAITING_FORCE_CHANNEL:
        channel = message.text.strip()
        if not channel.startswith('@'):
            channel = f"@{channel}"
        await db_set_force_subscribe(True, channel)
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم تعيين قناة الاشتراك الإجباري: {channel}")
        await admin_panel_callback(update, context)
        return
    
    elif state == UserState.WAITING_BROADCAST_TEXT:
        text = message.text.strip()
        users = await db_get_all_users()
        sent = 0
        for uid in users:
            try:
                await context.bot.send_message(uid, f"📨 **بث عام**\n\n{text}")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم إرسال البث لـ {sent} مستخدم.")
        await admin_panel_callback(update, context)
        return
    
    elif state == UserState.WAITING_SENDCODE_USER:
        try:
            sendcode_id = int(message.text.strip())
            await db_add_sendcode_user(sendcode_id)
            context.user_data.pop('state', None)
            await update.message.reply_text(f"✅ تم إضافة المستخدم {sendcode_id}.")
            await admin_panel_callback(update, context)
        except:
            await update.message.reply_text("⚠️ أرسل معرف مستخدم صحيح.")
        return
    
    elif state == UserState.WAITING_LOG_CHANNEL:
        channel = message.text.strip()
        await db_set_log_channel(channel)
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم تعيين قناة التقارير: {channel}")
        await admin_panel_callback(update, context)
        return
    
    elif state == UserState.WAITING_ADD_REPLY:
        lines = message.text.strip().split('\n')
        if len(lines) < 2:
            await update.message.reply_text("⚠️ أرسل الكلمة المفتاحية والرد في سطرين.")
            return
        keyword = lines[0].strip().lower()
        reply = '\n'.join(lines[1:]).strip()
        if not keyword or not reply:
            await update.message.reply_text("⚠️ لا يمكن أن تكون الكلمة أو الرد فارغين.")
            return
        await db_add_reply(keyword, reply)
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم إضافة الرد للكلمة '{keyword}'.")
        await admin_panel_callback(update, context)
        return
    
    elif state == UserState.WAITING_DEL_REPLY:
        keyword = message.text.strip().lower()
        if not keyword:
            await update.message.reply_text("⚠️ أرسل الكلمة المفتاحية.")
            return
        await db_delete_reply(keyword)
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم حذف الرد للكلمة '{keyword}'.")
        await admin_panel_callback(update, context)
        return
    
    elif state == UserState.WAITING_ADD_BANNED_WORD:
        word = message.text.strip().lower()
        if not word:
            await update.message.reply_text("⚠️ أرسل كلمة صالحة.")
            return
        await db_add_banned_word(-1, word, user_id)
        await rebuild_banned_patterns()
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم إضافة الكلمة '{word}'.")
        await admin_panel_callback(update, context)
        return
    
    elif state == UserState.WAITING_REMOVE_BANNED_WORD:
        word = message.text.strip().lower()
        if not word:
            await update.message.reply_text("⚠️ أرسل كلمة صالحة.")
            return
        await db_remove_banned_word(-1, word)
        await rebuild_banned_patterns()
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم حذف الكلمة '{word}'.")
        await admin_panel_callback(update, context)
        return
    
    elif state == UserState.WAITING_CONTEST_DETAILS:
        parts = message.text.strip().split('|')
        if len(parts) < 4:
            await update.message.reply_text("⚠️ أرسل التفاصيل بالتنسيق: العنوان|الوصف|الجائزة|عدد الأيام")
            return
        title = parts[0].strip()
        description = parts[1].strip()
        prize = parts[2].strip()
        try:
            days = int(parts[3].strip())
            end_date = utc_now() + timedelta(days=days)
        except:
            await update.message.reply_text("⚠️ عدد الأيام يجب أن يكون رقماً صحيحاً.")
            return
        await db_create_contest(user_id, title, description, prize, end_date)
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم إنشاء المسابقة '{title}' بنجاح!")
        await admin_panel_callback(update, context)
        return
    
    elif state == UserState.WAITING_CONTEST_ANSWER:
        contest_id = context.user_data.get('contest_join_id')
        if not contest_id:
            await update.message.reply_text("❌ لا توجد مسابقة نشطة.")
            return
        answer = message.text.strip()
        if answer.lower() == '/skip':
            context.user_data.pop('state', None)
            context.user_data.pop('contest_join_id', None)
            await update.message.reply_text("⏭️ تم تخطي المسابقة.")
            return
        success = await db_participate_in_contest(user_id, contest_id, answer)
        context.user_data.pop('state', None)
        context.user_data.pop('contest_join_id', None)
        if success:
            await update.message.reply_text("✅ تم تسجيل مشاركتك!")
        else:
            await update.message.reply_text("❌ فشل التسجيل.")
        await contests_menu_callback(update, context)
        return
    
    elif state == UserState.WAITING_GROUP_BANNED_WORD:
        chat_id = context.user_data.get('banned_words_chat_id')
        if not chat_id:
            await update.message.reply_text("❌ خطأ.")
            return
        word = message.text.strip().lower()
        if not word:
            await update.message.reply_text("⚠️ أرسل كلمة صالحة.")
            return
        success = await db_add_banned_word(chat_id, word, user_id)
        context.user_data.pop('state', None)
        if success:
            await update.message.reply_text(f"✅ تم إضافة الكلمة '{word}'.")
        else:
            await update.message.reply_text("❌ الكلمة موجودة مسبقاً.")
        await security_banned_words_menu_callback(update, context)
        return
    
    elif state == UserState.WAITING_REMOVE_GROUP_BANNED_WORD:
        chat_id = context.user_data.get('banned_words_chat_id')
        if not chat_id:
            await update.message.reply_text("❌ خطأ.")
            return
        word = message.text.strip().lower()
        if not word:
            await update.message.reply_text("⚠️ أرسل كلمة صالحة.")
            return
        await db_remove_banned_word(chat_id, word)
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم حذف الكلمة '{word}'.")
        await security_banned_words_menu_callback(update, context)
        return
    
    elif state == UserState.WAITING_TICKET_MESSAGE:
        msg = message.text.strip()
        if not msg:
            await update.message.reply_text("⚠️ أرسل رسالتك.")
            return
        username = update.effective_user.username or f"User_{user_id}"
        ticket_num = await db_create_ticket(user_id, username, msg)
        context.user_data.pop('state', None)
        await update.message.reply_text(f"✅ تم إنشاء تذكرة دعم برقم #{ticket_num}")
        await main_menu_callback(update, context)
        return
    
    else:
        if message.text:
            reply = await db_get_reply(message.text.lower())
            if reply:
                await update.message.reply_text(reply)
                return
        if message.text and contains_banned_word(message.text):
            try:
                await message.delete()
                await update.message.reply_text("🚫 تم حذف الرسالة لاحتوائها على كلمات محظورة.")
            except:
                pass
            return
        await update.message.reply_text("👋 مرحباً! استخدم /start للبدء.")

async def filter_messages_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    user_id = update.effective_user.id
    
    if await is_chat_locked(chat.id):
        try:
            await message.delete()
        except:
            pass
        return
    
    text = message.text or message.caption or ""
    if text and contains_banned_word(text):
        try:
            await message.delete()
            await context.bot.send_message(chat.id, f"🚫 {update.effective_user.first_name}، تم حذف الرسالة.")
        except:
            pass
        return
    
    settings = await db_get_security_settings(chat.id)
    
    if settings.get('links', False) and text:
        import re
        if re.search(r'https?://[^\s]+|t\.me/[^\s]+|@[^\s]+', text):
            try:
                await message.delete()
                await context.bot.send_message(chat.id, f"🔗 {update.effective_user.first_name}، الروابط غير مسموحة.")
            except:
                pass
            return
    
    if settings.get('mentions', False) and text and '@' in text:
        try:
            await message.delete()
            await context.bot.send_message(chat.id, f"@ {update.effective_user.first_name}، المعرفات غير مسموحة.")
        except:
            pass
        return
    
    media_types = {
        'delete_videos': 'video',
        'delete_audio': 'audio',
        'delete_animation': 'animation',
        'delete_documents': 'document',
        'delete_stickers': 'sticker',
        'delete_forwarded': 'forward',
        'delete_polls': 'poll',
        'delete_games': 'game',
        'delete_voice': 'voice',
        'delete_video_note': 'video_note'
    }
    
    for setting_key, media_type in media_types.items():
        if settings.get(setting_key, False):
            if media_type == 'forward' and message.forward_from:
                try:
                    await message.delete()
                except:
                    pass
                return
            elif media_type == 'poll' and message.poll:
                try:
                    await message.delete()
                except:
                    pass
                return
            elif hasattr(message, media_type) and getattr(message, media_type):
                try:
                    await message.delete()
                except:
                    pass
                return

async def chat_join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    chat_id = request.chat.id
    settings = await db_get_security_settings(chat_id)
    if settings.get('welcome_enabled', False):
        welcome_text = settings.get('welcome_text', "مرحباً {user} في {chat} 🤍").format(
            user=request.from_user.first_name, chat=request.chat.title)
        try:
            await request.approve()
            await context.bot.send_message(chat_id, welcome_text)
        except:
            pass
    else:
        try:
            await request.approve()
        except:
            pass

async def new_chat_members_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            await db_add_group(chat.id, chat.title, chat.username or "")
            await db_sync_group_admins(chat.id, context.bot)
            await update.message.reply_text("✅ تم تفعيل البوت في المجموعة!")
        else:
            settings = await db_get_security_settings(chat.id)
            if settings.get('welcome_enabled', False):
                welcome_text = settings.get('welcome_text', "مرحباً {user} في {chat} 🤍").format(
                    user=member.first_name, chat=chat.title)
                await update.message.reply_text(welcome_text)

async def left_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    member = update.message.left_chat_member
    if member.id == context.bot.id:
        async def _remove(conn):
            await conn.execute("UPDATE bot_groups SET banned = 1 WHERE chat_id = ?", (chat.id,))
            await conn.commit()
        await execute_db(_remove)
    else:
        settings = await db_get_security_settings(chat.id)
        if settings.get('goodbye_enabled', False):
            goodbye_text = settings.get('goodbye_text', "وداعاً {user} 👋").format(
                user=member.first_name, chat=chat.title)
            await update.message.reply_text(goodbye_text)

async def track_chat_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member = update.chat_member
    if chat_member.new_chat_member.user.id == context.bot.id:
        if chat_member.new_chat_member.status == 'member':
            chat = chat_member.chat
            await db_add_group(chat.id, chat.title, chat.username or "")
            await db_sync_group_admins(chat.id, context.bot)

async def on_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            await db_add_group(chat.id, chat.title, chat.username or "")
            await db_sync_group_admins(chat.id, context.bot)
            await update.message.reply_text("✅ تم تفعيل البوت في المجموعة!")

async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    settings = await db_get_security_settings(chat.id)
    if settings.get('delete_service', False):
        try:
            await update.message.delete()
        except:
            pass

async def pre_checkout_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await db_add_subscription_days(user_id, 30)
    await update.message.reply_text("✅ تم تفعيل اشتراكك بنجاح!")

async def create_backup():
    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        backup_file = BACKUP_DIR / f"backup_{utc_now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, backup_file)
        logger.info(f"✅ تم إنشاء نسخة احتياطية: {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"❌ فشل إنشاء النسخة الاحتياطية: {e}")
        return None

async def incremental_backup():
    return await create_backup()

async def list_backups():
    BACKUP_DIR.mkdir(exist_ok=True)
    return sorted(BACKUP_DIR.glob("*.db"), key=lambda x: x.stat().st_mtime, reverse=True)

async def restore_backup(backup_path: Path):
    if not backup_path.exists():
        raise FileNotFoundError(f"الملف {backup_path} غير موجود")
    current_backup = BACKUP_DIR / f"pre_restore_{utc_now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DB_PATH, current_backup)
    shutil.copy2(backup_path, DB_PATH)
    logger.info(f"✅ تم استعادة النسخة: {backup_path}")

async def auto_publish_loop_improved(bot):
    await asyncio.sleep(5)
    while True:
        try:
            publish_interval = await db_get_publish_interval_seconds()
            async def _get_due_channels(conn):
                now_utc_iso = utc_now().isoformat()
                cur = await conn.execute("""
                    SELECT uc.id, uc.channel_id, u.user_id
                    FROM user_channels uc
                    JOIN users u ON uc.user_id = u.user_id
                    LEFT JOIN schedule s ON uc.id = s.channel_db_id
                    WHERE u.auto_publish = 1 AND u.banned = 0 AND uc.banned = 0
                      AND (s.next_publish_date IS NULL OR s.next_publish_date <= ?)
                    ORDER BY COALESCE(s.next_publish_date, '1970-01-01') ASC LIMIT ?
                """, (now_utc_iso, MAX_CHANNELS_PER_CYCLE))
                return await cur.fetchall()
            rows = await execute_db(_get_due_channels)
            for row in rows:
                ch_db_id, ch_tele_id, user_id = row
                if not await db_has_active_subscription(user_id) and not await db_has_used_trial(user_id):
                    continue
                post = await db_get_next_post(ch_db_id)
                if not post:
                    auto_recycle = await db_get_auto_recycle(user_id)
                    total = await db_get_posts_count(ch_db_id)
                    if auto_recycle and total > 0:
                        await db_reset_all_posts_to_unpublished(ch_db_id)
                        logger.info(f"♻️ إعادة تدوير تلقائي {ch_tele_id}")
                    continue
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
                    await db_mark_published(post['id'])
                    await db_set_last_publish(ch_db_id, utc_now())
                    await db_update_next_publish_date(ch_db_id)
                except Exception as e:
                    logger.error(f"❌ فشل نشر المنشور {post['id']}: {e}")
                await asyncio.sleep(random.uniform(2, 5))
            await asyncio.sleep(publish_interval)
        except Exception as e:
            logger.error(f"خطأ في حلقة النشر: {e}")
            await asyncio.sleep(30)

async def auto_backup():
    while True:
        try:
            await asyncio.sleep(AUTO_BACKUP_SLEEP)
            if await db_get_auto_backup():
                await create_backup()
        except Exception as e:
            logger.error(f"خطأ في النسخ الاحتياطي: {e}")
            await asyncio.sleep(300)

async def run_scheduled_posts_loop_improved(bot):
    while True:
        await asyncio.sleep(SCHEDULED_POSTS_SLEEP)
        try:
            now_utc = utc_now()
            async def _get_due(conn):
                cur = await conn.execute("SELECT id, chat_id, text, fail_count FROM scheduled_posts WHERE publish_time <= ? AND fail_count < 5 LIMIT 50", (now_utc.isoformat(),))
                return await cur.fetchall()
            posts = await execute_db(_get_due)
            for post_id, chat_id, text, fail_count in posts:
                try:
                    await bot.send_message(chat_id, text)
                    async def _delete(conn):
                        await conn.execute("DELETE FROM scheduled_posts WHERE id = ?", (post_id,))
                        await conn.commit()
                    await execute_db(_delete)
                except Exception as e:
                    new_fail = fail_count + 1
                    async def _update(conn):
                        await conn.execute("UPDATE scheduled_posts SET fail_count = ? WHERE id = ?", (new_fail, post_id))
                        await conn.commit()
                    await execute_db(_update)
                    if new_fail >= 5:
                        async def _delete(conn):
                            await conn.execute("DELETE FROM scheduled_posts WHERE id = ?", (post_id,))
                            await conn.commit()
                        await execute_db(_delete)
        except:
            pass

async def send_reminders_loop_improved(bot):
    while True:
        await asyncio.sleep(REMINDERS_SLEEP)
        try:
            async def _get_users(conn):
                cur = await conn.execute("""
                    SELECT u.user_id, urs.reminder_days_before, urs.notification_lang
                    FROM users u JOIN user_reminder_settings urs ON u.user_id = urs.user_id
                    WHERE urs.subscription_reminder = 1 AND u.subscription_end IS NOT NULL
                      AND datetime(u.subscription_end) > datetime('now')
                      AND julianday(u.subscription_end) - julianday('now') <= urs.reminder_days_before
                """)
                return await cur.fetchall()
            users = await execute_db(_get_users)
            for user_id, days_before, lang in users:
                async def _get_days(conn):
                    cur = await conn.execute("SELECT julianday(subscription_end) - julianday('now') FROM users WHERE user_id = ?", (user_id,))
                    row = await cur.fetchone()
                    return int(row[0]) if row else 0
                days_left = await execute_db(_get_days)
                if days_left <= 0:
                    continue
                original_lang = user_language.get(user_id, 'ar')
                user_language[user_id] = lang
                text = get_text(user_id, 'subscription_warning').format(days_left)
                try:
                    await bot.send_message(user_id, text)
                except:
                    pass
                user_language[user_id] = original_lang
        except:
            pass

async def cleanup_expired_sessions_improved():
    while True:
        await asyncio.sleep(CLEANUP_SLEEP)
        try:
            now = time.time()
            async def _cleanup(conn):
                await conn.execute("DELETE FROM web_sessions WHERE expires < ?", (now,))
                await conn.commit()
            await execute_db(_cleanup)
        except:
            pass

async def self_ping_loop():
    import aiohttp
    while True:
        try:
            await asyncio.sleep(300)
            port = int(os.getenv("PORT", "10000"))
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:{port}/health", timeout=5) as resp:
                    if resp.status == 200:
                        logger.debug("✅ Ping ناجح")
        except:
            pass

async def broadcast_stats_periodically():
    while True:
        await asyncio.sleep(60)
        try:
            total, banned, posts, groups, channels = await db_stats()
            logger.info(f"📊 إحصائيات: مستخدمين={total}, محظورين={banned}, منشورات={posts}, مجموعات={groups}, قنوات={channels}")
        except:
            pass

async def cleanup_points_cache():
    while True:
        await asyncio.sleep(3600)
        _user_points_last_hour.clear()

async def memory_monitor():
    while True:
        try:
            ram = get_ram_usage()
            if ram['percent'] > MEMORY_LIMIT_PERCENT:
                await memory_optimizer()
            await asyncio.sleep(60)
        except:
            await asyncio.sleep(60)

async def memory_optimizer_loop():
    while True:
        await asyncio.sleep(300)
        try:
            await memory_optimizer()
        except:
            pass

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
                winner_id = await db_get_random_participant(contest_id)
                if winner_id:
                    await db_set_contest_winner(contest_id, winner_id)
                    try:
                        await bot.send_message(winner_id, f"🏆 **تهانينا!** فزت في مسابقة **{contest['title']}**! 🎁")
                    except:
                        pass
                else:
                    async def _close(conn):
                        await conn.execute("UPDATE contests SET status = 'finished' WHERE id = ?", (contest_id,))
                        await conn.commit()
                    await execute_db(_close)
        except:
            pass

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
                    await asyncio.sleep(0.5)
                except:
                    pass
            logger.info(f"✅ تم تحديث صلاحيات {len(groups)} مجموعة")
        except Exception as e:
            logger.error(f"خطأ في حلقة تحديث الصلاحيات: {e}")
        await asyncio.sleep(3600)

async def db_increment_fail_count(post_id: int):
    async def _inc(conn):
        await conn.execute("UPDATE posts SET fail_count = fail_count + 1 WHERE id = ?", (post_id,))
        await conn.commit()
    return await execute_db(_inc)

class TaskManager:
    def __init__(self, max_tasks=50, max_concurrent=10):
        self.tasks = set()
        self._lock = asyncio.Lock()
        self.max_tasks = max_tasks
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def create_task(self, coro: Awaitable) -> asyncio.Task:
        async def _wrapped():
            async with self.semaphore:
                return await coro
        if len(self.tasks) >= self.max_tasks:
            try:
                oldest = next(iter(self.tasks))
                oldest.cancel()
            except StopIteration:
                pass
        task = asyncio.create_task(_wrapped())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def cancel_all(self):
        for task in list(self.tasks):
            if not task.done():
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

task_manager = TaskManager(max_concurrent=10)

async def safe_loop(coro_func, name="background_loop"):
    while True:
        try:
            await coro_func()
        except asyncio.CancelledError:
            logger.info(f"🛑 تم إلغاء الحلقة: {name}")
            break
        except Exception as e:
            logger.error(f"❌ تعطلت الحلقة {name}: {e}. إعادة التشغيل بعد 10 ثوانٍ...")
            await asyncio.sleep(10)

async def global_error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        error = context.error
        error_id = f"ERR_{int(time.time())}"
        logger.error(f"⚠️ خطأ {error_id}: {error}")
        if isinstance(error, Conflict):
            logger.warning(f"⚠️ تعارض في التحديثات: {error}")
            return
        if isinstance(error, Forbidden):
            logger.warning(f"⚠️ البوت محظور: {error}")
            return
        if isinstance(error, TimedOut):
            logger.warning(f"⏱️ انتهت المهلة: {error}")
            return
        if update and update.effective_user and context and context.bot:
            try:
                await context.bot.send_message(update.effective_user.id, f"❌ حدث خطأ: `{str(error)[:300]}`\n(الرمز: `{error_id}`)")
            except:
                pass
    except Exception as e:
        logger.error(f"فشل معالج الأخطاء نفسه: {e}")

async def setup_unified_web_server(application, port: int):
    from aiohttp import web
    from telegram import Update
    
    if not hasattr(application, 'web_app') or application.web_app is None:
        application.web_app = web.Application()
    
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
    application.web_app.router.add_get('/health', health_check_handler)
    application.web_app.router.add_post(f"/{TOKEN}", webhook_handler)
    
    runner = web.AppRunner(application.web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"✅ خادم الويب يعمل على المنفذ {port}")
    return site

async def index_handler(request):
    html = """<html><head><title>ريلاكس مانيجر</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px; direction: rtl;">
        <h1>🌿 ريلاكس مانيجر</h1>
        <p>✅ البوت يعمل بكفاءة</p>
        <p>📊 <a href="/health">التحقق من الصحة</a></p>
        <p style="color: #666; font-size: 12px;">الإصدار 22.8.0</p>
    </body></html>"""
    return web.Response(text=html, content_type="text/html")

async def health_check_handler(request):
    try:
        async def _check(conn):
            cur = await conn.execute("SELECT 1")
            return await cur.fetchone() is not None
        db_healthy = await execute_db(_check)
        ram = get_ram_usage()
        return web.json_response({
            "status": "healthy" if db_healthy else "unhealthy",
            "database": db_healthy,
            "memory": ram,
            "uptime": time.time() - getattr(health_check_handler, 'start_time', time.time())
        }, status=200 if db_healthy else 503)
    except Exception as e:
        return web.json_response({"status": "unhealthy", "error": str(e)}, status=503)

async def run_polling_safe(application):
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

async def main():
    try:
        logger.info("🚀 بدء تشغيل البوت...")
        await init_db_improved()
        logger.info("✅ قاعدة البيانات جاهزة")
        
        try:
            words = load_banned_words_from_file("banned_words.txt")
            if words:
                async def _import(conn):
                    imported = 0
                    for word in words:
                        try:
                            await conn.execute("INSERT OR IGNORE INTO banned_words (word, chat_id, added_by, added_at) VALUES (?, ?, ?, ?)",
                                              (word, -1, PRIMARY_OWNER_ID, utc_now_iso()))
                            imported += 1
                        except:
                            continue
                    await conn.commit()
                    return imported
                imported_count = await execute_db(_import)
                logger.info(f"✅ تم استيراد {imported_count} كلمة محظورة")
                await rebuild_banned_patterns()
        except Exception as e:
            logger.error(f"❌ فشل استيراد الكلمات المحظورة: {e}")
        
        load_all_languages()
        logger.info("✅ تم تحميل اللغات")
        
        if USE_PROXY:
            request = HTTPXRequest(proxy_url=PROXY_URL, read_timeout=60.0, write_timeout=30.0, connect_timeout=30.0,
                                  pool_timeout=10.0, connection_pool_size=MAX_CONNECTIONS)
            application = Application.builder().token(TOKEN).request(request).build()
        else:
            request = HTTPXRequest(read_timeout=60.0, write_timeout=30.0, connect_timeout=30.0,
                                  pool_timeout=10.0, connection_pool_size=MAX_CONNECTIONS)
            application = Application.builder().token(TOKEN).request(request).build()
        logger.info("✅ تم إنشاء التطبيق")
        
        application.add_error_handler(global_error_handler)
        
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
        
        application.add_handler(CallbackQueryHandler(main_menu_callback, pattern=f"^{CallbackData.MAIN_MENU}$"))
        application.add_handler(CallbackQueryHandler(back_callback, pattern=f"^{CallbackData.BACK}$"))
        application.add_handler(CallbackQueryHandler(cancel_session_callback, pattern=f"^{CallbackData.CANCEL_SESSION}$"))
        application.add_handler(CallbackQueryHandler(add_channel_callback, pattern=f"^{CallbackData.CHANNELS_ADD}$"))
        application.add_handler(CallbackQueryHandler(my_channels_callback, pattern=f"^{CallbackData.CHANNELS_MY}$"))
        application.add_handler(CallbackQueryHandler(delete_channel_callback, pattern=f"^{CallbackData.CHANNELS_DELETE_PREFIX}"))
        application.add_handler(CallbackQueryHandler(select_channel_callback, pattern=f"^{CallbackData.CHANNELS_SELECT_PREFIX}"))
        application.add_handler(CallbackQueryHandler(add_15_posts_callback, pattern=f"^{CallbackData.POSTS_ADD_15}$"))
        application.add_handler(CallbackQueryHandler(publish_one_callback, pattern=f"^{CallbackData.POSTS_PUBLISH_ONE}$"))
        application.add_handler(CallbackQueryHandler(my_posts_callback, pattern=f"^{CallbackData.POSTS_MY}$"))
        application.add_handler(CallbackQueryHandler(recycle_posts_callback, pattern=f"^{CallbackData.POSTS_RECYCLE}$"))
        application.add_handler(CallbackQueryHandler(delete_single_post_callback, pattern=f"^{CallbackData.POSTS_DELETE_SINGLE_PREFIX}"))
        application.add_handler(CallbackQueryHandler(confirm_clear_all_posts_callback, pattern=f"^{CallbackData.POSTS_CONFIRM_CLEAR_ALL_PREFIX}"))
        application.add_handler(CallbackQueryHandler(clear_all_posts_callback, pattern=f"^{CallbackData.POSTS_CLEAR_ALL_PREFIX}"))
        application.add_handler(CallbackQueryHandler(pending_stats_callback, pattern=f"^{CallbackData.STATS_PENDING}$"))
        application.add_handler(CallbackQueryHandler(full_stats_callback, pattern=f"^{CallbackData.STATS_FULL}$"))
        application.add_handler(CallbackQueryHandler(my_groups_callback, pattern=f"^{CallbackData.GROUPS_MY}$"))
        application.add_handler(CallbackQueryHandler(group_settings_callback, pattern=f"^{CallbackData.GROUPS_SETTINGS_PREFIX}"))
        application.add_handler(CallbackQueryHandler(settings_menu_callback, pattern=f"^{CallbackData.SETTINGS_MENU}$"))
        application.add_handler(CallbackQueryHandler(toggle_auto_publish_callback, pattern=f"^{CallbackData.SETTINGS_TOGGLE_AUTO_PUBLISH}$"))
        application.add_handler(CallbackQueryHandler(toggle_auto_recycle_callback, pattern=f"^{CallbackData.SETTINGS_TOGGLE_AUTO_RECYCLE}$"))
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
        
        application.add_handler(CallbackQueryHandler(security_toggle_setting_callback, pattern="^security:(links|mentions|slow_mode|delete_videos|delete_service|delete_documents|delete_stickers|delete_audio|delete_animation|delete_forwarded|delete_polls|delete_games|delete_voice|delete_video_note|welcome_enabled|goodbye_enabled|antiflood|night_mode|max_length|warn_settings):[0-9-]+$"))
        application.add_handler(CallbackQueryHandler(security_banned_words_menu_callback, pattern=f"^{CallbackData.SECURITY_BANNED_WORDS_MENU_PREFIX}"))
        application.add_handler(CallbackQueryHandler(security_delete_penalty_callback, pattern=f"^{CallbackData.SECURITY_DELETE_PENALTY_PREFIX}"))
        application.add_handler(CallbackQueryHandler(security_warn_settings_callback, pattern="^security:warn_settings:"))
        application.add_handler(CallbackQueryHandler(security_advanced_actions_callback, pattern=f"^{CallbackData.ADVANCED_ACTIONS}"))
        application.add_handler(CallbackQueryHandler(security_enable_all_callback, pattern=f"^{CallbackData.SECURITY_ENABLE_ALL_PREFIX}"))
        application.add_handler(CallbackQueryHandler(security_disable_all_callback, pattern=f"^{CallbackData.SECURITY_DISABLE_ALL_PREFIX}"))
        application.add_handler(CallbackQueryHandler(security_close_callback, pattern=f"^{CallbackData.SECURITY_CLOSE}$"))
        application.add_handler(CallbackQueryHandler(security_select_group_callback, pattern=f"^{CallbackData.SECURITY_SELECT_GROUP}"))
        application.add_handler(CallbackQueryHandler(security_refresh_groups_callback, pattern=f"^{CallbackData.SECURITY_REFRESH_GROUPS}$"))
        
        application.add_handler(CallbackQueryHandler(penalty_menu_callback, pattern=f"^{CallbackData.PENALTY_MENU}:"))
        application.add_handler(CallbackQueryHandler(penalty_kick_callback, pattern=f"^{CallbackData.PENALTY_KICK}:"))
        application.add_handler(CallbackQueryHandler(penalty_ban_callback, pattern=f"^{CallbackData.PENALTY_BAN}:"))
        application.add_handler(CallbackQueryHandler(penalty_mute_callback, pattern=f"^{CallbackData.PENALTY_MUTE}:"))
        application.add_handler(CallbackQueryHandler(penalty_mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_5}"))
        application.add_handler(CallbackQueryHandler(penalty_mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_30}"))
        application.add_handler(CallbackQueryHandler(penalty_mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_60}"))
        application.add_handler(CallbackQueryHandler(penalty_mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_720}"))
        application.add_handler(CallbackQueryHandler(penalty_mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_1440}"))
        application.add_handler(CallbackQueryHandler(penalty_mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_10080}"))
        application.add_handler(CallbackQueryHandler(penalty_mute_duration_callback, pattern=f"^{CallbackData.GROUP_MUTE_DURATION_PERMANENT}"))
        
        application.add_handler(CallbackQueryHandler(advanced_actions_callback, pattern=f"^{CallbackData.ADVANCED_ACTIONS}"))
        application.add_handler(CallbackQueryHandler(group_action_ban_callback, pattern=f"^{CallbackData.GROUP_ACTION_BAN}"))
        application.add_handler(CallbackQueryHandler(group_action_mute_callback, pattern=f"^{CallbackData.GROUP_ACTION_MUTE}"))
        application.add_handler(CallbackQueryHandler(group_action_warn_callback, pattern=f"^{CallbackData.GROUP_ACTION_WARN}"))
        application.add_handler(CallbackQueryHandler(group_action_kick_callback, pattern=f"^{CallbackData.GROUP_ACTION_KICK}"))
        application.add_handler(CallbackQueryHandler(group_action_restrict_callback, pattern=f"^{CallbackData.GROUP_ACTION_RESTRICT}"))
        application.add_handler(CallbackQueryHandler(group_action_pin_callback, pattern=f"^{CallbackData.GROUP_ACTION_PIN}"))
        application.add_handler(CallbackQueryHandler(group_action_log_callback, pattern=f"^{CallbackData.GROUP_ACTION_LOG}"))
        application.add_handler(CallbackQueryHandler(group_action_unban_callback, pattern=f"^{CallbackData.GROUP_ACTION_UNBAN}"))
        application.add_handler(CallbackQueryHandler(advanced_mute_duration_callback, pattern="^adv_mute_duration:"))
        
        application.add_handler(CallbackQueryHandler(panel_lock_callback_handler, pattern=f"^{CallbackData.PANEL_LOCK_PREFIX}"))
        application.add_handler(CallbackQueryHandler(panel_unlock_callback_handler, pattern=f"^{CallbackData.PANEL_UNLOCK_PREFIX}"))
        application.add_handler(CallbackQueryHandler(panel_close_callback_handler, pattern=f"^{CallbackData.PANEL_CLOSE}$"))
        
        application.add_handler(CallbackQueryHandler(help_callback, pattern=f"^{CallbackData.HELP}$"))
        application.add_handler(CallbackQueryHandler(support_menu_callback, pattern=f"^{CallbackData.SUPPORT_MENU}$"))
        application.add_handler(CallbackQueryHandler(support_help_callback, pattern=f"^{CallbackData.SUPPORT_HELP}$"))
        application.add_handler(CallbackQueryHandler(support_ticket_callback, pattern=f"^{CallbackData.SUPPORT_TICKET}$"))
        application.add_handler(CallbackQueryHandler(support_back_callback, pattern=f"^{CallbackData.SUPPORT_BACK}$"))
        
        application.add_handler(CallbackQueryHandler(trial_callback, pattern=f"^{CallbackData.TRIAL}$"))
        application.add_handler(CallbackQueryHandler(subscribe_menu_callback, pattern=f"^{CallbackData.SUBSCRIBE_MENU}$"))
        application.add_handler(CallbackQueryHandler(buy_subscription_1_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_1}$"))
        application.add_handler(CallbackQueryHandler(buy_subscription_2_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_2}$"))
        application.add_handler(CallbackQueryHandler(buy_subscription_30_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_30}$"))
        application.add_handler(CallbackQueryHandler(buy_subscription_90_callback, pattern=f"^{CallbackData.BUY_SUBSCRIPTION_90}$"))
        
        application.add_handler(CallbackQueryHandler(developer_callback, pattern=f"^{CallbackData.DEVELOPER}$"))
        application.add_handler(CallbackQueryHandler(updates_callback, pattern=f"^{CallbackData.UPDATES}$"))
        
        application.add_handler(CallbackQueryHandler(referral_menu_callback, pattern=f"^{CallbackData.REFERRAL_MENU}$"))
        application.add_handler(CallbackQueryHandler(referral_copy_link_callback, pattern=f"^{CallbackData.REFERRAL_COPY_LINK_PREFIX}"))
        application.add_handler(CallbackQueryHandler(referral_claim_reward_callback, pattern=f"^{CallbackData.REFERRAL_CLAIM_REWARD}$"))
        application.add_handler(CallbackQueryHandler(referral_list_callback, pattern=f"^{CallbackData.REFERRAL_LIST}$"))
        application.add_handler(CallbackQueryHandler(reminder_menu_callback, pattern=f"^{CallbackData.REMINDER_MENU}$"))
        application.add_handler(CallbackQueryHandler(reminder_toggle_sub_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_SUB}$"))
        application.add_handler(CallbackQueryHandler(reminder_toggle_daily_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_DAILY}$"))
        application.add_handler(CallbackQueryHandler(reminder_toggle_weekly_callback, pattern=f"^{CallbackData.REMINDER_TOGGLE_WEEKLY}$"))
        application.add_handler(CallbackQueryHandler(reminder_set_days_callback, pattern=f"^{CallbackData.REMINDER_SET_DAYS}$"))
        application.add_handler(CallbackQueryHandler(reminder_set_lang_callback, pattern=f"^{CallbackData.REMINDER_SET_LANG}$"))
        application.add_handler(CallbackQueryHandler(reminder_lang_callback, pattern=f"^{CallbackData.REMINDER_LANG_PREFIX}"))
        application.add_handler(CallbackQueryHandler(translation_menu_callback, pattern=f"^{CallbackData.TRANSLATION_MENU}$"))
        application.add_handler(CallbackQueryHandler(translation_off_callback, pattern=f"^{CallbackData.TRANSLATION_OFF}$"))
        application.add_handler(CallbackQueryHandler(translation_set_callback, pattern=f"^{CallbackData.TRANSLATION_SET_PREFIX}"))
        
        application.add_handler(CallbackQueryHandler(contests_menu_callback, pattern=f"^{CallbackData.CONTESTS_MENU}$"))
        application.add_handler(CallbackQueryHandler(contest_join_callback, pattern=f"^{CallbackData.CONTEST_JOIN_PREFIX}"))
        application.add_handler(CallbackQueryHandler(contest_winners_callback, pattern=f"^{CallbackData.CONTEST_WINNERS}$"))
        application.add_handler(CallbackQueryHandler(contests_back_callback, pattern=f"^{CallbackData.CONTESTS_BACK}$"))
        application.add_handler(CallbackQueryHandler(channel_stats_callback, pattern=f"^{CallbackData.CHANNEL_STATS}:"))
        application.add_handler(CallbackQueryHandler(channel_growth_callback, pattern=f"^{CallbackData.CHANNEL_GROWTH}:"))
        application.add_handler(CallbackQueryHandler(channel_stats_refresh_callback, pattern=f"^{CallbackData.CHANNEL_STATS_REFRESH}:"))
        application.add_handler(CallbackQueryHandler(my_channel_stats_callback, pattern=f"^{CallbackData.MY_CHANNEL_STATS}$"))
        application.add_handler(CallbackQueryHandler(publish_all_channels_callback_handler, pattern=f"^{CallbackData.PUBLISH_ALL_CHANNELS}$"))
        
        application.add_handler(CallbackQueryHandler(nsfw_settings_callback, pattern=f"^{CallbackData.NSFW_SETTINGS}$"))
        application.add_handler(CallbackQueryHandler(nsfw_toggle_callback, pattern=f"^{CallbackData.NSFW_TOGGLE}$"))
        application.add_handler(CallbackQueryHandler(nsfw_threshold_set_callback, pattern=f"^{CallbackData.NSFW_THRESHOLD_SET}$"))
        application.add_handler(CallbackQueryHandler(check_subscribe_callback_handler, pattern=f"^{CallbackData.CHECK_SUBSCRIBE}$"))
        
        application.add_handler(CallbackQueryHandler(language_callback, pattern=r"^lang_"))
        application.add_handler(CallbackQueryHandler(handle_text_callbacks, pattern="^(rank|top|schedule_post|language)$"))
        
        application.add_handler(CallbackQueryHandler(banned_words_add_callback, pattern=f"^{CallbackData.BANNED_WORDS_ADD_PREFIX}"))
        application.add_handler(CallbackQueryHandler(banned_words_list_callback, pattern=f"^{CallbackData.BANNED_WORDS_LIST_PREFIX}"))
        application.add_handler(CallbackQueryHandler(banned_words_remove_callback, pattern=f"^{CallbackData.BANNED_WORDS_REMOVE_PREFIX}"))
        
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
        application.add_handler(CallbackQueryHandler(admin_replies_callback, pattern=f"^{CallbackData.ADMIN_REPLIES}$"))
        application.add_handler(CallbackQueryHandler(admin_add_reply_callback, pattern=f"^{CallbackData.ADMIN_ADD_REPLY}$"))
        application.add_handler(CallbackQueryHandler(admin_list_replies_callback, pattern=f"^{CallbackData.ADMIN_LIST_REPLIES}$"))
        application.add_handler(CallbackQueryHandler(admin_del_reply_callback, pattern=f"^{CallbackData.ADMIN_DEL_REPLY}$"))
        application.add_handler(CallbackQueryHandler(admin_banned_words_callback, pattern=f"^{CallbackData.ADMIN_BANNED_WORDS}$"))
        application.add_handler(CallbackQueryHandler(admin_add_banned_word_callback, pattern=f"^{CallbackData.ADMIN_ADD_BANNED_WORD}$"))
        application.add_handler(CallbackQueryHandler(admin_list_banned_words_callback, pattern=f"^{CallbackData.ADMIN_LIST_BANNED_WORDS}$"))
        application.add_handler(CallbackQueryHandler(admin_remove_banned_word_callback, pattern=f"^{CallbackData.ADMIN_REMOVE_BANNED_WORD}$"))
        application.add_handler(CallbackQueryHandler(admin_create_contest_callback, pattern=f"^{CallbackData.ADMIN_CREATE_CONTEST}$"))
        application.add_handler(CallbackQueryHandler(admin_declare_winner_callback, pattern=f"^{CallbackData.ADMIN_DECLARE_WINNER}$"))
        application.add_handler(CallbackQueryHandler(admin_del_contest_callback, pattern=f"^{CallbackData.ADMIN_DEL_CONTEST_PREFIX}"))
        application.add_handler(CallbackQueryHandler(admin_auto_reply_callback, pattern=f"^{CallbackData.ADMIN_AUTO_REPLY}$"))
        
        application.add_handler(CallbackQueryHandler(auto_reply_menu_callback, pattern=f"^{CallbackData.AUTO_REPLY_MENU_PREFIX}"))
        application.add_handler(CallbackQueryHandler(auto_reply_toggle_callback, pattern=f"^{CallbackData.AUTO_REPLY_TOGGLE_PREFIX}"))
        application.add_handler(CallbackQueryHandler(auto_reply_admins_callback, pattern=f"^{CallbackData.AUTO_REPLY_ADMINS_PREFIX}"))
        application.add_handler(CallbackQueryHandler(auto_reply_reset_callback, pattern=f"^{CallbackData.AUTO_REPLY_RESET_PREFIX}"))
        application.add_handler(CallbackQueryHandler(auto_reply_confirm_reset_callback, pattern=f"^{CallbackData.AUTO_REPLY_CONFIRM_RESET_PREFIX}"))
        application.add_handler(CallbackQueryHandler(auto_reply_cancel_callback, pattern=f"^{CallbackData.AUTO_REPLY_CANCEL_PREFIX}"))
        application.add_handler(CallbackQueryHandler(auto_reply_stats_callback, pattern=f"^{CallbackData.AUTO_REPLY_STATS_PREFIX}"))
        application.add_handler(CallbackQueryHandler(user_auto_reply_toggle_callback, pattern=f"^{CallbackData.USER_AUTO_REPLY_TOGGLE_PREFIX}"))
        
        application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler))
        application.add_handler(MessageHandler(filters.CAPTION & filters.ChatType.GROUPS & ~filters.COMMAND, filter_messages_handler))
        application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, message_handler_main))
        application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, message_handler_main))
        application.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.PRIVATE, message_handler_main))
        application.add_handler(MessageHandler(filters.AUDIO & filters.ChatType.PRIVATE, message_handler_main))
        application.add_handler(MessageHandler(filters.VOICE & filters.ChatType.PRIVATE, message_handler_main))
        application.add_handler(MessageHandler(filters.ANIMATION & filters.ChatType.PRIVATE, message_handler_main))
        application.add_handler(MessageHandler(filters.DOCUMENT & filters.ChatType.PRIVATE, message_handler_main))
        
        application.add_handler(ChatJoinRequestHandler(chat_join_request_handler))
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members_handler))
        application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_chat_member_handler))
        application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback_handler))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback_handler))
        application.add_handler(ChatMemberHandler(track_chat_add, ChatMemberHandler.MY_CHAT_MEMBER))
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER, delete_service_messages))
        
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
        logger.info("✅ تم تعيين أوامر البوت")
        
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
        logger.info("✅ تم تشغيل المهام الخلفية")
        
        hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("HEROKU_APP_NAME")
        
        if hostname:
            web_port = int(os.getenv("PORT", "10000"))
            logger.info(f"🌐 تشغيل Webhook على المنفذ {web_port}")
            await setup_unified_web_server(application, web_port)
            await application.initialize()
            await application.start()
            webhook_url = f"https://{hostname}/{TOKEN}"
            await application.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "chat_member", "chat_join_request", "pre_checkout_query"]
            )
            logger.info(f"✅ تم تعيين Webhook: {webhook_url}")
            try:
                await asyncio.Event().wait()
            except KeyboardInterrupt:
                logger.info("🛑 تم إيقاف البوت")
        else:
            logger.info("🔄 تشغيل Polling")
            await application.bot.delete_webhook()
            await run_polling_safe(application)
            
    except Exception as e:
        logger.error(f"❌ خطأ في main: {e}")
        logger.error(traceback.format_exc())
        raise

if __name__ == "__main__":
    try:
        os.environ["WEB_CONCURRENCY"] = "1"
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 تم إيقاف البوت")
    except Exception as e:
        logger.error(f"❌ خطأ فادح: {e}")
        traceback.print_exc()
        sys.exit(1)
