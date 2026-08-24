#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_callback.py - معالجات الأزرار (الكولباك) - نسخة محسنة ومكتملة
=====================================================================
يتضمن معالجة جميع أزرار الـ Inline مع تحسينات أمنية وديناميكية.
"""

import asyncio
import re
import shutil
import logging
import json
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
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
    _REPLIES_FROM_FILE,
    get_min_publish_interval, invalidate_banned_words_cache,
    get_banned_words_cached
)

from handlers_command import CommandHandlers

logger = logging.getLogger(__name__)


# =====================================================================
# دوال مساعدة داخلية
# =====================================================================

async def _check_admin_simple(bot, chat_id: int, user_id: int) -> bool:
    """تتحقق ببساطة مما إذا كان المستخدم مشرفاً في المجموعة (أو مالكاً خفياً)."""
    if user_id == CONFIG.PRIMARY_OWNER_ID:
        return True
    return await is_authorized_in_group(bot, chat_id, user_id)


async def _get_penalty_info(chat_id: int, violation_type: str) -> dict:
    """تسترجع معلومات العقوبة لنوع مخالفة معين."""
    rule = await DB.get_violation_penalty(chat_id, violation_type)
    if rule:
        return {
            'penalty_type': rule['penalty_type'],
            'duration_seconds': rule['duration_seconds']
        }
    settings = await DB.get_security_settings(chat_id)
    return {
        'penalty_type': settings.get('warn_penalty', 'ban'),
        'duration_seconds': 0
    }


def _is_command_cancel(text: str) -> bool:
    """تتحقق مما إذا كان النص أمر إلغاء."""
    return text and text.strip().lower() in ['/cancel', 'إلغاء', 'cancel']


async def _reply_and_clear_state(bot, user_id: int, chat_id: int, text: str, reply_markup=None):
    """ترسل رداً وتمسح حالة المستخدم."""
    StateManager.clear(user_id)
    await safe_send(bot, chat_id, text, reply_markup)


# =====================================================================
# المعالج الرئيسي
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
                if not await _check_admin_simple(context.bot, chat_id, user_id):
                    try:
                        await query.answer("❌ لا صلاحية", show_alert=True)
                    except BadRequest:
                        pass
                    return
                settings = await DB.get_security_settings(chat_id)
                text = KeyboardFactory._format_security_text(settings)
                kb = KeyboardFactory.build("security", chat_id=chat_id, user_id=user_id, lang=lang)
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
                if not await _check_admin_simple(context.bot, chat_id, user_id):
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
                if not await _check_admin_simple(context.bot, chat_id, user_id):
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

        valid_violations = {"links","mentions","banned_words","flood","max_len","service","videos","audio","documents","stickers","forwarded","polls","games","voice","video_note"}

        action = parts[0].replace("sec_", "")

        logger.info(f"🔍 _handle_security: action={action}, chat_id={chat_id}, data={data}")

        if not await _check_admin_simple(context.bot, chat_id, user_id):
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
            kb = KeyboardFactory.build("security", chat_id=chat_id, user_id=user_id, lang=lang)
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
            # التحقق من صلاحية البوت لتغيير كل الإعدادات (يتطلب صلاحيات مشرف)
            perms = await check_bot_permissions(context.bot, chat_id)
            if not perms.get('can_act', False):
                try:
                    await query.answer(await get_text(lang, 'bot_no_perms', reason=perms.get('reason', '')), show_alert=True)
                except BadRequest:
                    pass
                return

            async with DB._get_connection() as conn:
                for f in field_map.values():
                    await conn.execute(f"UPDATE group_security SET {f}=1 WHERE chat_id=?", (chat_id,))
                await conn.commit()
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id=chat_id, user_id=user_id, lang=lang)
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
            perms = await check_bot_permissions(context.bot, chat_id)
            if not perms.get('can_act', False):
                try:
                    await query.answer(await get_text(lang, 'bot_no_perms', reason=perms.get('reason', '')), show_alert=True)
                except BadRequest:
                    pass
                return

            async with DB._get_connection() as conn:
                for f in field_map.values():
                    await conn.execute(f"UPDATE group_security SET {f}=0 WHERE chat_id=?", (chat_id,))
                await conn.commit()
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id=chat_id, user_id=user_id, lang=lang)
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
            kb = KeyboardFactory.build("penalty", chat_id=chat_id, user_id=user_id, lang=lang)
            await query.edit_message_text("⚖️ عقوبة الحذف:", reply_markup=kb)
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "penalty":
            kb = KeyboardFactory.build("penalty", chat_id=chat_id, user_id=user_id, lang=lang)
            await query.edit_message_text("⚖️ العقوبة:", reply_markup=kb)
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "adv_act":
            kb = KeyboardFactory.build("advanced_actions", chat_id=chat_id, user_id=user_id, lang=lang)
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
            kb = KeyboardFactory.build("auto_reply_manage", chat_id=chat_id, user_id=user_id, lang=lang)
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

        if action == "antiflood_settings":
            await CallbackHandlers._handle_antiflood_settings(update, context, query, chat_id, user_id, lang)
            return

        if action == "night_settings":
            await CallbackHandlers._handle_night_settings(update, context, query, chat_id, user_id, lang)
            return

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

        if action == "slow_mode_seconds":
            StateManager.set(user_id, UserState.WAIT_SLOW_MODE_SECONDS)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("⏱️ أرسل مدة الوضع البطيء بالثواني (0-3600):")
            try:
                await query.answer()
            except BadRequest:
                pass
            return

        if action == "penalty_durations":
            await CallbackHandlers._handle_penalty_durations(update, context, query, chat_id, user_id, lang)
            return

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
            if not await _check_admin_simple(context.bot, chat_id, user_id):
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

        elif data == "admin_uptime":
            try:
                m = METRICS.get_stats()
                up_sec = m.get('uptime_seconds', 0)
                days, rem = divmod(up_sec, 86400)
                hours, rem = divmod(rem, 3600)
                mins, secs = divmod(rem, 60)
                text = "⏳ **فترة تشغيل البوت**\n\n"
                text += f"🕒 {int(days)} يوم, {int(hours)} ساعة, {int(mins)} دقيقة, {int(secs)} ثانية"
            except Exception as e:
                text = f"❌ تعذر حساب وقت التشغيل: {e}"
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

        if not await _check_admin_simple(context.bot, chat_id, user_id):
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
                reply_markup=KeyboardFactory.build("auto_reply_manage", chat_id=chat_id, user_id=user_id, lang=lang)
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
                if not await _check_admin_simple(context.bot, chat_id, user_id):
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

        if not await _check_admin_simple(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id)
            try:
                await query.answer(await get_text(lang, 'unauthorized'), show_alert=True)
            except BadRequest:
                pass
            return

        # التحقق من صلاحيات البوت
        perms = await check_bot_permissions(context.bot, chat_id)
        if not perms.get('can_act', False):
            lang = await DB.get_user_language(user_id)
            try:
                await query.answer(await get_text(lang, 'bot_no_perms', reason=perms.get('reason', '')), show_alert=True)
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

        if not await _check_admin_simple(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id)
            try:
                await query.answer(await get_text(lang, 'unauthorized'), show_alert=True)
            except BadRequest:
                pass
            return

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
