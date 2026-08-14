#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers.py - جميع معالجات البوت (الأوامر، الكولباك، الرسائل)
===============================================================
يحتوي على:
- CommandHandlers: معالجة الأوامر (/start, /help, ...)
- CallbackHandlers: معالجة ضغطات الأزرار
- MessageHandlers: معالجة الرسائل (خاصة ومجموعات)
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
    fetch_json_from_url, _increment_usage_async, get_ram_usage
)

logger = logging.getLogger(__name__)

# =====================================================================
# 1. معالج الأوامر - CommandHandlers (كامل)
# =====================================================================

class CommandHandlers:
    """جميع معالجات الأوامر"""

    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """بدء البوت وعرض القائمة الرئيسية"""
        user_id = update.effective_user.id
        username = update.effective_user.username or ""
        first_name = update.effective_user.first_name or ""
        await DB.register_user(user_id, username, first_name)

        # معالجة روابط الإحالة
        args = context.args
        if args and args[0].startswith('ref_'):
            ref_code = args[0][4:]
            referrer = await DB.get_user_by_referral_code(ref_code)
            if referrer and referrer != user_id:
                if await DB.add_referral(referrer, user_id):
                    reward = await DB.claim_referral_reward(referrer)
                    await safe_send(update.effective_chat.bot, referrer,
                                    f"🎁 تمت إحالة `{user_id}` (+{reward} يوم)")

        # التحقق من الاشتراك الإجباري
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
        channels = await DB.get_user_channels(user_id)
        active = await DB.get_active_channel(user_id)
        cnt = 0
        ch_display = "لا توجد قنوات"
        if active:
            cnt = await DB.get_unpublished_posts_count(active)
            ch_info = await DB.get_channel_info(active)
            if ch_info:
                ch_display = f"{ch_info['channel_name']} ({ch_info['channel_id']})"

        groups = len(await DB.get_user_groups(user_id))
        has_sub = await DB.has_active_subscription(user_id)
        sub_text = "✅ مفعل" if has_sub else "❌ غير مفعل"
        auto = await DB.get_auto_publish_status(user_id)
        auto_text = "مفعل" if auto else "معطل"

        title = await get_text(lang, 'main_menu',
                               user_id=user_id, groups=groups,
                               sub=sub_text, channel=ch_display,
                               pending=cnt, auto=auto_text,
                               bot_name=CONFIG.BOT_NAME)

        kb = KeyboardFactory.build("main_menu")
        await safe_send(context.bot, user_id, title, reply_markup=kb)

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """عرض المساعدة"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        await safe_send(context.bot, user_id, await get_text(lang, 'help_text'))

    @staticmethod
    async def trial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """تفعيل النسخة التجريبية"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        if await DB.has_used_trial(user_id):
            await safe_send(context.bot, user_id, await get_text(lang, 'trial_used'))
            return
        days = await DB.activate_trial(user_id)
        await safe_send(context.bot, user_id, await get_text(lang, 'trial_activated', days=days))

    @staticmethod
    async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """عرض باقات الاشتراك"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        kb = KeyboardFactory.build("plans")
        await safe_send(context.bot, user_id, await get_text(lang, 'plan_selector'), reply_markup=kb)

    @staticmethod
    async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """فتح تذكرة دعم"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        kb = KeyboardFactory.build("support")
        await safe_send(context.bot, user_id, await get_text(lang, 'send_support_message'), reply_markup=kb)

    @staticmethod
    async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """عرض معلومات المطور"""
        user_id = update.effective_user.id
        text = f"""
👨‍💻 **معلومات المطور**

📌 المعرف الأساسي: `{CONFIG.PRIMARY_OWNER_ID}`
👤 اسم البوت: {CONFIG.BOT_NAME}
🔗 المعرف: @{CONFIG.BOT_USERNAME}

🛠️ **المطورون المسجلون:**
"""
        for dev_id in CONFIG.DEVELOPER_IDS:
            text += f"• `{dev_id}`\n"
        text += f"\n🔐 هل أنت مطور؟ {'✅ نعم' if CONFIG.is_developer(user_id) else '❌ لا'}"
        await safe_send(context.bot, user_id, text)

    @staticmethod
    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """عرض إحصائيات البوت (للمطورين فقط)"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            await safe_send(context.bot, user_id, "❌ هذا الأمر للمطورين فقط")
            return
        lang = await DB.get_user_language(user_id)
        stats = await DB.get_user_stats()
        await safe_send(context.bot, user_id,
                        await get_text(lang, 'admin_stats',
                                       users=stats['users'],
                                       banned=stats['banned'],
                                       posts=0, groups=0, channels=0))

    @staticmethod
    async def security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """عرض إعدادات الأمان للمجموعة"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id,
                            await get_text(await DB.get_user_language(user_id), 'not_authorized'))
            return
        lang = await DB.get_user_language(user_id)
        settings = await DB.get_security_settings(chat_id)
        text = await KeyboardFactory._format_security_text(settings)
        kb = KeyboardFactory.build("security", chat_id)
        await safe_send(context.bot, user_id, text, reply_markup=kb)

    @staticmethod
    async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """عرض لوحة تحكم المجموعة"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id,
                            await get_text(await DB.get_user_language(user_id), 'not_authorized'))
            return
        kb = KeyboardFactory.build("panel", chat_id)
        await safe_send(context.bot, user_id, "📋 لوحة تحكم المجموعة", reply_markup=kb)

    @staticmethod
    async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """قفل المجموعة"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id,
                            await get_text(await DB.get_user_language(user_id), 'not_authorized'))
            return
        await DB.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?,1,?,?)",
                         (chat_id, TimeUtils.utc_iso(), user_id))
        await safe_send(context.bot, user_id, "🔒 تم القفل")

    @staticmethod
    async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """فتح المجموعة"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id,
                            await get_text(await DB.get_user_language(user_id), 'not_authorized'))
            return
        await DB.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await safe_send(context.bot, user_id, "🔓 تم الفتح")

    @staticmethod
    async def contests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """عرض المسابقات"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        contests = await DB.get_active_contests(10)
        if not contests:
            await safe_send(context.bot, user_id, await get_text(lang, 'contest_no_active'))
            return
        text = "🏆 **المسابقات النشطة**\n\n"
        for c in contests:
            text += f"• **{c['title']}**\n"
            text += f"  📝 {c['participants']} مشارك\n"
            text += f"  🎁 الجائزة: {c['prize']}\n"
            text += f"  📅 ينتهي: {c['end_date'][:10]}\n\n"
        kb = KeyboardFactory.build("contests")
        await safe_send(context.bot, user_id, text, reply_markup=kb)

    @staticmethod
    async def language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """عرض قائمة اللغات"""
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
        buttons.append([InlineKeyboardButton(await get_text(lang, 'back'), callback_data=CB.BACK)])
        kb = InlineKeyboardMarkup(buttons)
        await safe_send(context.bot, user_id,
                        await get_text(lang, 'language_select', current=lang), reply_markup=kb)

    @staticmethod
    async def replies_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """عرض معلومات الردود التلقائية"""
        user_id = update.effective_user.id
        await safe_send(context.bot, user_id, "📚 **الردود التلقائية**\n\n✅ يتم تحميل الردود من قاعدة البيانات")

    @staticmethod
    async def syncgroup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """تفعيل المجموعة ومزامنة المشرفين"""
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
    async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """حظر مستخدم في المجموعة"""
        await CommandHandlers._moderation_command(update, context, "ban")

    @staticmethod
    async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """كتم مستخدم في المجموعة"""
        await CommandHandlers._moderation_command(update, context, "mute")

    @staticmethod
    async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """تحذير مستخدم في المجموعة"""
        await CommandHandlers._moderation_command(update, context, "warn")

    @staticmethod
    async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """طرد مستخدم من المجموعة"""
        await CommandHandlers._moderation_command(update, context, "kick")

    @staticmethod
    async def restrict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """تقييد مستخدم في المجموعة"""
        await CommandHandlers._moderation_command(update, context, "restrict")

    @staticmethod
    async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """إلغاء حظر مستخدم في المجموعة"""
        await CommandHandlers._moderation_command(update, context, "unban")

    @staticmethod
    async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """تثبيت رسالة في المجموعة"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id,
                            await get_text(await DB.get_user_language(user_id), 'not_authorized'))
            return
        if update.message.reply_to_message:
            try:
                await context.bot.pin_chat_message(chat_id, update.message.reply_to_message.message_id)
                await safe_send(context.bot, user_id, "📌 تم تثبيت الرسالة")
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ {str(e)[:100]}")
        else:
            await safe_send(context.bot, user_id, "❌ رد على رسالة لتثبيتها")

    @staticmethod
    async def _moderation_command(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
        """تنفيذ أوامر الإدارة (حظر، كتم، تحذير، ...)"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id,
                            await get_text(await DB.get_user_language(user_id), 'not_authorized'))
            return

        args = context.args
        if not args:
            await safe_send(context.bot, user_id, f"📝 /{action} معرف_المستخدم [سبب]")
            return

        try:
            target = int(args[0])
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            return

        # التحقق من أن المستهدف ليس مشرفاً
        if await is_authorized_in_group(context.bot, chat_id, target):
            await safe_send(context.bot, user_id,
                            await get_text(await DB.get_user_language(user_id), 'error_user_admin'))
            return

        reason = " ".join(args[1:]) if len(args) > 1 else ""
        duration = None

        if action == 'mute' and len(args) > 2 and args[1].isdigit():
            duration = int(args[1])
            reason = " ".join(args[2:]) if len(args) > 2 else ""

        if action == 'unban':
            try:
                await context.bot.unban_chat_member(chat_id, target)
                await safe_send(context.bot, user_id, f"✅ تم إلغاء حظر {target}")
                await DB.add_admin_log(chat_id, user_id, 'unban', target, reason)
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ {str(e)[:100]}")
            return

        success, msg = await apply_penalty(context.bot, chat_id, target, action, duration, reason, user_id)
        await safe_send(context.bot, user_id, msg)
        if success:
            await DB.add_admin_log(chat_id, user_id, action, target, reason)


# =====================================================================
# 2. معالج الكولباك - CallbackHandlers (كامل)
# =====================================================================

