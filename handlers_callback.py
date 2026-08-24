#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_callback.py - معالجات الأزرار (الكولباك) - النسخة الكاملة النهائية
جميع الأزرار تعمل - جميع المعالجات موجودة
"""

import asyncio
import shutil
import logging
import json
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TimedOut

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

MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096
MAX_BACKUPS = 10


async def _safe_answer(query, text=None, show_alert=False):
    try:
        if text:
            await query.answer(text, show_alert=show_alert)
        else:
            await query.answer()
        return True
    except (BadRequest, TimedOut) as e:
        logger.debug(f"Query answer failed: {e}")
        return False
    except Exception as e:
        logger.warning(f"⚠️ فشل query.answer: {e}")
        return False


def _mask_id(id_value, prefix=3, suffix=2):
    if id_value is None:
        return "***"
    s = str(id_value)
    if len(s) <= 5:
        return "***"
    return s[:prefix] + "***" + s[-suffix:] if len(s) > prefix + suffix else s[:prefix] + "***"


class CallbackHandlers:
    """جميع معالجات ضغطات الأزرار"""

    @staticmethod
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        data = query.data
        if not data:
            return

        user_id = query.from_user.id
        lang = await DB.get_user_language(user_id) or 'ar'

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
                await _safe_answer(query, "لا تغيير")
                return

            if base_data == "start_btn":
                await _safe_answer(query)
                context.args = []
                await CommandHandlers.start(update, context)
                return

            if base_data in [CB.MAIN, CB.BACK]:
                await _safe_answer(query)
                StateManager.clear(user_id)
                context.args = []
                await CommandHandlers.start(update, context)
                return

            if base_data == CB.CANCEL:
                StateManager.clear(user_id)
                await _safe_answer(query, "❌ تم الإلغاء")
                return

            if base_data == CB.HELP:
                await _safe_answer(query)
                await CommandHandlers.help_command(update, context)
                return

            if base_data == CB.TRIAL:
                await _safe_answer(query)
                if await DB.has_used_trial(user_id):
                    await query.edit_message_text(await get_text(lang, 'trial_used'))
                    return
                days = await DB.activate_trial(user_id)
                await query.edit_message_text(await get_text(lang, 'trial_activated', days=days))
                return

            if base_data == CB.DEVELOPER:
                await _safe_answer(query)
                await CommandHandlers.developer(update, context)
                return

            if base_data == CB.SUBSCRIBE:
                await _safe_answer(query)
                await CommandHandlers.subscribe(update, context)
                return

            if base_data == CB.SUPPORT:
                await _safe_answer(query)
                await CommandHandlers.support(update, context)
                return

            if base_data == CB.LANGUAGE:
                await _safe_answer(query)
                await CommandHandlers.language(update, context)
                return

            if base_data == CB.CHECK_SUB:
                await _safe_answer(query)
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
                await _safe_answer(query)
                return

            if base_data == CB.TOGGLE_AUTO:
                await _safe_answer(query, "🔄 جارٍ التحديث...")
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
                await _safe_answer(query, "🔄 جارٍ التحديث...")
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
                await _safe_answer(query)
                return

            if base_data == "gift_plans":
                await _safe_answer(query)
                plans = await DB.get_gift_plans()
                if not plans:
                    await query.edit_message_text("📭 لا توجد خطط متاحة حالياً.")
                    return
                kb = []
                for plan in plans:
                    kb.append([InlineKeyboardButton(
                        f"🎁 {plan['days']} يوم - {plan['price']} ⭐",
                        callback_data=f"buy_gift:{plan['id']}"
                    )])
                kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
                text = "💎 **شراء كود هدية**\n\nاختر المدة المناسبة:"
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if base_data == "redeem_gift":
                await _safe_answer(query)
                await CommandHandlers.redeem_gift(update, context)
                return

            if data.startswith("buy_sub_"):
                await _safe_answer(query, "🔄 جارٍ التحضير...")
                try:
                    days = int(data.split("_")[-1])
                except (ValueError, IndexError):
                    await _safe_answer(query, "❌ بيانات غير صالحة", show_alert=True)
                    return
                plan_names = {1: "يوم", 7: "أسبوع", 30: "شهر", 90: "3 أشهر", 365: "سنة"}
                plan_name = plan_names.get(days)
                if not plan_name:
                    await _safe_answer(query, "❌ باقة غير موجودة", show_alert=True)
                    return
                plan = await DB.get_plan_by_name(plan_name)
                if not plan:
                    await _safe_answer(query, "❌ باقة غير موجودة", show_alert=True)
                    return
                invoice_number = await DB.create_invoice(user_id, plan['id'], plan['price'])
                if not invoice_number:
                    await _safe_answer(query, "❌ فشل الدفع", show_alert=True)
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
                    await _safe_answer(query, "✅ تم إرسال الفاتورة")
                    await query.message.delete()
                except Exception as e:
                    logger.error(f"❌ فشل إرسال الفاتورة: {e}")
                    await DB.execute("UPDATE invoices SET status='cancelled' WHERE number=?", (invoice_number,))
                    await _safe_answer(query, f"❌ {str(e)[:50]}", show_alert=True)
                return

            if base_data == CB.INVOICES:
                invoices = await DB.get_user_invoices(user_id, 10)
                if not invoices:
                    await query.edit_message_text("📭 لا توجد فواتير")
                    await _safe_answer(query)
                    return
                text = "🧾 **فواتيري**\n\n"
                for inv in invoices:
                    text += f"• #{inv['number']} - {inv['amount']} ⭐\n"
                kb = [[InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]]
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                await _safe_answer(query)
                return

            if base_data == CB.REFERRAL:
                await _safe_answer(query)
                stats = await DB.get_referral_stats(user_id)
                code = await DB.get_referral_code(user_id)
                text = f"🔗 **الإحالات**\n\n🔗 `https://t.me/{CONFIG.BOT_USERNAME}?start=ref_{code}`\n👥 {stats['total']}\n🎁 {stats['available']} يوم"
                kb = KeyboardFactory.build("referral", lang=lang)
                await query.edit_message_text(text, reply_markup=kb)
                return

            if base_data == CB.REF_CLAIM:
                await _safe_answer(query, "🔄 جارٍ الصرف...")
                days = await DB.claim_referral_reward(user_id)
                await query.edit_message_text(f"✅ {days} يوم!" if days else "📭 لا توجد")
                return

            if base_data == CB.REF_LIST:
                await _safe_answer(query)
                referrals = await DB.get_referrals_list(user_id)
                text = "📋 **المُحالين**\n\n" + "\n".join([f"• `{_mask_id(r)}`" for r in referrals[:20]]) if referrals else "📭 لا يوجد"
                await query.edit_message_text(text)
                return

            if base_data in [CB.REM_TOGGLE_SUB, CB.REM_TOGGLE_DAILY, CB.REM_TOGGLE_WEEKLY]:
                await _safe_answer(query, "🔄 جارٍ التحديث...")
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
                await _safe_answer(query)
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
                await _safe_answer(query)
                return

            if data.startswith(CB.REM_LANG + ":"):
                await _safe_answer(query, "✅ تم التحديث")
                lang_set = data.split(":")[-1]
                await DB.update_reminder_settings(user_id, notification_lang=lang_set)
                await query.edit_message_text(f"✅ تم تعيين لغة التذكير: {lang_set}")
                return

            if base_data == CB.TRANSLATION:
                await _safe_answer(query)
                cur = await DB.get_user_language(user_id) or 'ar'
                kb = KeyboardFactory.build("translation", lang=lang)
                await query.edit_message_text(f"🌐 الترجمة: {cur}", reply_markup=kb)
                return

            if base_data == CB.TRANS_OFF:
                await DB.set_user_language(user_id, 'off')
                await query.edit_message_text("✅ تم إيقاف الترجمة")
                await _safe_answer(query)
                return

            if data.startswith(CB.TRANS_SET + ":"):
                lang_set = data.split(":")[-1]
                await DB.set_user_language(user_id, lang_set)
                await query.edit_message_text(f"✅ تم تعيين: {lang_set}")
                await _safe_answer(query)
                return

            if base_data == CB.CONTESTS:
                await _safe_answer(query)
                await CommandHandlers.contests(update, context)
                return

            if base_data == CB.CONTEST_WINNERS:
                winners = await DB.get_contest_winners(10)
                if not winners:
                    await query.edit_message_text("📭 لا يوجد فائزون")
                    await _safe_answer(query)
                    return
                text = "🏆 **الفائزون**\n\n"
                for w in winners:
                    text += f"• {w['title']} → `{_mask_id(w['winner_id'])}`\n"
                await query.edit_message_text(text)
                await _safe_answer(query)
                return

            if data.startswith(CB.CONTEST_JOIN + ":"):
                cid = int(data.split(":")[-1])
                StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
                context.user_data['contest_join'] = cid
                await _safe_answer(query)
                await safe_send(context.bot, user_id, "📝 أرسل إجابتك:")
                return

            if base_data == CB.SUPPORT_TICKET:
                StateManager.set(user_id, UserState.SUPPORT_MODE)
                await _safe_answer(query)
                await safe_send(context.bot, user_id, "📞 أرسل رسالتك:")
                return

            if base_data == CB.CH_ADD:
                StateManager.set(user_id, UserState.WAIT_CHANNEL)
                await query.edit_message_text("📡 أرسل معرف القناة:")
                await _safe_answer(query)
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
                    await _safe_answer(query, "❌ لا يمكنك تحديد هذه القناة", show_alert=True)
                    return
                await _safe_answer(query)
                return

            if data.startswith(CB.CH_DEL + ":"):
                ch_id = int(data.split(":")[-1])
                success = await DB.delete_channel(user_id, ch_id)
                if success:
                    await _safe_answer(query, "✅ تم الحذف")
                else:
                    await _safe_answer(query, "❌ لا يمكنك حذف هذه القناة", show_alert=True)
                    return
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.CH_STATS + ":"):
                ch_id = int(data.split(":")[-1])
                row = await DB.fetchone("SELECT 1 FROM user_channels WHERE id=? AND user_id=?", (ch_id, user_id))
                if not row:
                    await _safe_answer(query, "❌ هذه القناة ليست لك", show_alert=True)
                    return
                stats = await DB.get_channel_stats(user_id, ch_id)
                text = f"📊 **إحصائيات القناة**\n\n"
                text += f"📝 المجموع: {stats['total']}\n"
                text += f"✅ المنشورة: {stats['published']}\n"
                text += f"⏳ غير المنشورة: {stats['unpublished']}"
                await query.edit_message_text(text)
                await _safe_answer(query)
                return

            if base_data == CB.POST_ADD:
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await _safe_answer(query, "❌ انتهى اشتراكك!", show_alert=True)
                    return
                active = await DB.get_active_channel(user_id)
                if not active:
                    await query.edit_message_text("❌ لا توجد قناة نشطة")
                    await _safe_answer(query)
                    return
                active_plan = await DB.get_active_plan(user_id)
                limit = active_plan['max_posts'] if active_plan else CONFIG.MAX_POSTS_PER_CHANNEL
                row = await DB.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (active,))
                total_posts = row[0] if row else 0
                if total_posts >= limit and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await _safe_answer(query, f"❌ وصلت للحد الأقصى ({limit} منشور) في هذه القناة.", show_alert=True)
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
                await _safe_answer(query, "✅ تم إنهاء الإضافة")
                await query.edit_message_text("✅ تم إنهاء إضافة المنشورات.")
                return

            if base_data == CB.POST_PUB:
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await _safe_answer(query, "❌ انتهى اشتراكك!", show_alert=True)
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
                await _safe_answer(query)
                return

            if base_data == CB.PUB_ALL:
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await _safe_answer(query, "❌ انتهى اشتراكك! يرجى تجديد الاشتراك", show_alert=True)
                    return
                channels = await DB.get_user_channels(user_id)
                if not channels:
                    await query.edit_message_text("❌ لا توجد قنوات للنشر")
                    await _safe_answer(query)
                    return
                published_count = 0
                failed_count = 0
                await query.edit_message_text("⏳ جاري النشر...")
                await _safe_answer(query)
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
                    await _safe_answer(query, "❌ المنشور غير موجود", show_alert=True)
                    return
                ch_id = row['channel_db_id']
                row2 = await DB.fetchone("SELECT user_id FROM user_channels WHERE id=?", (ch_id,))
                if not row2 or row2['user_id'] != user_id:
                    await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                    return
                await DB.execute("DELETE FROM posts WHERE id=?", (post_id,))
                await query.edit_message_text("✅ تم حذف المنشور!")
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.POST_CLEAR + ":"):
                ch_id = int(data.split(":")[-1])
                row = await DB.fetchone("SELECT user_id FROM user_channels WHERE id=?", (ch_id,))
                if not row or row['user_id'] != user_id:
                    await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                    return
                await DB.execute("DELETE FROM posts WHERE channel_db_id=?", (ch_id,))
                await query.edit_message_text("✅ تم مسح جميع المنشورات!")
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if base_data == CB.GROUPS:
                await _safe_answer(query)
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
                    kb.append([InlineKeyboardButton(security_text, callback_data=f"{CB.GRP_SET}:{gid}")])
                back_text = KeyboardFactory.get_text("back", lang)
                kb.append([InlineKeyboardButton(back_text, callback_data=CB.BACK)])
                await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data.startswith(CB.GRP_SET + ":"):
                chat_id = int(data.split(":")[-1])
                context.user_data['security_chat_id'] = chat_id
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    await _safe_answer(query, "❌ لا صلاحية", show_alert=True)
                    return
                settings = await DB.get_security_settings(chat_id)
                text = KeyboardFactory._format_security_text(settings)
                kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
                await query.edit_message_text(text, reply_markup=kb)
                await _safe_answer(query)
                return

            if base_data == CB.ADMIN:
                if CONFIG.is_developer(user_id):
                    kb = KeyboardFactory.build("admin_panel", lang=lang)
                    await query.edit_message_text("👑 لوحة الأدمن", reply_markup=kb)
                    await _safe_answer(query)
                else:
                    await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
                return

            if data == "admin_grant_free":
                if not CONFIG.is_developer(user_id):
                    await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                    return
                StateManager.set(user_id, UserState.WAIT_GRANT_FREE)
                await query.edit_message_text("🎁 أرسل معرف المستخدم ثم عدد الأيام هكذا:\n`123456789 365`")
                await _safe_answer(query)
                return

            if data.startswith(CB.PANEL_LOCK + ":"):
                chat_id = int(data.split(":")[-1])
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    await _safe_answer(query, "❌ لا صلاحية", show_alert=True)
                    return
                await DB.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?,1,?,?)",
                                 (chat_id, TimeUtils.sql_iso(), user_id))
                await query.edit_message_text("🔒 تم قفل المجموعة!")
                await _safe_answer(query)
                return

            if data.startswith(CB.PANEL_UNLOCK + ":"):
                chat_id = int(data.split(":")[-1])
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    await _safe_answer(query, "❌ لا صلاحية", show_alert=True)
                    return
                await DB.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
                await query.edit_message_text("🔓 تم فتح المجموعة!")
                await _safe_answer(query)
                return

            if base_data == CB.PANEL_CLOSE:
                try:
                    await query.message.delete()
                except:
                    pass
                await _safe_answer(query, "✅ تم الإغلاق")
                return

            if data.startswith("sec_") or base_data.startswith("sec_"):
                await CallbackHandlers._handle_security(update, context, query, user_id, lang)
                return

            if data.startswith("admin_") or base_data.startswith("admin_"):
                if CONFIG.is_developer(user_id):
                    await CallbackHandlers._handle_admin(update, context, query, user_id, lang)
                else:
                    await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                return

            if data.startswith("auto_reply_") or base_data.startswith("auto_reply_"):
                await CallbackHandlers._handle_auto_reply(update, context, query, user_id, lang)
                return

            if data.startswith("sched_open:"):
                ch_id = int(data.split(":")[-1])
                row = await DB.fetchone("SELECT user_id FROM user_channels WHERE id=?", (ch_id,))
                if not row or row['user_id'] != user_id:
                    await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                    return
                kb = KeyboardFactory.build("channel_settings", chat_id=ch_id, lang=lang)
                await query.edit_message_text("📅 **جدولة القناة**", reply_markup=kb)
                await _safe_answer(query)
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
                await _safe_answer(query, f"✅ {lang_set}")
                context.args = []
                await CommandHandlers.start(update, context)
                return

            if data.startswith("buy_gift:"):
                await _safe_answer(query, "🔄 جارٍ التحضير...")
                plan_id = int(data.split(":")[-1])
                plan = await DB.get_gift_plan(plan_id)
                if not plan:
                    await _safe_answer(query, "❌ خطة غير موجودة", show_alert=True)
                    return
                invoice_number = await DB.create_invoice(user_id, plan_id, plan['price'], currency='XTR', provider='xtr_gift')
                if not invoice_number:
                    await _safe_answer(query, "❌ فشل إنشاء الفاتورة", show_alert=True)
                    return
                try:
                    await context.bot.send_invoice(
                        chat_id=user_id,
                        title=f"🎁 كود هدية {plan['days']} يوم",
                        description=f"ستحصل على كود هدية لمدة {plan['days']} يوم يمكنك إرساله لأي شخص.",
                        payload=json.dumps({'gift_plan_id': plan_id, 'invoice': invoice_number, 'type': 'gift'}),
                        provider_token="",
                        currency="XTR",
                        prices=[LabeledPrice(f"{plan['days']} يوم", plan['price'])]
                    )
                    await _safe_answer(query, "✅ تم إرسال الفاتورة")
                    await query.message.delete()
                except Exception as e:
                    logger.error(f"❌ فشل إرسال الفاتورة: {e}")
                    await DB.execute("UPDATE invoices SET status='cancelled' WHERE number=?", (invoice_number,))
                    await _safe_answer(query, f"❌ {str(e)[:50]}", show_alert=True)
                return

            if base_data == "my_gifts":
                await _safe_answer(query)
                try:
                    codes = await DB.fetchall("SELECT code, used_by, created_at FROM gift_codes WHERE creator_id=? ORDER BY created_at DESC LIMIT 20", (user_id,))
                    if not codes:
                        await query.edit_message_text("📋 **أكواد الهدايا الخاصة بك**\n\n🎁 لا توجد أكواد لديك بعد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]]))
                        return
                    text = "🎁 **أكواد الهدايا الخاصة بك:**\n\n"
                    for c in codes:
                        status = "🟢 متاح" if not c['used_by'] else "🔴 مستخدم"
                        text += f"🎟️ `{c['code']}`\n📌 الحالة: {status}\n📅 التاريخ: {c['created_at'][:10] if c['created_at'] else '-'}\n\n"
                    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]]))
                except Exception as e:
                    logger.error(f"❌ خطأ: {e}")
                    await query.edit_message_text("❌ **تعذر عرض أكواد الهدايا.**")
                return

            await _safe_answer(query, "⚠️ غير متوفر", show_alert=True)

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
            text = post.get('text', '')
            media_file_id = post.get('media_file_id')
            media_type = post.get('media_type')
            caption = text[:MAX_CAPTION_LENGTH] if text else None
            try:
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
                    await bot.send_message(chat_id=ch_tele, text=text[:MAX_MESSAGE_LENGTH] if text else ".")
            except Exception as e:
                logger.error(f"❌ فشل إرسال المنشور {post['id']}: {e}")
                await DB.increment_post_fail(post['id'])
                raise
            try:
                await DB.mark_post_published(post['id'])
                await DB.update_last_publish(ch_db_id)
                await DB.update_next_publish(ch_db_id)
            except Exception as e:
                logger.error(f"❌ فشل تحديث قاعدة البيانات: {e}")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"❌ فشل النشر: {e}")
            raise

    @staticmethod
    async def _show_channel_list(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        channels = await DB.get_user_channels(user_id)
        if not channels:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]
            ])
            await query.edit_message_text("📭 لا توجد قنوات!\nاضغط للإضافة:", reply_markup=kb)
            await _safe_answer(query)
            return
        text = "📡 **قنواتي**\n\n"
        kb = []
        for ch in channels:
            st = "✅" if not ch['banned'] else "🚫"
            masked_channel_id = _mask_id(ch['channel_id'])
            text += f"{st} {ch['channel_name']} (`{masked_channel_id}`)\n"
            kb.append([
                InlineKeyboardButton(f"📌 {ch['channel_name'][:20]}", callback_data=f"{CB.CH_SEL}:{ch['id']}"),
                InlineKeyboardButton(KeyboardFactory.get_text("sched_btn", lang), callback_data=f"sched_open:{ch['id']}")
            ])
            kb.append([
                InlineKeyboardButton(KeyboardFactory.get_text("ch_stats", lang), callback_data=f"{CB.CH_STATS}:{ch['id']}"),
                InlineKeyboardButton(KeyboardFactory.get_text("ch_del", lang), callback_data=f"{CB.CH_DEL}:{ch['id']}")
            ])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
        await _safe_answer(query)

    @staticmethod
    async def _show_post_list(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        active = await DB.get_active_channel(user_id)
        if not active:
            await query.edit_message_text("❌ لا توجد قناة نشطة")
            await _safe_answer(query)
            return
        posts = await DB.get_user_posts(user_id, active, 10)
        text = "📋 **منشوراتي**\n\n"
        kb = []
        for p in posts:
            text += f"🆔 {p['id']}: {(p['text'] or '')[:30]}\n"
            kb.append([InlineKeyboardButton(f"🗑️ حذف {p['id']}", callback_data=f"{CB.POST_DEL}:{p['id']}")])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("post_clear", lang), callback_data=f"{CB.POST_CLEAR}:{active}")])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("post_rec", lang), callback_data=CB.POST_REC)])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
        await query.edit_message_text(text if posts else "📭 لا يوجد", reply_markup=InlineKeyboardMarkup(kb))
        await _safe_answer(query)

    @staticmethod
    async def _handle_security(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
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

        action = parts[0].replace("sec_", "")
        logger.info(f"🔍 _handle_security: action={action}, chat_id={chat_id}")

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return

        # ========== جميع معالجات الأزرار ==========

        # ✅ زر الردود التلقائية
        if action == "auto_reply_menu":
            kb = KeyboardFactory.build("auto_reply_manage", chat_id=chat_id, lang=lang)
            await query.edit_message_text("📝 **إدارة الردود التلقائية**", reply_markup=kb)
            await _safe_answer(query)
            return

        # ✅ زر الإجراءات المتقدمة
        if action == "adv_act":
            kb = KeyboardFactory.build("advanced_actions", chat_id=chat_id, lang=lang)
            await query.edit_message_text("🛠️ **إجراءات متقدمة**", reply_markup=kb)
            await _safe_answer(query)
            return

        # ✅ زر العقوبات
        if action == "penalty":
            kb = KeyboardFactory.build("penalty", chat_id=chat_id, lang=lang)
            await query.edit_message_text("⚖️ **العقوبات**", reply_markup=kb)
            await _safe_answer(query)
            return

        # ✅ زر عقوبة الحذف
        if action == "del_pen":
            kb = KeyboardFactory.build("penalty", chat_id=chat_id, lang=lang)
            await query.edit_message_text("⚖️ **عقوبة الحذف**", reply_markup=kb)
            await _safe_answer(query)
            return

        # ✅ زر السجل
        if action == "act_log":
            logs = await DB.get_admin_logs(chat_id, 20)
            if not logs:
                await query.edit_message_text("📭 لا توجد سجلات")
            else:
                text = "📜 **السجل**\n\n"
                for log in logs:
                    text += f"• {log['action']} → {log['target_id'] or '-'}\n"
                await query.edit_message_text(text)
            await _safe_answer(query)
            return

        # ✅ زر الكلمات المحظورة (إدارة)
        if action == "banned":
            await CallbackHandlers._handle_banned_words_direct(update, context, query, user_id, chat_id, lang)
            return

        # ✅ زر قائمة عقوبات المخالفات
        if action == "violation_penalties":
            kb = []
            violation_names = {
                "links": "الروابط", "mentions": "المنشنات", "banned_words": "الكلمات المحظورة",
                "flood": "التكرار", "max_len": "الطول الزائد", "service": "رسائل الخدمة",
                "videos": "الفيديو", "audio": "الصوت", "documents": "المستندات",
                "stickers": "الملصقات", "forwarded": "المعاد توجيهه", "polls": "الاستطلاعات",
                "games": "الألعاب", "voice": "البصمات الصوتية", "video_note": "رسائل الفيديو",
            }
            for v_type, v_name in violation_names.items():
                rule = await DB.get_violation_penalty(chat_id, v_type)
                if rule:
                    p_type = rule['penalty_type']
                    dur = rule['duration_seconds'] // 60
                    status = f"{p_type} ({dur} دقيقة)" if dur > 0 else f"{p_type} (دائم)"
                else:
                    status = "غير محدد"
                kb.append([InlineKeyboardButton(f"{v_name}: {status}", callback_data=f"sec_violation:{chat_id}:{v_type}")])
            kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")])
            await query.edit_message_text("⚖️ **عقوبات المخالفات**", reply_markup=InlineKeyboardMarkup(kb))
            await _safe_answer(query)
            return

        # ✅ زر اختيار نوع المخالفة
        if action == "violation":
            if len(parts) >= 3:
                v_type = parts[2]
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔨 حظر", callback_data=f"sec_violation_pen:{chat_id}:{v_type}:ban"),
                     InlineKeyboardButton("🔇 كتم", callback_data=f"sec_violation_pen:{chat_id}:{v_type}:mute")],
                    [InlineKeyboardButton("🔒 تقييد", callback_data=f"sec_violation_pen:{chat_id}:{v_type}:restrict")],
                    [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_violation_penalties:{chat_id}")]
                ])
                await query.edit_message_text("اختر نوع العقوبة:", reply_markup=kb)
            return

        # ✅ زر اختيار نوع العقوبة
        if action == "violation_pen":
            if len(parts) >= 4:
                v_type = parts[2]
                p_type = parts[3]
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("دقيقة", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:60"),
                     InlineKeyboardButton("10 دقائق", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:600")],
                    [InlineKeyboardButton("نص ساعة", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:1800"),
                     InlineKeyboardButton("ساعة", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:3600")],
                    [InlineKeyboardButton("يوم", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:86400"),
                     InlineKeyboardButton("أسبوع", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:604800")],
                    [InlineKeyboardButton("شهر", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:2592000"),
                     InlineKeyboardButton("دائم", callback_data=f"sec_violation_dur:{chat_id}:{v_type}:{p_type}:0")],
                    [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_violation_penalties:{chat_id}")]
                ])
                await query.edit_message_text("⏱️ اختر مدة العقوبة:", reply_markup=kb)
            return

        # ✅ زر حفظ مدة العقوبة
        if action == "violation_dur":
            if len(parts) >= 5:
                v_type = parts[2]
                p_type = parts[3]
                try:
                    duration_seconds = int(parts[4])
                except:
                    return
                await DB.set_violation_penalty(chat_id, v_type, p_type, duration_seconds)
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_violation_penalties:{chat_id}")
                ]])
                await query.edit_message_text(f"✅ تم حفظ العقوبة", reply_markup=kb)
            return

        # ✅ إعدادات الفيضان
        if action == "antiflood_settings":
            await CallbackHandlers._handle_antiflood_settings(update, context, query, chat_id, user_id, lang)
            return

        # ✅ الوضع الليلي
        if action == "night_settings":
            await CallbackHandlers._handle_night_settings(update, context, query, chat_id, user_id, lang)
            return

        # ✅ مدد العقوبات
        if action == "penalty_durations":
            await CallbackHandlers._handle_penalty_durations(update, context, query, chat_id, user_id, lang)
            return

        # ✅ معالجة اختيار عقوبة الفيضان
        if action == "antiflood_penalty":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔇 كتم", callback_data=f"sec_set_antiflood_penalty:{chat_id}:mute"),
                 InlineKeyboardButton("🔨 حظر", callback_data=f"sec_set_antiflood_penalty:{chat_id}:ban")],
                [InlineKeyboardButton("🔒 تقييد", callback_data=f"sec_set_antiflood_penalty:{chat_id}:restrict")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_antiflood_settings:{chat_id}")]
            ])
            await query.edit_message_text("🌊 اختر عقوبة الفيضان:", reply_markup=kb)
            await _safe_answer(query)
            return

        # ✅ حفظ عقوبة الفيضان
        if action == "set_antiflood_penalty":
            if len(parts) >= 3:
                penalty = parts[2]
                if penalty in ("mute", "ban", "restrict"):
                    await DB.execute("UPDATE group_security SET antiflood_penalty=? WHERE chat_id=?", (penalty, chat_id))
                    await _safe_answer(query, "✅ تم الحفظ")
                    await CallbackHandlers._handle_antiflood_settings(update, context, query, chat_id, user_id, lang)
            return

        # ✅ معالجة اختيار إجراء الوضع الليلي
        if action == "night_action":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔇 كتم", callback_data=f"sec_set_night_action:{chat_id}:mute"),
                 InlineKeyboardButton("🔨 حظر", callback_data=f"sec_set_night_action:{chat_id}:ban")],
                [InlineKeyboardButton("🔒 تقييد", callback_data=f"sec_set_night_action:{chat_id}:restrict")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_night_settings:{chat_id}")]
            ])
            await query.edit_message_text("🌙 اختر إجراء الوضع الليلي:", reply_markup=kb)
            await _safe_answer(query)
            return

        # ✅ حفظ إجراء الوضع الليلي
        if action == "set_night_action":
            if len(parts) >= 3:
                penalty = parts[2]
                if penalty in ("mute", "ban", "restrict"):
                    await DB.execute("UPDATE group_security SET night_mode_action=? WHERE chat_id=?", (penalty, chat_id))
                    await _safe_answer(query, "✅ تم الحفظ")
                    await CallbackHandlers._handle_night_settings(update, context, query, chat_id, user_id, lang)
            return

        # ✅ معالجة مدد العقوبات (اختيار المدة)
        if action in ("penalty_mute", "penalty_ban", "penalty_restrict"):
            penalty_type = action.replace("penalty_", "")
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("دقيقة", callback_data=f"sec_penalty_duration:{chat_id}:{penalty_type}:60"),
                 InlineKeyboardButton("10 دقائق", callback_data=f"sec_penalty_duration:{chat_id}:{penalty_type}:600")],
                [InlineKeyboardButton("نصف ساعة", callback_data=f"sec_penalty_duration:{chat_id}:{penalty_type}:1800"),
                 InlineKeyboardButton("ساعة", callback_data=f"sec_penalty_duration:{chat_id}:{penalty_type}:3600")],
                [InlineKeyboardButton("6 ساعات", callback_data=f"sec_penalty_duration:{chat_id}:{penalty_type}:21600"),
                 InlineKeyboardButton("12 ساعة", callback_data=f"sec_penalty_duration:{chat_id}:{penalty_type}:43200")],
                [InlineKeyboardButton("يوم", callback_data=f"sec_penalty_duration:{chat_id}:{penalty_type}:86400"),
                 InlineKeyboardButton("أسبوع", callback_data=f"sec_penalty_duration:{chat_id}:{penalty_type}:604800")],
                [InlineKeyboardButton("دائم", callback_data=f"sec_penalty_duration:{chat_id}:{penalty_type}:0")],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_penalty_durations:{chat_id}")]
            ])
            await query.edit_message_text(f"⏳ اختر مدة العقوبة الافتراضية لـ {penalty_type}:", reply_markup=kb)
            await _safe_answer(query)
            return

        # ✅ حفظ مدة العقوبة الافتراضية
        if action == "penalty_duration":
            if len(parts) >= 4:
                penalty_type = parts[2]
                try:
                    duration = int(parts[3])
                except:
                    return
                if penalty_type == "mute":
                    await DB.execute("UPDATE group_security SET mute_default_duration=? WHERE chat_id=?", (duration, chat_id))
                elif penalty_type == "ban":
                    await DB.execute("UPDATE group_security SET ban_default_duration=? WHERE chat_id=?", (duration, chat_id))
                elif penalty_type == "restrict":
                    await DB.execute("UPDATE group_security SET restrict_default_duration=? WHERE chat_id=?", (duration, chat_id))
                await _safe_answer(query, "✅ تم الحفظ")
                await CallbackHandlers._handle_penalty_durations(update, context, query, chat_id, user_id, lang)
            return

        # ========== toggle_queries ==========
        toggle_queries = {
            "links": "UPDATE group_security SET delete_links = 1 - delete_links WHERE chat_id=?",
            "mentions": "UPDATE group_security SET mentions = 1 - mentions WHERE chat_id=?",
            "slow": "UPDATE group_security SET slow_mode = 1 - slow_mode WHERE chat_id=?",
            "video": "UPDATE group_security SET delete_videos = 1 - delete_videos WHERE chat_id=?",
            "audio": "UPDATE group_security SET delete_audio = 1 - delete_audio WHERE chat_id=?",
            "anim": "UPDATE group_security SET delete_animation = 1 - delete_animation WHERE chat_id=?",
            "service": "UPDATE group_security SET delete_service = 1 - delete_service WHERE chat_id=?",
            "doc": "UPDATE group_security SET delete_documents = 1 - delete_documents WHERE chat_id=?",
            "sticker": "UPDATE group_security SET delete_stickers = 1 - delete_stickers WHERE chat_id=?",
            "forward": "UPDATE group_security SET delete_forwarded = 1 - delete_forwarded WHERE chat_id=?",
            "poll": "UPDATE group_security SET delete_polls = 1 - delete_polls WHERE chat_id=?",
            "game": "UPDATE group_security SET delete_games = 1 - delete_games WHERE chat_id=?",
            "voice": "UPDATE group_security SET delete_voice = 1 - delete_voice WHERE chat_id=?",
            "videonote": "UPDATE group_security SET delete_video_note = 1 - delete_video_note WHERE chat_id=?",
            "welcome": "UPDATE group_security SET welcome_enabled = 1 - welcome_enabled WHERE chat_id=?",
            "goodbye": "UPDATE group_security SET goodbye_enabled = 1 - goodbye_enabled WHERE chat_id=?",
            "flood": "UPDATE group_security SET antiflood_enabled = 1 - antiflood_enabled WHERE chat_id=?",
            "night": "UPDATE group_security SET night_mode_enabled = 1 - night_mode_enabled WHERE chat_id=?",
            "banned_words": "UPDATE group_security SET delete_banned_words = 1 - delete_banned_words WHERE chat_id=?",
            "approve_join": "UPDATE group_security SET auto_approve_join = 1 - auto_approve_join WHERE chat_id=?",
            "reject_join": "UPDATE group_security SET auto_reject_join = 1 - auto_reject_join WHERE chat_id=?"
        }

        if action in toggle_queries:
            await DB.execute(toggle_queries[action], (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except BadRequest:
                pass
            await _safe_answer(query)
            return

        # ========== enable_all / disable_all ==========
        if action == "enable_all":
            await DB.execute("""
                UPDATE group_security SET 
                    delete_links=1, mentions=1, slow_mode=1,
                    delete_videos=1, delete_audio=1, delete_animation=1,
                    delete_service=1, delete_documents=1, delete_stickers=1,
                    delete_forwarded=1, delete_polls=1, delete_games=1,
                    delete_voice=1, delete_video_note=1,
                    welcome_enabled=1, goodbye_enabled=1,
                    antiflood_enabled=1, night_mode_enabled=1,
                    delete_banned_words=1, auto_approve_join=1, auto_reject_join=1
                WHERE chat_id=?
            """, (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except BadRequest:
                pass
            await _safe_answer(query)
            return

        if action == "disable_all":
            await DB.execute("""
                UPDATE group_security SET 
                    delete_links=0, mentions=0, slow_mode=0,
                    delete_videos=0, delete_audio=0, delete_animation=0,
                    delete_service=0, delete_documents=0, delete_stickers=0,
                    delete_forwarded=0, delete_polls=0, delete_games=0,
                    delete_voice=0, delete_video_note=0,
                    welcome_enabled=0, goodbye_enabled=0,
                    antiflood_enabled=0, night_mode_enabled=0,
                    delete_banned_words=0, auto_approve_join=0, auto_reject_join=0
                WHERE chat_id=?
            """, (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
            try:
                await query.edit_message_text(text, reply_markup=kb)
            except BadRequest:
                pass
            await _safe_answer(query)
            return

        # ========== إعدادات تحتاج إدخال ==========
        if action == "maxlen":
            StateManager.set(user_id, UserState.WAIT_MAX_LEN)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("📏 أرسل الحد الأقصى للطول:")
            await _safe_answer(query)
            return

        if action == "warn_count":
            StateManager.set(user_id, UserState.WAIT_WARN_COUNT)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("📝 أرسل العدد (1-10):")
            await _safe_answer(query)
            return

        if action == "welcome_text":
            StateManager.set(user_id, UserState.WAIT_WELCOME_TEXT)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("👋 أرسل نص الترحيب:")
            await _safe_answer(query)
            return

        if action == "goodbye_text":
            StateManager.set(user_id, UserState.WAIT_GOODBYE_TEXT)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("👋 أرسل نص الوداع:")
            await _safe_answer(query)
            return

        if action == "slow_mode_seconds":
            StateManager.set(user_id, UserState.WAIT_SLOW_MODE_SECONDS)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("⏱️ أرسل مدة الوضع البطيء بالثواني (0-3600):")
            await _safe_answer(query)
            return

        if action == "antiflood_messages":
            StateManager.set(user_id, UserState.WAIT_ANTIFLOOD_MESSAGES)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("📝 أرسل عدد الرسائل المسموح بها (1-100):")
            await _safe_answer(query)
            return

        if action == "antiflood_seconds":
            StateManager.set(user_id, UserState.WAIT_ANTIFLOOD_SECONDS)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("⏱️ أرسل الفترة الزمنية بالثواني (1-3600):")
            await _safe_answer(query)
            return

        if action == "night_start":
            StateManager.set(user_id, UserState.WAIT_NIGHT_START)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("🌙 أرسل وقت بدء الوضع الليلي (HH:MM):")
            await _safe_answer(query)
            return

        if action == "night_end":
            StateManager.set(user_id, UserState.WAIT_NIGHT_END)
            context.user_data['sec_chat'] = chat_id
            await query.edit_message_text("🌙 أرسل وقت نهاية الوضع الليلي (HH:MM):")
            await _safe_answer(query)
            return

        # ========== إغلاق ==========
        if action == "close":
            try:
                await query.message.delete()
            except BadRequest:
                pass
            await _safe_answer(query)
            return

        await _safe_answer(query)

    # =====================================================================
    # دوال مساعدة للإعدادات
    # =====================================================================

    @staticmethod
    async def _handle_antiflood_settings(update, context, query, chat_id, user_id, lang):
        settings = await DB.get_security_settings(chat_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"عدد الرسائل: {settings.get('antiflood_messages', 5)}", callback_data=f"sec_antiflood_messages:{chat_id}")],
            [InlineKeyboardButton(f"الفترة بالثواني: {settings.get('antiflood_seconds', 10)}", callback_data=f"sec_antiflood_seconds:{chat_id}")],
            [InlineKeyboardButton(f"العقوبة: {settings.get('antiflood_penalty', 'mute')}", callback_data=f"sec_antiflood_penalty:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")]
        ])
        await query.edit_message_text(f"🌊 **إعدادات الفيضان**", reply_markup=kb)
        await _safe_answer(query)

    @staticmethod
    async def _handle_night_settings(update, context, query, chat_id, user_id, lang):
        settings = await DB.get_security_settings(chat_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"وقت البداية: {settings.get('night_mode_start', '23:00')}", callback_data=f"sec_night_start:{chat_id}")],
            [InlineKeyboardButton(f"وقت النهاية: {settings.get('night_mode_end', '06:00')}", callback_data=f"sec_night_end:{chat_id}")],
            [InlineKeyboardButton(f"الإجراء: {settings.get('night_mode_action', 'mute')}", callback_data=f"sec_night_action:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")]
        ])
        await query.edit_message_text(f"🌙 **إعدادات الوضع الليلي**", reply_markup=kb)
        await _safe_answer(query)

    @staticmethod
    async def _handle_penalty_durations(update, context, query, chat_id, user_id, lang):
        settings = await DB.get_security_settings(chat_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"كتم: {settings.get('mute_default_duration', 3600)//60} دقيقة", callback_data=f"sec_penalty_mute:{chat_id}")],
            [InlineKeyboardButton(f"حظر: {settings.get('ban_default_duration', 0)//60} دقيقة", callback_data=f"sec_penalty_ban:{chat_id}")],
            [InlineKeyboardButton(f"تقييد: {settings.get('restrict_default_duration', 1800)//60} دقيقة", callback_data=f"sec_penalty_restrict:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")]
        ])
        await query.edit_message_text(f"⏳ **مدد العقوبات الافتراضية**", reply_markup=kb)
        await _safe_answer(query)

    @staticmethod
    async def _handle_banned_words_direct(update, context, query, user_id, chat_id=None, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        if chat_id is None:
            data = query.data
            parts = data.split(":")
            chat_id = int(parts[1]) if len(parts) > 1 else -1
        if chat_id != -1:
            if not await is_authorized_in_group(context.bot, chat_id, user_id):
                await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
                return
        else:
            if not CONFIG.is_developer(user_id):
                await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(KeyboardFactory.get_text("ban_add", lang), callback_data=f"ban_add:{chat_id}"),
             InlineKeyboardButton(KeyboardFactory.get_text("ban_list", lang), callback_data=f"ban_list:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("ban_rem", lang), callback_data=f"ban_rem:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}" if chat_id != -1 else CB.ADMIN)]
        ])
        await query.edit_message_text("🚫 **إدارة الكلمات المحظورة**", reply_markup=kb)
        await _safe_answer(query)

    # =====================================================================
    # لوحة الأدمن
    # =====================================================================

    @staticmethod
    async def _handle_admin(update, context, query, user_id, lang=None):
        if not CONFIG.is_developer(user_id):
            await _safe_answer(query, "❌ غير مصرح", show_alert=True)
            return
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        data = query.data

        if data == CB.ADMIN_USERS:
            stats = await DB.get_user_stats()
            await query.edit_message_text(f"👥 {stats['users']} مستخدم\n⛔ {stats['banned']} محظور")
        elif data == CB.ADMIN_BANNED:
            users = await DB.get_all_users()
            banned = [str(_mask_id(u[0])) for u in users if u[1] == 1]
            await query.edit_message_text("⛔ **المحظورين**\n\n" + "\n".join(banned[:20]) if banned else "لا يوجد")
        elif data == CB.ADMIN_UNBAN_ALL:
            await DB.execute("UPDATE users SET banned=0 WHERE banned=1")
            await query.edit_message_text("✅ تم إلغاء حظر الجميع")
        elif data == CB.ADMIN_CHANNELS:
            channels = await DB.fetchall("SELECT channel_id, channel_name, banned FROM user_channels LIMIT 50")
            text = "📡 **القنوات**\n\n" + "\n".join(f"{'✅' if not c['banned'] else '🚫'} {c['channel_name']}" for c in channels)
            await query.edit_message_text(text if channels else "📭 لا توجد")
        elif data == CB.ADMIN_BANNED_CH:
            channels = await DB.fetchall("SELECT channel_id, channel_name FROM user_channels WHERE banned=1")
            text = "🚫 **القنوات المحظورة**\n\n" + "\n".join(f"• {c['channel_name']}" for c in channels)
            await query.edit_message_text(text if channels else "📭 لا يوجد")
        elif data == CB.ADMIN_ACTIVATE_CH:
            await DB.execute("UPDATE user_channels SET banned=0 WHERE banned=1")
            await query.edit_message_text("✅ تم تفعيل الكل")
        elif data == CB.ADMIN_GROUPS:
            groups = await DB.fetchall("SELECT chat_id, chat_name, banned FROM bot_groups LIMIT 50")
            text = "👥 **المجموعات**\n\n" + "\n".join(f"{'✅' if not g['banned'] else '🚫'} {g['chat_name']}" for g in groups)
            await query.edit_message_text(text if groups else "📭 لا توجد")
        elif data == CB.ADMIN_BANNED_GR:
            groups = await DB.fetchall("SELECT chat_id, chat_name FROM bot_groups WHERE banned=1")
            text = "🚫 **المجموعات المحظورة**\n\n" + "\n".join(f"• {g['chat_name']}" for g in groups)
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
                text = f"⏳ **فترة تشغيل البوت**\n\n🕒 {int(days)} يوم, {int(hours)} ساعة, {int(mins)} دقيقة, {int(secs)} ثانية"
            except Exception as e:
                text = f"❌ تعذر حساب وقت التشغيل: {e}"
            await query.edit_message_text(text)
        elif data == CB.ADMIN_METRICS:
            m = METRICS.get_stats()
            await query.edit_message_text(f"📊 API: {m.get('api_calls_last_hour', 0)}\n⚠️ أخطاء: {m.get('errors_last_hour', 0)}")
        elif data == CB.ADMIN_BACKUP:
            try:
                PATHS.BACKUPS.mkdir(parents=True, exist_ok=True)
                old_backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
                for old_backup in old_backups[MAX_BACKUPS-1:]:
                    try:
                        old_backup.unlink()
                    except:
                        pass
                backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2(PATHS.DB, backup_file)
                with open(backup_file, 'rb') as f:
                    await context.bot.send_document(chat_id=user_id, document=f, filename=backup_file.name)
                await _safe_answer(query)
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
            if not filename.startswith("backup_") or not filename.endswith(".db"):
                await _safe_answer(query, "❌ ملف غير صالح", show_alert=True)
                return
            filepath = PATHS.BACKUPS / filename
            try:
                if not filepath.resolve().is_relative_to(PATHS.BACKUPS.resolve()):
                    await _safe_answer(query, "❌ مسار غير صالح", show_alert=True)
                    return
            except AttributeError:
                if not str(filepath.resolve()).startswith(str(PATHS.BACKUPS.resolve())):
                    await _safe_answer(query, "❌ مسار غير صالح", show_alert=True)
                    return
            if filepath.exists():
                try:
                    current_backup = PATHS.BACKUPS / f"pre_restore_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                    shutil.copy2(PATHS.DB, current_backup)
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
                text = "📋 **التذاكر**\n\n" + "\n".join(f"#{t['ticket_number']} - `{_mask_id(t['user_id'])}`" for t in tickets)
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
            text = "📋 **الردود**\n\n" + "\n".join(f"• {r['keyword']} ({r['usage_count']})" for r in replies)
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
                kb = [[InlineKeyboardButton(c['title'], callback_data=f"{CB.DECLARE_WINNER_SEL}:{c['id']}")] for c in contests]
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
            invoices = await DB.fetchall("SELECT number, user_id, plan_id, amount, status, created_at FROM invoices ORDER BY id DESC LIMIT 20")
            if not invoices:
                await query.edit_message_text("📭 لا توجد فواتير")
            else:
                text = "🧾 **آخر الفواتير**\n\n"
                for inv in invoices:
                    masked_uid = _mask_id(inv['user_id'])
                    text += f"• `{inv['number']}`\n  👤 المستخدم: `{masked_uid}`\n  💰 المبلغ: {inv['amount']} ⭐\n  📌 الحالة: {inv['status']}\n  🕒 {inv['created_at']}\n\n"
                await query.edit_message_text(text)
        elif data == CB.ADMIN_PAYMENT_LOGS:
            logs = await DB.fetchall("SELECT user_id, event_type, data, created_at FROM payment_logs ORDER BY id DESC LIMIT 20")
            if not logs:
                await query.edit_message_text("📭 لا توجد سجلات دفع")
            else:
                text = "📊 **سجلات الدفع**\n\n"
                for log in logs:
                    masked_uid = _mask_id(log['user_id'])
                    text += f"• 👤 `{masked_uid}`\n  🎯 الحدث: {log['event_type']}\n  🕒 {log['created_at']}\n\n"
                await query.edit_message_text(text)
        else:
            await _safe_answer(query, "⚠️ غير متوفر", show_alert=True)

    # =====================================================================
    # الردود التلقائية
    # =====================================================================

    @staticmethod
    async def _handle_auto_reply(update, context, query, user_id, lang=None):
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
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
            await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return
        settings = await DB.get_auto_reply_settings(chat_id)
        current_enabled = settings.get('enabled', False)
        if action == "toggle":
            await _safe_answer(query, "🔄 جارٍ التحديث...")
            new_enabled = not current_enabled
            await DB.update_auto_reply_settings(chat_id, enabled=new_enabled)
            _auto_reply_cache.invalidate()
            status_text = "✅ **تم تفعيل الردود التلقائية!**" if new_enabled else "❌ **تم تعطيل الردود التلقائية!**"
            await query.edit_message_text(status_text, reply_markup=KeyboardFactory.build("auto_reply_manage", chat_id=chat_id, lang=lang))
            return
        if action == "menu":
            await _safe_answer(query)
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return
        if action == "admins":
            await DB.update_auto_reply_settings(chat_id, only_admins=not settings.get('only_admins', False))
            await _safe_answer(query, "✅ تم")
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return
        if action == "reset":
            await DB.reset_auto_replies(chat_id)
            _auto_reply_cache.invalidate()
            await _safe_answer(query, "✅ تم حذف جميع الردود")
            await CallbackHandlers._show_auto_reply_menu(update, context, query, user_id, lang)
            return
        if action == "add":
            StateManager.set(user_id, UserState.WAIT_AUTO_KEY)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text("📝 أرسل الكلمة المفتاحية:")
            await _safe_answer(query)
            return
        if action == "del":
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = chat_id
            await query.edit_message_text("🗑️ أرسل الكلمة لحذفها:")
            await _safe_answer(query)
            return
        if action == "stats":
            rows = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? LIMIT 10", (chat_id,))
            text = "📊 **الإحصائيات**\n\n" + "\n".join(f"• {r['keyword']}: {r['usage_count']}" for r in rows) if rows else "📭 لا يوجد"
            await query.edit_message_text(text)
            await _safe_answer(query)
            return
        if action == "list":
            rows = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=? LIMIT 20", (chat_id,))
            text = "📋 **الردود**\n\n" + "\n".join(f"• {r['keyword']}" for r in rows) if rows else "📭 لا يوجد"
            await query.edit_message_text(text)
            await _safe_answer(query)
            return

    @staticmethod
    async def _show_auto_reply_menu(update, context, query, user_id, lang):
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
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
        only_admins = settings.get('only_admins', False)
        status_icon = "🟢" if current_enabled else "🔴"
        status_text = "مفعل" if current_enabled else "معطل"
        admins_text = "✅ المشرفون فقط" if only_admins else "👥 الجميع"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{status_icon} الحالة: {status_text}", callback_data="status_only")],
            [InlineKeyboardButton(f"🔄 {'إيقاف' if current_enabled else 'تشغيل'} الردود", callback_data=f"auto_reply_toggle:{chat_id}")],
            [InlineKeyboardButton(f"👤 المسموح: {admins_text}", callback_data=f"auto_reply_admins:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("auto_reply_add", lang), callback_data=f"auto_reply_add:{chat_id}"),
             InlineKeyboardButton(KeyboardFactory.get_text("auto_reply_del", lang), callback_data=f"auto_reply_del:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("auto_reply_list", lang), callback_data=f"auto_reply_list:{chat_id}"),
             InlineKeyboardButton(KeyboardFactory.get_text("auto_reply_stats", lang), callback_data=f"auto_reply_stats:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("auto_reply_reset", lang), callback_data=f"auto_reply_reset:{chat_id}")],
            [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=f"sec_close:{chat_id}")]
        ])
        try:
            await query.edit_message_text("📝 **إدارة الردود التلقائية**", reply_markup=kb)
        except BadRequest as e:
            if "message is not modified" not in str(e).lower():
                raise

    # =====================================================================
    # الجدولة
    # =====================================================================

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
        if not row or row['user_id'] != user_id:
            await _safe_answer(query, "❌ غير مصرح", show_alert=True)
            return
        StateManager.clear(user_id)
        if action == "min":
            StateManager.set(user_id, UserState.WAIT_MIN)
            context.user_data['schedule_ch'] = ch_id
            min_val = await get_min_publish_interval()
            await query.edit_message_text(f"📅 أرسل عدد الدقائق (الحد الأدنى {min_val} دقيقة، كحد أقصى 1440):")
            await _safe_answer(query)
        elif action == "hour":
            StateManager.set(user_id, UserState.WAIT_HOUR)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text("📅 أرسل عدد الساعات (1-168):")
            await _safe_answer(query)
        elif action == "day":
            StateManager.set(user_id, UserState.WAIT_DAY)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text("📅 أرسل عدد الأيام (1-365):")
            await _safe_answer(query)
        elif action == "time":
            StateManager.set(user_id, UserState.WAIT_PUB_TIME)
            context.user_data['schedule_ch'] = ch_id
            await query.edit_message_text("🕐 أرسل وقت النشر (HH:MM):")
            await _safe_answer(query)

    # =====================================================================
    # الكلمات المحظورة
    # =====================================================================

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
                await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                return
        else:
            try:
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    lang = await DB.get_user_language(user_id) or 'ar'
                    await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
                    return
            except Exception as e:
                await _safe_answer(query, "❌ تعذر التحقق من الصلاحية", show_alert=True)
                return
        if action == "add":
            StateManager.set(user_id, UserState.WAIT_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            text = "📝 أرسل الكلمة المحظورة:"
            try:
                await query.edit_message_text(text)
            except BadRequest:
                await safe_send(context.bot, user_id, text)
            await _safe_answer(query)
        elif action == "list":
            words = await DB.get_banned_words(chat_id)
            text = "📭 لا توجد كلمات محظورة" if not words else "🚫 **الكلمات المحظورة**\n\n" + "\n".join(f"• {w}" for w in words)
            try:
                await query.edit_message_text(text)
            except BadRequest:
                await safe_send(context.bot, user_id, text)
            await _safe_answer(query)
        elif action == "rem":
            StateManager.set(user_id, UserState.WAIT_REM_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            text = "🗑️ أرسل الكلمة لحذفها:"
            try:
                await query.edit_message_text(text)
            except BadRequest:
                await safe_send(context.bot, user_id, text)
            await _safe_answer(query)

    # =====================================================================
    # الإجراءات المتقدمة
    # =====================================================================

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
            lang = await DB.get_user_language(user_id) or 'ar'
            await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return
        perms = await check_bot_permissions(context.bot, chat_id)
        if not perms.get('can_act', False):
            lang = await DB.get_user_language(user_id) or 'ar'
            await _safe_answer(query, await get_text(lang, 'bot_no_perms'), show_alert=True)
            return
        actions = {
            "ban": (UserState.WAIT_BAN, "🚫 أرسل معرف المستخدم والمدة بالدقائق"),
            "mute": (UserState.WAIT_MUTE, "🔇 أرسل معرف المستخدم والمدة بالدقائق"),
            "warn": (UserState.WAIT_WARN, "⚠️ أرسل معرف المستخدم:"),
            "kick": (UserState.WAIT_KICK, "👢 أرسل معرف المستخدم:"),
            "restrict": (UserState.WAIT_RESTRICT, "🔒 أرسل معرف المستخدم والمدة بالدقائق"),
            "unban": (UserState.WAIT_UNBAN, "🔓 أرسل معرف المستخدم:"),
            "pin": (UserState.WAIT_PIN, "📌 أرسل معرف الرسالة أو رد عليها:"),
        }
        if action in actions:
            if action == "pin":
                if not perms.get('can_pin_messages', False):
                    await _safe_answer(query, "❌ البوت لا يملك صلاحية تثبيت الرسائل.", show_alert=True)
                    return
            state, text = actions[action]
            StateManager.set(user_id, state)
            context.user_data['adv_chat'] = chat_id
            await query.edit_message_text(text)
            await _safe_answer(query)

    # =====================================================================
    # العقوبات
    # =====================================================================

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
            lang = await DB.get_user_language(user_id) or 'ar'
            await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return
        if penalty not in DB.VALID_PENALTY_TYPES:
            await _safe_answer(query, "❌ نوع عقوبة غير صالح", show_alert=True)
            return
        await DB.execute("UPDATE group_security SET auto_penalty=? WHERE chat_id=?", (penalty, chat_id))
        await query.edit_message_text(f"✅ تم تعيين العقوبة: {penalty}")
        await _safe_answer(query)

    # =====================================================================
    # المسابقات
    # =====================================================================

    @staticmethod
    async def _handle_contests(update, context, query, user_id):
        data = query.data
        if data == CB.ADMIN_CREATE_CONTEST:
            if not CONFIG.is_developer(user_id):
                await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                return
            StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
            await query.edit_message_text("🏆 أرسل عنوان المسابقة:")
            await _safe_answer(query)
        elif data.startswith(CB.CONTEST_JOIN + ":"):
            cid = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
            context.user_data['contest_join'] = cid
            await query.edit_message_text("📝 أرسل إجابتك:")
            await _safe_answer(query)
        elif data == CB.CONTEST_WINNERS:
            winners = await DB.get_contest_winners(10)
            if not winners:
                await query.edit_message_text("📭 لا يوجد فائزون")
            else:
                text = "🏆 **الفائزون**\n\n" + "\n".join(f"• {w['title']} → `{_mask_id(w['winner_id'])}`" for w in winners)
                await query.edit_message_text(text)
            await _safe_answer(query)
        elif data.startswith(CB.DECLARE_WINNER_SEL + ":"):
            if not CONFIG.is_developer(user_id):
                await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                return
            cid = int(data.split(":")[-1])
            row = await DB.fetchone("SELECT status FROM contests WHERE id=?", (cid,))
            if not row or row['status'] != 'active':
                await _safe_answer(query, "❌ المسابقة غير نشطة", show_alert=True)
                return
            winner = await DB.fetchone("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,))
            if winner:
                success = await DB.declare_winner(cid, winner['user_id'])
                if success:
                    await query.edit_message_text(f"✅ الفائز: `{_mask_id(winner['user_id'])}`")
                    try:
                        await context.bot.send_message(winner['user_id'], f"🎉 مبروك! لقد فزت بالمسابقة!")
                    except Exception as e:
                        logger.warning(f"⚠️ فشل إشعار الفائز: {e}")
                else:
                    await _safe_answer(query, "❌ فشل إعلان الفائز", show_alert=True)
                    return
            await _safe_answer(query)

    # =====================================================================
    # الاستيراد
    # =====================================================================

    @staticmethod
    async def _handle_import(update, context, query, user_id):
        if not CONFIG.is_developer(user_id):
            await _safe_answer(query, "❌ غير مصرح", show_alert=True)
            return
        data = query.data
        if data == CB.ADMIN_IMPORT_REPLIES:
            StateManager.set(user_id, UserState.WAIT_IMPORT_FILE)
            context.user_data['import_chat_id'] = -1
            await query.edit_message_text("📤 أرسل ملف JSON للاستيراد:")
            await _safe_answer(query)
        elif data == CB.ADMIN_IMPORT_GITHUB:
            StateManager.set(user_id, UserState.WAIT_GITHUB_URL)
            await query.edit_message_text("📥 أرسل رابط GitHub (JSON):")
            await _safe_answer(query)
