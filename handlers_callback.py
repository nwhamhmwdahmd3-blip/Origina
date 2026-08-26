#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_callback.py - معالجات الأزرار (الكولباك) - النسخة المحسّنة للأداء
جميع الأزرار تعمل - جميع المعالجات موجودة
تحسينات: كاش للاستعلامات المتكررة، استجابة أسرع، مهام خلفية للنشر، كاش للصلاحيات
+ إصلاح دعم المشرفين المجهولين في is_authorized_in_group_cached
"""

import asyncio
import shutil
import logging
import json
import time
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TimedOut

from config import CONFIG, PATHS
from database import DB
from utils import (
    TimeUtils, TextUtils, safe_send, is_authorized_in_group as _original_is_authorized,
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

# ثابت لتأخير النشر بعد كل عملية ناجحة (يمكن تعديله)
PUBLISH_DELAY = 0.5

# ============ كاش بسيط للاستعلامات المتكررة ============

# كاش لغة المستخدم
_language_cache = {}
_language_locks = {}

async def get_user_language_cached(user_id: int) -> str:
    if user_id in _language_cache:
        return _language_cache[user_id]
    if user_id not in _language_locks:
        _language_locks[user_id] = asyncio.Lock()
    async with _language_locks[user_id]:
        if user_id in _language_cache:
            return _language_cache[user_id]
        lang = await DB.get_user_language(user_id) or 'ar'
        _language_cache[user_id] = lang
        return lang

async def invalidate_user_language_cache(user_id: int):
    _language_cache.pop(user_id, None)

# كاش حالة النشر التلقائي
_auto_publish_cache = {}
_auto_publish_locks = {}

async def get_auto_publish_cached(user_id: int) -> bool:
    if user_id in _auto_publish_cache:
        return _auto_publish_cache[user_id]
    if user_id not in _auto_publish_locks:
        _auto_publish_locks[user_id] = asyncio.Lock()
    async with _auto_publish_locks[user_id]:
        if user_id in _auto_publish_cache:
            return _auto_publish_cache[user_id]
        status = await DB.get_auto_publish_status(user_id)
        _auto_publish_cache[user_id] = status
        return status

# كاش حالة التدوير التلقائي
_auto_recycle_cache = {}
_auto_recycle_locks = {}

async def get_auto_recycle_cached(user_id: int) -> bool:
    if user_id in _auto_recycle_cache:
        return _auto_recycle_cache[user_id]
    if user_id not in _auto_recycle_locks:
        _auto_recycle_locks[user_id] = asyncio.Lock()
    async with _auto_recycle_locks[user_id]:
        if user_id in _auto_recycle_cache:
            return _auto_recycle_cache[user_id]
        status = await DB.get_auto_recycle_status(user_id)
        _auto_recycle_cache[user_id] = status
        return status

def invalidate_settings_cache(user_id: int):
    _auto_publish_cache.pop(user_id, None)
    _auto_recycle_cache.pop(user_id, None)

# كاش إعدادات الردود التلقائية
_auto_reply_settings_cache = {}
_auto_reply_settings_locks = {}

async def get_auto_reply_settings_cached(chat_id: int) -> dict:
    if chat_id in _auto_reply_settings_cache:
        return _auto_reply_settings_cache[chat_id]
    if chat_id not in _auto_reply_settings_locks:
        _auto_reply_settings_locks[chat_id] = asyncio.Lock()
    async with _auto_reply_settings_locks[chat_id]:
        if chat_id in _auto_reply_settings_cache:
            return _auto_reply_settings_cache[chat_id]
        settings = await DB.get_auto_reply_settings(chat_id)
        _auto_reply_settings_cache[chat_id] = settings
        return settings

async def invalidate_auto_reply_settings_cache(chat_id: int):
    _auto_reply_settings_cache.pop(chat_id, None)

# كاش لقائمة مجموعات الأدمن
_admin_groups_cache = {}
_admin_groups_cache_time = {}

async def get_admin_groups_cached(limit=20, ttl=5.0):
    cache_key = 'admin_groups'
    now = time.monotonic()
    if cache_key in _admin_groups_cache and (now - _admin_groups_cache_time.get(cache_key, 0)) < ttl:
        return _admin_groups_cache[cache_key]
    groups = await DB.fetchall("SELECT chat_id, chat_name, banned FROM bot_groups LIMIT ?", (limit,))
    _admin_groups_cache[cache_key] = groups
    _admin_groups_cache_time[cache_key] = now
    return groups

# ✅ كاش لصلاحيات المستخدمين (مع دعم المشرفين المجهولين)
_auth_cache = {}
_auth_cache_time = {}
_auth_locks = {}

async def is_authorized_in_group_cached(bot, chat_id: int, user_id: int, ttl=30.0):
    """التحقق من الصلاحية مع دعم المشرفين المجهولين"""
    key = (chat_id, user_id)
    now = time.monotonic()
    
    # التحقق من الكاش
    if key in _auth_cache and (now - _auth_cache_time.get(key, 0)) < ttl:
        return _auth_cache[key]
    
    if key not in _auth_locks:
        _auth_locks[key] = asyncio.Lock()
    
    async with _auth_locks[key]:
        # إعادة التحقق بعد الحصول على القفل
        now = time.monotonic()
        if key in _auth_cache and (now - _auth_cache_time.get(key, 0)) < ttl:
            return _auth_cache[key]
        
        # ✅ التحقق من المشرف المجهول أولاً
        try:
            if await DB.is_anonymous_admin(chat_id, user_id):
                _auth_cache[key] = True
                _auth_cache_time[key] = now
                return True
        except Exception:
            pass
        
        # ✅ التحقق من المشرفين المخفيين
        try:
            row = await DB.fetchone(
                "SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=? AND is_hidden=1",
                (chat_id, user_id)
            )
            if row:
                _auth_cache[key] = True
                _auth_cache_time[key] = now
                return True
            
            row = await DB.fetchone(
                "SELECT 1 FROM hidden_admins WHERE chat_id=? AND admin_id=?",
                (chat_id, user_id)
            )
            if row:
                _auth_cache[key] = True
                _auth_cache_time[key] = now
                return True
        except Exception:
            pass
        
        # التحقق من الصلاحية الفعلية
        result = await _original_is_authorized(bot, chat_id, user_id)
        _auth_cache[key] = result
        _auth_cache_time[key] = now
        return result

async def invalidate_auth_cache_for(chat_id: int = None, user_id: int = None):
    if chat_id and user_id:
        _auth_cache.pop((chat_id, user_id), None)
        _auth_cache_time.pop((chat_id, user_id), None)
    elif chat_id:
        keys_to_remove = [k for k in _auth_cache if k[0] == chat_id]
        for k in keys_to_remove:
            _auth_cache.pop(k, None)
            _auth_cache_time.pop(k, None)
    else:
        _auth_cache.clear()
        _auth_cache_time.clear()

# كاش لمجموعات المستخدمين
_user_groups_cache = {}
_user_groups_cache_time = {}
_user_groups_locks = {}

async def get_user_groups_cached(user_id: int, ttl=10.0):
    now = time.monotonic()
    if user_id in _user_groups_cache and (now - _user_groups_cache_time.get(user_id, 0)) < ttl:
        return _user_groups_cache[user_id]
    if user_id not in _user_groups_locks:
        _user_groups_locks[user_id] = asyncio.Lock()
    async with _user_groups_locks[user_id]:
        now = time.monotonic()
        if user_id in _user_groups_cache and (now - _user_groups_cache_time.get(user_id, 0)) < ttl:
            return _user_groups_cache[user_id]
        groups = await DB.get_user_groups(user_id)
        _user_groups_cache[user_id] = groups
        _user_groups_cache_time[user_id] = now
        return groups

async def invalidate_user_groups_cache(user_id: int):
    _user_groups_cache.pop(user_id, None)
    _user_groups_cache_time.pop(user_id, None)

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

async def safe_edit(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        error_msg = str(e).lower()
        if "message is not modified" in error_msg:
            logger.debug("Message not modified")
        elif "message is too long" in error_msg:
            logger.warning(f"نص طويل جداً: {e}")
            try:
                short_text = text[:4000] + "\n\n... (تم الاختصار)"
                await query.edit_message_text(short_text, reply_markup=reply_markup, parse_mode=parse_mode)
            except BadRequest as e2:
                logger.error(f"فشل الاختصار: {e2}")
                try:
                    await query.answer("النص طويل جداً", show_alert=True)
                except:
                    pass
        elif "query is too old" in error_msg or "message can't be edited" in error_msg or "message not found" in error_msg:
            logger.debug("لا يمكن تعديل الرسالة")
        else:
            raise

class CallbackHandlers:
    """جميع معالجات ضغطات الأزرار"""

    @staticmethod
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        data = query.data
        if not data:
            return

        user_id = query.from_user.id
        lang = await get_user_language_cached(user_id)

        start_time = time.monotonic()

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
                auto = "✅" if await get_auto_publish_cached(user_id) else "❌"
                recycle = "✅" if await get_auto_recycle_cached(user_id) else "❌"
                kb = KeyboardFactory.build("settings", lang=lang)
                await safe_edit(query, f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}", reply_markup=kb)
                await _safe_answer(query)
                return

            if base_data == CB.TOGGLE_AUTO:
                await _safe_answer(query, "🔄 جارٍ التحديث...")
                cur = await get_auto_publish_cached(user_id)
                await DB.set_auto_publish(user_id, not cur)
                invalidate_settings_cache(user_id)
                auto = "✅" if await get_auto_publish_cached(user_id) else "❌"
                recycle = "✅" if await get_auto_recycle_cached(user_id) else "❌"
                kb = KeyboardFactory.build("settings", lang=lang)
                await safe_edit(query, f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}", reply_markup=kb)
                return

            if base_data == CB.TOGGLE_REC:
                await _safe_answer(query, "🔄 جارٍ التحديث...")
                cur = await get_auto_recycle_cached(user_id)
                await DB.set_auto_recycle(user_id, not cur)
                invalidate_settings_cache(user_id)
                auto = "✅" if await get_auto_publish_cached(user_id) else "❌"
                recycle = "✅" if await get_auto_recycle_cached(user_id) else "❌"
                kb = KeyboardFactory.build("settings", lang=lang)
                await safe_edit(query, f"⚙️ **الإعدادات**\n\n📤 النشر: {auto}\n♻️ التدوير: {recycle}", reply_markup=kb)
                return

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
                    await query.message.delete()
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
                    total_refs = stats.get('total', 0) if stats else 0
                    available_days = stats.get('available', 0) if stats else 0
                    code = await DB.get_referral_code(user_id)
                    if code and code.startswith('ref_'):
                        code = code[4:]
                    final_code = f"ref_{code}"
                    text = (
                        f"🔗 **نظام الإحالات**\n\n"
                        f"📎 **رابطك:**\n"
                        f"`https://t.me/{CONFIG.BOT_USERNAME}?start={final_code}`\n\n"
                        f"👥 المُحالين: {total_refs}\n"
                        f"🎁 الأيام المتاحة: {available_days} يوم"
                    )
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🎁 صرف", callback_data=CB.REF_CLAIM),
                         InlineKeyboardButton("📋 قائمة", callback_data=CB.REF_LIST)],
                        [InlineKeyboardButton("🔙 رجوع", callback_data=CB.BACK)]
                    ])
                    await safe_edit(query, text, reply_markup=kb, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"❌ خطأ: {e}")
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
                    logger.error(f"❌ خطأ: {e}")
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
                    await safe_edit(query, text, reply_markup=kb, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"❌ خطأ: {e}")
                    await _safe_answer(query, "❌ حدث خطأ", show_alert=True)
                return

            # ========== التذكيرات ==========
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
                text += f"📈 أسبوعي: {'✅' if settings.get('weekly_report', False) else '❌'}"
                kb = KeyboardFactory.build("reminder", lang=lang)
                await safe_edit(query, text, reply_markup=kb)
                return

            if base_data == CB.REMINDER:
                await _safe_answer(query)
                settings = await DB.get_reminder_settings(user_id)
                text = f"⏰ **التذكيرات**\n\n"
                text += f"🔔 الاشتراك: {'✅' if settings.get('subscription_reminder', False) else '❌'}\n"
                text += f"📊 يومي: {'✅' if settings.get('daily_stats_reminder', False) else '❌'}\n"
                text += f"📈 أسبوعي: {'✅' if settings.get('weekly_report', False) else '❌'}"
                kb = KeyboardFactory.build("reminder", lang=lang)
                await safe_edit(query, text, reply_markup=kb)
                return

            if base_data == CB.REM_SET_DAYS:
                StateManager.set(user_id, UserState.WAIT_REM_DAYS)
                await safe_edit(query, "📅 أرسل عدد الأيام (1-30):")
                await _safe_answer(query)
                return

            # ========== الترجمة ==========
            if base_data == CB.TRANSLATION:
                await _safe_answer(query)
                cur = await get_user_language_cached(user_id)
                kb = KeyboardFactory.build("translation", lang=lang)
                await safe_edit(query, f"🌐 الترجمة: {cur}", reply_markup=kb)
                return

            if base_data == CB.TRANS_OFF:
                await DB.set_user_language(user_id, 'off')
                await invalidate_user_language_cache(user_id)
                await safe_edit(query, "✅ تم إيقاف الترجمة")
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
                await safe_edit(query, text)
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
                StateManager.set(user_id, UserState.WAIT_CHANNEL)
                await safe_edit(query, "📡 أرسل معرف القناة:")
                await _safe_answer(query)
                return

            if base_data == CB.CH_LIST:
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.CH_SEL + ":"):
                ch_id = int(data.split(":")[-1])
                success = await DB.set_active_channel(user_id, ch_id)
                if success:
                    await safe_edit(query, "✅ تم تحديد القناة!")
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
                stats = await DB.get_channel_stats(user_id, ch_id)
                text = f"📊 **إحصائيات**\n\n📝 {stats['total']}\n✅ {stats['published']}\n⏳ {stats['unpublished']}"
                await safe_edit(query, text)
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
                asyncio.create_task(CallbackHandlers._publish_single(context.bot, active, ch_info['channel_id'], post))
                return

            if base_data == CB.POST_LIST:
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if base_data == CB.POST_REC:
                active = await DB.get_active_channel(user_id)
                if active:
                    count = await DB.reset_posts(user_id, active)
                    await safe_edit(query, f"♻️ {count} منشور!")
                await _safe_answer(query)
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
                return

            # ========== المجموعات ==========
            if base_data == CB.GROUPS:
                await _safe_answer(query)
                groups = await get_user_groups_cached(user_id)
                if not groups:
                    add_text = KeyboardFactory.get_text("add_group_button", lang)
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton(add_text, url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")]])
                    await safe_edit(query, "📭 لا توجد مجموعات", reply_markup=kb)
                    return
                text = "👥 **مجموعاتي**\n\n"
                kb = []
                for gid, name, username, banned in groups:
                    st = "✅" if not banned else "⛔"
                    text += f"{st} {name}\n"
                    security_text = KeyboardFactory.get_text("security_button", lang).replace("{name}", name[:15])
                    kb.append([InlineKeyboardButton(security_text, callback_data=f"{CB.GRP_SET}:{gid}")])
                kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
                return

            if data.startswith(CB.GRP_SET + ":"):
                chat_id = int(data.split(":")[-1])
                context.user_data['security_chat_id'] = chat_id
                
                # ✅ استخدام الدالة المحسنة
                if not await is_authorized_in_group_cached(context.bot, chat_id, user_id):
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
                ch_id = int(data.split(":")[-1])
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
                await DB.set_user_language(user_id, lang_set)
                await invalidate_user_language_cache(user_id)
                await _safe_answer(query, f"✅ {lang_set}")
                context.args = []
                await CommandHandlers.start(update, context)
                return

            await _safe_answer(query, "⚠️ غير متوفر", show_alert=True)

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

    # =====================================================================
    # الدوال المساعدة
    # =====================================================================

    @staticmethod
    async def _publish_single(bot, ch_db_id, ch_tele, post):
        try:
            text = post.get('text', '')
            media_file_id = post.get('media_file_id')
            media_type = post.get('media_type')
            caption = text[:MAX_CAPTION_LENGTH] if text else None
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
            await DB.mark_post_published(post['id'])
            await DB.update_last_publish(ch_db_id)
            await DB.update_next_publish(ch_db_id)
        except Exception as e:
            logger.error(f"❌ فشل النشر: {e}")
            await DB.increment_post_fail(post.get('id', -1))

    @staticmethod
    async def _publish_all(bot, user_id, channels):
        published_count = 0
        failed_count = 0
        await safe_send(bot, user_id, "⏳ جاري النشر...")
        tasks = []
        for ch in channels:
            post = await DB.get_next_post(ch['id'])
            if post:
                ch_info = await DB.get_channel_info(user_id, ch['id'])
                if ch_info:
                    tasks.append(CallbackHandlers._publish_single(bot, ch['id'], ch_info['channel_id'], post))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    failed_count += 1
                else:
                    published_count += 1
        await safe_send(bot, user_id, f"✅ تم نشر {published_count} | ❌ فشل {failed_count}")

    @staticmethod
    async def _show_channel_list(update, context, query, user_id, lang=None):
        if not lang:
            lang = await get_user_language_cached(user_id)
        channels = await DB.get_user_channels(user_id)
        if not channels:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)],
                [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]
            ])
            await safe_edit(query, "📭 لا توجد قنوات!", reply_markup=kb)
            await _safe_answer(query)
            return
        text = "📡 **قنواتي**\n\n"
        kb = []
        for ch in channels:
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
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
        await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb))
        await _safe_answer(query)

    @staticmethod
    async def _show_post_list(update, context, query, user_id, lang=None):
        if not lang:
            lang = await get_user_language_cached(user_id)
        active = await DB.get_active_channel(user_id)
        if not active:
            await safe_edit(query, "❌ لا توجد قناة نشطة")
            await _safe_answer(query)
            return
        posts = await DB.get_user_posts(user_id, active, 10)
        text = "📋 **منشوراتي**\n\n"
        kb = []
        for p in posts:
            text += f"🆔 {p['id']}: {(p['text'] or '')[:30]}\n"
            kb.append([InlineKeyboardButton(f"🗑️ حذف {p['id']}", callback_data=f"{CB.POST_DEL}:{p['id']}")])
        kb.append([InlineKeyboardButton("🔄 إعادة تدوير", callback_data=CB.POST_REC)])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
        await safe_edit(query, text if posts else "📭 لا يوجد", reply_markup=InlineKeyboardMarkup(kb))
        await _safe_answer(query)

    # ======================== دوال الأمان ========================

    @staticmethod
    async def _handle_security(update, context, query, user_id, lang=None):
        if not lang:
            lang = await get_user_language_cached(user_id)
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
        
        if not await is_authorized_in_group_cached(context.bot, chat_id, user_id):
            await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return

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
            "reject_join": "UPDATE group_security SET auto_reject_join = 1 - auto_reject_join WHERE chat_id=?",
            "nsfw": "UPDATE group_security SET nsfw_enabled = 1 - nsfw_enabled WHERE chat_id=?",
            "warn_enabled": "UPDATE group_security SET warn_enabled = 1 - warn_enabled WHERE chat_id=?",
        }
        
        if action in toggle_queries:
            await DB.execute(toggle_queries[action], (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
            await safe_edit(query, text, reply_markup=kb)
            await _safe_answer(query)
            return

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
                    delete_banned_words=1, auto_approve_join=1, auto_reject_join=1,
                    nsfw_enabled=1, warn_enabled=1
                WHERE chat_id=?
            """, (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
            await safe_edit(query, text, reply_markup=kb)
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
                    delete_banned_words=0, auto_approve_join=0, auto_reject_join=0,
                    nsfw_enabled=0, warn_enabled=0
                WHERE chat_id=?
            """, (chat_id,))
            settings = await DB.get_security_settings(chat_id)
            text = KeyboardFactory._format_security_text(settings)
            kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
            await safe_edit(query, text, reply_markup=kb)
            await _safe_answer(query)
            return

        if action == "close":
            try:
                await query.message.delete()
            except BadRequest:
                pass
            await _safe_answer(query)
            return

        await _safe_answer(query)

    # ======================== دوال الأدمن ========================

    @staticmethod
    async def _handle_admin(update, context, query, user_id, lang=None):
        if not CONFIG.is_developer(user_id):
            await _safe_answer(query, "❌ غير مصرح", show_alert=True)
            return
        if not lang:
            lang = await get_user_language_cached(user_id)
        data = query.data

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
        elif data == CB.ADMIN_BANNED:
            users = await DB.get_all_users()
            banned = [str(u.get('user_id', u[0] if isinstance(u, (tuple, list)) else '')) for u in users if (u.get('banned', 0) if isinstance(u, dict) else (u[1] if isinstance(u, (tuple, list)) else 0)) == 1]
            await safe_edit(query, "⛔ **المحظورين**\n\n" + "\n".join(banned[:20]) if banned else "لا يوجد محظورون")
            await _safe_answer(query)
        elif data == CB.ADMIN_UNBAN_ALL:
            await DB.execute("UPDATE users SET banned=0 WHERE banned=1")
            await safe_edit(query, "✅ تم إلغاء حظر الجميع")
            await _safe_answer(query)
        elif data == CB.ADMIN_CHANNELS:
            channels = await DB.fetchall("SELECT channel_id, channel_name, banned FROM user_channels LIMIT 50")
            text = "📡 **القنوات**\n\n" + "\n".join(f"{'✅' if not c['banned'] else '🚫'} {c['channel_name']}" for c in channels)
            await safe_edit(query, text if channels else "📭 لا توجد")
            await _safe_answer(query)
        elif data == CB.ADMIN_GROUPS:
            groups = await get_admin_groups_cached(20)
            text = "👥 **المجموعات**\n\n" + "\n".join(f"{'✅' if not g['banned'] else '🚫'} {g['chat_name']}" for g in groups)
            await safe_edit(query, text if groups else "📭 لا توجد")
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
            text = "🧾 **الفواتير**\n\n" + "\n".join(f"• {inv['number']} - {inv['amount']} ⭐ - {inv['status']}" for inv in invoices)
            await safe_edit(query, text if invoices else "📭 لا توجد")
            await _safe_answer(query)
        elif data == CB.ADMIN_BACKUP:
            await query.answer("⏳ جارٍ النسخ...")
            async def backup_bg():
                try:
                    PATHS.BACKUPS.mkdir(parents=True, exist_ok=True)
                    backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                    shutil.copy2(PATHS.DB, backup_file)
                    with open(backup_file, 'rb') as f:
                        await context.bot.send_document(chat_id=user_id, document=f, filename=backup_file.name)
                    await _safe_answer(query)
                except Exception as e:
                    logger.error(f"❌ فشل النسخ: {e}")
                    await safe_send(context.bot, user_id, "❌ فشل النسخ")
            asyncio.create_task(backup_bg())
        elif data == CB.ADMIN_RAM:
            ram = get_ram_usage()
            await safe_edit(query, f"🖥️ الرام: {ram['percent']}%")
            await _safe_answer(query)
        elif data == CB.ADMIN_METRICS:
            m = METRICS.get_stats()
            await safe_edit(query, f"📊 API: {m.get('api_calls_last_hour', 0)}\n⚠️ أخطاء: {m.get('errors_last_hour', 0)}")
            await _safe_answer(query)
        else:
            await _safe_answer(query, "⚠️ غير متوفر", show_alert=True)

    # ======================== دوال الردود ========================

    @staticmethod
    async def _handle_auto_reply(update, context, query, user_id, lang=None):
        if not lang:
            lang = await get_user_language_cached(user_id)
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("auto_reply_", "")
        try:
            chat_id = int(parts[1])
        except:
            return
        
        if not await is_authorized_in_group_cached(context.bot, chat_id, user_id):
            await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return
        
        settings = await get_auto_reply_settings_cached(chat_id)
        current_enabled = settings.get('enabled', False)
        
        if action == "toggle":
            new_enabled = not current_enabled
            await DB.update_auto_reply_settings(chat_id, enabled=new_enabled)
            _auto_reply_settings_cache[chat_id] = settings.copy()
            _auto_reply_settings_cache[chat_id]['enabled'] = new_enabled
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
            await invalidate_auto_reply_settings_cache(chat_id)
            await _safe_answer(query, "✅ تم الحذف")
            return
        elif action == "list":
            rows = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=? LIMIT 20", (chat_id,))
            text = "📋 **الردود**\n\n" + "\n".join(f"• {r['keyword']}" for r in rows) if rows else "📭 لا يوجد"
            await safe_edit(query, text)
            await _safe_answer(query)
            return

    # ======================== دوال الجدولة ========================

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
        
        await _safe_answer(query)

    # ======================== دوال الكلمات المحظورة ========================

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
            if not await is_authorized_in_group_cached(context.bot, chat_id, user_id):
                lang = await get_user_language_cached(user_id)
                await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
                return
        
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
        
        await _safe_answer(query)

    # ======================== دوال الإجراءات المتقدمة ========================

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
        
        if not await is_authorized_in_group_cached(context.bot, chat_id, user_id):
            lang = await get_user_language_cached(user_id)
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

    # ======================== دوال العقوبات ========================

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
        
        if not await is_authorized_in_group_cached(context.bot, chat_id, user_id):
            lang = await get_user_language_cached(user_id)
            await _safe_answer(query, await get_text(lang, 'unauthorized'), show_alert=True)
            return
        
        if penalty not in DB.VALID_PENALTY_TYPES:
            await _safe_answer(query, "❌ نوع غير صالح", show_alert=True)
            return
        
        await DB.execute("UPDATE group_security SET auto_penalty=? WHERE chat_id=?", (penalty, chat_id))
        await safe_edit(query, f"✅ تم تعيين: {penalty}")
        await _safe_answer(query)

    # ======================== دوال المسابقات ========================

    @staticmethod
    async def _handle_contests(update, context, query, user_id):
        data = query.data
        
        if data == CB.ADMIN_CREATE_CONTEST:
            if not CONFIG.is_developer(user_id):
                await _safe_answer(query, "❌ غير مصرح", show_alert=True)
                return
            StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
            await safe_edit(query, "🏆 أرسل العنوان:")
            await _safe_answer(query)
        elif data.startswith(CB.CONTEST_JOIN + ":"):
            cid = int(data.split(":")[-1])
            StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
            context.user_data['contest_join'] = cid
            await safe_edit(query, "📝 أرسل إجابتك:")
            await _safe_answer(query)
        elif data == CB.CONTEST_WINNERS:
            winners = await DB.get_contest_winners(10)
            text = "🏆 **الفائزون**\n\n" + "\n".join(f"• {w['title']} → `{w['winner_id']}`" for w in winners) if winners else "📭 لا يوجد"
            await safe_edit(query, text)
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

    # ======================== دوال الاستيراد ========================

    @staticmethod
    async def _handle_import(update, context, query, user_id):
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
