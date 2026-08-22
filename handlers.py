#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers.py - جميع معالجات البوت (نسخة نهائية مصححة)
- إصلاح مشكلة حفظ القناة
- إصلاح مشكلة بقاء حالة ADDING_POSTS
- معالجة جميع أزرار الأمان واللوحة
- مدد جاهزة للعقوبات (افتراضية ومخالفات)
- الفواتير وسجلات الدفع
"""

import asyncio
import os
import re
import shutil
import logging
import json
import time
import html
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple, Any

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
                        await safe_send(update.effective_chat.bot, referrer,
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
                    await safe_send(context.bot, user_id, "⚠️ اشترك في القناة أولاً", reply_markup=kb)
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
        await safe_send(context.bot, user_id, await get_text(lang, 'trial_activated', days=days))

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
        context.user_data['security_chat_id'] = chat_id
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

        bot_perms = await check_bot_permissions(context.bot, chat_id)
        if not bot_perms.get('can_act', False):
            await safe_send(context.bot, user_id, "⚠️ **البوت ليس مشرفاً!**")
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
        duration_seconds = 60
        if len(args) > 1:
            try:
                minutes = int(args[1])
                if minutes > 0:
                    duration_seconds = minutes * 60
                    reason_parts = args[2:]
                else:
                    reason_parts = args[1:]
            except ValueError:
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
                callback_data=f"buy_gift:{plan['id']}"
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
                try:
                    await query.answer("لا تغيير")
                except BadRequest:
                    pass
                return

            if base_data == "start_btn":
                try:
                    await query.answer()
                except BadRequest:
                    pass
                context.args = []
                await CommandHandlers.start(update, context)
                return

            if base_data in [CB.MAIN, CB.BACK]:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                StateManager.clear(user_id)
                context.args = []
                await CommandHandlers.start(update, context)
                return

            if base_data == CB.CANCEL:
                StateManager.clear(user_id)
                try:
                    await query.answer("❌ تم الإلغاء")
                except BadRequest:
                    pass
                return

            if base_data == CB.HELP:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                await CommandHandlers.help_command(update, context)
                return

            if base_data == CB.TRIAL:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                if await DB.has_used_trial(user_id):
                    await query.edit_message_text(await get_text(lang, 'trial_used'))
                    return
                days = await DB.activate_trial(user_id)
                await query.edit_message_text(await get_text(lang, 'trial_activated', days=days))
                return

            if base_data == CB.DEVELOPER:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                await CommandHandlers.developer(update, context)
                return

            if base_data == CB.SUBSCRIBE:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                await CommandHandlers.subscribe(update, context)
                return

            if base_data == CB.SUPPORT:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                await CommandHandlers.support(update, context)
                return

            if base_data == CB.LANGUAGE:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                await CommandHandlers.language(update, context)
                return

            if base_data == CB.CHECK_SUB:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                context.args = []
                await CommandHandlers.start(update, context)
                return

            # ========== الإعدادات ==========
            if base_data == CB.SETTINGS:
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings", lang=lang)
                await query.edit_message_text(
                    f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}",
                    reply_markup=kb
                )
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if base_data == CB.TOGGLE_AUTO:
                try:
                    await query.answer("🔄 جارٍ التحديث...")
                except BadRequest:
                    pass
                cur = await DB.get_auto_publish_status(user_id)
                await DB.set_auto_publish(user_id, not cur)
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings", lang=lang)
                await query.edit_message_text(
                    f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}",
                    reply_markup=kb
                )
                return

            if base_data == CB.TOGGLE_REC:
                try:
                    await query.answer("🔄 جارٍ التحديث...")
                except BadRequest:
                    pass
                cur = await DB.get_auto_recycle_status(user_id)
                await DB.set_auto_recycle(user_id, not cur)
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings", lang=lang)
                await query.edit_message_text(
                    f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}",
                    reply_markup=kb
                )
                return

            if base_data == CB.PLANS:
                kb = KeyboardFactory.build("plans", lang=lang)
                await query.edit_message_text(await get_text(lang, 'plan_selector'), reply_markup=kb)
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if base_data == "gift_plans":
                try:
                    await query.answer()
                except BadRequest:
                    pass

                plans = await DB.get_gift_plans()
                if not plans:
                    await query.edit_message_text("📭 لا توجد خطط متاحة حالياً.")
                    return

                kb = []
                for plan in plans:
                    days = plan['days']
                    price = plan['price']
                    kb.append([InlineKeyboardButton(
                        f"🎁 {days} يوم - {price} ⭐",
                        callback_data=f"buy_gift:{plan['id']}"
                    )])
                kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])

                text = "💎 **شراء كود هدية**\n\nاختر المدة المناسبة:\n\n"
                text += "• بعد الدفع، ستحصل على كود فريد.\n"
                text += "• يمكنك إرسال الكود لأي شخص.\n"
                text += "• الشخص الذي يستخدم الكود يحصل على اشتراك مجاني."

                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if base_data == "redeem_gift":
                try:
                    await query.answer()
                except BadRequest:
                    pass
                await CommandHandlers.redeem_gift(update, context)
                return

            if data.startswith("buy_sub_"):
                try:
                    await query.answer("🔄 جارٍ التحضير...")
                except BadRequest:
                    pass
                days = int(data.split("_")[-1])
                plan_names = {1: "يوم", 7: "أسبوع", 30: "شهر", 90: "3 أشهر", 365: "سنة"}
                plan_name = plan_names.get(days)
                if not plan_name:
                    try:
                        await query.answer("❌ باقة غير موجودة", show_alert=True)
                    except BadRequest:
                        pass
                    return
                plan = await DB.get_plan_by_name(plan_name)
                if not plan:
                    try:
                        await query.answer("❌ باقة غير موجودة", show_alert=True)
                    except BadRequest:
                        pass
                    return

                invoice_number = await DB.create_invoice(user_id, plan['id'], plan['price'])
                if not invoice_number:
                    try:
                        await query.answer("❌ فشل الدفع", show_alert=True)
                    except BadRequest:
                        pass
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
                    await query.answer("✅ تم إرسال الفاتورة")
                    await query.message.delete()
                except Exception as e:
                    logger.error(f"❌ فشل إرسال الفاتورة: {e}")
                    await DB.execute("UPDATE invoices SET status='cancelled' WHERE number=?", (invoice_number,))
                    try:
                        await query.answer(f"❌ {str(e)[:50]}", show_alert=True)
                    except BadRequest:
                        pass
                return

            if base_data == CB.INVOICES:
                invoices = await DB.get_user_invoices(user_id, 10)
                if not invoices:
                    await query.edit_message_text("📭 لا توجد فواتير")
                    try:
                        await query.answer()
                    except BadRequest:
                        pass
                    return
                text = "🧾 **فواتيري**\n\n"
                for inv in invoices:
                    text += f"• #{inv['number']} - {inv['amount']} ⭐\n"
                kb = [[InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if base_data == CB.REFERRAL:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                stats = await DB.get_referral_stats(user_id)
                code = await DB.get_referral_code(user_id)
                text = f"🔗 **الإحالات**\n\n🔗 `https://t.me/{CONFIG.BOT_USERNAME}?start=ref_{code}`\n👥 {stats['total']}\n🎁 {stats['available']} يوم"
                kb = KeyboardFactory.build("referral", lang=lang)
                await query.edit_message_text(text, reply_markup=kb)
                return

            if base_data == CB.REF_CLAIM:
                try:
                    await query.answer("🔄 جارٍ الصرف...")
                except BadRequest:
                    pass
                days = await DB.claim_referral_reward(user_id)
                await query.edit_message_text(f"✅ {days} يوم!" if days else "📭 لا توجد")
                return

            if base_data == CB.REF_LIST:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                referrals = await DB.get_referrals_list(user_id)
                text = "📋 **المُحالين**\n\n" + "\n".join([f"• `{r}`" for r in referrals[:20]]) if referrals else "📭 لا يوجد"
                await query.edit_message_text(text)
                return

            if base_data in [CB.REM_TOGGLE_SUB, CB.REM_TOGGLE_DAILY, CB.REM_TOGGLE_WEEKLY]:
                try:
                    await query.answer("🔄 جارٍ التحديث...")
                except BadRequest:
                    pass

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
                await query.edit_message_text(text, reply_markup=kb)
                return

            if base_data == CB.REMINDER:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                settings = await DB.get_reminder_settings(user_id)
                text = f"⏰ **التذكيرات**\n\n"
                text += f"🔔 الاشتراك: {'✅' if settings.get('subscription_reminder', False) else '❌'}\n"
                text += f"📊 يومي: {'✅' if settings.get('daily_stats_reminder', False) else '❌'}\n"
                text += f"📈 أسبوعي: {'✅' if settings.get('weekly_report', False) else '❌'}\n"
                text += f"📅 الأيام: {settings.get('reminder_days_before', 3)}"
                kb = KeyboardFactory.build("reminder", lang=lang)
                await query.edit_message_text(text, reply_markup=kb)
                return

            if base_data == CB.REM_SET_DAYS:
                StateManager.set(user_id, UserState.WAIT_REM_DAYS)
                await query.edit_message_text("📅 أرسل عدد الأيام (1-30):")
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if data.startswith(CB.REM_LANG + ":"):
                try:
                    await query.answer("✅ تم التحديث")
                except BadRequest:
                    pass
                lang_set = data.split(":")[-1]
                await DB.update_reminder_settings(user_id, notification_lang=lang_set)
                await query.edit_message_text(f"✅ تم تعيين لغة التذكير: {lang_set}")
                return

            if base_data == CB.TRANSLATION:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                cur = await DB.get_user_language(user_id)
                kb = KeyboardFactory.build("translation", lang=lang)
                await query.edit_message_text(f"🌐 الترجمة: {cur}", reply_markup=kb)
                return

            if base_data == CB.TRANS_OFF:
                await DB.set_user_language(user_id, 'off')
                await query.edit_message_text("✅ تم إيقاف الترجمة")
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if data.startswith(CB.TRANS_SET + ":"):
                lang_set = data.split(":")[-1]
                await DB.set_user_language(user_id, lang_set)
                await query.edit_message_text(f"✅ تم تعيين: {lang_set}")
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if base_data == CB.CONTESTS:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                await CommandHandlers.contests(update, context)
                return

            if base_data == CB.CONTEST_WINNERS:
                winners = await DB.get_contest_winners(10)
                if not winners:
                    await query.edit_message_text("📭 لا يوجد فائزون")
                    try:
                        await query.answer()
                    except BadRequest:
                        pass
                    return
                text = "🏆 **الفائزون**\n\n"
                for w in winners:
                    text += f"• {w['title']} → `{w['winner_id']}`\n"
                await query.edit_message_text(text)
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if data.startswith(CB.CONTEST_JOIN + ":"):
                cid = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
                context.user_data['contest_join'] = cid
                try:
                    await query.answer()
                except BadRequest:
                    pass
                await safe_send(context.bot, user_id, "📝 أرسل إجابتك:")
                return

            if base_data == CB.SUPPORT_TICKET:
                StateManager.set(user_id, UserState.SUPPORT_MODE)
                try:
                    await query.answer()
                except BadRequest:
                    pass
                await safe_send(context.bot, user_id, "📞 أرسل رسالتك:")
                return

            if base_data == CB.CH_ADD:
                StateManager.set(user_id, UserState.WAIT_CHANNEL)
                await query.edit_message_text("📡 أرسل معرف القناة:")
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if base_data == CB.CH_LIST:
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.CH_SEL + ":"):
                ch_id = int(data.split(":")[-1])
                success = await DB.set_active_channel(user_id, ch_id)
                if success:
                    await query.edit_message_text("✅ تم تحديد القناة!")
                else:
                    await query.answer("❌ لا يمكنك تحديد هذه القناة", show_alert=True)
                    return
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if data.startswith(CB.CH_DEL + ":"):
                ch_id = int(data.split(":")[-1])
                success = await DB.delete_channel(user_id, ch_id)
                if success:
                    try:
                        await query.answer("✅ تم الحذف")
                    except BadRequest:
                        pass
                else:
                    await query.answer("❌ لا يمكنك حذف هذه القناة", show_alert=True)
                    return
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.CH_STATS + ":"):
                ch_id = int(data.split(":")[-1])
                row = await DB.fetchone("SELECT 1 FROM user_channels WHERE id=? AND user_id=?", (ch_id, user_id))
                if not row:
                    await query.answer("❌ هذه القناة ليست لك", show_alert=True)
                    return
                stats = await DB.get_channel_stats(user_id, ch_id)
                text = f"📊 **إحصائيات القناة**\n\n"
                text += f"📝 المجموع: {stats['total']}\n"
                text += f"✅ المنشورة: {stats['published']}\n"
                text += f"⏳ غير المنشورة: {stats['unpublished']}"
                await query.edit_message_text(text)
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if base_data == CB.POST_ADD:
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    try:
                        await query.answer("❌ انتهى اشتراكك!", show_alert=True)
                    except BadRequest:
                        pass
                    return
                active = await DB.get_active_channel(user_id)
                if not active:
                    await query.edit_message_text("❌ لا توجد قناة نشطة")
                    try:
                        await query.answer()
                    except BadRequest:
                        pass
                    return
                active_plan = await DB.get_active_plan(user_id)
                limit = active_plan['max_posts'] if active_plan else CONFIG.MAX_POSTS_PER_CHANNEL
                row = await DB.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (active,))
                total_posts = row[0] if row else 0
                if total_posts >= limit and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await query.answer(f"❌ وصلت للحد الأقصى ({limit} منشور) في هذه القناة.", show_alert=True)
                    return
                StateManager.set(user_id, UserState.ADDING_POSTS)
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ إنهاء الإضافة", callback_data="finish_posts")
                ]])
                await query.edit_message_text(
                    "📥 أرسل المنشورات الآن (واحد تلو الآخر).\n"
                    "عند الانتهاء اضغط الزر أدناه أو أرسل /done",
                    reply_markup=kb
                )
                return

            if base_data == "finish_posts":
                StateManager.clear(user_id)
                try:
                    await query.answer("✅ تم إنهاء الإضافة")
                except BadRequest:
                    pass
                await query.edit_message_text("✅ تم إنهاء إضافة المنشورات.")
                return

            if base_data == CB.POST_PUB:
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    try:
                        await query.answer("❌ انتهى اشتراكك!", show_alert=True)
                    except BadRequest:
                        pass
                    return
                active = await DB.get_active_channel(user_id)
                if not active:
                    await query.edit_message_text("❌ لا توجد قناة")
                    return
                post = await DB.get_next_post(active)
                if not post:
                    await query.edit_message_text("📭 لا توجد منشورات")
                    return
                ch_info = await DB.get_channel_info(user_id, active)
                if not ch_info:
                    return
                try:
                    await CallbackHandlers._publish_single(context.bot, active, ch_info['channel_id'], post)
                    await query.edit_message_text("✅ تم النشر!")
                except Exception as e:
                    logger.error(f"❌ فشل النشر: {e}")
                    await query.edit_message_text("❌ فشل النشر، تحقق من صلاحيات البوت.")
                return

            if base_data == CB.POST_LIST:
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if base_data == CB.POST_REC:
                active = await DB.get_active_channel(user_id)
                if active:
                    count = await DB.reset_posts(user_id, active)
                    await query.edit_message_text(f"♻️ {count} منشور!")
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if base_data == CB.PUB_ALL:
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    try:
                        await query.answer("❌ انتهى اشتراكك! يرجى تجديد الاشتراك", show_alert=True)
                    except BadRequest:
                        pass
                    return

                channels = await DB.get_user_channels(user_id)
                if not channels:
                    await query.edit_message_text("❌ لا توجد قنوات للنشر")
                    try:
                        await query.answer()
                    except BadRequest:
                        pass
                    return

                published_count = 0
                failed_count = 0
                await query.edit_message_text("⏳ جاري النشر...")
                try:
                    await query.answer()
                except BadRequest:
                    pass

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
                    await query.edit_message_text(f"✅ تم نشر {published_count} منشور (منشور واحد في كل قناة)")
                elif published_count > 0 and failed_count > 0:
                    await query.edit_message_text(f"⚠️ تم نشر {published_count} منشور، فشل {failed_count} منشور")
                else:
                    await query.edit_message_text("📭 لا توجد منشورات للنشر في أي قناة")
                return

            if data.startswith(CB.POST_DEL + ":"):
                post_id = int(data.split(":")[-1])
                row = await DB.fetchone("SELECT channel_db_id FROM posts WHERE id=?", (post_id,))
                if not row:
                    try:
                        await query.answer("❌ المنشور غير موجود", show_alert=True)
                    except BadRequest:
                        pass
                    return
                ch_id = row[0]
                row2 = await DB.fetchone("SELECT user_id FROM user_channels WHERE id=?", (ch_id,))
                if not row2 or row2[0] != user_id:
                    try:
                        await query.answer("❌ غير مصرح", show_alert=True)
                    except BadRequest:
                        pass
                    return
                await DB.execute("DELETE FROM posts WHERE id=?", (post_id,))
                await query.edit_message_text("✅ تم حذف المنشور!")
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.POST_CLEAR + ":"):
                ch_id = int(data.split(":")[-1])
                row = await DB.fetchone("SELECT user_id FROM user_channels WHERE id=?", (ch_id,))
                if not row or row[0] != user_id:
                    try:
                        await query.answer("❌ غير مصرح", show_alert=True)
                    except BadRequest:
                        pass
                    return
                await DB.execute("DELETE FROM posts WHERE channel_db_id=?", (ch_id,))
                await query.edit_message_text("✅ تم مسح جميع المنشورات!")
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if base_data == CB.GROUPS:
                try:
                    await query.answer()
                except BadRequest:
                    pass
                groups = await DB.get_user_groups(user_id)
                if not groups:
                    add_text = KeyboardFactory.get_text("add_group_button", lang)
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton(add_text, url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")
                    ]])
                    await query.edit_message_text("📭 لا توجد مجموعات", reply_markup=kb)
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
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data.startswith(CB.GRP_SET + ":"):
                chat_id = int(data.split(":")[-1])
                context.user_data['security_chat_id'] = chat_id
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    try:
                        await query.answer("❌ لا صلاحية", show_alert=True)
                    except BadRequest:
                        pass
                    return
                settings = await DB.get_security_settings(chat_id)
                text = KeyboardFactory._format_security_text(settings)
                kb = KeyboardFactory.build("security", chat_id, lang=lang)
                await query.edit_message_text(text, reply_markup=kb)
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if base_data == CB.ADMIN:
                if CONFIG.is_developer(user_id):
                    kb = KeyboardFactory.build("admin_panel", lang=lang)
                    await query.edit_message_text("👑 لوحة الأدمن", reply_markup=kb)
                    try:
                        await query.answer()
                    except BadRequest:
                        pass
                else:
                    try:
                        await query.answer(await get_text(lang, 'unauthorized'), show_alert=True)
                    except BadRequest:
                        pass
                return

            if data == "admin_grant_free":
                if not CONFIG.is_developer(user_id):
                    try:
                        await query.answer("❌ غير مصرح", show_alert=True)
                    except BadRequest:
                        pass
                    return
                StateManager.set(user_id, UserState.WAIT_GRANT_FREE)
                await query.edit_message_text("🎁 أرسل معرف المستخدم ثم عدد الأيام هكذا:\n`123456789 365`")
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if data.startswith(CB.PANEL_LOCK + ":"):
                chat_id = int(data.split(":")[-1])
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    try:
                        await query.answer("❌ لا صلاحية", show_alert=True)
                    except BadRequest:
                        pass
                    return
                await DB.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?,1,?,?)",
                                 (chat_id, TimeUtils.sql_iso(), user_id))
                await query.edit_message_text("🔒 تم قفل المجموعة!")
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if data.startswith(CB.PANEL_UNLOCK + ":"):
                chat_id = int(data.split(":")[-1])
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    try:
                        await query.answer("❌ لا صلاحية", show_alert=True)
                    except BadRequest:
                        pass
                    return
                await DB.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
                await query.edit_message_text("🔓 تم فتح المجموعة!")
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return

            if base_data == CB.PANEL_CLOSE:
                try:
                    await query.message.delete()
                except:
                    pass
                try:
                    await query.answer("✅ تم الإغلاق")
                except BadRequest:
                    pass
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

            if data.startswith("sched_open:"):
                ch_id = int(data.split(":")[-1])
                row = await DB.fetchone("SELECT user_id FROM user_channels WHERE id=?", (ch_id,))
                if not row or row[0] != user_id:
                    try:
                        await query.answer("❌ غير مصرح", show_alert=True)
                    except BadRequest:
                        pass
                    return
                kb = KeyboardFactory.build("channel_settings", chat_id=ch_id, lang=lang)
                await query.edit_message_text(
                    "📅 **جدولة القناة**\nيمكنك ضبط الفاصل الزمني للنشر:",
                    reply_markup=kb
                )
                try:
                    await query.answer()
                except BadRequest:
                    pass
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
                try:
                    await query.answer(f"✅ {lang_set}")
                except BadRequest:
                    pass
                context.args = []
                await CommandHandlers.start(update, context)
                return

            if data.startswith("buy_gift:"):
                try:
                    await query.answer("🔄 جارٍ التحضير...")
                except BadRequest:
                    pass

                plan_id = int(data.split(":")[-1])
                plan = await DB.get_gift_plan(plan_id)
                if not plan:
                    try:
                        await query.answer("❌ خطة غير موجودة", show_alert=True)
                    except BadRequest:
                        pass
                    return

                invoice_number = await DB.create_invoice(
                    user_id, 
                    plan_id, 
                    plan['price'], 
                    currency='XTR', 
                    provider='xtr_gift'
                )
                if not invoice_number:
                    try:
                        await query.answer("❌ فشل إنشاء الفاتورة", show_alert=True)
                    except BadRequest:
                        pass
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
                    await query.answer("✅ تم إرسال الفاتورة")
                    await query.message.delete()
                except Exception as e:
                    logger.error(f"❌ فشل إرسال الفاتورة: {e}")
                    await DB.execute("UPDATE invoices SET status='cancelled' WHERE number=?", (invoice_number,))
                    try:
                        await query.answer(f"❌ {str(e)[:50]}", show_alert=True)
                    except BadRequest:
                        pass
                return

            if base_data == "my_gifts":
                try:
                    await query.answer()
                except BadRequest:
                    pass

                try:
                    codes = await DB.fetchall(
                        "SELECT code, used_by, created_at FROM gift_codes WHERE creator_id=? ORDER BY created_at DESC LIMIT 20",
                        (user_id,)
                    )

                    if not codes:
                        await query.edit_message_text(
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
                    await query.edit_message_text(text, reply_markup=kb)

                except Exception as e:
                    logger.error(f"❌ خطأ في عرض أكواد الهدايا: {e}")
                    await query.edit_message_text(
                        "❌ **تعذر عرض أكواد الهدايا.**\n\n"
                        "🔁 حاول مرة أخرى لاحقًا."
                    )
                return

            try:
                await query.answer("⚠️ غير متوفر", show_alert=True)
            except BadRequest:
                pass

        except Exception as e:
            logger.error(f"❌ Callback error: {e}", exc_info=True)
            try:
                await query.answer("❌ خطأ", show_alert=True)
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
            await query.edit_message_text("📭 لا توجد قنوات!\nاضغط للإضافة:", reply_markup=kb)
            try:
                await query.answer()
            except BadRequest:
                pass
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
                    callback_data=f"sched_open:{ch['id']}"
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
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        try:
            await query.answer()
        except BadRequest:
            pass

    @staticmethod
    async def _show_post_list(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        active = await DB.get_active_channel(user_id)
        if not active:
            await query.edit_message_text("❌ لا توجد قناة نشطة")
            try:
                await query.answer()
            except BadRequest:
                pass
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
        await query.edit_message_text(text if posts else "📭 لا يوجد", reply_markup=InlineKeyboardMarkup(kb))
        try:
            await query.answer()
        except BadRequest:
            pass

    @staticmethod
    async def _handle_security(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        data = query.data
        parts = data.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            chat_id = int(parts[1])
        else:
            chat_id = context.user_data.get('security_chat_id')
            if not chat_id and update.effective_chat and update.effective_chat.type in ['group', 'supergroup']:
                chat_id = update.effective_chat.id

        if chat_id is None:
            return

        # ✅ تعريف valid_violations هنا ليكون متاحًا لجميع الفروع
        valid_violations = {"links","mentions","banned_words","flood","max_len","service","videos","audio","documents","stickers","forwarded","polls","games","voice","video_note"}

        action = parts[0].replace("sec_", "")

        logger.info(f"🔍 _handle_security: action={action}, chat_id={chat_id}, data={data}")

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            try:
                await query.answer(await get_text(lang, 'unauthorized'), show_alert=True)
            except BadRequest:
                pass
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
            "reject_join": "auto_reject_join"
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
                await query.edit_message_text(text, reply_markup=kb)
            except BadRequest:
                pass
            try:
                await query.answer()
            except BadRequest:
                pass
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
                await query.edit_message_text(text, reply_markup=kb)
            except BadRequest:
                pass
            try:
                await query.answer()
            except BadRequest:
                pass
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
                await query.edit_message_text(text, reply_markup=kb)
            except BadRequest:
                pass
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "toggle_banned":
            current = await DB.fetchone("SELECT delete_banned_words FROM group_security WHERE chat_id=?", (chat_id,))
            new_val = 1 - (current[0] if current else 0)
            await DB.execute("UPDATE group_security SET delete_banned_words=? WHERE chat_id=?", (new_val, chat_id))
            status = "مفعل ✅" if new_val else "معطل ❌"
            await query.edit_message_text(f"🔄 حذف الكلمات المحظورة: {status}")
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "banned" or action == "banned_words":
            await CallbackHandlers._handle_banned_words_direct(update, context, query, user_id, chat_id, lang)
            return

        if action == "maxlen":
            StateManager.set(user_id, UserState.WAIT_MAX_LEN)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("📏 أرسل الحد الأقصى للطول:")
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "warn":
            settings = await DB.get_security_settings(chat_id)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 العدد", callback_data=f"sec_warn_count:{chat_id}"),
                 InlineKeyboardButton("⚖️ العقوبة", callback_data=f"sec_warn_penalty:{chat_id}")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"{CB.GRP_SET}:{chat_id}")]
            ])
            await query.edit_message_text(
                f"⚠️ **التحذيرات**\n\nالحد: {settings.get('max_warnings', 3)}\nالعقوبة: {settings.get('warn_penalty', 'ban')}",
                reply_markup=kb
            )
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "warn_count":
            StateManager.set(user_id, UserState.WAIT_WARN_COUNT)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("📝 أرسل العدد (1-10):")
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "warn_penalty":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 حظر", callback_data=f"sec_set_warn_penalty:{chat_id}:ban"),
                 InlineKeyboardButton("🔇 كتم", callback_data=f"sec_set_warn_penalty:{chat_id}:mute")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_warn:{chat_id}")]
            ])
            await query.edit_message_text("⚖️ اختر العقوبة:", reply_markup=kb)
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "set_warn_penalty":
            if len(parts) >= 3:
                penalty = parts[2]
                if penalty not in DB.VALID_PENALTY_TYPES:
                    try:
                        await query.answer("❌ نوع عقوبة غير صالح", show_alert=True)
                    except BadRequest:
                        pass
                    return
                await DB.execute("UPDATE group_security SET warn_penalty=? WHERE chat_id=?", (penalty, chat_id))
                await query.edit_message_text(f"✅ تم التعيين: {penalty}")
                try:
                    await query.answer()
                except BadRequest:
                    pass
            return

        if action == "del_pen":
            kb = KeyboardFactory.build("penalty", chat_id, lang=lang)
            await query.edit_message_text("⚖️ عقوبة الحذف:", reply_markup=kb)
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "penalty":
            kb = KeyboardFactory.build("penalty", chat_id, lang=lang)
            await query.edit_message_text("⚖️ العقوبة:", reply_markup=kb)
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "adv_act":
            kb = KeyboardFactory.build("advanced_actions", chat_id, lang=lang)
            await query.edit_message_text("🛠️ إجراءات:", reply_markup=kb)
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "act_log":
            logs = await DB.get_admin_logs(chat_id, 20)
            if not logs:
                await query.edit_message_text("📭 لا توجد سجلات")
                try:
                    await query.answer()
                except BadRequest:
                    pass
                return
            text = "📜 **السجل**\n\n"
            for log in logs:
                text += f"• {log['action']} → {log['target_id'] or '-'}\n"
            await query.edit_message_text(text)
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "auto_reply_menu":
            kb = KeyboardFactory.build("auto_reply_manage", chat_id, lang=lang)
            await query.edit_message_text("📝 الردود:", reply_markup=kb)
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "close":
            try:
                await query.message.delete()
            except BadRequest:
                pass
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        # ✅ معالجة إعدادات الفيضان
        if action == "antiflood_settings":
            await CallbackHandlers._handle_antiflood_settings(update, context, query, chat_id, user_id, lang)
            return

        # ✅ معالجة إعدادات الوضع الليلي
        if action == "night_settings":
            await CallbackHandlers._handle_night_settings(update, context, query, chat_id, user_id, lang)
            return

        # ✅ معالجة نصوص الترحيب والوداع
        if action == "welcome_text":
            StateManager.set(user_id, UserState.WAIT_WELCOME_TEXT)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("👋 أرسل نص الترحيب:")
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "goodbye_text":
            StateManager.set(user_id, UserState.WAIT_GOODBYE_TEXT)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("👋 أرسل نص الوداع:")
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        # ✅ معالجة مدة الوضع البطيء
        if action == "slow_mode_seconds":
            StateManager.set(user_id, UserState.WAIT_SLOW_MODE_SECONDS)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("⏱️ أرسل مدة الوضع البطيء بالثواني (0-3600):")
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        # ✅ معالجة مدد العقوبات
        if action == "penalty_durations":
            await CallbackHandlers._handle_penalty_durations(update, context, query, chat_id, user_id, lang)
            return

        # ✅ معالجة إعدادات الفيضان الفرعية
        if action == "antiflood_messages":
            StateManager.set(user_id, UserState.WAIT_ANTIFLOOD_MESSAGES)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("📝 أرسل عدد الرسائل المسموح بها قبل تفعيل الحماية (1-100):")
            try: await query.answer()
            except BadRequest: pass
            return

        if action == "antiflood_seconds":
            StateManager.set(user_id, UserState.WAIT_ANTIFLOOD_SECONDS)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("⏱️ أرسل الفترة الزمنية بالثواني (1-3600):")
            try: await query.answer()
            except BadRequest: pass
            return

        if action == "antiflood_penalty":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔇 كتم", callback_data=f"sec_antiflood_pen_set:{chat_id}:mute"),
                 InlineKeyboardButton("🚫 حظر", callback_data=f"sec_antiflood_pen_set:{chat_id}:ban"),
                 InlineKeyboardButton("🔒 تقييد", callback_data=f"sec_antiflood_pen_set:{chat_id}:restrict")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_antiflood_settings:{chat_id}")]
            ])
            await query.edit_message_text("اختر عقوبة الفيضان:", reply_markup=kb)
            try: await query.answer()
            except BadRequest: pass
            return

        if action == "antiflood_pen_set":
            if len(parts) >= 3:
                penalty = parts[2]
                if penalty not in DB.VALID_PENALTY_TYPES:
                    try: await query.answer("❌ نوع غير صالح", show_alert=True)
                    except BadRequest: pass
                    return
                await DB.execute("UPDATE group_security SET antiflood_penalty=? WHERE chat_id=?", (penalty, chat_id))
                await query.edit_message_text(f"✅ تم تعيين عقوبة الفيضان: {penalty}")
                await CallbackHandlers._handle_antiflood_settings(update, context, query, chat_id, user_id, lang)
            return

        # ✅ إعدادات الوضع الليلي الفرعية
        if action == "night_start":
            StateManager.set(user_id, UserState.WAIT_NIGHT_START)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("🌙 أرسل وقت بدء الوضع الليلي (HH:MM):")
            try: await query.answer()
            except BadRequest: pass
            return

        if action == "night_end":
            StateManager.set(user_id, UserState.WAIT_NIGHT_END)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("🌙 أرسل وقت نهاية الوضع الليلي (HH:MM):")
            try: await query.answer()
            except BadRequest: pass
            return

        if action == "night_action":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔇 كتم", callback_data=f"sec_night_action_set:{chat_id}:mute"),
                 InlineKeyboardButton("🚫 حظر", callback_data=f"sec_night_action_set:{chat_id}:ban"),
                 InlineKeyboardButton("🔒 تقييد", callback_data=f"sec_night_action_set:{chat_id}:restrict")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_night_settings:{chat_id}")]
            ])
            await query.edit_message_text("اختر إجراء الوضع الليلي:", reply_markup=kb)
            try: await query.answer()
            except BadRequest: pass
            return

        if action == "night_action_set":
            if len(parts) >= 3:
                penalty = parts[2]
                if penalty not in DB.VALID_PENALTY_TYPES:
                    try: await query.answer("❌ نوع غير صالح", show_alert=True)
                    except BadRequest: pass
                    return
                await DB.execute("UPDATE group_security SET night_mode_action=? WHERE chat_id=?", (penalty, chat_id))
                await query.edit_message_text(f"✅ تم تعيين إجراء الليل: {penalty}")
                await CallbackHandlers._handle_night_settings(update, context, query, chat_id, user_id, lang)
            return

        # ✅ مدد العقوبات الفرعية - عرض قائمة مدد جاهزة
        if action in ("penalty_mute", "penalty_ban", "penalty_restrict"):
            ptype = action.replace("penalty_", "")
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("دقيقة", callback_data=f"sec_pen_set:{chat_id}:{ptype}:60"),
                 InlineKeyboardButton("10 دقائق", callback_data=f"sec_pen_set:{chat_id}:{ptype}:600")],
                [InlineKeyboardButton("ساعة", callback_data=f"sec_pen_set:{chat_id}:{ptype}:3600"),
                 InlineKeyboardButton("يوم", callback_data=f"sec_pen_set:{chat_id}:{ptype}:86400")],
                [InlineKeyboardButton("أسبوع", callback_data=f"sec_pen_set:{chat_id}:{ptype}:604800"),
                 InlineKeyboardButton("10 أيام", callback_data=f"sec_pen_set:{chat_id}:{ptype}:864000")],
                [InlineKeyboardButton("15 يوم", callback_data=f"sec_pen_set:{chat_id}:{ptype}:1296000"),
                 InlineKeyboardButton("شهر", callback_data=f"sec_pen_set:{chat_id}:{ptype}:2592000")],
                [InlineKeyboardButton("سنة", callback_data=f"sec_pen_set:{chat_id}:{ptype}:31536000"),
                 InlineKeyboardButton("دائم", callback_data=f"sec_pen_set:{chat_id}:{ptype}:0")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_penalty_durations:{chat_id}")]
            ])
            await query.edit_message_text(f"⏱️ اختر مدة {ptype} الافتراضية:", reply_markup=kb)
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        # ✅ تطبيق المدة المختارة على العقوبة الافتراضية
        if action == "pen_set":
            if len(parts) >= 4:
                ptype = parts[2]
                try:
                    duration_seconds = int(parts[3])
                except:
                    return
                if ptype not in DB.VALID_PENALTY_TYPES:
                    try:
                        await query.answer("❌ نوع غير صالح", show_alert=True)
                    except BadRequest:
                        pass
                    return
                col_map = {
                    'mute': 'mute_default_duration',
                    'ban': 'ban_default_duration',
                    'restrict': 'restrict_default_duration'
                }
                col = col_map.get(ptype)
                if col:
                    await DB.execute(f"UPDATE group_security SET {col}=? WHERE chat_id=?", (duration_seconds, chat_id))
                    await query.edit_message_text(f"✅ تم تعيين مدة {ptype} الافتراضية إلى {duration_seconds} ثانية")
                    await CallbackHandlers._handle_penalty_durations(update, context, query, chat_id, user_id, lang)
            return

        # ✅ إدارة عقوبات المخالفات
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
            await query.edit_message_text("⚖️ **عقوبات المخالفات**\nاختر نوع المخالفة لضبط عقوبتها", reply_markup=InlineKeyboardMarkup(kb))
            return

        if action == "violation":
            if len(parts) >= 3:
                v_type = parts[2]
                if v_type not in valid_violations:
                    try:
                        await query.answer("❌ نوع مخالفة غير صالح", show_alert=True)
                    except BadRequest:
                        pass
                    return
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔨 حظر", callback_data=f"sec_violation_pen:{chat_id}:{v_type}:ban"),
                     InlineKeyboardButton("🔇 كتم", callback_data=f"sec_violation_pen:{chat_id}:{v_type}:mute")],
                    [InlineKeyboardButton("🔒 تقييد", callback_data=f"sec_violation_pen:{chat_id}:{v_type}:restrict")],
                    [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_violation_penalties:{chat_id}")]
                ])
                await query.edit_message_text("اختر نوع العقوبة:", reply_markup=kb)
            return

        # ✅ عرض قائمة مدد جاهزة لعقوبات المخالفات
        if action == "violation_pen":
            if len(parts) >= 4:
                v_type = parts[2]
                p_type = parts[3]
                if v_type not in valid_violations or p_type not in DB.VALID_PENALTY_TYPES:
                    try:
                        await query.answer("❌ بيانات غير صالحة", show_alert=True)
                    except BadRequest:
                        pass
                    return

                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("دقيقة", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:60"),
                     InlineKeyboardButton("10 دقائق", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:600")],
                    [InlineKeyboardButton("نص ساعة", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:1800"),
                     InlineKeyboardButton("ساعة", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:3600")],
                    [InlineKeyboardButton("يوم", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:86400"),
                     InlineKeyboardButton("أسبوع", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:604800")],
                    [InlineKeyboardButton("10 أيام", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:864000"),
                     InlineKeyboardButton("15 يوم", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:1296000")],
                    [InlineKeyboardButton("شهر", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:2592000"),
                     InlineKeyboardButton("سنة", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:31536000")],
                    [InlineKeyboardButton("دائم", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:0")],
                    [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_violation_penalties:{chat_id}")]
                ])
                await query.edit_message_text(f"⏱️ اختر مدة عقوبة {p_type} لمخالفة {v_type}:", reply_markup=kb)
            return

        # ✅ تطبيق المدة المختارة على عقوبة المخالفة
        if action == "violation_dur":
            if len(parts) >= 5:
                v_type = parts[2]
                p_type = parts[3]
                try:
                    duration_seconds = int(parts[4])
                except:
                    return
                if v_type not in valid_violations or p_type not in DB.VALID_PENALTY_TYPES:
                    try:
                        await query.answer("❌ بيانات غير صالحة", show_alert=True)
                    except BadRequest:
                        pass
                    return
                await DB.set_violation_penalty(chat_id, v_type, p_type, duration_seconds)
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_violation_penalties:{chat_id}")
                ]])
                await query.edit_message_text(f"✅ تم حفظ عقوبة {v_type}: {p_type} ({duration_seconds} ثانية)", reply_markup=kb)
            return

        try:
            await query.answer()
        except BadRequest:
            pass

    # ✅ دوال جديدة لمعالجة إعدادات الأمان
    @staticmethod
    async def _handle_antiflood_settings(update, context, query, chat_id, user_id, lang):
        settings = await DB.get_security_settings(chat_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"عدد الرسائل: {settings.get('antiflood_messages', 5)}",
                callback_data=f"sec_antiflood_messages:{chat_id}"
            )],
            [InlineKeyboardButton(
                f"الفترة بالثواني: {settings.get('antiflood_seconds', 10)}",
                callback_data=f"sec_antiflood_seconds:{chat_id}"
            )],
            [InlineKeyboardButton(
                f"العقوبة: {settings.get('antiflood_penalty', 'mute')}",
                callback_data=f"sec_antiflood_penalty:{chat_id}"
            )],
            [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")]
        ])
        await query.edit_message_text(
            f"🌊 **إعدادات الفيضان**\n\n"
            f"الحد: {settings.get('antiflood_messages', 5)} رسالة\n"
            f"الفترة: {settings.get('antiflood_seconds', 10)} ثانية\n"
            f"العقوبة: {settings.get('antiflood_penalty', 'mute')}",
            reply_markup=kb
        )
        try:
            await query.answer()
        except BadRequest:
            pass

    @staticmethod
    async def _handle_night_settings(update, context, query, chat_id, user_id, lang):
        settings = await DB.get_security_settings(chat_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"وقت البداية: {settings.get('night_mode_start', '23:00')}",
                callback_data=f"sec_night_start:{chat_id}"
            )],
            [InlineKeyboardButton(
                f"وقت النهاية: {settings.get('night_mode_end', '06:00')}",
                callback_data=f"sec_night_end:{chat_id}"
            )],
            [InlineKeyboardButton(
                f"الإجراء: {settings.get('night_mode_action', 'mute')}",
                callback_data=f"sec_night_action:{chat_id}"
            )],
            [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")]
        ])
        await query.edit_message_text(
            f"🌙 **إعدادات الوضع الليلي**\n\n"
            f"البداية: {settings.get('night_mode_start', '23:00')}\n"
            f"النهاية: {settings.get('night_mode_end', '06:00')}\n"
            f"الإجراء: {settings.get('night_mode_action', 'mute')}",
            reply_markup=kb
        )
        try:
            await query.answer()
        except BadRequest:
            pass

    @staticmethod
    async def _handle_penalty_durations(update, context, query, chat_id, user_id, lang):
        settings = await DB.get_security_settings(chat_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"كتم: {settings.get('mute_default_duration', 3600)//60} دقيقة",
                callback_data=f"sec_penalty_mute:{chat_id}"
            )],
            [InlineKeyboardButton(
                f"حظر: {settings.get('ban_default_duration', 0)//60} دقيقة",
                callback_data=f"sec_penalty_ban:{chat_id}"
            )],
            [InlineKeyboardButton(
                f"تقييد: {settings.get('restrict_default_duration', 1800)//60} دقيقة",
                callback_data=f"sec_penalty_restrict:{chat_id}"
            )],
            [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")]
        ])
        await query.edit_message_text(
            f"⏳ **مدد العقوبات الافتراضية**\n\n"
            f"كتم: {settings.get('mute_default_duration', 3600)//60} دقيقة\n"
            f"حظر: {settings.get('ban_default_duration', 0)//60} دقيقة (0 = دائم)\n"
            f"تقييد: {settings.get('restrict_default_duration', 1800)//60} دقيقة",
            reply_markup=kb
        )
        try:
            await query.answer()
        except BadRequest:
            pass

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
                try:
                    await query.answer(await get_text(lang, 'unauthorized'), show_alert=True)
                except BadRequest:
                    pass
                return
        else:
            if not CONFIG.is_developer(user_id):
                try:
                    await query.answer("❌ غير مصرح", show_alert=True)
                except BadRequest:
                    pass
                return

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(KeyboardFactory.get_text("ban_add", lang), callback_data=f"ban_add:{chat_id}"),
             InlineKeyboardButton(KeyboardFactory.get_text("ban_list", lang), callback_data=f"ban_list:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("ban_rem", lang), callback_data=f"ban_rem:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}" if chat_id != -1 else CB.ADMIN)]
        ])
        await query.edit_message_text("🚫 **إدارة الكلمات المحظورة**", reply_markup=kb)
        try:
            await query.answer()
        except BadRequest:
            pass

    @staticmethod
    async def _handle_admin(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        data = query.data

        if data == CB.ADMIN_USERS:
            stats = await DB.get_user_stats()
            await query.edit_message_text(f"👥 {stats['users']} مستخدم\n⛔ {stats['banned']} محظور")

        elif data == CB.ADMIN_BANNED:
            users = await DB.get_all_users()
            banned = [str(u[0]) for u in users if u[1] == 1]
            await query.edit_message_text("⛔ **المحظورين**\n\n" + "\n".join(banned[:20]) if banned else "لا يوجد")

        elif data == CB.ADMIN_UNBAN_ALL:
            await DB.execute("UPDATE users SET banned=0 WHERE banned=1")
            await query.edit_message_text("✅ تم إلغاء حظر الجميع")

        elif data == CB.ADMIN_CHANNELS:
            channels = await DB.fetchall("SELECT channel_id, channel_name, banned FROM user_channels LIMIT 50")
            text = "📡 **القنوات**\n\n" + "\n".join(f"{'✅' if not c[2] else '🚫'} {c[1]}" for c in channels)
            await query.edit_message_text(text if channels else "📭 لا توجد")

        elif data == CB.ADMIN_BANNED_CH:
            channels = await DB.fetchall("SELECT channel_id, channel_name FROM user_channels WHERE banned=1")
            text = "🚫 **القنوات المحظورة**\n\n" + "\n".join(f"• {c[1]}" for c in channels)
            await query.edit_message_text(text if channels else "📭 لا يوجد")

        elif data == CB.ADMIN_ACTIVATE_CH:
            await DB.execute("UPDATE user_channels SET banned=0 WHERE banned=1")
            await query.edit_message_text("✅ تم تفعيل الكل")

        elif data == CB.ADMIN_GROUPS:
            groups = await DB.fetchall("SELECT chat_id, chat_name, banned FROM bot_groups LIMIT 50")
            text = "👥 **المجموعات**\n\n" + "\n".join(f"{'✅' if not g[2] else '🚫'} {g[1]}" for g in groups)
            await query.edit_message_text(text if groups else "📭 لا توجد")

        elif data == CB.ADMIN_BANNED_GR:
            groups = await DB.fetchall("SELECT chat_id, chat_name FROM bot_groups WHERE banned=1")
            text = "🚫 **المجموعات المحظورة**\n\n" + "\n".join(f"• {g[1]}" for g in groups)
            await query.edit_message_text(text if groups else "📭 لا يوجد")

        elif data == CB.ADMIN_UNBAN_GR:
            await DB.execute("UPDATE bot_groups SET banned=0 WHERE banned=1")
            await query.edit_message_text("✅ تم إلغاء حظر المجموعات")

        elif data == CB.ADMIN_ADD_ADMIN:
            StateManager.set(user_id, UserState.WAIT_ADMIN_ADD)
            await query.edit_message_text("👑 أرسل معرف المشرف:")

        elif data == CB.ADMIN_REM_ADMIN:
            StateManager.set(user_id, UserState.WAIT_ADMIN_REM)
            await query.edit_message_text("🗑️ أرسل معرف المشرف:")

        elif data == "admin_grant_free":
            if not CONFIG.is_developer(user_id):
                try:
                    await query.answer("❌ غير مصرح", show_alert=True)
                except BadRequest:
                    pass
                return
            StateManager.set(user_id, UserState.WAIT_GRANT_FREE)
            await query.edit_message_text("🎁 أرسل معرف المستخدم ثم عدد الأيام هكذا:\n`123456789 365`")

        elif data == CB.ADMIN_RAM:
            ram = get_ram_usage()
            await query.edit_message_text(f"🖥️ الرام: {ram['percent']}%")

        elif data == CB.ADMIN_STATS:
            stats = await DB.get_bot_stats()
            text = f"👥 {stats.get('users',0)} مستخدم\n📡 {stats.get('channels',0)} قناة\n👥 {stats.get('groups',0)} مجموعة\n💎 {stats.get('active_subs',0)} اشتراك نشط"
            await query.edit_message_text(text)

        elif data == CB.ADMIN_METRICS:
            m = METRICS.get_stats()
            await query.edit_message_text(f"📊 API: {m.get('api_calls_last_hour', 0)}\n⚠️ أخطاء: {m.get('errors_last_hour', 0)}")

        elif data == CB.ADMIN_BACKUP:
            try:
                PATHS.BACKUPS.mkdir(parents=True, exist_ok=True)
                backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2(PATHS.DB, backup_file)
                with open(backup_file, 'rb') as f:
                    await context.bot.send_document(chat_id=user_id, document=f, filename=backup_file.name)
                try:
                    await query.answer()
                except BadRequest:
                    pass
            except Exception as e:
                logger.error(f"❌ فشل النسخ الاحتياطي: {e}")
                await safe_send(context.bot, user_id, "❌ فشل النسخ الاحتياطي")

        elif data == CB.ADMIN_RESTORE:
            backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
            if not backups:
                await query.edit_message_text("📭 لا توجد نسخ")
            else:
                kb = [[InlineKeyboardButton(b.name, callback_data=f"{CB.ADMIN_RESTORE_SEL}:{b.name}")] for b in backups[:10]]
                await query.edit_message_text("🔄 اختر النسخة:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith(CB.ADMIN_RESTORE_SEL + ":"):
            filename = data.split(":")[-1]
            filepath = PATHS.BACKUPS / filename
            if filepath.exists():
                try:
                    shutil.copy2(filepath, PATHS.DB)
                    await query.edit_message_text("✅ تمت الاستعادة (قد تحتاج إعادة تشغيل)")
                except Exception as e:
                    logger.error(f"❌ فشل الاستعادة: {e}")
                    await query.edit_message_text("❌ فشل الاستعادة")

        elif data == CB.ADMIN_SEND_UPDATE:
            StateManager.set(user_id, UserState.WAIT_UPDATE)
            await query.edit_message_text("📢 أرسل نص التحديث:")

        elif data == CB.ADMIN_SET_UPDATE_CH:
            StateManager.set(user_id, UserState.WAIT_UPDATE_CH)
            await query.edit_message_text("📢 أرسل معرف قناة التحديثات:")

        elif data == CB.ADMIN_SHOW_UPDATE:
            ch = await DB.get_updates_channel()
            await query.edit_message_text(f"📢 قناة التحديثات: @{ch}" if ch else "📢 لا توجد قناة")

        elif data == CB.ADMIN_FORCE_SUB:
            ch = await DB.get_force_subscribe_channel()
            await query.edit_message_text(f"🔒 قناة الاشتراك الإجباري: @{ch}" if ch else "🔒 غير محددة")

        elif data == CB.ADMIN_SET_FORCE:
            StateManager.set(user_id, UserState.WAIT_FORCE)
            await query.edit_message_text("🔒 أرسل معرف القناة:")

        elif data == CB.ADMIN_BROADCAST:
            StateManager.set(user_id, UserState.WAIT_BROADCAST)
            await query.edit_message_text("📨 أرسل الرسالة:")

        elif data == CB.ADMIN_TICKETS:
            tickets = await DB.get_tickets()
            if not tickets:
                await query.edit_message_text("📭 لا توجد تذاكر")
            else:
                text = "📋 **التذاكر**\n\n" + "\n".join(f"#{t['ticket_number']} - `{t['user_id']}`" for t in tickets)
                await query.edit_message_text(text)

        elif data == CB.ADMIN_DEL_TICKETS:
            await DB.delete_all_tickets()
            await query.edit_message_text("✅ تم الحذف")

        elif data == CB.ADMIN_LOG_CH:
            log_id = await DB.get_log_channel()
            await query.edit_message_text(f"📋 قناة السجلات: {log_id}" if log_id else "📋 غير محدد")

        elif data == CB.ADMIN_SET_LOG_CH:
            StateManager.set(user_id, UserState.WAIT_LOG_CH)
            await query.edit_message_text("📋 أرسل معرف القناة:")

        elif data == CB.ADMIN_REPLIES:
            stats = await DB.get_auto_reply_stats(-1, 20)
            text = "📊 **الردود**\n\n"
            for kw, cnt, source in stats:
                src = "عام" if source == "global" else "مجموعة"
                text += f"• {kw} ({cnt}) [{src}]\n"
            await query.edit_message_text(text if stats else "📭 لا يوجد")

        elif data == CB.ADMIN_ADD_REPLY:
            StateManager.set(user_id, UserState.WAIT_KEYWORD)
            await query.edit_message_text("📝 أرسل الكلمة:")

        elif data == CB.ADMIN_LIST_REPLIES:
            replies = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=-1 LIMIT 20")
            text = "📋 **الردود**\n\n" + "\n".join(f"• {r[0]} ({r[1]})" for r in replies)
            await query.edit_message_text(text if replies else "📭 لا يوجد")

        elif data == CB.ADMIN_DEL_REPLY:
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = -1
            await query.edit_message_text("🗑️ أرسل الكلمة:")

        elif data == CB.ADMIN_BANNED_WORDS:
            await CallbackHandlers._handle_banned_words_direct(update, context, query, user_id, -1, lang)

        elif data == CB.ADMIN_ADD_BANNED:
            StateManager.set(user_id, UserState.WAIT_GLOBAL_BAN)
            await query.edit_message_text("🚫 أرسل الكلمة:")

        elif data == CB.ADMIN_LIST_BANNED:
            words = await DB.get_banned_words(-1)
            text = "🚫 **الكلمات**\n\n" + "\n".join(words) if words else "📭 لا يوجد"
            await query.edit_message_text(text)

        elif data == CB.ADMIN_REM_BANNED:
            StateManager.set(user_id, UserState.WAIT_REM_GLOBAL_BAN)
            await query.edit_message_text("🗑️ أرسل الكلمة:")

        elif data == CB.ADMIN_CREATE_CONTEST:
            StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
            await query.edit_message_text("🏆 أرسل عنوان المسابقة:")

        elif data == CB.ADMIN_DECLARE_WINNER:
            contests = await DB.fetchall("SELECT id, title FROM contests WHERE status='active'")
            if not contests:
                await query.edit_message_text("📭 لا توجد مسابقات نشطة")
            else:
                kb = [[InlineKeyboardButton(title, callback_data=f"{CB.DECLARE_WINNER_SEL}:{cid}")] for cid, title in contests]
                await query.edit_message_text("اختر المسابقة:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith(CB.ADMIN_DEL_CONTEST + ":"):
            cid = int(data.split(":")[-1])
            await DB.delete_contest(cid, user_id)
            await query.edit_message_text("✅ تم حذف المسابقة")

        elif data == CB.ADMIN_EXPORT_REPLIES:
            count = await export_auto_replies(-1)
            await query.edit_message_text(f"✅ تم تصدير {count} رد")

        elif data == CB.ADMIN_REFRESH_CACHE:
            _auto_reply_cache.invalidate()
            await query.edit_message_text("🔄 تم تحديث الكاش")

        elif data in (CB.ADMIN_IMPORT_REPLIES, CB.ADMIN_IMPORT_GITHUB):
            await CallbackHandlers._handle_import(update, context, query, user_id)

        # ✅ أزرار الفواتير وسجلات الدفع
        elif data == CB.ADMIN_INVOICES:
            invoices = await DB.fetchall(
                "SELECT number, user_id, plan_id, amount, status, created_at FROM invoices ORDER BY id DESC LIMIT 20"
            )
            if not invoices:
                await query.edit_message_text("📭 لا توجد فواتير")
            else:
                text = "🧾 **آخر الفواتير**\n\n"
                for inv in invoices:
                    text += (
                        f"• `{inv['number']}`\n"
                        f"  👤 المستخدم: `{inv['user_id']}`\n"
                        f"  💰 المبلغ: {inv['amount']} ⭐\n"
                        f"  📌 الحالة: {inv['status']}\n"
                        f"  🕒 {inv['created_at']}\n\n"
                    )
                await query.edit_message_text(text)

        elif data == CB.ADMIN_PAYMENT_LOGS:
            logs = await DB.fetchall(
                "SELECT user_id, event_type, data, created_at FROM payment_logs ORDER BY id DESC LIMIT 20"
            )
            if not logs:
                await query.edit_message_text("📭 لا توجد سجلات دفع")
            else:
                text = "📊 **سجلات الدفع**\n\n"
                for log in logs:
                    text += (
                        f"• 👤 `{log['user_id']}`\n"
                        f"  🎯 الحدث: {log['event_type']}\n"
                        f"  🕒 {log['created_at']}\n\n"
                    )
                await query.edit_message_text(text)

        else:
            try:
                await query.answer("⚠️ غير متوفر", show_alert=True)
            except BadRequest:
                pass

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
            try:
                await query.answer(await get_text(lang, 'unauthorized'), show_alert=True)
            except BadRequest:
                pass
            return

        settings = await DB.get_auto_reply_settings(chat_id)
        current_enabled = settings.get('enabled', False)

        if action == "toggle":
            try:
                await query.answer("🔄 جارٍ التحديث...")
            except BadRequest:
                pass
            new_enabled = not current_enabled
            await DB.update_auto_reply_settings(chat_id, enabled=new_enabled)
            _auto_reply_cache.invalidate()
            status_text = "✅ **تم تفعيل الردود التلقائية!**" if new_enabled else "❌ **تم تعطيل الردود التلقائية!**"
            await query.edit_message_text(
                status_text,
                reply_markup=KeyboardFactory.build("auto_reply_manage", chat_id, lang=lang)
            )
            return

        if action == "menu":
            try:
                await query.answer()
            except BadRequest:
                pass
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return

        if action == "admins":
            await DB.update_auto_reply_settings(chat_id, only_admins=not settings.get('only_admins', False))
            try:
                await query.answer("✅ تم")
            except BadRequest:
                pass
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return

        if action == "reset":
            await DB.reset_auto_replies(chat_id)
            _auto_reply_cache.invalidate()
            try:
                await query.answer("✅ تم حذف جميع الردود")
            except BadRequest:
                pass
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return

        if action == "add":
            StateManager.set(user_id, UserState.WAIT_AUTO_KEY)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text("📝 أرسل الكلمة المفتاحية:")
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "del":
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text("🗑️ أرسل الكلمة لحذفها:")
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "stats":
            rows = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? LIMIT 10", (chat_id,))
            text = "📊 **الإحصائيات**\n\n" + "\n".join(f"• {r[0]}: {r[1]}" for r in rows) if rows else "📭 لا يوجد"
            await query.edit_message_text(text)
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "list":
            rows = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=? LIMIT 20", (chat_id,))
            text = "📋 **الردود**\n\n" + "\n".join(f"• {r[0]}" for r in rows) if rows else "📭 لا يوجد"
            await query.edit_message_text(text)
            try:
                await query.answer()
            except BadRequest:
                pass
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
        await query.edit_message_text("📝 **إدارة الردود التلقائية**", reply_markup=kb)

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
            try:
                await query.answer("❌ غير مصرح", show_alert=True)
            except BadRequest:
                pass
            return

        # ✅ مسح الحالة السابقة قبل تعيين حالة جديدة
        StateManager.clear(user_id)

        if action == "min":
            StateManager.set(user_id, UserState.WAIT_MIN)
            context.user_data['schedule_ch'] = ch_id
            min_val = await get_min_publish_interval()
            await query.edit_message_text(
                f"📅 أرسل عدد الدقائق (الحد الأدنى {min_val} دقيقة، كحد أقصى 1440):"
            )
            try:
                await query.answer()
            except BadRequest:
                pass
        elif action == "hour":
            StateManager.set(user_id, UserState.WAIT_HOUR)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text("📅 أرسل عدد الساعات (1-168):")
            try:
                await query.answer()
            except BadRequest:
                pass
        elif action == "day":
            StateManager.set(user_id, UserState.WAIT_DAY)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text("📅 أرسل عدد الأيام (1-365):")
            try:
                await query.answer()
            except BadRequest:
                pass
        elif action == "time":
            StateManager.set(user_id, UserState.WAIT_PUB_TIME)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text("🕐 أرسل وقت النشر (HH:MM):")
            try:
                await query.answer()
            except BadRequest:
                pass

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
                try:
                    await query.answer("❌ غير مصرح", show_alert=True)
                except BadRequest:
                    pass
                return
        else:
            try:
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    lang = await DB.get_user_language(user_id)
                    try:
                        await query.answer(await get_text(lang, 'unauthorized'), show_alert=True)
                    except BadRequest:
                        pass
                    return
            except Exception as e:
                logger.warning(f"⚠️ فشل التحقق من الصلاحية: {e}")
                try:
                    await query.answer("❌ تعذر التحقق من الصلاحية", show_alert=True)
                except BadRequest:
                    pass
                return

        if action == "add":
            StateManager.set(user_id, UserState.WAIT_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            text = "📝 أرسل الكلمة المحظورة:"
            try:
                await query.edit_message_text(text)
            except BadRequest as e:
                logger.warning(f"⚠️ edit_message_text فشل: {e}")
                await safe_send(context.bot, user_id, text)
            try:
                await query.answer()
            except BadRequest:
                pass
        elif action == "list":
            words = await DB.get_banned_words(chat_id)
            if not words:
                text = "📭 لا توجد كلمات محظورة"
            else:
                text = "🚫 **الكلمات المحظورة**\n\n" + "\n".join(f"• {w}" for w in words)
            try:
                await query.edit_message_text(text)
            except BadRequest as e:
                logger.warning(f"⚠️ edit_message_text فشل: {e}")
                await safe_send(context.bot, user_id, text)
            try:
                await query.answer()
            except BadRequest:
                pass
        elif action == "rem":
            StateManager.set(user_id, UserState.WAIT_REM_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            text = "🗑️ أرسل الكلمة لحذفها:"
            try:
                await query.edit_message_text(text)
            except BadRequest as e:
                logger.warning(f"⚠️ edit_message_text فشل: {e}")
                await safe_send(context.bot, user_id, text)
            try:
                await query.answer()
            except BadRequest:
                pass

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
            try:
                await query.answer(await get_text(lang, 'unauthorized'), show_alert=True)
            except BadRequest:
                pass
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
            await query.edit_message_text(text)
            try:
                await query.answer()
            except BadRequest:
                pass

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
            try:
                await query.answer(await get_text(lang, 'unauthorized'), show_alert=True)
            except BadRequest:
                pass
            return

        # ✅ التحقق من نوع العقوبة
        if penalty not in DB.VALID_PENALTY_TYPES:
            try:
                await query.answer("❌ نوع عقوبة غير صالح", show_alert=True)
            except BadRequest:
                pass
            return

        await DB.execute("UPDATE group_security SET auto_penalty=? WHERE chat_id=?", (penalty, chat_id))
        await query.edit_message_text(f"✅ تم تعيين العقوبة: {penalty}")
        try:
            await query.answer()
        except BadRequest:
            pass

    @staticmethod
    async def _handle_contests(update, context, query, user_id):
        data = query.data
        if data == CB.ADMIN_CREATE_CONTEST:
            StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
            await query.edit_message_text("🏆 أرسل عنوان المسابقة:")
            try:
                await query.answer()
            except BadRequest:
                pass
        elif data.startswith(CB.CONTEST_JOIN + ":"):
            cid = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
            context.user_data['contest_join'] = cid
            await query.edit_message_text("📝 أرسل إجابتك:")
            try:
                await query.answer()
            except BadRequest:
                pass
        elif data == CB.CONTEST_WINNERS:
            winners = await DB.get_contest_winners(10)
            if not winners:
                await query.edit_message_text("📭 لا يوجد فائزون")
            else:
                text = "🏆 **الفائزون**\n\n" + "\n".join(f"• {w['title']} → `{w['winner_id']}`" for w in winners)
                await query.edit_message_text(text)
            try:
                await query.answer()
            except BadRequest:
                pass
        elif data.startswith(CB.DECLARE_WINNER_SEL + ":"):
            if not CONFIG.is_developer(user_id):
                try:
                    await query.answer("❌ غير مصرح", show_alert=True)
                except BadRequest:
                    pass
                return
            cid = int(data.split(":")[-1])
            row = await DB.fetchone("SELECT status FROM contests WHERE id=?", (cid,))
            if not row or row[0] != 'active':
                try:
                    await query.answer("❌ المسابقة غير نشطة", show_alert=True)
                except BadRequest:
                    pass
                return
            winner = await DB.fetchone("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,))
            if winner:
                success = await DB.declare_winner(cid, winner[0])
                if success:
                    await query.edit_message_text(f"✅ الفائز: `{winner[0]}`")
                    try:
                        await context.bot.send_message(winner[0], f"🎉 مبروك! لقد فزت بالمسابقة!")
                    except Exception as e:
                        logger.warning(f"⚠️ فشل إشعار الفائز {winner[0]}: {e}")
                else:
                    await query.answer("❌ فشل إعلان الفائز", show_alert=True)
                    return
            try:
                await query.answer()
            except BadRequest:
                pass

    @staticmethod
    async def _handle_import(update, context, query, user_id):
        if not CONFIG.is_developer(user_id):
            try:
                await query.answer("❌ غير مصرح", show_alert=True)
            except BadRequest:
                pass
            return
        data = query.data
        if data == CB.ADMIN_IMPORT_REPLIES:
            StateManager.set(user_id, UserState.WAIT_IMPORT_FILE)
            context.user_data['import_chat_id'] = -1
            await query.edit_message_text("📤 أرسل ملف JSON للاستيراد:")
            try:
                await query.answer()
            except BadRequest:
                pass
        elif data == CB.ADMIN_IMPORT_GITHUB:
            StateManager.set(user_id, UserState.WAIT_GITHUB_URL)
            await query.edit_message_text("📥 أرسل رابط GitHub (JSON):")
            try:
                await query.answer()
            except BadRequest:
                pass


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

        if state == UserState.WAIT_IMPORT_FILE:
            if not msg.document:
                await safe_send(context.bot, user_id, "❌ أرسل ملف JSON")
                StateManager.clear(user_id)
                return
            file = msg.document
            if not file.file_name.endswith('.json'):
                await safe_send(context.bot, user_id, "❌ الملف يجب أن يكون JSON")
                StateManager.clear(user_id)
                return
            try:
                file_obj = await context.bot.get_file(file.file_id)
                temp_path = f"/tmp/import_{user_id}.json"
                await file_obj.download_to_drive(temp_path)
                import_chat_id = context.user_data.get('import_chat_id', -1)
                count = await import_auto_replies(import_chat_id, temp_path, overwrite=True)
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
                Path(temp_path).unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"❌ فشل الاستيراد: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GITHUB_URL:
            url = text.strip()
            if not url.startswith('http'):
                await safe_send(context.bot, user_id, "❌ رابط غير صالح")
                StateManager.clear(user_id)
                return
            json_data = await fetch_json_from_url(url)
            if not json_data:
                await safe_send(context.bot, user_id, "❌ فشل التحميل")
                StateManager.clear(user_id)
                return
            count = await import_auto_replies(-1, json_data, overwrite=True)
            _auto_reply_cache.invalidate()
            await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_CHANNEL:
            try:
                chat = await context.bot.get_chat(text)
                if chat.type != 'channel':
                    await safe_send(context.bot, user_id, "❌ ليس قناة!")
                    StateManager.clear(user_id)
                    return
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status != 'administrator':
                    await safe_send(context.bot, user_id, "❌ البوت ليس مشرفاً!")
                    StateManager.clear(user_id)
                    return

                user_member = await context.bot.get_chat_member(chat.id, user_id)
                if user_member.status not in ['creator', 'administrator']:
                    await safe_send(context.bot, user_id, "❌ يجب أن تكون مشرفًا في القناة لإضافتها.")
                    StateManager.clear(user_id)
                    return

                existing_channel = await DB.get_channel_by_user(user_id, chat.id)
                if existing_channel:
                    await safe_send(context.bot, user_id, "⚠️ هذه القناة مضافة مسبقاً")
                    StateManager.clear(user_id)
                    return

                if user_id != CONFIG.PRIMARY_OWNER_ID:
                    has_sub = await DB.has_active_subscription(user_id)
                    if not has_sub:
                        await safe_send(context.bot, user_id, "❌ يجب أن يكون لديك اشتراك نشط لإضافة قناة")
                        StateManager.clear(user_id)
                        return

                    active_plan = await DB.get_active_plan(user_id)
                    if active_plan:
                        current_channels = len(await DB.get_user_channels(user_id))
                        if current_channels >= active_plan['max_channels']:
                            await safe_send(
                                context.bot,
                                user_id,
                                f"❌ لقد وصلت للحد الأقصى ({active_plan['max_channels']} قنوات) في خطتك."
                            )
                            StateManager.clear(user_id)
                            return

                result = await DB.add_channel(user_id, chat.id, chat.title or "قناة")
                if result:
                    await DB.set_active_channel(user_id, result)
                    await safe_send(context.bot, user_id, f"✅ تمت إضافة {chat.title}!")
                else:
                    active_plan = await DB.get_active_plan(user_id)
                    if active_plan:
                        current_channels = len(await DB.get_user_channels(user_id))
                        if current_channels >= active_plan['max_channels']:
                            await safe_send(context.bot, user_id, f"❌ لقد وصلت للحد الأقصى ({active_plan['max_channels']} قنوات) في خطتك.")
                        else:
                            await safe_send(context.bot, user_id, "❌ فشلت الإضافة (ربما تجاوزت حد القنوات المسموح)")
                    else:
                        await safe_send(context.bot, user_id, "❌ يجب أن يكون لديك اشتراك نشط لإضافة قناة")
            except Exception as e:
                logger.error(f"❌ فشل إضافة القناة: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.ADDING_POSTS:
            if text.strip().lower() == "/done":
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "✅ تم إنهاء إضافة المنشورات.")
                return

            if text.strip().isdigit():
                await safe_send(
                    context.bot, user_id,
                    "⚠️ أنت في وضع إضافة المنشورات.\n"
                    "إذا أردت ضبط الجدولة فاضغط زر «القائمة الرئيسية» أولاً أو أرسل /done."
                )
                return

            media_type = 'text'
            media_file_id = None
            if msg.photo:
                media_type = 'photo'
                media_file_id = msg.photo[-1].file_id
            elif msg.video:
                media_type = 'video'
                media_file_id = msg.video.file_id
            elif msg.document:
                media_type = 'document'
                media_file_id = msg.document.file_id
            elif msg.audio:
                media_type = 'audio'
                media_file_id = msg.audio.file_id
            elif msg.voice:
                media_type = 'voice'
                media_file_id = msg.voice.file_id
            elif msg.animation:
                media_type = 'animation'
                media_file_id = msg.animation.file_id
            elif msg.sticker:
                media_type = 'sticker'
                media_file_id = msg.sticker.file_id
            elif msg.video_note:
                media_type = 'video_note'
                media_file_id = msg.video_note.file_id
            content = msg.caption or "" if media_type != 'text' else text

            active = await DB.get_active_channel(user_id)
            if active:
                active_plan = await DB.get_active_plan(user_id)
                limit = active_plan['max_posts'] if active_plan else CONFIG.MAX_POSTS_PER_CHANNEL
                row = await DB.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (active,))
                total_posts = row[0] if row else 0
                if total_posts >= limit and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await safe_send(
                        context.bot,
                        user_id,
                        f"❌ وصلت للحد الأقصى ({limit} منشور) في هذه القناة.\n"
                        "احذف بعض المنشورات أو استخدم قناة أخرى."
                    )
                    StateManager.clear(user_id)
                    return

                added = await DB.add_posts(user_id, active, [(content, media_type, media_file_id)])
                if added > 0:
                    await safe_send(context.bot, user_id, "✅ تم حفظ المنشور!\nأرسل منشورًا آخر أو /done للإنهاء.")
                else:
                    await safe_send(context.bot, user_id, "❌ فشل حفظ المنشور (ربما تجاوزت الحد المسموح).")
            else:
                await safe_send(context.bot, user_id, "❌ لا توجد قناة نشطة.")
            return

        if state == UserState.WAIT_BROADCAST:
            async def broadcast():
                offset = 0
                sent = 0
                try:
                    while True:
                        users = await DB.fetchall("SELECT user_id, banned FROM users ORDER BY user_id LIMIT 5000 OFFSET ?", (offset,))
                        if not users:
                            break
                        for uid, banned in users:
                            if not banned:
                                try:
                                    await safe_send(context.bot, uid, text)
                                    sent += 1
                                    await asyncio.sleep(0.05)
                                except:
                                    pass
                        offset += 5000
                    await safe_send(context.bot, user_id, f"✅ {sent}")
                except Exception as e:
                    logger.error(f"❌ فشل البث: {e}")
                    await safe_send(context.bot, user_id, "❌ فشل البث")

            asyncio.create_task(broadcast())
            await safe_send(context.bot, user_id, "⏳ جاري البث...")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_AUTO_KEY:
            context.user_data['auto_key'] = text.strip().lower()
            StateManager.set(user_id, UserState.WAIT_AUTO_REPLY)
            await safe_send(context.bot, user_id, "📝 الرد:")
            return

        if state == UserState.WAIT_AUTO_REPLY:
            chat_id_auto = context.user_data.get('auto_chat')
            keyword = context.user_data.get('auto_key')
            if chat_id_auto is not None and keyword:
                await DB.add_auto_reply(chat_id_auto, keyword, text)
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, "✅ تمت إضافة الرد")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_AUTO_DEL:
            chat_id_auto = context.user_data.get('auto_chat')
            if chat_id_auto is not None:
                await DB.remove_auto_reply(chat_id_auto, text.strip().lower())
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, "✅ تم حذف الرد")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GLOBAL_BAN:
            word = text.strip().lower()
            if len(word) >= 2:
                await DB.add_banned_word(word, -1, user_id)
                invalidate_banned_words_cache()
                await safe_send(context.bot, user_id, "✅ تمت الإضافة")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GLOBAL_BAN:
            await DB.remove_banned_word(text.strip().lower(), -1)
            invalidate_banned_words_cache()
            await safe_send(context.bot, user_id, "✅ تم الحذف")
            StateManager.clear(user_id)
            return

        if state == UserState.SUPPORT_MODE:
            content = msg.text or msg.caption or ""
            ticket_num = await DB.create_ticket(user_id, update.effective_user.username or "", content)
            await safe_send(context.bot, user_id, f"✅ #{ticket_num}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_MIN:
            try:
                val = int(text)
                min_val = await get_min_publish_interval()
                if val < min_val:
                    await safe_send(context.bot, user_id,
                                    f"❌ الحد الأدنى للفاصل الزمني هو {min_val} دقيقة")
                    StateManager.clear(user_id)
                    return
                if 1 <= val <= 1440:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_minutes',
                                                 interval_minutes=val)
                        await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {val} دقيقة")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-1440)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            except Exception as e:
                logger.error(f"❌ خطأ في WAIT_MIN: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_HOUR:
            try:
                val = int(text)
                if 1 <= val <= 168:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_hours', interval_hours=val)
                        await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {val} ساعة")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-168)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_DAY:
            try:
                val = int(text)
                if 1 <= val <= 365:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_days', interval_days=val)
                        await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {val} يوم")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-365)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PUB_TIME:
            if ':' in text:
                ch = context.user_data.get('schedule_ch')
                if ch:
                    await DB.update_schedule(ch, publish_time=text)
                    await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {text}")
            else:
                await safe_send(context.bot, user_id, "❌ الصيغة غير صالحة، استخدم HH:MM")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            word = text.strip().lower()
            if chat_id_ban and len(word) >= 2:
                await DB.add_banned_word(word, chat_id_ban, user_id)
                invalidate_banned_words_cache(chat_id_ban)
                await safe_send(context.bot, user_id, f"✅ تمت إضافة: {word}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            if chat_id_ban:
                await DB.remove_banned_word(text.strip().lower(), chat_id_ban)
                invalidate_banned_words_cache(chat_id_ban)
                await safe_send(context.bot, user_id, f"✅ تم حذف: {text}")
            StateManager.clear(user_id)
            return

        if state in (UserState.WAIT_BAN, UserState.WAIT_MUTE, UserState.WAIT_WARN,
                     UserState.WAIT_KICK, UserState.WAIT_RESTRICT, UserState.WAIT_UNBAN):
            chat_id_adv = context.user_data.get('adv_chat')
            try:
                parts = text.split()
                target = int(parts[0])
                if target <= 0:
                    await safe_send(context.bot, user_id, "❌ معرف غير صالح")
                    StateManager.clear(user_id)
                    return
                action_map = {
                    UserState.WAIT_BAN: "ban", UserState.WAIT_MUTE: "mute",
                    UserState.WAIT_WARN: "warn", UserState.WAIT_KICK: "kick",
                    UserState.WAIT_RESTRICT: "restrict", UserState.WAIT_UNBAN: "unban"
                }
                action = action_map.get(state)
                if action and chat_id_adv:
                    if action == 'unban':
                        await context.bot.unban_chat_member(chat_id_adv, target)
                        await DB.remove_penalties_for_user(target, chat_id_adv, penalty_type='ban')
                        await safe_send(context.bot, user_id, f"✅ تم إلغاء حظر `{target}`")
                    else:
                        duration_seconds = 60
                        if len(parts) > 1 and action in ('ban', 'mute', 'restrict'):
                            try:
                                minutes = int(parts[1])
                                if minutes > 0:
                                    duration_seconds = minutes * 60
                            except ValueError:
                                pass
                        success, msg = await apply_penalty(context.bot, chat_id_adv, target, action, duration_seconds)
                        await safe_send(context.bot, user_id, msg)
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            except Exception as e:
                logger.error(f"❌ خطأ في الإجراء: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PIN:
            chat_id_adv = context.user_data.get('adv_chat')
            try:
                if update.message.reply_to_message:
                    msg_id = update.message.reply_to_message.message_id
                else:
                    msg_id = int(text)
                await context.bot.pin_chat_message(chat_id_adv, msg_id)
                await safe_send(context.bot, user_id, f"📌 تم تثبيت الرسالة {msg_id}")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح أو رد على رسالة")
            except Exception as e:
                logger.error(f"❌ فشل التثبيت: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_CONTEST_TITLE:
            context.user_data['contest_title'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_DESC)
            await safe_send(context.bot, user_id, "📝 الوصف:")
            return

        if state == UserState.WAIT_CONTEST_DESC:
            context.user_data['contest_desc'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_PRIZE)
            await safe_send(context.bot, user_id, "🎁 الجائزة:")
            return

        if state == UserState.WAIT_CONTEST_PRIZE:
            context.user_data['contest_prize'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_DATE)
            await safe_send(context.bot, user_id, "📅 التاريخ (YYYY-MM-DD HH:MM):")
            return

        if state == UserState.WAIT_CONTEST_DATE:
            try:
                end_date = datetime.strptime(text, "%Y-%m-%d %H:%M")
                cid = await DB.create_contest(
                    user_id,
                    context.user_data.pop('contest_title', ''),
                    context.user_data.pop('contest_desc', ''),
                    context.user_data.pop('contest_prize', ''),
                    TimeUtils.mecca_to_utc(end_date).strftime('%Y-%m-%d %H:%M:%S')
                )
                await safe_send(context.bot, user_id, f"✅ مسابقة #{cid}")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ صيغة غير صالحة، استخدم YYYY-MM-DD HH:MM")
            except Exception as e:
                logger.error(f"❌ فشل إنشاء المسابقة: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_CONTEST_ANSWER:
            cid = context.user_data.get('contest_join')
            if cid:
                success = await DB.join_contest(cid, user_id, text)
                if success:
                    await safe_send(context.bot, user_id, "✅ تم المشاركة!")
                else:
                    await safe_send(context.bot, user_id, "❌ فشل المشاركة (ربما انتهت المسابقة أو شاركت مسبقًا)")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ADMIN_ADD:
            try:
                target = int(text)
                if target <= 0:
                    await safe_send(context.bot, user_id, "❌ معرف غير صالح")
                else:
                    await DB.execute("INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)",
                                     (target, user_id, TimeUtils.sql_iso()))
                    await safe_send(context.bot, user_id, f"✅ تم إضافة `{target}` كمشرف")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ADMIN_REM:
            try:
                target = int(text)
                if target <= 0:
                    await safe_send(context.bot, user_id, "❌ معرف غير صالح")
                else:
                    await DB.execute("DELETE FROM bot_admins WHERE user_id=?", (target,))
                    await safe_send(context.bot, user_id, f"✅ تم إزالة `{target}`")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GRANT_FREE:
            parts = text.split()
            if len(parts) < 2:
                await safe_send(context.bot, user_id, "❌ أرسل المعرف والأيام هكذا: `123456789 365`")
                StateManager.clear(user_id)
                return
            try:
                target_id = int(parts[0])
                days = int(parts[1])
            except ValueError:
                await safe_send(context.bot, user_id, "❌ قيم غير صالحة")
                StateManager.clear(user_id)
                return

            if days < 1 or days > 365:
                await safe_send(context.bot, user_id, "❌ عدد الأيام يجب أن يكون بين 1 و 365")
                StateManager.clear(user_id)
                return

            gift_plan = await DB.fetchone("SELECT id FROM plans WHERE is_gift=1 LIMIT 1")
            plan_id = gift_plan[0] if gift_plan else None
            if plan_id is None:
                await safe_send(context.bot, user_id, "❌ لا توجد خطة هدية متاحة")
                StateManager.clear(user_id)
                return

            success = await DB.grant_subscription_days(target_id, days, plan_id=plan_id, provider='manual')
            if success:
                await safe_send(context.bot, user_id, f"✅ تم منح {days} يوم للمستخدم `{target_id}`")
            else:
                await safe_send(context.bot, user_id, "❌ فشل المنح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_UPDATE:
            ch = await DB.get_updates_channel()
            if ch:
                try:
                    if ch.lstrip('-').isdigit():
                        await context.bot.send_message(int(ch), f"📢 {text}")
                    else:
                        await context.bot.send_message(f"@{ch}", f"📢 {text}")
                    await safe_send(context.bot, user_id, "✅ تم الإرسال")
                except Exception as e:
                    await safe_send(context.bot, user_id, f"❌ فشل الإرسال: {str(e)[:50]}")
            else:
                await safe_send(context.bot, user_id, "❌ لا توجد قناة تحديثات")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_UPDATE_CH:
            await DB.set_setting('updates_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, f"✅ تم تعيين قناة التحديثات: {text}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_FORCE:
            await DB.set_setting('force_subscribe_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, f"✅ تم تعيين الاشتراك الإجباري: {text}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_DAYS:
            try:
                val = int(text)
                if 1 <= val <= 30:
                    await DB.update_reminder_settings(user_id, reminder_days_before=val)
                    await safe_send(context.bot, user_id, f"✅ تم تعيين الأيام إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-30)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_MAX_LEN:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and val >= 0:
                    await DB.execute("UPDATE group_security SET max_message_length=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين الحد الأقصى إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_WARN_COUNT:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and 1 <= val <= 10:
                    await DB.execute("UPDATE group_security SET max_warnings=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين عدد التحذيرات إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-10)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_LOG_CH:
            try:
                chat = await context.bot.get_chat(text)
                if chat.type == 'channel':
                    await DB.set_setting('log_channel_id', str(chat.id))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين قناة السجلات: {text}")
                else:
                    await safe_send(context.bot, user_id, "❌ هذه ليست قناة")
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ فشل التعيين: {str(e)[:50]}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_KEYWORD:
            context.user_data['keyword'] = text.strip().lower()
            StateManager.set(user_id, UserState.WAIT_REPLY)
            await safe_send(context.bot, user_id, "📝 الرد:")
            return

        if state == UserState.WAIT_REPLY:
            keyword = context.user_data.get('keyword')
            if keyword:
                await DB.add_auto_reply(-1, keyword, text)
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, f"✅ تم إضافة الرد للكلمة: {keyword}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PENALTY_DURATION:
            try:
                dur_minutes = int(text)
                if dur_minutes < 0 or dur_minutes > 1440:
                    await safe_send(context.bot, user_id, "❌ المدة غير صالحة (0-1440 دقيقة)")
                    StateManager.clear(user_id)
                    return
                chat_id_pen = context.user_data.get('penalty_chat')
                v_type = context.user_data.get('penalty_vtype')
                p_type = context.user_data.get('penalty_ptype')
                if chat_id_pen and v_type and p_type:
                    duration_seconds = dur_minutes * 60 if dur_minutes > 0 else 0
                    await DB.set_violation_penalty(chat_id_pen, v_type, p_type, duration_seconds)
                    await safe_send(context.bot, user_id, "✅ تم حفظ العقوبة بنجاح")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_WELCOME_TEXT:
            chat_id_sec = context.user_data.get('sec_chat')
            if chat_id_sec:
                await DB.execute("UPDATE group_security SET welcome_text=? WHERE chat_id=?", (text, chat_id_sec))
                await safe_send(context.bot, user_id, "✅ تم تعيين نص الترحيب")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GOODBYE_TEXT:
            chat_id_sec = context.user_data.get('sec_chat')
            if chat_id_sec:
                await DB.execute("UPDATE group_security SET goodbye_text=? WHERE chat_id=?", (text, chat_id_sec))
                await safe_send(context.bot, user_id, "✅ تم تعيين نص الوداع")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_SLOW_MODE_SECONDS:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and 0 <= val <= 3600:
                    await DB.execute("UPDATE group_security SET slow_mode_seconds=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين مدة الوضع البطيء إلى {val} ثانية")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (0-3600)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ANTIFLOOD_MESSAGES:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and val >= 1:
                    await DB.execute("UPDATE group_security SET antiflood_messages=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين عدد الرسائل إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ANTIFLOOD_SECONDS:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and val >= 1:
                    await DB.execute("UPDATE group_security SET antiflood_seconds=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين الفترة إلى {val} ثانية")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_NIGHT_START:
            if re.match(r'^\d{2}:\d{2}$', text):
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec:
                    await DB.execute("UPDATE group_security SET night_mode_start=? WHERE chat_id=?", (text, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين وقت البداية إلى {text}")
            else:
                await safe_send(context.bot, user_id, "❌ الصيغة غير صالحة (HH:MM)")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_NIGHT_END:
            if re.match(r'^\d{2}:\d{2}$', text):
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec:
                    await DB.execute("UPDATE group_security SET night_mode_end=? WHERE chat_id=?", (text, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين وقت النهاية إلى {text}")
            else:
                await safe_send(context.bot, user_id, "❌ الصيغة غير صالحة (HH:MM)")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PENALTY_DEFAULT_DURATION:
            try:
                dur_minutes = int(text)
                if dur_minutes < 0:
                    await safe_send(context.bot, user_id, "❌ المدة غير صالحة")
                    StateManager.clear(user_id)
                    return
                chat_id_pen = context.user_data.get('penalty_chat')
                p_type = context.user_data.get('penalty_type')
                if chat_id_pen and p_type:
                    duration_seconds = dur_minutes * 60 if dur_minutes > 0 else 0
                    col_map = {
                        'mute': 'mute_default_duration',
                        'ban': 'ban_default_duration',
                        'restrict': 'restrict_default_duration'
                    }
                    col = col_map.get(p_type)
                    if col:
                        await DB.execute(f"UPDATE group_security SET {col}=? WHERE chat_id=?", (duration_seconds, chat_id_pen))
                        await safe_send(context.bot, user_id, f"✅ تم تعيين {p_type} إلى {dur_minutes} دقيقة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

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
            await apply_violation_penalty(context, chat_id, update.effective_user.id, 'links', "مخالفة روابط")
            return

        if settings.get('mentions', False) and TextUtils.contains_mention(text):
            if can_delete:
                try:
                    await update.message.delete()
                except:
                    pass
            await apply_violation_penalty(context, chat_id, update.effective_user.id, 'mentions', "مخالفة منشن")
            return

        if settings.get('delete_banned_words', False):
            banned_words = await get_banned_words_cached(chat_id)
            if any(word in text.lower() for word in banned_words):
                if can_delete:
                    try:
                        await update.message.delete()
                    except:
                        pass
                await apply_violation_penalty(context, chat_id, update.effective_user.id, 'banned_words', "كلمة محظورة")
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
                await apply_violation_penalty(context, chat_id, user_id, 'service', "رسالة خدمة")

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

async def apply_violation_penalty(context, chat_id, user_id, violation_type, reason="مخالفة"):
    if await is_authorized_in_group(context.bot, chat_id, user_id):
        return

    # زيادة تحذيرات المستخدم (تُستخدم كعداد للمخالفات)
    warnings = await DB.add_user_warning(user_id, chat_id)

    # محاولة الحصول على عقوبة مخصصة لنوع المخالفة
    rule = await DB.get_violation_penalty(chat_id, violation_type)
    if not rule:
        # إذا لم توجد عقوبة مخصصة، استخدم العقوبة الافتراضية من إعدادات التحذير (warn_penalty)
        settings = await DB.get_security_settings(chat_id)
        penalty_type = settings.get('warn_penalty', 'ban')
        duration_seconds = 0  # دائم افتراضيًا
    else:
        penalty_type = rule['penalty_type']
        duration_seconds = rule['duration_seconds']

    max_warnings = (await DB.get_security_settings(chat_id)).get('max_warnings', 3)

    if warnings < max_warnings:
        try:
            await context.bot.send_message(
                chat_id,
                f"⚠️ المستخدم `{user_id}` تلقى إنذارًا ({warnings}/{max_warnings}) بسبب: {reason}"
            )
        except:
            pass
        return

    # تطبيق العقوبة
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
            # تسجيل العقوبة في قاعدة البيانات
            await DB.add_penalty(
                user_id=user_id,
                chat_id=chat_id,
                penalty_type=penalty_type,
                duration=duration_seconds,
                reason=reason,
                issued_by=context.bot.id
            )
            # إعادة تعيين التحذيرات بعد العقوبة
            await DB.reset_user_warnings(user_id, chat_id)
        else:
            logger.error(f"❌ نوع عقوبة غير صالح في apply_violation_penalty: {penalty_type}")
    except Exception as e:
        logger.error(f"❌ فشل تطبيق عقوبة {penalty_type} على {user_id}: {e}")
