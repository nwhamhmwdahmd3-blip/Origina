#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers.py - جميع معالجات البوت
================================
- CommandHandlers: الأوامر
- CallbackHandlers: الأزرار
- MessageHandlers: الرسائل
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

        args = context.args
        if args and args[0].startswith('ref_'):
            ref_code = args[0][4:]
            referrer = await DB.get_user_by_referral_code(ref_code)
            if referrer and referrer != user_id and not await DB.is_user_banned(referrer):
                existing = await DB.fetchone("SELECT 1 FROM referrals WHERE referred_id=?", (user_id,))
                if not existing:
                    if await DB.add_referral(referrer, user_id):
                        reward = await DB.claim_referral_reward(referrer)
                        await safe_send(update.effective_chat.bot, referrer,
                                        f"🎁 تمت إحالة `{user_id}` (+{reward} يوم)")

        force_ch = await DB.get_force_subscribe_channel()
        if force_ch and user_id != CONFIG.PRIMARY_OWNER_ID:
            try:
                chat = await context.bot.get_chat(f"@{force_ch}")
                member = await context.bot.get_chat_member(chat.id, user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("📢 اشترك", url=f"https://t.me/{force_ch}"),
                         InlineKeyboardButton("✅ تحقق", callback_data=CB.CHECK_SUB)]
                    ])
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
                ch_display = f"{ch_info['channel_name']}"

        groups = len(await DB.get_user_groups(user_id))
        has_sub = await DB.has_active_subscription(user_id)
        sub_text = "✅ مفعل" if has_sub else "❌ غير مفعل"
        auto = await DB.get_auto_publish_status(user_id)
        auto_text = "مفعل" if auto else "معطل"
        recycle = await DB.get_auto_recycle_status(user_id)
        recycle_text = "مفعل" if recycle else "معطل"

        kb_rows = KeyboardFactory.get_menu("main_menu")
        keyboard = []

        for row in kb_rows:
            btn_row = []
            for item in row:
                if item == "admin_panel_btn":
                    if CONFIG.is_developer(user_id):
                        text_btn = KeyboardFactory.get_text("admin_panel_btn")
                        btn_row.append(InlineKeyboardButton(text_btn, callback_data=CB.ADMIN))
                else:
                    text_btn = KeyboardFactory.get_text(item)
                    if item.endswith("_url"):
                        url = f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup"
                        btn_row.append(InlineKeyboardButton(text_btn, url=url))
                    else:
                        btn_row.append(InlineKeyboardButton(text_btn, callback_data=item))
            if btn_row:
                keyboard.append(btn_row)

        if CONFIG.is_developer(user_id):
            keyboard.append([InlineKeyboardButton("👑 لوحة الأدمن", callback_data=CB.ADMIN)])

        kb = InlineKeyboardMarkup(keyboard)

        title = await get_text(lang, 'main_menu',
                               user_id=user_id, groups=groups,
                               sub=sub_text, channel=ch_display,
                               pending=cnt, auto=auto_text,
                               bot_name=CONFIG.BOT_NAME)
        title += f"\n♻️ إعادة التدوير: {recycle_text}"

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
        kb = KeyboardFactory.build("plans")
        await safe_send(context.bot, user_id, await get_text(lang, 'plan_selector'), reply_markup=kb)

    @staticmethod
    async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        kb = KeyboardFactory.build("support")
        await safe_send(context.bot, user_id, await get_text(lang, 'send_support_message'), reply_markup=kb)

    @staticmethod
    async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = f"""
👨‍💻 **معلومات المطور**

📌 المعرف: `{CONFIG.PRIMARY_OWNER_ID}`
👤 البوت: {CONFIG.BOT_NAME}
🔗 المعرف: @{CONFIG.BOT_USERNAME}

📞 **للتواصل:** @RelaxMgr

━━━━━━━━━━━━━━━━━━━━

📚 **شرح البوت:**

🆓 **مجاني:**
• حماية المجموعات
• الردود التلقائية
• المسابقات
• الترحيب والوداع

💎 **مدفوع:**
• إدارة القنوات
• النشر التلقائي
• إعادة التدوير
"""
        await safe_send(context.bot, update.effective_user.id, text)

    @staticmethod
    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            await safe_send(context.bot, user_id, "❌ للمطورين فقط")
            return
        stats = await DB.get_user_stats()
        await safe_send(context.bot, user_id,
                        f"👥 المستخدمين: {stats['users']}\n⛔ المحظورين: {stats['banned']}")

    @staticmethod
    async def security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ ليس لديك صلاحية")
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
            await safe_send(context.bot, user_id, "❌ ليس لديك صلاحية")
            return
        kb = KeyboardFactory.build("panel", chat_id)
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
                         (chat_id, TimeUtils.utc_iso(), user_id))
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
        kb = KeyboardFactory.build("contests")
        await safe_send(context.bot, user_id, text, reply_markup=kb)

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
        buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)])
        kb = InlineKeyboardMarkup(buttons)
        await safe_send(context.bot, user_id, f"🌐 اختر اللغة:\n\nالحالية: {lang}", reply_markup=kb)

    @staticmethod
    async def replies_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await safe_send(context.bot, update.effective_user.id, "📚 الردود التلقائية تعمل!")

    @staticmethod
    async def syncgroup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """تفعيل المجموعة مع التسجيل التلقائي للمالك والمشرفين"""
        if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
            await safe_send(context.bot, update.effective_user.id, "❌ هذا الأمر للمجموعات فقط")
            return

        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "بدون اسم"
        user_id = update.effective_user.id

        if user_id < 0:
            await safe_send(context.bot, chat_id, "❌ البوتات لا تستطيع")
            return

        try:
            all_admins = await context.bot.get_chat_administrators(chat_id)
        except Exception as e:
            await safe_send(context.bot, user_id, f"❌ فشل جلب المشرفين: {str(e)[:100]}")
            return

        creator_id = None
        for admin in all_admins:
            if admin.status == 'creator' and not admin.user.is_bot:
                creator_id = admin.user.id
                break

        is_admin = False
        is_anonymous = False

        for admin in all_admins:
            if admin.user.id == user_id:
                is_admin = True
                is_anonymous = getattr(admin, 'is_anonymous', False)
                break

        if not is_admin:
            await safe_send(
                context.bot,
                user_id,
                "❌ **أنت لست مشرفاً في هذه المجموعة!**\n\n"
                "فقط المشرفون يمكنهم تفعيل البوت."
            )
            return

        await DB.register_group(chat_id, chat_name, creator_id or user_id, update.effective_chat.username)
        bot_perms = await check_bot_permissions(context.bot, chat_id)

        if not bot_perms.get('can_act', False):
            await safe_send(
                context.bot,
                user_id,
                "⚠️ **البوت ليس مشرفاً!**\n\n"
                "اجعل البوت مشرفاً ثم أعد `/syncgroup`"
            )
            return

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

        admin_ids = [a.user.id for a in all_admins if a.user and not a.user.is_bot]
        admin_count = await DB.sync_group_admins(chat_id, admin_ids)

        msg = f"✅ **تم تفعيل المجموعة!**\n\n"
        msg += f"📌 {chat_name}\n"
        msg += f"🆔 `{chat_id}`\n"
        if creator_id:
            msg += f"👑 المالك: `{creator_id}`\n"
        msg += f"{'👻 مخفي' if is_anonymous else '👤 مشرف'}: `{user_id}`\n"
        msg += f"👥 {admin_count} مشرف\n\n"
        msg += f"🔐 /security | 🛠️ /panel"

        await safe_send(context.bot, user_id, msg)
        await safe_send(context.bot, chat_id, "🤖 **تم تفعيل البوت!**")

        if creator_id and creator_id != user_id:
            try:
                await safe_send(context.bot, creator_id, msg)
            except:
                pass

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
            except:
                pass

    @staticmethod
    async def _moderation_command(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ ليس لديك صلاحية")
            return

        args = context.args
        if not args:
            await safe_send(context.bot, user_id, f"📝 /{action} معرف_المستخدم")
            return

        try:
            target = int(args[0])
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            return

        if await is_authorized_in_group(context.bot, chat_id, target):
            await safe_send(context.bot, user_id, "❌ لا يمكن معاملة مشرف")
            return

        reason = " ".join(args[1:]) if len(args) > 1 else ""

        if action == 'unban':
            try:
                await context.bot.unban_chat_member(chat_id, target)
                await safe_send(context.bot, user_id, "✅ تم إلغاء الحظر")
            except:
                pass
            return

        success, msg = await apply_penalty(context.bot, chat_id, target, action, 60, reason, user_id)
        await safe_send(context.bot, user_id, msg)


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

        try:
            if data in [CB.MAIN, CB.BACK]:
                await query.answer()
                await CommandHandlers.start(update, context)
                return

            if data == CB.CANCEL:
                StateManager.clear(user_id)
                await query.answer("❌ تم الإلغاء")
                return

            if data == CB.HELP:
                await query.answer()
                await CommandHandlers.help_command(update, context)
                return

            if data == CB.TRIAL:
                await query.answer()
                if await DB.has_used_trial(user_id):
                    await query.edit_message_text("❌ استخدمت التجربة مسبقاً")
                    return
                days = await DB.activate_trial(user_id)
                await query.edit_message_text(f"🎁 تم تفعيل {days} يوم!")
                return

            if data == CB.DEVELOPER:
                await query.answer()
                await CommandHandlers.developer(update, context)
                return

            if data == CB.SUBSCRIBE:
                await query.answer()
                await CommandHandlers.subscribe(update, context)
                return

            if data == CB.SUPPORT:
                await query.answer()
                await CommandHandlers.support(update, context)
                return

            if data == CB.LANGUAGE:
                await query.answer()
                await CommandHandlers.language(update, context)
                return

            if data == CB.CHECK_SUB:
                await query.answer()
                await CommandHandlers.start(update, context)
                return

            if data == CB.SETTINGS:
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings")
                await query.edit_message_text(
                    f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}",
                    reply_markup=kb
                )
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
                await query.edit_message_text("💎 اختر الباقة:", reply_markup=kb)
                return

            if data.startswith("buy_sub_"):
                days = int(data.split("_")[-1])
                plan_names = {1: "يوم", 7: "أسبوع", 30: "شهر", 90: "3 أشهر"}
                plan_name = plan_names.get(days)
                if not plan_name:
                    await query.answer("❌ باقة غير موجودة", show_alert=True)
                    return
                plan = await DB.get_plan_by_name(plan_name)
                if not plan:
                    await query.answer("❌ باقة غير موجودة", show_alert=True)
                    return

                invoice_number = await DB.create_invoice(user_id, plan['id'], plan['price'])
                if not invoice_number:
                    await query.answer("❌ فشل الدفع", show_alert=True)
                    return

                try:
                    await context.bot.send_invoice(
                        chat_id=user_id,
                        title=f"💎 {plan['name']}",
                        description=plan['description'],
                        payload=json.dumps({'plan_id': plan['id'], 'invoice': invoice_number}),
                        provider_token="",
                        currency="XTR",
                        prices=[LabeledPrice(plan['name'], plan['price'])]
                    )
                    await query.message.delete()
                except Exception as e:
                    await query.answer(f"❌ {str(e)[:50]}", show_alert=True)
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
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("➕ إضافة قناة", callback_data=CB.CH_ADD)],
                        [InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]
                    ])
                    await query.edit_message_text("📭 لا توجد قنوات!\n\nاضغط للإضافة:", reply_markup=kb)
                    return
                
                text = "📡 **قنواتي**\n\n"
                kb = []
                for ch in channels:
                    st = "✅" if not ch['banned'] else "🚫"
                    text += f"{st} {ch['channel_name']} (`{ch['channel_id']}`)\n"
                    if not ch['banned']:
                        kb.append([InlineKeyboardButton(
                            f"📌 {ch['channel_name'][:20]}",
                            callback_data=f"{CB.CH_SEL}{ch['id']}"
                        )])
                
                kb.append([InlineKeyboardButton("➕ إضافة", callback_data=CB.CH_ADD)])
                kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)])
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
                target = min(15, CONFIG.MAX_UNPUBLISHED_POSTS)
                context.user_data[f"session_{user_id}"] = []
                context.user_data[f"session_target_{user_id}"] = target
                StateManager.set(user_id, UserState.ADDING_POSTS)
                await query.edit_message_text(f"📥 أرسل {target} منشور:")
                return

            if data == CB.POST_PUB:
                if not await DB.has_active_subscription(user_id):
                    await query.answer("❌ انتهى اشتراكك!", show_alert=True)
                    return
                active = await DB.get_active_channel(user_id)
                if not active:
                    await query.edit_message_text("❌ لا توجد قناة")
                    return
                post = await DB.get_next_post(active)
                if not post:
                    await query.edit_message_text("📭 لا توجد منشورات")
                    return
                ch_info = await DB.get_channel_info(active)
                if not ch_info:
                    return
                try:
                    if post['media_type'] == 'photo' and post['media_file_id']:
                        await context.bot.send_photo(ch_info['channel_id'], post['media_file_id'],
                                                     caption=post['text'][:1024] if post['text'] else None)
                    elif post['media_type'] == 'video' and post['media_file_id']:
                        await context.bot.send_video(ch_info['channel_id'], post['media_file_id'],
                                                     caption=post['text'][:1024] if post['text'] else None)
                    else:
                        await context.bot.send_message(ch_info['channel_id'],
                                                       post['text'][:4096] if post['text'] else ".")
                    await DB.mark_post_published(post['id'])
                    await query.edit_message_text("✅ تم النشر!")
                except Exception as e:
                    await DB.increment_post_fail(post['id'])
                    await query.edit_message_text(f"❌ فشل: {str(e)[:100]}")
                return

            if data == CB.POST_LIST:
                active = await DB.get_active_channel(user_id)
                if not active:
                    await query.edit_message_text("❌ لا توجد قناة")
                    return
                posts = await DB.get_user_posts(active, 10)
                if not posts:
                    await query.edit_message_text("📭 لا توجد منشورات")
                    return
                text = "📋 **منشوراتي**\n\n"
                for p in posts:
                    short = (p['text'] or "بدون نص")[:30]
                    text += f"🆔 {p['id']}: {short}...\n"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data == CB.POST_REC:
                active = await DB.get_active_channel(user_id)
                if active:
                    count = await DB.reset_posts(active)
                    await query.edit_message_text(f"♻️ تم إعادة {count} منشور!")
                return

            if data == CB.PUB_ALL:
                channels = await DB.get_user_channels(user_id)
                tasks = []
                for ch in channels:
                    post = await DB.get_next_post(ch['id'])
                    if post:
                        ch_info = await DB.get_channel_info(ch['id'])
                        if ch_info:
                            tasks.append(CallbackHandlers._publish_single(
                                context.bot, ch['id'], ch_info['channel_id'], post))
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    await query.edit_message_text("✅ تم النشر!")
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
                    st = "✅" if not banned else "⛔"
                    text += f"{st} {name}\n"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data == CB.ADMIN:
                if CONFIG.is_developer(user_id):
                    kb = KeyboardFactory.build("admin_panel")
                    await query.edit_message_text("👑 لوحة الأدمن", reply_markup=kb)
                else:
                    await query.answer("❌ لا صلاحية", show_alert=True)
                return

            # ✅ أزرار الأمان
            if data.startswith("sec_"):
                await CallbackHandlers._handle_security_callback(update, context, query, user_id, lang)
                return

            # ✅ أزرار الأدمن
            if data.startswith("admin_"):
                if CONFIG.is_developer(user_id):
                    await CallbackHandlers._handle_admin_callback(update, context, query, user_id, lang)
                return

            # ✅ أزرار الردود التلقائية
            if data.startswith("auto_reply_"):
                await CallbackHandlers._handle_auto_reply_callback(update, context, query, user_id, lang)
                return

            await query.answer("⚠️ غير متوفر", show_alert=True)

        except Exception as e:
            logger.error(f"Callback error: {e}", exc_info=True)
            try:
                await query.answer("❌ خطأ", show_alert=True)
            except:
                pass

    # ========== دوال مساعدة ==========

    @staticmethod
    async def _handle_security_callback(update, context, query, user_id, lang):
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
            await query.answer("❌ لا صلاحية", show_alert=True)
            return

        field_map = {
            "links": "delete_links", "mentions": "mentions", "slow": "slow_mode",
            "video": "delete_videos", "audio": "delete_audio", "anim": "delete_animation",
            "service": "delete_service", "doc": "delete_documents", "sticker": "delete_stickers",
            "forward": "delete_forwarded", "poll": "delete_polls", "game": "delete_games",
            "voice": "delete_voice", "videonote": "delete_video_note",
            "welcome": "welcome_enabled", "goodbye": "goodbye_enabled",
            "flood": "antiflood_enabled", "night": "night_mode_enabled",
            "auto_approve": "auto_approve_join", "auto_reject": "auto_reject_join"
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
            for f in ['delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
                      'delete_documents', 'delete_stickers', 'delete_forwarded', 'delete_polls',
                      'delete_games', 'delete_voice', 'delete_video_note']:
                await DB.execute(f"UPDATE group_security SET {f}=1 WHERE chat_id=?", (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = await KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id)
            await query.edit_message_text(text, reply_markup=kb)
            return

        if action == "disable_all":
            for f in ['delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
                      'delete_documents', 'delete_stickers', 'delete_forwarded', 'delete_polls',
                      'delete_games', 'delete_voice', 'delete_video_note']:
                await DB.execute(f"UPDATE group_security SET {f}=0 WHERE chat_id=?", (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = await KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id)
            await query.edit_message_text(text, reply_markup=kb)
            return

        await query.answer()

    @staticmethod
    async def _handle_admin_callback(update, context, query, user_id, lang):
        data = query.data

        if data == CB.ADMIN_STATS:
            stats = await DB.get_user_stats()
            await query.edit_message_text(f"👥 {stats['users']} مستخدم\n⛔ {stats['banned']} محظور")
            return

        if data == CB.ADMIN_BROADCAST:
            StateManager.set(user_id, UserState.WAIT_BROADCAST)
            await query.edit_message_text("📨 أرسل الرسالة:")
            return

        if data == CB.ADMIN_BACKUP:
            try:
                backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2(PATHS.DB, backup_file)
                await safe_send(context.bot, user_id, f"✅ نسخة: {backup_file.name}")
            except:
                pass
            return

        await query.answer()

    @staticmethod
    async def _handle_auto_reply_callback(update, context, query, user_id, lang):
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
            await query.answer("❌ لا صلاحية", show_alert=True)
            return

        if action == "toggle":
            settings = await DB.get_auto_reply_settings(chat_id)
            await DB.update_auto_reply_settings(chat_id, enabled=not settings.get('enabled', False))
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

        await query.answer()

    @staticmethod
    async def _publish_single(bot, ch_db_id, ch_tele, post):
        try:
            if post['media_type'] == 'photo' and post['media_file_id']:
                await bot.send_photo(ch_tele, post['media_file_id'],
                                     caption=post['text'][:1024] if post['text'] else None)
            elif post['media_type'] == 'video' and post['media_file_id']:
                await bot.send_video(ch_tele, post['media_file_id'],
                                     caption=post['text'][:1024] if post['text'] else None)
            else:
                await bot.send_message(ch_tele, post['text'][:4096] if post['text'] else ".")
            await DB.mark_post_published(post['id'])
        except:
            await DB.increment_post_fail(post['id'])


# =====================================================================
# 3. معالج الرسائل
# =====================================================================

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

        if state == UserState.WAIT_CHANNEL:
            if not await DB.has_active_subscription(user_id):
                await safe_send(context.bot, user_id, "❌ انتهى اشتراكك!")
                StateManager.clear(user_id)
                return

            channel_input = text.strip()
            try:
                chat = await context.bot.get_chat(channel_input)
                if chat.type != 'channel':
                    await safe_send(context.bot, user_id, "❌ ليس قناة!")
                    StateManager.clear(user_id)
                    return
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status != 'administrator':
                    await safe_send(context.bot, user_id, "❌ البوت ليس مشرفاً في القناة!")
                    StateManager.clear(user_id)
                    return
                result = await DB.add_channel(user_id, chat.id, chat.title or "قناة")
                if result:
                    await DB.set_active_channel(user_id, result)
                    await safe_send(context.bot, user_id, f"✅ تمت إضافة {chat.title}!")
                else:
                    await safe_send(context.bot, user_id, "⚠️ القناة موجودة مسبقاً")
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ خطأ: {str(e)[:100]}")
            
            StateManager.clear(user_id)
            await CommandHandlers.start(update, context)
            return

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
            elif msg.text:
                media_type = 'text'

            content = msg.caption or "" if media_type != 'text' else text
            session.append((content, media_type, media_file_id))
            context.user_data[f"session_{user_id}"] = session

            if len(session) >= target:
                active = await DB.get_active_channel(user_id)
                if active:
                    await DB.add_posts(active, session)
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "✅ تم حفظ المنشورات!")
            else:
                await safe_send(context.bot, user_id, f"✅ {len(session)}/{target}")
            return

        if state == UserState.WAIT_BROADCAST:
            context.user_data['broadcast_text'] = text
            StateManager.clear(user_id)
            users = await DB.get_all_users()
            sent = 0
            for uid, banned in users:
                if banned:
                    continue
                try:
                    await safe_send(context.bot, uid, text)
                    sent += 1
                except:
                    pass
            await safe_send(context.bot, user_id, f"✅ تم الإرسال إلى {sent}")
            return

        if state == UserState.WAIT_AUTO_KEY:
            context.user_data['auto_key'] = text.strip().lower()
            StateManager.set(user_id, UserState.WAIT_AUTO_REPLY)
            await safe_send(context.bot, user_id, "📝 أرسل الرد:")
            return

        if state == UserState.WAIT_AUTO_REPLY:
            chat_id_auto = context.user_data.get('auto_chat')
            keyword = context.user_data.get('auto_key')
            if chat_id_auto is not None and keyword:
                await DB.add_auto_reply(chat_id_auto, keyword, text)
                await safe_send(context.bot, user_id, f"✅ تمت إضافة: {keyword}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_AUTO_DEL:
            chat_id_auto = context.user_data.get('auto_chat')
            if chat_id_auto is not None:
                await DB.remove_auto_reply(chat_id_auto, text.strip().lower())
                await safe_send(context.bot, user_id, "✅ تم الحذف")
            StateManager.clear(user_id)
            return

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
                if member.id == context.bot.id:
                    continue
                welcome_text = settings.get('welcome_text', "مرحباً {user} في {chat} 🤍")
                text = welcome_text.format(
                    user=member.full_name or "العضو",
                    chat=update.effective_chat.title or "المجموعة"
                )
                await context.bot.send_message(chat_id, text)

        if settings.get('goodbye_enabled', False) and update.message.left_chat_member:
            member = update.message.left_chat_member
            if member.id == context.bot.id:
                return
            goodbye_text = settings.get('goodbye_text', "وداعاً {user} 👋")
            text = goodbye_text.format(
                user=member.full_name or "العضو",
                chat=update.effective_chat.title or "المجموعة"
            )
            await context.bot.send_message(chat_id, text)

    @staticmethod
    async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        join_request = update.chat_join_request
        chat_id = update.effective_chat.id
        user_id = join_request.from_user.id
        
        settings = await DB.get_security_settings(chat_id)
        
        if settings.get('auto_approve_join', False):
            try:
                await join_request.approve()
                if settings.get('welcome_enabled', False):
                    welcome_text = settings.get('welcome_text', "مرحباً {user} في {chat} 🤍")
                    text = welcome_text.format(
                        user=join_request.from_user.full_name or "العضو",
                        chat=update.effective_chat.title or "المجموعة"
                    )
                    await context.bot.send_message(chat_id, text)
            except:
                pass
            return
        
        if settings.get('auto_reject_join', False):
            try:
                await join_request.decline()
            except:
                pass
