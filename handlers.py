#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers.py - جميع معالجات البوت (نسخة كاملة مصححة ومحسّنة)
- إصلاح متغير valid_violations
- حماية حذف الرسائل
- تحسين فحوصات الاشتراك والحدود
- التحقق من صحة وقت النشر
- تمرير issued_by في العقوبات
- معالجة النسخ الاحتياطي بأمان
- تقليل الاستعلامات المتكررة
- إضافة ميزات متقدمة: نقاط المستخدم، قوانين، إدارة الفيضان، إلخ.
"""

import asyncio
import os
import re
import shutil
import logging
import json
import time
import html
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple, Any
from contextlib import closing

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatPermissions, LabeledPrice
)
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from config import CONFIG, PATHS
from database import DB
from utils import (
    TimeUtils, TextUtils, safe_send, is_authorized_in_group,
    check_bot_permissions, invalidate_auth_cache, apply_penalty,
    RATE_LIMITER, METRICS, get_text, StateManager, UserState,
    KeyboardFactory, TranslationManager, CB,
    _auto_reply_cache, export_auto_replies, import_auto_replies,
    fetch_json_from_url, _increment_usage_async, get_ram_usage,
    get_reply_from_file, load_replies_from_file, reload_replies_from_file,
    get_min_publish_interval, invalidate_banned_words_cache,
    get_banned_words_cached
)

logger = logging.getLogger(__name__)

# أنواع المخالفات الصالحة
VALID_VIOLATION_TYPES = {
    "links", "mentions", "banned_words", "flood", "max_len",
    "service", "videos", "audio", "documents", "stickers",
    "forwarded", "polls", "games", "voice", "video_note"
}

# ثوابت callback إضافية
BUY_GIFT = "buy_gift:"
MY_GIFTS = "my_gifts"
SCHED_OPEN = "sched_open:"

# =====================================================================
# دوال مساعدة عامة
# =====================================================================

async def safe_answer_query(query, text=None, show_alert=False):
    """إرسال إجابة آمنة لاستعلام كولباك."""
    try:
        if text is not None:
            await query.answer(text, show_alert=show_alert)
        else:
            await query.answer()
    except BadRequest:
        pass

async def safe_edit_message_text(query, text, reply_markup=None, parse_mode=None):
    """تعديل رسالة مع تجاهل خطأ 'message is not modified'."""
    try:
        if reply_markup is not None:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await query.edit_message_text(text, parse_mode=parse_mode)
    except BadRequest as e:
        if "not modified" in str(e).lower():
            return
        raise

def backup_database(source_path: Path, dest_path: Path) -> bool:
    """نسخ احتياطي آمن باستخدام sqlite3.backup."""
    src = None
    dst = None
    try:
        src = sqlite3.connect(str(source_path))
        dst = sqlite3.connect(str(dest_path))
        with dst:
            src.backup(dst)
        logger.info(f"✅ تم إنشاء نسخة احتياطية: {dest_path}")
        return True
    except Exception as e:
        logger.error(f"❌ فشل النسخ الاحتياطي: {e}")
        return False
    finally:
        if dst:
            dst.close()
        if src:
            src.close()

def restore_database(backup_path: Path, target_path: Path) -> bool:
    """استعادة قاعدة البيانات بأمان."""
    src = None
    dst = None
    try:
        src = sqlite3.connect(str(backup_path))
        dst = sqlite3.connect(str(target_path))
        with dst:
            src.backup(dst)
        logger.info(f"✅ تمت الاستعادة من: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"❌ فشل الاستعادة: {e}")
        return False
    finally:
        if dst:
            dst.close()
        if src:
            src.close()

# =====================================================================
# 1. معالج الأوامر
# =====================================================================

class CommandHandlers:
    """جميع معالجات الأوامر"""

    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        username = update.effective_user.username or ""
        first_name = update.effective_user.first_name or ""
        await DB.register_user(user_id, username, first_name)

        args = context.args or []
        if args and args[0].startswith('ref_'):
            ref_code = args[0][4:]
            referrer = await DB.get_user_by_referral_code(ref_code)
            if referrer and referrer != user_id and not await DB.is_user_banned(referrer):
                existing = await DB.fetchone("SELECT 1 FROM referrals WHERE referred_id=?", (user_id,))
                if not existing:
                    if await DB.add_referral(referrer, user_id):
                        reward = await DB.get_referral_stats(referrer)
                        await safe_send(context.bot, referrer,
                                        f"🎁 تمت إحالة `{user_id}`. لديك {reward['available']} يوم متاح للصرف.")

        force_ch = await DB.get_force_subscribe_channel()
        if force_ch and user_id != CONFIG.PRIMARY_OWNER_ID:
            try:
                if force_ch.lstrip('-').isdigit():
                    chat = await context.bot.get_chat(int(force_ch))
                else:
                    chat = await context.bot.get_chat(f"@{force_ch}")
                member = await context.bot.get_chat_member(chat.id, user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    invite_link = None
                    try:
                        invite_link = await context.bot.export_chat_invite_link(chat.id)
                    except Exception:
                        pass

                    if invite_link:
                        kb = InlineKeyboardMarkup([[
                            InlineKeyboardButton("📢 اشترك", url=invite_link),
                            InlineKeyboardButton("✅ تحقق", callback_data=CB.CHECK_SUB)
                        ]])
                    else:
                        kb = InlineKeyboardMarkup([[
                            InlineKeyboardButton("✅ تحقق", callback_data=CB.CHECK_SUB)
                        ]])
                    await safe_send(context.bot, user_id, f"⚠️ اشترك في القناة أولاً", reply_markup=kb)
                    return
            except Exception as e:
                logger.error(f"❌ خطأ في التحقق من الاشتراك الإجباري: {e}")
                await safe_send(context.bot, user_id, "❌ تعذر التحقق من الاشتراك الإجباري، حاول لاحقًا")
                return

        lang = await DB.get_user_language(user_id)
        active = await DB.get_active_channel(user_id)
        cnt = 0
        ch_display = "لا توجد قنوات"
        if active:
            cnt = await DB.get_unpublished_posts_count(user_id, active)
            ch_info = await DB.get_channel_info(user_id, active)
            if ch_info:
                ch_display = f"{ch_info['channel_name']}"

        groups = len(await DB.get_user_groups(user_id))
        has_sub = await DB.has_active_subscription(user_id)
        sub_text = "✅ مفعل" if has_sub else "❌ غير مفعل"
        auto = await DB.get_auto_publish_status(user_id)
        auto_text = "مفعل" if auto else "معطل"
        recycle = await DB.get_auto_recycle_status(user_id)
        recycle_text = "مفعل" if recycle else "معطل"

        kb_rows = KeyboardFactory.get_menu("main_menu", lang)
        keyboard = []

        for row in kb_rows:
            btn_row = []
            for item in row:
                if item == "admin_panel_btn":
                    if CONFIG.is_developer(user_id):
                        text_btn = KeyboardFactory.get_text("admin_panel_btn", lang)
                        btn_row.append(InlineKeyboardButton(text_btn, callback_data=CB.ADMIN))
                else:
                    text_btn = KeyboardFactory.get_text(item, lang)
                    if item.endswith("_url"):
                        url = f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup"
                        btn_row.append(InlineKeyboardButton(text_btn, url=url))
                    else:
                        btn_row.append(InlineKeyboardButton(text_btn, callback_data=item))
            if btn_row:
                keyboard.append(btn_row)

        if CONFIG.is_developer(user_id):
            admin_text = KeyboardFactory.get_text("admin_panel_btn", lang)
            if not any(btn.callback_data == CB.ADMIN for row in keyboard for btn in row):
                keyboard.append([InlineKeyboardButton(admin_text, callback_data=CB.ADMIN)])

        kb = InlineKeyboardMarkup(keyboard)

        title = await get_text(lang, 'main_menu',
                               user_id=user_id, groups=groups,
                               sub=sub_text, channel=ch_display,
                               pending=cnt, auto=auto_text,
                               recycle=recycle_text,
                               bot_name=CONFIG.BOT_NAME)

        await safe_send(context.bot, user_id, title, reply_markup=kb)

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        await safe_send(context.bot, user_id, await get_text(lang, 'help_text'))

    @staticmethod
    async def trial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        if await DB.has_used_trial(user_id):
            await safe_send(context.bot, user_id, await get_text(lang, 'trial_used'))
            return
        days = await DB.activate_trial(user_id)
        if days > 0:
            await safe_send(context.bot, user_id, await get_text(lang, 'trial_activated', days=days))
        else:
            await safe_send(context.bot, user_id, "✅ لديك اشتراك حالي أطول من التجربة.")

    @staticmethod
    async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        kb = KeyboardFactory.build("plans", lang=lang)
        await safe_send(context.bot, user_id, await get_text(lang, 'plan_selector'), reply_markup=kb)

    @staticmethod
    async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        kb = KeyboardFactory.build("support", lang=lang)
        await safe_send(context.bot, user_id, await get_text(lang, 'send_support_message'), reply_markup=kb)

    @staticmethod
    async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        text = await get_text(lang, 'developer_info',
                              owner_id=CONFIG.PRIMARY_OWNER_ID,
                              bot_name=CONFIG.BOT_NAME,
                              bot_username=CONFIG.BOT_USERNAME)
        await safe_send(context.bot, user_id, text)

    @staticmethod
    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        stats = await DB.get_bot_stats()
        text = f"👥 المستخدمون: {stats.get('users',0)}\n"
        text += f"📡 القنوات: {stats.get('channels',0)}\n"
        text += f"👥 المجموعات: {stats.get('groups',0)}\n"
        text += f"📝 المنشورات: {stats.get('posts',0)}\n"
        text += f"✅ المنشورة: {stats.get('published',0)}\n"
        text += f"💎 الاشتراكات النشطة: {stats.get('active_subs',0)}\n"
        text += f"🎫 التذاكر المعلقة: {stats.get('tickets',0)}"
        await safe_send(context.bot, user_id, text)

    @staticmethod
    async def language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        available = TranslationManager.get_available_languages()
        buttons = []
        row = []
        for code, name in available.items():
            row.append(InlineKeyboardButton(name, callback_data=f"lang_{code}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        back_text = KeyboardFactory.get_text("back", lang)
        buttons.append([InlineKeyboardButton(back_text, callback_data=CB.BACK)])
        kb = InlineKeyboardMarkup(buttons)
        await safe_send(context.bot, user_id, f"🌐 اختر اللغة:\n\nالحالية: {lang}", reply_markup=kb)

    @staticmethod
    async def replies_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await safe_send(context.bot, update.effective_user.id, "📚 الردود التلقائية تعمل!")

    @staticmethod
    async def contests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        contests = await DB.get_active_contests(10)
        if not contests:
            await safe_send(context.bot, user_id, "📭 لا توجد مسابقات نشطة")
            return
        text = "🏆 **المسابقات النشطة**\n\n"
        for c in contests:
            text += f"• **{c['title']}**\n"
            text += f"  🎁 {c['prize']}\n"
            text += f"  📅 {c['end_date'][:10]}\n\n"
        kb = KeyboardFactory.build("contests", lang=lang)
        await safe_send(context.bot, user_id, text, reply_markup=kb)

    @staticmethod
    async def security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        lang = await DB.get_user_language(user_id)
        settings = await DB.get_security_settings(chat_id)
        text = KeyboardFactory._format_security_text(settings)
        kb = KeyboardFactory.build("security", chat_id, lang=lang)
        await safe_send(context.bot, user_id, text, reply_markup=kb)

    @staticmethod
    async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        lang = await DB.get_user_language(user_id)
        kb = KeyboardFactory.build("panel", chat_id, lang=lang)
        await safe_send(context.bot, user_id, "📋 لوحة تحكم المجموعة", reply_markup=kb)

    @staticmethod
    async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        await DB.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?,1,?,?)",
                         (chat_id, TimeUtils.sql_iso(), user_id))
        await safe_send(context.bot, user_id, "🔒 تم القفل")

    @staticmethod
    async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        await DB.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await safe_send(context.bot, user_id, "🔓 تم الفتح")

    # ========== أوامر المالكين والمشرفين المخفيين ==========

    @staticmethod
    async def register_hidden_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        user_id = update.effective_user.id
        if user_id != CONFIG.PRIMARY_OWNER_ID:
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        if not context.args:
            await safe_send(context.bot, user_id, "📝 /register_hidden_owner <user_id>")
            return
        try:
            owner_id = int(context.args[0])
        except:
            await safe_send(context.bot, user_id, "⚠️ معرف غير صالح")
            return
        chat_id = update.effective_chat.id
        await DB.execute("INSERT OR IGNORE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,1)", (chat_id, owner_id))
        invalidate_auth_cache(chat_id, owner_id)
        await safe_send(context.bot, user_id, f"✅ تم تسجيل `{owner_id}` كمالك مخفي")

    @staticmethod
    async def remove_hidden_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        user_id = update.effective_user.id
        if user_id != CONFIG.PRIMARY_OWNER_ID:
            return
        if not context.args:
            return
        try:
            owner_id = int(context.args[0])
        except:
            return
        chat_id = update.effective_chat.id
        await DB.execute("DELETE FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, owner_id))
        invalidate_auth_cache(chat_id, owner_id)
        await safe_send(context.bot, user_id, f"✅ تم إزالة `{owner_id}`")

    @staticmethod
    async def add_hidden_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        is_owner = user_id == CONFIG.PRIMARY_OWNER_ID
        if not is_owner:
            row = await DB.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
            is_owner = row is not None
        if not is_owner:
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        if not context.args:
            return
        try:
            admin_id = int(context.args[0])
        except:
            return
        await DB.add_hidden_admin(chat_id, admin_id, user_id)
        invalidate_auth_cache(chat_id, admin_id)
        await safe_send(context.bot, user_id, f"✅ تم إضافة `{admin_id}` كمشرف مخفي")

    @staticmethod
    async def remove_hidden_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        is_owner = user_id == CONFIG.PRIMARY_OWNER_ID
        if not is_owner:
            row = await DB.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
            is_owner = row is not None
        if not is_owner:
            return
        if not context.args:
            return
        try:
            admin_id = int(context.args[0])
        except:
            return
        await DB.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
        invalidate_auth_cache(chat_id, admin_id)
        await safe_send(context.bot, user_id, f"✅ تم إزالة `{admin_id}`")

    @staticmethod
    async def list_hidden_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        is_owner = user_id == CONFIG.PRIMARY_OWNER_ID
        if not is_owner:
            row = await DB.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
            is_owner = row is not None
        if not is_owner:
            return
        owners = await DB.fetchall("SELECT owner_id FROM hidden_owner_groups WHERE chat_id=?", (chat_id,))
        admins = await DB.fetchall("SELECT admin_id FROM hidden_admins WHERE chat_id=?", (chat_id,))
        text = "👤 **المخفيون**\n"
        for o in owners:
            text += f"👑 `{o[0]}`\n"
        for a in admins:
            text += f"🛡️ `{a[0]}`\n"
        await safe_send(context.bot, user_id, text if owners or admins else "📭 لا يوجد")

    # ========== تفعيل المجموعة ==========

    @staticmethod
    async def syncgroup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
            await safe_send(context.bot, update.effective_user.id, "❌ هذا الأمر للمجموعات فقط")
            return

        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "بدون اسم"
        user_id = update.effective_user.id

        logger.info(f"🔍 محاولة تسجيل المجموعة: chat_id={chat_id}, user_id={user_id}")

        # التحقق من صلاحيات البوت أولاً
        bot_perms = await check_bot_permissions(context.bot, chat_id)
        if not bot_perms.get('can_act', False):
            await safe_send(context.bot, user_id, "⚠️ **البوت ليس مشرفاً!**")
            return

        try:
            all_admins = await context.bot.get_chat_administrators(chat_id)
            logger.info(f"🔍 عدد المشرفين: {len(all_admins)}")
        except Exception as e:
            logger.error(f"❌ فشل جلب المشرفين: {e}")
            await safe_send(context.bot, user_id, "❌ فشل جلب المشرفين")
            return

        creator_id = None
        for admin in all_admins:
            if admin.status == 'creator' and not admin.user.is_bot:
                creator_id = admin.user.id
                break
        logger.info(f"🔍 المالك: {creator_id}")

        is_admin = False
        is_anonymous = False

        for admin in all_admins:
            if admin.user.id == user_id:
                is_admin = True
                is_anonymous = getattr(admin, 'is_anonymous', False)
                break

        if not is_admin and user_id == CONFIG.ANONYMOUS_ADMIN_ID:
            is_admin = True
            is_anonymous = True
            logger.info("🔍 تم التعرف على مشرف مخفي")

        if not is_admin:
            await safe_send(context.bot, user_id, "❌ **أنت لست مشرفاً في هذه المجموعة!**")
            return

        logger.info(f"🔍 المستخدم مشرف: is_anonymous={is_anonymous}")

        try:
            await DB.register_group(chat_id, chat_name, creator_id or user_id, update.effective_chat.username)
            logger.info("✅ تم تسجيل المجموعة في bot_groups")
        except Exception as e:
            logger.error(f"❌ فشل تسجيل المجموعة في bot_groups: {e}")
            await safe_send(context.bot, user_id, "❌ فشل تسجيل المجموعة")
            return

        try:
            if creator_id:
                await DB.execute(
                    "INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,0)",
                    (chat_id, creator_id)
                )
                await DB.execute(
                    "INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?,?)",
                    (creator_id, chat_id)
                )
                invalidate_auth_cache(chat_id, creator_id)

            await DB.execute(
                "INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?,?)",
                (user_id, chat_id)
            )
            invalidate_auth_cache(chat_id, user_id)
            logger.info("✅ تم ربط المستخدم بالمجموعة")
        except Exception as e:
            logger.error(f"❌ فشل ربط المستخدم بالمجموعة: {e}")
            await safe_send(context.bot, user_id, "❌ فشل ربط المستخدم بالمجموعة")
            return

        try:
            admin_ids = [a.user.id for a in all_admins if a.user and not a.user.is_bot]
            admin_count = await DB.sync_group_admins(chat_id, admin_ids)
            logger.info(f"✅ تم مزامنة {admin_count} مشرف")
        except Exception as e:
            logger.error(f"❌ فشل مزامنة المشرفين: {e}")
            admin_count = 0

        msg = f"✅ **تم تفعيل المجموعة!**\n\n"
        msg += f"📌 {chat_name}\n"
        msg += f"🆔 `{chat_id}`\n"
        if creator_id:
            msg += f"👑 المالك: `{creator_id}`\n"
        msg += f"{'👻 مخفي' if is_anonymous else '👤 مشرف'}: `{user_id}`\n"
        msg += f"👥 {admin_count} مشرف"

        try:
            await safe_send(context.bot, user_id, msg)
        except BadRequest as e:
            if "User_bot_to_bot_disabled" in str(e):
                await safe_send(context.bot, chat_id, msg)
            else:
                logger.error(f"❌ فشل إرسال رسالة التأكيد: {e}")

        sent_msg = await safe_send(context.bot, chat_id, "🤖 **تم تفعيل البوت!**")
        if sent_msg:
            try:
                await asyncio.sleep(5)
                await sent_msg.delete()
            except Exception as e:
                logger.warning(f"⚠️ فشل حذف رسالة التفعيل: {e}")

    # ========== أوامر الإشراف ==========

    @staticmethod
    async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "ban")

    @staticmethod
    async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "mute")

    @staticmethod
    async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "warn")

    @staticmethod
    async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "kick")

    @staticmethod
    async def restrict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "restrict")

    @staticmethod
    async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "unban")

    @staticmethod
    async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        if update.message.reply_to_message:
            try:
                await context.bot.pin_chat_message(chat_id, update.message.reply_to_message.message_id)
                await safe_send(context.bot, user_id, "📌 تم التثبيت")
            except Exception as e:
                logger.error(f"❌ فشل التثبيت: {e}")
        else:
            await safe_send(context.bot, user_id, "❌ قم بالرد على الرسالة التي تريد تثبيتها")

    @staticmethod
    async def _moderation_command(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return

        args = context.args or []
        if not args:
            await safe_send(context.bot, user_id, f"📝 /{action} معرف_المستخدم [مدة_بالدقائق]")
            return

        try:
            target = int(args[0])
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            return

        if target <= 0:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            return

        if await is_authorized_in_group(context.bot, chat_id, target):
            await safe_send(context.bot, user_id, "❌ لا يمكن معاملة مشرف")
            return

        reason_parts = []
        duration_seconds = 60  # افتراضي 60 ثانية

        # تحليل المدة فقط للأوامر التي تدعمها
        if action in ('ban', 'mute', 'restrict') and len(args) > 1:
            try:
                minutes = int(args[1])
                if minutes <= 0:
                    await safe_send(context.bot, user_id, "❌ المدة يجب أن تكون رقمًا موجبًا")
                    return
                duration_seconds = minutes * 60
                reason_parts = args[2:]
            except ValueError:
                reason_parts = args[1:]
        else:
            reason_parts = args[1:]

        reason = " ".join(reason_parts)

        if action == 'unban':
            try:
                await context.bot.unban_chat_member(chat_id, target)
                await DB.remove_penalties_for_user(target, chat_id, penalty_type='ban')
                await safe_send(context.bot, user_id, "✅ تم إلغاء الحظر")
            except Exception as e:
                logger.error(f"❌ فشل إلغاء الحظر: {e}")
            return

        success, msg = await apply_penalty(context.bot, chat_id, target, action, duration_seconds, reason, user_id)
        await safe_send(context.bot, user_id, msg)

    # ========== أمر منح اشتراك مجاني ==========

    @staticmethod
    async def set_min_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return

        args = context.args or []
        if not args:
            await safe_send(context.bot, user_id, "📝 /set_min_interval <دقائق>\nمثال: /set_min_interval 15")
            return

        try:
            val = int(args[0])
            if val < 1:
                await safe_send(context.bot, user_id, "❌ الحد الأدنى يجب أن يكون 1 دقيقة على الأقل")
                return
            await DB.set_setting('min_publish_interval', str(val))
            await safe_send(context.bot, user_id, f"✅ تم تعيين الحد الأدنى إلى {val} دقيقة\n🔄 أعد تشغيل البوت لتطبيق التغيير")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة، أدخل رقماً")

    @staticmethod
    async def grant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return

        args = context.args or []
        if len(args) < 2:
            await safe_send(context.bot, user_id, "📝 /grant <user_id> <days>")
            return

        try:
            target_id = int(args[0])
            days = int(args[1])
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيم غير صالحة")
            return

        if days < 1 or days > 365:
            await safe_send(context.bot, user_id, "❌ عدد الأيام يجب أن يكون بين 1 و 365")
            return

        user_row = await DB.fetchone("SELECT user_id FROM users WHERE user_id=?", (target_id,))
        if not user_row:
            await safe_send(context.bot, user_id, "❌ المستخدم غير موجود في قاعدة البيانات")
            return

        # استخدام خطة هدية افتراضية (أو خطة أولى)
        plan_row = await DB.fetchone("SELECT id FROM plans WHERE is_gift=1 LIMIT 1")
        if not plan_row:
            plan_row = await DB.fetchone("SELECT id FROM plans WHERE is_active=1 AND is_gift=0 LIMIT 1")
        plan_id = plan_row[0] if plan_row else None

        if plan_id is None:
            await safe_send(context.bot, user_id, "❌ لا توجد خطط متاحة للمنح")
            return

        success = await DB.grant_subscription_days(target_id, days, plan_id=plan_id, provider='manual')
        if success:
            await safe_send(context.bot, user_id, f"✅ تم منح {days} يوم للمستخدم `{target_id}`")
        else:
            await safe_send(context.bot, user_id, "❌ فشل المنح - تحقق من السجلات")

    # ========== أوامر الهدايا ==========

    @staticmethod
    async def gift_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)

        plans = await DB.get_gift_plans()
        if not plans:
            await safe_send(context.bot, user_id, "📭 لا توجد خطط متاحة حالياً.")
            return

        kb = []
        for plan in plans:
            days = plan['days']
            price = plan['price']
            kb.append([InlineKeyboardButton(
                f"🎁 {days} يوم - {price} ⭐",
                callback_data=f"{BUY_GIFT}{plan['id']}"
            )])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])

        text = "💎 **شراء كود هدية**\n\nاختر المدة المناسبة:\n\n"
        text += "• بعد الدفع، ستحصل على كود فريد.\n"
        text += "• يمكنك إرسال الكود لأي شخص.\n"
        text += "• الشخص الذي يستخدم الكود يحصل على اشتراك مجاني."

        await safe_send(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(kb))

    @staticmethod
    async def redeem_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)

        args = context.args or []
        if not args:
            await safe_send(context.bot, user_id, "📝 أرسل الكود: `/redeem_gift <الكود>`")
            return

        code = args[0].strip()
        success, days = await DB.redeem_gift_code(user_id, code)

        if success and days > 0:
            await safe_send(context.bot, user_id, f"🎉 **تم تفعيل الاشتراك بنجاح!**\n\n✅ {days} يوم اشتراك مجاني.")
        elif days == -1:
            await safe_send(context.bot, user_id, "❌ لا يمكنك استخدام كود هدية قمت بإنشائه بنفسك.")
        else:
            await safe_send(context.bot, user_id, "❌ كود غير صالح أو مستخدم مسبقاً.")


# =====================================================================
# 2. معالج الكولباك
# =====================================================================

class CallbackHandlers:
    """جميع معالجات ضغطات الأزرار"""

    @staticmethod
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        data = query.data
        if not data:
            return

        user_id = query.from_user.id
        lang = await DB.get_user_language(user_id)

        base_data = data
        if ':' in data:
            parts = data.split(':')
            known_constants = [
                CB.TOGGLE_AUTO, CB.TOGGLE_REC, CB.TRANSLATION, CB.REFERRAL,
                CB.REMINDER, CB.CONTESTS, CB.SUPPORT_TICKET, CB.CH_LIST,
                CB.POST_ADD, CB.POST_PUB, CB.POST_LIST, CB.POST_REC, CB.PUB_ALL,
                CB.GROUPS, CB.ADMIN, CB.PANEL_CLOSE, CB.SETTINGS,
                CB.PLANS, CB.INVOICES, CB.REF_CLAIM, CB.REF_LIST,
                CB.CONTEST_WINNERS, CB.DEVELOPER, CB.SUBSCRIBE, CB.SUPPORT,
                CB.LANGUAGE, CB.TRIAL, CB.HELP, CB.CANCEL, CB.CHECK_SUB,
                CB.TRANS_OFF, CB.REM_TOGGLE_SUB, CB.REM_TOGGLE_DAILY,
                CB.REM_TOGGLE_WEEKLY, CB.REM_SET_DAYS
            ]
            if parts[0] in known_constants:
                base_data = parts[0]

        logger.info(f"Callback data: {data} (base: {base_data})")

        try:
            if base_data == "status_only":
                await safe_answer_query(query, "لا تغيير")
                return

            if base_data == "start_btn":
                await safe_answer_query(query)
                context.args = []
                await CommandHandlers.start(update, context)
                return

            if base_data in [CB.MAIN, CB.BACK]:
                await safe_answer_query(query)
                context.args = []
                await CommandHandlers.start(update, context)
                return

            if base_data == CB.CANCEL:
                StateManager.clear(user_id)
                await safe_answer_query(query, "❌ تم الإلغاء")
                return

            if base_data == CB.HELP:
                await safe_answer_query(query)
                await CommandHandlers.help_command(update, context)
                return

            if base_data == CB.TRIAL:
                await safe_answer_query(query)
                if await DB.has_used_trial(user_id):
                    await safe_edit_message_text(query, await get_text(lang, 'trial_used'))
                    return
                days = await DB.activate_trial(user_id)
                if days > 0:
                    await safe_edit_message_text(query, await get_text(lang, 'trial_activated', days=days))
                else:
                    await safe_edit_message_text(query, "✅ لديك اشتراك حالي أطول من التجربة.")
                return

            if base_data == CB.DEVELOPER:
                await safe_answer_query(query)
                await CommandHandlers.developer(update, context)
                return

            if base_data == CB.SUBSCRIBE:
                await safe_answer_query(query)
                await CommandHandlers.subscribe(update, context)
                return

            if base_data == CB.SUPPORT:
                await safe_answer_query(query)
                await CommandHandlers.support(update, context)
                return

            if base_data == CB.LANGUAGE:
                await safe_answer_query(query)
                await CommandHandlers.language(update, context)
                return

            if base_data == CB.CHECK_SUB:
                await safe_answer_query(query)
                context.args = []
                await CommandHandlers.start(update, context)
                return

            # ========== الإعدادات ==========
            if base_data == CB.SETTINGS:
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings", lang=lang)
                await safe_edit_message_text(
                    query,
                    f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}",
                    reply_markup=kb
                )
                await safe_answer_query(query)
                return

            if base_data == CB.TOGGLE_AUTO:
                await safe_answer_query(query, "🔄 جارٍ التحديث...")
                cur = await DB.get_auto_publish_status(user_id)
                await DB.set_auto_publish(user_id, not cur)
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings", lang=lang)
                await safe_edit_message_text(
                    query,
                    f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}",
                    reply_markup=kb
                )
                return

            if base_data == CB.TOGGLE_REC:
                await safe_answer_query(query, "🔄 جارٍ التحديث...")
                cur = await DB.get_auto_recycle_status(user_id)
                await DB.set_auto_recycle(user_id, not cur)
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings", lang=lang)
                await safe_edit_message_text(
                    query,
                    f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}",
                    reply_markup=kb
                )
                return

            if base_data == CB.PLANS:
                kb = KeyboardFactory.build("plans", lang=lang)
                await safe_edit_message_text(query, await get_text(lang, 'plan_selector'), reply_markup=kb)
                await safe_answer_query(query)
                return

            if base_data == "gift_plans":
                await safe_answer_query(query)

                plans = await DB.get_gift_plans()
                if not plans:
                    await safe_edit_message_text(query, "📭 لا توجد خطط متاحة حالياً.")
                    return

                kb = []
                for plan in plans:
                    days = plan['days']
                    price = plan['price']
                    kb.append([InlineKeyboardButton(
                        f"🎁 {days} يوم - {price} ⭐",
                        callback_data=f"{BUY_GIFT}{plan['id']}"
                    )])
                kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])

                text = "💎 **شراء كود هدية**\n\nاختر المدة المناسبة:\n\n"
                text += "• بعد الدفع، ستحصل على كود فريد.\n"
                text += "• يمكنك إرسال الكود لأي شخص.\n"
                text += "• الشخص الذي يستخدم الكود يحصل على اشتراك مجاني."

                await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if base_data == "redeem_gift":
                await safe_answer_query(query)
                await CommandHandlers.redeem_gift(update, context)
                return

            if data.startswith("buy_sub_"):
                await safe_answer_query(query, "🔄 جارٍ التحضير...")
                days = int(data.split("_")[-1])
                plan_names = {1: "يوم", 7: "أسبوع", 30: "شهر", 90: "3 أشهر", 365: "سنة"}
                plan_name = plan_names.get(days)
                if not plan_name:
                    await safe_answer_query(query, "❌ باقة غير موجودة", show_alert=True)
                    return
                plan = await DB.get_plan_by_name(plan_name)
                if not plan:
                    await safe_answer_query(query, "❌ باقة غير موجودة", show_alert=True)
                    return

                invoice_number = await DB.create_invoice(user_id, plan['id'], plan['price'])
                if not invoice_number:
                    await safe_answer_query(query, "❌ فشل الدفع", show_alert=True)
                    return

                try:
                    await context.bot.send_invoice(
                        chat_id=user_id,
                        title=f"💎 {plan['name']}",
                        description=plan['description'],
                        payload=json.dumps({'plan_id': plan['id'], 'invoice': invoice_number, 'type': 'subscription'}),
                        provider_token="",
                        currency="XTR",
                        prices=[LabeledPrice(plan['name'], plan['price'])]
                    )
                    await safe_answer_query(query, "✅ تم إرسال الفاتورة")
                    try:
                        await query.message.delete()
                    except BadRequest:
                        pass
                except Exception as e:
                    logger.error(f"❌ فشل إرسال الفاتورة: {e}")
                    await DB.execute("UPDATE invoices SET status='cancelled' WHERE number=?", (invoice_number,))
                    await safe_answer_query(query, f"❌ {str(e)[:50]}", show_alert=True)
                return

            if base_data == CB.INVOICES:
                invoices = await DB.get_user_invoices(user_id, 10)
                if not invoices:
                    await safe_edit_message_text(query, "📭 لا توجد فواتير")
                    await safe_answer_query(query)
                    return
                text = "🧾 **فواتيري**\n\n"
                for inv in invoices:
                    text += f"• #{inv['number']} - {inv['amount']} ⭐\n"
                kb = [[InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]]
                await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(kb))
                await safe_answer_query(query)
                return

            if base_data == CB.REFERRAL:
                await safe_answer_query(query)
                stats = await DB.get_referral_stats(user_id)
                code = await DB.get_referral_code(user_id)
                text = f"🔗 **الإحالات**\n\n🔗 `https://t.me/{CONFIG.BOT_USERNAME}?start=ref_{code}`\n👥 {stats['total']}\n🎁 {stats['available']} يوم"
                kb = KeyboardFactory.build("referral", lang=lang)
                await safe_edit_message_text(query, text, reply_markup=kb)
                return

            if base_data == CB.REF_CLAIM:
                await safe_answer_query(query, "🔄 جارٍ الصرف...")
                days = await DB.claim_referral_reward(user_id)
                await safe_edit_message_text(query, f"✅ {days} يوم!" if days else "📭 لا توجد")
                return

            if base_data == CB.REF_LIST:
                await safe_answer_query(query)
                referrals = await DB.get_referrals_list(user_id)
                text = "📋 **المُحالين**\n\n" + "\n".join([f"• `{r}`" for r in referrals[:20]]) if referrals else "📭 لا يوجد"
                await safe_edit_message_text(query, text)
                return

            if base_data in [CB.REM_TOGGLE_SUB, CB.REM_TOGGLE_DAILY, CB.REM_TOGGLE_WEEKLY]:
                await safe_answer_query(query, "🔄 جارٍ التحديث...")

                if base_data == CB.REM_TOGGLE_SUB:
                    s = await DB.get_reminder_settings(user_id)
                    await DB.update_reminder_settings(user_id, subscription_reminder=not s.get('subscription_reminder', False))
                elif base_data == CB.REM_TOGGLE_DAILY:
                    s = await DB.get_reminder_settings(user_id)
                    await DB.update_reminder_settings(user_id, daily_stats_reminder=not s.get('daily_stats_reminder', False))
                elif base_data == CB.REM_TOGGLE_WEEKLY:
                    s = await DB.get_reminder_settings(user_id)
                    await DB.update_reminder_settings(user_id, weekly_report=not s.get('weekly_report', False))

                settings = await DB.get_reminder_settings(user_id)
                text = f"⏰ **التذكيرات**\n\n"
                text += f"🔔 الاشتراك: {'✅' if settings.get('subscription_reminder', False) else '❌'}\n"
                text += f"📊 يومي: {'✅' if settings.get('daily_stats_reminder', False) else '❌'}\n"
                text += f"📈 أسبوعي: {'✅' if settings.get('weekly_report', False) else '❌'}\n"
                text += f"📅 الأيام: {settings.get('reminder_days_before', 3)}"
                kb = KeyboardFactory.build("reminder", lang=lang)
                await safe_edit_message_text(query, text, reply_markup=kb)
                return

            if base_data == CB.REMINDER:
                await safe_answer_query(query)
                settings = await DB.get_reminder_settings(user_id)
                text = f"⏰ **التذكيرات**\n\n"
                text += f"🔔 الاشتراك: {'✅' if settings.get('subscription_reminder', False) else '❌'}\n"
                text += f"📊 يومي: {'✅' if settings.get('daily_stats_reminder', False) else '❌'}\n"
                text += f"📈 أسبوعي: {'✅' if settings.get('weekly_report', False) else '❌'}\n"
                text += f"📅 الأيام: {settings.get('reminder_days_before', 3)}"
                kb = KeyboardFactory.build("reminder", lang=lang)
                await safe_edit_message_text(query, text, reply_markup=kb)
                return

            if base_data == CB.REM_SET_DAYS:
                StateManager.set(user_id, UserState.WAIT_REM_DAYS)
                await safe_edit_message_text(query, "📅 أرسل عدد الأيام (1-30):")
                await safe_answer_query(query)
                return

            if data.startswith(CB.REM_LANG + ":"):
                await safe_answer_query(query, "✅ تم التحديث")
                lang_set = data.split(":")[-1]
                await DB.update_reminder_settings(user_id, notification_lang=lang_set)
                await safe_edit_message_text(query, f"✅ تم تعيين لغة التذكير: {lang_set}")
                return

            if base_data == CB.TRANSLATION:
                await safe_answer_query(query)
                cur = await DB.get_user_language(user_id)
                kb = KeyboardFactory.build("translation", lang=lang)
                await safe_edit_message_text(query, f"🌐 الترجمة: {cur}", reply_markup=kb)
                return

            if base_data == CB.TRANS_OFF:
                await DB.set_user_language(user_id, 'off')
                await safe_edit_message_text(query, "✅ تم إيقاف الترجمة")
                await safe_answer_query(query)
                return

            if data.startswith(CB.TRANS_SET + ":"):
                lang_set = data.split(":")[-1]
                await DB.set_user_language(user_id, lang_set)
                await safe_edit_message_text(query, f"✅ تم تعيين: {lang_set}")
                await safe_answer_query(query)
                return

            if base_data == CB.CONTESTS:
                await safe_answer_query(query)
                await CommandHandlers.contests(update, context)
                return

            if base_data == CB.CONTEST_WINNERS:
                winners = await DB.get_contest_winners(10)
                if not winners:
                    await safe_edit_message_text(query, "📭 لا يوجد فائزون")
                    await safe_answer_query(query)
                    return
                text = "🏆 **الفائزون**\n\n"
                for w in winners:
                    text += f"• {w['title']} → `{w['winner_id']}`\n"
                await safe_edit_message_text(query, text)
                await safe_answer_query(query)
                return

            if data.startswith(CB.CONTEST_JOIN + ":"):
                cid = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
                context.user_data['contest_join'] = cid
                await safe_answer_query(query)
                await safe_send(context.bot, user_id, "📝 أرسل إجابتك:")
                return

            if base_data == CB.SUPPORT_TICKET:
                StateManager.set(user_id, UserState.SUPPORT_MODE)
                await safe_answer_query(query)
                await safe_send(context.bot, user_id, "📞 أرسل رسالتك:")
                return

            if base_data == CB.CH_ADD:
                StateManager.set(user_id, UserState.WAIT_CHANNEL)
                await safe_edit_message_text(query, "📡 أرسل معرف القناة:")
                await safe_answer_query(query)
                return

            if base_data == CB.CH_LIST:
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.CH_SEL + ":"):
                ch_id = int(data.split(":")[-1])
                success = await DB.set_active_channel(user_id, ch_id)
                if success:
                    await safe_edit_message_text(query, "✅ تم تحديد القناة!")
                else:
                    await safe_answer_query(query, "❌ لا يمكنك تحديد هذه القناة", show_alert=True)
                    return
                await safe_answer_query(query)
                return

            if data.startswith(CB.CH_DEL + ":"):
                ch_id = int(data.split(":")[-1])
                success = await DB.delete_channel(user_id, ch_id)
                if success:
                    await safe_answer_query(query, "✅ تم الحذف")
                else:
                    await safe_answer_query(query, "❌ لا يمكنك حذف هذه القناة", show_alert=True)
                    return
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.CH_STATS + ":"):
                ch_id = int(data.split(":")[-1])
                row = await DB.fetchone("SELECT 1 FROM user_channels WHERE id=? AND user_id=?", (ch_id, user_id))
                if not row:
                    await safe_answer_query(query, "❌ هذه القناة ليست لك", show_alert=True)
                    return
                stats = await DB.get_channel_stats(user_id, ch_id)
                text = f"📊 **إحصائيات القناة**\n\n"
                text += f"📝 المجموع: {stats['total']}\n"
                text += f"✅ المنشورة: {stats['published']}\n"
                text += f"⏳ غير المنشورة: {stats['unpublished']}"
                await safe_edit_message_text(query, text)
                await safe_answer_query(query)
                return

            if base_data == CB.POST_ADD:
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await safe_answer_query(query, "❌ انتهى اشتراكك!", show_alert=True)
                    return
                active = await DB.get_active_channel(user_id)
                if not active:
                    await safe_edit_message_text(query, "❌ لا توجد قناة نشطة")
                    await safe_answer_query(query)
                    return
                active_plan = await DB.get_active_plan(user_id)
                limit = active_plan['max_posts'] if active_plan else CONFIG.MAX_POSTS_PER_CHANNEL
                row = await DB.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (active,))
                total_posts = row[0] if row else 0
                if total_posts >= limit and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await safe_answer_query(query, f"❌ وصلت للحد الأقصى ({limit} منشور) في هذه القناة.", show_alert=True)
                    return
                StateManager.set(user_id, UserState.ADDING_POSTS)
                await safe_edit_message_text(
                    query,
                    "📥 أرسل المنشورات الآن (واحد تلو الآخر).\n"
                    "عند الانتهاء أرسل /done"
                )
                return

            if base_data == CB.POST_PUB:
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await safe_answer_query(query, "❌ انتهى اشتراكك!", show_alert=True)
                    return
                active = await DB.get_active_channel(user_id)
                if not active:
                    await safe_edit_message_text(query, "❌ لا توجد قناة")
                    return
                post = await DB.get_next_post(active)
                if not post:
                    await safe_edit_message_text(query, "📭 لا توجد منشورات")
                    return
                ch_info = await DB.get_channel_info(user_id, active)
                if not ch_info:
                    return
                try:
                    await CallbackHandlers._publish_single(context.bot, active, ch_info['channel_id'], post)
                    await safe_edit_message_text(query, "✅ تم النشر!")
                except Exception as e:
                    logger.error(f"❌ فشل النشر: {e}")
                    await safe_edit_message_text(query, "❌ فشل النشر، تحقق من صلاحيات البوت.")
                return

            if base_data == CB.POST_LIST:
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if base_data == CB.POST_REC:
                active = await DB.get_active_channel(user_id)
                if active:
                    count = await DB.reset_posts(user_id, active)
                    await safe_edit_message_text(query, f"♻️ {count} منشور!")
                await safe_answer_query(query)
                return

            if base_data == CB.PUB_ALL:
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await safe_answer_query(query, "❌ انتهى اشتراكك! يرجى تجديد الاشتراك", show_alert=True)
                    return

                channels = await DB.get_user_channels(user_id)
                if not channels:
                    await safe_edit_message_text(query, "❌ لا توجد قنوات للنشر")
                    await safe_answer_query(query)
                    return

                published_count = 0
                failed_count = 0
                await safe_edit_message_text(query, "⏳ جاري النشر...")
                await safe_answer_query(query)

                for ch in channels:
                    post = await DB.get_next_post(ch['id'])
                    if not post:
                        continue
                    ch_info = await DB.get_channel_info(user_id, ch['id'])
                    if not ch_info:
                        continue
                    try:
                        await CallbackHandlers._publish_single(context.bot, ch['id'], ch_info['channel_id'], post)
                        published_count += 1
                    except Exception as e:
                        logger.error(f"❌ فشل النشر في القناة {ch['channel_id']}: {e}")
                        failed_count += 1

                if published_count > 0 and failed_count == 0:
                    await safe_edit_message_text(query, f"✅ تم نشر {published_count} منشور (منشور واحد في كل قناة)")
                elif published_count > 0 and failed_count > 0:
                    await safe_edit_message_text(query, f"⚠️ تم نشر {published_count} منشور، فشل {failed_count} منشور")
                else:
                    await safe_edit_message_text(query, "📭 لا توجد منشورات للنشر في أي قناة")
                return

            if data.startswith(CB.POST_DEL + ":"):
                post_id = int(data.split(":")[-1])
                row = await DB.fetchone("SELECT channel_db_id FROM posts WHERE id=?", (post_id,))
                if not row:
                    await safe_answer_query(query, "❌ المنشور غير موجود", show_alert=True)
                    return
                ch_id = row[0]
                row2 = await DB.fetchone("SELECT user_id FROM user_channels WHERE id=?", (ch_id,))
                if not row2 or row2[0] != user_id:
                    await safe_answer_query(query, "❌ غير مصرح", show_alert=True)
                    return
                await DB.execute("DELETE FROM posts WHERE id=?", (post_id,))
                await safe_edit_message_text(query, "✅ تم حذف المنشور!")
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.POST_CLEAR + ":"):
                ch_id = int(data.split(":")[-1])
                row = await DB.fetchone("SELECT user_id FROM user_channels WHERE id=?", (ch_id,))
                if not row or row[0] != user_id:
                    await safe_answer_query(query, "❌ غير مصرح", show_alert=True)
                    return
                await DB.execute("DELETE FROM posts WHERE channel_db_id=?", (ch_id,))
                await safe_edit_message_text(query, "✅ تم مسح جميع المنشورات!")
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if base_data == CB.GROUPS:
                await safe_answer_query(query)
                groups = await DB.get_user_groups(user_id)
                if not groups:
                    add_text = KeyboardFactory.get_text("add_group_button", lang)
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton(add_text, url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")
                    ]])
                    await safe_edit_message_text(query, "📭 لا توجد مجموعات", reply_markup=kb)
                    return
                text = "👥 **مجموعاتي**\n\n"
                kb = []
                for gid, name, username, banned in groups:
                    st = "✅" if not banned else "⛔"
                    text += f"{st} {name}\n"
                    security_text = KeyboardFactory.get_text("security_button", lang).replace("{name}", name[:15])
                    kb.append([
                        InlineKeyboardButton(
                            security_text,
                            callback_data=f"{CB.GRP_SET}:{gid}"
                        )
                    ])
                back_text = KeyboardFactory.get_text("back", lang)
                kb.append([InlineKeyboardButton(back_text, callback_data=CB.BACK)])
                await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data.startswith(CB.GRP_SET + ":"):
                chat_id = int(data.split(":")[-1])
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    await safe_answer_query(query, "❌ لا صلاحية", show_alert=True)
                    return
                settings = await DB.get_security_settings(chat_id)
                text = KeyboardFactory._format_security_text(settings)
                kb = KeyboardFactory.build("security", chat_id, lang=lang)
                await safe_edit_message_text(query, text, reply_markup=kb)
                await safe_answer_query(query)
                return

            if base_data == CB.ADMIN:
                if CONFIG.is_developer(user_id):
                    kb = KeyboardFactory.build("admin_panel", lang=lang)
                    await safe_edit_message_text(query, "👑 لوحة الأدمن", reply_markup=kb)
                    await safe_answer_query(query)
                else:
                    await safe_answer_query(query, await get_text(lang, 'unauthorized'), show_alert=True)
                return

            if data == "admin_grant_free":
                if not CONFIG.is_developer(user_id):
                    await safe_answer_query(query, "❌ غير مصرح", show_alert=True)
                    return
                StateManager.set(user_id, UserState.WAIT_GRANT_FREE)
                await safe_edit_message_text(query, "🎁 أرسل معرف المستخدم ثم عدد الأيام هكذا:\n`123456789 365`")
                await safe_answer_query(query)
                return

            if data.startswith(CB.PANEL_LOCK + ":"):
                chat_id = int(data.split(":")[-1])
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    await safe_answer_query(query, "❌ لا صلاحية", show_alert=True)
                    return
                await DB.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?,1,?,?)",
                                 (chat_id, TimeUtils.sql_iso(), user_id))
                await safe_edit_message_text(query, "🔒 تم قفل المجموعة!")
                await safe_answer_query(query)
                return

            if data.startswith(CB.PANEL_UNLOCK + ":"):
                chat_id = int(data.split(":")[-1])
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    await safe_answer_query(query, "❌ لا صلاحية", show_alert=True)
                    return
                await DB.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
                await safe_edit_message_text(query, "🔓 تم فتح المجموعة!")
                await safe_answer_query(query)
                return

            if base_data == CB.PANEL_CLOSE:
                try:
                    await query.message.delete()
                except:
                    pass
                await safe_answer_query(query, "✅ تم الإغلاق")
                return

            if data.startswith("sec_banned_words") or base_data == "sec_banned_words":
                await CallbackHandlers._handle_banned_words_direct(update, context, query, user_id, None, lang)
                return

            if data.startswith("sec_") or base_data.startswith("sec_"):
                await CallbackHandlers._handle_security(update, context, query, user_id, lang)
                return

            if data.startswith("admin_") or base_data.startswith("admin_"):
                if CONFIG.is_developer(user_id):
                    await CallbackHandlers._handle_admin(update, context, query, user_id, lang)
                return

            if data.startswith("auto_reply_") or base_data.startswith("auto_reply_"):
                await CallbackHandlers._handle_auto_reply(update, context, query, user_id, lang)
                return

            if data.startswith(SCHED_OPEN):
                ch_id = int(data.split(":")[-1])
                row = await DB.fetchone("SELECT user_id FROM user_channels WHERE id=?", (ch_id,))
                if not row or row[0] != user_id:
                    await safe_answer_query(query, "❌ غير مصرح", show_alert=True)
                    return
                kb = KeyboardFactory.build("channel_settings", chat_id=ch_id, lang=lang)
                await safe_edit_message_text(
                    query,
                    f"📅 **جدولة القناة**\nيمكنك ضبط الفاصل الزمني للنشر:",
                    reply_markup=kb
                )
                await safe_answer_query(query)
                return

            if data.startswith("sched_") or base_data.startswith("sched_"):
                await CallbackHandlers._handle_schedule(update, context, query, user_id)
                return

            if data.startswith("ban_") or base_data.startswith("ban_"):
                await CallbackHandlers._handle_banned_words(update, context, query, user_id)
                return

            if data.startswith("act_") or base_data.startswith("act_"):
                await CallbackHandlers._handle_advanced_actions(update, context, query, user_id)
                return

            if data.startswith("pen_") or base_data.startswith("pen_"):
                await CallbackHandlers._handle_penalty(update, context, query, user_id)
                return

            if data.startswith("contest_") or data.startswith(CB.DECLARE_WINNER_SEL + ":"):
                await CallbackHandlers._handle_contests(update, context, query, user_id)
                return

            if data in (CB.ADMIN_IMPORT_REPLIES, CB.ADMIN_IMPORT_GITHUB):
                await CallbackHandlers._handle_import(update, context, query, user_id)
                return

            if data.startswith("lang_"):
                lang_set = data.split("_")[-1]
                await DB.set_user_language(user_id, lang_set)
                await safe_answer_query(query, f"✅ {lang_set}")
                context.args = []
                await CommandHandlers.start(update, context)
                return

            if data.startswith(BUY_GIFT):
                await safe_answer_query(query, "🔄 جارٍ التحضير...")

                plan_id = int(data.split(":")[-1])
                plan = await DB.get_gift_plan(plan_id)
                if not plan:
                    await safe_answer_query(query, "❌ خطة غير موجودة", show_alert=True)
                    return

                invoice_number = await DB.create_invoice(
                    user_id, 
                    plan_id, 
                    plan['price'], 
                    currency='XTR', 
                    provider='xtr_gift'
                )
                if not invoice_number:
                    await safe_answer_query(query, "❌ فشل إنشاء الفاتورة", show_alert=True)
                    return

                try:
                    await context.bot.send_invoice(
                        chat_id=user_id,
                        title=f"🎁 كود هدية {plan['days']} يوم",
                        description=f"ستحصل على كود هدية لمدة {plan['days']} يوم يمكنك إرساله لأي شخص.",
                        payload=json.dumps({
                            'gift_plan_id': plan_id, 
                            'invoice': invoice_number, 
                            'type': 'gift'
                        }),
                        provider_token="",
                        currency="XTR",
                        prices=[LabeledPrice(f"{plan['days']} يوم", plan['price'])]
                    )
                    await safe_answer_query(query, "✅ تم إرسال الفاتورة")
                    try:
                        await query.message.delete()
                    except BadRequest:
                        pass
                except Exception as e:
                    logger.error(f"❌ فشل إرسال الفاتورة: {e}")
                    await DB.execute("UPDATE invoices SET status='cancelled' WHERE number=?", (invoice_number,))
                    await safe_answer_query(query, f"❌ {str(e)[:50]}", show_alert=True)
                return

            if base_data == MY_GIFTS:
                await safe_answer_query(query)
                try:
                    codes = await DB.fetchall(
                        "SELECT code, used_by, created_at FROM gift_codes WHERE creator_id=? ORDER BY created_at DESC LIMIT 20",
                        (user_id,)
                    )
                    if not codes:
                        await safe_edit_message_text(
                            query,
                            "📋 **أكواد الهدايا الخاصة بك**\n\n"
                            "🎁 لا توجد أكواد لديك بعد.\n\n"
                            "يمكنك شراء كود هدية من قائمة الباقات.",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)
                            ]])
                        )
                        return
                    text = "🎁 **أكواد الهدايا الخاصة بك:**\n\n"
                    for c in codes:
                        code_text = c['code'] if isinstance(c, dict) else c[0]
                        used_by = c['used_by'] if isinstance(c, dict) else c[1]
                        created_at = c['created_at'] if isinstance(c, dict) else c[2]
                        status = "🟢 متاح" if not used_by else "🔴 مستخدم"
                        text += f"🎟️ `{code_text}`\n"
                        text += f"📌 الحالة: {status}\n"
                        text += f"📅 التاريخ: {created_at[:10] if created_at else '-'}\n\n"
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)
                    ]])
                    await safe_edit_message_text(query, text, reply_markup=kb)
                except Exception as e:
                    logger.error(f"❌ خطأ في عرض أكواد الهدايا: {e}")
                    await safe_edit_message_text(query, "❌ **تعذر عرض أكواد الهدايا.**\n\n🔁 حاول مرة أخرى لاحقًا.")
                return

            await safe_answer_query(query, "⚠️ غير متوفر", show_alert=True)

        except Exception as e:
            logger.error(f"❌ Callback error: {e}", exc_info=True)
            try:
                await safe_answer_query(query, "❌ خطأ", show_alert=True)
            except:
                pass

    # =====================================================================
    # دوال مساعدة
    # =====================================================================

    @staticmethod
    async def _publish_single(bot, ch_db_id, ch_tele, post):
        try:
            caption = post['text'][:1024] if post['text'] else None
            media_file_id = post.get('media_file_id')
            media_type = post.get('media_type')

            if media_type == 'photo' and media_file_id:
                await bot.send_photo(chat_id=ch_tele, photo=media_file_id, caption=caption)
            elif media_type == 'video' and media_file_id:
                await bot.send_video(chat_id=ch_tele, video=media_file_id, caption=caption)
            elif media_type == 'document' and media_file_id:
                await bot.send_document(chat_id=ch_tele, document=media_file_id, caption=caption)
            elif media_type == 'audio' and media_file_id:
                await bot.send_audio(chat_id=ch_tele, audio=media_file_id, caption=caption)
            elif media_type == 'voice' and media_file_id:
                await bot.send_voice(chat_id=ch_tele, voice=media_file_id, caption=caption)
            elif media_type == 'animation' and media_file_id:
                await bot.send_animation(chat_id=ch_tele, animation=media_file_id, caption=caption)
            elif media_type == 'sticker' and media_file_id:
                await bot.send_sticker(chat_id=ch_tele, sticker=media_file_id)
            elif media_type == 'video_note' and media_file_id:
                await bot.send_video_note(chat_id=ch_tele, video_note=media_file_id)
            else:
                await bot.send_message(chat_id=ch_tele, text=post['text'][:4096] if post['text'] else ".")
            await DB.mark_post_published(post['id'])
            await DB.update_last_publish(ch_db_id)
            await DB.update_next_publish(ch_db_id)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"❌ فشل النشر التلقائي: {e}")
            await DB.increment_post_fail(post['id'])
            raise

    @staticmethod
    async def _show_channel_list(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        channels = await DB.get_user_channels(user_id)
        if not channels:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]
            ])
            await safe_edit_message_text(query, "📭 لا توجد قنوات!\nاضغط للإضافة:", reply_markup=kb)
            await safe_answer_query(query)
            return
        text = "📡 **قنواتي**\n\n"
        kb = []
        for ch in channels:
            st = "✅" if not ch['banned'] else "🚫"
            text += f"{st} {ch['channel_name']} (`{ch['channel_id']}`)\n"
            kb.append([
                InlineKeyboardButton(
                    f"📌 {ch['channel_name'][:20]}",
                    callback_data=f"{CB.CH_SEL}:{ch['id']}"
                ),
                InlineKeyboardButton(
                    KeyboardFactory.get_text("sched_btn", lang),
                    callback_data=f"{SCHED_OPEN}{ch['id']}"
                )
            ])
            kb.append([
                InlineKeyboardButton(
                    KeyboardFactory.get_text("ch_stats", lang),
                    callback_data=f"{CB.CH_STATS}:{ch['id']}"
                ),
                InlineKeyboardButton(
                    KeyboardFactory.get_text("ch_del", lang),
                    callback_data=f"{CB.CH_DEL}:{ch['id']}"
                )
            ])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
        await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(kb))
        await safe_answer_query(query)

    @staticmethod
    async def _show_post_list(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        active = await DB.get_active_channel(user_id)
        if not active:
            await safe_edit_message_text(query, "❌ لا توجد قناة نشطة")
            await safe_answer_query(query)
            return
        posts = await DB.get_user_posts(user_id, active, 10)
        text = "📋 **منشوراتي**\n\n"
        kb = []
        for p in posts:
            text += f"🆔 {p['id']}: {(p['text'] or '')[:30]}\n"
            kb.append([
                InlineKeyboardButton(f"🗑️ حذف {p['id']}", callback_data=f"{CB.POST_DEL}:{p['id']}")
            ])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("post_clear", lang), callback_data=f"{CB.POST_CLEAR}:{active}")])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("post_rec", lang), callback_data=CB.POST_REC)])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
        await safe_edit_message_text(query, text if posts else "📭 لا يوجد", reply_markup=InlineKeyboardMarkup(kb))
        await safe_answer_query(query)

    @staticmethod
    async def _handle_security(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("sec_", "")
        try:
            chat_id = int(parts[1])
        except:
            return

        logger.info(f"🔍 _handle_security: action={action}, chat_id={chat_id}, data={data}")

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_answer_query(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return

        field_map = {
            "links": "delete_links",
            "mentions": "mentions",
            "slow": "slow_mode",
            "video": "delete_videos",
            "audio": "delete_audio",
            "anim": "delete_animation",
            "service": "delete_service",
            "doc": "delete_documents",
            "sticker": "delete_stickers",
            "forward": "delete_forwarded",
            "poll": "delete_polls",
            "game": "delete_games",
            "voice": "delete_voice",
            "videonote": "delete_video_note",
            "welcome": "welcome_enabled",
            "goodbye": "goodbye_enabled",
            "flood": "antiflood_enabled",
            "night": "night_mode_enabled",
            "banned_words": "delete_banned_words",
            "approve_join": "auto_approve_join",
            "reject_join": "auto_reject_join",
            "nsfw": "nsfw_enabled"
        }

        if action in field_map:
            col = field_map[action]
            current = await DB.fetchone(f"SELECT {col} FROM group_security WHERE chat_id=?", (chat_id,))
            new_val = 1 - (current[0] if current else 0)
            await DB.execute(f"UPDATE group_security SET {col}=? WHERE chat_id=?", (new_val, chat_id))
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id, lang=lang)
            try:
                await safe_edit_message_text(query, text, reply_markup=kb)
            except BadRequest:
                pass
            await safe_answer_query(query)
            return

        if action == "enable_all":
            async with DB._get_connection() as conn:
                for f in field_map.values():
                    await conn.execute(f"UPDATE group_security SET {f}=1 WHERE chat_id=?", (chat_id,))
                await conn.commit()
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id, lang=lang)
            try:
                await safe_edit_message_text(query, text, reply_markup=kb)
            except BadRequest:
                pass
            await safe_answer_query(query)
            return

        if action == "disable_all":
            async with DB._get_connection() as conn:
                for f in field_map.values():
                    await conn.execute(f"UPDATE group_security SET {f}=0 WHERE chat_id=?", (chat_id,))
                await conn.commit()
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id, lang=lang)
            try:
                await safe_edit_message_text(query, text, reply_markup=kb)
            except BadRequest:
                pass
            await safe_answer_query(query)
            return

        if action == "toggle_banned":
            current = await DB.fetchone("SELECT delete_banned_words FROM group_security WHERE chat_id=?", (chat_id,))
            new_val = 1 - (current[0] if current else 0)
            await DB.execute("UPDATE group_security SET delete_banned_words=? WHERE chat_id=?", (new_val, chat_id))
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id, lang=lang)
            await safe_edit_message_text(query, text, reply_markup=kb)
            await safe_answer_query(query)
            return

        if action == "banned" or action == "banned_words":
            await CallbackHandlers._handle_banned_words_direct(update, context, query, user_id, chat_id, lang)
            return

        if action == "maxlen":
            StateManager.set(user_id, UserState.WAIT_MAX_LEN)
            context.user_data['sec_chat'] = chat_id
            await safe_edit_message_text(query, "📏 أرسل الحد الأقصى للطول:")
            await safe_answer_query(query)
            return

        if action == "warn":
            settings = await DB.get_security_settings(chat_id)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 العدد", callback_data=f"sec_warn_count:{chat_id}"),
                 InlineKeyboardButton("⚖️ العقوبة", callback_data=f"sec_warn_penalty:{chat_id}")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"{CB.GRP_SET}:{chat_id}")]
            ])
            await safe_edit_message_text(
                query,
                f"⚠️ **التحذيرات**\n\nالحد: {settings.get('max_warnings', 3)}\nالعقوبة: {settings.get('warn_penalty', 'ban')}",
                reply_markup=kb
            )
            await safe_answer_query(query)
            return

        if action == "warn_count":
            StateManager.set(user_id, UserState.WAIT_WARN_COUNT)
            context.user_data['sec_chat'] = chat_id
            await safe_edit_message_text(query, "📝 أرسل العدد (1-10):")
            await safe_answer_query(query)
            return

        if action == "warn_penalty":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 حظر", callback_data=f"sec_set_warn_penalty:{chat_id}:ban"),
                 InlineKeyboardButton("🔇 كتم", callback_data=f"sec_set_warn_penalty:{chat_id}:mute")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_warn:{chat_id}")]
            ])
            await safe_edit_message_text(query, "⚖️ اختر العقوبة:", reply_markup=kb)
            await safe_answer_query(query)
            return

        if action == "set_warn_penalty":
            if len(parts) >= 3:
                penalty = parts[2]
                if penalty not in DB.VALID_PENALTY_TYPES:
                    await safe_answer_query(query, "❌ نوع عقوبة غير صالح", show_alert=True)
                    return
                await DB.execute("UPDATE group_security SET warn_penalty=? WHERE chat_id=?", (penalty, chat_id))
                await safe_edit_message_text(query, f"✅ تم التعيين: {penalty}")
                await safe_answer_query(query)
            return

        if action == "del_pen":
            kb = KeyboardFactory.build("penalty", chat_id, lang=lang)
            await safe_edit_message_text(query, "⚖️ عقوبة الحذف:", reply_markup=kb)
            await safe_answer_query(query)
            return

        if action == "penalty":
            kb = KeyboardFactory.build("penalty", chat_id, lang=lang)
            await safe_edit_message_text(query, "⚖️ العقوبة:", reply_markup=kb)
            await safe_answer_query(query)
            return

        if action == "adv_act":
            kb = KeyboardFactory.build("advanced_actions", chat_id, lang=lang)
            await safe_edit_message_text(query, "🛠️ إجراءات:", reply_markup=kb)
            await safe_answer_query(query)
            return

        if action == "act_log":
            logs = await DB.get_admin_logs(chat_id, 20)
            if not logs:
                await safe_edit_message_text(query, "📭 لا توجد سجلات")
                await safe_answer_query(query)
                return
            text = "📜 **السجل**\n\n"
            for log in logs:
                text += f"• {log['action']} → {log['target_id'] or '-'}\n"
            await safe_edit_message_text(query, text)
            await safe_answer_query(query)
            return

        if action == "auto_reply_menu":
            kb = KeyboardFactory.build("auto_reply_manage", chat_id, lang=lang)
            await safe_edit_message_text(query, "📝 الردود:", reply_markup=kb)
            await safe_answer_query(query)
            return

        if action == "close":
            try:
                await query.message.delete()
            except BadRequest:
                pass
            await safe_answer_query(query)
            return

        # ========== إعدادات جديدة ==========
        if action == "antiflood_settings":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 الرسائل", callback_data=f"sec_antiflood_msgs:{chat_id}"),
                 InlineKeyboardButton("⏱️ الثواني", callback_data=f"sec_antiflood_secs:{chat_id}")],
                [InlineKeyboardButton("⚖️ العقوبة", callback_data=f"sec_antiflood_penalty:{chat_id}")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")]
            ])
            await safe_edit_message_text(query, "🌊 **إعدادات الفيضان**", reply_markup=kb)
            await safe_answer_query(query)
            return

        if action == "antiflood_msgs":
            StateManager.set(user_id, UserState.WAIT_ANTIFLOOD_MESSAGES)
            context.user_data['sec_chat'] = chat_id
            await safe_edit_message_text(query, "📊 أرسل عدد الرسائل المسموحة (1-20):")
            await safe_answer_query(query)
            return

        if action == "antiflood_secs":
            StateManager.set(user_id, UserState.WAIT_ANTIFLOOD_SECONDS)
            context.user_data['sec_chat'] = chat_id
            await safe_edit_message_text(query, "⏱️ أرسل الفترة بالثواني (1-120):")
            await safe_answer_query(query)
            return

        if action == "antiflood_penalty":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔨 حظر", callback_data=f"sec_set_antiflood_penalty:{chat_id}:ban"),
                 InlineKeyboardButton("🔇 كتم", callback_data=f"sec_set_antiflood_penalty:{chat_id}:mute")],
                [InlineKeyboardButton("🔒 تقييد", callback_data=f"sec_set_antiflood_penalty:{chat_id}:restrict")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_antiflood_settings:{chat_id}")]
            ])
            await safe_edit_message_text(query, "اختر عقوبة الفيضان:", reply_markup=kb)
            await safe_answer_query(query)
            return

        if action == "set_antiflood_penalty":
            if len(parts) >= 3:
                penalty = parts[2]
                if penalty not in DB.VALID_PENALTY_TYPES:
                    await safe_answer_query(query, "❌ نوع عقوبة غير صالح", show_alert=True)
                    return
                await DB.execute("UPDATE group_security SET antiflood_penalty=? WHERE chat_id=?", (penalty, chat_id))
                await safe_edit_message_text(query, f"✅ تم التعيين: {penalty}")
                await safe_answer_query(query)
            return

        if action == "night_settings":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🌙 البداية", callback_data=f"sec_night_start:{chat_id}"),
                 InlineKeyboardButton("☀️ النهاية", callback_data=f"sec_night_end:{chat_id}")],
                [InlineKeyboardButton("⚖️ الإجراء", callback_data=f"sec_night_action:{chat_id}")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")]
            ])
            await safe_edit_message_text(query, "🌙 **إعدادات الوضع الليلي**", reply_markup=kb)
            await safe_answer_query(query)
            return

        if action == "night_start":
            StateManager.set(user_id, UserState.WAIT_NIGHT_START)
            context.user_data['sec_chat'] = chat_id
            await safe_edit_message_text(query, "أرسل وقت البداية (HH:MM):")
            await safe_answer_query(query)
            return

        if action == "night_end":
            StateManager.set(user_id, UserState.WAIT_NIGHT_END)
            context.user_data['sec_chat'] = chat_id
            await safe_edit_message_text(query, "أرسل وقت النهاية (HH:MM):")
            await safe_answer_query(query)
            return

        if action == "night_action":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔇 كتم", callback_data=f"sec_set_night_action:{chat_id}:mute"),
                 InlineKeyboardButton("🔒 تقييد", callback_data=f"sec_set_night_action:{chat_id}:restrict")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_night_settings:{chat_id}")]
            ])
            await safe_edit_message_text(query, "اختر الإجراء الليلي:", reply_markup=kb)
            await safe_answer_query(query)
            return

        if action == "set_night_action":
            if len(parts) >= 3:
                act = parts[2]
                if act not in ('mute', 'restrict', 'ban'):
                    await safe_answer_query(query, "❌ إجراء غير صالح", show_alert=True)
                    return
                await DB.execute("UPDATE group_security SET night_mode_action=? WHERE chat_id=?", (act, chat_id))
                await safe_edit_message_text(query, f"✅ تم التعيين: {act}")
                await safe_answer_query(query)
            return

        if action == "welcome_text":
            StateManager.set(user_id, UserState.WAIT_WELCOME_TEXT)
            context.user_data['sec_chat'] = chat_id
            await safe_edit_message_text(query, "📝 أرسل نص الترحيب الجديد (استخدم {user} و {chat}):")
            await safe_answer_query(query)
            return

        if action == "goodbye_text":
            StateManager.set(user_id, UserState.WAIT_GOODBYE_TEXT)
            context.user_data['sec_chat'] = chat_id
            await safe_edit_message_text(query, "📝 أرسل نص الوداع الجديد (استخدم {user} و {chat}):")
            await safe_answer_query(query)
            return

        if action == "slow_mode_seconds":
            StateManager.set(user_id, UserState.WAIT_SLOW_MODE_SECONDS)
            context.user_data['sec_chat'] = chat_id
            await safe_edit_message_text(query, "⏱️ أرسل مدة الوضع البطيء بالثواني (1-300):")
            await safe_answer_query(query)
            return

        if action == "penalty_durations":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔇 كتم", callback_data=f"sec_mute_duration:{chat_id}"),
                 InlineKeyboardButton("🔨 حظر", callback_data=f"sec_ban_duration:{chat_id}")],
                [InlineKeyboardButton("🔒 تقييد", callback_data=f"sec_restrict_duration:{chat_id}"),
                 InlineKeyboardButton("⚠️ تحذير", callback_data=f"sec_warn_duration:{chat_id}")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")]
            ])
            await safe_edit_message_text(query, "⏳ **المدد الافتراضية للعقوبات**", reply_markup=kb)
            await safe_answer_query(query)
            return

        if action in ("mute_duration", "ban_duration", "restrict_duration", "warn_duration"):
            duration_type = action.replace("_duration", "")
            StateManager.set(user_id, UserState.WAIT_PENALTY_DEFAULT_DURATION)
            context.user_data['penalty_chat'] = chat_id
            context.user_data['penalty_type'] = duration_type
            await safe_edit_message_text(query, f"أرسل المدة بالدقائق (0 للدائم) لـ {duration_type}:")
            await safe_answer_query(query)
            return

        if action == "violation_penalties":
            kb = []
            violation_names = {
                "links": "الروابط",
                "mentions": "المنشنات",
                "banned_words": "الكلمات المحظورة",
                "flood": "التكرار",
                "max_len": "الطول الزائد",
                "service": "رسائل الخدمة",
                "videos": "الفيديو",
                "audio": "الصوت",
                "documents": "المستندات",
                "stickers": "الملصقات",
                "forwarded": "المعاد توجيهه",
                "polls": "الاستطلاعات",
                "games": "الألعاب",
                "voice": "البصمات الصوتية",
                "video_note": "رسائل الفيديو",
            }
            for v_type, v_name in violation_names.items():
                rule = await DB.get_violation_penalty(chat_id, v_type)
                if rule:
                    p_type = rule['penalty_type']
                    dur = rule['duration_seconds'] // 60
                    status = f"{p_type} ({dur} دقيقة)" if dur > 0 else f"{p_type} (دائم)"
                else:
                    status = "غير محدد"
                kb.append([InlineKeyboardButton(
                    f"{v_name}: {status}",
                    callback_data=f"sec_violation:{chat_id}:{v_type}"
                )])
            kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")])
            await safe_edit_message_text(query, "⚖️ **عقوبات المخالفات**\nاختر نوع المخالفة لضبط عقوبتها", reply_markup=InlineKeyboardMarkup(kb))
            return

        if action == "violation":
            if len(parts) >= 3:
                v_type = parts[2]
                if v_type not in VALID_VIOLATION_TYPES:
                    await safe_answer_query(query, "❌ نوع مخالفة غير صالح", show_alert=True)
                    return
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔨 حظر", callback_data=f"sec_violation_pen:{chat_id}:{v_type}:ban"),
                     InlineKeyboardButton("🔇 كتم", callback_data=f"sec_violation_pen:{chat_id}:{v_type}:mute")],
                    [InlineKeyboardButton("🔒 تقييد", callback_data=f"sec_violation_pen:{chat_id}:{v_type}:restrict")],
                    [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_violation_penalties:{chat_id}")]
                ])
                await safe_edit_message_text(query, "اختر نوع العقوبة:", reply_markup=kb)
            return

        if action == "violation_pen":
            if len(parts) >= 4:
                v_type = parts[2]
                p_type = parts[3]
                if v_type not in VALID_VIOLATION_TYPES or p_type not in DB.VALID_PENALTY_TYPES:
                    await safe_answer_query(query, "❌ بيانات غير صالحة", show_alert=True)
                    return
                StateManager.set(user_id, UserState.WAIT_PENALTY_DURATION)
                context.user_data['penalty_chat'] = chat_id
                context.user_data['penalty_vtype'] = v_type
                context.user_data['penalty_ptype'] = p_type
                context.user_data['penalty_setting'] = False
                await safe_edit_message_text(query, "⏱️ أرسل المدة بالدقائق (0 للدائم):")
            return

        await safe_answer_query(query)

    @staticmethod
    async def _handle_banned_words_direct(update, context, query, user_id, chat_id: int = None, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)

        if chat_id is None:
            data = query.data
            parts = data.split(":")
            chat_id = int(parts[1]) if len(parts) > 1 else -1

        if chat_id != -1:
            if not await is_authorized_in_group(context.bot, chat_id, user_id):
                await safe_answer_query(query, await get_text(lang, 'unauthorized'), show_alert=True)
                return
        else:
            if not CONFIG.is_developer(user_id):
                await safe_answer_query(query, "❌ غير مصرح", show_alert=True)
                return

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(KeyboardFactory.get_text("ban_add", lang), callback_data=f"ban_add:{chat_id}"),
             InlineKeyboardButton(KeyboardFactory.get_text("ban_list", lang), callback_data=f"ban_list:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("ban_rem", lang), callback_data=f"ban_rem:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}" if chat_id != -1 else CB.ADMIN)]
        ])
        await safe_edit_message_text(query, "🚫 **إدارة الكلمات المحظورة**", reply_markup=kb)
        await safe_answer_query(query)

    @staticmethod
    async def _handle_admin(update, context, query, user_id, lang=None):
        if not CONFIG.is_developer(user_id):
            await safe_answer_query(query, "❌ غير مصرح", show_alert=True)
            return

        if not lang:
            lang = await DB.get_user_language(user_id)
        data = query.data

        if data == CB.ADMIN_USERS:
            stats = await DB.get_user_stats()
            await safe_edit_message_text(query, f"👥 {stats['users']} مستخدم\n⛔ {stats['banned']} محظور")

        elif data == CB.ADMIN_BANNED:
            banned = await DB.fetchall("SELECT user_id FROM users WHERE banned=1 LIMIT 20")
            text = "⛔ **المحظورين**\n\n" + "\n".join(f"`{u[0]}`" for u in banned) if banned else "لا يوجد"
            await safe_edit_message_text(query, text)

        elif data == CB.ADMIN_UNBAN_ALL:
            await DB.execute("UPDATE users SET banned=0 WHERE banned=1")
            await safe_edit_message_text(query, "✅ تم إلغاء حظر الجميع")

        elif data == CB.ADMIN_CHANNELS:
            channels = await DB.fetchall("SELECT channel_id, channel_name, banned FROM user_channels LIMIT 50")
            text = "📡 **القنوات**\n\n" + "\n".join(f"{'✅' if not c[2] else '🚫'} {c[1]}" for c in channels)
            await safe_edit_message_text(query, text if channels else "📭 لا توجد")

        elif data == CB.ADMIN_BANNED_CH:
            channels = await DB.fetchall("SELECT channel_id, channel_name FROM user_channels WHERE banned=1")
            text = "🚫 **القنوات المحظورة**\n\n" + "\n".join(f"• {c[1]}" for c in channels)
            await safe_edit_message_text(query, text if channels else "📭 لا يوجد")

        elif data == CB.ADMIN_ACTIVATE_CH:
            await DB.execute("UPDATE user_channels SET banned=0 WHERE banned=1")
            await safe_edit_message_text(query, "✅ تم تفعيل الكل")

        elif data == CB.ADMIN_GROUPS:
            groups = await DB.fetchall("SELECT chat_id, chat_name, banned FROM bot_groups LIMIT 50")
            text = "👥 **المجموعات**\n\n" + "\n".join(f"{'✅' if not g[2] else '🚫'} {g[1]}" for g in groups)
            await safe_edit_message_text(query, text if groups else "📭 لا توجد")

        elif data == CB.ADMIN_BANNED_GR:
            groups = await DB.fetchall("SELECT chat_id, chat_name FROM bot_groups WHERE banned=1")
            text = "🚫 **المجموعات المحظورة**\n\n" + "\n".join(f"• {g[1]}" for g in groups)
            await safe_edit_message_text(query, text if groups else "📭 لا يوجد")

        elif data == CB.ADMIN_UNBAN_GR:
            await DB.execute("UPDATE bot_groups SET banned=0 WHERE banned=1")
            await safe_edit_message_text(query, "✅ تم إلغاء حظر المجموعات")

        elif data == CB.ADMIN_ADD_ADMIN:
            StateManager.set(user_id, UserState.WAIT_ADMIN_ADD)
            await safe_edit_message_text(query, "👑 أرسل معرف المشرف:")

        elif data == CB.ADMIN_REM_ADMIN:
            StateManager.set(user_id, UserState.WAIT_ADMIN_REM)
            await safe_edit_message_text(query, "🗑️ أرسل معرف المشرف:")

        elif data == CB.ADMIN_LIST_ADMINS:
            admins = await DB.fetchall("SELECT user_id FROM bot_admins")
            if not admins:
                await safe_edit_message_text(query, "📭 لا يوجد مشرفون")
            else:
                text = "👑 **مشرفو البوت**\n\n" + "\n".join(f"`{a[0]}`" for a in admins)
                await safe_edit_message_text(query, text)

        elif data == "admin_grant_free":
            StateManager.set(user_id, UserState.WAIT_GRANT_FREE)
            await safe_edit_message_text(query, "🎁 أرسل معرف المستخدم ثم عدد الأيام هكذا:\n`123456789 365`")

        elif data == CB.ADMIN_RAM:
            ram = get_ram_usage()
            await safe_edit_message_text(query, f"🖥️ الرام: {ram['percent']}%")

        elif data == CB.ADMIN_STATS:
            stats = await DB.get_bot_stats()
            text = f"👥 {stats.get('users',0)} مستخدم\n📡 {stats.get('channels',0)} قناة\n👥 {stats.get('groups',0)} مجموعة\n💎 {stats.get('active_subs',0)} اشتراك نشط"
            await safe_edit_message_text(query, text)

        elif data == CB.ADMIN_METRICS:
            m = METRICS.get_stats()
            await safe_edit_message_text(query, f"📊 API: {m.get('api_calls_last_hour', 0)}\n⚠️ أخطاء: {m.get('errors_last_hour', 0)}")

        elif data == CB.ADMIN_BACKUP:
            try:
                PATHS.BACKUPS.mkdir(parents=True, exist_ok=True)
                backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                success = backup_database(PATHS.DB, backup_file)
                if success:
                    with open(backup_file, 'rb') as f:
                        await context.bot.send_document(chat_id=user_id, document=f, filename=backup_file.name)
                    await safe_answer_query(query)
                else:
                    await safe_answer_query(query, "❌ فشل النسخ الاحتياطي", show_alert=True)
            except Exception as e:
                logger.error(f"❌ فشل النسخ الاحتياطي: {e}")
                await safe_send(context.bot, user_id, "❌ فشل النسخ الاحتياطي")

        elif data == CB.ADMIN_RESTORE:
            backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
            if not backups:
                await safe_edit_message_text(query, "📭 لا توجد نسخ")
            else:
                kb = [[InlineKeyboardButton(b.name, callback_data=f"{CB.ADMIN_RESTORE_SEL}:{b.name}")] for b in backups[:10]]
                await safe_edit_message_text(query, "🔄 اختر النسخة:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith(CB.ADMIN_RESTORE_SEL + ":"):
            filename = data.split(":")[-1]
            filepath = PATHS.BACKUPS / filename
            if filepath.exists():
                success = restore_database(filepath, PATHS.DB)
                if success:
                    await safe_edit_message_text(query, "✅ تمت الاستعادة (قد تحتاج إعادة تشغيل البوت لتصبح التغييرات سارية)")
                else:
                    await safe_edit_message_text(query, "❌ فشل الاستعادة")
            else:
                await safe_edit_message_text(query, "❌ الملف غير موجود")

        elif data == CB.ADMIN_SEND_UPDATE:
            StateManager.set(user_id, UserState.WAIT_UPDATE)
            await safe_edit_message_text(query, "📢 أرسل نص التحديث:")

        elif data == CB.ADMIN_SET_UPDATE_CH:
            StateManager.set(user_id, UserState.WAIT_UPDATE_CH)
            await safe_edit_message_text(query, "📢 أرسل معرف قناة التحديثات:")

        elif data == CB.ADMIN_SHOW_UPDATE:
            ch = await DB.get_updates_channel()
            await safe_edit_message_text(query, f"📢 قناة التحديثات: @{ch}" if ch else "📢 لا توجد قناة")

        elif data == CB.ADMIN_FORCE_SUB:
            ch = await DB.get_force_subscribe_channel()
            await safe_edit_message_text(query, f"🔒 قناة الاشتراك الإجباري: @{ch}" if ch else "🔒 غير محددة")

        elif data == CB.ADMIN_SET_FORCE:
            StateManager.set(user_id, UserState.WAIT_FORCE)
            await safe_edit_message_text(query, "🔒 أرسل معرف القناة:")

        elif data == CB.ADMIN_BROADCAST:
            StateManager.set(user_id, UserState.WAIT_BROADCAST)
            await safe_edit_message_text(query, "📨 أرسل الرسالة:")

        elif data == CB.ADMIN_TICKETS:
            tickets = await DB.get_tickets()
            if not tickets:
                await safe_edit_message_text(query, "📭 لا توجد تذاكر")
            else:
                kb = []
                for t in tickets:
                    kb.append([
                        InlineKeyboardButton(f"#{t['ticket_number']} - {t['user_id']}", callback_data=f"admin_ticket_view:{t['id']}")
                    ])
                await safe_edit_message_text(query, "📋 **التذاكر**\n\nاختر تذكرة:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("admin_ticket_view:"):
            ticket_id = int(data.split(":")[-1])
            ticket = await DB.fetchone("SELECT * FROM support_tickets WHERE id=?", (ticket_id,))
            if not ticket:
                await safe_edit_message_text(query, "❌ التذكرة غير موجودة")
                return
            text = f"📋 **تذكرة #{ticket['ticket_number']}**\n\n"
            text += f"👤 المستخدم: `{ticket['user_id']}`\n"
            text += f"💬 الرسالة: {ticket['message']}\n"
            text += f"📅 الوقت: {ticket['created_at']}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ إغلاق", callback_data=f"admin_ticket_close:{ticket_id}"),
                 InlineKeyboardButton("❌ حذف", callback_data=f"admin_ticket_delete:{ticket_id}")]
            ])
            await safe_edit_message_text(query, text, reply_markup=kb)

        elif data.startswith("admin_ticket_close:"):
            ticket_id = int(data.split(":")[-1])
            await DB.close_ticket(ticket_id)
            await safe_edit_message_text(query, "✅ تم إغلاق التذكرة")

        elif data.startswith("admin_ticket_delete:"):
            ticket_id = int(data.split(":")[-1])
            await DB.execute("DELETE FROM support_tickets WHERE id=?", (ticket_id,))
            await safe_edit_message_text(query, "✅ تم حذف التذكرة")

        elif data == CB.ADMIN_DEL_TICKETS:
            await DB.delete_all_tickets()
            await safe_edit_message_text(query, "✅ تم الحذف")

        elif data == CB.ADMIN_LOG_CH:
            log_id = await DB.get_log_channel()
            await safe_edit_message_text(query, f"📋 قناة السجلات: {log_id}" if log_id else "📋 غير محدد")

        elif data == CB.ADMIN_SET_LOG_CH:
            StateManager.set(user_id, UserState.WAIT_LOG_CH)
            await safe_edit_message_text(query, "📋 أرسل معرف القناة:")

        elif data == CB.ADMIN_REPLIES:
            stats = await DB.get_auto_reply_stats(-1, 20)
            text = "📊 **الردود**\n\n"
            for kw, cnt, source in stats:
                src = "عام" if source == "global" else "مجموعة"
                text += f"• {kw} ({cnt}) [{src}]\n"
            await safe_edit_message_text(query, text if stats else "📭 لا يوجد")

        elif data == CB.ADMIN_ADD_REPLY:
            StateManager.set(user_id, UserState.WAIT_KEYWORD)
            await safe_edit_message_text(query, "📝 أرسل الكلمة:")

        elif data == CB.ADMIN_LIST_REPLIES:
            replies = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=-1 LIMIT 20")
            text = "📋 **الردود**\n\n" + "\n".join(f"• {r[0]} ({r[1]})" for r in replies)
            await safe_edit_message_text(query, text if replies else "📭 لا يوجد")

        elif data == CB.ADMIN_DEL_REPLY:
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = -1
            await safe_edit_message_text(query, "🗑️ أرسل الكلمة:")

        elif data == CB.ADMIN_BANNED_WORDS:
            await CallbackHandlers._handle_banned_words_direct(update, context, query, user_id, -1, lang)

        elif data == CB.ADMIN_ADD_BANNED:
            StateManager.set(user_id, UserState.WAIT_GLOBAL_BAN)
            await safe_edit_message_text(query, "🚫 أرسل الكلمة:")

        elif data == CB.ADMIN_LIST_BANNED:
            words = await DB.get_banned_words(-1)
            text = "🚫 **الكلمات**\n\n" + "\n".join(words) if words else "📭 لا يوجد"
            await safe_edit_message_text(query, text)

        elif data == CB.ADMIN_REM_BANNED:
            StateManager.set(user_id, UserState.WAIT_REM_GLOBAL_BAN)
            await safe_edit_message_text(query, "🗑️ أرسل الكلمة:")

        elif data == CB.ADMIN_CREATE_CONTEST:
            StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
            await safe_edit_message_text(query, "🏆 أرسل عنوان المسابقة:")

        elif data == CB.ADMIN_DECLARE_WINNER:
            contests = await DB.fetchall("SELECT id, title FROM contests WHERE status='active'")
            if not contests:
                await safe_edit_message_text(query, "📭 لا توجد مسابقات نشطة")
            else:
                kb = [[InlineKeyboardButton(title, callback_data=f"{CB.DECLARE_WINNER_SEL}:{cid}")] for cid, title in contests]
                await safe_edit_message_text(query, "اختر المسابقة:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith(CB.ADMIN_DEL_CONTEST + ":"):
            cid = int(data.split(":")[-1])
            await DB.delete_contest(cid, user_id)
            await safe_edit_message_text(query, "✅ تم حذف المسابقة")

        elif data == CB.ADMIN_EXPORT_REPLIES:
            count = await export_auto_replies(-1)
            await safe_edit_message_text(query, f"✅ تم تصدير {count} رد")

        elif data == CB.ADMIN_REFRESH_CACHE:
            _auto_reply_cache.invalidate()
            await safe_edit_message_text(query, "🔄 تم تحديث الكاش")

        elif data in (CB.ADMIN_IMPORT_REPLIES, CB.ADMIN_IMPORT_GITHUB):
            await CallbackHandlers._handle_import(update, context, query, user_id)

        elif data == CB.ADMIN_INVOICES:
            invoices = await DB.fetchall("SELECT * FROM invoices ORDER BY created_at DESC LIMIT 20")
            if not invoices:
                await safe_edit_message_text(query, "📭 لا توجد فواتير")
            else:
                text = "🧾 **أحدث الفواتير**\n\n"
                for inv in invoices:
                    text += f"🔹 #{inv['number']} - المستخدم: {inv['user_id']} - المبلغ: {inv['amount']} - الحالة: {inv['status']}\n"
                await safe_edit_message_text(query, text)

        elif data == CB.ADMIN_PAYMENT_LOGS:
            logs = await DB.fetchall("SELECT * FROM payment_logs ORDER BY created_at DESC LIMIT 20")
            if not logs:
                await safe_edit_message_text(query, "📭 لا توجد سجلات دفع")
            else:
                text = "📊 **سجلات الدفع**\n\n"
                for log in logs:
                    text += f"🔹 {log['event_type']} - المستخدم: {log['user_id']} - الوقت: {log['created_at']}\n"
                await safe_edit_message_text(query, text)

        else:
            await safe_answer_query(query, "⚠️ غير متوفر", show_alert=True)

    # =====================================================================
    # بقية دوال CallbackHandlers تبقى كما هي
    # =====================================================================

    @staticmethod
    async def _handle_auto_reply(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("auto_reply_", "")
        try:
            chat_id = int(parts[1])
        except:
            return

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_answer_query(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return

        settings = await DB.get_auto_reply_settings(chat_id)
        current_enabled = settings.get('enabled', False)

        if action == "toggle":
            await safe_answer_query(query, "🔄 جارٍ التحديث...")
            new_enabled = not current_enabled
            await DB.update_auto_reply_settings(chat_id, enabled=new_enabled)
            _auto_reply_cache.invalidate()
            status_text = "✅ **تم تفعيل الردود التلقائية!**" if new_enabled else "❌ **تم تعطيل الردود التلقائية!**"
            await safe_edit_message_text(
                query,
                status_text,
                reply_markup=KeyboardFactory.build("auto_reply_manage", chat_id, lang=lang)
            )
            return

        if action == "menu":
            await safe_answer_query(query)
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return

        if action == "admins":
            await DB.update_auto_reply_settings(chat_id, only_admins=not settings.get('only_admins', False))
            await safe_answer_query(query, "✅ تم")
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return

        if action == "reset":
            await DB.reset_auto_replies(chat_id)
            _auto_reply_cache.invalidate()
            await safe_answer_query(query, "✅ تم حذف جميع الردود")
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return

        if action == "add":
            StateManager.set(user_id, UserState.WAIT_AUTO_KEY)
            context.user_data['auto_chat'] = chat_id
            await safe_edit_message_text(query, "📝 أرسل الكلمة المفتاحية:")
            await safe_answer_query(query)
            return

        if action == "del":
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = chat_id
            await safe_edit_message_text(query, "🗑️ أرسل الكلمة لحذفها:")
            await safe_answer_query(query)
            return

        if action == "stats":
            rows = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? LIMIT 10", (chat_id,))
            text = "📊 **الإحصائيات**\n\n" + "\n".join(f"• {r[0]}: {r[1]}" for r in rows) if rows else "📭 لا يوجد"
            await safe_edit_message_text(query, text)
            await safe_answer_query(query)
            return

        if action == "list":
            rows = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=? LIMIT 20", (chat_id,))
            text = "📋 **الردود**\n\n" + "\n".join(f"• {r[0]}" for r in rows) if rows else "📭 لا يوجد"
            await safe_edit_message_text(query, text)
            await safe_answer_query(query)
            return

    @staticmethod
    async def _show_auto_reply_menu(update, context, query, user_id, lang):
        if not lang:
            lang = await DB.get_user_language(user_id)
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        try:
            chat_id = int(parts[1])
        except:
            return
        settings = await DB.get_auto_reply_settings(chat_id)
        current_enabled = settings.get('enabled', False)
        status_icon = "🟢" if current_enabled else "🔴"
        status_text = "مفعل" if current_enabled else "معطل"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{status_icon} الحالة: {status_text}", callback_data="status_only")],
            [InlineKeyboardButton(
                f"🔄 {'إيقاف' if current_enabled else 'تشغيل'} الردود",
                callback_data=f"auto_reply_toggle:{chat_id}"
            )],
            [InlineKeyboardButton(KeyboardFactory.get_text("auto_reply_admins", lang), callback_data=f"auto_reply_admins:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("auto_reply_add", lang), callback_data=f"auto_reply_add:{chat_id}"),
             InlineKeyboardButton(KeyboardFactory.get_text("auto_reply_del", lang), callback_data=f"auto_reply_del:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("auto_reply_list", lang), callback_data=f"auto_reply_list:{chat_id}"),
             InlineKeyboardButton(KeyboardFactory.get_text("auto_reply_stats", lang), callback_data=f"auto_reply_stats:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("auto_reply_reset", lang), callback_data=f"auto_reply_reset:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")]
        ])
        await safe_edit_message_text(query, "📝 **إدارة الردود التلقائية**", reply_markup=kb)

    @staticmethod
    async def _handle_schedule(update, context, query, user_id):
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("sched_", "")
        try:
            ch_id = int(parts[1])
        except:
            return

        row = await DB.fetchone("SELECT user_id FROM user_channels WHERE id=?", (ch_id,))
        if not row or row[0] != user_id:
            await safe_answer_query(query, "❌ غير مصرح", show_alert=True)
            return

        if action == "min":
            StateManager.set(user_id, UserState.WAIT_MIN)
            context.user_data['schedule_ch'] = ch_id
            min_val = await get_min_publish_interval()
            await safe_edit_message_text(
                query,
                f"📅 أرسل عدد الدقائق (الحد الأدنى {min_val} دقيقة، كحد أقصى 1440):"
            )
            await safe_answer_query(query)
        elif action == "hour":
            StateManager.set(user_id, UserState.WAIT_HOUR)
            context.user_data['schedule_ch'] = ch_id
            await safe_edit_message_text(query, "📅 أرسل عدد الساعات (1-168):")
            await safe_answer_query(query)
        elif action == "day":
            StateManager.set(user_id, UserState.WAIT_DAY)
            context.user_data['schedule_ch'] = ch_id
            await safe_edit_message_text(query, "📅 أرسل عدد الأيام (1-365):")
            await safe_answer_query(query)
        elif action == "time":
            StateManager.set(user_id, UserState.WAIT_PUB_TIME)
            context.user_data['schedule_ch'] = ch_id
            await safe_edit_message_text(query, "🕐 أرسل وقت النشر (HH:MM):")
            await safe_answer_query(query)

    @staticmethod
    async def _handle_banned_words(update, context, query, user_id):
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("ban_", "")
        try:
            chat_id = int(parts[1])
        except:
            return

        if chat_id == -1:
            if not CONFIG.is_developer(user_id):
                await safe_answer_query(query, "❌ غير مصرح", show_alert=True)
                return
        else:
            try:
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    lang = await DB.get_user_language(user_id)
                    await safe_answer_query(query, await get_text(lang, 'unauthorized'), show_alert=True)
                    return
            except Exception as e:
                logger.warning(f"⚠️ فشل التحقق من الصلاحية: {e}")
                await safe_answer_query(query, "❌ تعذر التحقق من الصلاحية", show_alert=True)
                return

        if action == "add":
            StateManager.set(user_id, UserState.WAIT_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            text = "📝 أرسل الكلمة المحظورة:"
            try:
                await safe_edit_message_text(query, text)
            except BadRequest as e:
                logger.warning(f"⚠️ edit_message_text فشل: {e}")
                await safe_send(context.bot, user_id, text)
            await safe_answer_query(query)
        elif action == "list":
            words = await DB.get_banned_words(chat_id)
            if not words:
                text = "📭 لا توجد كلمات محظورة"
            else:
                text = "🚫 **الكلمات المحظورة**\n\n" + "\n".join(f"• {w}" for w in words)
            try:
                await safe_edit_message_text(query, text)
            except BadRequest as e:
                logger.warning(f"⚠️ edit_message_text فشل: {e}")
                await safe_send(context.bot, user_id, text)
            await safe_answer_query(query)
        elif action == "rem":
            StateManager.set(user_id, UserState.WAIT_REM_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            text = "🗑️ أرسل الكلمة لحذفها:"
            try:
                await safe_edit_message_text(query, text)
            except BadRequest as e:
                logger.warning(f"⚠️ edit_message_text فشل: {e}")
                await safe_send(context.bot, user_id, text)
            await safe_answer_query(query)

    @staticmethod
    async def _handle_advanced_actions(update, context, query, user_id):
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("act_", "")
        try:
            chat_id = int(parts[1])
        except:
            return

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id)
            await safe_answer_query(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return

        actions = {
            "ban": (UserState.WAIT_BAN, "🚫 أرسل معرف المستخدم والمدة بالدقائق (مثال: 123456 30)\nاترك المدة فارغة لاستخدام 60 ثانية افتراضية"),
            "mute": (UserState.WAIT_MUTE, "🔇 أرسل معرف المستخدم والمدة بالدقائق (مثال: 123456 30)\nاترك المدة فارغة لاستخدام 60 ثانية افتراضية"),
            "warn": (UserState.WAIT_WARN, "⚠️ أرسل معرف المستخدم:"),
            "kick": (UserState.WAIT_KICK, "👢 أرسل معرف المستخدم:"),
            "restrict": (UserState.WAIT_RESTRICT, "🔒 أرسل معرف المستخدم والمدة بالدقائق (مثال: 123456 30)\nاترك المدة فارغة لاستخدام 60 ثانية افتراضية"),
            "unban": (UserState.WAIT_UNBAN, "🔓 أرسل معرف المستخدم:"),
            "pin": (UserState.WAIT_PIN, "📌 أرسل معرف الرسالة أو رد عليها:"),
        }
        if action in actions:
            state, text = actions[action]
            StateManager.set(user_id, state)
            context.user_data['adv_chat'] = chat_id
            await safe_edit_message_text(query, text)
            await safe_answer_query(query)

    @staticmethod
    async def _handle_penalty(update, context, query, user_id):
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        penalty = parts[0].replace("pen_", "")
        try:
            chat_id = int(parts[1])
        except:
            return

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id)
            await safe_answer_query(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return

        if penalty not in DB.VALID_PENALTY_TYPES:
            await safe_answer_query(query, "❌ نوع عقوبة غير صالح", show_alert=True)
            return

        await DB.execute("UPDATE group_security SET auto_penalty=? WHERE chat_id=?", (penalty, chat_id))
        await safe_edit_message_text(query, f"✅ تم تعيين العقوبة: {penalty}")
        await safe_answer_query(query)

    @staticmethod
    async def _handle_contests(update, context, query, user_id):
        data = query.data
        if data == CB.ADMIN_CREATE_CONTEST:
            StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
            await safe_edit_message_text(query, "🏆 أرسل عنوان المسابقة:")
            await safe_answer_query(query)
        elif data.startswith(CB.CONTEST_JOIN + ":"):
            cid = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
            context.user_data['contest_join'] = cid
            await safe_edit_message_text(query, "📝 أرسل إجابتك:")
            await safe_answer_query(query)
        elif data == CB.CONTEST_WINNERS:
            winners = await DB.get_contest_winners(10)
            if not winners:
                await safe_edit_message_text(query, "📭 لا يوجد فائزون")
            else:
                text = "🏆 **الفائزون**\n\n" + "\n".join(f"• {w['title']} → `{w['winner_id']}`" for w in winners)
                await safe_edit_message_text(query, text)
            await safe_answer_query(query)
        elif data.startswith(CB.DECLARE_WINNER_SEL + ":"):
            if not CONFIG.is_developer(user_id):
                await safe_answer_query(query, "❌ غير مصرح", show_alert=True)
                return
            cid = int(data.split(":")[-1])
            row = await DB.fetchone("SELECT status FROM contests WHERE id=?", (cid,))
            if not row or row[0] != 'active':
                await safe_answer_query(query, "❌ المسابقة غير نشطة", show_alert=True)
                return
            winner = await DB.fetchone("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,))
            if winner:
                success = await DB.declare_winner(cid, winner[0])
                if success:
                    await safe_edit_message_text(query, f"✅ الفائز: `{winner[0]}`")
                    try:
                        await context.bot.send_message(winner[0], f"🎉 مبروك! لقد فزت بالمسابقة!")
                    except Exception as e:
                        logger.warning(f"⚠️ فشل إشعار الفائز {winner[0]}: {e}")
                else:
                    await safe_answer_query(query, "❌ فشل إعلان الفائز", show_alert=True)
                    return
            await safe_answer_query(query)

    @staticmethod
    async def _handle_import(update, context, query, user_id):
        if not CONFIG.is_developer(user_id):
            await safe_answer_query(query, "❌ غير مصرح", show_alert=True)
            return
        data = query.data
        if data == CB.ADMIN_IMPORT_REPLIES:
            StateManager.set(user_id, UserState.WAIT_IMPORT_FILE)
            context.user_data['import_chat_id'] = -1
            await safe_edit_message_text(query, "📤 أرسل ملف JSON للاستيراد:")
            await safe_answer_query(query)
        elif data == CB.ADMIN_IMPORT_GITHUB:
            StateManager.set(user_id, UserState.WAIT_GITHUB_URL)
            await safe_edit_message_text(query, "📥 أرسل رابط GitHub (JSON):")
            await safe_answer_query(query)


# =====================================================================
# 3. معالج الرسائل
# =====================================================================

class MessageHandlers:
    @staticmethod
    async def handle_private(update, context):
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        msg = update.message
        text = msg.text.strip() if msg.text else ""
        state = StateManager.get(user_id)

        # (معظم الكود السابق يبقى كما هو، مع إضافة حالات جديدة)

        if state == UserState.WAIT_ANTIFLOOD_MESSAGES:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and 1 <= val <= 20:
                    await DB.execute("UPDATE group_security SET antiflood_messages=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين عدد الرسائل إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (1-20)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            finally:
                StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ANTIFLOOD_SECONDS:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and 1 <= val <= 120:
                    await DB.execute("UPDATE group_security SET antiflood_seconds=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين الفترة إلى {val} ثانية")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (1-120)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            finally:
                StateManager.clear(user_id)
            return

        if state == UserState.WAIT_NIGHT_START:
            try:
                if re.match(r'^\d{2}:\d{2}$', text):
                    parts_time = text.split(":")
                    hour = int(parts_time[0])
                    minute = int(parts_time[1])
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        chat_id_sec = context.user_data.get('sec_chat')
                        if chat_id_sec:
                            await DB.execute("UPDATE group_security SET night_mode_start=? WHERE chat_id=?", (text, chat_id_sec))
                            await safe_send(context.bot, user_id, f"✅ تم تعيين وقت البداية إلى {text}")
                    else:
                        await safe_send(context.bot, user_id, "❌ وقت غير صالح")
                else:
                    await safe_send(context.bot, user_id, "❌ استخدم HH:MM")
            except Exception as e:
                logger.error(f"❌ خطأ: {e}")
            finally:
                StateManager.clear(user_id)
            return

        if state == UserState.WAIT_NIGHT_END:
            try:
                if re.match(r'^\d{2}:\d{2}$', text):
                    parts_time = text.split(":")
                    hour = int(parts_time[0])
                    minute = int(parts_time[1])
                    if 0 <= hour <= 23 and 0 <= minute <= 59:
                        chat_id_sec = context.user_data.get('sec_chat')
                        if chat_id_sec:
                            await DB.execute("UPDATE group_security SET night_mode_end=? WHERE chat_id=?", (text, chat_id_sec))
                            await safe_send(context.bot, user_id, f"✅ تم تعيين وقت النهاية إلى {text}")
                    else:
                        await safe_send(context.bot, user_id, "❌ وقت غير صالح")
                else:
                    await safe_send(context.bot, user_id, "❌ استخدم HH:MM")
            except Exception as e:
                logger.error(f"❌ خطأ: {e}")
            finally:
                StateManager.clear(user_id)
            return

        if state == UserState.WAIT_WELCOME_TEXT:
            chat_id_sec = context.user_data.get('sec_chat')
            if chat_id_sec:
                await DB.execute("UPDATE group_security SET welcome_text=? WHERE chat_id=?", (text, chat_id_sec))
                await safe_send(context.bot, user_id, "✅ تم تحديث نص الترحيب")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GOODBYE_TEXT:
            chat_id_sec = context.user_data.get('sec_chat')
            if chat_id_sec:
                await DB.execute("UPDATE group_security SET goodbye_text=? WHERE chat_id=?", (text, chat_id_sec))
                await safe_send(context.bot, user_id, "✅ تم تحديث نص الوداع")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_SLOW_MODE_SECONDS:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and 1 <= val <= 300:
                    await DB.execute("UPDATE group_security SET slow_mode_seconds=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين مدة الوضع البطيء إلى {val} ثانية")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (1-300)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            finally:
                StateManager.clear(user_id)
            return

        # معالجة المدة الافتراضية للعقوبات
        if state == UserState.WAIT_PENALTY_DEFAULT_DURATION:
            try:
                dur_minutes = int(text)
                if dur_minutes < 0 or dur_minutes > 1440:
                    await safe_send(context.bot, user_id, "❌ المدة غير صالحة (0-1440 دقيقة)")
                    return
                chat_id_pen = context.user_data.get('penalty_chat')
                penalty_type = context.user_data.get('penalty_type')
                if chat_id_pen and penalty_type:
                    duration_seconds = dur_minutes * 60 if dur_minutes > 0 else 0
                    column = f"{penalty_type}_default_duration"
                    await DB.execute(f"UPDATE group_security SET {column}=? WHERE chat_id=?", (duration_seconds, chat_id_pen))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين المدة الافتراضية لـ {penalty_type} إلى {dur_minutes} دقيقة")
                else:
                    await safe_send(context.bot, user_id, "❌ بيانات غير مكتملة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            finally:
                StateManager.clear(user_id)
            return

        # معالجة مدة عقوبة المخالفة
        if state == UserState.WAIT_PENALTY_DURATION:
            try:
                dur_minutes = int(text)
                if dur_minutes < 0 or dur_minutes > 1440:
                    await safe_send(context.bot, user_id, "❌ المدة غير صالحة (0-1440 دقيقة)")
                    return
                chat_id_pen = context.user_data.get('penalty_chat')
                v_type = context.user_data.get('penalty_vtype')
                p_type = context.user_data.get('penalty_ptype')
                if chat_id_pen and v_type and p_type:
                    duration_seconds = dur_minutes * 60 if dur_minutes > 0 else 0
                    await DB.set_violation_penalty(chat_id_pen, v_type, p_type, duration_seconds)
                    await safe_send(context.bot, user_id, "✅ تم حفظ العقوبة بنجاح")
                else:
                    await safe_send(context.bot, user_id, "❌ بيانات غير مكتملة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            finally:
                StateManager.clear(user_id)
            return

        # (باقي معالجات الحالات كما في السابق)
        # ...

        # الرسالة الافتراضية
        await CommandHandlers.start(update, context)

    @staticmethod
    async def handle_group(update, context):
        if not update.message or not update.effective_user:
            return
        chat = update.effective_chat
        if not chat or chat.type not in ['group', 'supergroup']:
            return
        chat_id = chat.id
        text = update.message.text or ""
        if update.effective_user.is_bot:
            return

        locked = await DB.fetchone("SELECT locked FROM chat_locks WHERE chat_id=?", (chat_id,))
        if locked and locked[0] == 1:
            if not await is_authorized_in_group(context.bot, chat_id, update.effective_user.id):
                try:
                    await update.message.delete()
                except:
                    pass
                return

        settings = await DB.get_security_settings(chat_id)
        perms = await check_bot_permissions(context.bot, chat_id)
        can_delete = perms.get('can_delete_messages', perms.get('can_act', False))

        if await is_authorized_in_group(context.bot, chat_id, update.effective_user.id):
            ars = await DB.get_auto_reply_settings(chat_id)
            if ars.get('enabled', False):
                reply = get_reply_from_file(text.lower().strip())
                if not reply:
                    reply_data = await DB.get_auto_reply(text.lower().strip(), chat_id)
                    if reply_data:
                        reply = reply_data.get('reply')
                if reply:
                    try:
                        await update.message.reply_text(reply)
                        await _increment_usage_async(chat_id, text.lower().strip())
                    except:
                        pass
            return

        if settings.get('delete_links', False) and TextUtils.contains_link(text):
            if can_delete:
                try:
                    await update.message.delete()
                except:
                    pass
            await apply_violation_penalty(context, chat_id, update.effective_user.id, 'links', "مخالفة روابط", settings)
            return

        if settings.get('mentions', False) and TextUtils.contains_mention(text):
            if can_delete:
                try:
                    await update.message.delete()
                except:
                    pass
            await apply_violation_penalty(context, chat_id, update.effective_user.id, 'mentions', "مخالفة منشن", settings)
            return

        if settings.get('delete_banned_words', False):
            banned_words = await get_banned_words_cached(chat_id)
            if any(word in text.lower() for word in banned_words):
                if can_delete:
                    try:
                        await update.message.delete()
                    except:
                        pass
                await apply_violation_penalty(context, chat_id, update.effective_user.id, 'banned_words', "كلمة محظورة", settings)
                return

        ars = await DB.get_auto_reply_settings(chat_id)
        if ars.get('enabled', False):
            reply = get_reply_from_file(text.lower().strip())
            if not reply:
                reply_data = await DB.get_auto_reply(text.lower().strip(), chat_id)
                if reply_data:
                    reply = reply_data.get('reply')
            if reply:
                try:
                    await update.message.reply_text(reply)
                    await _increment_usage_async(chat_id, text.lower().strip())
                except:
                    pass

    @staticmethod
    async def handle_service(update, context):
        if not update.message or not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        settings = await DB.get_security_settings(chat_id)

        if settings.get('delete_service', False):
            try:
                await update.message.delete()
            except:
                pass
            user_id = update.message.from_user.id if update.message.from_user else None
            if user_id:
                await apply_violation_penalty(context, chat_id, user_id, 'service', "رسالة خدمة", settings)

        if settings.get('welcome_enabled', False) and update.message.new_chat_members:
            for member in update.message.new_chat_members:
                if member.id != context.bot.id:
                    welcome_text = settings.get('welcome_text', "مرحباً {user} 🤍")
                    text = welcome_text.format(user=member.full_name or "العضو")
                    try:
                        await context.bot.send_message(chat_id, text)
                    except:
                        pass

        if settings.get('goodbye_enabled', False) and update.message.left_chat_member:
            member = update.message.left_chat_member
            if member.id != context.bot.id:
                goodbye_text = settings.get('goodbye_text', "وداعاً {user} 👋")
                text = goodbye_text.format(user=member.full_name or "العضو")
                try:
                    await context.bot.send_message(chat_id, text)
                except:
                    pass

    @staticmethod
    async def handle_join_request(update, context):
        join_request = update.chat_join_request
        chat_id = update.effective_chat.id
        settings = await DB.get_security_settings(chat_id)

        if settings.get('auto_approve_join', False):
            try:
                await join_request.approve()
                if settings.get('welcome_enabled', False):
                    await context.bot.send_message(chat_id, f"مرحباً {join_request.from_user.full_name} 🤍")
            except:
                pass
            return

        if settings.get('auto_reject_join', False):
            try:
                await join_request.decline()
            except:
                pass


# =====================================================================
# دالة تطبيق العقوبة المخصصة
# =====================================================================

async def apply_violation_penalty(context, chat_id, user_id, violation_type, reason="مخالفة", settings=None):
    if await is_authorized_in_group(context.bot, chat_id, user_id):
        return

    if settings is None:
        settings = await DB.get_security_settings(chat_id)

    warnings = await DB.add_user_warning(user_id, chat_id)

    rule = await DB.get_violation_penalty(chat_id, violation_type)
    if not rule:
        penalty_type = settings.get('warn_penalty', 'ban')
        duration_seconds = 0
    else:
        penalty_type = rule['penalty_type']
        duration_seconds = rule['duration_seconds']

    if penalty_type not in DB.VALID_PENALTY_TYPES:
        penalty_type = 'ban'
        duration_seconds = 0

    max_warnings = settings.get('max_warnings', 3)

    if warnings < max_warnings:
        try:
            await context.bot.send_message(
                user_id,
                f"⚠️ لقد تلقيت إنذارًا ({warnings}/{max_warnings}) في المجموعة بسبب: {reason}"
            )
        except:
            pass
        return

    try:
        if penalty_type in ('ban', 'mute', 'restrict'):
            until_date = TimeUtils.utc_now() + timedelta(seconds=duration_seconds) if duration_seconds > 0 else None
            if penalty_type == 'ban':
                await context.bot.ban_chat_member(chat_id, user_id, until_date=until_date)
            elif penalty_type == 'mute':
                await context.bot.restrict_chat_member(
                    chat_id, user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date
                )
            elif penalty_type == 'restrict':
                await context.bot.restrict_chat_member(
                    chat_id, user_id,
                    permissions=ChatPermissions(can_send_messages=False, can_send_media_messages=False),
                    until_date=until_date
                )
            await DB.add_penalty(
                user_id=user_id,
                chat_id=chat_id,
                penalty_type=penalty_type,
                duration=duration_seconds,
                reason=reason,
                issued_by=0
            )
            await DB.reset_user_warnings(user_id, chat_id)
        else:
            logger.error(f"❌ نوع عقوبة غير صالح في apply_violation_penalty: {penalty_type}")
            await DB.reset_user_warnings(user_id, chat_id)
    except Exception as e:
        logger.error(f"❌ فشل تطبيق عقوبة {penalty_type} على {user_id}: {e}")