class CallbackHandlers:
    """جميع معالجات ضغطات الأزرار"""

    @staticmethod
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """المعالج الرئيسي للكولباك"""
        query = update.callback_query
        data = query.data
        if not data:
            return

        user_id = query.from_user.id
        lang = await DB.get_user_language(user_id)

        try:
            # ====================================================
            # الأزرار الأساسية
            # ====================================================
            if data == CB.MAIN or data == CB.BACK:
                await query.answer()
                await CommandHandlers.start(update, context)
                return

            if data == CB.CANCEL:
                await query.answer()
                StateManager.clear(user_id)
                await query.edit_message_text("❌ تم الإلغاء")
                await CommandHandlers.start(update, context)
                return

            if data == CB.HELP:
                await query.answer()
                await CommandHandlers.help_command(update, context)
                return

            if data == CB.TRIAL:
                await query.answer()
                await CommandHandlers.trial(update, context)
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

            # ====================================================
            # الإعدادات
            # ====================================================
            if data == CB.SETTINGS:
                await query.answer()
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings")
                await query.edit_message_text(await get_text(lang, 'settings_auto', status=auto), reply_markup=kb)
                return

            if data == CB.TOGGLE_AUTO:
                await query.answer()
                cur = await DB.get_auto_publish_status(user_id)
                await DB.set_auto_publish(user_id, not cur)
                await CallbackHandlers.handle(update, context)
                return

            # ====================================================
            # الباقات والاشتراك
            # ====================================================
            if data == CB.PLANS:
                await query.answer()
                kb = KeyboardFactory.build("plans")
                await query.edit_message_text(await get_text(lang, 'plan_selector'), reply_markup=kb)
                return

            if data.startswith(CB.BUY_SUB):
                days = int(data.split(":")[-1])
                plan_names = {1: "يوم", 7: "أسبوع", 30: "شهر", 90: "3 أشهر"}
                plan_name = plan_names.get(days)
                if not plan_name:
                    await query.answer(await get_text(lang, 'plan_not_found'), show_alert=True)
                    return
                plan = await DB.get_plan_by_name(plan_name)
                if not plan:
                    await query.answer(await get_text(lang, 'plan_not_found'), show_alert=True)
                    return

                # إنشاء فاتورة وإرسالها
                invoice_number = await DB.create_invoice(user_id, plan['id'], plan['price'])
                if not invoice_number:
                    await query.answer(await get_text(lang, 'payment_init_failed'), show_alert=True)
                    return

                try:
                    await context.bot.send_invoice(
                        chat_id=user_id,
                        title=await get_text(lang, 'buy_plan', plan=plan['name']),
                        description=await get_text(lang, 'plan_description',
                                                   description=plan['description'],
                                                   price=plan['price']),
                        payload=json.dumps({'plan_id': plan['id'], 'invoice': invoice_number}),
                        provider_token="",
                        currency="XTR",
                        prices=[LabeledPrice(f"{plan['name']} ({plan['duration_days']} يوم)", plan['price'])]
                    )
                    await query.message.delete()
                except Exception as e:
                    await query.answer(f"❌ {str(e)[:50]}", show_alert=True)
                return

            if data == CB.INVOICES:
                await query.answer()
                invoices = await DB.get_user_invoices(user_id, 10)
                if not invoices:
                    await query.edit_message_text(await get_text(lang, 'no_invoices'))
                    return
                text = await get_text(lang, 'invoice_list',
                                      invoices="\n".join([f"• #{inv['number']} - {inv['amount']} {inv['currency']} - {inv['status']}"
                                                          for inv in invoices]))
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(await get_text(lang, 'back'), callback_data=CB.BACK)]])
                await query.edit_message_text(text, reply_markup=kb)
                return

            # ====================================================
            # الإحالات
            # ====================================================
            if data == CB.REFERRAL:
                await query.answer()
                stats = await DB.get_referral_stats(user_id)
                code = await DB.get_referral_code(user_id)
                text = await get_text(lang, 'referral_header',
                                      link=f"https://t.me/{CONFIG.BOT_USERNAME}?start=ref_{code}",
                                      total=stats['total'],
                                      available=stats['available'])
                kb = KeyboardFactory.build("referral")
                await query.edit_message_text(text, reply_markup=kb)
                return

            if data == CB.REF_CLAIM:
                await query.answer()
                days = await DB.claim_referral_reward(user_id)
                await query.edit_message_text(await get_text(lang, 'referral_claimed', days=days) if days
                                              else await get_text(lang, 'no_referrals'))
                return

            if data == CB.REF_LIST:
                await query.answer()
                referrals = await DB.get_referrals_list(user_id)
                if not referrals:
                    await query.edit_message_text(await get_text(lang, 'no_referrals'))
                else:
                    text = await get_text(lang, 'referral_list',
                                          list="\n".join([f"• `{r}`" for r in referrals[:20]]))
                    await query.edit_message_text(text)
                return

            # ====================================================
            # التذكيرات
            # ====================================================
            if data == CB.REMINDER:
                await query.answer()
                settings = await DB.get_reminder_settings(user_id)
                sub = "✅" if settings.get('sub', False) else "❌"
                daily = "✅" if settings.get('daily', False) else "❌"
                weekly = "✅" if settings.get('weekly', False) else "❌"
                days = settings.get('days', 3)
                text = f"⏰ **إعدادات التذكيرات**\n\n🔔 تذكير الاشتراك: {sub}\n📊 يومي: {daily}\n📈 أسبوعي: {weekly}\n📅 عدد الأيام: {days}"
                kb = KeyboardFactory.build("reminder")
                await query.edit_message_text(text, reply_markup=kb)
                return

            if data == CB.REM_TOGGLE_SUB:
                settings = await DB.get_reminder_settings(user_id)
                await DB.update_reminder_settings(user_id, subscription_reminder=not settings.get('sub', False))
                await CallbackHandlers.handle(update, context)
                return

            if data == CB.REM_TOGGLE_DAILY:
                settings = await DB.get_reminder_settings(user_id)
                await DB.update_reminder_settings(user_id, daily_stats_reminder=not settings.get('daily', False))
                await CallbackHandlers.handle(update, context)
                return

            if data == CB.REM_TOGGLE_WEEKLY:
                settings = await DB.get_reminder_settings(user_id)
                await DB.update_reminder_settings(user_id, weekly_report=not settings.get('weekly', False))
                await CallbackHandlers.handle(update, context)
                return

            if data == CB.REM_SET_DAYS:
                StateManager.set(user_id, UserState.WAIT_REM_DAYS)
                await query.edit_message_text("📅 أرسل عدد الأيام قبل انتهاء الاشتراك (1-30):")
                return

            if data == CB.REM_SET_LANG:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🇸🇦 عربي", callback_data=f"{CB.REM_LANG}ar"),
                     InlineKeyboardButton("🇬🇧 English", callback_data=f"{CB.REM_LANG}en")],
                    [InlineKeyboardButton(await get_text(lang, 'back'), callback_data=CB.REMINDER)]
                ])
                await query.edit_message_text("🌐 اختر لغة الإشعارات:", reply_markup=kb)
                return

            if data.startswith(CB.REM_LANG):
                lang_set = data.split(":")[-1]
                await DB.update_reminder_settings(user_id, notification_lang=lang_set)
                await CallbackHandlers.handle(update, context)
                return

            # ====================================================
            # الترجمة
            # ====================================================
            if data == CB.TRANSLATION:
                await query.answer()
                current_lang = await DB.get_user_language(user_id)
                text = f"🌐 الترجمة: {current_lang}"
                kb = KeyboardFactory.build("translation")
                await query.edit_message_text(text, reply_markup=kb)
                return

            if data == CB.TRANS_OFF:
                await DB.set_user_language(user_id, 'off')
                await query.edit_message_text(await get_text(lang, 'translation_off'))
                return

            if data.startswith(CB.TRANS_SET):
                lang_set = data.split(":")[-1]
                await DB.set_user_language(user_id, lang_set)
                await query.edit_message_text(await get_text(lang, 'translation_set', lang=lang_set))
                return

            # ====================================================
            # المسابقات
            # ====================================================
            if data == CB.CONTESTS:
                await query.answer()
                await CommandHandlers.contests(update, context)
                return

            if data == CB.CONTEST_WINNERS:
                await query.answer()
                winners = await DB.get_contest_winners(10)
                if not winners:
                    await query.edit_message_text(await get_text(lang, 'no_contest_winners'))
                    return
                text = await get_text(lang, 'contest_winners',
                                      winners="\n".join([f"• {w['title']} → `{w['winner_id']}`" for w in winners]))
                await query.edit_message_text(text)
                return

            if data.startswith(CB.CONTEST_JOIN):
                await query.answer()
                cid = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
                context.user_data['contest_join'] = cid
                await safe_send(context.bot, user_id, "📝 أرسل إجابتك (أو /skip للتخطي):")
                try:
                    await query.message.delete()
                except:
                    pass
                return

            # ====================================================
            # الدعم
            # ====================================================
            if data == CB.SUPPORT_TICKET:
                await query.answer()
                StateManager.set(user_id, UserState.SUPPORT_MODE)
                await safe_send(context.bot, user_id, await get_text(lang, 'send_support_message'))
                try:
                    await query.message.delete()
                except:
                    pass
                return

            # ====================================================
            # القنوات
            # ====================================================
            if data == CB.CH_ADD:
                has_sub = await DB.has_active_subscription(user_id)
                has_trial = await DB.has_used_trial(user_id)
                if not has_sub and not has_trial:
                    await query.answer(await get_text(lang, 'subscription_expired'), show_alert=True)
                    return
                await query.answer()
                StateManager.set(user_id, UserState.WAIT_CHANNEL)
                await query.edit_message_text(await get_text(lang, 'enter_channel_id'))
                return

            if data == CB.CH_LIST:
                await query.answer()
                channels = await DB.get_user_channels(user_id)
                if not channels:
                    await query.edit_message_text(await get_text(lang, 'channels_empty'))
                    return
                text = "📡 **قنواتي**\n\n"
                for ch in channels:
                    st = "🚫" if ch['banned'] else "✅"
                    text += f"{st} {ch['channel_name']} (ID: {ch['id']})\n"
                kb = KeyboardFactory.build("main_menu")
                await query.edit_message_text(text, reply_markup=kb)
                return

            if data.startswith(CB.CH_DEL):
                ch_id = int(data.split(":")[-1])
                await DB.delete_channel(user_id, ch_id)
                await query.edit_message_text("✅ تم حذف القناة")
                await CallbackHandlers.handle(update, context)
                return

            if data.startswith(CB.CH_SEL):
                ch_id = int(data.split(":")[-1])
                await DB.set_active_channel(user_id, ch_id)
                await query.edit_message_text("✅ تم تحديد القناة النشطة")
                await CommandHandlers.start(update, context)
                return

            if data.startswith("ch_stats:"):
                ch_id = int(data.split(":")[-1])
                stats = await DB.get_channel_stats(ch_id)
                await query.edit_message_text(f"📊 **إحصائيات القناة**\n\n"
                                               f"📝 إجمالي المنشورات: {stats['total']}\n"
                                               f"✅ منشورة: {stats['published']}\n"
                                               f"⏳ غير منشورة: {stats['unpublished']}")
                return

            # ====================================================
            # المنشورات
            # ====================================================
            if data == CB.POST_ADD:
                await query.answer()
                active = await DB.get_active_channel(user_id)
                if not active:
                    await query.edit_message_text(await get_text(lang, 'no_active_channel'))
                    return
                unpub = await DB.get_unpublished_posts_count(active)
                if unpub >= CONFIG.MAX_UNPUBLISHED_POSTS:
                    await query.edit_message_text(await get_text(lang, 'max_posts_reached'))
                    return
                target = min(15, CONFIG.MAX_UNPUBLISHED_POSTS - unpub)
                context.user_data[f"session_{user_id}"] = []
                context.user_data[f"session_target_{user_id}"] = target
                StateManager.set(user_id, UserState.ADDING_POSTS)
                await query.edit_message_text(await get_text(lang, 'enter_posts', count=target))
                return

            if data == CB.POST_PUB:
                await query.answer()
                active = await DB.get_active_channel(user_id)
                if not active:
                    await query.edit_message_text(await get_text(lang, 'no_active_channel'))
                    return
                post = await DB.get_next_post(active)
                if not post:
                    await query.edit_message_text(await get_text(lang, 'posts_empty'))
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
                    await DB.update_last_publish(active)
                    await DB.update_next_publish(active)
                    await query.edit_message_text(await get_text(lang, 'publish_success'))
                except Exception as e:
                    await DB.increment_post_fail(post['id'])
                    await query.edit_message_text(await get_text(lang, 'publish_fail', error=str(e)[:100]))
                return

            if data == CB.POST_LIST:
                await query.answer()
                active = await DB.get_active_channel(user_id)
                if not active:
                    await query.edit_message_text(await get_text(lang, 'no_active_channel'))
                    return
                posts = await DB.get_user_posts(active, 15)
                if not posts:
                    await query.edit_message_text(await get_text(lang, 'posts_empty'))
                    return
                text = await get_text(lang, 'my_posts_title') + "\n"
                kb = []
                for p in posts[:10]:
                    short = (p['text'] or "بدون نص")[:50]
                    text += f"🆔 {p['id']}: {short}...\n"
                    kb.append([InlineKeyboardButton(f"🗑️ حذف #{p['id']}", callback_data=f"{CB.POST_DEL}{p['id']}_{active}")])
                kb.append([InlineKeyboardButton("🗑️ حذف الكل", callback_data=f"{CB.POST_CLEAR}{active}")])
                kb.append([InlineKeyboardButton(await get_text(lang, 'back'), callback_data=CB.BACK)])
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data == CB.POST_REC:
                await query.answer()
                active = await DB.get_active_channel(user_id)
                if active:
                    await DB.reset_posts(active)
                    await query.edit_message_text("♻️ تم إعادة تعيين جميع المنشورات")
                else:
                    await query.edit_message_text(await get_text(lang, 'no_active_channel'))
                return

            if data.startswith(CB.POST_DEL):
                parts = data.split(":")[-1].split("_")
                if len(parts) >= 2:
                    pid, active = int(parts[0]), int(parts[1])
                    await DB.delete_post(pid, user_id, active)
                    await CallbackHandlers.handle(update, context)
                return

            if data.startswith(CB.POST_CLEAR):
                active = int(data.split(":")[-1])
                await DB.execute("DELETE FROM posts WHERE channel_db_id=?", (active,))
                await query.edit_message_text("✅ تم حذف جميع المنشورات")
                return

            if data == CB.PUB_ALL:
                await query.answer()
                channels = await DB.get_user_channels(user_id)
                if not channels:
                    await query.edit_message_text("📭 لا توجد قنوات")
                    return
                tasks = []
                for ch in channels:
                    if ch['banned']:
                        continue
                    post = await DB.get_next_post(ch['id'])
                    if not post:
                        continue
                    ch_info = await DB.get_channel_info(ch['id'])
                    if ch_info:
                        tasks.append(CallbackHandlers._publish_single(context.bot, ch['id'],
                                                                      ch_info['channel_id'], post))
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    await query.edit_message_text(await get_text(lang, 'publish_success'))
                else:
                    await query.edit_message_text(await get_text(lang, 'no_posts'))
                return

            # ====================================================
            # الإحصائيات
            # ====================================================
            if data == CB.STATS_PEND or data == CB.STATS_FULL:
                await query.answer()
                u = await DB.get_user_unpublished_count(user_id)
                t = await DB.get_user_total_posts(user_id)
                ch = len(await DB.get_user_channels(user_id))
                g = len(await DB.get_user_groups(user_id))
                auto = "مفعل" if await DB.get_auto_publish_status(user_id) else "معطل"
                text = f"📊 **الإحصائيات**\n\n📝 منشورات: {t}\n⏳ غير منشورة: {u}\n📡 قنوات: {ch}\n👥 مجموعات: {g}\n⚙️ النشر التلقائي: {auto}"
                await query.edit_message_text(text)
                return

            # ====================================================
            # المجموعات
            # ====================================================
            if data == CB.GROUPS:
                await query.answer()
                groups = await DB.get_user_groups(user_id)
                if not groups:
                    text = await get_text(lang, 'groups_empty')
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton(await get_text(lang, 'add_group'),
                                                                     url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")]])
                    await query.edit_message_text(text, reply_markup=kb)
                    return
                text = "👥 **المجموعات**\n\n"
                kb = []
                for gid, name, username, banned in groups:
                    st = "⛔" if banned else "✅"
                    text += f"{st} {name} (ID: {gid})\n"
                    kb.append([InlineKeyboardButton(f"🔐 أمان {name[:15]}", callback_data=f"{CB.GRP_SET}{gid}")])
                kb.append([InlineKeyboardButton(await get_text(lang, 'back'), callback_data=CB.BACK)])
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data.startswith(CB.GRP_SET):
                chat_id = int(data.split(":")[-1])
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    await query.answer(await get_text(lang, 'not_authorized'), show_alert=True)
                    return
                settings = await DB.get_security_settings(chat_id)
                text = await KeyboardFactory._format_security_text(settings)
                kb = KeyboardFactory.build("security", chat_id)
                await query.edit_message_text(text, reply_markup=kb)
                return

            # ====================================================
            # الجدولة
            # ====================================================
            if data.startswith(CB.SCHEDULE):
                ch_id = int(data.split(":")[-1])
                s = await DB.get_schedule(ch_id)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏱️ دقائق", callback_data=f"{CB.SCHED_MIN}{ch_id}"),
                     InlineKeyboardButton("⏱️ ساعات", callback_data=f"{CB.SCHED_HOUR}{ch_id}")],
                    [InlineKeyboardButton("⏱️ أيام", callback_data=f"{CB.SCHED_DAY}{ch_id}"),
                     InlineKeyboardButton("🕐 وقت النشر", callback_data=f"{CB.SCHED_TIME}{ch_id}")],
                    [InlineKeyboardButton(await get_text(lang, 'back'), callback_data=CB.BACK)]
                ])
                await query.edit_message_text(await get_text(lang, 'schedule_current', type=s.get('type', 'غير محدد')),
                                              reply_markup=kb)
                return

            if data.startswith(CB.SCHED_MIN):
                ch_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_MIN)
                context.user_data['schedule_ch'] = ch_id
                await query.edit_message_text(await get_text(lang, 'enter_minutes'))
                return

            if data.startswith(CB.SCHED_HOUR):
                ch_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_HOUR)
                context.user_data['schedule_ch'] = ch_id
                await query.edit_message_text(await get_text(lang, 'enter_hours'))
                return

            if data.startswith(CB.SCHED_DAY):
                ch_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_DAY)
                context.user_data['schedule_ch'] = ch_id
                await query.edit_message_text(await get_text(lang, 'enter_days'))
                return

            if data.startswith(CB.SCHED_TIME):
                ch_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_PUB_TIME)
                context.user_data['schedule_ch'] = ch_id
                await query.edit_message_text(await get_text(lang, 'enter_publish_time'))
                return

            # ====================================================
            # أزرار الأمان (sec_*)
            # ====================================================
            if data.startswith("sec_"):
                await CallbackHandlers._handle_security_callback(update, context, query, user_id, lang)
                return

            # ====================================================
            # أزرار الكلمات المحظورة
            # ====================================================
            if data.startswith(CB.BAN_ADD):
                chat_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_GROUP_BAN)
                context.user_data['ban_chat'] = chat_id
                await query.edit_message_text(await get_text(lang, 'enter_word'))
                return

            if data.startswith(CB.BAN_LIST):
                chat_id = int(data.split(":")[-1])
                words = await DB.get_banned_words(chat_id)
                if not words:
                    await query.edit_message_text(await get_text(lang, 'no_banned_words'))
                    return
                text = await get_text(lang, 'banned_words_list',
                                      words="\n".join([f"• `{w}`" for w in words]))
                await query.edit_message_text(text)
                return

            if data.startswith(CB.BAN_REM):
                chat_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_REM_GROUP_BAN)
                context.user_data['ban_chat'] = chat_id
                await query.edit_message_text(await get_text(lang, 'enter_word_to_remove'))
                return

            # ====================================================
            # أزرار العقوبات
            # ====================================================
            if data.startswith(CB.PENALTY):
                chat_id = int(data.split(":")[-1])
                await query.edit_message_text("⚖️ اختر العقوبة الأساسية:",
                                              reply_markup=KeyboardFactory.build("penalty", chat_id))
                return

            for p in ['kick', 'ban', 'mute', 'warn', 'restrict', 'none']:
                if data.startswith(f"pen_{p}:"):
                    chat_id = int(data.split(":")[-1])
                    await DB.execute("UPDATE group_security SET auto_penalty=? WHERE chat_id=?", (p, chat_id))
                    await query.edit_message_text(f"✅ تم تعيين العقوبة: {p}")
                    return

            # ====================================================
            # أزرار الإجراءات المتقدمة
            # ====================================================
            if data.startswith(CB.ADV_ACT):
                chat_id = int(data.split(":")[-1])
                await query.edit_message_text("🛠️ إجراءات متقدمة:",
                                              reply_markup=KeyboardFactory.build("advanced_actions", chat_id))
                return

            if data.startswith(CB.ACT_BAN):
                chat_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_BAN)
                context.user_data['adv_chat'] = chat_id
                await query.edit_message_text("🚫 أرسل معرف المستخدم:")
                return

            if data.startswith(CB.ACT_MUTE):
                chat_id = int(data.split(":")[-1])
                await query.edit_message_text("🔇 اختر المدة:",
                                              reply_markup=KeyboardFactory.build("mute_duration", chat_id))
                return

            if data.startswith(CB.MUTE_DUR):
                parts = data.split(":")
                minutes = int(parts[1])
                chat_id = int(parts[2])
                context.user_data['mute_minutes'] = minutes if minutes > 0 else None
                StateManager.set(user_id, UserState.WAIT_MUTE)
                context.user_data['adv_chat'] = chat_id
                await query.edit_message_text(f"🔇 كتم {minutes} دقيقة\nأرسل معرف المستخدم:")
                return

            if data.startswith(CB.ACT_WARN):
                chat_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_WARN)
                context.user_data['adv_chat'] = chat_id
                await query.edit_message_text("⚠️ أرسل معرف المستخدم:")
                return

            if data.startswith(CB.ACT_KICK):
                chat_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_KICK)
                context.user_data['adv_chat'] = chat_id
                await query.edit_message_text("👢 أرسل معرف المستخدم:")
                return

            if data.startswith(CB.ACT_RESTRICT):
                chat_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_RESTRICT)
                context.user_data['adv_chat'] = chat_id
                await query.edit_message_text("🔒 أرسل معرف المستخدم:")
                return

            if data.startswith(CB.ACT_UNBAN):
                chat_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_UNBAN)
                context.user_data['adv_chat'] = chat_id
                await query.edit_message_text("🔓 أرسل معرف المستخدم:")
                return

            if data.startswith(CB.ACT_PIN):
                chat_id = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_PIN)
                context.user_data['adv_chat'] = chat_id
                await query.edit_message_text("📌 أرسل معرف الرسالة أو رد على الرسالة لتثبيتها:")
                return

            if data.startswith(CB.ACT_LOG):
                chat_id = int(data.split(":")[-1])
                logs = await DB.get_admin_logs(chat_id, 20)
                if not logs:
                    await query.edit_message_text("📭 لا توجد سجلات")
                    return
                text = "📜 **آخر الإجراءات**\n"
                for log in logs:
                    time_str = TimeUtils.safe_parse_iso(log['created_at'])
                    if time_str:
                        time_str = time_str.strftime("%H:%M")
                    else:
                        time_str = "??"
                    text += f"• {time_str} - `{log['admin_id']}` {log['action']}"
                    if log['target_id']:
                        text += f" → `{log['target_id']}`"
                    if log['reason']:
                        text += f" ({log['reason']})"
                    text += "\n"
                await query.edit_message_text(text)
                return

            # ====================================================
            # أزرار الردود التلقائية
            # ====================================================
            if data.startswith("auto_reply_"):
                await CallbackHandlers._handle_auto_reply_callback(update, context, query, user_id, lang)
                return

            # ====================================================
            # أزرار لوحة المجموعة
            # ====================================================
            if data.startswith(CB.PANEL_LOCK) or data.startswith(CB.PANEL_UNLOCK):
                await query.answer()
                chat_id = int(data.split(":")[-1])
                locked = data.startswith(CB.PANEL_LOCK)
                if locked:
                    await DB.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?,1,?,?)",
                                     (chat_id, TimeUtils.utc_iso(), user_id))
                else:
                    await DB.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
                await query.edit_message_text(f"🔒 تم القفل" if locked else "🔓 تم الفتح")
                return

            if data == CB.PANEL_CLOSE:
                await query.answer()
                try:
                    await query.message.delete()
                except:
                    pass
                return

            # ====================================================
            # أزرار الأدمن (للمطورين فقط)
            # ====================================================
            if data.startswith("admin_"):
                if not CONFIG.is_developer(user_id):
                    await query.answer(await get_text(lang, 'not_authorized'), show_alert=True)
                    return
                await CallbackHandlers._handle_admin_callback(update, context, query, user_id, lang)
                return

            # ====================================================
            # أزرار اللغة
            # ====================================================
            if data.startswith("lang_"):
                await query.answer()
                lang_set = data.split("_")[-1]
                available = TranslationManager.get_available_languages()
                if lang_set in available:
                    await DB.set_user_language(user_id, lang_set)
                    await query.answer(f"✅ تم تغيير اللغة إلى {available[lang_set]}")
                    await CommandHandlers.start(update, context)
                else:
                    await query.answer("❌ اللغة غير متوفرة", show_alert=True)
                return

            # ====================================================
            # أزرار لوحة الأدمن الرئيسية
            # ====================================================
            if data == CB.ADMIN:
                if CONFIG.is_developer(user_id):
                    kb = KeyboardFactory.build("admin_panel")
                    await query.edit_message_text(await get_text(lang, 'admin_panel'), reply_markup=kb)
                    await query.answer()
                else:
                    await query.answer(await get_text(lang, 'not_authorized'), show_alert=True)
                return

            await query.answer("⚠️ هذا الزر غير متوفر حالياً", show_alert=True)

        except Exception as e:
            logger.error(f"Callback error: {e}", exc_info=True)
            try:
                await query.answer("❌ حدث خطأ غير متوقع", show_alert=True)
            except:
                pass

    # ================================================================
    # دوال مساعدة للمعالجات
    # ================================================================

    @staticmethod
    async def _handle_security_callback(update, context, query, user_id, lang):
        """معالجة أزرار الأمان"""
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            await query.answer("❌ خطأ في البيانات", show_alert=True)
            return

        action = parts[0].replace("sec_", "")
        try:
            chat_id = int(parts[1])
        except:
            await query.answer("❌ خطأ في البيانات", show_alert=True)
            return

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer(await get_text(lang, 'not_authorized'), show_alert=True)
            return

        if data == CB.SEC_CLOSE:
            await query.answer()
            try:
                await query.message.delete()
            except:
                pass
            return

        # تبديل الإعدادات
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
            await query.answer()
            return

        if action == "banned":
            await query.answer()
            await query.edit_message_text("🚫 **الكلمات المحظورة**",
                                          reply_markup=KeyboardFactory.build("banned_words", chat_id))
            return

        if action == "maxlen":
            await query.answer()
            StateManager.set(user_id, UserState.WAIT_MAX_LEN)
            context.user_data[f"sec_chat_{user_id}"] = chat_id
            await query.edit_message_text("📏 أرسل الحد الأقصى لطول الرسالة (0 = غير محدود):")
            return

        if action == "warn":
            await query.answer()
            settings = await DB.get_security_settings(chat_id)
            text = await get_text(lang, 'warning_settings',
                                  max_warnings=settings.get('max_warnings', 3),
                                  warn_penalty=settings.get('warn_penalty', 'ban'))
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 عدد التحذيرات", callback_data=f"sec_warn_count:{chat_id}"),
                 InlineKeyboardButton("⚖️ العقوبة", callback_data=f"sec_warn_penalty:{chat_id}")],
                [InlineKeyboardButton(await get_text(lang, 'back'), callback_data=f"{CB.GRP_SET}{chat_id}")]
            ])
            await query.edit_message_text(text, reply_markup=kb)
            return

        if action == "warn_count":
            await query.answer()
            StateManager.set(user_id, UserState.WAIT_WARN_COUNT)
            context.user_data[f"sec_chat_{user_id}"] = chat_id
            await query.edit_message_text("📝 أرسل الحد الأقصى للتحذيرات (1-10):")
            return

        if action == "warn_penalty":
            await query.answer()
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 حظر", callback_data=f"sec_set_warn_penalty:{chat_id}:ban"),
                 InlineKeyboardButton("🔇 كتم", callback_data=f"sec_set_warn_penalty:{chat_id}:mute")],
                [InlineKeyboardButton(await get_text(lang, 'back'), callback_data=f"sec_warn:{chat_id}")]
            ])
            await query.edit_message_text("⚖️ اختر عقوبة تجاوز التحذيرات:", reply_markup=kb)
            return

        if action == "set_warn_penalty":
            if len(parts) >= 3:
                penalty = parts[2]
                if penalty not in ["ban", "mute"]:
                    await query.answer("❌ عقوبة غير صالحة", show_alert=True)
                    return
                await DB.execute("UPDATE group_security SET warn_penalty=? WHERE chat_id=?", (penalty, chat_id))
                settings = await DB.get_security_settings(chat_id)
                text = await get_text(lang, 'warning_settings',
                                      max_warnings=settings.get('max_warnings', 3),
                                      warn_penalty=settings.get('warn_penalty', 'ban'))
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 عدد التحذيرات", callback_data=f"sec_warn_count:{chat_id}"),
                     InlineKeyboardButton("⚖️ العقوبة", callback_data=f"sec_warn_penalty:{chat_id}")],
                    [InlineKeyboardButton(await get_text(lang, 'back'), callback_data=f"{CB.GRP_SET}{chat_id}")]
                ])
                try:
                    await query.edit_message_text(text, reply_markup=kb)
                except BadRequest as e:
                    if "Message is not modified" not in str(e):
                        raise
                await query.answer()
                return

        if action == "enable_all":
            await query.answer()
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
            await query.answer()
            for f in ['delete_videos', 'delete_audio', 'delete_animation', 'delete_service',
                      'delete_documents', 'delete_stickers', 'delete_forwarded', 'delete_polls',
                      'delete_games', 'delete_voice', 'delete_video_note']:
                await DB.execute(f"UPDATE group_security SET {f}=0 WHERE chat_id=?", (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = await KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id)
            await query.edit_message_text(text, reply_markup=kb)
            return

        if action == "del_pen":
            await query.answer()
            await query.edit_message_text("⚖️ اختر عقوبة حذف الوسائط:",
                                          reply_markup=KeyboardFactory.build("penalty", chat_id))
            return

        if action == "penalty":
            await query.answer()
            await query.edit_message_text("⚖️ اختر العقوبة الأساسية:",
                                          reply_markup=KeyboardFactory.build("penalty", chat_id))
            return

        if action == "adv_act":
            await query.answer()
            await query.edit_message_text("🛠️ إجراءات متقدمة:",
                                          reply_markup=KeyboardFactory.build("advanced_actions", chat_id))
            return

        if action == "act_log":
            await query.answer()
            logs = await DB.get_admin_logs(chat_id, 20)
            if not logs:
                await query.edit_message_text("📭 لا توجد سجلات")
                return
            text = "📜 **آخر الإجراءات**\n"
            for log in logs:
                time_str = TimeUtils.safe_parse_iso(log['created_at'])
                if time_str:
                    time_str = time_str.strftime("%H:%M")
                else:
                    time_str = "??"
                text += f"• {time_str} - `{log['admin_id']}` {log['action']}"
                if log['target_id']:
                    text += f" → `{log['target_id']}`"
                if log['reason']:
                    text += f" ({log['reason']})"
                text += "\n"
            await query.edit_message_text(text)
            return

        if action == "auto_reply_menu":
            await query.answer()
            await query.edit_message_text(await get_text(lang, 'auto_reply_settings'),
                                          reply_markup=KeyboardFactory.build("auto_reply_manage", chat_id))
            return

        await query.answer()

    @staticmethod
    async def _handle_admin_callback(update, context, query, user_id, lang):
        """معالجة أزرار لوحة الأدمن"""
        data = query.data

        # ============================================================
        # المستخدمون
        # ============================================================
        if data == CB.ADMIN_USERS:
            stats = await DB.get_user_stats()
            await query.edit_message_text(await get_text(lang, 'admin_users',
                                                         users=stats['users'], banned=stats['banned']))
            return

        if data == CB.ADMIN_BANNED:
            users = await DB.get_all_users()
            banned_list = [str(u[0]) for u in users if u[1] == 1]
            text = "⛔ **المحظورين**\n\n" + "\n".join([f"• `{u}`" for u in banned_list[:20]]) if banned_list else "لا يوجد محظورين"
            await query.edit_message_text(text)
            return

        if data == CB.ADMIN_UNBAN_ALL:
            await DB.execute("UPDATE users SET banned=0 WHERE banned=1")
            await query.edit_message_text(await get_text(lang, 'admin_unbanned_all'))
            return

        # ============================================================
        # القنوات
        # ============================================================
        if data == CB.ADMIN_CHANNELS:
            channels = await DB.fetchall("SELECT id, channel_id, channel_name, banned FROM user_channels LIMIT 50")
            if not channels:
                await query.edit_message_text(await get_text(lang, 'no_channels'))
                return
            text = await get_text(lang, 'admin_channels_list',
                                  list="\n".join([f"• `{c[1]}` - {c[2]} {'🚫' if c[3] else '✅'}" for c in channels]))
            await query.edit_message_text(text)
            return

        if data == CB.ADMIN_BANNED_CH:
            channels = await DB.fetchall("SELECT id, channel_id, channel_name FROM user_channels WHERE banned=1 LIMIT 50")
            if not channels:
                await query.edit_message_text("📭 لا توجد قنوات محظورة")
                return
            text = "🚫 **القنوات المحظورة**\n\n" + "\n".join([f"• `{c[1]}` - {c[2]}" for c in channels])
            await query.edit_message_text(text)
            return

        if data == CB.ADMIN_ACTIVATE_CH:
            await DB.execute("UPDATE user_channels SET banned=0 WHERE banned=1")
            await query.edit_message_text(await get_text(lang, 'admin_activated_channels'))
            return

        # ============================================================
        # المجموعات
        # ============================================================
        if data == CB.ADMIN_GROUPS:
            groups = await DB.fetchall("SELECT chat_id, chat_name, banned FROM bot_groups LIMIT 50")
            if not groups:
                await query.edit_message_text(await get_text(lang, 'no_groups'))
                return
            text = await get_text(lang, 'admin_groups_list',
                                  list="\n".join([f"• `{g[0]}` - {g[1]} {'🚫' if g[2] else '✅'}" for g in groups]))
            await query.edit_message_text(text)
            return

        if data == CB.ADMIN_BANNED_GR:
            groups = await DB.fetchall("SELECT chat_id, chat_name FROM bot_groups WHERE banned=1 LIMIT 50")
            if not groups:
                await query.edit_message_text("📭 لا توجد مجموعات محظورة")
                return
            text = "🚫 **المجموعات المحظورة**\n\n" + "\n".join([f"• `{g[0]}` - {g[1]}" for g in groups])
            await query.edit_message_text(text)
            return

        if data == CB.ADMIN_UNBAN_GR:
            await DB.execute("UPDATE bot_groups SET banned=0 WHERE banned=1")
            await query.edit_message_text(await get_text(lang, 'admin_unbanned_groups'))
            return

        # ============================================================
        # إدارة المشرفين
        # ============================================================
        if data == CB.ADMIN_ADD_ADMIN:
            StateManager.set(user_id, UserState.WAIT_ADMIN_ADD)
            await query.edit_message_text(await get_text(lang, 'admin_add_admin'))
            return

        if data == CB.ADMIN_REM_ADMIN:
            StateManager.set(user_id, UserState.WAIT_ADMIN_REM)
            await query.edit_message_text(await get_text(lang, 'admin_rem_admin'))
            return

        # ============================================================
        # النظام
        # ============================================================
        if data == CB.ADMIN_RAM:
            ram = get_ram_usage()
            await query.edit_message_text(await get_text(lang, 'admin_ram',
                                                         used=ram['used'], total=ram['total'], percent=ram['percent']))
            return

        if data == CB.ADMIN_STATS:
            stats = await DB.get_user_stats()
            await query.edit_message_text(await get_text(lang, 'admin_stats_text',
                                                         users=stats['users'], banned=stats['banned'],
                                                         posts=0, groups=0, channels=0))
            return

        if data == CB.ADMIN_METRICS:
            metrics = METRICS.get_stats()
            active = (await DB.fetchone("SELECT COUNT(*) FROM users WHERE updated_at > datetime('now', '-30 days')"))[0]
            today = (await DB.fetchone("SELECT COUNT(*) FROM posts WHERE published_at > datetime('now', 'start of day')"))[0]
            db_size = (PATHS.DB.stat().st_size / (1024 * 1024)) if PATHS.DB.exists() else 0
            uptime_hours = metrics['uptime_seconds'] // 3600
            uptime_minutes = (metrics['uptime_seconds'] % 3600) // 60
            uptime_str = f"{uptime_hours}h {uptime_minutes}m"
            await query.edit_message_text(await get_text(lang, 'admin_metrics',
                                                         active=active, today=today, db_size=db_size,
                                                         api_calls=metrics['api_calls_last_hour'],
                                                         errors=metrics['errors_last_hour'],
                                                         uptime=uptime_str))
            return

        # ============================================================
        # النسخ الاحتياطي
        # ============================================================
        if data == CB.ADMIN_BACKUP:
            try:
                backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2(PATHS.DB, backup_file)
                await safe_send(context.bot, user_id, await get_text(lang, 'admin_backup_created',
                                                                     filename=backup_file.name))
            except Exception as e:
                await safe_send(context.bot, user_id, await get_text(lang, 'admin_backup_failed', error=str(e)[:100]))
            return

        if data == CB.ADMIN_RESTORE:
            backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
            if not backups:
                await query.edit_message_text(await get_text(lang, 'no_backups'))
                return
            kb = [[InlineKeyboardButton(b.name, callback_data=f"{CB.ADMIN_RESTORE_SEL}{b.name}")] for b in backups[:10]]
            kb.append([InlineKeyboardButton(await get_text(lang, 'back'), callback_data=CB.ADMIN)])
            await query.edit_message_text(await get_text(lang, 'admin_restore_choose'), reply_markup=InlineKeyboardMarkup(kb))
            return

        if data.startswith(CB.ADMIN_RESTORE_SEL):
            filename = data.split(":")[-1]
            filepath = PATHS.BACKUPS / filename
            if not filepath.exists():
                await query.edit_message_text(await get_text(lang, 'file_not_found'))
                return
            try:
                shutil.copy2(filepath, PATHS.DB)
                await query.edit_message_text(await get_text(lang, 'admin_restore_success'))
            except Exception as e:
                await query.edit_message_text(await get_text(lang, 'admin_restore_failed', error=str(e)[:100]))
            return

        # ============================================================
        # التحديثات والبث
        # ============================================================
        if data == CB.ADMIN_SEND_UPDATE:
            StateManager.set(user_id, UserState.WAIT_UPDATE)
            await query.edit_message_text("📢 أرسل نص التحديث:")
            return

        if data == CB.ADMIN_SET_UPDATE_CH:
            StateManager.set(user_id, UserState.WAIT_UPDATE_CH)
            await query.edit_message_text("📢 أرسل معرف القناة (بدون @):")
            return

        if data == CB.ADMIN_SHOW_UPDATE:
            ch = await DB.get_updates_channel()
            await query.edit_message_text(f"📢 القناة: @{ch}" if ch else "لا توجد قناة تحديثات")
            return

        if data == CB.ADMIN_FORCE_SUB:
            ch = await DB.get_force_subscribe_channel()
            await query.edit_message_text(await get_text(lang, 'admin_force_sub_on', channel=ch) if ch
                                          else await get_text(lang, 'admin_force_sub_off'))
            return

        if data == CB.ADMIN_SET_FORCE:
            StateManager.set(user_id, UserState.WAIT_FORCE)
            await query.edit_message_text("🔒 أرسل معرف القناة (بدون @):")
            return

        if data == CB.ADMIN_BROADCAST:
            StateManager.set(user_id, UserState.WAIT_BROADCAST)
            await query.edit_message_text("📨 أرسل الرسالة:")
            return

        if data == CB.ADMIN_CONFIRM_BROADCAST:
            text = context.user_data.get('broadcast_text')
            if not text:
                await query.edit_message_text("لا توجد رسالة")
                return
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
            await query.edit_message_text(await get_text(lang, 'admin_broadcast_sent', sent=sent))
            context.user_data.pop('broadcast_text', None)
            return

        # ============================================================
        # التذاكر
        # ============================================================
        if data == CB.ADMIN_TICKETS:
            tickets = await DB.get_tickets()
            if not tickets:
                await query.edit_message_text(await get_text(lang, 'no_tickets'))
                return
            text = await get_text(lang, 'tickets_list',
                                  tickets="\n".join([f"#{t['ticket_number']} - من `{t['user_id']}`" for t in tickets]))
            await query.edit_message_text(text)
            return

        if data == CB.ADMIN_DEL_TICKETS:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ نعم", callback_data=CB.ADMIN_CONFIRM_DEL_TICKETS),
                 InlineKeyboardButton("❌ لا", callback_data=CB.ADMIN)]
            ])
            await query.edit_message_text(await get_text(lang, 'confirm_delete_tickets'), reply_markup=kb)
            return

        if data == CB.ADMIN_CONFIRM_DEL_TICKETS:
            await DB.delete_all_tickets()
            await query.edit_message_text(await get_text(lang, 'tickets_deleted'))
            return

        # ============================================================
        # قناة السجلات
        # ============================================================
        if data == CB.ADMIN_LOG_CH:
            log_id = await DB.get_log_channel()
            await query.edit_message_text(f"📋 قناة السجلات: {log_id}" if log_id else "📋 غير محدد")
            return

        if data == CB.ADMIN_SET_LOG_CH:
            StateManager.set(user_id, UserState.WAIT_LOG_CH)
            await query.edit_message_text("📋 أرسل معرف القناة:")
            return

        # ============================================================
        # الردود التلقائية (إدارة عامة)
        # ============================================================
        if data == CB.ADMIN_REPLIES:
            stats = await DB.get_auto_reply_stats(-1, 20)
            if not stats:
                await query.edit_message_text(await get_text(lang, 'no_auto_replies'))
                return
            text = await get_text(lang, 'auto_reply_stats',
                                  stats="\n".join([f"• `{kw}`: {cnt} مرة" for kw, cnt in stats]))
            await query.edit_message_text(text)
            return

        if data == CB.ADMIN_ADD_REPLY:
            StateManager.set(user_id, UserState.WAIT_KEYWORD)
            await query.edit_message_text(await get_text(lang, 'enter_keyword'))
            return

        if data == CB.ADMIN_LIST_REPLIES:
            replies = await DB.fetchall("SELECT keyword, reply, usage_count FROM auto_replies WHERE chat_id=0 ORDER BY keyword LIMIT 20")
            if not replies:
                await query.edit_message_text(await get_text(lang, 'no_auto_replies'))
                return
            text = await get_text(lang, 'auto_reply_list',
                                  replies="\n".join([f"• `{r[0]}` → {r[1][:30]}... ({r[2]})" for r in replies]))
            await query.edit_message_text(text)
            return

        if data == CB.ADMIN_DEL_REPLY:
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = -1
            await query.edit_message_text(await get_text(lang, 'enter_keyword_to_delete'))
            return

        # ============================================================
        # الكلمات المحظورة (عامة)
        # ============================================================
        if data == CB.ADMIN_BANNED_WORDS:
            words = await DB.get_banned_words(-1)
            text = await get_text(lang, 'admin_banned_words_global',
                                  words="\n".join([f"• `{w}`" for w in words])) if words else await get_text(lang, 'no_banned_words')
            await query.edit_message_text(text)
            return

        if data == CB.ADMIN_ADD_BANNED:
            StateManager.set(user_id, UserState.WAIT_GLOBAL_BAN)
            await query.edit_message_text(await get_text(lang, 'enter_word'))
            return

        if data == CB.ADMIN_REM_BANNED:
            StateManager.set(user_id, UserState.WAIT_REM_GLOBAL_BAN)
            await query.edit_message_text(await get_text(lang, 'enter_word_to_remove'))
            return

        # ============================================================
        # المسابقات (إدارة)
        # ============================================================
        if data == CB.ADMIN_CREATE_CONTEST:
            StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
            await query.edit_message_text("🏆 أرسل عنوان المسابقة:")
            return

        if data == CB.ADMIN_DECLARE_WINNER:
            contests = await DB.fetchall("SELECT id, title FROM contests WHERE status='active'")
            if not contests:
                await query.edit_message_text(await get_text(lang, 'no_active_contests'))
                return
            kb = [[InlineKeyboardButton(title, callback_data=f"{CB.DECLARE_WINNER_SEL}{cid}")] for cid, title in contests]
            kb.append([InlineKeyboardButton(await get_text(lang, 'back'), callback_data=CB.ADMIN)])
            await query.edit_message_text("اختر المسابقة:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if data.startswith(CB.DECLARE_WINNER_SEL):
            cid = int(data.split(":")[-1])
            contest = await DB.fetchone("SELECT title FROM contests WHERE id=?", (cid,))
            if not contest:
                await query.edit_message_text(await get_text(lang, 'contest_not_found'))
                return
            winner = await DB.fetchone("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,))
            if not winner:
                await query.edit_message_text(await get_text(lang, 'admin_contest_no_participants'))
                return
            await DB.declare_winner(cid, winner[0])
            await query.edit_message_text(await get_text(lang, 'admin_contest_declared', title=contest[0], winner=winner[0]))
            return

        if data.startswith(CB.ADMIN_DEL_CONTEST):
            cid = int(data.split(":")[-1])
            await DB.delete_contest(cid, user_id)
            await query.edit_message_text(await get_text(lang, 'admin_contest_deleted'))
            return

        # ============================================================
        # تصدير/استيراد الردود
        # ============================================================
        if data == CB.ADMIN_EXPORT_REPLIES:
            count = await export_auto_replies(-1)
            await query.edit_message_text(f"✅ تم تصدير {count} رد إلى ملف `auto_replies_-1.json`")
            return

        if data == CB.ADMIN_IMPORT_REPLIES:
            StateManager.set(user_id, UserState.WAIT_IMPORT_FILE)
            context.user_data['import_chat_id'] = -1
            await query.edit_message_text("📤 أرسل ملف JSON للاستيراد (سيتم استبدال الردود الموجودة)")
            return

        if data == CB.ADMIN_IMPORT_GITHUB:
            StateManager.set(user_id, UserState.WAIT_GITHUB_URL)
            await query.edit_message_text(await get_text(lang, 'import_from_github_prompt'))
            return

        # ============================================================
        # تحديث الكاش
        # ============================================================
        if data == CB.ADMIN_REFRESH_CACHE:
            _auto_reply_cache.invalidate()
            await query.edit_message_text("🔄 تم تحديث الكاش بنجاح")
            return

        await query.answer("⚠️ هذا الزر غير متوفر حالياً", show_alert=True)

    @staticmethod
    async def _handle_auto_reply_callback(update, context, query, user_id, lang):
        """معالجة أزرار الردود التلقائية"""
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            await query.answer("❌ خطأ في البيانات", show_alert=True)
            return

        action = parts[0].replace("auto_reply_", "")
        try:
            chat_id = int(parts[1])
        except:
            await query.answer("❌ خطأ في البيانات", show_alert=True)
            return

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer(await get_text(lang, 'not_authorized'), show_alert=True)
            return

        if action == "toggle":
            settings = await DB.get_auto_reply_settings(chat_id)
            new_status = not settings.get('enabled', False)
            await DB.update_auto_reply_settings(chat_id, enabled=new_status)
            settings = await DB.get_auto_reply_settings(chat_id)
            kb = KeyboardFactory.build("auto_reply_settings", chat_id)
            await query.edit_message_text(await get_text(lang, 'auto_reply_settings'), reply_markup=kb)
            await query.answer()
            return

        if action == "admins":
            settings = await DB.get_auto_reply_settings(chat_id)
            new_admins = not settings.get('only_admins', False)
            await DB.update_auto_reply_settings(chat_id, only_admins=new_admins)
            settings = await DB.get_auto_reply_settings(chat_id)
            kb = KeyboardFactory.build("auto_reply_settings", chat_id)
            await query.edit_message_text(await get_text(lang, 'auto_reply_settings'), reply_markup=kb)
            await query.answer()
            return

        if action == "reset" or action == "confirm_reset":
            await DB.reset_auto_replies(chat_id)
            settings = await DB.get_auto_reply_settings(chat_id)
            kb = KeyboardFactory.build("auto_reply_settings", chat_id)
            await query.edit_message_text(await get_text(lang, 'auto_reply_settings'), reply_markup=kb)
            await query.answer()
            return

        if action == "stats":
            stats = await DB.get_auto_reply_stats(chat_id, 10)
            if not stats:
                await query.edit_message_text(await get_text(lang, 'no_auto_reply_stats'))
                return
            text = await get_text(lang, 'auto_reply_stats',
                                  stats="\n".join([f"• `{kw}`: {count} مرة" for kw, count in stats]))
            await query.edit_message_text(text)
            await query.answer()
            return

        if action == "add":
            StateManager.set(user_id, UserState.WAIT_AUTO_KEY)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text(await get_text(lang, 'enter_keyword'))
            return

        if action == "del":
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text(await get_text(lang, 'enter_keyword_to_delete'))
            return

        if action == "list":
            replies = await DB.fetchall("SELECT keyword, reply, usage_count FROM auto_replies WHERE chat_id=? ORDER BY usage_count DESC LIMIT 20", (chat_id,))
            if not replies:
                await query.edit_message_text(await get_text(lang, 'no_auto_replies'))
                return
            text = await get_text(lang, 'auto_reply_list',
                                  replies="\n".join([f"• `{r[0]}` → {r[1][:30]}... ({r[2]})" for r in replies]))
            await query.edit_message_text(text)
            await query.answer()
            return

        if action == "menu":
            kb = KeyboardFactory.build("auto_reply_manage", chat_id)
            await query.edit_message_text(await get_text(lang, 'auto_reply_settings'), reply_markup=kb)
            await query.answer()
            return

        await query.answer()

    @staticmethod
    async def _publish_single(bot, ch_db_id, ch_tele, post):
        """نشر منشور واحد (مستخدم في PUB_ALL)"""
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
            await DB.update_last_publish(ch_db_id)
            await DB.update_next_publish(ch_db_id)
        except Exception as e:
            await DB.increment_post_fail(post['id'])


# =====================================================================
# 3. معالج الرسائل - MessageHandlers (كامل)
# =====================================================================

class MessageHandlers:
    """جميع معالجات الرسائل (خاصة ومجموعات)"""

    @staticmethod
    async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة الرسائل الخاصة"""
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        msg = update.message
        text = msg.text.strip() if msg.text else ""
        state = StateManager.get(user_id)
        lang = await DB.get_user_language(user_id)

        # ============================================================
        # حالة: استيراد ملف JSON
        # ============================================================
        if state == UserState.WAIT_IMPORT_FILE:
            if not msg.document:
                await safe_send(context.bot, user_id, "❌ أرسل ملف JSON")
                return
            file = msg.document
            if not file.file_name.endswith('.json'):
                await safe_send(context.bot, user_id, "❌ الملف يجب أن يكون JSON")
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
                await safe_send(context.bot, user_id, f"❌ فشل الاستيراد: {str(e)[:100]}")
            StateManager.clear(user_id)
            context.user_data.pop('import_chat_id', None)
            return

        # ============================================================
        # حالة: استيراد من GitHub
        # ============================================================
        if state == UserState.WAIT_GITHUB_URL:
            url = text.strip()
            if not url.startswith('http'):
                await safe_send(context.bot, user_id, await get_text(lang, 'import_github_invalid_url'))
                StateManager.clear(user_id)
                return
            await safe_send(context.bot, user_id, await get_text(lang, 'import_github_loading'))
            json_data = await fetch_json_from_url(url)
            if not json_data:
                await safe_send(context.bot, user_id, await get_text(lang, 'import_github_failed'))
                StateManager.clear(user_id)
                return
            try:
                count = await import_auto_replies(-1, json_data, overwrite=True)
                await safe_send(context.bot, user_id, await get_text(lang, 'import_github_success', count=count))
            except Exception as e:
                await safe_send(context.bot, user_id, await get_text(lang, 'import_github_error', error=str(e)[:100]))
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: إضافة قناة
        # ============================================================
        if state == UserState.WAIT_CHANNEL:
            if not await DB.has_active_subscription(user_id) and not await DB.has_used_trial(user_id):
                await safe_send(context.bot, user_id, await get_text(lang, 'subscription_expired'))
                StateManager.clear(user_id)
                return

            channel_input = text.strip()
            if not channel_input:
                await safe_send(context.bot, user_id, await get_text(lang, 'invalid_format'))
                StateManager.clear(user_id)
                return

            try:
                chat = await context.bot.get_chat(channel_input)
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ خطأ: {str(e)[:100]}")
                StateManager.clear(user_id)
                return

            if chat.type != 'channel':
                await safe_send(context.bot, user_id, await get_text(lang, 'invalid_channel'))
                StateManager.clear(user_id)
                return

            # التحقق من صلاحيات البوت
            try:
                bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                if bot_member.status != 'administrator':
                    await safe_send(context.bot, user_id, await get_text(lang, 'bot_not_admin'))
                    StateManager.clear(user_id)
                    return
                if not bot_member.can_post_messages:
                    await safe_send(context.bot, user_id, "❌ البوت لا يملك صلاحية النشر في القناة")
                    StateManager.clear(user_id)
                    return
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ فشل التحقق من صلاحيات البوت: {str(e)[:100]}")
                StateManager.clear(user_id)
                return

            try:
                channel_id = chat.id
                channel_name = chat.title or "بدون اسم"
                result = await DB.add_channel(user_id, channel_id, channel_name)
                if result:
                    await DB.set_active_channel(user_id, result)
                    await safe_send(context.bot, user_id, f"✅ تمت إضافة القناة **{channel_name}** بنجاح!")
                else:
                    await safe_send(context.bot, user_id, await get_text(lang, 'channel_exists'))
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ فشل إضافة القناة: {str(e)[:100]}")

            StateManager.clear(user_id)
            await CommandHandlers.start(update, context)
            return

        # ============================================================
        # حالة: إضافة منشورات
        # ============================================================
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
            elif msg.text:
                media_type = 'text'
            else:
                await safe_send(context.bot, user_id, "⚠️ هذا النوع غير مدعوم")
                return

            content = msg.caption or "" if media_type != 'text' else text
            session.append((content, media_type, media_file_id))
            context.user_data[f"session_{user_id}"] = session
            remaining = target - len(session)
            await safe_send(context.bot, user_id, await get_text(lang, 'post_saved',
                                                                 saved=len(session), target=target, remaining=remaining))

            if len(session) >= target:
                active = await DB.get_active_channel(user_id)
                if active:
                    await DB.add_posts(active, session)
                context.user_data.pop(f"session_{user_id}", None)
                context.user_data.pop(f"session_target_{user_id}", None)
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, await get_text(lang, 'all_posts_saved'))
            return

        # ============================================================
        # حالة: الجدولة (دقائق، ساعات، أيام، وقت)
        # ============================================================
        if state == UserState.WAIT_MIN:
            try:
                val = int(text)
                if 1 <= val <= 1440:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_minutes', interval_minutes=val)
                        await safe_send(context.bot, user_id, await get_text(lang, 'schedule_updated_ok'))
                else:
                    await safe_send(context.bot, user_id, "❌ بين 1 و 1440")
            except:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_HOUR:
            try:
                val = int(text)
                if 1 <= val <= 168:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_hours', interval_hours=val)
                        await safe_send(context.bot, user_id, await get_text(lang, 'schedule_updated_ok'))
                else:
                    await safe_send(context.bot, user_id, "❌ بين 1 و 168")
            except:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_DAY:
            try:
                val = int(text)
                if 1 <= val <= 365:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_days', interval_days=val)
                        await safe_send(context.bot, user_id, await get_text(lang, 'schedule_updated_ok'))
                else:
                    await safe_send(context.bot, user_id, "❌ بين 1 و 365")
            except:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PUB_TIME:
            if ':' in text:
                try:
                    h, m = map(int, text.split(':'))
                    if 0 <= h <= 23 and 0 <= m <= 59:
                        ch = context.user_data.get('schedule_ch')
                        if ch:
                            await DB.update_schedule(ch, publish_time=text)
                            await safe_send(context.bot, user_id, await get_text(lang, 'schedule_updated_ok'))
                    else:
                        await safe_send(context.bot, user_id, "❌ وقت غير صالح")
                except:
                    await safe_send(context.bot, user_id, "❌ صيغة خاطئة")
            else:
                await safe_send(context.bot, user_id, "❌ أرسل وقت صحيح مثل 14:30")
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: الكلمات المحظورة (مجموعة)
        # ============================================================
        if state == UserState.WAIT_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            if chat_id_ban and await is_authorized_in_group(context.bot, chat_id_ban, user_id):
                word = text.strip().lower()
                if len(word) < 2:
                    await safe_send(context.bot, user_id, await get_text(lang, 'word_too_short'))
                else:
                    added, exists = await DB.add_banned_word(word, chat_id_ban, user_id)
                    if exists:
                        await safe_send(context.bot, user_id, await get_text(lang, 'word_exists', word=word))
                    else:
                        await safe_send(context.bot, user_id, await get_text(lang, 'word_added', word=word))
            else:
                await safe_send(context.bot, user_id, await get_text(lang, 'not_authorized'))
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            if chat_id_ban and await is_authorized_in_group(context.bot, chat_id_ban, user_id):
                word = text.strip().lower()
                if word:
                    await DB.remove_banned_word(word, chat_id_ban)
                    await safe_send(context.bot, user_id, await get_text(lang, 'word_removed', word=word))
                else:
                    await safe_send(context.bot, user_id, await get_text(lang, 'word_not_found'))
            else:
                await safe_send(context.bot, user_id, await get_text(lang, 'not_authorized'))
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: الكلمات المحظورة (عامة)
        # ============================================================
        if state == UserState.WAIT_GLOBAL_BAN:
            word = text.strip().lower()
            if len(word) < 2:
                await safe_send(context.bot, user_id, await get_text(lang, 'word_too_short'))
            else:
                added, exists = await DB.add_banned_word(word, -1, user_id)
                if exists:
                    await safe_send(context.bot, user_id, await get_text(lang, 'word_exists', word=word))
                else:
                    await safe_send(context.bot, user_id, await get_text(lang, 'word_added', word=word))
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GLOBAL_BAN:
            word = text.strip().lower()
            if word:
                await DB.remove_banned_word(word, -1)
                await safe_send(context.bot, user_id, await get_text(lang, 'word_removed', word=word))
            else:
                await safe_send(context.bot, user_id, await get_text(lang, 'word_not_found'))
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: إدارة المشرفين (إضافة/حذف)
        # ============================================================
        if state == UserState.WAIT_ADMIN_ADD:
            try:
                target = int(text)
                await DB.execute("INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)",
                                 (target, user_id, TimeUtils.utc_iso()))
                await safe_send(context.bot, user_id, await get_text(lang, 'admin_added', user=target))
            except:
                await safe_send(context.bot, user_id, "❌ خطأ")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ADMIN_REM:
            try:
                target = int(text)
                await DB.execute("DELETE FROM bot_admins WHERE user_id=?", (target,))
                await safe_send(context.bot, user_id, await get_text(lang, 'admin_removed', user=target))
            except:
                await safe_send(context.bot, user_id, "❌ خطأ")
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: البث
        # ============================================================
        if state == UserState.WAIT_BROADCAST:
            context.user_data['broadcast_text'] = text
            StateManager.clear(user_id)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ تأكيد", callback_data=CB.ADMIN_CONFIRM_BROADCAST),
                 InlineKeyboardButton("❌ إلغاء", callback_data=CB.ADMIN)]
            ])
            await safe_send(context.bot, user_id, await get_text(lang, 'admin_broadcast_confirm', text=text[:200]),
                            reply_markup=kb)
            return

        # ============================================================
        # حالة: التحديثات
        # ============================================================
        if state == UserState.WAIT_UPDATE:
            ch = await DB.get_updates_channel()
            if ch:
                try:
                    await context.bot.send_message(f"@{ch}", f"📢 {text}")
                    await safe_send(context.bot, user_id, await get_text(lang, 'admin_update_sent'))
                except:
                    await safe_send(context.bot, user_id, await get_text(lang, 'admin_update_failed'))
            else:
                await safe_send(context.bot, user_id, "❌ لا توجد قناة تحديثات")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_UPDATE_CH:
            await DB.set_setting('updates_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, f"✅ تم تعيين قناة التحديثات: @{text.replace('@', '')}")
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: الاشتراك الإجباري
        # ============================================================
        if state == UserState.WAIT_FORCE:
            await DB.set_setting('force_subscribe_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, await get_text(lang, 'admin_force_sub_set', channel=text.replace('@', '')))
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: التذكيرات
        # ============================================================
        if state == UserState.WAIT_REM_DAYS:
            try:
                val = int(text)
                if 1 <= val <= 30:
                    await DB.update_reminder_settings(user_id, reminder_days_before=val)
                    await safe_send(context.bot, user_id, await get_text(lang, 'reminder_days_updated', days=val))
                else:
                    await safe_send(context.bot, user_id, "❌ بين 1 و 30")
            except:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: الإجراءات المتقدمة (حظر، كتم، تحذير، ...)
        # ============================================================
        if state in (UserState.WAIT_BAN, UserState.WAIT_MUTE, UserState.WAIT_WARN,
                     UserState.WAIT_KICK, UserState.WAIT_RESTRICT, UserState.WAIT_UNBAN):
            chat_id_adv = context.user_data.get('adv_chat')
            if chat_id_adv:
                try:
                    target = int(text.split()[0]) if text.split()[0].isdigit() else None
                    if target:
                        if await is_authorized_in_group(context.bot, chat_id_adv, target):
                            await safe_send(context.bot, user_id, await get_text(lang, 'error_user_admin'))
                            StateManager.clear(user_id)
                            return
                        action_map = {
                            UserState.WAIT_BAN: "ban",
                            UserState.WAIT_MUTE: "mute",
                            UserState.WAIT_WARN: "warn",
                            UserState.WAIT_KICK: "kick",
                            UserState.WAIT_RESTRICT: "restrict",
                            UserState.WAIT_UNBAN: "unban"
                        }
                        action = action_map.get(state)
                        if action:
                            dur = context.user_data.get('mute_minutes', 60) if action == 'mute' else None
                            success, msg = await apply_penalty(context.bot, chat_id_adv, target, action,
                                                               dur, "", user_id)
                            await safe_send(context.bot, user_id, msg)
                            if success:
                                await DB.add_admin_log(chat_id_adv, user_id, action, target, "")
                except:
                    pass
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: تثبيت رسالة
        # ============================================================
        if state == UserState.WAIT_PIN:
            chat_id_adv = context.user_data.get('adv_chat')
            if chat_id_adv:
                try:
                    if update.message.reply_to_message:
                        msg_id = update.message.reply_to_message.message_id
                    else:
                        msg_id = int(text.strip())
                    await context.bot.pin_chat_message(chat_id_adv, msg_id)
                    await safe_send(context.bot, user_id, "📌 تم التثبيت")
                except Exception as e:
                    await safe_send(context.bot, user_id, f"❌ {str(e)[:100]}")
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: المسابقات (إنشاء)
        # ============================================================
        if state == UserState.WAIT_CONTEST_TITLE:
            context.user_data['contest_title'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_DESC)
            await safe_send(context.bot, user_id, "📝 أرسل وصف المسابقة:")
            return

        if state == UserState.WAIT_CONTEST_DESC:
            context.user_data['contest_desc'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_PRIZE)
            await safe_send(context.bot, user_id, "🎁 أرسل الجائزة:")
            return

        if state == UserState.WAIT_CONTEST_PRIZE:
            context.user_data['contest_prize'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_DATE)
            await safe_send(context.bot, user_id, "📅 أرسل تاريخ الانتهاء (YYYY-MM-DD HH:MM):")
            return

        if state == UserState.WAIT_CONTEST_DATE:
            try:
                end_date = datetime.strptime(text, "%Y-%m-%d %H:%M")
                if end_date > TimeUtils.mecca_now():
                    cid = await DB.create_contest(
                        user_id,
                        context.user_data.pop('contest_title', ''),
                        context.user_data.pop('contest_desc', ''),
                        context.user_data.pop('contest_prize', ''),
                        TimeUtils.mecca_to_utc(end_date).isoformat()
                    )
                    await safe_send(context.bot, user_id, await get_text(lang, 'contest_created', id=cid))
                else:
                    await safe_send(context.bot, user_id, "❌ تاريخ في الماضي")
            except:
                await safe_send(context.bot, user_id, "❌ صيغة خاطئة")
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: المشاركة في مسابقة
        # ============================================================
        if state == UserState.WAIT_CONTEST_ANSWER:
            cid = context.user_data.get('contest_join')
            if cid:
                answer = text if text != '/skip' else ""
                await DB.join_contest(cid, user_id, answer)
                await safe_send(context.bot, user_id, await get_text(lang, 'contest_joined'))
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: إضافة رد تلقائي
        # ============================================================
        if state == UserState.WAIT_AUTO_KEY:
            keyword = text.strip().lower()
            if keyword:
                context.user_data['auto_key'] = keyword
                StateManager.set(user_id, UserState.WAIT_AUTO_REPLY)
                await safe_send(context.bot, user_id, await get_text(lang, 'enter_reply'))
            else:
                await safe_send(context.bot, user_id, "❌ كلمة غير صالحة")
                StateManager.clear(user_id)
            return

        if state == UserState.WAIT_AUTO_REPLY:
            chat_id_auto = context.user_data.get('auto_chat')
            keyword = context.user_data.get('auto_key')
            if chat_id_auto is not None and keyword:
                await DB.add_auto_reply(chat_id_auto, keyword, text)
                await safe_send(context.bot, user_id, await get_text(lang, 'auto_reply_added', keyword=keyword))
            else:
                await safe_send(context.bot, user_id, "❌ خطأ في البيانات")
            StateManager.clear(user_id)
            context.user_data.pop('auto_key', None)
            context.user_data.pop('auto_chat', None)
            return

        # ============================================================
        # حالة: حذف رد تلقائي
        # ============================================================
        if state == UserState.WAIT_AUTO_DEL:
            chat_id_auto = context.user_data.get('auto_chat')
            if chat_id_auto is not None:
                keyword = text.strip().lower()
                if keyword:
                    if await DB.remove_auto_reply(chat_id_auto, keyword):
                        await safe_send(context.bot, user_id, await get_text(lang, 'auto_reply_deleted', keyword=keyword))
                    else:
                        await safe_send(context.bot, user_id, await get_text(lang, 'auto_reply_not_found', keyword=keyword))
                else:
                    await safe_send(context.bot, user_id, "❌ كلمة غير صالحة")
            else:
                await safe_send(context.bot, user_id, "❌ خطأ في البيانات")
            StateManager.clear(user_id)
            context.user_data.pop('auto_chat', None)
            return

        # ============================================================
        # حالة: إضافة رد (عام)
        # ============================================================
        if state == UserState.WAIT_KEYWORD:
            context.user_data['keyword'] = text.strip().lower()
            StateManager.set(user_id, UserState.WAIT_REPLY)
            await safe_send(context.bot, user_id, await get_text(lang, 'enter_reply'))
            return

        if state == UserState.WAIT_REPLY:
            keyword = context.user_data.get('keyword')
            if keyword:
                await DB.add_auto_reply(0, keyword, text)
                await safe_send(context.bot, user_id, await get_text(lang, 'auto_reply_added', keyword=keyword))
            StateManager.clear(user_id)
            context.user_data.pop('keyword', None)
            return

        # ============================================================
        # حالة: قناة السجلات
        # ============================================================
        if state == UserState.WAIT_LOG_CH:
            try:
                chat = await context.bot.get_chat(text)
                if chat.type == 'channel':
                    await DB.set_setting('log_channel_id', str(chat.id))
                    await safe_send(context.bot, user_id, await get_text(lang, 'admin_log_channel_set', channel=chat.title))
                else:
                    await safe_send(context.bot, user_id, await get_text(lang, 'admin_log_channel_not_channel'))
            except:
                await safe_send(context.bot, user_id, await get_text(lang, 'admin_log_channel_failed'))
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: الحد الأقصى للطول
        # ============================================================
        if state == UserState.WAIT_MAX_LEN:
            try:
                val = int(text)
                if val >= 0:
                    chat_id_sec = context.user_data.get(f'sec_chat_{user_id}')
                    if chat_id_sec:
                        await DB.execute("UPDATE group_security SET max_message_length=? WHERE chat_id=?",
                                         (val, chat_id_sec))
                        await safe_send(context.bot, user_id, f"✅ تم تعيين الحد الأقصى للطول: {val}")
                    else:
                        await safe_send(context.bot, user_id, "❌ خطأ في البيانات")
                else:
                    await safe_send(context.bot, user_id, "❌ يجب أن يكون 0 أو أكبر")
            except:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: عدد التحذيرات
        # ============================================================
        if state == UserState.WAIT_WARN_COUNT:
            try:
                val = int(text)
                if 1 <= val <= 10:
                    chat_id_sec = context.user_data.get(f'sec_chat_{user_id}')
                    if chat_id_sec:
                        await DB.execute("UPDATE group_security SET max_warnings=? WHERE chat_id=?",
                                         (val, chat_id_sec))
                        await safe_send(context.bot, user_id, await get_text(lang, 'warning_count_updated', count=val))
                    else:
                        await safe_send(context.bot, user_id, "❌ خطأ في البيانات")
                else:
                    await safe_send(context.bot, user_id, "❌ بين 1 و 10")
            except:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        # ============================================================
        # حالة: الدعم
        # ============================================================
        if state == UserState.SUPPORT_MODE:
            media_type = None
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
            elif msg.text:
                media_type = 'text'
            else:
                await safe_send(context.bot, user_id, "⚠️ هذا النوع غير مدعوم")
                return

            content = msg.caption or "" if media_type != 'text' else text
            if not content and not media_file_id:
                await safe_send(context.bot, user_id, "❌ أرسل نصاً أو وسيطاً")
                return

            ticket_num = await DB.create_ticket(user_id, update.effective_user.username or "",
                                                content, media_type, media_file_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'support_ticket_created', num=ticket_num))
            StateManager.clear(user_id)
            return

        # ============================================================
        # افتراضي: عرض القائمة الرئيسية
        # ============================================================
        await CommandHandlers.start(update, context)

    @staticmethod
    async def handle_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة رسائل المجموعة - تطبيق الأمان والردود التلقائية"""
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

        # ============================================================
        # 1. التحقق من القفل
        # ============================================================
        locked = await DB.fetchone("SELECT locked FROM chat_locks WHERE chat_id=?", (chat_id,))
        if locked and locked[0] == 1:
            try:
                await update.message.delete()
            except:
                pass
            return

        # ============================================================
        # 2. تطبيق إعدادات الأمان
        # ============================================================
        settings = await DB.get_security_settings(chat_id)

        # 2.1 حذف الروابط
        if settings.get('delete_links', False) and TextUtils.contains_link(text):
            try:
                await update.message.delete()
                penalty = settings.get('auto_penalty', 'none')
                if penalty != 'none':
                    await apply_penalty(context.bot, chat_id, user_id, penalty,
                                        settings.get('auto_mute_duration', 60))
                return
            except:
                pass

        # 2.2 حذف المعرفات
        if settings.get('mentions', False) and TextUtils.contains_mention(text):
            try:
                await update.message.delete()
                penalty = settings.get('auto_penalty', 'none')
                if penalty != 'none':
                    await apply_penalty(context.bot, chat_id, user_id, penalty,
                                        settings.get('auto_mute_duration', 60))
                return
            except:
                pass

        # 2.3 حذف الكلمات المحظورة
        if settings.get('delete_banned_words', False):
            banned_words = await DB.get_banned_words(chat_id)
            for word in banned_words:
                if word in text.lower():
                    try:
                        await update.message.delete()
                        penalty = settings.get('auto_penalty', 'none')
                        if penalty != 'none':
                            await apply_penalty(context.bot, chat_id, user_id, penalty,
                                                settings.get('auto_mute_duration', 60))
                        return
                    except:
                        pass

        # 2.4 حذف أنواع الوسائط المحددة
        media_checks = {
            'delete_videos': 'video',
            'delete_audio': 'audio',
            'delete_animation': 'animation',
            'delete_voice': 'voice',
            'delete_video_note': 'video_note',
            'delete_stickers': 'sticker',
            'delete_documents': 'document',
            'delete_forwarded': 'forward_from',
            'delete_polls': 'poll',
            'delete_games': 'game',
            'delete_service': 'new_chat_members'
        }

        for setting, media_type in media_checks.items():
            if settings.get(setting, False):
                if hasattr(update.message, media_type) and getattr(update.message, media_type) is not None:
                    try:
                        await update.message.delete()
                        penalty = settings.get('delete_penalty', 'none')
                        if penalty != 'none':
                            await apply_penalty(context.bot, chat_id, user_id, penalty,
                                                settings.get('delete_penalty_duration', 0))
                        return
                    except:
                        pass

        # 2.5 التحقق من الطول
        max_len = settings.get('max_message_length', 0)
        if max_len and len(text) > max_len:
            try:
                await update.message.delete()
                penalty = settings.get('auto_penalty', 'none')
                if penalty != 'none':
                    await apply_penalty(context.bot, chat_id, user_id, penalty,
                                        settings.get('auto_mute_duration', 60))
                return
            except:
                pass

        # 2.6 الفيضان (Antiflood)
        if settings.get('antiflood_enabled', False):
            now = TimeUtils.utc_iso()
            row = await DB.fetchone("SELECT message_time FROM user_messages WHERE user_id=? AND chat_id=?",
                                    (user_id, chat_id))
            if row:
                last_time = TimeUtils.safe_parse_iso(row[0])
                if last_time:
                    diff = (TimeUtils.utc_now() - last_time).total_seconds()
                    if diff < settings.get('antiflood_seconds', 10):
                        try:
                            await update.message.delete()
                            penalty = settings.get('antiflood_penalty', 'mute')
                            if penalty != 'none':
                                await apply_penalty(context.bot, chat_id, user_id, penalty, 60)
                            return
                        except:
                            pass
            await DB.execute("INSERT OR REPLACE INTO user_messages (user_id, chat_id, message_time) VALUES (?,?,?)",
                             (user_id, chat_id, now))

        # 2.7 الوضع الليلي
        if settings.get('night_mode_enabled', False):
            now = TimeUtils.mecca_now()
            start = datetime.strptime(settings.get('night_mode_start', '23:00'), '%H:%M').time()
            end = datetime.strptime(settings.get('night_mode_end', '06:00'), '%H:%M').time()
            current_time = now.time()

            is_night = False
            if start <= end:
                is_night = start <= current_time <= end
            else:
                is_night = current_time >= start or current_time <= end

            if is_night:
                action = settings.get('night_mode_action', 'mute')
                if action != 'none':
                    try:
                        await update.message.delete()
                        await apply_penalty(context.bot, chat_id, user_id, action, 60)
                        return
                    except:
                        pass

        # ============================================================
        # 3. الردود التلقائية
        # ============================================================
        ars = await DB.get_auto_reply_settings(chat_id)
        if ars.get('enabled', False):
            if not ars.get('only_admins', False) or await is_authorized_in_group(context.bot, chat_id, user_id):
                reply_data = await DB.get_auto_reply(text.lower(), chat_id)
                if reply_data:
                    try:
                        if reply_data.get('reply_type') == 'text':
                            await update.message.reply_text(reply_data['reply'])
                        elif reply_data.get('reply_type') == 'photo' and reply_data.get('reply_media_id'):
                            await update.message.reply_photo(reply_data['reply_media_id'],
                                                             caption=reply_data['reply'])
                        elif reply_data.get('reply_type') == 'video' and reply_data.get('reply_media_id'):
                            await update.message.reply_video(reply_data['reply_media_id'],
                                                             caption=reply_data['reply'])
                        await _increment_usage_async(chat_id, text.lower())
                    except:
                        pass

