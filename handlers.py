#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers.py - جميع معالجات البوت (النسخة النهائية الكاملة)
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
        auto = "✅ مفعل" if await DB.get_auto_publish_status(user_id) else "❌ معطل"
        recycle = "✅ مفعل" if await DB.get_auto_recycle_status(user_id) else "❌ معطل"

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

        title = (
            f"🌿 **{CONFIG.BOT_NAME}**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 **المعرف:** `{user_id}`\n"
            f"👥 **المجموعات:** {groups}\n"
            f"📡 **القناة:** {ch_display}\n"
            f"⏳ **غير منشورة:** {cnt}\n\n"
            f"💎 **الاشتراك:** {sub_text}\n"
            f"⚙️ **النشر التلقائي:** {auto}\n"
            f"♻️ **إعادة التدوير:** {recycle}\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

        await safe_send(context.bot, user_id, title, reply_markup=kb)

    @staticmethod
    async def help_command(update, context):
        await safe_send(context.bot, update.effective_user.id, "📚 استخدم /start")

    @staticmethod
    async def trial(update, context):
        user_id = update.effective_user.id
        if await DB.has_used_trial(user_id):
            await safe_send(context.bot, user_id, "❌ استخدمت التجربة")
            return
        days = await DB.activate_trial(user_id)
        await safe_send(context.bot, user_id, f"🎁 {days} يوم!")

    @staticmethod
    async def subscribe(update, context):
        kb = KeyboardFactory.build("plans")
        await safe_send(context.bot, update.effective_user.id, "💎 الباقات:", reply_markup=kb)

    @staticmethod
    async def support(update, context):
        StateManager.set(update.effective_user.id, UserState.SUPPORT_MODE)
        await safe_send(context.bot, update.effective_user.id, "📞 أرسل رسالتك:")

    @staticmethod
    async def developer(update, context):
        text = f"👨‍💻 **المطور**\n\n📌 `{CONFIG.PRIMARY_OWNER_ID}`\n🔗 @{CONFIG.BOT_USERNAME}\n📞 @RelaxMgr"
        await safe_send(context.bot, update.effective_user.id, text)

    @staticmethod
    async def stats(update, context):
        if not CONFIG.is_developer(update.effective_user.id):
            return
        stats = await DB.get_user_stats()
        await safe_send(context.bot, update.effective_user.id, f"👥 {stats['users']}\n⛔ {stats['banned']}")

    @staticmethod
    async def language(update, context):
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
    async def contests(update, context):
        contests = await DB.get_active_contests(10)
        if not contests:
            await safe_send(context.bot, update.effective_user.id, "📭 لا توجد")
            return
        text = "🏆 **المسابقات**\n\n"
        for c in contests:
            text += f"• {c['title']}\n"
        await safe_send(context.bot, update.effective_user.id, text)

    @staticmethod
    async def replies_command(update, context):
        await safe_send(context.bot, update.effective_user.id, "📚 الردود تعمل!")

    # ========== أوامر المجموعة ==========
    @staticmethod
    async def security(update, context):
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
    async def panel(update, context):
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        kb = KeyboardFactory.build("panel", chat_id)
        await safe_send(context.bot, user_id, "📋 لوحة التحكم", reply_markup=kb)

    @staticmethod
    async def lock(update, context):
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        await DB.execute("INSERT OR REPLACE INTO chat_locks VALUES (?,1,?,?)", (chat_id, TimeUtils.sql_iso(), user_id))
        await safe_send(context.bot, user_id, "🔒 تم")

    @staticmethod
    async def unlock(update, context):
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        await DB.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await safe_send(context.bot, user_id, "🔓 تم")

    # ========== أوامر المخفيين ==========
    @staticmethod
    async def register_hidden_owner(update, context):
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
        await DB.execute("INSERT OR IGNORE INTO hidden_owner_groups VALUES (?,?,1)", (chat_id, owner_id))
        invalidate_auth_cache(chat_id, owner_id)
        await safe_send(context.bot, user_id, f"✅ {owner_id}")

    @staticmethod
    async def add_hidden_admin(update, context):
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
        await DB.execute("INSERT OR IGNORE INTO hidden_admins VALUES (?,?,?,?)", (chat_id, admin_id, user_id, TimeUtils.sql_iso()))
        invalidate_auth_cache(chat_id, admin_id)
        await safe_send(context.bot, user_id, f"✅ {admin_id}")

    @staticmethod
    async def remove_hidden_admin(update, context):
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
    async def list_hidden_admins(update, context):
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
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
    async def syncgroup(update, context):
        if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
            await safe_send(context.bot, update.effective_user.id, "❌ للمجموعات فقط")
            return

        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "بدون اسم"
        user_id = update.effective_user.id

        if user_id < 0:
            return

        try:
            all_admins = await context.bot.get_chat_administrators(chat_id)
        except Exception as e:
            logger.error(f"❌ فشل جلب المشرفين: {e}")
            await safe_send(context.bot, user_id, "❌ فشل جلب المشرفين")
            return

        creator_id = None
        is_admin = False
        is_anonymous = False

        for admin in all_admins:
            if admin.status == 'creator' and not getattr(admin, 'is_anonymous', False) and not admin.user.is_bot:
                creator_id = admin.user.id
            if admin.user.id == user_id:
                is_admin = True
                is_anonymous = getattr(admin, 'is_anonymous', False)

        if not is_admin:
            await update.message.reply_text("❌ **أنت لست مشرفاً في هذه المجموعة!**")
            return

        owner_id = user_id

        await DB.register_group(chat_id, chat_name, creator_id or owner_id, update.effective_chat.username)
        bot_perms = await check_bot_permissions(context.bot, chat_id)

        if not bot_perms.get('can_act', False):
            if is_anonymous:
                await update.message.reply_text("⚠️ **البوت ليس مشرفاً!**")
            else:
                await safe_send(context.bot, user_id, "⚠️ **البوت ليس مشرفاً!**")
            return

        if creator_id and creator_id != owner_id:
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
            (owner_id, chat_id)
        )
        if is_anonymous:
            await DB.execute(
                "INSERT OR IGNORE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,1)",
                (chat_id, owner_id)
            )
        invalidate_auth_cache(chat_id, owner_id)

        admin_ids = [a.user.id for a in all_admins if a.user and not a.user.is_bot]
        admin_count = await DB.sync_group_admins(chat_id, admin_ids)

        msg = f"✅ **تم تفعيل المجموعة!**\n\n"
        msg += f"📌 {chat_name}\n"
        msg += f"🆔 `{chat_id}`\n"
        if creator_id and creator_id != owner_id:
            msg += f"👑 المالك الحقيقي: `{creator_id}`\n"
        if is_anonymous:
            msg += f"👻 مشرف مخفي: `{owner_id}`\n"
        else:
            msg += f"👤 مشرف: `{owner_id}`\n"
        msg += f"👥 {admin_count} مشرف"

        if is_anonymous:
            await update.message.reply_text(msg)
        else:
            await safe_send(context.bot, user_id, msg)
        await safe_send(context.bot, chat_id, "🤖 **تم تفعيل البوت!**")

    # ========== أوامر الإشراف ==========
    @staticmethod
    async def ban(update, context):
        await CommandHandlers._moderation_command(update, context, "ban")

    @staticmethod
    async def mute(update, context):
        await CommandHandlers._moderation_command(update, context, "mute")

    @staticmethod
    async def warn(update, context):
        await CommandHandlers._moderation_command(update, context, "warn")

    @staticmethod
    async def kick(update, context):
        await CommandHandlers._moderation_command(update, context, "kick")

    @staticmethod
    async def restrict(update, context):
        await CommandHandlers._moderation_command(update, context, "restrict")

    @staticmethod
    async def unban(update, context):
        await CommandHandlers._moderation_command(update, context, "unban")

    @staticmethod
    async def pin(update, context):
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        if update.message.reply_to_message:
            try:
                await context.bot.pin_chat_message(chat_id, update.message.reply_to_message.message_id)
            except:
                pass

    @staticmethod
    async def _moderation_command(update, context, action):
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


