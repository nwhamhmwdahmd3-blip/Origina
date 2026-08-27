#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_callback.py - معالجات الأزرار الكاملة (مصححة)
جميع الأزرار تعمل مع المحافظة على الكود الأصلي
- إصلاح استدعاء get_general_stats
- إصلاح حذف المنشورات (تمرير channel_db_id)
- إصلاح _handle_penalty لاستخدام القائمة الصحيحة
- إضافة معالجة الدفعات في _publish_all
- تحسين معالجة الأخطاء
"""

import asyncio
import logging
import json
import time
import re
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from collections import OrderedDict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
from telegram.error import (
    BadRequest, TimedOut, Forbidden, ChatMigrated, RetryAfter, NetworkError, TelegramError
)

from config import CONFIG, PATHS
from database import DB, TimeUtils
from utils import (
    safe_send, is_authorized_in_group, check_bot_permissions,
    get_text, StateManager, UserState,
    KeyboardFactory, TranslationManager, CB,
    get_ram_usage
)

logger = logging.getLogger(__name__)

# ============ ثوابت ============
MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096
MAX_BACKUPS = 10
PUBLISH_DELAY = 0.5
DEFAULT_PAGE_SIZE = 10
MAX_CONCURRENT_PUBLISH = 3

# ============ دوال مساعدة ============

async def _safe_answer(query, text=None, show_alert=False):
    """إجابة آمنة على الأزرار"""
    if not query:
        return False
    try:
        if text:
            await query.answer(text, show_alert=show_alert)
        else:
            await query.answer()
        return True
    except Exception as e:
        logger.debug(f"Query answer failed: {e}")
        return False


async def safe_edit(query, text, reply_markup=None, parse_mode=None):
    """تعديل آمن للرسائل"""
    if not query or not query.message:
        return False
    try:
        await query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except BadRequest as e:
        error_msg = str(e).lower()
        if "message is not modified" in error_msg:
            pass
        elif "message is too long" in error_msg:
            try:
                short_text = text[:4000] + "\n\n... (تم الاختصار)"
                await query.edit_message_text(
                    short_text, reply_markup=reply_markup, parse_mode=parse_mode)
            except:
                pass
        else:
            logger.debug(f"Edit failed: {e}")
    except Exception as e:
        logger.debug(f"Edit error: {e}")
    return False


async def safe_delete_message(query_or_message):
    """حذف آمن للرسائل"""
    try:
        if hasattr(query_or_message, 'message') and query_or_message.message:
            await query_or_message.message.delete()
        elif query_or_message:
            await query_or_message.delete()
    except Exception as e:
        logger.debug(f"Delete failed: {e}")


def escape_markdown(text: str) -> str:
    """تهريب النص للـ Markdown"""
    if not text:
        return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{c}' if c in escape_chars else c for c in text)


def _mask_id(id_value, prefix=3, suffix=2):
    """إخفاء جزء من المعرف"""
    if id_value is None:
        return "***"
    s = str(id_value)
    if len(s) <= 5:
        return "***"
    return s[:prefix] + "***" + s[-suffix:] if len(s) > prefix + suffix else s[:prefix] + "***"


async def _is_channel_owner(user_id: int, channel_db_id: int) -> bool:
    """التحقق من ملكية القناة"""
    return await DB.is_channel_owner(user_id, channel_db_id)


async def _delete_group(chat_id: int) -> bool:
    """حذف مجموعة"""
    return await DB.delete_group(chat_id)


async def _get_posts_page(user_id: int, channel_db_id: int, page: int, per_page: int) -> Tuple[List[Dict], int]:
    """جلب صفحة من المنشورات"""
    offset = page * per_page
    posts = await DB.fetchall(
        "SELECT id, text, published FROM posts WHERE channel_db_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?",
        (channel_db_id, per_page, offset)
    )
    total = await DB.fetchval(
        "SELECT COUNT(*) FROM posts WHERE channel_db_id = ?",
        (channel_db_id,),
        default=0
    )
    return posts, total


# ============ المعالج الرئيسي ============

class CallbackHandlers:
    """معالجات الأزرار الرئيسية"""

    @staticmethod
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """المعالج الرئيسي للأزرار"""
        query = update.callback_query
        data = query.data
        if not data:
            return

        user_id = query.from_user.id
        lang = await DB.get_user_language(user_id) or 'ar'

        start_time = time.monotonic()

        # استخراج البيانات الأساسية
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
                CB.REM_TOGGLE_WEEKLY, CB.REM_SET_DAYS, CB.ADMIN_LIST_ADMINS
            ]
            if parts[0] in known_constants:
                base_data = parts[0]

        logger.info(f"Callback data: {data} (base: {base_data})")

        try:
            # ========== الأزرار الأساسية ==========
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
                context.user_data.clear()
                context.args = []
                await CommandHandlers.start(update, context)
                return

            if base_data == CB.CANCEL:
                StateManager.clear(user_id)
                for key in list(context.user_data.keys()):
                    if key in ['security_chat_id', 'schedule_ch', 'auto_chat', 'ban_chat',
                               'adv_chat', 'import_chat_id', 'contest_join', 'admin_action']:
                        context.user_data.pop(key, None)
                await _safe_answer(query, "❌ تم الإلغاء")
                return

            if base_data == CB.HELP:
                await _safe_answer(query)
                await CommandHandlers.help_command(update, context)
                return

            if base_data == CB.TRIAL:
                await query.answer("🔄 جارٍ التفعيل...")
                if await DB.has_used_trial(user_id):
                    await safe_edit(query, await get_text(lang, 'trial_used'))
                    return
                days = await DB.activate_trial(user_id)
                if days > 0:
                    text = await get_text(lang, 'trial_activated', days=days)
                else:
                    text = "❌ تعذر تفعيل التجربة المجانية."
                await safe_edit(query, text)
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
                await safe_edit(query, f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}", reply_markup=kb)
                await _safe_answer(query)
                return

            if base_data == CB.TOGGLE_AUTO:
                await _safe_answer(query, "🔄 جارٍ التحديث...")
                cur = await DB.get_auto_publish_status(user_id)
                await DB.set_auto_publish(user_id, not cur)
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings", lang=lang)
                await safe_edit(query, f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}", reply_markup=kb)
                return

            if base_data == CB.TOGGLE_REC:
                await _safe_answer(query, "🔄 جارٍ التحديث...")
                cur = await DB.get_auto_recycle_status(user_id)
                await DB.set_auto_recycle(user_id, not cur)
                auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
                recycle = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings", lang=lang)
                await safe_edit(query, f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}", reply_markup=kb)
                return

            # ========== الباقات والاشتراكات ==========
            if base_data == CB.PLANS:
                kb = KeyboardFactory.build("plans", lang=lang)
                await safe_edit(query, await get_text(lang, 'plan_selector'), reply_markup=kb)
                await _safe_answer(query)
                return

            if base_data == "gift_plans":
                await _safe_answer(query)
                plans = await DB.get_gift_plans()
                if not plans:
                    await safe_edit(query, "📭 لا توجد خطط متاحة حالياً.")
                    return
                kb = []
                for plan in plans:
                    kb.append([InlineKeyboardButton(
                        f"🎁 {plan['days']} يوم - {plan['price']} ⭐",
                        callback_data=f"buy_gift:{plan['id']}"
                    )])
                kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
                await safe_edit(query, "💎 **شراء كود هدية**", reply_markup=InlineKeyboardMarkup(kb))
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
                    await safe_delete_message(query)
                except Exception as e:
                    logger.error(f"❌ فشل إرسال الفاتورة: {e}")
                    await DB.execute("UPDATE invoices SET status='cancelled' WHERE number=?", (invoice_number,))
                    await _safe_answer(query, f"❌ {str(e)[:50]}", show_alert=True)
                return

            if base_data == CB.INVOICES:
                invoices = await DB.get_user_invoices(user_id, 10)
                if not invoices:
                    await safe_edit(query, "📭 لا توجد فواتير")
                    await _safe_answer(query)
                    return
                text = "🧾 **فواتيري**\n\n"
                for inv in invoices:
                    text += f"• #{inv['number']} - {inv['amount']} ⭐\n"
                kb = [[InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]]
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                await _safe_answer(query)
                return

            # ========== نظام الإحالات ==========
            if base_data == CB.REFERRAL:
                await _safe_answer(query)
                try:
                    stats = await DB.get_referral_stats(user_id)
                    total_refs = stats.get('total', 0)
                    available_days = stats.get('available', 0)
                    code = await DB.get_referral_code(user_id)
                    if code and code.startswith('ref_'):
                        code = code[4:]
                    final_code = f"ref_{code}"
                    safe_link = escape_markdown(f"https://t.me/{CONFIG.BOT_USERNAME}?start={final_code}")
                    text = (
                        f"🔗 **نظام الإحالات**\n\n"
                        f"📎 **رابطك:**\n"
                        f"`{safe_link}`\n\n"
                        f"👥 المُحالين: {total_refs}\n"
                        f"🎁 الأيام المتاحة: {available_days} يوم"
                    )
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🎁 صرف", callback_data=CB.REF_CLAIM),
                         InlineKeyboardButton("📋 قائمة", callback_data=CB.REF_LIST)],
                        [InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]
                    ])
                    await safe_edit(query, text, reply_markup=kb, parse_mode="MarkdownV2")
                except Exception as e:
                    logger.error(f"❌ خطأ في الإحالات: {e}")
                    await safe_send(context.bot, user_id, "❌ حدث خطأ")
                return

            if base_data == CB.REF_CLAIM:
                await _safe_answer(query, "🔄 جارٍ الصرف...")
                try:
                    days = await DB.claim_referral_reward(user_id)
                    if days and days > 0:
                        text = f"✅ تم صرف {days} يوم!"
                    else:
                        text = "📭 لا توجد مكافآت"
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 رجوع", callback_data=CB.REFERRAL)],
                        [InlineKeyboardButton("🏠 الرئيسية", callback_data=CB.MAIN)]
                    ])
                    await safe_edit(query, text, reply_markup=kb)
                except Exception as e:
                    logger.error(f"❌ خطأ في صرف الإحالات: {e}")
                    await _safe_answer(query, "❌ حدث خطأ", show_alert=True)
                return

            if base_data == CB.REF_LIST:
                await _safe_answer(query)
                try:
                    referrals = await DB.get_referrals_list(user_id)
                    if referrals:
                        text = "📋 **المُحالين**\n\n"
                        for i, r in enumerate(referrals[:20], 1):
                            text += f"{i}. `{_mask_id(r)}`\n"
                    else:
                        text = "📭 لا يوجد"
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 رجوع", callback_data=CB.REFERRAL)],
                        [InlineKeyboardButton("🏠 الرئيسية", callback_data=CB.MAIN)]
                    ])
                    await safe_edit(query, text, reply_markup=kb, parse_mode="MarkdownV2")
                except Exception as e:
                    logger.error(f"❌ خطأ في قائمة الإحالات: {e}")
                    await _safe_answer(query, "❌ حدث خطأ", show_alert=True)
                return

            # ========== التذكيرات ==========
            if base_data in [CB.REM_TOGGLE_SUB, CB.REM_TOGGLE_DAILY, CB.REM_TOGGLE_WEEKLY]:
                await _safe_answer(query, "🔄 جارٍ التحديث...")
                try:
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
                    text += f"📈 أسبوعي: {'✅' if settings.get('weekly_report', False) else '❌'}"
                    kb = KeyboardFactory.build("reminder", lang=lang)
                    await safe_edit(query, text, reply_markup=kb)
                except Exception as e:
                    logger.error(f"تحديث التذكيرات فشل: {e}")
                    await _safe_answer(query, "❌ فشل التحديث", show_alert=True)
                return

            if base_data == CB.REMINDER:
                await _safe_answer(query)
                try:
                    settings = await DB.get_reminder_settings(user_id)
                    text = f"⏰ **التذكيرات**\n\n"
                    text += f"🔔 الاشتراك: {'✅' if settings.get('subscription_reminder', False) else '❌'}\n"
                    text += f"📊 يومي: {'✅' if settings.get('daily_stats_reminder', False) else '❌'}\n"
                    text += f"📈 أسبوعي: {'✅' if settings.get('weekly_report', False) else '❌'}"
                    kb = KeyboardFactory.build("reminder", lang=lang)
                    await safe_edit(query, text, reply_markup=kb)
                except Exception as e:
                    logger.error(f"عرض التذكيرات فشل: {e}")
                    await _safe_answer(query, "❌ حدث خطأ", show_alert=True)
                return

            if base_data == CB.REM_SET_DAYS:
                StateManager.set(user_id, UserState.WAIT_REM_DAYS)
                await safe_edit(query, "📅 أرسل عدد الأيام (1-30):")
                await _safe_answer(query)
                return

            # ========== الترجمة ==========
            if base_data == CB.TRANSLATION:
                await _safe_answer(query)
                kb = KeyboardFactory.build("translation", lang=lang)
                await safe_edit(query, "🌐 اختر اللغة:", reply_markup=kb)
                return

            if base_data == CB.TRANS_OFF:
                try:
                    await DB.set_user_language(user_id, 'off')
                    await safe_edit(query, "✅ تم إيقاف الترجمة")
                except Exception as e:
                    logger.error(f"إيقاف الترجمة فشل: {e}")
                    await _safe_answer(query, "❌ فشل", show_alert=True)
                await _safe_answer(query)
                return

            # ========== المسابقات ==========
            if base_data == CB.CONTESTS:
                await _safe_answer(query)
                await CommandHandlers.contests(update, context)
                return

            if base_data == CB.CONTEST_WINNERS:
                winners = await DB.get_contest_winners(10)
                if not winners:
                    await safe_edit(query, "📭 لا يوجد فائزون")
                    await _safe_answer(query)
                    return
                text = "🏆 **الفائزون**\n\n"
                for w in winners:
                    text += f"• {w['title']} → `{_mask_id(w['winner_id'])}`\n"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]]
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="MarkdownV2")
                await _safe_answer(query)
                return

            # ========== الدعم ==========
            if base_data == CB.SUPPORT_TICKET:
                StateManager.set(user_id, UserState.SUPPORT_MODE)
                await _safe_answer(query)
                await safe_send(context.bot, user_id, "📞 أرسل رسالتك:")
                return

            # ========== القنوات ==========
            if base_data == CB.CH_ADD:
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await _safe_answer(query, "❌ يتطلب اشتراك نشط", show_alert=True)
                    return
                StateManager.set(user_id, UserState.WAIT_CHANNEL)
                await safe_edit(query, "📡 أرسل معرف القناة:")
                await _safe_answer(query)
                return

            if base_data == CB.CH_LIST:
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.CH_SEL + ":"):
                try:
                    ch_id = int(data.split(":")[-1])
                except ValueError:
                    await _safe_answer(query, "❌ بيانات غير صالحة", show_alert=True)
                    return
                channel = await DB.get_channel_info(user_id, ch_id)
                if channel and channel.get('banned'):
                    await _safe_answer(query, "❌ القناة محظورة", show_alert=True)
                    return
                success = await DB.set_active_channel(user_id, ch_id)
                if success:
                    await safe_edit(query, "✅ تم تحديد القناة!")
                else:
                    await _safe_answer(query, "❌ لا يمكنك تحديد هذه القناة", show_alert=True)
                    return
                await _safe_answer(query)
                return

            if data.startswith(CB.CH_DEL + ":"):
                try:
                    ch_id = int(data.split(":")[-1])
                except ValueError:
                    await _safe_answer(query, "❌ بيانات غير صالحة", show_alert=True)
                    return
                success = await DB.delete_channel(user_id, ch_id)
                if success:
                    await _safe_answer(query, "✅ تم الحذف")
                else:
                    await _safe_answer(query, "❌ لا يمكنك حذف هذه القناة", show_alert=True)
                    return
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.CH_STATS + ":"):
                try:
                    ch_id = int(data.split(":")[-1])
                except ValueError:
                    await _safe_answer(query, "❌ بيانات غير صالحة", show_alert=True)
                    return
                stats = await DB.get_channel_stats(user_id, ch_id)
                text = f"📊 **إحصائيات**\n\n📝 {stats['total']}\n✅ {stats['published']}\n⏳ {stats['unpublished']}"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.CH_LIST)]]
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                await _safe_answer(query)
                return

            # ========== المنشورات ==========
            if base_data == CB.POST_ADD:
                await query.answer("⏳ جارٍ التحقق...")
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await _safe_answer(query, "❌ انتهى اشتراكك!", show_alert=True)
                    return
                active = await DB.get_active_channel(user_id)
                if not active:
                    await safe_edit(query, "❌ لا توجد قناة نشطة")
                    await _safe_answer(query)
                    return
                StateManager.set(user_id, UserState.ADDING_POSTS)
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ إنهاء", callback_data="finish_posts")]])
                await safe_edit(query, "📥 أرسل المنشورات:", reply_markup=kb)
                return

            if base_data == "finish_posts":
                StateManager.clear(user_id)
                await _safe_answer(query, "✅ تم الإنهاء")
                return

            if base_data == CB.POST_PUB:
                await query.answer("⏳ جارٍ النشر...")
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await _safe_answer(query, "❌ انتهى اشتراكك!", show_alert=True)
                    return
                active = await DB.get_active_channel(user_id)
                if not active:
                    await safe_edit(query, "❌ لا توجد قناة")
                    return
                post = await DB.get_next_post(active)
                if not post:
                    await safe_edit(query, "📭 لا توجد منشورات")
                    return
                ch_info = await DB.get_channel_info(user_id, active)
                if not ch_info:
                    return
                asyncio.create_task(
                    CallbackHandlers._publish_single(context.bot, active, ch_info['channel_id'], post)
                )
                await _safe_answer(query, "✅ بدأ النشر")
                return

            if base_data == CB.POST_LIST:
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if base_data == CB.POST_REC:
                active = await DB.get_active_channel(user_id)
                if active:
                    count = await DB.reset_posts(user_id, active)
                    await safe_edit(query, f"♻️ {count} منشور!")
                else:
                    await _safe_answer(query, "❌ لا توجد قناة نشطة", show_alert=True)
                await _safe_answer(query)
                return

            # معالجة حذف منشور (مصحح - مع تمرير channel_db_id)
            if data.startswith(CB.POST_DEL + ":"):
                try:
                    post_id = int(data.split(":")[-1])
                except ValueError:
                    await _safe_answer(query, "❌ بيانات غير صالحة", show_alert=True)
                    return
                active_channel = await DB.get_active_channel(user_id)
                if not active_channel:
                    await _safe_answer(query, "❌ لا توجد قناة نشطة", show_alert=True)
                    return
                success = await DB.delete_post(user_id, post_id, active_channel)
                if success:
                    await _safe_answer(query, "✅ تم الحذف")
                else:
                    await _safe_answer(query, "❌ فشل الحذف", show_alert=True)
                    return
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if base_data == CB.PUB_ALL:
                await query.answer("⏳ جاري النشر...")
                if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await _safe_answer(query, "❌ انتهى اشتراكك!", show_alert=True)
                    return
                channels = await DB.get_user_channels(user_id)
                if not channels:
                    await safe_edit(query, "❌ لا توجد قنوات")
                    return
                asyncio.create_task(CallbackHandlers._publish_all(context.bot, user_id, channels))
                await _safe_answer(query, "✅ بدأ النشر الجماعي")
                return

            # ========== المجموعات ==========
            if base_data == CB.GROUPS:
                await _safe_answer(query)
                groups = await DB.get_user_groups(user_id)
                if not groups:
                    add_text = "➕ أضف البوت لمجموعة"
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton(add_text, url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")]])
                    await safe_edit(query, "📭 لا توجد مجموعات", reply_markup=kb)
                    return
                text = "👥 **مجموعاتي**\n\n"
                kb = []
                for group in groups:
                    gid = group.get('chat_id')
                    name = group.get('chat_name', 'غير معروف')
                    banned = group.get('banned', 0)
                    st = "✅" if not banned else "⛔"
                    text += f"{st} {name}\n"
                    kb.append([InlineKeyboardButton(f"⚙️ أمان {name[:15]}", callback_data=f"{CB.GRP_SET}:{gid}")])
                    kb.append([InlineKeyboardButton("🗑️ حذف", callback_data=f"grp_del:{gid}")])
                kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)])
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data.startswith("grp_del:"):
                try:
                    chat_id = int(data.split(":")[-1])
                except ValueError:
                    await _safe_answer(query, "❌ بيانات غير صالحة", show_alert=True)
                    return
                success = await _delete_group(chat_id)
                if success:
                    await safe_edit(query, "✅ تم حذف المجموعة")
                else:
                    await _safe_answer(query, "❌ فشل الحذف", show_alert=True)
                return

            if data.startswith(CB.GRP_SET + ":"):
                try:
                    chat_id = int(data.split(":")[-1])
                except ValueError:
                    await _safe_answer(query, "❌ بيانات غير صالحة", show_alert=True)
                    return
                context.user_data['security_chat_id'] = chat_id
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    await _safe_answer(query, "❌ لا صلاحية", show_alert=True)
                    return
                settings = await DB.get_security_settings(chat_id)
                text = KeyboardFactory._format_security_text(settings)
                kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
                await safe_edit(query, text, reply_markup=kb)
                await _safe_answer(query)
                return

            # ========== لوحة الأدمن ==========
            if base_data == CB.ADMIN:
                if CONFIG.is_developer(user_id):
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("👥 المستخدمين", callback_data=CB.ADMIN_USERS),
                         InlineKeyboardButton("📊 الإحصائيات", callback_data=CB.ADMIN_STATS)],
                        [InlineKeyboardButton("⛔ المحظورين", callback_data=CB.ADMIN_BANNED),
                         InlineKeyboardButton("✅ فك الكل", callback_data=CB.ADMIN_UNBAN_ALL)],
                        [InlineKeyboardButton("📡 القنوات", callback_data=CB.ADMIN_CHANNELS),
                         InlineKeyboardButton("👥 المجموعات", callback_data=CB.ADMIN_GROUPS)],
                        [InlineKeyboardButton("🎁 منح", callback_data="admin_grant_free"),
                         InlineKeyboardButton("👑 مشرف", callback_data=CB.ADMIN_ADD_ADMIN)],
                        [InlineKeyboardButton("📨 بث", callback_data=CB.ADMIN_BROADCAST),
                         InlineKeyboardButton("🧾 فواتير", callback_data=CB.ADMIN_INVOICES)],
                        [InlineKeyboardButton("💾 نسخ", callback_data=CB.ADMIN_BACKUP),
                         InlineKeyboardButton("🔄 استعادة", callback_data=CB.ADMIN_RESTORE)],
                        [InlineKeyboardButton("🖥️ الرام", callback_data=CB.ADMIN_RAM),
                         InlineKeyboardButton("📊 المقاييس", callback_data=CB.ADMIN_METRICS)],
                        [InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]
                    ])
                    await safe_edit(query, "👑 **لوحة الأدمن**", reply_markup=kb)
                    await _safe_answer(query)
                else:
                    await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
                return

            # ========== توجيه المعالجات المتخصصة ==========
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
                try:
                    ch_id = int(data.split(":")[-1])
                except ValueError:
                    await _safe_answer(query, "❌ بيانات غير صالحة", show_alert=True)
                    return
                kb = KeyboardFactory.build("channel_settings", chat_id=ch_id, lang=lang)
                await safe_edit(query, "📅 **جدولة القناة**", reply_markup=kb)
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
                if lang_set in ['ar', 'en', 'off']:
                    try:
                        await DB.set_user_language(user_id, lang_set)
                        await _safe_answer(query, f"✅ {lang_set}")
                        context.args = []
                        await CommandHandlers.start(update, context)
                    except Exception as e:
                        logger.error(f"تغيير اللغة فشل: {e}")
                        await _safe_answer(query, "❌ فشل", show_alert=True)
                else:
                    await _safe_answer(query, "❌ لغة غير مدعومة", show_alert=True)
                return

            # التعامل مع أزرار ترقيم الصفحات
            if data == "ch_page_prev":
                context.user_data['channel_page'] = max(0, context.user_data.get('channel_page', 0) - 1)
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return
            if data == "ch_page_next":
                context.user_data['channel_page'] = context.user_data.get('channel_page', 0) + 1
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return
            if data == "post_page_prev":
                context.user_data['post_page'] = max(0, context.user_data.get('post_page', 0) - 1)
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return
            if data == "post_page_next":
                context.user_data['post_page'] = context.user_data.get('post_page', 0) + 1
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            # معالجة أزرار الردود التلقائية
            if data.startswith("auto_reply_menu:"):
                try:
                    chat_id = int(data.split(":")[-1])
                except ValueError:
                    await _safe_answer(query, "❌ بيانات غير صالحة", show_alert=True)
                    return
                settings = await DB.get_auto_reply_settings(chat_id)
                kb = KeyboardFactory.build("auto_reply", chat_id=chat_id, lang=lang)
                await safe_edit(query, "🤖 **إعدادات الردود التلقائية**", reply_markup=kb)
                await _safe_answer(query)
                return

            # معالجة أزرار set_duration
            if data.startswith("set_duration:"):
                parts_data = data.split(":")
                if len(parts_data) >= 3:
                    try:
                        chat_id = int(parts_data[1])
                        duration = int(parts_data[2])
                    except ValueError:
                        await _safe_answer(query, "❌ بيانات غير صالحة", show_alert=True)
                        return
                    penalty_type = context.user_data.get('penalty_type', 'mute')
                    if penalty_type == 'mute':
                        col = 'mute_default_duration'
                    elif penalty_type == 'ban':
                        col = 'ban_default_duration'
                    elif penalty_type == 'restrict':
                        col = 'restrict_default_duration'
                    else:
                        await _safe_answer(query, "❌ نوع غير معروف", show_alert=True)
                        return
                    await DB.update_security_settings(chat_id, **{col: duration})
                    await _safe_answer(query, f"✅ تم تعيين المدة: {duration} ثانية")
                    await CallbackHandlers._handle_security(update, context, query, user_id, lang, return_to_main=True)
                    return

            # معالجة أزرار اختيار نوع العقوبة
            if data.startswith("sec_penalty_") and ":" in data:
                try:
                    penalty_type = data.split("_")[-1].split(":")[0]
                    chat_id = int(data.split(":")[-1])
                except:
                    await _safe_answer(query, "❌ بيانات غير صالحة", show_alert=True)
                    return
                if penalty_type in ['mute', 'ban', 'restrict', 'kick', 'warn']:
                    context.user_data['penalty_type'] = penalty_type
                    await CallbackHandlers._show_penalty_durations(update, context, query, chat_id, lang, penalty_type)
                    return

            await _safe_answer(query, "⚠️ غير متوفر", show_alert=True)

        except BadRequest as e:
            if "query is too old" in str(e).lower():
                logger.debug("Query is too old in main handler")
            else:
                logger.error(f"❌ BadRequest in callback: {e}", exc_info=True)
                try:
                    await query.answer("❌ خطأ", show_alert=True)
                except:
                    pass
        except Exception as e:
            logger.error(f"❌ Callback error: {e}", exc_info=True)
            try:
                await query.answer("❌ خطأ", show_alert=True)
            except:
                pass
        finally:
            elapsed = time.monotonic() - start_time
            if elapsed > 1.0:
                logger.warning(f"🐢 زر بطيء {data}: {elapsed:.2f}s")

    # ============ دوال النشر ============

    @staticmethod
    async def _publish_single(bot, ch_db_id, ch_tele, post):
        """نشر منشور واحد مع معالجة الأخطاء"""
        try:
            if not post:
                logger.warning("منشور فارغ")
                return
            post_id = post.get('id')
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
                    if text and len(text) > MAX_MESSAGE_LENGTH:
                        for i in range(0, len(text), MAX_MESSAGE_LENGTH):
                            await bot.send_message(chat_id=ch_tele, text=text[i:i+MAX_MESSAGE_LENGTH])
                    else:
                        await bot.send_message(chat_id=ch_tele, text=text if text else ".")
            except RetryAfter as e:
                wait = e.retry_after
                logger.warning(f"RetryAfter: sleeping {wait}s")
                await asyncio.sleep(wait)
                raise
            except (ChatMigrated, Forbidden) as e:
                logger.error(f"ChatMigrated/Forbidden: {e}")
                raise
            except NetworkError as e:
                logger.error(f"NetworkError: {e}")
                raise
            except Exception as e:
                logger.error(f"Error sending: {e}")
                raise

            try:
                if post_id:
                    await DB.mark_post_published(post_id)
                await DB.update_last_publish(ch_db_id)
                await DB.update_next_publish(ch_db_id)
            except Exception as db_err:
                logger.error(f"فشل تحديث قاعدة البيانات بعد النشر: {db_err}")

        except Exception as e:
            logger.error(f"❌ فشل النشر النهائي: {e}")
            if post and post.get('id'):
                await DB.increment_post_fail(post.get('id', -1))

    @staticmethod
    async def _publish_all(bot, user_id, channels):
        """نشر جميع القنوات مع حد أقصى للتوازي ومعالجة بالدفعات"""
        published_count = 0
        failed_count = 0
        await safe_send(bot, user_id, "⏳ جاري النشر...")

        tasks = []
        for ch in channels:
            if ch.get('banned'):
                continue
            post = await DB.get_next_post(ch['id'])
            if post:
                ch_info = await DB.get_channel_info(user_id, ch['id'])
                if ch_info:
                    tasks.append((ch['id'], ch_info['channel_id'], post))

        if not tasks:
            await safe_send(bot, user_id, "📭 لا توجد منشورات للنشر")
            return

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PUBLISH)

        async def _run_task(task):
            async with semaphore:
                ch_db_id, ch_tele, post = task
                try:
                    await CallbackHandlers._publish_single(bot, ch_db_id, ch_tele, post)
                    return True
                except Exception:
                    return False

        # معالجة بالدفعات لتجنب استهلاك الذاكرة
        BATCH_SIZE = 10
        for i in range(0, len(tasks), BATCH_SIZE):
            batch = tasks[i:i+BATCH_SIZE]
            results = await asyncio.gather(*(_run_task(t) for t in batch))
            published_count += sum(1 for r in results if r)
            failed_count += sum(1 for r in results if not r)

        await safe_send(bot, user_id, f"✅ تم نشر {published_count} | ❌ فشل {failed_count}")

    # ============ دوال عرض القوائم ============

    @staticmethod
    async def _show_channel_list(update, context, query, user_id, lang=None):
        """عرض قائمة القنوات مع ترقيم الصفحات"""
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        channels = await DB.get_user_channels(user_id)
        if not channels:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]
            ])
            await safe_edit(query, "📭 لا توجد قنوات!", reply_markup=kb)
            await _safe_answer(query)
            return

        page = int(context.user_data.get('channel_page', 0))
        per_page = 5
        total_pages = max(1, (len(channels) + per_page - 1) // per_page)
        start = page * per_page
        end = start + per_page
        page_channels = channels[start:end]

        text = f"📡 **قنواتي** (صفحة {page+1}/{total_pages})\n\n"
        kb = []
        for ch in page_channels:
            st = "✅" if not ch['banned'] else "🚫"
            text += f"{st} {ch['channel_name']}\n"
            kb.append([
                InlineKeyboardButton(f"📌 {ch['channel_name'][:20]}", callback_data=f"{CB.CH_SEL}:{ch['id']}"),
                InlineKeyboardButton("📅", callback_data=f"sched_open:{ch['id']}")
            ])
            kb.append([
                InlineKeyboardButton("📊", callback_data=f"{CB.CH_STATS}:{ch['id']}"),
                InlineKeyboardButton("🗑️", callback_data=f"{CB.CH_DEL}:{ch['id']}")
            ])
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data="ch_page_prev"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data="ch_page_next"))
        if nav_buttons:
            kb.append(nav_buttons)
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
        await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
        await _safe_answer(query)

    @staticmethod
    async def _show_post_list(update, context, query, user_id, lang=None):
        """عرض قائمة المنشورات مع ترقيم الصفحات"""
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        active = await DB.get_active_channel(user_id)
        if not active:
            await safe_edit(query, "❌ لا توجد قناة نشطة")
            await _safe_answer(query)
            return

        page = int(context.user_data.get('post_page', 0))
        per_page = 5
        posts, total_posts = await _get_posts_page(user_id, active, page, per_page)
        total_pages = max(1, (total_posts + per_page - 1) // per_page)

        text = f"📋 **منشوراتي** (صفحة {page+1}/{total_pages})\n\n"
        kb = []
        for p in posts:
            text += f"🆔 {p['id']}: {(p['text'] or '')[:30]}\n"
            kb.append([InlineKeyboardButton(f"🗑️ حذف {p['id']}", callback_data=f"{CB.POST_DEL}:{p['id']}")])
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ السابق", callback_data="post_page_prev"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("التالي ➡️", callback_data="post_page_next"))
        if nav:
            kb.append(nav)
        kb.append([InlineKeyboardButton("🔄 إعادة تدوير", callback_data=CB.POST_REC)])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
        await safe_edit(query, text if posts else "📭 لا يوجد", reply_markup=InlineKeyboardMarkup(kb))
        await _safe_answer(query)

    # ============ معالجات الأمان ============

    @staticmethod
    async def _handle_security(update, context, query, user_id, lang=None, return_to_main=False):
        """معالجة أزرار الأمان"""
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

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return

        toggle_queries = {
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
            "reject_join": "auto_reject_join",
            "nsfw": "nsfw_enabled",
            "warn_enabled": "warn_enabled",
        }

        try:
            if action in toggle_queries:
                column = toggle_queries[action]
                settings = await DB.get_security_settings(chat_id)
                current = settings.get(column, 0)
                await DB.update_security_settings(chat_id, **{column: 1 - current})
            elif action == "enable_all":
                await DB.update_security_settings(chat_id,
                    delete_links=1, mentions=1, slow_mode=1,
                    delete_videos=1, delete_audio=1, delete_animation=1,
                    delete_service=1, delete_documents=1, delete_stickers=1,
                    delete_forwarded=1, delete_polls=1, delete_games=1,
                    delete_voice=1, delete_video_note=1,
                    welcome_enabled=1, goodbye_enabled=1,
                    antiflood_enabled=1, night_mode_enabled=1,
                    delete_banned_words=1, auto_approve_join=1, auto_reject_join=0,
                    nsfw_enabled=1, warn_enabled=1
                )
            elif action == "disable_all":
                await DB.update_security_settings(chat_id,
                    delete_links=0, mentions=0, slow_mode=0,
                    delete_videos=0, delete_audio=0, delete_animation=0,
                    delete_service=0, delete_documents=0, delete_stickers=0,
                    delete_forwarded=0, delete_polls=0, delete_games=0,
                    delete_voice=0, delete_video_note=0,
                    welcome_enabled=0, goodbye_enabled=0,
                    antiflood_enabled=0, night_mode_enabled=0,
                    delete_banned_words=0, auto_approve_join=0, auto_reject_join=0,
                    nsfw_enabled=0, warn_enabled=0
                )
            elif action == "close":
                await safe_delete_message(query)
                await _safe_answer(query)
                return
            elif action == "penalty_durations":
                await CallbackHandlers._show_penalty_durations(update, context, query, chat_id, lang)
                return
            elif action == "violation_penalties":
                await CallbackHandlers._show_violation_penalties(update, context, query, chat_id, lang)
                return
            elif action == "antiflood_settings":
                await CallbackHandlers._show_antiflood_settings(update, context, query, chat_id, lang)
                return
            elif action == "night_settings":
                await CallbackHandlers._show_night_settings(update, context, query, chat_id, lang)
                return
            elif action == "auto_reply_menu":
                await CallbackHandlers._show_auto_reply_menu(update, context, query, chat_id, lang)
                return
            elif action == "adv_act":
                await CallbackHandlers._show_advanced_actions(update, context, query, chat_id, lang)
                return
            elif action == "act_log":
                await CallbackHandlers._show_admin_logs(update, context, query, chat_id, lang)
                return
            elif action == "maxlen":
                StateManager.set(user_id, UserState.WAIT_MAX_LEN)
                context.user_data['sec_chat'] = chat_id
                await safe_edit(query, "📏 أرسل الحد الأقصى لطول الرسالة:")
                await _safe_answer(query)
                return
            elif action == "del_pen":
                StateManager.set(user_id, UserState.WAIT_PENALTY_DURATION)
                context.user_data['adv_chat'] = chat_id
                await safe_edit(query, "⏱️ أرسل مدة العقوبة بالثواني:")
                await _safe_answer(query)
                return
            elif action == "penalty":
                await CallbackHandlers._show_penalty_types(update, context, query, chat_id, lang)
                return
            elif action == "set_violation_strikes":
                StateManager.set(user_id, UserState.WAIT_WARN_COUNT)
                context.user_data['sec_chat'] = chat_id
                await safe_edit(query, "📊 أرسل عدد المخالفات قبل العقوبة:")
                await _safe_answer(query)
                return
            elif action == "set_violation_duration":
                StateManager.set(user_id, UserState.WAIT_PENALTY_DURATION)
                context.user_data['adv_chat'] = chat_id
                await safe_edit(query, "⏱️ أرسل مدة العقوبة بالثواني:")
                await _safe_answer(query)
                return
            elif action == "set_antiflood_messages":
                StateManager.set(user_id, UserState.WAIT_ANTIFLOOD_MESSAGES)
                context.user_data['sec_chat'] = chat_id
                await safe_edit(query, "📊 أرسل عدد الرسائل المسموحة:")
                await _safe_answer(query)
                return
            elif action == "set_antiflood_seconds":
                StateManager.set(user_id, UserState.WAIT_ANTIFLOOD_SECONDS)
                context.user_data['sec_chat'] = chat_id
                await safe_edit(query, "⏱️ أرسل المدة بالثواني:")
                await _safe_answer(query)
                return
            elif action == "set_night_start":
                StateManager.set(user_id, UserState.WAIT_NIGHT_START)
                context.user_data['sec_chat'] = chat_id
                await safe_edit(query, "🌙 أرسل وقت البدء (HH:MM):")
                await _safe_answer(query)
                return
            elif action == "set_night_end":
                StateManager.set(user_id, UserState.WAIT_NIGHT_END)
                context.user_data['sec_chat'] = chat_id
                await safe_edit(query, "🌙 أرسل وقت النهاية (HH:MM):")
                await _safe_answer(query)
                return
            else:
                await _safe_answer(query, "⚠️ غير معروف", show_alert=True)
                return

            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)

            try:
                await query.edit_message_text(text, reply_markup=kb, parse_mode=None)
            except BadRequest as e:
                error_msg = str(e).lower()
                if "message is not modified" in error_msg:
                    pass
                elif "message is too long" in error_msg:
                    short_text = text[:4000] + "\n\n... (تم الاختصار)"
                    await query.edit_message_text(short_text, reply_markup=kb, parse_mode=None)
                else:
                    await query.message.reply_text(text, reply_markup=kb)
            except Exception:
                await query.message.reply_text(text, reply_markup=kb)

            await _safe_answer(query)
        except BadRequest as e:
            if "query is too old" in str(e).lower():
                logger.debug("Query too old in security")
            else:
                logger.error(f"خطأ في إعدادات الأمان: {e}", exc_info=True)
                await _safe_answer(query, "❌ حدث خطأ", show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في إعدادات الأمان: {e}", exc_info=True)
            await _safe_answer(query, "❌ حدث خطأ", show_alert=True)

    # ============ دوال عرض القوائم الفرعية للأمان ============

    @staticmethod
    async def _show_penalty_durations(update, context, query, chat_id, lang, penalty_type='mute'):
        """عرض مدد العقوبات"""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("30 ثانية", callback_data=f"set_duration:{chat_id}:30"),
             InlineKeyboardButton("دقيقة", callback_data=f"set_duration:{chat_id}:60")],
            [InlineKeyboardButton("5 دقائق", callback_data=f"set_duration:{chat_id}:300"),
             InlineKeyboardButton("ساعة", callback_data=f"set_duration:{chat_id}:3600")],
            [InlineKeyboardButton("يوم", callback_data=f"set_duration:{chat_id}:86400"),
             InlineKeyboardButton("أسبوع", callback_data=f"set_duration:{chat_id}:604800")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"grp_set:{chat_id}")]
        ])
        type_name = {'mute': 'كتم', 'ban': 'حظر', 'restrict': 'تقييد', 'kick': 'طرد', 'warn': 'تحذير'}.get(penalty_type, penalty_type)
        await safe_edit(query, f"⏱️ اختر مدة {type_name}:", reply_markup=kb)
        await _safe_answer(query)

    @staticmethod
    async def _show_violation_penalties(update, context, query, chat_id, lang):
        """عرض عقوبات المخالفات"""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("عدد الضربات", callback_data=f"sec_set_violation_strikes:{chat_id}"),
             InlineKeyboardButton("المدة", callback_data=f"sec_set_violation_duration:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"grp_set:{chat_id}")]
        ])
        await safe_edit(query, "🚨 إعدادات المخالفات:", reply_markup=kb)
        await _safe_answer(query)

    @staticmethod
    async def _show_antiflood_settings(update, context, query, chat_id, lang):
        """عرض إعدادات الفيضان"""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("عدد الرسائل", callback_data=f"sec_set_antiflood_messages:{chat_id}"),
             InlineKeyboardButton("الثواني", callback_data=f"sec_set_antiflood_seconds:{chat_id}")],
            [InlineKeyboardButton("نوع العقوبة", callback_data=f"sec_set_antiflood_penalty:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"grp_set:{chat_id}")]
        ])
        await safe_edit(query, "🌊 إعدادات الفيضان:", reply_markup=kb)
        await _safe_answer(query)

    @staticmethod
    async def _show_night_settings(update, context, query, chat_id, lang):
        """عرض إعدادات الوضع الليلي"""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("وقت البدء", callback_data=f"sec_set_night_start:{chat_id}"),
             InlineKeyboardButton("وقت النهاية", callback_data=f"sec_set_night_end:{chat_id}")],
            [InlineKeyboardButton("الإجراء", callback_data=f"sec_set_night_action:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"grp_set:{chat_id}")]
        ])
        await safe_edit(query, "🌙 إعدادات الوضع الليلي:", reply_markup=kb)
        await _safe_answer(query)

    @staticmethod
    async def _show_auto_reply_menu(update, context, query, chat_id, lang):
        """عرض قائمة الردود التلقائية"""
        kb = KeyboardFactory.build("auto_reply", chat_id=chat_id, lang=lang)
        await safe_edit(query, "🤖 إعدادات الردود التلقائية:", reply_markup=kb)
        await _safe_answer(query)

    @staticmethod
    async def _show_advanced_actions(update, context, query, chat_id, lang):
        """عرض الإجراءات المتقدمة"""
        kb = KeyboardFactory.build("advanced_actions", chat_id=chat_id, lang=lang)
        await safe_edit(query, "🛠️ الإجراءات المتقدمة:", reply_markup=kb)
        await _safe_answer(query)

    @staticmethod
    async def _show_admin_logs(update, context, query, chat_id, lang):
        """عرض سجلات المشرفين"""
        logs = await DB.get_admin_logs(chat_id, 10)
        if logs:
            text = "📋 **سجل المشرفين**\n\n"
            for log in logs:
                text += f"• {log['admin_id']} → {log['action']} on {log['target_id']}\n"
        else:
            text = "📭 لا يوجد سجلات"
        kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=f"grp_set:{chat_id}")]]
        await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
        await _safe_answer(query)

    @staticmethod
    async def _show_penalty_types(update, context, query, chat_id, lang):
        """عرض أنواع العقوبات"""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("حظر", callback_data=f"sec_penalty_ban:{chat_id}"),
             InlineKeyboardButton("كتم", callback_data=f"sec_penalty_mute:{chat_id}")],
            [InlineKeyboardButton("طرد", callback_data=f"sec_penalty_kick:{chat_id}"),
             InlineKeyboardButton("تحذير", callback_data=f"sec_penalty_warn:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"grp_set:{chat_id}")]
        ])
        await safe_edit(query, "🚫 اختر نوع العقوبة:", reply_markup=kb)
        await _safe_answer(query)

    # ============ معالجات الأدمن ============

    @staticmethod
    async def _handle_admin(update, context, query, user_id, lang=None):
        """معالجة أزرار لوحة الأدمن"""
        if not CONFIG.is_developer(user_id):
            await _safe_answer(query, "❌ غير مصرح", show_alert=True)
            return
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        data = query.data

        try:
            if data == "admin_grant_free":
                StateManager.set(user_id, UserState.WAIT_GRANT_FREE)
                context.user_data['admin_action'] = 'grant_free'
                await safe_edit(query, "🎁 أرسل: معرف_المستخدم عدد_الأيام")
                await _safe_answer(query)
                return
            elif data == CB.ADMIN_USERS:
                stats = await DB.get_user_stats()
                await safe_edit(query, f"👥 {stats['users']} مستخدم\n⛔ {stats['banned']} محظور")
                await _safe_answer(query)
            elif data == CB.ADMIN_STATS:
                stats = await DB.get_general_stats()
                text = (f"📊 **إحصائيات عامة**\n\n"
                        f"👥 المستخدمون: {stats['users']}\n"
                        f"📡 القنوات: {stats['channels']}\n"
                        f"👥 المجموعات: {stats['groups']}\n"
                        f"📝 المنشورات: {stats['posts']}\n"
                        f"🧾 الفواتير: {stats['invoices']}")
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.ADMIN)]]
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                await _safe_answer(query)
            elif data == CB.ADMIN_BANNED:
                banned_users = await DB.fetchall("SELECT user_id FROM users WHERE banned=1 LIMIT 20")
                if banned_users:
                    text = "⛔ **المحظورين**\n\n" + "\n".join(str(u['user_id']) for u in banned_users)
                else:
                    text = "لا يوجد محظورون"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.ADMIN)]]
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                await _safe_answer(query)
            elif data == CB.ADMIN_UNBAN_ALL:
                await DB.execute("UPDATE users SET banned=0 WHERE banned=1")
                await safe_edit(query, "✅ تم إلغاء حظر الجميع")
                await _safe_answer(query)
            elif data == CB.ADMIN_CHANNELS:
                channels = await DB.fetchall("SELECT channel_id, channel_name, banned FROM user_channels LIMIT 50")
                if channels:
                    text = "📡 **القنوات**\n\n" + "\n".join(f"{'✅' if not c['banned'] else '🚫'} {c['channel_name']}" for c in channels)
                else:
                    text = "📭 لا توجد"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.ADMIN)]]
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                await _safe_answer(query)
            elif data == CB.ADMIN_GROUPS:
                groups = await DB.fetchall("SELECT chat_id, chat_name, banned FROM bot_groups LIMIT 20")
                if groups:
                    text = "👥 **المجموعات**\n\n" + "\n".join(f"{'✅' if not g['banned'] else '🚫'} {g['chat_name']}" for g in groups)
                else:
                    text = "📭 لا توجد"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.ADMIN)]]
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                await _safe_answer(query)
            elif data == CB.ADMIN_ADD_ADMIN:
                StateManager.set(user_id, UserState.WAIT_ADMIN_ADD)
                await safe_edit(query, "👑 أرسل معرف المشرف:")
                await _safe_answer(query)
            elif data == CB.ADMIN_BROADCAST:
                StateManager.set(user_id, UserState.WAIT_BROADCAST)
                await safe_edit(query, "📨 أرسل الرسالة:")
                await _safe_answer(query)
            elif data == CB.ADMIN_INVOICES:
                invoices = await DB.fetchall("SELECT number, amount, status FROM invoices ORDER BY id DESC LIMIT 20")
                if invoices:
                    text = "🧾 **الفواتير**\n\n" + "\n".join(f"• {inv['number']} - {inv['amount']} ⭐ - {inv['status']}" for inv in invoices)
                else:
                    text = "📭 لا توجد"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.ADMIN)]]
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                await _safe_answer(query)
            elif data == CB.ADMIN_BACKUP:
                await query.answer("⏳ جارٍ النسخ...")
                async def backup_bg():
                    try:
                        PATHS.BACKUPS.mkdir(parents=True, exist_ok=True)
                        timestamp = TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')
                        backup_file = PATHS.BACKUPS / f"backup_{timestamp}.db"
                        shutil.copy2(PATHS.DB, backup_file)
                        backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
                        for old in backups[MAX_BACKUPS:]:
                            old.unlink(missing_ok=True)
                        with open(backup_file, 'rb') as f:
                            await context.bot.send_document(chat_id=user_id, document=f, filename=backup_file.name)
                        await _safe_answer(query)
                    except Exception as e:
                        logger.error(f"❌ فشل النسخ: {e}")
                        await safe_send(context.bot, user_id, "❌ فشل النسخ")
                asyncio.create_task(backup_bg())
            elif data == CB.ADMIN_RESTORE:
                await _safe_answer(query, "📂 أرسل ملف النسخة الاحتياطية:")
                StateManager.set(user_id, UserState.WAIT_RESTORE)
                await safe_edit(query, "📂 أرسل ملف النسخة الاحتياطية:")
                return
            elif data == CB.ADMIN_RAM:
                ram = get_ram_usage()
                await safe_edit(query, f"🖥️ الرام: {ram['percent']}%")
                await _safe_answer(query)
            elif data == CB.ADMIN_METRICS:
                await safe_edit(query, "📊 المقاييس غير متوفرة حالياً")
                await _safe_answer(query)
            elif data == CB.ADMIN_LIST_ADMINS:
                admins = await DB.get_admin_list()
                if admins:
                    text = "👑 **المشرفون**\n\n" + "\n".join(f"• {a['user_id']}" for a in admins)
                else:
                    text = "لا يوجد مشرفون"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.ADMIN)]]
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                await _safe_answer(query)
            else:
                await _safe_answer(query, "⚠️ غير متوفر", show_alert=True)
        except BadRequest as e:
            if "query is too old" in str(e).lower():
                logger.debug("Query too old in admin")
            else:
                logger.error(f"خطأ في لوحة الأدمن: {e}", exc_info=True)
                await _safe_answer(query, "❌ حدث خطأ", show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في لوحة الأدمن: {e}", exc_info=True)
            await _safe_answer(query, "❌ حدث خطأ", show_alert=True)

    # ============ معالجات الردود التلقائية ============

    @staticmethod
    async def _handle_auto_reply(update, context, query, user_id, lang=None):
        """معالجة أزرار الردود التلقائية"""
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

        try:
            settings = await DB.get_auto_reply_settings(chat_id)
            current_enabled = settings.get('enabled', False)

            if action == "toggle":
                new_enabled = not current_enabled
                await DB.update_auto_reply_settings(chat_id, enabled=new_enabled)
                await _safe_answer(query, "✅ تم" if new_enabled else "❌ تم")
                return
            elif action == "add":
                StateManager.set(user_id, UserState.WAIT_AUTO_KEY)
                context.user_data['auto_chat'] = chat_id
                await safe_edit(query, "📝 أرسل الكلمة:")
                await _safe_answer(query)
                return
            elif action == "del":
                StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
                context.user_data['auto_chat'] = chat_id
                await safe_edit(query, "🗑️ أرسل الكلمة:")
                await _safe_answer(query)
                return
            elif action == "reset":
                await DB.reset_auto_replies(chat_id)
                await _safe_answer(query, "✅ تم الحذف")
                return
            elif action == "list":
                rows = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=? LIMIT 20", (chat_id,))
                text = "📋 **الردود**\n\n" + "\n".join(f"• {r['keyword']}" for r in rows) if rows else "📭 لا يوجد"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=f"auto_reply_menu:{chat_id}")]]
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                await _safe_answer(query)
                return
        except BadRequest as e:
            if "query is too old" in str(e).lower():
                logger.debug("Query too old in auto_reply")
            else:
                logger.error(f"خطأ في الردود التلقائية: {e}", exc_info=True)
                await _safe_answer(query, "❌ حدث خطأ", show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في الردود التلقائية: {e}", exc_info=True)
            await _safe_answer(query, "❌ حدث خطأ", show_alert=True)

    # ============ معالجات الجدولة ============

    @staticmethod
    async def _handle_schedule(update, context, query, user_id):
        """معالجة أزرار الجدولة"""
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("sched_", "")
        try:
            ch_id = int(parts[1])
        except:
            return

        if not await _is_channel_owner(user_id, ch_id):
            await _safe_answer(query, "❌ لا تملك هذه القناة", show_alert=True)
            return

        StateManager.clear(user_id)

        if action == "min":
            StateManager.set(user_id, UserState.WAIT_MIN)
            context.user_data['schedule_ch'] = ch_id
            await safe_edit(query, "📅 أرسل الدقائق:")
        elif action == "hour":
            StateManager.set(user_id, UserState.WAIT_HOUR)
            context.user_data['schedule_ch'] = ch_id
            await safe_edit(query, "📅 أرسل الساعات:")
        elif action == "day":
            StateManager.set(user_id, UserState.WAIT_DAY)
            context.user_data['schedule_ch'] = ch_id
            await safe_edit(query, "📅 أرسل الأيام:")
        elif action == "time":
            StateManager.set(user_id, UserState.WAIT_PUB_TIME)
            context.user_data['schedule_ch'] = ch_id
            await safe_edit(query, "🕐 أرسل الوقت HH:MM:")
        else:
            await _safe_answer(query)

        await _safe_answer(query)

    # ============ معالجات الكلمات المحظورة ============

    @staticmethod
    async def _handle_banned_words(update, context, query, user_id):
        """معالجة أزرار الكلمات المحظورة"""
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
            if not await is_authorized_in_group(context.bot, chat_id, user_id):
                lang = await DB.get_user_language(user_id) or 'ar'
                await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
                return

        try:
            if action == "add":
                StateManager.set(user_id, UserState.WAIT_GROUP_BAN if chat_id != -1 else UserState.WAIT_GLOBAL_BAN)
                context.user_data['ban_chat'] = chat_id
                await safe_edit(query, "📝 أرسل الكلمة:")
            elif action == "list":
                words = await DB.get_banned_words(chat_id)
                text = "🚫 **الكلمات**\n\n" + "\n".join(f"• {w}" for w in words[:50]) if words else "📭 لا يوجد"
                await safe_edit(query, text)
            elif action == "rem":
                StateManager.set(user_id, UserState.WAIT_REM_GROUP_BAN if chat_id != -1 else UserState.WAIT_REM_GLOBAL_BAN)
                context.user_data['ban_chat'] = chat_id
                await safe_edit(query, "🗑️ أرسل الكلمة:")
            else:
                await _safe_answer(query)
        except BadRequest as e:
            if "query is too old" in str(e).lower():
                logger.debug("Query too old in banned_words")
            else:
                logger.error(f"خطأ في الكلمات المحظورة: {e}", exc_info=True)
                await _safe_answer(query, "❌ حدث خطأ", show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في الكلمات المحظورة: {e}", exc_info=True)
            await _safe_answer(query, "❌ حدث خطأ", show_alert=True)

    # ============ معالجات الإجراءات المتقدمة ============

    @staticmethod
    async def _handle_advanced_actions(update, context, query, user_id):
        """معالجة أزرار الإجراءات المتقدمة"""
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

        actions = {
            "ban": (UserState.WAIT_BAN, "🚫 أرسل معرف المستخدم:"),
            "mute": (UserState.WAIT_MUTE, "🔇 أرسل معرف المستخدم:"),
            "warn": (UserState.WAIT_WARN, "⚠️ أرسل معرف المستخدم:"),
            "kick": (UserState.WAIT_KICK, "👢 أرسل معرف المستخدم:"),
            "restrict": (UserState.WAIT_RESTRICT, "🔒 أرسل معرف المستخدم:"),
            "unban": (UserState.WAIT_UNBAN, "🔓 أرسل معرف المستخدم:"),
        }

        if action in actions:
            state, text = actions[action]
            StateManager.set(user_id, state)
            context.user_data['adv_chat'] = chat_id
            await safe_edit(query, text)
            await _safe_answer(query)
        else:
            await _safe_answer(query, "⚠️ غير معروف", show_alert=True)

    # ============ معالجات العقوبات ============

    @staticmethod
    async def _handle_penalty(update, context, query, user_id):
        """معالجة أزرار العقوبات"""
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

        # استخدام DB.VALID_PENALTY_TYPES مباشرة
        valid_penalties = DB.VALID_PENALTY_TYPES
        if penalty not in valid_penalties:
            await _safe_answer(query, "❌ نوع غير صالح", show_alert=True)
            return

        try:
            await DB.update_security_settings(chat_id, auto_penalty=penalty)
            await safe_edit(query, f"✅ تم تعيين: {penalty}")
        except BadRequest as e:
            if "query is too old" in str(e).lower():
                logger.debug("Query too old in penalty")
            else:
                logger.error(f"خطأ في تعيين العقوبة: {e}", exc_info=True)
                await _safe_answer(query, "❌ فشل", show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في تعيين العقوبة: {e}", exc_info=True)
            await _safe_answer(query, "❌ فشل", show_alert=True)
        await _safe_answer(query)

    # ============ معالجات المسابقات ============

    @staticmethod
    async def _handle_contests(update, context, query, user_id):
        """معالجة أزرار المسابقات"""
        data = query.data

        try:
            if data == CB.ADMIN_CREATE_CONTEST:
                if not CONFIG.is_developer(user_id):
                    await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                    return
                StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
                await safe_edit(query, "🏆 أرسل العنوان:")
                await _safe_answer(query)
            elif data.startswith(CB.CONTEST_JOIN + ":"):
                cid = int(data.split(":")[-1])
                contest = await DB.get_contest_by_id(cid)
                if not contest or contest['status'] != 'active':
                    await _safe_answer(query, "❌ المسابقة غير متاحة", show_alert=True)
                    return
                StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
                context.user_data['contest_join'] = cid
                await safe_edit(query, "📝 أرسل إجابتك:")
                await _safe_answer(query)
            elif data == CB.CONTEST_WINNERS:
                winners = await DB.get_contest_winners(10)
                text = "🏆 **الفائزون**\n\n" + "\n".join(f"• {w['title']} → `{w['winner_id']}`" for w in winners) if winners else "📭 لا يوجد"
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data=CB.CONTESTS)]]
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                await _safe_answer(query)
            elif data.startswith(CB.DECLARE_WINNER_SEL + ":"):
                if not CONFIG.is_developer(user_id):
                    await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                    return
                cid = int(data.split(":")[-1])
                winner = await DB.fetchone("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,))
                if winner:
                    success = await DB.declare_winner(cid, winner['user_id'])
                    if success:
                        await safe_edit(query, f"✅ الفائز: `{winner['user_id']}`")
                        await _safe_answer(query)
                        try:
                            await context.bot.send_message(winner['user_id'], "🎉 مبروك! فزت بالمسابقة!")
                        except:
                            pass
                    else:
                        await _safe_answer(query, "❌ فشل", show_alert=True)
                else:
                    await safe_edit(query, "❌ لا يوجد مشاركون")
                    await _safe_answer(query)
        except BadRequest as e:
            if "query is too old" in str(e).lower():
                logger.debug("Query too old in contests")
            else:
                logger.error(f"خطأ في المسابقات: {e}", exc_info=True)
                await _safe_answer(query, "❌ حدث خطأ", show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في المسابقات: {e}", exc_info=True)
            await _safe_answer(query, "❌ حدث خطأ", show_alert=True)

    # ============ معالجات الاستيراد ============

    @staticmethod
    async def _handle_import(update, context, query, user_id):
        """معالجة أزرار الاستيراد"""
        if not CONFIG.is_developer(user_id):
            await _safe_answer(query, "❌ غير مصرح", show_alert=True)
            return

        data = query.data

        if data == CB.ADMIN_IMPORT_REPLIES:
            StateManager.set(user_id, UserState.WAIT_IMPORT_FILE)
            context.user_data['import_chat_id'] = -1
            await safe_edit(query, "📤 أرسل ملف JSON:")
            await _safe_answer(query)
        elif data == CB.ADMIN_IMPORT_GITHUB:
            StateManager.set(user_id, UserState.WAIT_GITHUB_URL)
            await safe_edit(query, "📥 أرسل الرابط:")
            await _safe_answer(query)


# استيراد CommandHandlers في نهاية الملف لتجنب الاستيراد الدائري
from handlers_command import CommandHandlers
