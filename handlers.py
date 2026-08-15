#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers.py - جميع معالجات البوت (النسخة الكاملة)
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
    get_reply_from_file
)

logger = logging.getLogger(__name__)


class CommandHandlers:
    """جميع معالجات الأوامر"""

    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        username = update.effective_user.username or ""
        first_name = update.effective_user.first_name or ""
        await DB.register_user(user_id, username, first_name)

        args = context.args
        if args and args[0].startswith('ref_'):
            ref_code = args[0][4:]
            referrer = await DB.get_user_by_referral_code(ref_code)
            if referrer and referrer != user_id:
                await DB.add_referral(referrer, user_id)
                await DB.claim_referral_reward(referrer)

        force_ch = await DB.get_force_subscribe_channel()
        if force_ch and user_id != CONFIG.PRIMARY_OWNER_ID:
            try:
                chat = await context.bot.get_chat(f"@{force_ch}")
                member = await context.bot.get_chat_member(chat.id, user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton("📢 اشترك", url=f"https://t.me/{force_ch}"),
                        InlineKeyboardButton("✅ تحقق", callback_data=CB.CHECK_SUB)
                    ]])
                    await safe_send(context.bot, user_id, f"⚠️ اشترك في @{force_ch}", reply_markup=kb)
                    return
            except:
                pass

        lang = await DB.get_user_language(user_id)
        active = await DB.get_active_channel(user_id)
        cnt = 0
        ch_display = "لا توجد قنوات"
        if active:
            cnt = await DB.get_unpublished_posts_count(active)
            ch_info = await DB.get_channel_info(active)
            if ch_info:
                ch_display = ch_info['channel_name']

        groups = len(await DB.get_user_groups(user_id))
        has_sub = await DB.has_active_subscription(user_id)
        sub_text = "✅" if has_sub else "❌"
        auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
        recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"

        kb_rows = KeyboardFactory.get_menu("main_menu")
        keyboard = []
        for row in kb_rows:
            btn_row = []
            for item in row:
                if item == "admin_panel_btn":
                    if CONFIG.is_developer(user_id):
                        btn_row.append(InlineKeyboardButton("👑 لوحة الأدمن", callback_data=CB.ADMIN))
                else:
                    text_btn = KeyboardFactory.get_text(item)
                    if item.endswith("_url"):
                        btn_row.append(InlineKeyboardButton(text_btn, url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup"))
                    else:
                        btn_row.append(InlineKeyboardButton(text_btn, callback_data=item))
            if btn_row:
                keyboard.append(btn_row)

        if CONFIG.is_developer(user_id):
            keyboard.append([InlineKeyboardButton("👑 لوحة الأدمن", callback_data=CB.ADMIN)])

        kb = InlineKeyboardMarkup(keyboard)
        title = f"🌿 **{CONFIG.BOT_NAME}**\n\n👤 `{user_id}`\n👥 {groups}\n💎 {sub_text}\n📡 {ch_display}\n⏳ {cnt}\n⚙️ {auto}\n♻️ {recycle}"
        await safe_send(context.bot, user_id, title, reply_markup=kb)

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = "📚 **الأوامر:**\n\n/start - الرئيسية\n/trial - تجربة\n/subscribe - اشتراك\n/support - دعم"
        await safe_send(context.bot, update.effective_user.id, text)

    @staticmethod
    async def trial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if await DB.has_used_trial(user_id):
            await safe_send(context.bot, user_id, "❌ استخدمت التجربة")
            return
        days = await DB.activate_trial(user_id)
        await safe_send(context.bot, user_id, f"🎁 {days} يوم!")

    @staticmethod
    async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        kb = KeyboardFactory.build("plans")
        await safe_send(context.bot, update.effective_user.id, "💎 الباقات:", reply_markup=kb)

    @staticmethod
    async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        StateManager.set(update.effective_user.id, UserState.SUPPORT_MODE)
        await safe_send(context.bot, update.effective_user.id, "📞 أرسل رسالتك:")

    @staticmethod
    async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = f"👨‍💻 **المطور**\n\n📌 `{CONFIG.PRIMARY_OWNER_ID}`\n🔗 @{CONFIG.BOT_USERNAME}\n📞 @RelaxMgr"
        await safe_send(context.bot, update.effective_user.id, text)

    @staticmethod
    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not CONFIG.is_developer(update.effective_user.id):
            return
        stats = await DB.get_user_stats()
        await safe_send(context.bot, update.effective_user.id, f"👥 {stats['users']}\n⛔ {stats['banned']}")

    @staticmethod
    async def language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        buttons.append([InlineKeyboardButton("🔙", callback_data=CB.BACK)])
        await safe_send(context.bot, update.effective_user.id, "🌐 اختر:", reply_markup=InlineKeyboardMarkup(buttons))

    @staticmethod
    async def security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ لا صلاحية")
            return
        settings = await DB.get_security_settings(chat_id)
        text = await KeyboardFactory._format_security_text(settings)
        kb = KeyboardFactory.build("security", chat_id)
        await safe_send(context.bot, user_id, text, reply_markup=kb)

    @staticmethod
    async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        kb = KeyboardFactory.build("panel", chat_id)
        await safe_send(context.bot, user_id, "📋 لوحة التحكم", reply_markup=kb)

    @staticmethod
    async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        await DB.execute("INSERT OR REPLACE INTO chat_locks VALUES (?,1,?,?)", (chat_id, TimeUtils.utc_iso(), user_id))
        await safe_send(context.bot, user_id, "🔒 تم")

    @staticmethod
    async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        await DB.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await safe_send(context.bot, user_id, "🔓 تم")

    @staticmethod
    async def contests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        contests = await DB.get_active_contests(10)
        if not contests:
            await safe_send(context.bot, update.effective_user.id, "📭 لا توجد")
            return
        text = "🏆 **المسابقات**\n\n"
        for c in contests:
            text += f"• {c['title']}\n"
        await safe_send(context.bot, update.effective_user.id, text)

    # ========== المخفيون ==========

    @staticmethod
    async def register_hidden_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id != CONFIG.PRIMARY_OWNER_ID:
            await safe_send(context.bot, user_id, "❌ المالك الأساسي فقط")
            return
        if not context.args:
            return
        try:
            owner_id = int(context.args[0])
        except:
            return
        chat_id = update.effective_chat.id
        await DB.execute("INSERT OR IGNORE INTO hidden_owner_groups VALUES (?,?,1)", (chat_id, owner_id))
        invalidate_auth_cache(chat_id, owner_id)
        await safe_send(context.bot, user_id, f"✅ {owner_id}")

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
        await safe_send(context.bot, user_id, f"✅ {owner_id}")

    @staticmethod
    async def add_hidden_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        is_owner = user_id == CONFIG.PRIMARY_OWNER_ID
        if not is_owner:
            row = await DB.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
            is_owner = row is not None
        if not is_owner:
            await safe_send(context.bot, user_id, "❌ غير مصرح")
            return
        if not context.args:
            return
        try:
            admin_id = int(context.args[0])
        except:
            return
        await DB.execute("INSERT OR IGNORE INTO hidden_admins VALUES (?,?,?,?)", (chat_id, admin_id, user_id, TimeUtils.utc_iso()))
        invalidate_auth_cache(chat_id, admin_id)
        await safe_send(context.bot, user_id, f"✅ {admin_id}")

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
        await safe_send(context.bot, user_id, f"✅ {admin_id}")

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

    @staticmethod
    async def syncgroup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
            await safe_send(context.bot, update.effective_user.id, "❌ هذا الأمر يستخدم فقط في المجموعات")
            return

        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "بدون اسم"
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)

        if user_id < 0:
            await safe_send(context.bot, chat_id, "❌ البوتات لا تستطيع استخدام هذا الأمر")
            return

        await DB.register_group(chat_id, chat_name, user_id, update.effective_chat.username)
        bot_perms = await check_bot_permissions(context.bot, chat_id)

        if not bot_perms.get('can_act', False):
            msg = f"⚠️ **البوت ليس مشرفاً في المجموعة!**\n\n"
            msg += f"📌 تم تسجيل المجموعة `{chat_name}`.\n\n"
            msg += f"🔹 **لتفعيل الميزات المتقدمة:**\n"
            msg += f"• اجعل البوت مشرفاً في المجموعة\n"
            msg += f"• ثم استخدم `/syncgroup` مرة أخرى"
            await safe_send(context.bot, user_id, msg)
            return

        is_admin = False
        real_user_id = user_id
        is_hidden = (user_id == CONFIG.ANONYMOUS_ADMIN_ID)

        if is_hidden:
            try:
                admins = await context.bot.get_chat_administrators(chat_id)
                for admin in admins:
                    if admin.status == 'creator':
                        real_user_id = admin.user.id
                        is_admin = True
                        break
                if not is_admin and admins:
                    real_user_id = admins[0].user.id
                    is_admin = True
            except:
                is_admin = False
        else:
            try:
                member = await context.bot.get_chat_member(chat_id, user_id)
                is_admin = member.status in ['administrator', 'creator']
                real_user_id = user_id
            except:
                is_admin = False

        if is_admin:
            await DB.execute(
                "INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,?)",
                (chat_id, real_user_id, 1 if is_hidden else 0)
            )
            await DB.execute(
                "INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?,?)",
                (real_user_id, chat_id)
            )
            invalidate_auth_cache(chat_id, real_user_id)

            try:
                admins = await context.bot.get_chat_administrators(chat_id)
                admin_ids = [a.user.id for a in admins]
                admin_count = await DB.sync_group_admins(chat_id, admin_ids)
            except:
                admin_count = 0

            msg = f"✅ **تم تفعيل المجموعة بنجاح!**\n\n"
            msg += f"📌 اسم المجموعة: {chat_name}\n"
            msg += f"🆔 المعرف: {chat_id}\n"
            msg += f"👤 تم تسجيل {'المالك' if not is_hidden else 'المشرف المخفي'} (المعرف: `{real_user_id}`)\n"
            msg += f"👥 تم مزامنة {admin_count} مشرف\n\n"
            msg += f"🔐 استخدم `/security` لإعدادات الأمان\n"
            msg += f"🛠️ استخدم `/panel` للوحة التحكم"

            if is_hidden:
                await safe_send(context.bot, chat_id, f"🤖 **تم تفعيل البوت بواسطة مشرف مخفي!**")
                await safe_send(context.bot, chat_id, msg)
                if real_user_id and real_user_id > 0 and real_user_id != CONFIG.ANONYMOUS_ADMIN_ID:
                    try:
                        await safe_send(context.bot, real_user_id, msg)
                    except:
                        pass
            else:
                await safe_send(context.bot, real_user_id, msg)
                await safe_send(context.bot, chat_id, f"🤖 **تم تفعيل البوت في المجموعة!**")
        else:
            msg = f"✅ **تم تسجيل المجموعة!**\n\n"
            msg += f"📌 اسم المجموعة: {chat_name}\n"
            msg += f"🆔 المعرف: {chat_id}\n\n"
            msg += f"🔹 **لتفعيل الميزات المتقدمة:**\n"
            msg += f"• تأكد من أن البوت مشرف في المجموعة\n"
            msg += f"• يجب أن يقوم أحد المشرفين بتنفيذ الأمر"
            await safe_send(context.bot, user_id, msg)

    @staticmethod
    async def ban(update, context): await CommandHandlers._moderation_command(update, context, "ban")
    @staticmethod
    async def mute(update, context): await CommandHandlers._moderation_command(update, context, "mute")
    @staticmethod
    async def warn(update, context): await CommandHandlers._moderation_command(update, context, "warn")
    @staticmethod
    async def kick(update, context): await CommandHandlers._moderation_command(update, context, "kick")
    @staticmethod
    async def restrict(update, context): await CommandHandlers._moderation_command(update, context, "restrict")
    @staticmethod
    async def unban(update, context): await CommandHandlers._moderation_command(update, context, "unban")

    @staticmethod
    async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        if update.message.reply_to_message:
            try:
                await context.bot.pin_chat_message(update.effective_chat.id, update.message.reply_to_message.message_id)
            except:
                pass

    @staticmethod
    async def _moderation_command(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        if not context.args:
            return
        try:
            target = int(context.args[0])
        except:
            return
        if await is_authorized_in_group(context.bot, chat_id, target):
            return
        if action == 'unban':
            try:
                await context.bot.unban_chat_member(chat_id, target)
            except:
                pass
            return
        success, msg = await apply_penalty(context.bot, chat_id, target, action, 60)
        await safe_send(context.bot, user_id, msg)


class CallbackHandlers:
    """معالجات الأزرار"""

    @staticmethod
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        data = query.data
        if not data:
            return
        user_id = query.from_user.id

        try:
            if data in [CB.MAIN, CB.BACK]:
                await query.answer()
                await CommandHandlers.start(update, context)
                return

            if data == CB.TRIAL:
                if await DB.has_used_trial(user_id):
                    await query.edit_message_text("❌ استخدمت التجربة")
                else:
                    days = await DB.activate_trial(user_id)
                    await query.edit_message_text(f"🎁 {days} يوم!")
                return

            if data == CB.DEVELOPER:
                await CommandHandlers.developer(update, context)
                return

            if data == CB.SUBSCRIBE:
                await CommandHandlers.subscribe(update, context)
                return

            if data == CB.SUPPORT:
                await CommandHandlers.support(update, context)
                return

            if data == CB.LANGUAGE:
                await CommandHandlers.language(update, context)
                return

            if data == CB.SETTINGS:
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings")
                await query.edit_message_text(f"⚙️ {auto}\n♻️ {recycle}", reply_markup=kb)
                return

            if data == CB.TOGGLE_AUTO:
                cur = await DB.get_auto_publish_status(user_id)
                await DB.set_auto_publish(user_id, not cur)
                await CallbackHandlers.handle(update, context)
                return

            if data == CB.TOGGLE_REC:
                cur = await DB.get_auto_recycle_status(user_id)
                await DB.set_auto_recycle(user_id, not cur)
                await CallbackHandlers.handle(update, context)
                return

            if data == CB.PLANS:
                kb = KeyboardFactory.build("plans")
                await query.edit_message_text("💎 الباقات:", reply_markup=kb)
                return

            if data.startswith("buy_sub_"):
                days = int(data.split("_")[-1])
                plan_names = {1: "يوم", 7: "أسبوع", 30: "شهر", 90: "3 أشهر"}
                plan = await DB.get_plan_by_name(plan_names.get(days, ""))
                if plan:
                    try:
                        await context.bot.send_invoice(
                            chat_id=user_id,
                            title=plan['name'],
                            description=plan['description'],
                            payload=json.dumps({'plan_id': plan['id']}),
                            provider_token="",
                            currency="XTR",
                            prices=[LabeledPrice(plan['name'], plan['price'])]
                        )
                    except:
                        pass
                return

            if data == CB.CH_ADD:
                if not await DB.has_active_subscription(user_id):
                    await query.answer("❌ انتهى اشتراكك!", show_alert=True)
                    return
                StateManager.set(user_id, UserState.WAIT_CHANNEL)
                await query.edit_message_text("📡 أرسل معرف القناة:")
                return

            if data == CB.CH_LIST:
                channels = await DB.get_user_channels(user_id)
                if not channels:
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton("➕ إضافة", callback_data=CB.CH_ADD),
                        InlineKeyboardButton("🔙", callback_data=CB.BACK)
                    ]])
                    await query.edit_message_text("📭 لا توجد قنوات!\nاضغط للإضافة:", reply_markup=kb)
                    return
                text = "📡 **قنواتي**\n\n"
                kb = []
                for ch in channels:
                    st = "✅" if not ch['banned'] else "🚫"
                    text += f"{st} {ch['channel_name']} (`{ch['channel_id']}`)\n"
                    kb.append([InlineKeyboardButton(f"📌 {ch['channel_name'][:20]}", callback_data=f"{CB.CH_SEL}{ch['id']}")])
                kb.append([InlineKeyboardButton("➕ إضافة", callback_data=CB.CH_ADD)])
                kb.append([InlineKeyboardButton("🔙", callback_data=CB.BACK)])
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data.startswith(CB.CH_SEL):
                ch_id = int(data.split(":")[-1])
                await DB.set_active_channel(user_id, ch_id)
                await query.edit_message_text("✅ تم تحديد القناة!")
                return

            if data.startswith(CB.CH_DEL):
                ch_id = int(data.split(":")[-1])
                await DB.delete_channel(user_id, ch_id)
                await query.answer("✅ تم الحذف")
                await CallbackHandlers.handle(update, context)
                return

            if data == CB.POST_ADD:
                if not await DB.has_active_subscription(user_id):
                    await query.answer("❌ انتهى اشتراكك!", show_alert=True)
                    return
                active = await DB.get_active_channel(user_id)
                if not active:
                    await query.edit_message_text("❌ لا توجد قناة نشطة")
                    return
                context.user_data[f"session_{user_id}"] = []
                context.user_data[f"session_target_{user_id}"] = 15
                StateManager.set(user_id, UserState.ADDING_POSTS)
                await query.edit_message_text("📥 أرسل المنشورات (15):")
                return

            if data == CB.POST_PUB:
                active = await DB.get_active_channel(user_id)
                if not active:
                    return
                post = await DB.get_next_post(active)
                if post:
                    ch_info = await DB.get_channel_info(active)
                    if ch_info:
                        try:
                            if post['media_type'] == 'photo' and post['media_file_id']:
                                await context.bot.send_photo(ch_info['channel_id'], post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
                            elif post['media_type'] == 'video' and post['media_file_id']:
                                await context.bot.send_video(ch_info['channel_id'], post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
                            else:
                                await context.bot.send_message(ch_info['channel_id'], post['text'] or ".")
                            await DB.mark_post_published(post['id'])
                            await query.edit_message_text("✅ تم النشر!")
                        except Exception as e:
                            await query.edit_message_text(f"❌ {str(e)[:100]}")
                else:
                    await query.edit_message_text("📭 لا توجد منشورات")
                return

            if data == CB.POST_LIST:
                active = await DB.get_active_channel(user_id)
                if active:
                    posts = await DB.get_user_posts(active, 10)
                    text = "📋 **منشوراتي**\n\n"
                    for p in posts:
                        text += f"🆔 {p['id']}\n"
                    kb = [[InlineKeyboardButton("🔙", callback_data=CB.BACK)]]
                    await query.edit_message_text(text if posts else "📭 لا يوجد", reply_markup=InlineKeyboardMarkup(kb))
                return

            if data == CB.POST_REC:
                active = await DB.get_active_channel(user_id)
                if active:
                    count = await DB.reset_posts(active)
                    await query.edit_message_text(f"♻️ {count} منشور!")
                return

            if data == CB.GROUPS:
                groups = await DB.get_user_groups(user_id)
                if not groups:
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton("➕ أضف", url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")
                    ]])
                    await query.edit_message_text("📭 لا توجد مجموعات", reply_markup=kb)
                    return
                text = "👥 **مجموعاتي**\n\n"
                for gid, name, _, banned in groups:
                    text += f"{'✅' if not banned else '⛔'} {name}\n"
                kb = [[InlineKeyboardButton("🔙", callback_data=CB.BACK)]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data == CB.ADMIN:
                if CONFIG.is_developer(user_id):
                    kb = KeyboardFactory.build("admin_panel")
                    await query.edit_message_text("👑 لوحة الأدمن", reply_markup=kb)
                else:
                    await query.answer("❌ لا صلاحية", show_alert=True)
                return

            if data.startswith("sec_"):
                await CallbackHandlers._handle_security(update, context, query, user_id)
                return

            if data.startswith("admin_"):
                if CONFIG.is_developer(user_id):
                    await CallbackHandlers._handle_admin(update, context, query, user_id)
                return

            if data.startswith("auto_reply_"):
                await CallbackHandlers._handle_auto_reply(update, context, query, user_id)
                return

            if data.startswith("lang_"):
                lang_set = data.split("_")[-1]
                await DB.set_user_language(user_id, lang_set)
                await query.answer(f"✅ {lang_set}")
                await CommandHandlers.start(update, context)
                return

            await query.answer("⚠️", show_alert=True)

        except Exception as e:
            logger.error(f"Callback: {e}")

    @staticmethod
    async def _handle_security(update, context, query, user_id):
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("sec_", "")
        try:
            chat_id = int(parts[1])
        except:
            return

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("❌", show_alert=True)
            return

        field_map = {
            "links": "delete_links", "mentions": "mentions", "slow": "slow_mode",
            "video": "delete_videos", "audio": "delete_audio", "anim": "delete_animation",
            "service": "delete_service", "doc": "delete_documents", "sticker": "delete_stickers",
            "forward": "delete_forwarded", "poll": "delete_polls", "game": "delete_games",
            "voice": "delete_voice", "videonote": "delete_video_note",
            "welcome": "welcome_enabled", "goodbye": "goodbye_enabled",
            "flood": "antiflood_enabled", "night": "night_mode_enabled"
        }

        if action in field_map:
            col = field_map[action]
            current = await DB.fetchone(f"SELECT {col} FROM group_security WHERE chat_id=?", (chat_id,))
            new_val = 1 - (current[0] if current else 0)
            await DB.execute(f"UPDATE group_security SET {col}=? WHERE chat_id=?", (new_val, chat_id))
            settings = await DB.get_security_settings(chat_id)
            text = await KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id)
            await query.edit_message_text(text, reply_markup=kb)
            return

        if action == "enable_all":
            for f in field_map.values():
                await DB.execute(f"UPDATE group_security SET {f}=1 WHERE chat_id=?", (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = await KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id)
            await query.edit_message_text(text, reply_markup=kb)
            return

        if action == "disable_all":
            for f in field_map.values():
                await DB.execute(f"UPDATE group_security SET {f}=0 WHERE chat_id=?", (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = await KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id)
            await query.edit_message_text(text, reply_markup=kb)
            return

    @staticmethod
    async def _handle_admin(update, context, query, user_id):
        data = query.data

        if data == CB.ADMIN_USERS:
            stats = await DB.get_user_stats()
            await query.edit_message_text(f"👥 {stats['users']}\n⛔ {stats['banned']}")
            return

        if data == CB.ADMIN_BANNED:
            users = await DB.get_all_users()
            banned = [str(u[0]) for u in users if u[1] == 1]
            text = "⛔ **المحظورين**\n\n" + "\n".join(banned[:20]) if banned else "لا يوجد"
            await query.edit_message_text(text)
            return

        if data == CB.ADMIN_UNBAN_ALL:
            await DB.execute("UPDATE users SET banned=0 WHERE banned=1")
            await query.edit_message_text("✅ تم")
            return

        if data == CB.ADMIN_CHANNELS:
            channels = await DB.fetchall("SELECT channel_id, channel_name, banned FROM user_channels LIMIT 50")
            text = "📡 **القنوات**\n\n"
            for c in channels:
                text += f"{'✅' if not c[2] else '🚫'} {c[1]}\n"
            await query.edit_message_text(text if channels else "📭 لا توجد")
            return

        if data == CB.ADMIN_BROADCAST:
            StateManager.set(user_id, UserState.WAIT_BROADCAST)
            await query.edit_message_text("📨 أرسل الرسالة:")
            return

        if data == CB.ADMIN_BACKUP:
            try:
                backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2(PATHS.DB, backup_file)
                await safe_send(context.bot, user_id, f"✅ {backup_file.name}")
            except:
                pass
            return

        if data == CB.ADMIN_BANNED_WORDS:
            words = await DB.get_banned_words(-1)
            text = "🚫 **الكلمات**\n\n" + "\n".join(words) if words else "📭 لا يوجد"
            await query.edit_message_text(text)
            return

        if data == CB.ADMIN_ADD_BANNED:
            StateManager.set(user_id, UserState.WAIT_GLOBAL_BAN)
            await query.edit_message_text("🚫 أرسل الكلمة:")
            return

        if data == CB.ADMIN_REM_BANNED:
            StateManager.set(user_id, UserState.WAIT_REM_GLOBAL_BAN)
            await query.edit_message_text("🗑️ أرسل الكلمة:")
            return

        if data == CB.ADMIN_ADD_REPLY:
            StateManager.set(user_id, UserState.WAIT_KEYWORD)
            await query.edit_message_text("📝 أرسل الكلمة:")
            return

        if data == CB.ADMIN_DEL_REPLY:
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = -1
            await query.edit_message_text("🗑️ أرسل الكلمة:")
            return

        if data == CB.ADMIN_IMPORT_GITHUB:
            StateManager.set(user_id, UserState.WAIT_GITHUB_URL)
            await query.edit_message_text("📥 أرسل الرابط:")
            return

        await query.answer()

    @staticmethod
    async def _handle_auto_reply(update, context, query, user_id):
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("auto_reply_", "")
        try:
            chat_id = int(parts[1])
        except:
            return

        if action == "toggle":
            s = await DB.get_auto_reply_settings(chat_id)
            await DB.update_auto_reply_settings(chat_id, enabled=not s.get('enabled', False))
            await query.answer("✅ تم")
            return

        if action == "add":
            StateManager.set(user_id, UserState.WAIT_AUTO_KEY)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text("📝 أرسل الكلمة:")
            return

        if action == "del":
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text("🗑️ أرسل الكلمة:")
            return

        if action == "stats":
            stats = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? LIMIT 10", (chat_id,))
            text = "📊 **الإحصائيات**\n\n"
            for r in stats:
                text += f"• {r[0]}: {r[1]}\n"
            await query.edit_message_text(text if stats else "📭 لا يوجد")
            return

        if action == "list":
            replies = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=? LIMIT 20", (chat_id,))
            text = "📋 **الردود**\n\n" + "\n".join([f"• {r[0]}" for r in replies]) if replies else "📭 لا يوجد"
            await query.edit_message_text(text)
            return

        await query.answer()


class MessageHandlers:
    """معالجات الرسائل"""

    @staticmethod
    async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        msg = update.message
        text = msg.text.strip() if msg.text else ""
        state = StateManager.get(user_id)
        lang = await DB.get_user_language(user_id)

        # استيراد ملف JSON
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
                await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
                Path(temp_path).unlink(missing_ok=True)
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ {str(e)[:100]}")
            StateManager.clear(user_id)
            context.user_data.pop('import_chat_id', None)
            return

        # استيراد من GitHub
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
            await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
            StateManager.clear(user_id)
            return

        # إضافة قناة
        if state == UserState.WAIT_CHANNEL:
            if not await DB.has_active_subscription(user_id):
                await safe_send(context.bot, user_id, "❌ انتهى اشتراكك!")
                StateManager.clear(user_id)
                return
            channel_input = text.strip()
            if not channel_input:
                await safe_send(context.bot, user_id, "❌ أرسل معرف القناة!")
                StateManager.clear(user_id)
                return
            try:
                chat = await context.bot.get_chat(channel_input)
                if chat.type != 'channel':
                    await safe_send(context.bot, user_id, "❌ ليس قناة!")
                    StateManager.clear(user_id)
                    return
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status != 'administrator':
                    await safe_send(context.bot, user_id, "❌ البوت ليس مشرفاً!")
                    StateManager.clear(user_id)
                    return
                result = await DB.add_channel(user_id, chat.id, chat.title or "قناة")
                if result:
                    await DB.set_active_channel(user_id, result)
                    await safe_send(context.bot, user_id, f"✅ {chat.title}!")
                else:
                    await safe_send(context.bot, user_id, "⚠️ موجودة مسبقاً")
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ {str(e)[:100]}")
            StateManager.clear(user_id)
            return

        # إضافة منشورات
        if state == UserState.ADDING_POSTS:
            session = context.user_data.get(f"session_{user_id}", [])
            target = context.user_data.get(f"session_target_{user_id}", 15)
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

            content = msg.caption or "" if media_type != 'text' else text
            session.append((content, media_type, media_file_id))
            context.user_data[f"session_{user_id}"] = session

            if len(session) >= target:
                active = await DB.get_active_channel(user_id)
                if active:
                    await DB.add_posts(active, session)
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "✅ تم الحفظ!")
            else:
                await safe_send(context.bot, user_id, f"✅ {len(session)}/{target}")
            return

        # الجدولة
        if state == UserState.WAIT_MIN:
            try:
                val = int(text)
                ch = context.user_data.get('schedule_ch')
                if ch and 1 <= val <= 1440:
                    await DB.update_schedule(ch, schedule_type='interval_minutes', interval_minutes=val)
                    await safe_send(context.bot, user_id, "✅ تم")
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_HOUR:
            try:
                val = int(text)
                ch = context.user_data.get('schedule_ch')
                if ch and 1 <= val <= 168:
                    await DB.update_schedule(ch, schedule_type='interval_hours', interval_hours=val)
                    await safe_send(context.bot, user_id, "✅ تم")
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_DAY:
            try:
                val = int(text)
                ch = context.user_data.get('schedule_ch')
                if ch and 1 <= val <= 365:
                    await DB.update_schedule(ch, schedule_type='interval_days', interval_days=val)
                    await safe_send(context.bot, user_id, "✅ تم")
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PUB_TIME:
            if ':' in text:
                ch = context.user_data.get('schedule_ch')
                if ch:
                    await DB.update_schedule(ch, publish_time=text)
                    await safe_send(context.bot, user_id, "✅ تم")
            StateManager.clear(user_id)
            return

        # الكلمات المحظورة
        if state == UserState.WAIT_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            word = text.strip().lower()
            if chat_id_ban and len(word) >= 2:
                added, exists = await DB.add_banned_word(word, chat_id_ban, user_id)
                await safe_send(context.bot, user_id, "✅ تمت الإضافة" if added else "⚠️ موجودة")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            word = text.strip().lower()
            if chat_id_ban and word:
                await DB.remove_banned_word(word, chat_id_ban)
                await safe_send(context.bot, user_id, "✅ تم الحذف")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GLOBAL_BAN:
            word = text.strip().lower()
            if len(word) >= 2:
                added, _ = await DB.add_banned_word(word, -1, user_id)
                await safe_send(context.bot, user_id, "✅ تمت الإضافة" if added else "⚠️ موجودة")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GLOBAL_BAN:
            word = text.strip().lower()
            if word:
                await DB.remove_banned_word(word, -1)
                await safe_send(context.bot, user_id, "✅ تم الحذف")
            StateManager.clear(user_id)
            return

        # المشرفين
        if state == UserState.WAIT_ADMIN_ADD:
            try:
                target = int(text)
                await DB.execute("INSERT OR IGNORE INTO bot_admins VALUES (?,?,?)", (target, user_id, TimeUtils.utc_iso()))
                await safe_send(context.bot, user_id, "✅ تمت الإضافة")
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ADMIN_REM:
            try:
                target = int(text)
                await DB.execute("DELETE FROM bot_admins WHERE user_id=?", (target,))
                await safe_send(context.bot, user_id, "✅ تم الحذف")
            except:
                pass
            StateManager.clear(user_id)
            return

        # البث
        if state == UserState.WAIT_BROADCAST:
            users = await DB.get_all_users()
            sent = 0
            for uid, banned in users:
                if not banned:
                    try:
                        await safe_send(context.bot, uid, text)
                        sent += 1
                    except:
                        pass
            await safe_send(context.bot, user_id, f"✅ {sent}")
            StateManager.clear(user_id)
            return

        # التحديثات
        if state == UserState.WAIT_UPDATE:
            ch = await DB.get_updates_channel()
            if ch:
                try:
                    await context.bot.send_message(f"@{ch}", f"📢 {text}")
                    await safe_send(context.bot, user_id, "✅ تم الإرسال")
                except:
                    await safe_send(context.bot, user_id, "❌ فشل")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_UPDATE_CH:
            await DB.set_setting('updates_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, "✅ تم التعيين")
            StateManager.clear(user_id)
            return

        # اشتراك إجباري
        if state == UserState.WAIT_FORCE:
            await DB.set_setting('force_subscribe_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, "✅ تم التعيين")
            StateManager.clear(user_id)
            return

        # تذكيرات
        if state == UserState.WAIT_REM_DAYS:
            try:
                val = int(text)
                if 1 <= val <= 30:
                    await DB.update_reminder_settings(user_id, reminder_days_before=val)
                    await safe_send(context.bot, user_id, "✅ تم")
            except:
                pass
            StateManager.clear(user_id)
            return

        # إجراءات متقدمة
        if state in (UserState.WAIT_BAN, UserState.WAIT_MUTE, UserState.WAIT_WARN,
                     UserState.WAIT_KICK, UserState.WAIT_RESTRICT, UserState.WAIT_UNBAN):
            chat_id_adv = context.user_data.get('adv_chat')
            if chat_id_adv:
                try:
                    target = int(text.split()[0])
                    action_map = {
                        UserState.WAIT_BAN: "ban", UserState.WAIT_MUTE: "mute",
                        UserState.WAIT_WARN: "warn", UserState.WAIT_KICK: "kick",
                        UserState.WAIT_RESTRICT: "restrict", UserState.WAIT_UNBAN: "unban"
                    }
                    action = action_map.get(state)
                    if action and not await is_authorized_in_group(context.bot, chat_id_adv, target):
                        success, msg_text = await apply_penalty(context.bot, chat_id_adv, target, action, 60)
                        await safe_send(context.bot, user_id, msg_text)
                except:
                    pass
            StateManager.clear(user_id)
            return

        # تثبيت
        if state == UserState.WAIT_PIN:
            chat_id_adv = context.user_data.get('adv_chat')
            if chat_id_adv:
                try:
                    msg_id = update.message.reply_to_message.message_id if update.message.reply_to_message else int(text)
                    await context.bot.pin_chat_message(chat_id_adv, msg_id)
                    await safe_send(context.bot, user_id, "📌 تم")
                except:
                    pass
            StateManager.clear(user_id)
            return

        # المسابقات
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
                    TimeUtils.mecca_to_utc(end_date).isoformat()
                )
                await safe_send(context.bot, user_id, f"✅ مسابقة #{cid}")
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_CONTEST_ANSWER:
            cid = context.user_data.get('contest_join')
            if cid:
                await DB.join_contest(cid, user_id, text)
                await safe_send(context.bot, user_id, "✅ تمت المشاركة")
            StateManager.clear(user_id)
            return

        # الردود التلقائية
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
                await safe_send(context.bot, user_id, "✅ تمت الإضافة")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_AUTO_DEL:
            chat_id_auto = context.user_data.get('auto_chat')
            if chat_id_auto is not None:
                await DB.remove_auto_reply(chat_id_auto, text.strip().lower())
                await safe_send(context.bot, user_id, "✅ تم الحذف")
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
                await DB.add_auto_reply(0, keyword, text)
                await safe_send(context.bot, user_id, "✅ تمت الإضافة")
            StateManager.clear(user_id)
            return

        # قناة السجلات
        if state == UserState.WAIT_LOG_CH:
            try:
                chat = await context.bot.get_chat(text)
                if chat.type == 'channel':
                    await DB.set_setting('log_channel_id', str(chat.id))
                    await safe_send(context.bot, user_id, "✅ تم التعيين")
            except:
                pass
            StateManager.clear(user_id)
            return

        # الحد الأقصى
        if state == UserState.WAIT_MAX_LEN:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get(f'sec_chat_{user_id}')
                if chat_id_sec and val >= 0:
                    await DB.execute("UPDATE group_security SET max_message_length=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, "✅ تم")
            except:
                pass
            StateManager.clear(user_id)
            return

        # عدد التحذيرات
        if state == UserState.WAIT_WARN_COUNT:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get(f'sec_chat_{user_id}')
                if chat_id_sec and 1 <= val <= 10:
                    await DB.execute("UPDATE group_security SET max_warnings=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, "✅ تم")
            except:
                pass
            StateManager.clear(user_id)
            return

        # الدعم
        if state == UserState.SUPPORT_MODE:
            content = msg.text or msg.caption or ""
            ticket_num = await DB.create_ticket(user_id, update.effective_user.username or "", content)
            await safe_send(context.bot, user_id, f"✅ تذكرة #{ticket_num}")
            StateManager.clear(user_id)
            return

        await CommandHandlers.start(update, context)

    @staticmethod
    async def handle_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        chat = update.effective_chat
        if not chat or chat.type not in ['group', 'supergroup']:
            return
        chat_id = chat.id
        user_id = update.effective_user.id
        text = update.message.text or ""

        if update.effective_user.is_bot:
            return

        locked = await DB.fetchone("SELECT locked FROM chat_locks WHERE chat_id=?", (chat_id,))
        if locked and locked[0] == 1:
            try:
                await update.message.delete()
            except:
                pass
            return

        settings = await DB.get_security_settings(chat_id)

        if settings.get('delete_links', False) and TextUtils.contains_link(text):
            try:
                await update.message.delete()
            except:
                pass
            return

        if settings.get('mentions', False) and TextUtils.contains_mention(text):
            try:
                await update.message.delete()
            except:
                pass
            return

        if settings.get('delete_banned_words', False):
            banned_words = await DB.get_banned_words(chat_id)
            for word in banned_words:
                if word in text.lower():
                    try:
                        await update.message.delete()
                    except:
                        pass
                    return

        media_checks = {
            'delete_videos': 'video', 'delete_audio': 'audio', 'delete_animation': 'animation',
            'delete_voice': 'voice', 'delete_video_note': 'video_note', 'delete_stickers': 'sticker',
            'delete_documents': 'document', 'delete_forwarded': 'forward_from',
            'delete_polls': 'poll', 'delete_games': 'game'
        }
        for setting, media_type in media_checks.items():
            if settings.get(setting, False):
                if hasattr(update.message, media_type) and getattr(update.message, media_type) is not None:
                    try:
                        await update.message.delete()
                    except:
                        pass
                    return

        max_len = settings.get('max_message_length', 0)
        if max_len and len(text) > max_len:
            try:
                await update.message.delete()
            except:
                pass
            return

        if settings.get('antiflood_enabled', False):
            row = await DB.fetchone("SELECT message_time FROM user_messages WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            if row:
                last_time = TimeUtils.safe_parse_iso(row[0])
                if last_time and (TimeUtils.utc_now() - last_time).total_seconds() < settings.get('antiflood_seconds', 10):
                    try:
                        await update.message.delete()
                    except:
                        pass
                    return
            await DB.execute("INSERT OR REPLACE INTO user_messages VALUES (?,?,?)", (user_id, chat_id, TimeUtils.utc_iso()))

        if settings.get('night_mode_enabled', False):
            now = TimeUtils.mecca_now()
            start = datetime.strptime(settings.get('night_mode_start', '23:00'), '%H:%M').time()
            end = datetime.strptime(settings.get('night_mode_end', '06:00'), '%H:%M').time()
            current = now.time()
            is_night = (start <= current <= end) if start <= end else (current >= start or current <= end)
            if is_night:
                try:
                    await update.message.delete()
                except:
                    pass
                return

        ars = await DB.get_auto_reply_settings(chat_id)
        if ars.get('enabled', False):
            reply = get_reply_from_file(text.lower().strip())
            if not reply:
                reply_data = await DB.get_auto_reply(text.lower(), chat_id)
                if reply_data:
                    reply = reply_data.get('reply')
            if reply:
                try:
                    await update.message.reply_text(reply)
                except:
                    pass

        if settings.get('welcome_enabled', False) and update.message.new_chat_members:
            for member in update.message.new_chat_members:
                if member.id != context.bot.id:
                    welcome_text = settings.get('welcome_text', "مرحباً {user} 🤍")
                    await context.bot.send_message(chat_id, welcome_text.format(user=member.full_name))

        if settings.get('goodbye_enabled', False) and update.message.left_chat_member:
            member = update.message.left_chat_member
            if member.id != context.bot.id:
                goodbye_text = settings.get('goodbye_text', "وداعاً {user} 👋")
                await context.bot.send_message(chat_id, goodbye_text.format(user=member.full_name))

        if settings.get('slow_mode', False):
            try:
                await context.bot.set_chat_slow_mode(chat_id, settings.get('slow_mode_seconds', 5))
            except:
                pass

    @staticmethod
    async def handle_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        settings = await DB.get_security_settings(chat_id)

        if settings.get('delete_service', False):
            try:
                await update.message.delete()
            except:
                pass

        if settings.get('welcome_enabled', False) and update.message.new_chat_members:
            for member in update.message.new_chat_members:
                if member.id != context.bot.id:
                    welcome_text = settings.get('welcome_text', "مرحباً {user} 🤍")
                    await context.bot.send_message(chat_id, welcome_text.format(user=member.full_name))

        if settings.get('goodbye_enabled', False) and update.message.left_chat_member:
            member = update.message.left_chat_member
            if member.id != context.bot.id:
                goodbye_text = settings.get('goodbye_text', "وداعاً {user} 👋")
                await context.bot.send_message(chat_id, goodbye_text.format(user=member.full_name))

    @staticmethod
    async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