# =====================================================================
# 2. معالج الكولباك
# =====================================================================

class CallbackHandlers:
    @staticmethod
    async def handle(update, context):
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
                    await query.edit_message_text("❌ استخدمت التجربة")
                    return
                days = await DB.activate_trial(user_id)
                await query.edit_message_text(f"🎁 {days} يوم!")
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
                await query.edit_message_text("💎 **الباقات:**", reply_markup=kb)
                return

            if data.startswith("buy_sub_"):
                days = int(data.split("_")[-1])
                plan_names = {1: "يوم", 7: "أسبوع", 30: "شهر", 90: "3 أشهر"}
                plan = await DB.get_plan_by_name(plan_names.get(days, ""))
                if plan:
                    try:
                        await context.bot.send_invoice(
                            chat_id=user_id,
                            title=f"💎 {plan['name']}",
                            description=plan['description'],
                            payload=json.dumps({'plan_id': plan['id']}),
                            provider_token="",
                            currency="XTR",
                            prices=[LabeledPrice(plan['name'], plan['price'])]
                        )
                        await query.message.delete()
                    except Exception as e:
                        await query.answer(f"❌ {str(e)[:50]}", show_alert=True)
                return

            if data == CB.CH_ADD:
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
                    await query.edit_message_text("📭 لا توجد قنوات!", reply_markup=kb)
                    return
                text = "📡 **قنواتي**\n\n"
                kb = []
                for ch in channels:
                    st = "✅" if not ch['banned'] else "🚫"
                    text += f"{st} {ch['channel_name']} (`{ch['channel_id']}`)\n"
                    kb.append([InlineKeyboardButton(f"📌 {ch['channel_name'][:20]}", callback_data=f"{CB.CH_SEL}:{ch['id']}")])
                kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)])
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
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
                        await context.bot.send_photo(ch_info['channel_id'], post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
                    elif post['media_type'] == 'video' and post['media_file_id']:
                        await context.bot.send_video(ch_info['channel_id'], post['media_file_id'], caption=post['text'][:1024] if post['text'] else None)
                    else:
                        await context.bot.send_message(ch_info['channel_id'], post['text'] or ".")
                    await DB.mark_post_published(post['id'])
                    await query.edit_message_text("✅ تم النشر!")
                except Exception as e:
                    await query.edit_message_text(f"❌ {str(e)[:100]}")
                return

            if data == CB.POST_LIST:
                active = await DB.get_active_channel(user_id)
                if active:
                    posts = await DB.get_user_posts(active, 10)
                    text = "📋 **منشوراتي**\n\n"
                    for p in posts:
                        text += f"🆔 {p['id']}\n"
                    kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]]
                    await query.edit_message_text(text if posts else "📭 لا يوجد", reply_markup=InlineKeyboardMarkup(kb))
                return

            if data == CB.POST_REC:
                active = await DB.get_active_channel(user_id)
                if active:
                    count = await DB.reset_posts(active)
                    await query.edit_message_text(f"♻️ تم إعادة {count} منشور!")
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

            # ========== الأزرار الفرعية ==========
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

            if data.startswith("sched_"):
                await CallbackHandlers._handle_schedule(update, context, query, user_id)
                return

            if data.startswith("ban_"):
                await CallbackHandlers._handle_banned_words(update, context, query, user_id)
                return

            if data.startswith("act_"):
                await CallbackHandlers._handle_advanced_actions(update, context, query, user_id)
                return

            if data.startswith("pen_"):
                await CallbackHandlers._handle_penalty(update, context, query, user_id)
                return

            if data.startswith("contest_") or data.startswith(CB.DECLARE_WINNER_SEL):
                await CallbackHandlers._handle_contests(update, context, query, user_id)
                return

            if data in (CB.ADMIN_IMPORT_REPLIES, CB.ADMIN_IMPORT_GITHUB):
                await CallbackHandlers._handle_import(update, context, query, user_id)
                return

            if data.startswith("lang_"):
                lang_set = data.split("_")[-1]
                await DB.set_user_language(user_id, lang_set)
                await query.answer(f"✅ {lang_set}")
                await CommandHandlers.start(update, context)
                return

            await query.answer("⚠️ غير متوفر", show_alert=True)

        except Exception as e:
            logger.error(f"❌ Callback error: {e}", exc_info=True)
            try:
                await query.answer("❌ خطأ", show_alert=True)
            except:
                pass

    # ========== دوال مساعدة ==========
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
            await query.answer("❌ لا صلاحية", show_alert=True)
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
            text = await KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id)
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except BadRequest:
                pass
            return

        if action == "enable_all":
            for f in field_map.values():
                await DB.execute(f"UPDATE group_security SET {f}=1 WHERE chat_id=?", (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = await KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id)
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except BadRequest:
                pass
            return

        if action == "disable_all":
            for f in field_map.values():
                await DB.execute(f"UPDATE group_security SET {f}=0 WHERE chat_id=?", (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = await KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id)
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except BadRequest:
                pass
            return

        if action == "banned":
            kb = KeyboardFactory.build("banned_words", chat_id)
            await query.edit_message_text("🚫 **الكلمات المحظورة**", reply_markup=kb)
            return

        if action == "maxlen":
            StateManager.set(user_id, UserState.WAIT_MAX_LEN)
            context.user_data[f"sec_chat_{user_id}"] = chat_id
            await query.edit_message_text("📏 أرسل الحد الأقصى للطول:")
            return

        if action == "warn_count":
            StateManager.set(user_id, UserState.WAIT_WARN_COUNT)
            context.user_data[f"sec_chat_{user_id}"] = chat_id
            await query.edit_message_text("📝 أرسل العدد (1-10):")
            return

        if action == "auto_reply_menu":
            kb = KeyboardFactory.build("auto_reply_manage", chat_id)
            await query.edit_message_text("📝 الردود:", reply_markup=kb)
            return

        if action == "close":
            try:
                await query.message.delete()
            except BadRequest:
                pass
            return

        await query.answer()

    @staticmethod
    async def _handle_admin(update, context, query, user_id):
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
        elif data == CB.ADMIN_GROUPS:
            groups = await DB.fetchall("SELECT chat_id, chat_name, banned FROM bot_groups LIMIT 50")
            text = "👥 **المجموعات**\n\n" + "\n".join(f"{'✅' if not g[2] else '🚫'} {g[1]}" for g in groups)
            await query.edit_message_text(text if groups else "📭 لا توجد")
        elif data == CB.ADMIN_ADD_ADMIN:
            StateManager.set(user_id, UserState.WAIT_ADMIN_ADD)
            await query.edit_message_text("👑 أرسل معرف المشرف:")
        elif data == CB.ADMIN_REM_ADMIN:
            StateManager.set(user_id, UserState.WAIT_ADMIN_REM)
            await query.edit_message_text("🗑️ أرسل معرف المشرف:")
        elif data == CB.ADMIN_RAM:
            ram = get_ram_usage()
            await query.edit_message_text(f"🖥️ الرام: {ram['percent']}%")
        elif data == CB.ADMIN_STATS:
            stats = await DB.get_user_stats()
            await query.edit_message_text(f"👥 {stats['users']} مستخدم")
        elif data == CB.ADMIN_BACKUP:
            try:
                backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2(PATHS.DB, backup_file)
                with open(backup_file, 'rb') as f:
                    await context.bot.send_document(chat_id=user_id, document=f, filename=backup_file.name)
                await query.answer()
            except Exception as e:
                logger.error(f"❌ فشل النسخ الاحتياطي: {e}")
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
        elif data == CB.ADMIN_ADD_REPLY:
            StateManager.set(user_id, UserState.WAIT_KEYWORD)
            await query.edit_message_text("📝 أرسل الكلمة:")
        elif data == CB.ADMIN_DEL_REPLY:
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = -1
            await query.edit_message_text("🗑️ أرسل الكلمة:")
        elif data == CB.ADMIN_ADD_BANNED:
            StateManager.set(user_id, UserState.WAIT_GLOBAL_BAN)
            await query.edit_message_text("🚫 أرسل الكلمة:")
        elif data == CB.ADMIN_REM_BANNED:
            StateManager.set(user_id, UserState.WAIT_REM_GLOBAL_BAN)
            await query.edit_message_text("🗑️ أرسل الكلمة:")
        elif data == CB.ADMIN_CREATE_CONTEST:
            StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
            await query.edit_message_text("🏆 أرسل عنوان المسابقة:")
        elif data == CB.ADMIN_REFRESH_CACHE:
            _auto_reply_cache.invalidate()
            await query.edit_message_text("🔄 تم التحديث")
        else:
            await query.answer("⚠️ غير متوفر", show_alert=True)

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

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("❌ لا صلاحية", show_alert=True)
            return

        if action == "toggle":
            s = await DB.get_auto_reply_settings(chat_id)
            await DB.update_auto_reply_settings(chat_id, enabled=not s.get('enabled', False))
            _auto_reply_cache.invalidate()
            await query.answer("✅ تم")
        elif action == "add":
            StateManager.set(user_id, UserState.WAIT_AUTO_KEY)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text("📝 أرسل الكلمة:")
        elif action == "del":
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text("🗑️ أرسل الكلمة:")
        elif action == "stats":
            rows = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? LIMIT 10", (chat_id,))
            text = "📊 **الإحصائيات**\n\n" + "\n".join(f"• {r[0]}: {r[1]}" for r in rows)
            await query.edit_message_text(text if rows else "📭 لا يوجد")
        elif action == "list":
            rows = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=? LIMIT 20", (chat_id,))
            text = "📋 **الردود**\n\n" + "\n".join(f"• {r[0]}" for r in rows)
            await query.edit_message_text(text if rows else "📭 لا يوجد")
        elif action == "menu":
            kb = KeyboardFactory.build("auto_reply_manage", chat_id)
            await query.edit_message_text("📝 الردود:", reply_markup=kb)
        else:
            await query.answer()

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
        if action == "min":
            StateManager.set(user_id, UserState.WAIT_MIN)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text("📅 أرسل عدد الدقائق (1-1440):")
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
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("ban_", "")
        try:
            chat_id = int(parts[1])
        except:
            return
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await query.answer("❌ لا صلاحية", show_alert=True)
            return
        if action == "add":
            StateManager.set(user_id, UserState.WAIT_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            await query.edit_message_text("📝 أرسل الكلمة المحظورة:")
        elif action == "list":
            words = await DB.get_banned_words(chat_id)
            await query.edit_message_text("🚫 **الكلمات**\n\n" + "\n".join(f"• {w}" for w in words) if words else "📭 لا توجد")
        elif action == "rem":
            StateManager.set(user_id, UserState.WAIT_REM_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            await query.edit_message_text("🗑️ أرسل الكلمة لحذفها:")

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
            await query.answer("❌ لا صلاحية", show_alert=True)
            return
        actions = {
            "ban": (UserState.WAIT_BAN, "🚫 أرسل معرف المستخدم:"),
            "mute": (UserState.WAIT_MUTE, "🔇 أرسل معرف المستخدم:"),
            "warn": (UserState.WAIT_WARN, "⚠️ أرسل معرف المستخدم:"),
            "kick": (UserState.WAIT_KICK, "👢 أرسل معرف المستخدم:"),
            "restrict": (UserState.WAIT_RESTRICT, "🔒 أرسل معرف المستخدم:"),
            "unban": (UserState.WAIT_UNBAN, "🔓 أرسل معرف المستخدم:"),
            "pin": (UserState.WAIT_PIN, "📌 أرسل معرف الرسالة أو رد عليها:"),
        }
        if action in actions:
            state, text = actions[action]
            StateManager.set(user_id, state)
            context.user_data['adv_chat'] = chat_id
            await query.edit_message_text(text)

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
            await query.answer("❌ لا صلاحية", show_alert=True)
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
            text = "🏆 **الفائزون**\n\n" + "\n".join(f"• {w['title']} → `{w['winner_id']}`" for w in winners)
            await query.edit_message_text(text if winners else "📭 لا يوجد")
        elif data.startswith(CB.DECLARE_WINNER_SEL + ":"):
            cid = int(data.split(":")[-1])
            winner = await DB.fetchone("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,))
            if winner:
                await DB.declare_winner(cid, winner[0])
                await query.edit_message_text(f"✅ الفائز: `{winner[0]}`")

    @staticmethod
    async def _handle_import(update, context, query, user_id):
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
                result = await DB.add_channel(user_id, chat.id, chat.title or "قناة")
                if result:
                    await DB.set_active_channel(user_id, result)
                    await safe_send(context.bot, user_id, f"✅ {chat.title}!")
                else:
                    await safe_send(context.bot, user_id, "⚠️ القناة موجودة مسبقاً")
            except Exception as e:
                logger.error(f"❌ فشل إضافة القناة: {e}")
            StateManager.clear(user_id)
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

        if state == UserState.WAIT_BROADCAST:
            users = await DB.get_all_users()
            sent = 0
            for uid, banned in users:
                if not banned:
                    try:
                        await safe_send(context.bot, uid, text)
                        sent += 1
                        await asyncio.sleep(0.05)
                    except:
                        pass
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
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GLOBAL_BAN:
            await DB.remove_banned_word(text.strip().lower(), -1)
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
                if 1 <= val <= 1440:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_minutes', interval_minutes=val)
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_HOUR:
            try:
                val = int(text)
                if 1 <= val <= 168:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_hours', interval_hours=val)
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_DAY:
            try:
                val = int(text)
                if 1 <= val <= 365:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_days', interval_days=val)
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PUB_TIME:
            if ':' in text:
                ch = context.user_data.get('schedule_ch')
                if ch:
                    await DB.update_schedule(ch, publish_time=text)
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            word = text.strip().lower()
            if chat_id_ban and len(word) >= 2:
                await DB.add_banned_word(word, chat_id_ban, user_id)
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            if chat_id_ban:
                await DB.remove_banned_word(text.strip().lower(), chat_id_ban)
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
                    else:
                        success, msg = await apply_penalty(context.bot, chat_id_adv, target, action, 60)
                        await safe_send(context.bot, user_id, msg)
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PIN:
            chat_id_adv = context.user_data.get('adv_chat')
            try:
                msg_id = update.message.reply_to_message.message_id if update.message.reply_to_message else int(text)
                await context.bot.pin_chat_message(chat_id_adv, msg_id)
            except:
                pass
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
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_CONTEST_ANSWER:
            cid = context.user_data.get('contest_join')
            if cid:
                await DB.join_contest(cid, user_id, text)
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ADMIN_ADD:
            try:
                target = int(text)
                await DB.execute("INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)",
                                 (target, user_id, TimeUtils.sql_iso()))
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ADMIN_REM:
            try:
                target = int(text)
                await DB.execute("DELETE FROM bot_admins WHERE user_id=?", (target,))
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_UPDATE:
            ch = await DB.get_updates_channel()
            if ch:
                try:
                    await context.bot.send_message(f"@{ch}", f"📢 {text}")
                except:
                    pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_UPDATE_CH:
            await DB.set_setting('updates_channel', text.replace('@', ''))
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_FORCE:
            await DB.set_setting('force_subscribe_channel', text.replace('@', ''))
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_DAYS:
            try:
                val = int(text)
                if 1 <= val <= 30:
                    await DB.update_reminder_settings(user_id, reminder_days_before=val)
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_MAX_LEN:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get(f'sec_chat_{user_id}')
                if chat_id_sec and val >= 0:
                    await DB.execute("UPDATE group_security SET max_message_length=? WHERE chat_id=?", (val, chat_id_sec))
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_WARN_COUNT:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get(f'sec_chat_{user_id}')
                if chat_id_sec and 1 <= val <= 10:
                    await DB.execute("UPDATE group_security SET max_warnings=? WHERE chat_id=?", (val, chat_id_sec))
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_LOG_CH:
            try:
                chat = await context.bot.get_chat(text)
                if chat.type == 'channel':
                    await DB.set_setting('log_channel_id', str(chat.id))
            except:
                pass
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
                    welcome_text = settings.get('welcome_text', "مرحباً {user} 🤍")
                    text = welcome_text.format(user=member.full_name or "العضو")
                    await context.bot.send_message(chat_id, text)

    @staticmethod
    async def handle_join_request(update, context):
        join_request = update.chat_join_request
        chat_id = update.effective_chat.id
        settings = await DB.get_security_settings(chat_id)
        if settings.get('auto_approve_join', False):
            try:
                await join_request.approve()
            except:
                pass
        elif settings.get('auto_reject_join', False):
            try:
                await join_request.decline()
            except:
                pass
