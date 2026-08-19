#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers.py - جميع معالجات البوت (النسخة النهائية الكاملة والمصلحة)
- حفظ المنشورات فورًا مع /done
- إخفاء رسالة تفعيل المجموعة بعد 5 ثوان
- أمر /grant لمنح اشتراك مجاني
- زر منح اشتراك مجاني + حذف مستخدم/قناة/مجموعة في لوحة الأدمن
- إصلاح قائمة الكلمات المحظورة
- دعم القنوات الرقمية
- إصلاحات أمنية ومنطقية
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
                        reward = await DB.claim_referral_reward(referrer)
                        await safe_send(update.effective_chat.bot, referrer,
                                        f"🎁 تمت إحالة `{user_id}` (+{reward} يوم)")

        force_ch = await DB.get_force_subscribe_channel()
        if force_ch and user_id != CONFIG.PRIMARY_OWNER_ID:
            try:
                # دعم المعرف الرقمي
                if force_ch.lstrip('-').isdigit():
                    chat = await context.bot.get_chat(int(force_ch))
                else:
                    chat = await context.bot.get_chat(f"@{force_ch}")
                member = await context.bot.get_chat_member(chat.id, user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton("📢 اشترك", url=f"https://t.me/{force_ch}"),
                        InlineKeyboardButton("✅ تحقق", callback_data=CB.CHECK_SUB)
                    ]])
                    await safe_send(context.bot, user_id, f"⚠️ اشترك في @{force_ch}", reply_markup=kb)
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

        # ✅ منع تكرار زر الأدمن
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
        text = (
            "👨‍💻 **معلومات المطور**\n\n"
            "📌 المعرف: `7983340250`\n"
            "👤 البوت: ريلاكس مانيجر\n"
            "🔗 المعرف: @Reeilaxxbot\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📚 **شرح البوت:**\n\n"
            "🆓 مجاني:\n"
            "• حماية المجموعات\n"
            "• الردود التلقائية\n"
            "• المسابقات\n"
            "• الترحيب والوداع\n\n"
            "💎 مدفوع:\n"
            "• إدارة القنوات\n"
            "• النشر التلقائي\n"
            "• إعادة التدوير\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "📞 للتواصل: @RelaxMggr"
        )
        await safe_send(context.bot, user_id, text)

    @staticmethod
    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        stats = await DB.get_user_stats()
        await safe_send(context.bot, user_id,
                        f"👥 المستخدمين: {stats['users']}\n⛔ المحظورين: {stats['banned']}")

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
        text = await KeyboardFactory._format_security_text(settings)
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
        await DB.execute("INSERT OR IGNORE INTO hidden_admins (chat_id, admin_id, added_by, added_at) VALUES (?,?,?,?)", (chat_id, admin_id, user_id, TimeUtils.sql_iso()))
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

        try:
            all_admins = await context.bot.get_chat_administrators(chat_id)
        except Exception as e:
            logger.error(f"❌ فشل جلب المشرفين: {e}")
            await safe_send(context.bot, user_id, "❌ فشل جلب المشرفين")
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
        if not is_admin and user_id == CONFIG.ANONYMOUS_ADMIN_ID:
            is_admin = True
            is_anonymous = True

        if not is_admin:
            await safe_send(context.bot, user_id, "❌ **أنت لست مشرفاً في هذه المجموعة!**")
            return

        await DB.register_group(chat_id, chat_name, creator_id or user_id, update.effective_chat.username)

        bot_perms = await check_bot_permissions(context.bot, chat_id)
        if not bot_perms.get('can_act', False):
            await safe_send(context.bot, user_id, "⚠️ **البوت ليس مشرفاً!**")
            return

        if creator_id:
            await DB.execute("INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,0)", (chat_id, creator_id))
            await DB.execute("INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?,?)", (creator_id, chat_id))
            invalidate_auth_cache(chat_id, creator_id)

        await DB.execute("INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?,?)", (user_id, chat_id))
        invalidate_auth_cache(chat_id, user_id)

        admin_ids = [a.user.id for a in all_admins if a.user and not a.user.is_bot]
        admin_count = await DB.sync_group_admins(chat_id, admin_ids)

        msg = f"✅ **تم تفعيل المجموعة!**\n\n📌 {chat_name}\n🆔 `{chat_id}`\n"
        if creator_id:
            msg += f"👑 المالك: `{creator_id}`\n"
        msg += f"{'👻 مخفي' if is_anonymous else '👤 مشرف'}: `{user_id}`\n👥 {admin_count} مشرف"

        await safe_send(context.bot, user_id, msg)

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
            except Exception as e:
                logger.error(f"❌ فشل إلغاء الحظر: {e}")
            return

        success, msg = await apply_penalty(context.bot, chat_id, target, action, 60, reason, user_id)
        await safe_send(context.bot, user_id, msg)

    # ========== أمر تعيين الحد الأدنى للفاصل الزمني ==========

    @staticmethod
    async def set_min_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        args = context.args or []
        if not args:
            await safe_send(context.bot, user_id, "📝 /set_min_interval <دقائق>")
            return
        try:
            val = int(args[0])
            if val < 1:
                await safe_send(context.bot, user_id, "❌ الحد الأدنى يجب أن يكون 1 دقيقة على الأقل")
                return
            await DB.set_setting('min_publish_interval', str(val))
            await safe_send(context.bot, user_id, f"✅ تم تعيين الحد الأدنى إلى {val} دقيقة")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")

    # ========== أمر منح اشتراك مجاني ==========

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
        plan_row = await DB.fetchone("SELECT id FROM plans WHERE is_gift=1 LIMIT 1")
        if not plan_row:
            plan_row = await DB.fetchone("SELECT id FROM plans WHERE is_active=1 AND is_gift=0 LIMIT 1")
        plan_id = plan_row[0] if plan_row else None
        success = await DB.grant_subscription_days(target_id, days, plan_id=plan_id, provider='manual')
        if success:
            await safe_send(context.bot, user_id, f"✅ تم منح {days} يوم للمستخدم `{target_id}`")
        else:
            await safe_send(context.bot, user_id, "❌ فشل المنح - تحقق من السجلات")

    # ========== أوامر الهدايا ==========

    @staticmethod
    async def gift_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        plans = await DB.get_gift_plans()
        if not plans:
            await safe_send(context.bot, user_id, "📭 لا توجد خطط متاحة حالياً.")
            return
        kb = []
        for plan in plans:
            kb.append([InlineKeyboardButton(f"🎁 {plan['days']} يوم - {plan['price']} ⭐", callback_data=f"buy_gift:{plan['id']}")])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)])
        await safe_send(context.bot, user_id, "💎 **شراء كود هدية**\n\nاختر المدة المناسبة:", reply_markup=InlineKeyboardMarkup(kb))

    @staticmethod
    async def redeem_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
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

        try:
            if base_data in [CB.MAIN, CB.BACK]:
                await query.answer()
                await CommandHandlers.start(update, context)
                return
            if base_data == CB.CANCEL:
                StateManager.clear(user_id)
                await query.answer("❌ تم الإلغاء")
                return
            if base_data == CB.HELP:
                await query.answer()
                await CommandHandlers.help_command(update, context)
                return
            if base_data == CB.TRIAL:
                if await DB.has_used_trial(user_id):
                    await query.edit_message_text(await get_text(lang, 'trial_used'))
                    return
                days = await DB.activate_trial(user_id)
                await query.edit_message_text(await get_text(lang, 'trial_activated', days=days))
                return
            if base_data == CB.DEVELOPER:
                await query.answer()
                await CommandHandlers.developer(update, context)
                return
            if base_data == CB.SUBSCRIBE:
                await query.answer()
                await CommandHandlers.subscribe(update, context)
                return
            if base_data == CB.SUPPORT:
                await query.answer()
                await CommandHandlers.support(update, context)
                return
            if base_data == CB.LANGUAGE:
                await query.answer()
                await CommandHandlers.language(update, context)
                return
            if base_data == CB.CHECK_SUB:
                await query.answer()
                await CommandHandlers.start(update, context)
                return

            if base_data == CB.SETTINGS:
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                await query.edit_message_text(f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}", reply_markup=KeyboardFactory.build("settings", lang=lang))
                await query.answer()
                return
            if base_data == CB.TOGGLE_AUTO:
                await DB.set_auto_publish(user_id, not await DB.get_auto_publish_status(user_id))
                await query.answer("🔄 تم التحديث")
                await query.edit_message_text(f"⚙️ **الإعدادات**\n\n📤 النشر: {'✅' if await DB.get_auto_publish_status(user_id) else '❌'}\n♻️ التدوير: {'✅' if await DB.get_auto_recycle_status(user_id) else '❌'}", reply_markup=KeyboardFactory.build("settings", lang=lang))
                return
            if base_data == CB.TOGGLE_REC:
                await DB.set_auto_recycle(user_id, not await DB.get_auto_recycle_status(user_id))
                await query.answer("🔄 تم التحديث")
                await query.edit_message_text(f"⚙️ **الإعدادات**\n\n📤 النشر: {'✅' if await DB.get_auto_publish_status(user_id) else '❌'}\n♻️ التدوير: {'✅' if await DB.get_auto_recycle_status(user_id) else '❌'}", reply_markup=KeyboardFactory.build("settings", lang=lang))
                return

            if base_data == CB.PLANS:
                await query.edit_message_text(await get_text(lang, 'plan_selector'), reply_markup=KeyboardFactory.build("plans", lang=lang))
                await query.answer()
                return

            if data.startswith("buy_sub_"):
                days = int(data.split("_")[-1])
                plan_name = {1: "يوم", 7: "أسبوع", 30: "شهر", 90: "3 أشهر"}.get(days)
                if not plan_name:
                    await query.answer("❌ باقة غير موجودة", show_alert=True)
                    return
                plan = await DB.get_plan_by_name(plan_name)
                if not plan:
                    await query.answer("❌ باقة غير موجودة", show_alert=True)
                    return
                invoice = await DB.create_invoice(user_id, plan['id'], plan['price'])
                await context.bot.send_invoice(
                    chat_id=user_id,
                    title=f"💎 {plan['name']}",
                    description=plan['description'],
                    payload=json.dumps({'plan_id': plan['id'], 'invoice': invoice, 'type': 'subscription'}),
                    provider_token="",
                    currency="XTR",
                    prices=[LabeledPrice(plan['name'], plan['price'])]
                )
                await query.message.delete()
                return

            if base_data == CB.INVOICES:
                invoices = await DB.get_user_invoices(user_id, 10)
                text = "🧾 **فواتيري**\n\n" + "\n".join(f"• #{inv['number']} - {inv['amount']} ⭐" for inv in invoices) if invoices else "📭 لا توجد فواتير"
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]]))
                await query.answer()
                return

            if base_data == CB.REFERRAL:
                stats = await DB.get_referral_stats(user_id)
                code = await DB.get_referral_code(user_id)
                await query.edit_message_text(f"🔗 **الإحالات**\n\n🔗 `https://t.me/{CONFIG.BOT_USERNAME}?start=ref_{code}`\n👥 {stats['total']}\n🎁 {stats['available']} يوم", reply_markup=KeyboardFactory.build("referral", lang=lang))
                await query.answer()
                return
            if base_data == CB.REF_CLAIM:
                days = await DB.claim_referral_reward(user_id)
                await query.edit_message_text(f"✅ {days} يوم!" if days else "📭 لا توجد")
                return
            if base_data == CB.REF_LIST:
                referrals = await DB.get_referrals_list(user_id)
                await query.edit_message_text("📋 **المُحالين**\n\n" + "\n".join([f"• `{r}`" for r in referrals[:20]]) if referrals else "📭 لا يوجد")
                return

            if base_data in [CB.REM_TOGGLE_SUB, CB.REM_TOGGLE_DAILY, CB.REM_TOGGLE_WEEKLY]:
                s = await DB.get_reminder_settings(user_id)
                if base_data == CB.REM_TOGGLE_SUB:
                    await DB.update_reminder_settings(user_id, subscription_reminder=not s.get('subscription_reminder', False))
                elif base_data == CB.REM_TOGGLE_DAILY:
                    await DB.update_reminder_settings(user_id, daily_stats_reminder=not s.get('daily_stats_reminder', False))
                else:
                    await DB.update_reminder_settings(user_id, weekly_report=not s.get('weekly_report', False))
                settings = await DB.get_reminder_settings(user_id)
                await query.edit_message_text(f"⏰ **التذكيرات**\n\n🔔 الاشتراك: {'✅' if settings.get('subscription_reminder', False) else '❌'}\n📊 يومي: {'✅' if settings.get('daily_stats_reminder', False) else '❌'}\n📈 أسبوعي: {'✅' if settings.get('weekly_report', False) else '❌'}", reply_markup=KeyboardFactory.build("reminder", lang=lang))
                return
            if base_data == CB.REMINDER:
                settings = await DB.get_reminder_settings(user_id)
                await query.edit_message_text(f"⏰ **التذكيرات**\n\n🔔 الاشتراك: {'✅' if settings.get('subscription_reminder', False) else '❌'}\n📊 يومي: {'✅' if settings.get('daily_stats_reminder', False) else '❌'}\n📈 أسبوعي: {'✅' if settings.get('weekly_report', False) else '❌'}", reply_markup=KeyboardFactory.build("reminder", lang=lang))
                return
            if base_data == CB.REM_SET_DAYS:
                StateManager.set(user_id, UserState.WAIT_REM_DAYS)
                await query.edit_message_text("📅 أرسل عدد الأيام (1-30):")
                return
            if data.startswith(CB.REM_LANG + ":"):
                await DB.update_reminder_settings(user_id, notification_lang=data.split(":")[-1])
                await query.edit_message_text("✅ تم تعيين لغة التذكير")
                return

            if base_data == CB.TRANSLATION:
                await query.edit_message_text(f"🌐 الترجمة: {await DB.get_user_language(user_id)}", reply_markup=KeyboardFactory.build("translation", lang=lang))
                await query.answer()
                return
            if base_data == CB.TRANS_OFF:
                await DB.set_user_language(user_id, 'off')
                await query.edit_message_text("✅ تم إيقاف الترجمة")
                return
            if data.startswith(CB.TRANS_SET):
                await DB.set_user_language(user_id, data.split(":")[-1])
                await query.edit_message_text("✅ تم تعيين اللغة")
                return

            if base_data == CB.CONTESTS:
                await CommandHandlers.contests(update, context)
                return
            if base_data == CB.CONTEST_WINNERS:
                winners = await DB.get_contest_winners(10)
                text = "🏆 **الفائزون**\n\n" + "\n".join(f"• {w['title']} → `{w['winner_id']}`" for w in winners) if winners else "📭 لا يوجد فائزون"
                await query.edit_message_text(text)
                return
            if data.startswith(CB.CONTEST_JOIN):
                cid = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
                context.user_data['contest_join'] = cid
                await safe_send(context.bot, user_id, "📝 أرسل إجابتك:")
                return
            if base_data == CB.SUPPORT_TICKET:
                StateManager.set(user_id, UserState.SUPPORT_MODE)
                await safe_send(context.bot, user_id, "📞 أرسل رسالتك:")
                return

            if base_data == CB.CH_ADD:
                StateManager.set(user_id, UserState.WAIT_CHANNEL)
                await query.edit_message_text("📡 أرسل معرف القناة:")
                return
            if base_data == CB.CH_LIST:
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return
            if data.startswith(CB.CH_SEL + ":"):
                ch_id = int(data.split(":")[-1])
                await DB.set_active_channel(user_id, ch_id)
                await query.edit_message_text("✅ تم تحديد القناة!")
                return
            if data.startswith(CB.CH_DEL + ":"):
                ch_id = int(data.split(":")[-1])
                await DB.delete_channel(user_id, ch_id)
                await query.answer("✅ تم الحذف")
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return
            if data.startswith(CB.CH_STATS + ":"):
                ch_id = int(data.split(":")[-1])
                stats = await DB.get_channel_stats(ch_id)
                await query.edit_message_text(f"📊 **إحصائيات القناة**\n\n📝 المجموع: {stats['total']}\n✅ المنشورة: {stats['published']}\n⏳ غير المنشورة: {stats['unpublished']}")
                return

            if base_data == CB.POST_ADD:
                if not await DB.has_active_subscription(user_id):
                    await query.answer("❌ انتهى اشتراكك!", show_alert=True)
                    return
                active = await DB.get_active_channel(user_id)
                if not active:
                    await query.edit_message_text("❌ لا توجد قناة نشطة")
                    return
                StateManager.set(user_id, UserState.ADDING_POSTS)
                await query.edit_message_text("📥 أرسل المنشورات الآن (واحد تلو الآخر).\nعند الانتهاء أرسل /done")
                return
            if base_data == CB.POST_PUB:
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
                await CallbackHandlers._publish_single(context.bot, active, ch_info['channel_id'], post)
                await query.edit_message_text("✅ تم النشر!")
                return
            if base_data == CB.POST_LIST:
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return
            if base_data == CB.POST_REC:
                active = await DB.get_active_channel(user_id)
                if active:
                    count = await DB.reset_posts(active)
                    await query.edit_message_text(f"♻️ {count} منشور!")
                return
            if base_data == CB.PUB_ALL:
                if not await DB.has_active_subscription(user_id):
                    await query.answer("❌ انتهى اشتراكك!", show_alert=True)
                    return
                channels = await DB.get_user_channels(user_id)
                count = 0
                for ch in channels:
                    post = await DB.get_next_post(ch['id'])
                    if not post:
                        continue
                    ch_info = await DB.get_channel_info(ch['id'])
                    await CallbackHandlers._publish_single(context.bot, ch['id'], ch_info['channel_id'], post)
                    count += 1
                await query.edit_message_text(f"✅ تم نشر {count} منشور" if count else "📭 لا توجد منشورات للنشر")
                return
            if data.startswith(CB.POST_DEL + ":"):
                post_id = int(data.split(":")[-1])
                await DB.execute("DELETE FROM posts WHERE id=?", (post_id,))
                await query.edit_message_text("✅ تم حذف المنشور!")
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return
            if data.startswith(CB.POST_CLEAR + ":"):
                ch_id = int(data.split(":")[-1])
                await DB.execute("DELETE FROM posts WHERE channel_db_id=?", (ch_id,))
                await query.edit_message_text("✅ تم مسح جميع المنشورات!")
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if base_data == CB.GROUPS:
                await query.answer()
                groups = await DB.get_user_groups(user_id)
                if not groups:
                    await query.edit_message_text("📭 لا توجد مجموعات", reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("➕ إضافة مجموعة", url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")
                    ]]))
                    return
                text = "👥 **مجموعاتي**\n\n"
                kb = []
                for gid, name, username, banned in groups:
                    text += f"{'✅' if not banned else '⛔'} {name}\n"
                    kb.append([InlineKeyboardButton(f"🛡️ إعدادات {name[:15]}", callback_data=f"{CB.GRP_SET}:{gid}")])
                kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)])
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return
            if data.startswith(CB.GRP_SET + ":"):
                chat_id = int(data.split(":")[-1])
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    await query.answer("❌ لا صلاحية", show_alert=True)
                    return
                settings = await DB.get_security_settings(chat_id)
                text = await KeyboardFactory._format_security_text(settings)
                kb = KeyboardFactory.build("security", chat_id, lang=lang)
                await query.edit_message_text(text, reply_markup=kb)
                return

            if base_data == CB.ADMIN:
                if CONFIG.is_developer(user_id):
                    await query.edit_message_text("👑 لوحة الأدمن", reply_markup=KeyboardFactory.build("admin_panel", lang=lang))
                else:
                    await query.answer(await get_text(lang, 'unauthorized'), show_alert=True)
                return

            if data == "admin_grant_free":
                if not CONFIG.is_developer(user_id):
                    await query.answer("❌ غير مصرح", show_alert=True)
                    return
                StateManager.set(user_id, UserState.WAIT_GRANT_FREE)
                await query.edit_message_text("🎁 أرسل معرف المستخدم ثم عدد الأيام هكذا:\n`123456789 365`")
                return

            if data == "admin_del_user":
                if not CONFIG.is_developer(user_id):
                    await query.answer("❌ غير مصرح", show_alert=True)
                    return
                StateManager.set(user_id, UserState.WAIT_DEL_USER)
                await query.edit_message_text("🗑️ أرسل معرف المستخدم لحذفه نهائيًا:")
                return

            if data.startswith("del_ch:"):
                if not CONFIG.is_developer(user_id):
                    await query.answer("❌ غير مصرح", show_alert=True)
                    return
                ch_id = int(data.split(":")[-1])
                await DB.execute("DELETE FROM user_channels WHERE id=?", (ch_id,))
                await DB.execute("DELETE FROM posts WHERE channel_db_id=?", (ch_id,))
                await DB.execute("DELETE FROM schedule WHERE channel_db_id=?", (ch_id,))
                await DB.execute("DELETE FROM last_publish WHERE channel_db_id=?", (ch_id,))
                await query.answer("✅ تم حذف القناة")
                await CallbackHandlers._handle_admin(update, context, query, user_id, lang)
                return

            if data.startswith("del_gr:"):
                if not CONFIG.is_developer(user_id):
                    await query.answer("❌ غير مصرح", show_alert=True)
                    return
                gr_id = int(data.split(":")[-1])
                await DB.execute("DELETE FROM bot_groups WHERE chat_id=?", (gr_id,))
                await DB.execute("DELETE FROM user_groups_link WHERE chat_id=?", (gr_id,))
                await DB.execute("DELETE FROM hidden_owner_groups WHERE chat_id=?", (gr_id,))
                await DB.execute("DELETE FROM hidden_admins WHERE chat_id=?", (gr_id,))
                await DB.execute("DELETE FROM group_admins WHERE chat_id=?", (gr_id,))
                await DB.execute("DELETE FROM group_security WHERE chat_id=?", (gr_id,))
                await query.answer("✅ تم حذف المجموعة")
                await CallbackHandlers._handle_admin(update, context, query, user_id, lang)
                return

            if data == "status_only":
                await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
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
                    await query.answer("❌ غير مصرح", show_alert=True)
                    return
                await query.edit_message_text("📅 **جدولة القناة**", reply_markup=KeyboardFactory.build("channel_settings", chat_id=ch_id, lang=lang))
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
            if data.startswith("contest_") or data.startswith(CB.DECLARE_WINNER_SEL):
                await CallbackHandlers._handle_contests(update, context, query, user_id)
                return
            if data in (CB.ADMIN_IMPORT_REPLIES, CB.ADMIN_IMPORT_GITHUB):
                await CallbackHandlers._handle_import(update, context, query, user_id)
                return
            if data.startswith("lang_"):
                await DB.set_user_language(user_id, data.split("_")[-1])
                await query.answer("✅")
                await CommandHandlers.start(update, context)
                return
            if data.startswith("buy_gift:"):
                plan_id = int(data.split(":")[-1])
                plan = await DB.get_gift_plan(plan_id)
                if not plan:
                    await query.answer("❌ خطة غير موجودة", show_alert=True)
                    return
                invoice = await DB.create_invoice(user_id, plan_id, plan['price'], currency='XTR', provider='xtr_gift')
                await context.bot.send_invoice(
                    chat_id=user_id,
                    title=f"🎁 كود هدية {plan['days']} يوم",
                    description=f"ستحصل على كود هدية لمدة {plan['days']} يوم يمكنك إرساله لأي شخص.",
                    payload=json.dumps({'gift_plan_id': plan_id, 'invoice': invoice, 'type': 'gift'}),
                    provider_token="",
                    currency="XTR",
                    prices=[LabeledPrice(f"{plan['days']} يوم", plan['price'])]
                )
                await query.message.delete()
                return

            await query.answer("⚠️ غير متوفر", show_alert=True)

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
            if post['media_type'] == 'photo' and post['media_file_id']:
                await bot.send_photo(ch_tele, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
            elif post['media_type'] == 'video' and post['media_file_id']:
                await bot.send_video(ch_tele, post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
            else:
                await bot.send_message(ch_tele, post['text'][:4096] if post['text'] else ".")
            await DB.mark_post_published(post['id'])
            await DB.update_next_publish(ch_db_id)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"❌ فشل النشر التلقائي: {e}")
            await DB.increment_post_fail(post['id'])

    @staticmethod
    async def _show_channel_list(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        channels = await DB.get_user_channels(user_id)
        if not channels:
            await query.edit_message_text("📭 لا توجد قنوات!\nاضغط للإضافة:", reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)
            ], [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]]))
            return
        text = "📡 **قنواتي**\n\n"
        kb = []
        for ch in channels:
            text += f"{'✅' if not ch['banned'] else '🚫'} {ch['channel_name']} (`{ch['channel_id']}`)\n"
            kb.append([
                InlineKeyboardButton(f"📌 {ch['channel_name'][:20]}", callback_data=f"{CB.CH_SEL}:{ch['id']}"),
                InlineKeyboardButton("📅", callback_data=f"sched_open:{ch['id']}"),
                InlineKeyboardButton("📊", callback_data=f"{CB.CH_STATS}:{ch['id']}"),
                InlineKeyboardButton("🗑️", callback_data=f"{CB.CH_DEL}:{ch['id']}")
            ])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

    @staticmethod
    async def _show_post_list(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        active = await DB.get_active_channel(user_id)
        if not active:
            await query.edit_message_text("❌ لا توجد قناة نشطة")
            return
        posts = await DB.get_user_posts(active, 10)
        text = "📋 **منشوراتي**\n\n"
        kb = []
        for p in posts:
            text += f"🆔 {p['id']}: {(p['text'] or '')[:30]}\n"
            kb.append([InlineKeyboardButton(f"🗑️ حذف {p['id']}", callback_data=f"{CB.POST_DEL}:{p['id']}")])
        kb.append([InlineKeyboardButton("🧹 مسح الكل", callback_data=f"{CB.POST_CLEAR}:{active}")])
        kb.append([InlineKeyboardButton("♻️ إعادة التدوير", callback_data=CB.POST_REC)])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)])
        await query.edit_message_text(text if posts else "📭 لا يوجد", reply_markup=InlineKeyboardMarkup(kb))

    @staticmethod
    async def _handle_security(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("sec_", "")
        chat_id = int(parts[1]) if parts[1].lstrip('-').isdigit() else 0
        if not chat_id:
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("❌ غير مصرح", show_alert=True)
            return

        field_map = {
            "links": "delete_links", "mentions": "mentions", "slow": "slow_mode",
            "video": "delete_videos", "audio": "delete_audio", "anim": "delete_animation",
            "service": "delete_service", "doc": "delete_documents", "sticker": "delete_stickers",
            "forward": "delete_forwarded", "poll": "delete_polls", "game": "delete_games",
            "voice": "delete_voice", "videonote": "delete_video_note",
            "welcome": "welcome_enabled", "goodbye": "goodbye_enabled",
            "flood": "antiflood_enabled", "night": "night_mode_enabled",
            "banned_words": "delete_banned_words", "approve_join": "auto_approve_join",
            "reject_join": "auto_reject_join"
        }

        if action in field_map:
            col = field_map[action]
            cur = await DB.fetchone(f"SELECT {col} FROM group_security WHERE chat_id=?", (chat_id,))
            new_val = 1 - (cur[0] if cur else 0)
            await DB.execute(f"UPDATE group_security SET {col}=? WHERE chat_id=?", (new_val, chat_id))
            settings = await DB.get_security_settings(chat_id)
            text = await KeyboardFactory._format_security_text(settings)
            await query.edit_message_text(text, reply_markup=KeyboardFactory.build("security", chat_id, lang=lang))
            await query.answer()
            return

        if action == "enable_all":
            for col in field_map.values():
                await DB.execute(f"UPDATE group_security SET {col}=1 WHERE chat_id=?", (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            await query.edit_message_text(await KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id, lang=lang))
            await query.answer()
            return
        if action == "disable_all":
            for col in field_map.values():
                await DB.execute(f"UPDATE group_security SET {col}=0 WHERE chat_id=?", (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            await query.edit_message_text(await KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id, lang=lang))
            await query.answer()
            return
        if action == "toggle_banned":
            cur = await DB.fetchone("SELECT delete_banned_words FROM group_security WHERE chat_id=?", (chat_id,))
            new_val = 1 - (cur[0] if cur else 0)
            await DB.execute("UPDATE group_security SET delete_banned_words=? WHERE chat_id=?", (new_val, chat_id))
            await query.edit_message_text(f"🔄 حذف الكلمات المحظورة: {'مفعل ✅' if new_val else 'معطل ❌'}")
            await query.answer()
            return
        if action == "mute_duration":
            StateManager.set(user_id, UserState.WAIT_MUTE_DURATION)
            context.user_data[f"sec_chat_{user_id}"] = chat_id
            await query.edit_message_text("⏱️ أرسل مدة الكتم بالدقائق (1-1440):")
            await query.answer()
            return
        if action == "maxlen":
            StateManager.set(user_id, UserState.WAIT_MAX_LEN)
            context.user_data[f"sec_chat_{user_id}"] = chat_id
            await query.edit_message_text("📏 أرسل الحد الأقصى للطول:")
            await query.answer()
            return
        if action == "warn":
            settings = await DB.get_security_settings(chat_id)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 العدد", callback_data=f"sec_warn_count:{chat_id}"), InlineKeyboardButton("⚖️ العقوبة", callback_data=f"sec_warn_penalty:{chat_id}")],
                [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CB.GRP_SET}:{chat_id}")]
            ])
            await query.edit_message_text(f"⚠️ **التحذيرات**\n\nالحد: {settings.get('max_warnings', 3)}\nالعقوبة: {settings.get('warn_penalty', 'ban')}", reply_markup=kb)
            await query.answer()
            return
        if action == "warn_count":
            StateManager.set(user_id, UserState.WAIT_WARN_COUNT)
            context.user_data[f"sec_chat_{user_id}"] = chat_id
            await query.edit_message_text("📝 أرسل العدد (1-10):")
            return
        if action == "warn_penalty":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🛑 حظر", callback_data=f"sec_set_warn_penalty:{chat_id}:ban"), InlineKeyboardButton("🔇 كتم", callback_data=f"sec_set_warn_penalty:{chat_id}:mute")],
                [InlineKeyboardButton("🔙 رجوع", callback_data=f"sec_warn:{chat_id}")]
            ])
            await query.edit_message_text("⚖️ اختر العقوبة:", reply_markup=kb)
            return
        if action == "set_warn_penalty":
            penalty = parts[2] if len(parts) > 2 else 'ban'
            await DB.execute("UPDATE group_security SET warn_penalty=? WHERE chat_id=?", (penalty, chat_id))
            await query.edit_message_text(f"✅ تم التعيين: {penalty}")
            return
        if action == "del_pen":
            kb = KeyboardFactory.build("penalty", chat_id, lang=lang)
            await query.edit_message_text("⚖️ عقوبة الحذف:", reply_markup=kb)
            return
        if action == "penalty":
            kb = KeyboardFactory.build("penalty", chat_id, lang=lang)
            await query.edit_message_text("⚖️ العقوبة:", reply_markup=kb)
            return
        if action == "adv_act":
            await query.edit_message_text("🛠️ إجراءات:", reply_markup=KeyboardFactory.build("advanced_actions", chat_id, lang=lang))
            return
        if action == "act_log":
            logs = await DB.get_admin_logs(chat_id, 20)
            text = "📜 **السجل**\n\n" + "\n".join(f"• {log['action']} → {log['target_id'] or '-'}" for log in logs) if logs else "📭 لا توجد سجلات"
            await query.edit_message_text(text)
            return
        if action == "auto_reply_menu":
            await query.edit_message_text("📝 الردود:", reply_markup=KeyboardFactory.build("auto_reply_manage", chat_id, lang=lang))
            return
        if action == "close":
            try:
                await query.message.delete()
            except:
                pass
            return

    @staticmethod
    async def _handle_banned_words_direct(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        parts = query.data.split(":")
        chat_id = int(parts[1]) if len(parts) > 1 and parts[1].lstrip('-').isdigit() else None
        if not chat_id:
            await query.answer("❌ خطأ في المعرف", show_alert=True)
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("❌ غير مصرح", show_alert=True)
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة كلمة", callback_data=f"ban_add:{chat_id}"), InlineKeyboardButton("📋 قائمة الكلمات", callback_data=f"ban_list:{chat_id}")],
            [InlineKeyboardButton("🗑️ حذف كلمة", callback_data=f"ban_rem:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"sec_close:{chat_id}")]
        ])
        try:
            await query.edit_message_text("🚫 **إدارة الكلمات المحظورة**", reply_markup=kb)
        except BadRequest:
            await safe_send(context.bot, user_id, "🚫 **إدارة الكلمات المحظورة**", reply_markup=kb)
        await query.answer()

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
            channels = await DB.fetchall("SELECT id, channel_id, channel_name, banned FROM user_channels LIMIT 50")
            if not channels:
                await query.edit_message_text("📭 لا توجد قنوات")
                return
            text = "📡 **القنوات**\n\n"
            kb = []
            for ch in channels:
                text += f"{'✅' if not ch[3] else '🚫'} {ch[2]} (`{ch[1]}`)\n"
                kb.append([InlineKeyboardButton(f"🗑️ حذف {ch[2][:20]}", callback_data=f"del_ch:{ch[0]}")])
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        elif data == CB.ADMIN_BANNED_CH:
            channels = await DB.fetchall("SELECT channel_id, channel_name FROM user_channels WHERE banned=1")
            await query.edit_message_text("🚫 **القنوات المحظورة**\n\n" + "\n".join(f"• {c[1]}" for c in channels) if channels else "📭 لا يوجد")
        elif data == CB.ADMIN_ACTIVATE_CH:
            await DB.execute("UPDATE user_channels SET banned=0 WHERE banned=1")
            await query.edit_message_text("✅ تم تفعيل الكل")
        elif data == CB.ADMIN_GROUPS:
            groups = await DB.fetchall("SELECT chat_id, chat_name, banned FROM bot_groups LIMIT 50")
            if not groups:
                await query.edit_message_text("📭 لا توجد مجموعات")
                return
            text = "👥 **المجموعات**\n\n"
            kb = []
            for g in groups:
                text += f"{'✅' if not g[2] else '🚫'} {g[1]} (`{g[0]}`)\n"
                kb.append([InlineKeyboardButton(f"🗑️ حذف {g[1][:20]}", callback_data=f"del_gr:{g[0]}")])
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        elif data == CB.ADMIN_BANNED_GR:
            groups = await DB.fetchall("SELECT chat_id, chat_name FROM bot_groups WHERE banned=1")
            await query.edit_message_text("🚫 **المجموعات المحظورة**\n\n" + "\n".join(f"• {g[1]}" for g in groups) if groups else "📭 لا يوجد")
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
                await query.answer("❌ غير مصرح", show_alert=True)
                return
            StateManager.set(user_id, UserState.WAIT_GRANT_FREE)
            await query.edit_message_text("🎁 أرسل معرف المستخدم ثم عدد الأيام هكذا:\n`123456789 365`")
        elif data == "admin_del_user":
            if not CONFIG.is_developer(user_id):
                await query.answer("❌ غير مصرح", show_alert=True)
                return
            StateManager.set(user_id, UserState.WAIT_DEL_USER)
            await query.edit_message_text("🗑️ أرسل معرف المستخدم لحذفه نهائيًا:")
        elif data == CB.ADMIN_RAM:
            await query.edit_message_text(f"🖥️ الرام: {get_ram_usage()['percent']}%")
        elif data == CB.ADMIN_STATS:
            stats = await DB.get_user_stats()
            await query.edit_message_text(f"👥 {stats['users']} مستخدم")
        elif data == CB.ADMIN_METRICS:
            m = METRICS.get_stats()
            await query.edit_message_text(f"📊 API: {m['api_calls_last_hour']}\n⚠️ أخطاء: {m['errors_last_hour']}")
        elif data == CB.ADMIN_BACKUP:
            backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(PATHS.DB, backup_file)
            with open(backup_file, 'rb') as f:
                await context.bot.send_document(chat_id=user_id, document=f, filename=backup_file.name)
        elif data == CB.ADMIN_RESTORE:
            backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
            if not backups:
                await query.edit_message_text("📭 لا توجد نسخ")
            else:
                kb = [[InlineKeyboardButton(b.name, callback_data=f"{CB.ADMIN_RESTORE_SEL}:{b.name}")] for b in backups[:10]]
                await query.edit_message_text("🔄 اختر النسخة:", reply_markup=InlineKeyboardMarkup(kb))
        elif data.startswith(CB.ADMIN_RESTORE_SEL + ":"):
            filepath = PATHS.BACKUPS / data.split(":")[-1]
            if filepath.exists():
                shutil.copy2(filepath, PATHS.DB)
                await query.edit_message_text("✅ تمت الاستعادة")
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
            await query.edit_message_text("📋 **التذاكر**\n\n" + "\n".join(f"#{t['ticket_number']} - `{t['user_id']}`" for t in tickets) if tickets else "📭 لا توجد تذاكر")
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
            await query.edit_message_text("📊 **الردود**\n\n" + "\n".join(f"• {kw}: {cnt}" for kw, cnt in stats) if stats else "📭 لا يوجد")
        elif data == CB.ADMIN_ADD_REPLY:
            StateManager.set(user_id, UserState.WAIT_KEYWORD)
            await query.edit_message_text("📝 أرسل الكلمة:")
        elif data == CB.ADMIN_LIST_REPLIES:
            replies = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=0 LIMIT 20")
            await query.edit_message_text("📋 **الردود**\n\n" + "\n".join(f"• {r[0]} ({r[1]})" for r in replies) if replies else "📭 لا يوجد")
        elif data == CB.ADMIN_DEL_REPLY:
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = -1
            await query.edit_message_text("🗑️ أرسل الكلمة:")
        elif data == CB.ADMIN_BANNED_WORDS:
            words = await DB.get_banned_words(-1)
            await query.edit_message_text("🚫 **الكلمات المحظورة**\n\n" + "\n".join(words) if words else "📭 لا يوجد")
        elif data == CB.ADMIN_ADD_BANNED:
            StateManager.set(user_id, UserState.WAIT_GLOBAL_BAN)
            await query.edit_message_text("🚫 أرسل الكلمة:")
        elif data == CB.ADMIN_LIST_BANNED:
            words = await DB.get_banned_words(-1)
            await query.edit_message_text("🚫 **الكلمات**\n\n" + "\n".join(words) if words else "📭 لا يوجد")
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
            await DB.delete_contest(int(data.split(":")[-1]), user_id)
            await query.edit_message_text("✅ تم حذف المسابقة")
        elif data == CB.ADMIN_EXPORT_REPLIES:
            count = await export_auto_replies(-1)
            await query.edit_message_text(f"✅ تم تصدير {count} رد")
        elif data == CB.ADMIN_REFRESH_CACHE:
            _auto_reply_cache.invalidate()
            await query.edit_message_text("🔄 تم تحديث الكاش")
        elif data in (CB.ADMIN_IMPORT_REPLIES, CB.ADMIN_IMPORT_GITHUB):
            await CallbackHandlers._handle_import(update, context, query, user_id)
        else:
            try:
                await query.answer("⚠️ غير متوفر", show_alert=True)
            except:
                pass

    @staticmethod
    async def _handle_auto_reply(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id)
        parts = query.data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("auto_reply_", "")
        chat_id = int(parts[1]) if parts[1].lstrip('-').isdigit() else 0
        if not chat_id:
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("❌ غير مصرح", show_alert=True)
            return

        settings = await DB.get_auto_reply_settings(chat_id)
        if action == "toggle":
            await DB.update_auto_reply_settings(chat_id, enabled=not settings.get('enabled', False))
            _auto_reply_cache.invalidate()
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return
        if action == "menu":
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return
        if action == "admins":
            await DB.update_auto_reply_settings(chat_id, only_admins=not settings.get('only_admins', False))
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return
        if action == "reset":
            await DB.reset_auto_replies(chat_id)
            _auto_reply_cache.invalidate()
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return
        if action == "add":
            StateManager.set(user_id, UserState.WAIT_AUTO_KEY)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text("📝 أرسل الكلمة المفتاحية:")
            return
        if action == "del":
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text("🗑️ أرسل الكلمة لحذفها:")
            return
        if action == "stats":
            rows = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? LIMIT 10", (chat_id,))
            await query.edit_message_text("📊 **الإحصائيات**\n\n" + "\n".join(f"• {r[0]}: {r[1]}" for r in rows) if rows else "📭 لا يوجد")
            return
        if action == "list":
            rows = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=? LIMIT 20", (chat_id,))
            await query.edit_message_text("📋 **الردود**\n\n" + "\n".join(f"• {r[0]}" for r in rows) if rows else "📭 لا يوجد")
            return

    @staticmethod
    async def _show_auto_reply_menu(update, context, query, user_id, lang):
        if not lang:
            lang = await DB.get_user_language(user_id)
        parts = query.data.split(":")
        if len(parts) < 2:
            return
        chat_id = int(parts[1]) if parts[1].lstrip('-').isdigit() else 0
        if not chat_id:
            return
        settings = await DB.get_auto_reply_settings(chat_id)
        enabled = settings.get('enabled', False)
        status = "🟢 مفعل" if enabled else "🔴 معطل"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{status}", callback_data="status_only")],
            [InlineKeyboardButton("🔄 " + ("إيقاف" if enabled else "تشغيل") + " الردود", callback_data=f"auto_reply_toggle:{chat_id}")],
            [InlineKeyboardButton("👤 للمشرفين فقط", callback_data=f"auto_reply_admins:{chat_id}")],
            [InlineKeyboardButton("➕ إضافة رد", callback_data=f"auto_reply_add:{chat_id}"), InlineKeyboardButton("🗑️ حذف رد", callback_data=f"auto_reply_del:{chat_id}")],
            [InlineKeyboardButton("📋 قائمة", callback_data=f"auto_reply_list:{chat_id}"), InlineKeyboardButton("📊 إحصائيات", callback_data=f"auto_reply_stats:{chat_id}")],
            [InlineKeyboardButton("🗑️ حذف الكل", callback_data=f"auto_reply_reset:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"sec_close:{chat_id}")]
        ])
        await query.edit_message_text("📝 **إدارة الردود التلقائية**", reply_markup=kb)

    @staticmethod
    async def _handle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, query, user_id):
        parts = query.data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("sched_", "")
        ch_id = int(parts[1]) if parts[1].lstrip('-').isdigit() else 0
        if not ch_id:
            return
        row = await DB.fetchone("SELECT user_id FROM user_channels WHERE id=?", (ch_id,))
        if not row or row[0] != user_id:
            await query.answer("❌ غير مصرح", show_alert=True)
            return
        if action == "min":
            StateManager.set(user_id, UserState.WAIT_MIN)
            context.user_data['schedule_ch'] = ch_id
            min_val = await get_min_publish_interval()
            await query.edit_message_text(f"📅 أرسل عدد الدقائق (الحد الأدنى {min_val} دقيقة، كحد أقصى 1440):")
        elif action == "hour":
            StateManager.set(user_id, UserState.WAIT_HOUR)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text("📅 أرسل عدد الساعات (1-168):")
        elif action == "day":
            StateManager.set(user_id, UserState.WAIT_DAY)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text("📅 أرسل عدد الأيام (1-365):")
        elif action == "time":
            StateManager.set(user_id, UserState.WAIT_PUB_TIME)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text("🕐 أرسل وقت النشر (HH:MM):")

    @staticmethod
    async def _handle_banned_words(update, context, query, user_id):
        parts = query.data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("ban_", "")
        chat_id = int(parts[1]) if parts[1].lstrip('-').isdigit() else 0
        if not chat_id:
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("❌ غير مصرح", show_alert=True)
            return
        if action == "add":
            StateManager.set(user_id, UserState.WAIT_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            await query.edit_message_text("📝 أرسل الكلمة المحظورة:")
        elif action == "list":
            words = await DB.get_banned_words(chat_id)
            text = "🚫 **الكلمات المحظورة**\n\n" + "\n".join(f"• {w}" for w in words) if words else "📭 لا توجد كلمات محظورة"
            try:
                await query.edit_message_text(text)
            except BadRequest:
                await safe_send(context.bot, user_id, text)
        elif action == "rem":
            StateManager.set(user_id, UserState.WAIT_REM_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            await query.edit_message_text("🗑️ أرسل الكلمة لحذفها:")

    @staticmethod
    async def _handle_advanced_actions(update, context, query, user_id):
        parts = query.data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("act_", "")
        chat_id = int(parts[1]) if parts[1].lstrip('-').isdigit() else 0
        if not chat_id:
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("❌ غير مصرح", show_alert=True)
            return
        actions = {
            "ban": (UserState.WAIT_BAN, "🚫 أرسل معرف المستخدم:"),
            "mute": (UserState.WAIT_MUTE, "🔇 أرسل معرف المستخدم:"),
            "warn": (UserState.WAIT_WARN, "⚠️ أرسل معرف المستخدم:"),
            "kick": (UserState.WAIT_KICK, "👢 أرسل معرف المستخدم:"),
            "restrict": (UserState.WAIT_RESTRICT, "🔒 أرسل معرف المستخدم:"),
            "unban": (UserState.WAIT_UNBAN, "🔓 أرسل معرف المستخدم:"),
            "pin": (UserState.WAIT_PIN, "📌 أرسل معرف الرسالة أو رد عليها:")
        }
        if action in actions:
            state, text = actions[action]
            StateManager.set(user_id, state)
            context.user_data['adv_chat'] = chat_id
            await query.edit_message_text(text)

    @staticmethod
    async def _handle_penalty(update, context, query, user_id):
        parts = query.data.split(":")
        if len(parts) < 2:
            return
        penalty = parts[0].replace("pen_", "")
        chat_id = int(parts[1]) if parts[1].lstrip('-').isdigit() else 0
        if not chat_id:
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("❌ غير مصرح", show_alert=True)
            return
        await DB.execute("UPDATE group_security SET auto_penalty=? WHERE chat_id=?", (penalty, chat_id))
        await query.edit_message_text(f"✅ تم تعيين العقوبة: {penalty}")

    @staticmethod
    async def _handle_contests(update, context, query, user_id):
        data = query.data
        if data == CB.ADMIN_CREATE_CONTEST:
            StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
            await query.edit_message_text("🏆 أرسل عنوان المسابقة:")
        elif data.startswith(CB.CONTEST_JOIN + ":"):
            cid = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
            context.user_data['contest_join'] = cid
            await query.edit_message_text("📝 أرسل إجابتك:")
        elif data == CB.CONTEST_WINNERS:
            winners = await DB.get_contest_winners(10)
            text = "🏆 **الفائزون**\n\n" + "\n".join(f"• {w['title']} → `{w['winner_id']}`" for w in winners) if winners else "📭 لا يوجد فائزون"
            await query.edit_message_text(text)
        elif data.startswith(CB.DECLARE_WINNER_SEL + ":"):
            if not CONFIG.is_developer(user_id):
                await query.answer("❌ غير مصرح", show_alert=True)
                return
            cid = int(data.split(":")[-1])
            winner = await DB.fetchone("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,))
            if winner:
                await DB.declare_winner(cid, winner[0])
                await query.edit_message_text(f"✅ الفائز: `{winner[0]}`")

    @staticmethod
    async def _handle_import(update, context, query, user_id):
        if not CONFIG.is_developer(user_id):
            await query.answer("❌ غير مصرح", show_alert=True)
            return
        data = query.data
        if data == CB.ADMIN_IMPORT_REPLIES:
            StateManager.set(user_id, UserState.WAIT_IMPORT_FILE)
            context.user_data['import_chat_id'] = -1
            await query.edit_message_text("📤 أرسل ملف JSON للاستيراد:")
        elif data == CB.ADMIN_IMPORT_GITHUB:
            StateManager.set(user_id, UserState.WAIT_GITHUB_URL)
            await query.edit_message_text("📥 أرسل رابط GitHub (JSON):")


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
            if not msg.document or not msg.document.file_name.endswith('.json'):
                await safe_send(context.bot, user_id, "❌ أرسل ملف JSON")
                StateManager.clear(user_id)
                return
            file_obj = await context.bot.get_file(msg.document.file_id)
            temp_path = f"/tmp/import_{user_id}.json"
            await file_obj.download_to_drive(temp_path)
            count = await import_auto_replies(-1, temp_path, overwrite=True)
            _auto_reply_cache.invalidate()
            await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
            Path(temp_path).unlink(missing_ok=True)
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GITHUB_URL:
            json_data = await fetch_json_from_url(text.strip()) if text.strip().startswith('http') else None
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
                existing = await DB.get_channel_by_user(user_id, chat.id)
                if existing:
                    await safe_send(context.bot, user_id, "⚠️ هذه القناة مضافة مسبقاً")
                    StateManager.clear(user_id)
                    return
                if user_id != CONFIG.PRIMARY_OWNER_ID and not await DB.has_active_subscription(user_id):
                    await safe_send(context.bot, user_id, "❌ يجب أن يكون لديك اشتراك نشط لإضافة قناة")
                    StateManager.clear(user_id)
                    return
                result = await DB.add_channel(user_id, chat.id, chat.title or "قناة")
                if result:
                    await DB.set_active_channel(user_id, result)
                    await safe_send(context.bot, user_id, f"✅ تمت إضافة {chat.title}!")
                else:
                    await safe_send(context.bot, user_id, "❌ فشلت الإضافة (ربما تجاوزت حد القنوات المسموح)")
            except Exception as e:
                logger.error(f"❌ فشل إضافة القناة: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.ADDING_POSTS:
            if text.strip().lower() == "/done":
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "✅ تم إنهاء إضافة المنشورات.")
                return

            media_type = 'text'
            media_file_id = None
            if msg.photo:
                media_type, media_file_id = 'photo', msg.photo[-1].file_id
            elif msg.video:
                media_type, media_file_id = 'video', msg.video.file_id
            elif msg.document:
                media_type, media_file_id = 'document', msg.document.file_id
            elif msg.audio:
                media_type, media_file_id = 'audio', msg.audio.file_id
            elif msg.voice:
                media_type, media_file_id = 'voice', msg.voice.file_id
            elif msg.animation:
                media_type, media_file_id = 'animation', msg.animation.file_id
            content = msg.caption or "" if media_type != 'text' else text

            active = await DB.get_active_channel(user_id)
            if active:
                added = await DB.add_posts(active, [(content, media_type, media_file_id)])
                if added > 0:
                    await safe_send(context.bot, user_id, "✅ تم حفظ المنشور!\nأرسل منشورًا آخر أو /done للإنهاء.")
                else:
                    await safe_send(context.bot, user_id, "❌ فشل حفظ المنشور (ربما تجاوزت الحد المسموح).")
            else:
                await safe_send(context.bot, user_id, "❌ لا توجد قناة نشطة.")
            return

        if state == UserState.WAIT_BROADCAST:
            sent = 0
            offset = 0
            while True:
                users = await DB.fetchall("SELECT user_id, banned FROM users LIMIT 5000 OFFSET ?", (offset,))
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
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_AUTO_DEL:
            chat_id_auto = context.user_data.get('auto_chat')
            if chat_id_auto is not None:
                await DB.remove_auto_reply(chat_id_auto, text.strip().lower())
                _auto_reply_cache.invalidate()
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GLOBAL_BAN:
            word = text.strip().lower()
            if len(word) >= 2:
                await DB.add_banned_word(word, -1, user_id)
                invalidate_banned_words_cache()
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GLOBAL_BAN:
            await DB.remove_banned_word(text.strip().lower(), -1)
            invalidate_banned_words_cache()
            StateManager.clear(user_id)
            return

        if state == UserState.SUPPORT_MODE:
            ticket_num = await DB.create_ticket(user_id, update.effective_user.username or "", text)
            await safe_send(context.bot, user_id, f"✅ #{ticket_num}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_MIN:
            try:
                val = int(text)
                min_val = await get_min_publish_interval()
                if val < min_val:
                    await safe_send(context.bot, user_id, f"❌ الحد الأدنى هو {min_val} دقيقة")
                    StateManager.clear(user_id)
                    return
                ch = context.user_data.get('schedule_ch')
                if ch:
                    await DB.update_schedule(ch, schedule_type='interval_minutes', interval_minutes=val)
                    await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {val} دقيقة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_HOUR:
            try:
                val = int(text)
                ch = context.user_data.get('schedule_ch')
                if ch and 1 <= val <= 168:
                    await DB.update_schedule(ch, schedule_type='interval_hours', interval_hours=val)
                    await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {val} ساعة")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-168)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_DAY:
            try:
                val = int(text)
                ch = context.user_data.get('schedule_ch')
                if ch and 1 <= val <= 365:
                    await DB.update_schedule(ch, schedule_type='interval_days', interval_days=val)
                    await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {val} يوم")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-365)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PUB_TIME:
            ch = context.user_data.get('schedule_ch')
            if ch and ':' in text:
                await DB.update_schedule(ch, publish_time=text)
                await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {text}")
            else:
                await safe_send(context.bot, user_id, "❌ صيغة غير صالحة (HH:MM)")
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
                target = int(text.split()[0])
                action_map = {
                    UserState.WAIT_BAN: "ban", UserState.WAIT_MUTE: "mute",
                    UserState.WAIT_WARN: "warn", UserState.WAIT_KICK: "kick",
                    UserState.WAIT_RESTRICT: "restrict", UserState.WAIT_UNBAN: "unban"
                }
                action = action_map.get(state)
                if action and chat_id_adv:
                    if action == 'unban':
                        await context.bot.unban_chat_member(chat_id_adv, target)
                        await safe_send(context.bot, user_id, f"✅ تم إلغاء حظر `{target}`")
                    else:
                        success, msg = await apply_penalty(context.bot, chat_id_adv, target, action, 60)
                        await safe_send(context.bot, user_id, msg)
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PIN:
            chat_id_adv = context.user_data.get('adv_chat')
            try:
                msg_id = update.message.reply_to_message.message_id if update.message.reply_to_message else int(text)
                await context.bot.pin_chat_message(chat_id_adv, msg_id)
                await safe_send(context.bot, user_id, f"📌 تم تثبيت الرسالة {msg_id}")
            except:
                await safe_send(context.bot, user_id, "❌ فشل التثبيت")
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
                cid = await DB.create_contest(user_id, context.user_data.get('contest_title',''), context.user_data.get('contest_desc',''), context.user_data.get('contest_prize',''), TimeUtils.mecca_to_utc(end_date).strftime('%Y-%m-%d %H:%M:%S'))
                await safe_send(context.bot, user_id, f"✅ مسابقة #{cid}")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ صيغة غير صالحة")
            StateManager.clear(user_id)
            return
        if state == UserState.WAIT_CONTEST_ANSWER:
            cid = context.user_data.get('contest_join')
            if cid:
                await DB.join_contest(cid, user_id, text)
                await safe_send(context.bot, user_id, "✅ تم المشاركة!")
            StateManager.clear(user_id)
            return
        if state == UserState.WAIT_ADMIN_ADD:
            try:
                await DB.execute("INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)", (int(text), user_id, TimeUtils.sql_iso()))
                await safe_send(context.bot, user_id, f"✅ تم إضافة `{text}` كمشرف")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            StateManager.clear(user_id)
            return
        if state == UserState.WAIT_ADMIN_REM:
            try:
                await DB.execute("DELETE FROM bot_admins WHERE user_id=?", (int(text),))
                await safe_send(context.bot, user_id, f"✅ تم إزالة `{text}`")
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
                target_id, days = int(parts[0]), int(parts[1])
                plan_row = await DB.fetchone("SELECT id FROM plans WHERE is_gift=1 LIMIT 1")
                if not plan_row:
                    plan_row = await DB.fetchone("SELECT id FROM plans WHERE is_active=1 AND is_gift=0 LIMIT 1")
                success = await DB.grant_subscription_days(target_id, days, plan_id=plan_row[0] if plan_row else None, provider='manual')
                await safe_send(context.bot, user_id, f"✅ تم منح {days} يوم للمستخدم `{target_id}`" if success else "❌ فشل المنح")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ قيم غير صالحة")
            StateManager.clear(user_id)
            return
        if state == UserState.WAIT_DEL_USER:
            try:
                target = int(text)
                await DB.execute("DELETE FROM users WHERE user_id=?", (target,))
                await DB.execute("DELETE FROM user_channels WHERE user_id=?", (target,))
                await DB.execute("DELETE FROM referrals WHERE referrer_id=? OR referred_id=?", (target, target))
                await DB.execute("DELETE FROM subscriptions WHERE user_id=?", (target,))
                await DB.execute("DELETE FROM user_groups_link WHERE user_id=?", (target,))
                await DB.execute("DELETE FROM hidden_owner_groups WHERE owner_id=?", (target,))
                await DB.execute("DELETE FROM hidden_admins WHERE admin_id=?", (target,))
                await safe_send(context.bot, user_id, f"✅ تم حذف المستخدم `{target}`")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
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
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return
        if state == UserState.WAIT_MAX_LEN:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get(f'sec_chat_{user_id}')
                if chat_id_sec and val >= 0:
                    await DB.execute("UPDATE group_security SET max_message_length=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين الحد الأقصى إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return
        if state == UserState.WAIT_WARN_COUNT:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get(f'sec_chat_{user_id}')
                if chat_id_sec and 1 <= val <= 10:
                    await DB.execute("UPDATE group_security SET max_warnings=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين عدد التحذيرات إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-10)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
            StateManager.clear(user_id)
            return
        if state == UserState.WAIT_MUTE_DURATION:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get(f'sec_chat_{user_id}')
                if chat_id_sec and 1 <= val <= 1440:
                    await DB.execute("UPDATE group_security SET auto_mute_duration=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين مدة الكتم إلى {val} دقيقة")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-1440)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ رقم غير صالح")
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
            except:
                await safe_send(context.bot, user_id, "❌ فشل التعيين")
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
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, f"✅ تم إضافة الرد للكلمة: {keyword}")
            StateManager.clear(user_id)
            return

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
            try:
                await update.message.delete()
            except:
                pass
            return
        settings = await DB.get_security_settings(chat_id)
        perms = await check_bot_permissions(context.bot, chat_id)
        can_delete = perms.get('can_act', False)

        if settings.get('delete_links', False) and TextUtils.contains_link(text):
            if can_delete:
                try:
                    await update.message.delete()
                except:
                    pass
            return
        if settings.get('mentions', False) and TextUtils.contains_mention(text):
            if can_delete:
                try:
                    await update.message.delete()
                except:
                    pass
            return
        if settings.get('delete_banned_words', False):
            banned_words = await get_banned_words_cached(chat_id)
            for word in banned_words:
                if word in text.lower():
                    if can_delete:
                        try:
                            await update.message.delete()
                        except:
                            pass
                    return
        ars = await DB.get_auto_reply_settings(chat_id)
        if ars.get('enabled', False):
            if ars.get('only_admins', False) and not await is_authorized_in_group(context.bot, chat_id, update.effective_user.id):
                return
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
        if settings.get('welcome_enabled', False) and update.message.new_chat_members:
            for member in update.message.new_chat_members:
                if member.id != context.bot.id:
                    welcome_text = settings.get('welcome_text', 'مرحباً {user} 🤍')
                    text = welcome_text.format(user=member.full_name or 'العضو')
                    try:
                        await context.bot.send_message(chat_id, text)
                    except:
                        pass
        if settings.get('goodbye_enabled', False) and update.message.left_chat_member:
            member = update.message.left_chat_member
            if member.id != context.bot.id:
                goodbye_text = settings.get('goodbye_text', 'وداعاً {user} 👋')
                text = goodbye_text.format(user=member.full_name or 'العضو')
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
