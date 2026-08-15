#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers.py - جميع معالجات البوت (كامل 100%)
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
        title = f"🌿 **{CONFIG.BOT_NAME}**\n\n👤 `{user_id}`\n👥 {groups} مجموعة\n💎 {sub_text}\n📡 {ch_display}\n⏳ {cnt}\n⚙️ {auto}\n♻️ {recycle}"
        await safe_send(context.bot, user_id, title, reply_markup=kb)

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await safe_send(context.bot, update.effective_user.id, "📚 /start للبدء")

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
        text = f"""
👨‍💻 **المطور**

📌 `{CONFIG.PRIMARY_OWNER_ID}`
👤 {CONFIG.BOT_NAME}
🔗 @{CONFIG.BOT_USERNAME}
📞 @RelaxMgr

🆓 مجاني: حماية المجموعات
💎 مدفوع: إدارة القنوات
"""
        await safe_send(context.bot, update.effective_user.id, text)

    @staticmethod
    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not CONFIG.is_developer(update.effective_user.id):
            return
        stats = await DB.get_user_stats()
        await safe_send(context.bot, update.effective_user.id, f"👥 {stats['users']}\n⛔ {stats['banned']}")

    @staticmethod
    async def security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
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

    # ========== المخفيون ==========

    @staticmethod
    async def register_hidden_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    async def add_hidden_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        is_owner = user_id == CONFIG.PRIMARY_OWNER_ID
        if not is_owner:
            row = await DB.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
            is_owner = row is not None
        if not is_owner or not context.args:
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
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "بدون اسم"
        user_id = update.effective_user.id

        try:
            all_admins = await context.bot.get_chat_administrators(chat_id)
        except:
            all_admins = []

        creator_id = None
        for admin in all_admins:
            if admin.status == 'creator' and not admin.user.is_bot:
                creator_id = admin.user.id
                break

        is_admin = False
        for admin in all_admins:
            if admin.user.id == user_id:
                is_admin = True
                break

        if not is_admin:
            row = await DB.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
            if row:
                is_admin = True
            else:
                row2 = await DB.fetchone("SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, user_id))
                if row2:
                    is_admin = True

        if not is_admin:
            await safe_send(context.bot, user_id, "❌ لست مشرفاً!")
            return

        await DB.register_group(chat_id, chat_name, creator_id or user_id)

        if creator_id:
            await DB.execute("INSERT OR IGNORE INTO hidden_owner_groups VALUES (?,?,0)", (chat_id, creator_id))
            await DB.execute("INSERT OR IGNORE INTO user_groups_link VALUES (?,?)", (creator_id, chat_id))

        await DB.execute("INSERT OR IGNORE INTO user_groups_link VALUES (?,?)", (user_id, chat_id))

        admin_ids = [a.user.id for a in all_admins if a.user and not a.user.is_bot]
        await DB.sync_group_admins(chat_id, admin_ids)

        await safe_send(context.bot, user_id, f"✅ **{chat_name}**!")
        await safe_send(context.bot, chat_id, "🤖 تم التفعيل!")

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
                    await query.edit_message_text("❌ استخدمت")
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
                    await query.edit_message_text("📭 لا توجد", reply_markup=kb)
                    return
                text = "📡 **قنواتي**\n\n"
                kb = []
                for ch in channels:
                    text += f"{'✅' if not ch['banned'] else '🚫'} {ch['channel_name']}\n"
                    kb.append([InlineKeyboardButton(f"📌 {ch['channel_name'][:20]}", callback_data=f"{CB.CH_SEL}{ch['id']}")])
                kb.append([InlineKeyboardButton("🔙", callback_data=CB.BACK)])
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data.startswith(CB.CH_SEL):
                ch_id = int(data.split(":")[-1])
                await DB.set_active_channel(user_id, ch_id)
                await query.edit_message_text("✅ تم!")
                return

            if data == CB.POST_ADD:
                if not await DB.has_active_subscription(user_id):
                    await query.answer("❌ انتهى اشتراكك!", show_alert=True)
                    return
                active = await DB.get_active_channel(user_id)
                if not active:
                    return
                context.user_data[f"session_{user_id}"] = []
                context.user_data[f"session_target_{user_id}"] = 15
                StateManager.set(user_id, UserState.ADDING_POSTS)
                await query.edit_message_text("📥 أرسل المنشورات:")
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
                            await context.bot.send_message(ch_info['channel_id'], post['text'] or ".")
                            await DB.mark_post_published(post['id'])
                            await query.edit_message_text("✅ تم!")
                        except:
                            pass
                return

            if data == CB.POST_LIST:
                active = await DB.get_active_channel(user_id)
                if active:
                    posts = await DB.get_user_posts(active, 10)
                    text = "📋 **منشوراتي**\n\n"
                    for p in posts:
                        text += f"🆔 {p['id']}\n"
                    kb = [[InlineKeyboardButton("🔙", callback_data=CB.BACK)]]
                    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data == CB.POST_REC:
                active = await DB.get_active_channel(user_id)
                if active:
                    await DB.reset_posts(active)
                    await query.edit_message_text("♻️ تم!")
                return

            if data == CB.GROUPS:
                groups = await DB.get_user_groups(user_id)
                if not groups:
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton("➕ أضف", url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")
                    ]])
                    await query.edit_message_text("📭 لا توجد", reply_markup=kb)
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
                return

            if data.startswith("sec_"):
                await CallbackHandlers._handle_security(update, context, query, user_id)
                return

            if data.startswith("lang_"):
                lang_set = data.split("_")[-1]
                await DB.set_user_language(user_id, lang_set)
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


class MessageHandlers:
    @staticmethod
    async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        msg = update.message
        text = msg.text.strip() if msg.text else ""
        state = StateManager.get(user_id)

        if state == UserState.WAIT_CHANNEL:
            try:
                chat = await context.bot.get_chat(text)
                if chat.type == 'channel':
                    result = await DB.add_channel(user_id, chat.id, chat.title or "قناة")
                    if result:
                        await DB.set_active_channel(user_id, result)
                        await safe_send(context.bot, user_id, f"✅ {chat.title}")
            except:
                pass
            StateManager.clear(user_id)
            return

        if state == UserState.ADDING_POSTS:
            session = context.user_data.get(f"session_{user_id}", [])
            media_type = 'text'
            media_file_id = None
            if msg.photo:
                media_type = 'photo'
                media_file_id = msg.photo[-1].file_id
            elif msg.video:
                media_type = 'video'
                media_file_id = msg.video.file_id
            content = msg.caption or "" if media_type != 'text' else text
            session.append((content, media_type, media_file_id))
            context.user_data[f"session_{user_id}"] = session
            if len(session) >= 15:
                active = await DB.get_active_channel(user_id)
                if active:
                    await DB.add_posts(active, session)
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "✅ تم!")
            else:
                await safe_send(context.bot, user_id, f"✅ {len(session)}/15")
            return

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
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_AUTO_DEL:
            chat_id_auto = context.user_data.get('auto_chat')
            if chat_id_auto is not None:
                await DB.remove_auto_reply(chat_id_auto, text.strip().lower())
            StateManager.clear(user_id)
            return

        if state == UserState.SUPPORT_MODE:
            ticket_num = await DB.create_ticket(user_id, update.effective_user.username or "", text)
            await safe_send(context.bot, user_id, f"✅ #{ticket_num}")
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
                if member.id != context.bot.id:
                    await context.bot.send_message(chat_id, f"مرحباً {member.full_name} 🤍")

    @staticmethod
    async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
