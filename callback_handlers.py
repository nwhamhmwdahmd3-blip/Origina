#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
callback_handlers.py - معالجات الأزرار المنفصلة
"""

import asyncio
import json
import logging
import shutil

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes

from config import CONFIG, PATHS
from database import DB
from utils import (
    TimeUtils, safe_send, is_authorized_in_group,
    invalidate_auth_cache, StateManager, UserState,
    KeyboardFactory, TranslationManager, CB,
    _auto_reply_cache, export_auto_replies, import_auto_replies,
    fetch_json_from_url, get_ram_usage, METRICS,
    get_reply_from_file, _increment_usage_async
)

logger = logging.getLogger(__name__)


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
            # ========== الأزرار الأساسية ==========
            if data in [CB.MAIN, CB.BACK]:
                await query.answer()
                from handlers import CommandHandlers
                await CommandHandlers.start(update, context)
                return

            if data == CB.CANCEL:
                StateManager.clear(user_id)
                await query.answer("❌ تم الإلغاء")
                return

            if data == CB.HELP:
                await query.answer()
                from handlers import CommandHandlers
                await CommandHandlers.help_command(update, context)
                return

            if data == CB.TRIAL:
                await query.answer()
                if await DB.has_used_trial(user_id):
                    await query.edit_message_text("❌ استخدمت التجربة")
                else:
                    days = await DB.activate_trial(user_id)
                    await query.edit_message_text(f"🎁 {days} يوم!")
                return

            if data == CB.DEVELOPER:
                await query.answer()
                from handlers import CommandHandlers
                await CommandHandlers.developer(update, context)
                return

            if data == CB.SUBSCRIBE:
                await query.answer()
                from handlers import CommandHandlers
                await CommandHandlers.subscribe(update, context)
                return

            if data == CB.SUPPORT:
                await query.answer()
                from handlers import CommandHandlers
                await CommandHandlers.support(update, context)
                return

            if data == CB.LANGUAGE:
                await query.answer()
                from handlers import CommandHandlers
                await CommandHandlers.language(update, context)
                return

            if data == CB.CHECK_SUB:
                await query.answer()
                from handlers import CommandHandlers
                await CommandHandlers.start(update, context)
                return

            # ========== الإعدادات ==========
            if data == CB.SETTINGS:
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings")
                await query.edit_message_text(
                    f"⚙️ **الإعدادات**\n\n📤 النشر التلقائي: {auto}\n♻️ إعادة التدوير: {recycle}",
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

            # ========== الباقات ==========
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

            if data == CB.INVOICES:
                invoices = await DB.get_user_invoices(user_id, 10)
                if not invoices:
                    await query.edit_message_text("📭 لا توجد فواتير")
                    return
                text = "🧾 **فواتيري**\n\n"
                for inv in invoices:
                    text += f"• #{inv['number']} - {inv['amount']} ⭐ - {inv['status']}\n"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            # ========== الإحالات ==========
            if data == CB.REFERRAL:
                stats = await DB.get_referral_stats(user_id)
                code = await DB.get_referral_code(user_id)
                text = (
                    f"🔗 **الإحالات**\n\n"
                    f"🔗 رابطك: `https://t.me/{CONFIG.BOT_USERNAME}?start=ref_{code}`\n"
                    f"👥 الإجمالي: {stats['total']}\n"
                    f"🎁 المتاح: {stats['available']} يوم"
                )
                kb = KeyboardFactory.build("referral")
                await query.edit_message_text(text, reply_markup=kb)
                return

            if data == CB.REF_CLAIM:
                days = await DB.claim_referral_reward(user_id)
                await query.edit_message_text(f"✅ صرفت {days} يوم!" if days else "📭 لا توجد مكافآت")
                return

            if data == CB.REF_LIST:
                referrals = await DB.get_referrals_list(user_id)
                text = "📋 **المُحالين**\n\n" + "\n".join([f"• `{r}`" for r in referrals[:20]]) if referrals else "📭 لا يوجد"
                await query.edit_message_text(text)
                return

            # ========== التذكيرات ==========
            if data == CB.REMINDER:
                settings = await DB.get_reminder_settings(user_id)
                sub = "✅" if settings.get('subscription_reminder', False) else "❌"
                daily = "✅" if settings.get('daily_stats_reminder', False) else "❌"
                weekly = "✅" if settings.get('weekly_report', False) else "❌"
                days = settings.get('reminder_days_before', 3)
                text = (
                    f"⏰ **التذكيرات**\n\n"
                    f"🔔 الاشتراك: {sub}\n"
                    f"📊 يومي: {daily}\n"
                    f"📈 أسبوعي: {weekly}\n"
                    f"📅 الأيام: {days}"
                )
                kb = KeyboardFactory.build("reminder")
                await query.edit_message_text(text, reply_markup=kb)
                return

            if data == CB.REM_TOGGLE_SUB:
                s = await DB.get_reminder_settings(user_id)
                await DB.update_reminder_settings(user_id, subscription_reminder=not s.get('subscription_reminder', False))
                await CallbackHandlers.handle(update, context)
                return

            if data == CB.REM_TOGGLE_DAILY:
                s = await DB.get_reminder_settings(user_id)
                await DB.update_reminder_settings(user_id, daily_stats_reminder=not s.get('daily_stats_reminder', False))
                await CallbackHandlers.handle(update, context)
                return

            if data == CB.REM_TOGGLE_WEEKLY:
                s = await DB.get_reminder_settings(user_id)
                await DB.update_reminder_settings(user_id, weekly_report=not s.get('weekly_report', False))
                await CallbackHandlers.handle(update, context)
                return

            if data == CB.REM_SET_DAYS:
                StateManager.set(user_id, UserState.WAIT_REM_DAYS)
                await query.edit_message_text("📅 أرسل عدد الأيام (1-30):")
                return

            # ========== الترجمة ==========
            if data == CB.TRANSLATION:
                cur = await DB.get_user_language(user_id)
                kb = KeyboardFactory.build("translation")
                await query.edit_message_text(f"🌐 الترجمة: {cur}", reply_markup=kb)
                return

            if data == CB.TRANS_OFF:
                await DB.set_user_language(user_id, 'off')
                await query.edit_message_text("✅ تم إيقاف الترجمة")
                return

            if data.startswith(CB.TRANS_SET):
                lang_set = data.split(":")[-1]
                await DB.set_user_language(user_id, lang_set)
                await query.edit_message_text(f"✅ تم التعيين: {lang_set}")
                return

            # ========== المسابقات ==========
            if data == CB.CONTESTS:
                from handlers import CommandHandlers
                await CommandHandlers.contests(update, context)
                return

            if data == CB.CONTEST_WINNERS:
                winners = await DB.get_contest_winners(10)
                if not winners:
                    await query.edit_message_text("📭 لا يوجد فائزون")
                    return
                text = "🏆 **الفائزون**\n\n" + "\n".join([f"• {w['title']} → `{w['winner_id']}`" for w in winners])
                await query.edit_message_text(text)
                return

            if data.startswith(CB.CONTEST_JOIN):
                cid = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
                context.user_data['contest_join'] = cid
                await query.answer()
                await safe_send(context.bot, user_id, "📝 أرسل إجابتك:")
                return

            # ========== الدعم ==========
            if data == CB.SUPPORT_TICKET:
                StateManager.set(user_id, UserState.SUPPORT_MODE)
                await query.answer()
                await safe_send(context.bot, user_id, "📞 أرسل رسالتك:")
                return

            # ========== القنوات ==========
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
                        InlineKeyboardButton("➕ إضافة قناة", callback_data=CB.CH_ADD),
                        InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)
                    ]])
                    await query.edit_message_text("📭 لا توجد قنوات!\n\nاضغط للإضافة:", reply_markup=kb)
                    return
                text = "📡 **قنواتي**\n\n"
                kb = []
                for ch in channels:
                    st = "✅" if not ch['banned'] else "🚫"
                    text += f"{st} {ch['channel_name']} (`{ch['channel_id']}`)\n"
                    if not ch['banned']:
                        kb.append([InlineKeyboardButton(f"📌 {ch['channel_name'][:20]}", callback_data=f"{CB.CH_SEL}{ch['id']}")])
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

            # ========== المنشورات ==========
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
                    kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]]
                    await query.edit_message_text(text if posts else "📭 لا يوجد", reply_markup=InlineKeyboardMarkup(kb))
                return

            if data == CB.POST_REC:
                active = await DB.get_active_channel(user_id)
                if active:
                    count = await DB.reset_posts(active)
                    await query.edit_message_text(f"♻️ {count} منشور!")
                return

            if data == CB.PUB_ALL:
                channels = await DB.get_user_channels(user_id)
                tasks = []
                for ch in channels:
                    post = await DB.get_next_post(ch['id'])
                    if post:
                        ch_info = await DB.get_channel_info(ch['id'])
                        if ch_info:
                            tasks.append(CallbackHandlers._publish_single(context.bot, ch['id'], ch_info['channel_id'], post))
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    await query.edit_message_text("✅ تم النشر!")
                return

            # ========== المجموعات ==========
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

            # ========== لوحة الأدمن ==========
            if data == CB.ADMIN:
                if CONFIG.is_developer(user_id):
                    kb = KeyboardFactory.build("admin_panel")
                    await query.edit_message_text("👑 لوحة الأدمن", reply_markup=kb)
                else:
                    await query.answer("❌ لا صلاحية", show_alert=True)
                return

            # ========== أزرار الأمان ==========
            if data.startswith("sec_"):
                await CallbackHandlers._handle_security(update, context, query, user_id)
                return

            # ========== أزرار الأدمن ==========
            if data.startswith("admin_"):
                if CONFIG.is_developer(user_id):
                    await CallbackHandlers._handle_admin(update, context, query, user_id)
                return

            # ========== أزرار الردود ==========
            if data.startswith("auto_reply_"):
                await CallbackHandlers._handle_auto_reply(update, context, query, user_id)
                return

            # ========== اللغة ==========
            if data.startswith("lang_"):
                lang_set = data.split("_")[-1]
                await DB.set_user_language(user_id, lang_set)
                await query.answer(f"✅ {lang_set}")
                from handlers import CommandHandlers
                await CommandHandlers.start(update, context)
                return

            await query.answer("⚠️ غير متوفر", show_alert=True)

        except Exception as e:
            logger.error(f"Callback error: {e}", exc_info=True)
            try:
                await query.answer("❌ خطأ", show_alert=True)
            except:
                pass

    # ========== الدوال المساعدة ==========

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
        except:
            await DB.increment_post_fail(post['id'])
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

    if data == CB.SEC_CLOSE:
        try:
            await query.message.delete()
        except:
            pass
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

    if action == "banned":
        kb = KeyboardFactory.build("banned_words", chat_id)
        await query.edit_message_text("🚫 **الكلمات المحظورة**", reply_markup=kb)
        return

    if action == "maxlen":
        StateManager.set(user_id, UserState.WAIT_MAX_LEN)
        context.user_data[f"sec_chat_{user_id}"] = chat_id
        await query.edit_message_text("📏 أرسل الحد الأقصى (0 = غير محدود):")
        return

    if action == "warn":
        settings = await DB.get_security_settings(chat_id)
        text = f"⚠️ **التحذيرات**\n\nالحد: {settings.get('max_warnings', 3)}\nالعقوبة: {settings.get('warn_penalty', 'ban')}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 العدد", callback_data=f"sec_warn_count:{chat_id}"),
             InlineKeyboardButton("⚖️ العقوبة", callback_data=f"sec_warn_penalty:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"{CB.GRP_SET}{chat_id}")]
        ])
        await query.edit_message_text(text, reply_markup=kb)
        return

    if action == "warn_count":
        StateManager.set(user_id, UserState.WAIT_WARN_COUNT)
        context.user_data[f"sec_chat_{user_id}"] = chat_id
        await query.edit_message_text("📝 أرسل العدد (1-10):")
        return

    if action == "warn_penalty":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 حظر", callback_data=f"sec_set_warn_penalty:{chat_id}:ban"),
             InlineKeyboardButton("🔇 كتم", callback_data=f"sec_set_warn_penalty:{chat_id}:mute")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"sec_warn:{chat_id}")]
        ])
        await query.edit_message_text("⚖️ اختر العقوبة:", reply_markup=kb)
        return

    if action == "set_warn_penalty":
        if len(parts) >= 3:
            penalty = parts[2]
            await DB.execute("UPDATE group_security SET warn_penalty=? WHERE chat_id=?", (penalty, chat_id))
            await query.edit_message_text(f"✅ تم التعيين: {penalty}")
        return

    if action == "del_pen":
        kb = KeyboardFactory.build("penalty", chat_id)
        await query.edit_message_text("⚖️ عقوبة الحذف:", reply_markup=kb)
        return

    if action == "penalty":
        kb = KeyboardFactory.build("penalty", chat_id)
        await query.edit_message_text("⚖️ العقوبة الأساسية:", reply_markup=kb)
        return

    if action == "adv_act":
        kb = KeyboardFactory.build("advanced_actions", chat_id)
        await query.edit_message_text("🛠️ إجراءات متقدمة:", reply_markup=kb)
        return

    if action == "act_log":
        logs = await DB.get_admin_logs(chat_id, 20)
        if not logs:
            await query.edit_message_text("📭 لا توجد سجلات")
            return
        text = "📜 **آخر الإجراءات**\n\n"
        for log in logs:
            text += f"• {log['action']} → {log['target_id'] or '-'}\n"
        await query.edit_message_text(text)
        return

    if action == "auto_reply_menu":
        kb = KeyboardFactory.build("auto_reply_manage", chat_id)
        await query.edit_message_text("📝 الردود التلقائية:", reply_markup=kb)
        return

    await query.answer()

@staticmethod
async def _handle_admin(update, context, query, user_id):
    data = query.data

    if data == CB.ADMIN_USERS:
        stats = await DB.get_user_stats()
        await query.edit_message_text(f"👥 {stats['users']} مستخدم\n⛔ {stats['banned']} محظور")
        return

    if data == CB.ADMIN_BANNED:
        users = await DB.get_all_users()
        banned = [str(u[0]) for u in users if u[1] == 1]
        text = "⛔ **المحظورين**\n\n" + "\n".join(banned[:20]) if banned else "لا يوجد"
        await query.edit_message_text(text)
        return

    if data == CB.ADMIN_UNBAN_ALL:
        await DB.execute("UPDATE users SET banned=0 WHERE banned=1")
        await query.edit_message_text("✅ تم إلغاء حظر الجميع")
        return

    if data == CB.ADMIN_CHANNELS:
        channels = await DB.fetchall("SELECT channel_id, channel_name, banned FROM user_channels LIMIT 50")
        text = "📡 **القنوات**\n\n"
        for c in channels:
            text += f"{'✅' if not c[2] else '🚫'} {c[1]}\n"
        await query.edit_message_text(text if channels else "📭 لا توجد")
        return

    if data == CB.ADMIN_BANNED_CH:
        channels = await DB.fetchall("SELECT channel_id, channel_name FROM user_channels WHERE banned=1")
        text = "🚫 **المحظورة**\n\n"
        for c in channels:
            text += f"• {c[1]}\n"
        await query.edit_message_text(text if channels else "📭 لا يوجد")
        return

    if data == CB.ADMIN_ACTIVATE_CH:
        await DB.execute("UPDATE user_channels SET banned=0 WHERE banned=1")
        await query.edit_message_text("✅ تم التفعيل")
        return

    if data == CB.ADMIN_GROUPS:
        groups = await DB.fetchall("SELECT chat_id, chat_name, banned FROM bot_groups LIMIT 50")
        text = "👥 **المجموعات**\n\n"
        for g in groups:
            text += f"{'✅' if not g[2] else '🚫'} {g[1]}\n"
        await query.edit_message_text(text if groups else "📭 لا توجد")
        return

    if data == CB.ADMIN_BANNED_GR:
        groups = await DB.fetchall("SELECT chat_id, chat_name FROM bot_groups WHERE banned=1")
        text = "🚫 **المحظورة**\n\n"
        for g in groups:
            text += f"• {g[1]}\n"
        await query.edit_message_text(text if groups else "📭 لا يوجد")
        return

    if data == CB.ADMIN_UNBAN_GR:
        await DB.execute("UPDATE bot_groups SET banned=0 WHERE banned=1")
        await query.edit_message_text("✅ تم إلغاء الحظر")
        return

    if data == CB.ADMIN_ADD_ADMIN:
        StateManager.set(user_id, UserState.WAIT_ADMIN_ADD)
        await query.edit_message_text("👑 أرسل معرف المشرف:")
        return

    if data == CB.ADMIN_REM_ADMIN:
        StateManager.set(user_id, UserState.WAIT_ADMIN_REM)
        await query.edit_message_text("🗑️ أرسل معرف المشرف:")
        return

    if data == CB.ADMIN_RAM:
        ram = get_ram_usage()
        await query.edit_message_text(f"🖥️ الرام: {ram['percent']}%")
        return

    if data == CB.ADMIN_STATS:
        stats = await DB.get_user_stats()
        await query.edit_message_text(f"👥 {stats['users']} مستخدم\n⛔ {stats['banned']} محظور")
        return

    if data == CB.ADMIN_METRICS:
        m = METRICS.get_stats()
        await query.edit_message_text(f"📊 API: {m['api_calls_last_hour']}\n⚠️ أخطاء: {m['errors_last_hour']}")
        return

    if data == CB.ADMIN_BACKUP:
        try:
            backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(PATHS.DB, backup_file)
            await safe_send(context.bot, user_id, f"✅ {backup_file.name}")
        except:
            pass
        return

    if data == CB.ADMIN_RESTORE:
        backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not backups:
            await query.edit_message_text("📭 لا توجد نسخ")
            return
        kb = [[InlineKeyboardButton(b.name, callback_data=f"{CB.ADMIN_RESTORE_SEL}{b.name}")] for b in backups[:10]]
        await query.edit_message_text("🔄 اختر النسخة:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith(CB.ADMIN_RESTORE_SEL):
        filename = data.split(":")[-1]
        filepath = PATHS.BACKUPS / filename
        if filepath.exists():
            shutil.copy2(filepath, PATHS.DB)
            await query.edit_message_text("✅ تمت الاستعادة")
        return

    if data == CB.ADMIN_SEND_UPDATE:
        StateManager.set(user_id, UserState.WAIT_UPDATE)
        await query.edit_message_text("📢 أرسل التحديث:")
        return

    if data == CB.ADMIN_SET_UPDATE_CH:
        StateManager.set(user_id, UserState.WAIT_UPDATE_CH)
        await query.edit_message_text("📢 أرسل معرف القناة:")
        return

    if data == CB.ADMIN_SHOW_UPDATE:
        ch = await DB.get_updates_channel()
        await query.edit_message_text(f"📢 @{ch}" if ch else "📭 غير محدد")
        return

    if data == CB.ADMIN_FORCE_SUB:
        ch = await DB.get_force_subscribe_channel()
        await query.edit_message_text(f"🔒 @{ch}" if ch else "🔒 غير محدد")
        return

    if data == CB.ADMIN_SET_FORCE:
        StateManager.set(user_id, UserState.WAIT_FORCE)
        await query.edit_message_text("🔒 أرسل معرف القناة:")
        return

    if data == CB.ADMIN_BROADCAST:
        StateManager.set(user_id, UserState.WAIT_BROADCAST)
        await query.edit_message_text("📨 أرسل الرسالة:")
        return

    if data == CB.ADMIN_TICKETS:
        tickets = await DB.get_tickets()
        if not tickets:
            await query.edit_message_text("📭 لا توجد تذاكر")
            return
        text = "📋 **التذاكر**\n\n"
        for t in tickets:
            text += f"#{t['ticket_number']} - `{t['user_id']}`\n"
        await query.edit_message_text(text)
        return

    if data == CB.ADMIN_DEL_TICKETS:
        await DB.delete_all_tickets()
        await query.edit_message_text("✅ تم الحذف")
        return

    if data == CB.ADMIN_LOG_CH:
        log_id = await DB.get_log_channel()
        await query.edit_message_text(f"📋 {log_id}" if log_id else "📋 غير محدد")
        return

    if data == CB.ADMIN_SET_LOG_CH:
        StateManager.set(user_id, UserState.WAIT_LOG_CH)
        await query.edit_message_text("📋 أرسل معرف القناة:")
        return

    if data == CB.ADMIN_REPLIES:
        stats = await DB.get_auto_reply_stats(-1, 20)
        text = "📊 **الردود**\n\n"
        for kw, cnt in stats:
            text += f"• {kw}: {cnt}\n"
        await query.edit_message_text(text if stats else "📭 لا يوجد")
        return

    if data == CB.ADMIN_ADD_REPLY:
        StateManager.set(user_id, UserState.WAIT_KEYWORD)
        await query.edit_message_text("📝 أرسل الكلمة:")
        return

    if data == CB.ADMIN_LIST_REPLIES:
        replies = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=0 LIMIT 20")
        text = "📋 **الردود**\n\n"
        for r in replies:
            text += f"• {r[0]} ({r[1]})\n"
        await query.edit_message_text(text if replies else "📭 لا يوجد")
        return

    if data == CB.ADMIN_DEL_REPLY:
        StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
        context.user_data['auto_chat'] = -1
        await query.edit_message_text("🗑️ أرسل الكلمة:")
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

    if data == CB.ADMIN_LIST_BANNED:
        words = await DB.get_banned_words(-1)
        text = "🚫 **الكلمات**\n\n" + "\n".join(words) if words else "📭 لا يوجد"
        await query.edit_message_text(text)
        return

    if data == CB.ADMIN_REM_BANNED:
        StateManager.set(user_id, UserState.WAIT_REM_GLOBAL_BAN)
        await query.edit_message_text("🗑️ أرسل الكلمة:")
        return

    if data == CB.ADMIN_CREATE_CONTEST:
        StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
        await query.edit_message_text("🏆 أرسل العنوان:")
        return

    if data == CB.ADMIN_DECLARE_WINNER:
        contests = await DB.fetchall("SELECT id, title FROM contests WHERE status='active'")
        if not contests:
            await query.edit_message_text("📭 لا توجد مسابقات")
            return
        kb = [[InlineKeyboardButton(title, callback_data=f"{CB.DECLARE_WINNER_SEL}{cid}")] for cid, title in contests]
        await query.edit_message_text("🏆 اختر المسابقة:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith(CB.DECLARE_WINNER_SEL):
        cid = int(data.split(":")[-1])
        winner = await DB.fetchone("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,))
        if winner:
            await DB.declare_winner(cid, winner[0])
            await query.edit_message_text(f"✅ الفائز: {winner[0]}")
        return

    if data == CB.ADMIN_EXPORT_REPLIES:
        count = await export_auto_replies(-1)
        await query.edit_message_text(f"✅ تم تصدير {count} رد")
        return

    if data == CB.ADMIN_IMPORT_REPLIES:
        StateManager.set(user_id, UserState.WAIT_IMPORT_FILE)
        await query.edit_message_text("📤 أرسل ملف JSON:")
        return

    if data == CB.ADMIN_IMPORT_GITHUB:
        StateManager.set(user_id, UserState.WAIT_GITHUB_URL)
        await query.edit_message_text("📥 أرسل الرابط:")
        return

    if data == CB.ADMIN_REFRESH_CACHE:
        _auto_reply_cache.invalidate()
        await query.edit_message_text("✅ تم التحديث")
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

    if not await is_authorized_in_group(context.bot, chat_id, user_id):
        await query.answer("❌ لا صلاحية", show_alert=True)
        return

    if action == "toggle":
        s = await DB.get_auto_reply_settings(chat_id)
        await DB.update_auto_reply_settings(chat_id, enabled=not s.get('enabled', False))
        await query.answer("✅ تم")
        return

    if action == "admins":
        s = await DB.get_auto_reply_settings(chat_id)
        await DB.update_auto_reply_settings(chat_id, only_admins=not s.get('only_admins', False))
        await query.answer("✅ تم")
        return

    if action == "reset":
        await DB.reset_auto_replies(chat_id)
        await query.answer("✅ تم الحذف")
        return

    if action == "stats":
        stats = await DB.get_auto_reply_stats(chat_id, 10)
        text = "📊 **الإحصائيات**\n\n"
        for kw, cnt in stats:
            text += f"• {kw}: {cnt}\n"
        await query.edit_message_text(text if stats else "📭 لا يوجد")
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

    if action == "list":
        replies = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? LIMIT 20", (chat_id,))
        text = "📋 **الردود**\n\n"
        for r in replies:
            text += f"• {r[0]} ({r[1]})\n"
        await query.edit_message_text(text if replies else "📭 لا يوجد")
        return

    if action == "menu":
        kb = KeyboardFactory.build("auto_reply_manage", chat_id)
        await query.edit_message_text("📝 الردود التلقائية:", reply_markup=kb)
        return

    await query.answer()

