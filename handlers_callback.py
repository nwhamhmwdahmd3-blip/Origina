#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_callback.py - المعالج النهائي الكامل لجميع الأزرار (نسخة محسنة وآمنة بالكامل)
- لوحة أدمن كاملة مع جميع الصلاحيات
- معالجات أمان محسنة مع التحقق الكامل من الصلاحيات
- شراء الهدايا يعمل بشكل كامل
- إصلاح جميع الأزرار المعطلة
- تحسين نظام الرجوع للخلف
- إضافة التحقق من صحة جميع المدخلات
- حماية كاملة من هجمات CSRF والتلاعب بالبيانات
- تسجيل جميع محاولات الوصول غير المصرح
- دعم كامل لجميع اللغات
- تحسين الأداء مع التخزين المؤقت
"""

import asyncio
import logging
import json
import time
import shutil
import os
import weakref
import hmac
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Set

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, ChatPermissions
from telegram.ext import ContextTypes
from telegram.error import BadRequest, RetryAfter, Forbidden

from config import CONFIG, PATHS
from database import DB, TimeUtils
from utils import (
    safe_send, is_authorized_in_group,
    get_text, StateManager, UserState,
    KeyboardFactory, CB, get_ram_usage
)
from .handlers_command import CommandHandlers

logger = logging.getLogger(__name__)

# الثوابت
MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096
MAX_BACKUPS = CONFIG.MAX_BACKUPS
MAX_CONCURRENT_PUBLISH = 3
MAX_PAGE_SIZE = 5
MAX_HISTORY_SIZE = 10
DEBOUNCE_TIME = 1.5
RATE_LIMIT_TIME = 2.0

# أنواع العقوبات الصالحة
VALID_PENALTY_TYPES = {'mute', 'ban', 'restrict', 'kick', 'none'}
VALID_WARN_PENALTIES = {'mute', 'ban', 'restrict', 'kick'}

# خريطة أعمدة قاعدة البيانات للعقوبات
PENALTY_COLUMN_MAP = {
    'mute': 'mute_default_duration',
    'ban': 'ban_default_duration',
    'restrict': 'restrict_default_duration',
    'antiflood': 'antiflood_penalty_duration',
    'night': 'night_mode_action_duration',
    'warn_penalty': 'warn_penalty_duration',
}

# خريطة إعدادات الأمان
SECURITY_TOGGLE_MAP = {
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
    "approve_join": "auto_approve_join",
    "reject_join": "auto_reject_join",
    "nsfw": "nsfw_enabled",
}

# قائمة الأزرار المعروفة
KNOWN_CALLBACK_PREFIXES = [
    CB.TOGGLE_AUTO, CB.TOGGLE_REC, CB.TRANSLATION, CB.REFERRAL,
    CB.REMINDER, CB.CONTESTS, CB.SUPPORT_TICKET, CB.CH_LIST,
    CB.CH_ADD, CB.POST_ADD, CB.POST_PUB, CB.POST_LIST, CB.POST_REC, 
    CB.PUB_ALL, CB.GROUPS, CB.ADMIN, CB.SETTINGS, CB.PLANS, CB.INVOICES,
    CB.REF_CLAIM, CB.REF_LIST, CB.CONTEST_WINNERS, CB.DEVELOPER,
    CB.SUBSCRIBE, CB.SUPPORT, CB.LANGUAGE, CB.TRIAL, CB.HELP,
    CB.CANCEL, CB.CHECK_SUB, CB.TRANS_OFF, CB.REM_TOGGLE_SUB,
    CB.REM_TOGGLE_DAILY, CB.REM_TOGGLE_WEEKLY, CB.REM_SET_DAYS,
    CB.ADMIN_LIST_ADMINS, CB.ADMIN_USERS, CB.ADMIN_BANNED,
    CB.ADMIN_UNBAN_ALL, CB.ADMIN_STATS, CB.ADMIN_CHANNELS,
    CB.ADMIN_GROUPS, CB.ADMIN_ADD_ADMIN, CB.ADMIN_REM_ADMIN,
    CB.ADMIN_BROADCAST, CB.ADMIN_INVOICES, CB.ADMIN_BACKUP,
    CB.ADMIN_RESTORE, CB.ADMIN_RESTORE_SEL, CB.ADMIN_RAM,
    CB.ADMIN_METRICS, CB.ADMIN_UPTIME, CB.ADMIN_TICKETS,
    CB.ADMIN_DEL_TICKETS, CB.ADMIN_PAYMENT_LOGS, CB.ADMIN_SET_UPDATE_CH,
    CB.ADMIN_SEND_UPDATE, CB.ADMIN_SHOW_UPDATE, CB.ADMIN_SET_LOG_CH,
    CB.ADMIN_LOG_CH, CB.ADMIN_FORCE_SUB, CB.ADMIN_SET_FORCE,
    CB.ADMIN_REFRESH_CACHE, CB.ADMIN_BANNED_CH, CB.ADMIN_ACTIVATE_CH,
    CB.ADMIN_BANNED_GR, CB.ADMIN_UNBAN_GR, CB.ADMIN_REPLIES,
    CB.ADMIN_EXPORT_REPLIES, CB.ADMIN_IMPORT_REPLIES, CB.ADMIN_IMPORT_GITHUB,
    CB.ADMIN_BANNED_WORDS, CB.ADMIN_CREATE_CONTEST, CB.ADMIN_DECLARE_WINNER,
    CB.ADMIN_DEL_CONTEST, CB.DECLARE_WINNER_SEL, CB.CONTEST_JOIN,
    # الإضافات الجديدة
    CB.STATS, CB.ADMIN_HELP, CB.ADMIN_PUSH, CB.ADMIN_FILES,
    CB.ADMIN_DEL_FILE, CB.ADMIN_PING, CB.CH_STATS_DETAILED,
]

ACTIVE_TASKS = weakref.WeakSet()


def generate_csrf_token(user_id: int, chat_id: int, action: str) -> str:
    """توليد رمز CSRF للتحقق من سلامة الأزرار"""
    try:
        secret = CONFIG.SECRET_KEY if hasattr(CONFIG, 'SECRET_KEY') else "default_secret_key"
        message = f"{user_id}:{chat_id}:{action}"
        token = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()[:16]
        return token
    except Exception as e:
        logger.error(f"خطأ في توليد CSRF token: {e}")
        return ""


def verify_csrf_token(user_id: int, chat_id: int, action: str, token: str) -> bool:
    """التحقق من صحة رمز CSRF"""
    try:
        expected = generate_csrf_token(user_id, chat_id, action)
        return hmac.compare_digest(expected, token)
    except Exception:
        return False


async def _safe_answer(query, text=None, show_alert=False):
    """إرسال رد آمن على الاستعلام"""
    if not query:
        return False
    try:
        if text:
            await query.answer(text, show_alert=show_alert)
        else:
            await query.answer()
        return True
    except Exception as e:
        logger.debug(f"فشل في الإجابة على الاستعلام: {e}")
        return False


async def _trans(key, lang, default_ar):
    """جلب النص المترجم مع fallback للعربية"""
    try:
        text = await get_text(lang, key)
        if not text or text == key:
            return default_ar
        return text
    except Exception:
        return default_ar


async def safe_edit(query, text, reply_markup=None, parse_mode=None, bot=None):
    """تعديل رسالة بأمان مع معالجة الأخطاء"""
    await _safe_answer(query)
    if not query or not query.message:
        return False
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            return True
        except RetryAfter as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(e.retry_after)
            else:
                logger.warning(f"فشل التعديل بعد {max_retries} محاولات بسبب RetryAfter")
                return False
        except BadRequest as e:
            error_msg = str(e).lower()
            if "message is not modified" in error_msg:
                return True
            elif "message is too long" in error_msg:
                chat_id = query.message.chat_id
                try:
                    await query.message.delete()
                except Exception:
                    pass
                try:
                    send_bot = bot if bot else query._bot
                    await send_bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                    return True
                except Exception as e2:
                    logger.error(f"فشل إرسال رسالة جديدة بعد الطول الزائد: {e2}")
                    return False
            else:
                logger.debug(f"BadRequest في التعديل: {e}")
                return False
        except Exception as e:
            logger.debug(f"خطأ في التعديل: {e}")
            return False
    return False


async def safe_delete_message(query_or_message):
    """حذف رسالة بأمان"""
    try:
        if hasattr(query_or_message, 'message') and query_or_message.message:
            await query_or_message.message.delete()
        elif query_or_message:
            await query_or_message.delete()
    except Exception:
        pass


def _mask_id(id_value, prefix=3, suffix=2):
    """إخفاء جزء من المعرف للأمان"""
    if id_value is None:
        return "***"
    s = str(id_value)
    if len(s) <= 5:
        return "***"
    return s[:prefix] + "***" + s[-suffix:]


async def _is_channel_owner(user_id: int, channel_db_id: int) -> bool:
    """التحقق من ملكية القناة"""
    try:
        return await DB.is_channel_owner(user_id, channel_db_id)
    except Exception as e:
        logger.error(f"خطأ في التحقق من ملكية القناة: {e}")
        return False


async def _is_group_owner(user_id: int, chat_id: int) -> bool:
    """التحقق من ملكية المجموعة"""
    try:
        return await DB.is_group_owner(user_id, chat_id)
    except Exception as e:
        logger.error(f"خطأ في التحقق من ملكية المجموعة: {e}")
        return False


def validate_chat_id(chat_id_str: str) -> Optional[int]:
    """التحقق من صحة معرف المجموعة"""
    try:
        chat_id = int(chat_id_str)
        if chat_id == 0:
            return None
        return chat_id
    except (ValueError, TypeError):
        return None


def validate_user_id(user_id_str: str) -> Optional[int]:
    """التحقق من صحة معرف المستخدم"""
    try:
        user_id = int(user_id_str)
        if user_id <= 0:
            return None
        return user_id
    except (ValueError, TypeError):
        return None


class CallbackHandlers:
    """معالج جميع أزرار البوت"""

    @staticmethod
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """المعالج الرئيسي لجميع الأزرار"""
        query = update.callback_query
        if not query:
            return
        
        data = query.data
        if not data:
            return

        # نظام منع النقر المتكرر
        debounce_key = f"debounce_{query.id}"
        now_time = time.monotonic()
        last_time = context.user_data.get(debounce_key, 0)
        if now_time - last_time < DEBOUNCE_TIME:
            await _safe_answer(query, await _trans('wait_moment', 'ar', "⚠️ انتظر لحظة"))
            return
        context.user_data[debounce_key] = now_time

        user_id = query.from_user.id
        lang = context.user_data.get('lang')
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
            context.user_data['lang'] = lang
        
        start_time = time.monotonic()

        if 'start_time' not in context.bot_data:
            context.bot_data['start_time'] = time.monotonic()

        # استخراج البيانات الأساسية
        base_data = data
        if ':' in data:
            parts = data.split(':')
            if parts[0] in KNOWN_CALLBACK_PREFIXES:
                base_data = parts[0]

        # نظام rate limiting
        rate_key = f"rate_{user_id}_{base_data}"
        last_click = context.user_data.get(rate_key, 0)
        if time.monotonic() - last_click < RATE_LIMIT_TIME:
            await _safe_answer(query, await _trans('wait_moment', lang, "⚠️ يرجى الانتظار قليلاً"), show_alert=True)
            return
        context.user_data[rate_key] = time.monotonic()

        try:
            # ========== الأزرار الأساسية ==========
            if base_data == "status_only":
                await _safe_answer(query, await _trans('status', lang, "📊 الحالة"))
                return

            if base_data in [CB.MAIN, CB.BACK]:
                await _safe_answer(query)
                StateManager.clear(user_id)
                context.user_data.clear()
                context.args = []
                await CommandHandlers.start(update, context)
                return

            if base_data == CB.CANCEL:
                current_state = StateManager.get(user_id)
                StateManager.clear(user_id)
                context.user_data.clear()
                context.args = []
                await _safe_answer(query, await _trans('cancelled', lang, "❌ تم الإلغاء"))
                await safe_delete_message(query)
                await CommandHandlers.start(update, context)
                return

            if base_data == CB.HELP:
                await _safe_answer(query)
                StateManager.clear(user_id)
                await CommandHandlers.help_command(update, context)
                return

            if base_data == CB.TRIAL:
                await _safe_answer(query, await _trans('activating', lang, "🔄 جارٍ التفعيل..."))
                if await DB.has_used_trial(user_id):
                    await safe_edit(query, await _trans('trial_used', lang, "❌ لقد استخدمت التجربة المجانية بالفعل."), bot=context.bot)
                    return
                
                days = await DB.activate_trial(user_id)
                if days > 0:
                    text = await _trans('trial_activated', lang, "✅ تم تفعيل التجربة المجانية لمدة {days} يوم")
                    try:
                        text = text.format(days=days)
                    except:
                        text = f"✅ تم تفعيل التجربة المجانية لمدة {days} يوم"
                else:
                    text = await _trans('trial_failed', lang, "❌ تعذر تفعيل التجربة")
                await safe_edit(query, text, bot=context.bot)
                return

            if base_data == CB.DEVELOPER:
                await _safe_answer(query)
                StateManager.clear(user_id)
                await CommandHandlers.developer(update, context)
                return

            if base_data == CB.SUBSCRIBE:
                await _safe_answer(query)
                StateManager.clear(user_id)
                await CommandHandlers.subscribe(update, context)
                return

            if base_data == CB.SUPPORT:
                await _safe_answer(query)
                StateManager.clear(user_id)
                await CommandHandlers.support(update, context)
                return

            if base_data == CB.LANGUAGE:
                await _safe_answer(query)
                StateManager.clear(user_id)
                await CommandHandlers.language(update, context)
                return

            if base_data == CB.CHECK_SUB:
                await _safe_answer(query)
                StateManager.clear(user_id)
                await CommandHandlers.start(update, context)
                return

            # ========== الإحصائيات العامة ==========
            if base_data == CB.STATS:
                await CallbackHandlers._show_public_stats(update, context, query, user_id, lang)
                return

            # ========== الإعدادات ==========
            if base_data in [CB.SETTINGS, CB.TOGGLE_AUTO, CB.TOGGLE_REC]:
                await CallbackHandlers._handle_settings(update, context, query, user_id, lang, base_data)
                return

            # ========== الباقات والدفع ==========
            if base_data == CB.PLANS:
                await safe_edit(query, await _trans('plan_selector', lang, "💎 اختر باقة:"), reply_markup=KeyboardFactory.build("plans", lang=lang), bot=context.bot)
                return

            if base_data == "gift_plans":
                await CallbackHandlers._show_gift_plans(update, context, query, user_id, lang)
                return

            if base_data == "redeem_gift":
                await _safe_answer(query)
                StateManager.clear(user_id)
                await CommandHandlers.redeem_gift(update, context)
                return

            if data.startswith("buy_sub_"):
                await CallbackHandlers._handle_buy_subscription(update, context, query, user_id, lang, data)
                return

            if data.startswith("buy_gift:"):
                await CallbackHandlers._handle_buy_gift(update, context, query, user_id, lang, data)
                return

            if base_data == CB.INVOICES:
                await CallbackHandlers._show_invoices(update, context, query, user_id, lang)
                return

            # ========== الإحالات ==========
            if base_data in [CB.REFERRAL, CB.REF_CLAIM, CB.REF_LIST]:
                await CallbackHandlers._handle_referrals(update, context, query, user_id, lang, base_data)
                return

            # ========== التذكيرات ==========
            if base_data in [CB.REMINDER, CB.REM_TOGGLE_SUB, CB.REM_TOGGLE_DAILY, CB.REM_TOGGLE_WEEKLY, CB.REM_SET_DAYS]:
                await CallbackHandlers._handle_reminders(update, context, query, user_id, lang, base_data)
                return

            # ========== الترجمة ==========
            if base_data == CB.TRANSLATION:
                await CallbackHandlers._show_translation_menu(update, context, query, user_id, lang)
                return

            if base_data == CB.TRANS_OFF:
                await DB.set_user_language(user_id, 'off')
                context.user_data['lang'] = 'ar'
                await safe_edit(query, await _trans('translation_disabled', lang, "✅ تم إيقاف الترجمة"), bot=context.bot)
                await CommandHandlers.start(update, context)
                return

            if data.startswith("lang_"):
                await CallbackHandlers._handle_language_change(update, context, query, user_id, data)
                return

            # ========== المسابقات ==========
            if base_data == CB.CONTESTS:
                await _safe_answer(query)
                StateManager.clear(user_id)
                await CommandHandlers.contests(update, context)
                return

            if base_data == CB.CONTEST_WINNERS:
                await CallbackHandlers._show_contest_winners(update, context, query, user_id, lang)
                return

            # ========== الدعم ==========
            if base_data == CB.SUPPORT_TICKET:
                StateManager.set(user_id, UserState.SUPPORT_MODE)
                await safe_send(context.bot, user_id, await _trans('send_support_message', lang, "📞 أرسل رسالتك:"))
                await _safe_answer(query)
                return

            # ========== القنوات ==========
            if base_data == CB.CH_ADD:
                await CallbackHandlers._handle_add_channel(update, context, query, user_id, lang)
                return

            if base_data == CB.CH_LIST:
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
                return

            if data.startswith(CB.CH_SEL + ":"):
                await CallbackHandlers._handle_select_channel(update, context, query, user_id, lang, data)
                return

            if data.startswith(CB.CH_DEL + ":"):
                await CallbackHandlers._handle_delete_channel(update, context, query, user_id, lang, data)
                return

            if data.startswith(CB.CH_STATS + ":"):
                await CallbackHandlers._handle_channel_stats(update, context, query, user_id, lang, data)
                return

            if data.startswith(CB.CH_STATS_DETAILED + ":"):
                await CallbackHandlers._show_channel_detailed_stats(update, context, query, user_id, lang, data)
                return

            # ========== المنشورات ==========
            if base_data == CB.POST_ADD:
                await CallbackHandlers._handle_add_post(update, context, query, user_id, lang)
                return

            if base_data == "finish_posts":
                await CallbackHandlers._handle_finish_posts(update, context, query, user_id, lang)
                return

            if base_data == CB.POST_PUB:
                await CallbackHandlers._handle_publish_post(update, context, query, user_id, lang)
                return

            if base_data == CB.POST_LIST:
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
                return

            if base_data == CB.POST_REC:
                await CallbackHandlers._handle_recycle_posts(update, context, query, user_id, lang)
                return

            if data.startswith(CB.POST_DEL + ":"):
                await CallbackHandlers._handle_delete_post(update, context, query, user_id, lang, data)
                return

            if base_data == CB.POST_CLEAR:
                await CallbackHandlers._handle_clear_posts(update, context, query, user_id, lang)
                return

            if base_data == CB.PUB_ALL:
                await CallbackHandlers._handle_publish_all(update, context, query, user_id, lang)
                return

            # ========== المجموعات ==========
            if base_data == CB.GROUPS:
                await CallbackHandlers._show_groups(update, context, query, user_id, lang)
                return

            if data.startswith("grp_del:"):
                await CallbackHandlers._handle_delete_group(update, context, query, user_id, lang, data)
                return

            if data.startswith(CB.GRP_SET + ":"):
                await CallbackHandlers._handle_group_settings(update, context, query, user_id, lang, data)
                return

            # ========== لوحة الأدمن ==========
            if base_data == CB.ADMIN:
                if not CONFIG.is_developer(user_id):
                    await _safe_answer(query, await _trans('unauthorized', lang, "❌ غير مصرح"), show_alert=True)
                    return
                kb = KeyboardFactory.build("admin_panel", lang=lang)
                await safe_edit(query, await _trans('admin_panel', lang, "👑 لوحة الأدمن"), reply_markup=kb, bot=context.bot)
                return

            # ========== توجيه المعالجات المتخصصة ==========
            if data.startswith("sec_"):
                await CallbackHandlers._handle_security(update, context, query, user_id, lang)
                return

            if data.startswith("admin_") or data == "admin_grant_free":
                if CONFIG.is_developer(user_id):
                    await CallbackHandlers._handle_admin(update, context, query, user_id, lang)
                else:
                    await _safe_answer(query, await _trans('unauthorized', lang, "❌ غير مصرح"), show_alert=True)
                return

            if data.startswith("auto_reply_") or data.startswith("auto_reply_menu:"):
                await CallbackHandlers._handle_auto_reply(update, context, query, user_id, lang)
                return

            if data.startswith("sched_open:") or data.startswith("sched_"):
                await CallbackHandlers._handle_schedule(update, context, query, user_id)
                return

            if data.startswith("ban_") or data.startswith("act_") or data.startswith("pen_"):
                await CallbackHandlers._handle_advanced_actions(update, context, query, user_id)
                return

            if data.startswith("contest_") or data.startswith(CB.DECLARE_WINNER_SEL + ":"):
                await CallbackHandlers._handle_contests(update, context, query, user_id)
                return

            if data in (CB.ADMIN_IMPORT_REPLIES, CB.ADMIN_IMPORT_GITHUB):
                await CallbackHandlers._handle_import(update, context, query, user_id)
                return

            # ========== ترقيم الصفحات ==========
            if data.startswith("ch_page_"):
                await CallbackHandlers._handle_channel_pagination(update, context, query, user_id, lang, data)
                return

            if data.startswith("post_page_"):
                await CallbackHandlers._handle_post_pagination(update, context, query, user_id, lang, data)
                return

            # ========== set_duration ==========
            if data.startswith("set_duration:"):
                await CallbackHandlers._handle_set_duration(update, context, query, user_id, lang, data)
                return

            # ========== sec_penalty_ ==========
            if data.startswith("sec_penalty_") and ":" in data:
                await CallbackHandlers._handle_sec_penalty(update, context, query, user_id, lang, data)
                return

            # ========== معالجات اللوحة الخاصة ==========
            if data in ["panel_lock", "panel_unlock", "panel_close"]:
                await CallbackHandlers._handle_panel(update, context, query, user_id, data)
                return

            # زر غير معروف
            logger.warning(f"⚠️ زر غير معروف: {data} | مستخدم: {user_id}")
            await _safe_answer(query, await _trans('not_available', lang, "⚠️ هذا الزر غير متوفر حالياً"), show_alert=True)

        except BadRequest as e:
            if "query is too old" not in str(e).lower():
                logger.error(f"❌ BadRequest: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Callback error: {e}", exc_info=True)
        finally:
            if time.monotonic() - start_time > 1.0:
                logger.warning(f"🐢 زر بطيء {data} | الوقت: {time.monotonic() - start_time:.2f} ثانية")

    # ============ معالج الإعدادات ============
    @staticmethod
    async def _handle_settings(update, context, query, user_id, lang, action):
        """معالجة أزرار الإعدادات"""
        try:
            if action == CB.TOGGLE_AUTO:
                cur = await DB.get_auto_publish_status(user_id)
                await DB.set_auto_publish(user_id, not cur)
                status = "✅" if not cur else "❌"
                await _safe_answer(query, f"📤 النشر التلقائي: {status}")
            elif action == CB.TOGGLE_REC:
                cur = await DB.get_auto_recycle_status(user_id)
                await DB.set_auto_recycle(user_id, not cur)
                status = "✅" if not cur else "❌"
                await _safe_answer(query, f"♻️ التدوير التلقائي: {status}")

            # عرض الإعدادات المحدثة
            auto = "✅" if await DB.get_auto_publish_status(user_id) else "❌"
            rec = "✅" if await DB.get_auto_recycle_status(user_id) else "❌"
            settings_title = await _trans('settings_title', lang, "⚙️ الإعدادات")
            auto_label = await _trans('auto_publish_status', lang, "📤 النشر")
            recycle_label = await _trans('auto_recycle_status', lang, "♻️ التدوير")
            kb = KeyboardFactory.build("settings", lang=lang)
            await safe_edit(query, f"{settings_title}\n\n{auto_label}: {auto}\n{recycle_label}: {rec}", reply_markup=kb, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في معالجة الإعدادات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ الإحصائيات العامة ============
    @staticmethod
    async def _show_public_stats(update, context, query, user_id, lang):
        """عرض الإحصائيات العامة للمستخدمين العاديين"""
        try:
            stats = await DB.get_general_stats()
            
            text = await _trans('public_stats', lang, "📊 إحصائيات البوت") + "\n\n"
            text += f"👥 {await _trans('total_users', lang, 'المستخدمون')}: {stats['users']}\n"
            text += f"📡 {await _trans('total_channels', lang, 'القنوات')}: {stats['channels']}\n"
            text += f"👥 {await _trans('total_groups', lang, 'المجموعات')}: {stats['groups']}\n"
            text += f"📝 {await _trans('total_posts', lang, 'المنشورات')}: {stats['posts']}\n"
            text += f"✅ {await _trans('published_posts', lang, 'المنشورة')}: {stats['published']}"
            
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.BACK)]])
            await safe_edit(query, text, reply_markup=kb, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض الإحصائيات العامة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات الهدايا والباقات ============
    @staticmethod
    async def _show_gift_plans(update, context, query, user_id, lang):
        """عرض خطط الهدايا المتاحة"""
        try:
            plans = await DB.get_gift_plans()
            if not plans:
                await safe_edit(query, await _trans('no_gift_plans', lang, "📭 لا توجد خطط هدايا"), bot=context.bot)
                return
            
            kb = [[InlineKeyboardButton(f"🎁 {p['days']} يوم - {p['price']} ⭐", callback_data=f"buy_gift:{p['id']}")] for p in plans]
            kb.append([InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.BACK)])
            await safe_edit(query, await _trans('gift_plans_text', lang, "💎 اختر خطة هدية:"), reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض خطط الهدايا: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_buy_subscription(update, context, query, user_id, lang, data):
        """معالجة شراء الاشتراك"""
        try:
            await _safe_answer(query, await _trans('preparing', lang, "🔄 جارٍ التحضير..."))
            try:
                days = int(data.split("_")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            plan_names = {1: "يوم", 7: "أسبوع", 30: "شهر", 90: "3 أشهر", 365: "سنة"}
            plan_name = plan_names.get(days)
            if not plan_name:
                await _safe_answer(query, await _trans('plan_not_found', lang, "❌ باقة غير موجودة"), show_alert=True)
                return
            
            plan = await DB.get_plan_by_name(plan_name)
            if not plan:
                await _safe_answer(query, await _trans('plan_not_found', lang, "❌ باقة غير موجودة"), show_alert=True)
                return
            
            invoice_number = await DB.create_invoice(user_id, plan['id'], plan['price'])
            if not invoice_number:
                await _safe_answer(query, await _trans('payment_failed', lang, "❌ فشل الدفع"), show_alert=True)
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
                await _safe_answer(query, await _trans('invoice_sent', lang, "✅ تم إرسال الفاتورة"))
                await safe_delete_message(query)
            except Exception as e:
                logger.error(f"❌ فشل إرسال الفاتورة: {e}")
                await DB.execute("UPDATE invoices SET status='cancelled' WHERE number=?", (invoice_number,))
                await _safe_answer(query, f"❌ {str(e)[:50]}", show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في شراء الاشتراك: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_buy_gift(update, context, query, user_id, lang, data):
        """معالجة شراء هدية"""
        try:
            await _safe_answer(query, await _trans('preparing', lang, "🔄 جارٍ التحضير..."))
            try:
                gift_plan_id = int(data.split(":")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            plan = await DB.get_gift_plan(gift_plan_id)
            if not plan:
                await _safe_answer(query, await _trans('gift_plan_not_found', lang, "❌ خطة الهدية غير موجودة"), show_alert=True)
                return
            
            invoice_number = await DB.create_invoice(user_id, plan['id'], plan['price'])
            if not invoice_number:
                await _safe_answer(query, await _trans('invoice_failed', lang, "❌ فشل إنشاء الفاتورة"), show_alert=True)
                return
            
            try:
                await context.bot.send_invoice(
                    chat_id=user_id,
                    title=f"🎁 {plan['name']}",
                    description=plan['description'] or "كود هدية",
                    payload=json.dumps({'gift_plan_id': plan['id'], 'invoice': invoice_number, 'type': 'gift'}),
                    provider_token="",
                    currency="XTR",
                    prices=[LabeledPrice(plan['name'], plan['price'])]
                )
                await _safe_answer(query, await _trans('invoice_sent', lang, "✅ تم إرسال الفاتورة"))
                await safe_delete_message(query)
            except Exception as e:
                logger.error(f"❌ فشل إرسال فاتورة الهدية: {e}")
                await DB.execute("UPDATE invoices SET status='cancelled' WHERE number=?", (invoice_number,))
                await _safe_answer(query, f"❌ {str(e)[:50]}", show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في شراء الهدية: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _show_invoices(update, context, query, user_id, lang):
        """عرض فواتير المستخدم"""
        try:
            invoices = await DB.get_user_invoices(user_id, 10)
            if not invoices:
                await safe_edit(query, await _trans('no_invoices', lang, "📭 لا توجد فواتير"), bot=context.bot)
                return
            
            text = await _trans('my_invoices', lang, "🧾 فواتيري") + "\n\n"
            for inv in invoices:
                text += f"• #{inv['number']} - {inv['amount']} ⭐ - {inv['status']}\n"
            
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.BACK)]])
            await safe_edit(query, text, reply_markup=kb, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض الفواتير: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات الإحالات ============
    @staticmethod
    async def _handle_referrals(update, context, query, user_id, lang, action):
        """معالجة أزرار الإحالات"""
        try:
            if action == CB.REFERRAL:
                stats = await DB.get_referral_stats(user_id)
                code = await DB.get_referral_code(user_id)
                if code.startswith('ref_'):
                    code = code[4:]
                link = f"https://t.me/{CONFIG.BOT_USERNAME}?start=ref_{code}"

                referral_title = await _trans('referral_title', lang, "🔗 نظام الإحالات")
                referral_link_label = await _trans('referral_link_label', lang, "📎 رابطك:")
                referral_referred = await _trans('referral_referred', lang, "👥 المُحالين:")
                referral_available = await _trans('referral_available', lang, "🎁 الأيام المتاحة:")
                days_suffix = await _trans('days_suffix', lang, "يوم")

                text = (
                    f"{referral_title}\n\n"
                    f"{referral_link_label}\n{link}\n\n"
                    f"{referral_referred} {stats['total']}\n"
                    f"{referral_available} {stats['available']} {days_suffix}"
                )

                ref_claim_btn = KeyboardFactory.get_text("ref_claim", lang)
                ref_list_btn = KeyboardFactory.get_text("ref_list", lang)
                back_btn = KeyboardFactory.get_text("back", lang)

                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(ref_claim_btn, callback_data=CB.REF_CLAIM),
                     InlineKeyboardButton(ref_list_btn, callback_data=CB.REF_LIST)],
                    [InlineKeyboardButton(back_btn, callback_data=CB.BACK)]
                ])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                
            elif action == CB.REF_CLAIM:
                days = await DB.claim_referral_reward(user_id)
                if days > 0:
                    text = await _trans('referral_claimed', lang, "✅ تم صرف {days} يوم!")
                    try:
                        text = text.format(days=days)
                    except:
                        text = f"✅ تم صرف {days} يوم!"
                else:
                    text = await _trans('no_rewards', lang, "📭 لا توجد مكافآت")
                
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.REFERRAL)]])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                
            elif action == CB.REF_LIST:
                refs = await DB.get_referrals_list(user_id)
                if refs:
                    text = await _trans('referrals_list', lang, "📋 المُحالين") + "\n\n"
                    for i, r in enumerate(refs[:20], 1):
                        text += f"{i}. {_mask_id(r)}\n"
                else:
                    text = await _trans('none', lang, "📭 لا يوجد")
                
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.REFERRAL)]])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في معالجة الإحالات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات التذكيرات ============
    @staticmethod
    async def _handle_reminders(update, context, query, user_id, lang, action):
        """معالجة أزرار التذكيرات"""
        try:
            settings = await DB.get_reminder_settings(user_id) or {}
            
            if action == CB.REM_TOGGLE_SUB:
                new_val = not settings.get('subscription_reminder', False)
                settings['subscription_reminder'] = new_val
                await DB.update_reminder_settings(user_id, subscription_reminder=new_val)
                status = "✅" if new_val else "❌"
                await _safe_answer(query, f"🔔 تذكير الاشتراك: {status}")
                
            elif action == CB.REM_TOGGLE_DAILY:
                new_val = not settings.get('daily_stats_reminder', False)
                settings['daily_stats_reminder'] = new_val
                await DB.update_reminder_settings(user_id, daily_stats_reminder=new_val)
                status = "✅" if new_val else "❌"
                await _safe_answer(query, f"📊 التذكير اليومي: {status}")
                
            elif action == CB.REM_TOGGLE_WEEKLY:
                new_val = not settings.get('weekly_report', False)
                settings['weekly_report'] = new_val
                await DB.update_reminder_settings(user_id, weekly_report=new_val)
                status = "✅" if new_val else "❌"
                await _safe_answer(query, f"📈 التقرير الأسبوعي: {status}")
                
            elif action == CB.REM_SET_DAYS:
                StateManager.set(user_id, UserState.WAIT_REM_DAYS)
                await safe_edit(query, await _trans('send_days', lang, "📅 أرسل عدد الأيام (1-30):"), bot=context.bot)
                return

            # عرض الإعدادات المحدثة
            reminder_title = await _trans('reminder_title', lang, "⏰ التذكيرات")
            rem_sub_label = await _trans('rem_sub_label', lang, "🔔 الاشتراك")
            rem_daily_label = await _trans('rem_daily_label', lang, "📊 يومي")
            rem_weekly_label = await _trans('rem_weekly_label', lang, "📈 أسبوعي")

            text = (
                f"{reminder_title}\n\n"
                f"{rem_sub_label}: {'✅' if settings.get('subscription_reminder') else '❌'}\n"
                f"{rem_daily_label}: {'✅' if settings.get('daily_stats_reminder') else '❌'}\n"
                f"{rem_weekly_label}: {'✅' if settings.get('weekly_report') else '❌'}"
            )
            await safe_edit(query, text, reply_markup=KeyboardFactory.build("reminder", lang=lang), bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في معالجة التذكيرات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات الترجمة ============
    @staticmethod
    async def _show_translation_menu(update, context, query, user_id, lang):
        """عرض قائمة الترجمة"""
        try:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"),
                 InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
                [InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr"),
                 InlineKeyboardButton("🇹🇷 Türkçe", callback_data="lang_tr")],
                [InlineKeyboardButton("🇨🇳 中文", callback_data="lang_zh"),
                 InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")],
                [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de"),
                 InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es")],
                [InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it"),
                 InlineKeyboardButton("🇵🇹 Português", callback_data="lang_pt")],
                [InlineKeyboardButton("🇯🇵 日本語", callback_data="lang_ja"),
                 InlineKeyboardButton("🇰🇷 한국어", callback_data="lang_ko")],
                [InlineKeyboardButton("🇮🇷 فارسی", callback_data="lang_fa"),
                 InlineKeyboardButton("🇵🇰 اردو", callback_data="lang_ur")],
                [InlineKeyboardButton(await _trans('disable_translation', lang, "❌ إيقاف الترجمة"), callback_data=CB.TRANS_OFF)],
                [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.BACK)]
            ])
            await safe_edit(query, await _trans('choose_language', lang, "🌐 اختر اللغة:"), reply_markup=kb, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض قائمة الترجمة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_language_change(update, context, query, user_id, data):
        """معالجة تغيير اللغة"""
        try:
            lang_set = data.split("_")[-1]
            supported_langs = {'ar', 'en', 'fr', 'tr', 'zh', 'ru', 'de', 'es', 'it', 'pt', 'ja', 'ko', 'fa', 'ur', 'nl', 'pl', 'hi', 'off'}
            
            if lang_set in supported_langs:
                await DB.set_user_language(user_id, lang_set)
                context.user_data['lang'] = lang_set if lang_set != 'off' else 'ar'
                await _safe_answer(query, f"✅ تم تغيير اللغة إلى {lang_set}")
                await CommandHandlers.start(update, context)
            else:
                await _safe_answer(query, await _trans('unsupported_language', 'ar', "❌ لغة غير مدعومة"), show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في تغيير اللغة: {e}", exc_info=True)
            await _safe_answer(query, "❌ حدث خطأ", show_alert=True)

    # ============ معالجات المسابقات ============
    @staticmethod
    async def _show_contest_winners(update, context, query, user_id, lang):
        """عرض الفائزين في المسابقات"""
        try:
            winners = await DB.get_contest_winners(10)
            if winners:
                text = await _trans('contest_winners_title', lang, "🏆 الفائزون") + "\n\n"
                for w in winners:
                    text += f"• {w['title']} - {_mask_id(w['winner_id'])}\n"
            else:
                text = await _trans('none', lang, "📭 لا يوجد")
            
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.BACK)]])
            await safe_edit(query, text, reply_markup=kb, bot=context.bot)
            StateManager.clear(user_id)
        except Exception as e:
            logger.error(f"خطأ في عرض الفائزين: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات القنوات ============
    @staticmethod
    async def _handle_add_channel(update, context, query, user_id, lang):
        """معالجة إضافة قناة"""
        try:
            if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                await _safe_answer(query, await _trans('requires_subscription', lang, "❌ يتطلب اشتراك نشط"), show_alert=True)
                return
            
            StateManager.set(user_id, UserState.WAIT_CHANNEL)
            await safe_edit(query, await _trans('send_channel_id', lang, "📡 أرسل معرف القناة:"), bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في إضافة قناة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_select_channel(update, context, query, user_id, lang, data):
        """معالجة اختيار قناة"""
        try:
            try:
                ch_id = int(data.split(":")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            if not await _is_channel_owner(user_id, ch_id):
                await _safe_answer(query, await _trans('cannot_select_channel', lang, "❌ لا يمكنك تحديد هذه القناة"), show_alert=True)
                return
            
            if await DB.set_active_channel(user_id, ch_id):
                await safe_edit(query, await _trans('channel_selected', lang, "✅ تم تحديد القناة!"), bot=context.bot)
            else:
                await _safe_answer(query, await _trans('cannot_select_channel', lang, "❌ لا يمكنك تحديد هذه القناة"), show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في اختيار القناة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_delete_channel(update, context, query, user_id, lang, data):
        """معالجة حذف قناة"""
        try:
            try:
                ch_id = int(data.split(":")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            if not await _is_channel_owner(user_id, ch_id):
                await _safe_answer(query, await _trans('not_channel_owner', lang, "❌ لا تملك هذه القناة"), show_alert=True)
                return
            
            if await DB.delete_channel(user_id, ch_id):
                await _safe_answer(query, await _trans('deleted_success', lang, "✅ تم الحذف"))
                context.user_data['channel_page'] = 0
                await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
            else:
                await _safe_answer(query, await _trans('failed', lang, "❌ فشل"), show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في حذف القناة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_channel_stats(update, context, query, user_id, lang, data):
        """معالجة إحصائيات القناة"""
        try:
            try:
                ch_id = int(data.split(":")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            if not await _is_channel_owner(user_id, ch_id):
                await _safe_answer(query, await _trans('not_channel_owner', lang, "❌ لا تملك هذه القناة"), show_alert=True)
                return
            
            stats = await DB.get_channel_stats(user_id, ch_id)
            stats_title = await _trans('channel_stats', lang, "📊 إحصائيات")
            total_label = await _trans('total', lang, "📝")
            published_label = await _trans('published', lang, "✅")
            unpublished_label = await _trans('unpublished', lang, "⏳")
            
            text = f"{stats_title}\n\n{total_label} {stats['total']}\n{published_label} {stats['published']}\n{unpublished_label} {stats['unpublished']}"
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(await _trans('detailed_stats', lang, "📈 إحصائيات تفصيلية"), callback_data=f"{CB.CH_STATS_DETAILED}:{ch_id}")],
                [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.CH_LIST)]
            ])
            await safe_edit(query, text, reply_markup=kb, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض إحصائيات القناة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _show_channel_detailed_stats(update, context, query, user_id, lang, data):
        """عرض إحصائيات تفصيلية للقناة"""
        try:
            try:
                ch_id = int(data.split(":")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            if not await _is_channel_owner(user_id, ch_id):
                await _safe_answer(query, await _trans('not_channel_owner', lang, "❌ لا تملك هذه القناة"), show_alert=True)
                return
            
            stats = await DB.get_channel_detailed_stats(user_id, ch_id)
            
            if not stats:
                await safe_edit(query, await _trans('no_stats', lang, "📭 لا توجد إحصائيات"), bot=context.bot)
                return
            
            text = await _trans('detailed_stats', lang, "📊 إحصائيات تفصيلية") + "\n\n"
            text += f"📝 {await _trans('total_posts', lang, 'إجمالي المنشورات')}: {stats['total_posts']}\n"
            text += f"✅ {await _trans('published', lang, 'المنشورة')}: {stats['published_posts']}\n"
            text += f"❌ {await _trans('failed', lang, 'الفاشلة')}: {stats['failed_posts']}\n"
            text += f"📈 {await _trans('success_rate', lang, 'نسبة النجاح')}: {stats['success_rate']:.1f}%\n"
            text += f"🕐 {await _trans('last_publish', lang, 'آخر نشر')}: {stats['last_publish_time'] or await _trans('never', lang, 'لم يتم')}\n"
            text += f"⏱️ {await _trans('avg_interval', lang, 'متوسط الفاصل')}: {stats['avg_interval']} {await _trans('minutes', lang, 'دقيقة')}\n"
            text += f"🔥 {await _trans('best_time', lang, 'أفضل وقت')}: {stats['best_hour']}:00\n"
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"{CB.CH_STATS}:{ch_id}")]
            ])
            await safe_edit(query, text, reply_markup=kb, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض الإحصائيات التفصيلية: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات المنشورات ============
    @staticmethod
    async def _handle_add_post(update, context, query, user_id, lang):
        """معالجة إضافة منشور"""
        try:
            if not await DB.has_active_subscription(user_id) and user_id != CONFIG.PRIMARY_OWNER_ID:
                await _safe_answer(query, await _trans('subscription_expired', lang, "❌ انتهى اشتراكك!"), show_alert=True)
                return
            
            active = await DB.get_active_channel(user_id)
            if not active:
                await safe_edit(query, await _trans('no_active_channel', lang, "❌ لا توجد قناة نشطة"), bot=context.bot)
                return
            
            StateManager.set(user_id, UserState.ADDING_POSTS)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('finish', lang, "✅ إنهاء"), callback_data="finish_posts")]])
            await safe_edit(query, await _trans('send_posts', lang, "📥 أرسل المنشورات:"), reply_markup=kb, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في إضافة منشور: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_finish_posts(update, context, query, user_id, lang):
        """معالجة إنهاء إضافة المنشورات"""
        try:
            StateManager.clear(user_id)
            
            active = await DB.get_active_channel(user_id)
            if active:
                count = await DB.fetchval("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (active,), default=0)
                await safe_edit(query, f"✅ تم إضافة {count} منشور", bot=context.bot)
            else:
                await _safe_answer(query, await _trans('finished', lang, "✅ تم الإنهاء"))
        except Exception as e:
            logger.error(f"خطأ في إنهاء إضافة المنشورات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_publish_post(update, context, query, user_id, lang):
        """معالجة نشر منشور"""
        try:
            active = await DB.get_active_channel(user_id)
            if not active:
                await safe_edit(query, await _trans('no_channel', lang, "❌ لا توجد قناة"), bot=context.bot)
                return
            
            if not await _is_channel_owner(user_id, active):
                await _safe_answer(query, await _trans('not_channel_owner', lang, "❌ لا تملك هذه القناة"), show_alert=True)
                return
            
            post = await DB.get_next_post(active)
            if not post:
                await safe_edit(query, await _trans('no_posts', lang, "📭 لا توجد منشورات"), bot=context.bot)
                return
            
            ch_info = await DB.get_channel_info(user_id, active)
            if ch_info:
                asyncio.create_task(CallbackHandlers._publish_single(context.bot, active, ch_info['channel_id'], post))
                await _safe_answer(query, await _trans('publish_started', lang, "✅ بدأ النشر"))
        except Exception as e:
            logger.error(f"خطأ في نشر منشور: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_recycle_posts(update, context, query, user_id, lang):
        """معالجة إعادة تدوير المنشورات"""
        try:
            active = await DB.get_active_channel(user_id)
            if not active:
                await _safe_answer(query, await _trans('no_active_channel', lang, "❌ لا توجد قناة نشطة"), show_alert=True)
                return
            
            if not await _is_channel_owner(user_id, active):
                await _safe_answer(query, await _trans('not_channel_owner', lang, "❌ لا تملك هذه القناة"), show_alert=True)
                return
            
            count = await DB.reset_posts(user_id, active)
            text = await _trans('posts_recycled', lang, "♻️ {count} منشور!")
            try:
                text = text.format(count=count)
            except:
                text = f"♻️ {count} منشور!"
            await safe_edit(query, text, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في إعادة تدوير المنشورات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_delete_post(update, context, query, user_id, lang, data):
        """معالجة حذف منشور"""
        try:
            try:
                post_id = int(data.split(":")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            active = await DB.get_active_channel(user_id)
            if not active:
                await _safe_answer(query, await _trans('no_active_channel', lang, "❌ لا توجد قناة نشطة"), show_alert=True)
                return
            
            if not await _is_channel_owner(user_id, active):
                await _safe_answer(query, await _trans('not_channel_owner', lang, "❌ لا تملك هذه القناة"), show_alert=True)
                return
            
            if await DB.delete_post(user_id, post_id, active):
                await _safe_answer(query, await _trans('deleted_success', lang, "✅ تم الحذف"))
                await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
            else:
                await _safe_answer(query, await _trans('failed', lang, "❌ فشل"), show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في حذف منشور: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_clear_posts(update, context, query, user_id, lang):
        """معالجة مسح جميع المنشورات"""
        try:
            active = await DB.get_active_channel(user_id)
            if not active:
                await _safe_answer(query, await _trans('no_active_channel', lang, "❌ لا توجد قناة نشطة"), show_alert=True)
                return
            
            if not await _is_channel_owner(user_id, active):
                await _safe_answer(query, await _trans('not_channel_owner', lang, "❌ لا تملك هذه القناة"), show_alert=True)
                return
            
            await DB.execute("DELETE FROM posts WHERE channel_db_id=?", (active,))
            await safe_edit(query, await _trans('posts_cleared', lang, "✅ تم مسح جميع المنشورات"), bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في مسح المنشورات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_publish_all(update, context, query, user_id, lang):
        """معالجة النشر الجماعي"""
        try:
            channels = await DB.get_user_channels(user_id)
            if not channels:
                await safe_edit(query, await _trans('no_channels', lang, "❌ لا توجد قنوات"), bot=context.bot)
                return
            
            task = asyncio.create_task(CallbackHandlers._publish_all(context.bot, user_id, channels))
            ACTIVE_TASKS.add(task)
            task.add_done_callback(ACTIVE_TASKS.discard)
            await _safe_answer(query, await _trans('mass_publish_started', lang, "✅ بدأ النشر الجماعي"))
        except Exception as e:
            logger.error(f"خطأ في النشر الجماعي: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات المجموعات ============
    @staticmethod
    async def _show_groups(update, context, query, user_id, lang):
        """عرض مجموعات المستخدم"""
        try:
            groups = await DB.get_user_groups(user_id)
            if not groups:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('add_bot', lang, "➕ أضف البوت"), url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")]])
                await safe_edit(query, await _trans('no_groups', lang, "📭 لا توجد مجموعات"), reply_markup=kb, bot=context.bot)
                return
            
            text = await _trans('my_groups', lang, "👥 مجموعاتي") + "\n\n"
            kb = []
            for g in groups:
                status = "⛔" if g['banned'] else "✅"
                text += f"{status} {g['chat_name']}\n"
                
                settings_btn = await _trans('security_settings', lang, "⚙️ أمان")
                delete_btn = await _trans('delete', lang, "🗑️ حذف")
                
                kb.append([InlineKeyboardButton(f"{settings_btn} {g['chat_name'][:15]}", callback_data=f"{CB.GRP_SET}:{g['chat_id']}")])
                kb.append([InlineKeyboardButton(delete_btn, callback_data=f"grp_del:{g['chat_id']}")])
            
            kb.append([InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.BACK)])
            await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض المجموعات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_delete_group(update, context, query, user_id, lang, data):
        """معالجة حذف مجموعة"""
        try:
            try:
                chat_id = int(data.split(":")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            is_owner = await _is_group_owner(user_id, chat_id)
            is_admin = await is_authorized_in_group(context.bot, chat_id, user_id)
            
            if not is_owner and not is_admin:
                logger.warning(f"🚫 محاولة حذف مجموعة بدون صلاحية: user={user_id}, chat={chat_id}")
                await _safe_answer(query, await _trans('no_permission', lang, "❌ لا صلاحية"), show_alert=True)
                return
            
            if await DB.delete_group(user_id, chat_id):
                await safe_edit(query, await _trans('group_deleted', lang, "✅ تم حذف المجموعة"), bot=context.bot)
            else:
                await _safe_answer(query, await _trans('failed', lang, "❌ فشل"), show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في حذف المجموعة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_group_settings(update, context, query, user_id, lang, data):
        """معالجة إعدادات المجموعة"""
        try:
            try:
                chat_id = int(data.split(":")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            if not await is_authorized_in_group(context.bot, chat_id, user_id):
                logger.warning(f"🚫 محاولة وصول غير مصرح: user={user_id}, chat={chat_id}")
                await _safe_answer(query, await _trans('no_permission', lang, "❌ لا صلاحية"), show_alert=True)
                return
            
            context.user_data['security_chat_id'] = chat_id
            settings = await DB.get_security_settings(chat_id)
            await safe_edit(query, KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id=chat_id, lang=lang), bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في إعدادات المجموعة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ دوال النشر ============
    @staticmethod
    async def _publish_single(bot, ch_db_id, ch_tele, post) -> bool:
        """نشر منشور واحد"""
        try:
            post_id = post.get('id')
            text = post.get('text', '')
            media_type = post.get('media_type')
            media_file_id = post.get('media_file_id')
            caption = text[:MAX_CAPTION_LENGTH] if text else None

            if media_type == 'photo' and media_file_id:
                await bot.send_photo(ch_tele, media_file_id, caption=caption)
            elif media_type == 'video' and media_file_id:
                await bot.send_video(ch_tele, media_file_id, caption=caption)
            elif media_type == 'document' and media_file_id:
                await bot.send_document(ch_tele, media_file_id, caption=caption)
            elif media_type == 'audio' and media_file_id:
                await bot.send_audio(ch_tele, media_file_id, caption=caption)
            elif media_type == 'voice' and media_file_id:
                await bot.send_voice(ch_tele, media_file_id)
                if text:
                    try:
                        await bot.send_message(ch_tele, text)
                    except Exception as e:
                        logger.warning(f"فشل إرسال النص المصاحب للصوت: {e}")
            elif media_type == 'animation' and media_file_id:
                await bot.send_animation(ch_tele, media_file_id, caption=caption)
            elif media_type == 'sticker' and media_file_id:
                await bot.send_sticker(ch_tele, media_file_id)
                if text:
                    try:
                        await bot.send_message(ch_tele, text)
                    except Exception as e:
                        logger.warning(f"فشل إرسال النص المصاحب للملصق: {e}")
            elif media_type == 'video_note' and media_file_id:
                await bot.send_video_note(ch_tele, media_file_id)
                if text:
                    try:
                        await bot.send_message(ch_tele, text)
                    except Exception as e:
                        logger.warning(f"فشل إرسال النص المصاحب لفيديو نوت: {e}")
            else:
                if text and len(text) > MAX_MESSAGE_LENGTH:
                    for i in range(0, len(text), MAX_MESSAGE_LENGTH):
                        await bot.send_message(ch_tele, text[i:i+MAX_MESSAGE_LENGTH])
                else:
                    await bot.send_message(ch_tele, text if text else ".")

            if post_id:
                await DB.mark_post_published(post_id)
            await DB.update_last_publish(ch_db_id)
            await DB.update_next_publish(ch_db_id)
            return True
            
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            if post.get('id'):
                await DB.increment_post_fail(post['id'])
            return False
        except Forbidden as e:
            await DB.execute("UPDATE user_channels SET banned=1 WHERE id=?", (ch_db_id,))
            if post.get('id'):
                await DB.increment_post_fail(post['id'])
            return False
        except Exception as e:
            logger.error(f"❌ فشل النشر: {e}")
            if post.get('id'):
                await DB.increment_post_fail(post['id'])
            return False

    @staticmethod
    async def _publish_all(bot, user_id, channels):
        """النشر الجماعي لجميع القنوات"""
        published = 0
        failed = 0
        tasks = []
        banned_count = 0
        no_post_count = 0
        
        for ch in channels:
            if ch.get('banned'):
                banned_count += 1
                continue
            post = await DB.get_next_post(ch['id'])
            if post:
                ch_info = await DB.get_channel_info(user_id, ch['id'])
                if ch_info:
                    tasks.append((ch['id'], ch_info['channel_id'], post))
            else:
                no_post_count += 1
        
        if not tasks:
            if banned_count == len(channels):
                msg = "❌ جميع القنوات محظورة"
            elif no_post_count == len(channels) - banned_count:
                msg = "📭 لا توجد منشورات للنشر"
            else:
                msg = "📭 لا توجد منشورات صالحة للنشر"
            await safe_send(bot, user_id, msg)
            return
        
        sem = asyncio.Semaphore(MAX_CONCURRENT_PUBLISH)

        async def run(task):
            async with sem:
                return await CallbackHandlers._publish_single(bot, task[0], task[1], task[2])

        BATCH = 10
        for i in range(0, len(tasks), BATCH):
            batch = tasks[i:i+BATCH]
            results = await asyncio.gather(*(run(t) for t in batch), return_exceptions=True)
            for r in results:
                if r is True:
                    published += 1
                else:
                    failed += 1
        
        await safe_send(bot, user_id, f"✅ تم نشر {published} | ❌ فشل {failed}")

    # ============ دوال عرض القوائم ============
    @staticmethod
    async def _show_channel_list(update, context, query, user_id, lang=None):
        """عرض قائمة القنوات"""
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        
        try:
            channels = await DB.get_user_channels(user_id)
            if not channels:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)],
                    [InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)]
                ])
                await safe_edit(query, await _trans('no_channels', lang, "📭 لا توجد قنوات!"), reply_markup=kb, bot=context.bot)
                return
            
            page = int(context.user_data.get('channel_page', 0))
            per_page = MAX_PAGE_SIZE
            total_pages = max(1, (len(channels) + per_page - 1) // per_page)
            
            if page >= total_pages:
                page = total_pages - 1
            if page < 0:
                page = 0
            
            context.user_data['channel_page'] = page
            page_channels = channels[page*per_page:(page+1)*per_page]
            
            text = await _trans('my_channels_page', lang, "📡 قنواتي (صفحة {page}/{total})").format(page=page+1, total=total_pages) + "\n\n"
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
            
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("⬅️ السابق", callback_data="ch_page_prev"))
            if page < total_pages - 1:
                nav.append(InlineKeyboardButton("التالي ➡️", callback_data="ch_page_next"))
            if nav:
                kb.append(nav)
            
            kb.append([InlineKeyboardButton(KeyboardFactory.get_text("ch_add", lang), callback_data=CB.CH_ADD)])
            kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])
            
            await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض قائمة القنوات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _show_post_list(update, context, query, user_id, lang=None):
        """عرض قائمة المنشورات"""
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        
        try:
            active = await DB.get_active_channel(user_id)
            if not active:
                await safe_edit(query, await _trans('no_active_channel', lang, "❌ لا توجد قناة نشطة"), bot=context.bot)
                return
            
            per_page = MAX_PAGE_SIZE
            total = await DB.fetchval("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (active,), default=0)
            total_pages = max(1, (total + per_page - 1) // per_page)
            
            page = int(context.user_data.get('post_page', 0))
            
            if page >= total_pages:
                page = total_pages - 1
            if page < 0:
                page = 0
            
            context.user_data['post_page'] = page
            
            posts = await DB.fetchall(
                "SELECT id, text, published FROM posts WHERE channel_db_id=? ORDER BY created_at ASC LIMIT ? OFFSET ?",
                (active, per_page, page * per_page)
            )
            
            if not posts:
                text = await _trans('no_posts', lang, "📭 لا يوجد منشورات")
            else:
                text = await _trans('my_posts_page', lang, "📋 منشوراتي (صفحة {page}/{total})").format(page=page+1, total=total_pages) + "\n\n"
                kb = []
                
                for p in posts:
                    status = "✅" if p['published'] else "⏳"
                    text += f"{status} 🆔 {p['id']}: {(p['text'] or '')[:30]}\n"
                    kb.append([InlineKeyboardButton(await _trans('delete_post', lang, "🗑️ حذف") + f" {p['id']}", callback_data=f"{CB.POST_DEL}:{p['id']}")])
                
                nav = []
                if page > 0:
                    nav.append(InlineKeyboardButton("⬅️ السابق", callback_data="post_page_prev"))
                if page < total_pages - 1:
                    nav.append(InlineKeyboardButton("التالي ➡️", callback_data="post_page_next"))
                if nav:
                    kb.append(nav)
                
                kb.append([InlineKeyboardButton(await _trans('recycle', lang, "🔄 إعادة تدوير"), callback_data=CB.POST_REC)])
                kb.append([InlineKeyboardButton(await _trans('clear_all', lang, "🧹 مسح الكل"), callback_data=CB.POST_CLEAR)])
                kb.append([InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.BACK)])
                
                await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض قائمة المنشورات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات ترقيم الصفحات ============
    @staticmethod
    async def _handle_channel_pagination(update, context, query, user_id, lang, data):
        """معالجة ترقيم صفحات القنوات"""
        try:
            channels = await DB.get_user_channels(user_id)
            per_page = MAX_PAGE_SIZE
            total_pages = max(1, (len(channels) + per_page - 1) // per_page)
            current_page = int(context.user_data.get('channel_page', 0))
            
            if data == "ch_page_prev":
                context.user_data['channel_page'] = max(0, current_page - 1)
            elif data == "ch_page_next":
                context.user_data['channel_page'] = min(total_pages - 1, current_page + 1)
            
            await CallbackHandlers._show_channel_list(update, context, query, user_id, lang)
        except Exception as e:
            logger.error(f"خطأ في ترقيم صفحات القنوات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_post_pagination(update, context, query, user_id, lang, data):
        """معالجة ترقيم صفحات المنشورات"""
        try:
            active = await DB.get_active_channel(user_id)
            if not active:
                return
            
            per_page = MAX_PAGE_SIZE
            total = await DB.fetchval("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (active,), default=0)
            total_pages = max(1, (total + per_page - 1) // per_page)
            current_page = int(context.user_data.get('post_page', 0))
            
            if data == "post_page_prev":
                context.user_data['post_page'] = max(0, current_page - 1)
            elif data == "post_page_next":
                context.user_data['post_page'] = min(total_pages - 1, current_page + 1)
            
            await CallbackHandlers._show_post_list(update, context, query, user_id, lang)
        except Exception as e:
            logger.error(f"خطأ في ترقيم صفحات المنشورات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات المدة والعقوبات ============
    @staticmethod
    async def _handle_set_duration(update, context, query, user_id, lang, data):
        """معالجة تعيين مدة العقوبة"""
        try:
            parts_data = data.split(":")
            if len(parts_data) < 4:
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            try:
                penalty_type = parts_data[1]
                chat_id = int(parts_data[2])
                duration = int(parts_data[3])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            if not await is_authorized_in_group(context.bot, chat_id, user_id):
                await _safe_answer(query, await _trans('no_permission', lang, "❌ لا صلاحية"), show_alert=True)
                return
            
            if penalty_type == 'kick':
                context_penalty = context.user_data.get('penalty_type', 'mute')
                if context_penalty == 'warn_penalty':
                    await DB.update_security_settings(chat_id, warn_penalty='kick')
                    await _safe_answer(query, await _trans('warn_penalty_set', lang, "✅ تم تعيين عقوبة التحذير: طرد"))
                else:
                    await DB.update_security_settings(chat_id, auto_penalty='kick')
                    await _safe_answer(query, await _trans('penalty_set', lang, "✅ تم تعيين العقوبة: طرد"))
                
                settings = await DB.get_security_settings(chat_id)
                await safe_edit(query, KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id=chat_id, lang=lang), bot=context.bot)
                return
            
            if penalty_type not in PENALTY_COLUMN_MAP:
                await _safe_answer(query, await _trans('invalid_penalty_type', lang, "❌ نوع عقوبة غير صالح"), show_alert=True)
                return
            
            col = PENALTY_COLUMN_MAP[penalty_type]
            await DB.update_security_settings(chat_id, **{col: duration})
            
            text = await _trans('duration_set', lang, "✅ تم تعيين المدة: {duration} ثانية")
            try:
                text = text.format(duration=duration)
            except:
                text = f"✅ تم تعيين المدة: {duration} ثانية"
            
            await _safe_answer(query, text)
            settings = await DB.get_security_settings(chat_id)
            await safe_edit(query, KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id=chat_id, lang=lang), bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في تعيين المدة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_sec_penalty(update, context, query, user_id, lang, data):
        """معالجة تعيين نوع العقوبة"""
        try:
            try:
                prefix, chat_id_str = data.split(":", 1)
                penalty_type = prefix.replace("sec_penalty_", "")
                chat_id = int(chat_id_str)
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            if penalty_type not in VALID_PENALTY_TYPES:
                logger.warning(f"⚠️ محاولة استخدام نوع عقوبة غير صالح: {penalty_type}")
                await _safe_answer(query, await _trans('invalid_penalty_type', lang, "❌ نوع عقوبة غير صالح"), show_alert=True)
                return
            
            if not await is_authorized_in_group(context.bot, chat_id, user_id):
                await _safe_answer(query, await _trans('no_permission', lang, "❌ لا صلاحية"), show_alert=True)
                return
            
            if penalty_type == 'none':
                await DB.update_security_settings(chat_id, auto_penalty='none')
                await _safe_answer(query, await _trans('no_penalty', lang, "🚫 بدون عقوبة"))
            elif penalty_type == 'kick':
                await DB.update_security_settings(chat_id, auto_penalty='kick')
                await _safe_answer(query, await _trans('penalty_set', lang, "✅ تم تعيين العقوبة: طرد"))
                settings = await DB.get_security_settings(chat_id)
                await safe_edit(query, KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id=chat_id, lang=lang), bot=context.bot)
            else:
                context.user_data['penalty_type'] = penalty_type
                await CallbackHandlers._show_penalty_durations(update, context, query, chat_id, lang, penalty_type)
        except Exception as e:
            logger.error(f"خطأ في تعيين نوع العقوبة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات الأمان ============
    @staticmethod
    async def _handle_security(update, context, query, user_id, lang=None, return_to_main=False):
        """معالجة أزرار الأمان"""
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        
        data = query.data
        parts = data.split(":")
        
        if len(parts) < 2 or not parts[1].lstrip('-').isdigit():
            logger.error(f"❌ محاولة وصول بدون chat_id: {data}")
            await _safe_answer(query, await _trans('group_not_specified', lang, "❌ لم يتم تحديد المجموعة"), show_alert=True)
            return
        
        try:
            chat_id = int(parts[1])
        except (ValueError, IndexError):
            await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
            return
        
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            logger.warning(f"🚫 محاولة وصول غير مصرح: user={user_id}, chat={chat_id}, action={data}")
            await _safe_answer(query, await _trans('no_permission', lang, "❌ لا صلاحية"), show_alert=True)
            return
        
        action = parts[0].replace("sec_", "")
        
        try:
            if action.startswith("penalty_"):
                penalty_type = action.replace("penalty_", "")
                if penalty_type in VALID_PENALTY_TYPES:
                    if penalty_type == 'none':
                        await DB.update_security_settings(chat_id, auto_penalty='none')
                        await _safe_answer(query, await _trans('no_penalty', lang, "🚫 بدون عقوبة"))
                    elif penalty_type == 'kick':
                        await DB.update_security_settings(chat_id, auto_penalty='kick')
                        await _safe_answer(query, await _trans('penalty_set', lang, "✅ تم تعيين العقوبة: طرد"))
                        settings = await DB.get_security_settings(chat_id)
                        await safe_edit(query, KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id=chat_id, lang=lang), bot=context.bot)
                    else:
                        await DB.update_security_settings(chat_id, auto_penalty=penalty_type)
                        await _safe_answer(query, await _trans('penalty_set_type', lang, "✅ تم تعيين العقوبة: {type}").format(type=penalty_type))
                    return
            
            if action == "banned_words":
                await CallbackHandlers._show_banned_words_menu(update, context, query, chat_id, lang)
                return
            
            if action == "toggle_banned_words":
                settings = await DB.get_security_settings(chat_id)
                new_val = 1 - settings.get('delete_banned_words', 0)
                await DB.update_security_settings(chat_id, delete_banned_words=new_val)
                settings['delete_banned_words'] = new_val
                await CallbackHandlers._show_banned_words_menu(update, context, query, chat_id, lang)
                return
            
            if action == "warn":
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(await _trans('toggle', lang, "✅ تفعيل/تعطيل"), callback_data=f"sec_warn_toggle:{chat_id}")],
                    [InlineKeyboardButton(await _trans('warn_count', lang, "🔢 عدد التحذيرات"), callback_data=f"sec_warn_count:{chat_id}")],
                    [InlineKeyboardButton(await _trans('warn_penalty', lang, "⚖️ عقوبة التحذير"), callback_data=f"sec_warn_penalty:{chat_id}")],
                    [InlineKeyboardButton(await _trans('penalty_duration', lang, "⏱️ مدة العقوبة"), callback_data=f"sec_warn_penalty_duration:{chat_id}")],
                    [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"grp_set:{chat_id}")]
                ])
                await safe_edit(query, await _trans('manage_warnings', lang, "⚠️ إدارة التحذيرات:"), reply_markup=kb, bot=context.bot)
                await _safe_answer(query)
                return
            
            if action in SECURITY_TOGGLE_MAP:
                col = SECURITY_TOGGLE_MAP[action]
                settings = await DB.get_security_settings(chat_id)
                new_val = 1 - settings.get(col, 0)
                update_data = {col: new_val}
                
                if action == "approve_join" and new_val:
                    update_data['auto_reject_join'] = 0
                elif action == "reject_join" and new_val:
                    update_data['auto_approve_join'] = 0
                
                await DB.update_security_settings(chat_id, **update_data)
                settings[col] = new_val
                
                if action == "approve_join" and new_val:
                    settings['auto_reject_join'] = 0
                elif action == "reject_join" and new_val:
                    settings['auto_approve_join'] = 0
                
                await safe_edit(query, KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id=chat_id, lang=lang), bot=context.bot)
                return
            
            if action == "enable_all":
                settings = await DB.get_security_settings(chat_id)
                update_data = {k: 1 for k in SECURITY_TOGGLE_MAP.values() if k not in ['auto_approve_join', 'auto_reject_join']}
                update_data['auto_approve_join'] = 1
                update_data['auto_reject_join'] = 0
                update_data['warn_enabled'] = 1
                await DB.update_security_settings(chat_id, **update_data)
                settings.update(update_data)
                await safe_edit(query, KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id=chat_id, lang=lang), bot=context.bot)
                return
            
            if action == "disable_all":
                update_data = {k: 0 for k in SECURITY_TOGGLE_MAP.values()}
                update_data['warn_enabled'] = 0
                await DB.update_security_settings(chat_id, **update_data)
                settings = await DB.get_security_settings(chat_id)
                await safe_edit(query, KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id=chat_id, lang=lang), bot=context.bot)
                return
            
            if action == "warn_toggle":
                settings = await DB.get_security_settings(chat_id)
                new_val = 1 - settings.get('warn_enabled', 0)
                await DB.update_security_settings(chat_id, warn_enabled=new_val)
                settings['warn_enabled'] = new_val
                await safe_edit(query, KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id=chat_id, lang=lang), bot=context.bot)
                return
            
            if action == "warn_count":
                StateManager.set(user_id, UserState.WAIT_WARN_COUNT)
                context.user_data['sec_chat'] = chat_id
                await safe_edit(query, await _trans('send_warn_count', lang, "🔢 أرسل عدد التحذيرات (1-10):"), bot=context.bot)
                return
            
            if action == "warn_penalty":
                await CallbackHandlers._show_warn_penalty_types(update, context, query, chat_id, lang)
                return
            
            if action == "adv_act":
                await CallbackHandlers._show_advanced_actions(update, context, query, chat_id, lang)
                return
            
            if action == "act_log":
                await CallbackHandlers._show_admin_logs(update, context, query, chat_id, lang)
                StateManager.clear(user_id)
                return
            
            if action == "restrict_settings":
                await CallbackHandlers._show_restrict_settings(update, context, query, chat_id, lang)
                return
            
            if action == "restrict_toggle":
                if len(parts) < 4:
                    await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                    return
                
                restrict_type = parts[2]
                chat_id = int(parts[3])
                
                col_map = {
                    'send_messages': 'restrict_send_messages',
                    'send_media': 'restrict_send_media',
                    'send_links': 'restrict_send_links',
                    'send_stickers': 'restrict_send_stickers',
                }
                
                if restrict_type not in col_map:
                    await _safe_answer(query, await _trans('invalid_type', lang, "❌ نوع غير صالح"), show_alert=True)
                    return
                
                col = col_map[restrict_type]
                settings = await DB.get_security_settings(chat_id)
                new_val = 1 - settings.get(col, 0)
                await DB.update_security_settings(chat_id, **{col: new_val})
                
                await CallbackHandlers._show_restrict_settings(update, context, query, chat_id, lang)
                return
            
            action_handlers = {
                "maxlen": (UserState.WAIT_MAX_LEN, await _trans('send_max_length', lang, "📏 أرسل الحد الأقصى لطول الرسالة:")),
                "del_pen": (UserState.WAIT_PENALTY_DURATION, await _trans('send_penalty_minutes', lang, "⏱️ أرسل مدة العقوبة بالدقائق:")),
                "set_violation_strikes": (UserState.WAIT_VIOLATION_STRIKES, await _trans('send_violation_strikes', lang, "📊 أرسل عدد المخالفات قبل العقوبة:")),
                "set_violation_duration": (UserState.WAIT_VIOLATION_DURATION, await _trans('send_violation_duration', lang, "⏱️ أرسل مدة العقوبة بالدقائق:")),
                "set_antiflood_messages": (UserState.WAIT_ANTIFLOOD_MESSAGES, await _trans('send_antiflood_messages', lang, "📊 أرسل عدد الرسائل المسموحة:")),
                "set_antiflood_seconds": (UserState.WAIT_ANTIFLOOD_SECONDS, await _trans('send_antiflood_seconds', lang, "⏱️ أرسل المدة بالثواني:")),
                "set_night_start": (UserState.WAIT_NIGHT_START, await _trans('send_night_start', lang, "🌙 أرسل وقت البدء (HH:MM):")),
                "set_night_end": (UserState.WAIT_NIGHT_END, await _trans('send_night_end', lang, "🌙 أرسل وقت النهاية (HH:MM):")),
                "slow_mode_seconds": (UserState.WAIT_SLOW_MODE_SECONDS, await _trans('send_slow_mode_seconds', lang, "⏱️ أرسل مدة الوضع البطيء بالثواني:")),
                "welcome_text": (UserState.WAIT_WELCOME_TEXT, await _trans('send_welcome_text', lang, "📝 أرسل نص الترحيب:")),
                "goodbye_text": (UserState.WAIT_GOODBYE_TEXT, await _trans('send_goodbye_text', lang, "📝 أرسل نص الوداع:")),
            }
            
            if action in action_handlers:
                state, msg = action_handlers[action]
                StateManager.set(user_id, state)
                context.user_data['sec_chat'] = chat_id
                await safe_edit(query, msg, bot=context.bot)
                return
            
            if action == "antiflood_duration":
                context.user_data['penalty_type'] = 'antiflood'
                await CallbackHandlers._show_penalty_durations(update, context, query, chat_id, lang, 'antiflood')
                return
            
            if action == "night_duration":
                context.user_data['penalty_type'] = 'night'
                await CallbackHandlers._show_penalty_durations(update, context, query, chat_id, lang, 'night')
                return
            
            if action == "warn_penalty_duration":
                context.user_data['penalty_type'] = 'warn_penalty'
                await CallbackHandlers._show_penalty_durations(update, context, query, chat_id, lang, 'warn_penalty')
                return
            
            if action == "penalty":
                await CallbackHandlers._show_penalty_types(update, context, query, chat_id, lang)
                return
            
            if action == "penalty_durations":
                await CallbackHandlers._show_penalty_durations(update, context, query, chat_id, lang)
                return
            
            if action == "violation_penalties":
                await CallbackHandlers._show_violation_penalties(update, context, query, chat_id, lang)
                return
            
            if action == "antiflood_settings":
                await CallbackHandlers._show_antiflood_settings(update, context, query, chat_id, lang)
                return
            
            if action == "antiflood_penalty":
                await CallbackHandlers._show_penalty_type_selection(update, context, query, chat_id, lang, "antiflood_penalty")
                return
            
            if action == "night_settings":
                await CallbackHandlers._show_night_settings(update, context, query, chat_id, lang)
                return
            
            if action == "night_action":
                await CallbackHandlers._show_penalty_type_selection(update, context, query, chat_id, lang, "night_mode_action")
                return
            
            if action == "auto_reply_menu":
                await CallbackHandlers._show_auto_reply_menu(update, context, query, chat_id, lang)
                return
            
            if action == "close":
                await safe_delete_message(query)
                StateManager.clear(user_id)
                context.user_data.clear()
                return
            
            await _safe_answer(query, await _trans('unknown_action', lang, "⚠️ غير معروف"), show_alert=True)
            
        except Exception as e:
            logger.error(f"خطأ في إعدادات الأمان: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ دوال عرض قوائم الأمان ============
    @staticmethod
    async def _show_warn_penalty_types(update, context, query, chat_id, lang):
        """عرض أنواع عقوبات التحذير"""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(await _trans('ban', lang, "🚫 حظر"), callback_data=f"sec_warn_penalty_set:{chat_id}:ban"),
             InlineKeyboardButton(await _trans('mute', lang, "🔇 كتم"), callback_data=f"sec_warn_penalty_set:{chat_id}:mute")],
            [InlineKeyboardButton(await _trans('kick', lang, "👢 طرد"), callback_data=f"sec_warn_penalty_set:{chat_id}:kick"),
             InlineKeyboardButton(await _trans('restrict', lang, "🔒 تقييد"), callback_data=f"sec_warn_penalty_set:{chat_id}:restrict")],
            [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"grp_set:{chat_id}")]
        ])
        await safe_edit(query, await _trans('choose_warn_penalty', lang, "⚖️ اختر عقوبة تجاوز التحذيرات:"), reply_markup=kb, bot=context.bot)
        await _safe_answer(query)

    @staticmethod
    async def _show_banned_words_menu(update, context, query, chat_id, lang):
        """عرض قائمة الكلمات المحظورة"""
        settings = await DB.get_security_settings(chat_id)
        is_enabled = settings.get('delete_banned_words', 0)
        toggle_text = await _trans('enable_delete', lang, "✅ تفعيل الحذف") if not is_enabled else await _trans('disable_delete', lang, "❌ تعطيل الحذف")
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(await _trans('add_word', lang, "➕ إضافة كلمة"), callback_data=f"ban_add:{chat_id}"),
             InlineKeyboardButton(await _trans('words_list', lang, "📋 القائمة"), callback_data=f"ban_list:{chat_id}")],
            [InlineKeyboardButton(await _trans('delete_word', lang, "🗑️ حذف كلمة"), callback_data=f"ban_rem:{chat_id}")],
            [InlineKeyboardButton(toggle_text, callback_data=f"sec_toggle_banned_words:{chat_id}")],
            [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"grp_set:{chat_id}")]
        ])
        await safe_edit(query, await _trans('manage_banned_words', lang, "🚫 إدارة الكلمات المحظورة:"), reply_markup=kb, bot=context.bot)

    @staticmethod
    async def _show_penalty_type_selection(update, context, query, chat_id, lang, setting_key):
        """عرض اختيار نوع العقوبة"""
        penalty_types = [
            (await _trans('mute', lang, "🔇 كتم"), "mute"),
            (await _trans('ban', lang, "🚫 حظر"), "ban"),
            (await _trans('kick', lang, "👢 طرد"), "kick"),
            (await _trans('restrict', lang, "🔒 تقييد"), "restrict"),
        ]
        kb = []
        for label, ptype in penalty_types:
            callback = f"sec_set_{setting_key}:{chat_id}:{ptype}"
            kb.append([InlineKeyboardButton(label, callback_data=callback)])
        kb.append([InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"grp_set:{chat_id}")])
        await safe_edit(query, await _trans('choose_penalty_type', lang, "🚫 اختر نوع العقوبة:"), reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)

    @staticmethod
    async def _show_penalty_durations(update, context, query, chat_id, lang, penalty_type='mute'):
        """عرض مدد العقوبات"""
        if penalty_type == 'kick':
            await _safe_answer(query, await _trans('kick_no_duration', lang, "✅ عقوبة الطرد لا تحتاج مدة"))
            settings = await DB.get_security_settings(chat_id)
            await safe_edit(query, KeyboardFactory._format_security_text(settings), reply_markup=KeyboardFactory.build("security", chat_id=chat_id, lang=lang), bot=context.bot)
            return

        durations = [
            (await _trans('permanent', lang, "دائم"), 0),
            (await _trans('half_hour', lang, "نصف ساعة"), 1800),
            (await _trans('hour', lang, "ساعة"), 3600),
            (await _trans('day', lang, "يوم"), 86400),
            (await _trans('week', lang, "أسبوع"), 604800),
            (await _trans('ten_days', lang, "عشرة أيام"), 864000),
            (await _trans('month', lang, "شهر"), 2592000),
        ]
        
        kb = []
        for i in range(0, len(durations), 2):
            row = []
            name, secs = durations[i]
            row.append(InlineKeyboardButton(name, callback_data=f"set_duration:{penalty_type}:{chat_id}:{secs}"))
            if i + 1 < len(durations):
                name2, secs2 = durations[i+1]
                row.append(InlineKeyboardButton(name2, callback_data=f"set_duration:{penalty_type}:{chat_id}:{secs2}"))
            kb.append(row)
        
        kb.append([InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"grp_set:{chat_id}")])
        
        type_names = {
            'mute': await _trans('mute', lang, 'كتم'),
            'ban': await _trans('ban', lang, 'حظر'),
            'restrict': await _trans('restrict', lang, 'تقييد'),
            'antiflood': await _trans('antiflood', lang, 'الفيضان'),
            'night': await _trans('night_mode', lang, 'الوضع الليلي'),
            'warn_penalty': await _trans('warn_penalty', lang, 'عقوبة التحذير')
        }
        type_name = type_names.get(penalty_type, penalty_type)
        
        text = await _trans('choose_duration', lang, "⏱️ اختر مدة {type}:")
        try:
            text = text.format(type=type_name)
        except:
            text = f"⏱️ اختر مدة {type_name}:"
        
        await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)

    @staticmethod
    async def _show_violation_penalties(update, context, query, chat_id, lang):
        """عرض إعدادات المخالفات"""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(await _trans('strikes_count', lang, "عدد الضربات"), callback_data=f"sec_set_violation_strikes:{chat_id}"),
             InlineKeyboardButton(await _trans('duration', lang, "المدة"), callback_data=f"sec_set_violation_duration:{chat_id}")],
            [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"grp_set:{chat_id}")]
        ])
        await safe_edit(query, await _trans('violation_settings', lang, "🚨 إعدادات المخالفات:"), reply_markup=kb, bot=context.bot)

    @staticmethod
    async def _show_antiflood_settings(update, context, query, chat_id, lang):
        """عرض إعدادات الفيضان"""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(await _trans('messages_count', lang, "عدد الرسائل"), callback_data=f"sec_set_antiflood_messages:{chat_id}"),
             InlineKeyboardButton(await _trans('seconds', lang, "الثواني"), callback_data=f"sec_set_antiflood_seconds:{chat_id}")],
            [InlineKeyboardButton(await _trans('penalty_type', lang, "نوع العقوبة"), callback_data=f"sec_antiflood_penalty:{chat_id}"),
             InlineKeyboardButton(await _trans('penalty_duration', lang, "⏱️ مدة العقوبة"), callback_data=f"sec_antiflood_duration:{chat_id}")],
            [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"grp_set:{chat_id}")]
        ])
        await safe_edit(query, await _trans('antiflood_settings', lang, "🌊 إعدادات الفيضان:"), reply_markup=kb, bot=context.bot)

    @staticmethod
    async def _show_night_settings(update, context, query, chat_id, lang):
        """عرض إعدادات الوضع الليلي"""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(await _trans('start_time', lang, "وقت البدء"), callback_data=f"sec_set_night_start:{chat_id}"),
             InlineKeyboardButton(await _trans('end_time', lang, "وقت النهاية"), callback_data=f"sec_set_night_end:{chat_id}")],
            [InlineKeyboardButton(await _trans('action_type', lang, "نوع الإجراء"), callback_data=f"sec_night_action:{chat_id}"),
             InlineKeyboardButton(await _trans('action_duration', lang, "⏱️ مدة الإجراء"), callback_data=f"sec_night_duration:{chat_id}")],
            [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"grp_set:{chat_id}")]
        ])
        await safe_edit(query, await _trans('night_mode_settings', lang, "🌙 إعدادات الوضع الليلي:"), reply_markup=kb, bot=context.bot)

    @staticmethod
    async def _show_auto_reply_menu(update, context, query, chat_id, lang):
        """عرض إعدادات الردود التلقائية"""
        kb = KeyboardFactory.build("auto_reply", chat_id=chat_id, lang=lang)
        await safe_edit(query, await _trans('auto_reply_settings', lang, "🤖 إعدادات الردود التلقائية:"), reply_markup=kb, bot=context.bot)

    @staticmethod
    async def _show_advanced_actions(update, context, query, chat_id, lang):
        """عرض الإجراءات المتقدمة"""
        kb = KeyboardFactory.build("advanced_actions", chat_id=chat_id, lang=lang)
        await safe_edit(query, await _trans('advanced_actions', lang, "🛠️ الإجراءات المتقدمة:"), reply_markup=kb, bot=context.bot)

    @staticmethod
    async def _show_admin_logs(update, context, query, chat_id, lang):
        """عرض سجل المشرفين"""
        logs = await DB.get_admin_logs(chat_id, 10)
        if logs:
            text = await _trans('admin_logs', lang, "📋 سجل المشرفين") + "\n\n"
            for l in logs:
                text += f"• {l['admin_id']} → {l['action']}\n"
        else:
            text = await _trans('none', lang, "📭 لا يوجد")
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"grp_set:{chat_id}")]])
        await safe_edit(query, text, reply_markup=kb, bot=context.bot)

    @staticmethod
    async def _show_penalty_types(update, context, query, chat_id, lang):
        """عرض أنواع العقوبات"""
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(await _trans('ban', lang, "حظر"), callback_data=f"sec_penalty_ban:{chat_id}"),
             InlineKeyboardButton(await _trans('mute', lang, "كتم"), callback_data=f"sec_penalty_mute:{chat_id}")],
            [InlineKeyboardButton(await _trans('kick', lang, "طرد"), callback_data=f"sec_penalty_kick:{chat_id}"),
             InlineKeyboardButton(await _trans('restrict', lang, "تقييد"), callback_data=f"sec_penalty_restrict:{chat_id}")],
            [InlineKeyboardButton(await _trans('no_penalty', lang, "بدون عقوبة"), callback_data=f"sec_penalty_none:{chat_id}")],
            [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"grp_set:{chat_id}")]
        ])
        await safe_edit(query, await _trans('choose_penalty_type', lang, "🚫 اختر نوع العقوبة:"), reply_markup=kb, bot=context.bot)

    @staticmethod
    async def _show_restrict_settings(update, context, query, chat_id, lang):
        """عرض إعدادات التقييد التفصيلية"""
        try:
            settings = await DB.get_security_settings(chat_id)
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"{'✅' if settings.get('restrict_send_messages') else '❌'} {await _trans('send_messages', lang, 'إرسال الرسائل')}",
                    callback_data=f"sec_restrict_toggle:send_messages:{chat_id}"
                )],
                [InlineKeyboardButton(
                    f"{'✅' if settings.get('restrict_send_media') else '❌'} {await _trans('send_media', lang, 'إرسال الوسائط')}",
                    callback_data=f"sec_restrict_toggle:send_media:{chat_id}"
                )],
                [InlineKeyboardButton(
                    f"{'✅' if settings.get('restrict_send_links') else '❌'} {await _trans('send_links', lang, 'إرسال الروابط')}",
                    callback_data=f"sec_restrict_toggle:send_links:{chat_id}"
                )],
                [InlineKeyboardButton(
                    f"{'✅' if settings.get('restrict_send_stickers') else '❌'} {await _trans('send_stickers', lang, 'إرسال الملصقات')}",
                    callback_data=f"sec_restrict_toggle:send_stickers:{chat_id}"
                )],
                [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"grp_set:{chat_id}")]
            ])
            
            await safe_edit(query, await _trans('restrict_settings', lang, "🔒 إعدادات التقييد:"), reply_markup=kb, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض إعدادات التقييد: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات الأدمن ============
    @staticmethod
    async def _handle_admin(update, context, query, user_id, lang=None):
        """معالجة أزرار لوحة الأدمن"""
        if not CONFIG.is_developer(user_id):
            await _safe_answer(query, await _trans('unauthorized', lang or 'ar', "❌ غير مصرح"), show_alert=True)
            return

        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'

        data = query.data

        try:
            if data == "admin_grant_free":
                StateManager.set(user_id, UserState.WAIT_GRANT_FREE)
                await safe_edit(query, await _trans('send_user_days', lang, "🎁 أرسل: معرف_المستخدم عدد_الأيام"), bot=context.bot)
                return

            elif data == CB.ADMIN_USERS:
                stats = await DB.get_user_stats()
                text = await _trans('admin_users', lang, "👥 المستخدمون") + "\n\n"
                text += f"👥 {await _trans('total', lang, 'الإجمالي')}: {stats['users']}\n"
                text += f"⛔ {await _trans('banned_users', lang, 'المحظورون')}: {stats['banned']}"
                
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(await _trans('banned_users', lang, "⛔ المحظورين"), callback_data=CB.ADMIN_BANNED)],
                    [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]
                ])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif data == CB.ADMIN_BANNED:
                banned_users = await DB.fetchall("SELECT user_id FROM users WHERE banned=1 LIMIT 20")
                if banned_users:
                    text = await _trans('banned_users', lang, "⛔ المحظورين") + "\n\n"
                    for u in banned_users:
                        text += f"• {u['user_id']}\n"
                else:
                    text = await _trans('no_banned_users', lang, "📭 لا يوجد محظورون")
                
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(await _trans('unban_all', lang, "✅ فك حظر الكل"), callback_data=CB.ADMIN_UNBAN_ALL)],
                    [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]
                ])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif data == CB.ADMIN_UNBAN_ALL:
                await DB.execute("UPDATE users SET banned=0 WHERE banned=1")
                await safe_edit(query, await _trans('all_unbanned', lang, "✅ تم إلغاء حظر الجميع"), bot=context.bot)
                return

            elif data == CB.ADMIN_STATS:
                stats = await DB.get_general_stats()
                text = await _trans('general_stats', lang, "📊 إحصائيات عامة") + "\n\n"
                text += f"👥 {await _trans('users', lang, 'المستخدمون')}: {stats['users']}\n"
                text += f"📡 {await _trans('channels', lang, 'القنوات')}: {stats['channels']}\n"
                text += f"👥 {await _trans('groups', lang, 'المجموعات')}: {stats['groups']}\n"
                text += f"📝 {await _trans('posts', lang, 'المنشورات')}: {stats['posts']}\n"
                text += f"✅ {await _trans('published_posts', lang, 'المنشورة')}: {stats['published']}\n"
                text += f"🧾 {await _trans('invoices', lang, 'الفواتير')}: {stats['invoices']}\n"
                text += f"🎫 {await _trans('pending_tickets', lang, 'التذاكر المعلقة')}: {stats['tickets']}"
                
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif data == CB.ADMIN_CHANNELS:
                await CallbackHandlers._show_admin_channels(update, context, query, user_id, lang)
                return

            elif data.startswith("admin_toggle_ch:"):
                await CallbackHandlers._handle_toggle_channel(update, context, query, user_id, lang, data)
                return

            elif data == CB.ADMIN_GROUPS:
                await CallbackHandlers._show_admin_groups(update, context, query, user_id, lang)
                return

            elif data.startswith("admin_toggle_gr:"):
                await CallbackHandlers._handle_toggle_group(update, context, query, user_id, lang, data)
                return

            elif data == CB.ADMIN_ADD_ADMIN:
                StateManager.set(user_id, UserState.WAIT_ADMIN_ADD)
                await safe_edit(query, await _trans('send_admin_id', lang, "👑 أرسل معرف المشرف:"), bot=context.bot)
                return

            elif data == CB.ADMIN_REM_ADMIN:
                StateManager.set(user_id, UserState.WAIT_ADMIN_REM)
                await safe_edit(query, await _trans('send_admin_id_remove', lang, "🗑️ أرسل معرف المشرف:"), bot=context.bot)
                return

            elif data == CB.ADMIN_LIST_ADMINS:
                admins = await DB.get_admin_list()
                if admins:
                    text = await _trans('admins_list', lang, "👑 المشرفون") + "\n\n"
                    for a in admins:
                        text += f"• {a['user_id']}\n"
                else:
                    text = await _trans('no_admins', lang, "📭 لا يوجد")
                
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(await _trans('add', lang, "➕ إضافة"), callback_data=CB.ADMIN_ADD_ADMIN),
                     InlineKeyboardButton(await _trans('remove', lang, "🗑️ إزالة"), callback_data=CB.ADMIN_REM_ADMIN)],
                    [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]
                ])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif data == CB.ADMIN_BROADCAST:
                StateManager.set(user_id, UserState.WAIT_BROADCAST)
                await safe_edit(query, await _trans('send_broadcast', lang, "📨 أرسل الرسالة:"), bot=context.bot)
                return

            elif data == CB.ADMIN_INVOICES:
                invoices = await DB.fetchall("SELECT number, amount, status FROM invoices ORDER BY id DESC LIMIT 20")
                if invoices:
                    text = await _trans('invoices_list', lang, "🧾 الفواتير") + "\n\n"
                    for i in invoices:
                        text += f"• {i['number']} - {i['amount']} ⭐ - {i['status']}\n"
                else:
                    text = await _trans('none', lang, "📭 لا توجد")
                
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif data == CB.ADMIN_BACKUP:
                await _safe_answer(query, await _trans('backing_up', lang, "⏳ جارٍ النسخ..."))
                task = asyncio.create_task(CallbackHandlers._do_backup(context, user_id))
                ACTIVE_TASKS.add(task)
                task.add_done_callback(ACTIVE_TASKS.discard)
                return

            elif data in [CB.ADMIN_RESTORE, CB.ADMIN_RESTORE_SEL]:
                await CallbackHandlers._show_restore_backups(update, context, query, user_id)
                return

            elif data.startswith("admin_restore_file:"):
                await CallbackHandlers._handle_restore_backup(update, context, query, user_id, lang, data)
                return

            elif data == CB.ADMIN_RAM:
                ram = get_ram_usage()
                text = f"🖥️ {await _trans('ram', lang, 'الرام')}\n\n"
                text += f"💾 {await _trans('total', lang, 'الإجمالي')}: {ram['total']} GB\n"
                text += f"📊 {await _trans('used', lang, 'المستخدم')}: {ram['used']} GB\n"
                text += f"📈 {await _trans('percent', lang, 'النسبة')}: {ram['percent']}%"
                await safe_edit(query, text, bot=context.bot)
                return

            elif data == CB.ADMIN_METRICS:
                await CallbackHandlers._show_metrics(update, context, query, user_id, lang)
                return

            elif data == CB.ADMIN_UPTIME:
                uptime = time.monotonic() - context.bot_data.get('start_time', time.monotonic())
                hours, remainder = divmod(uptime, 3600)
                minutes, seconds = divmod(remainder, 60)
                text = f"{await _trans('uptime', lang, '⏳ فترة التشغيل')}: {int(hours)} {await _trans('hours', lang, 'ساعة')} {int(minutes)} {await _trans('minutes', lang, 'دقيقة')} {int(seconds)} {await _trans('seconds', lang, 'ثانية')}"
                await safe_edit(query, text, bot=context.bot)
                return

            elif data == CB.ADMIN_TICKETS:
                tickets = await DB.get_tickets()
                if tickets:
                    text = await _trans('pending_tickets', lang, "🎫 التذاكر المعلقة") + "\n\n"
                    for t in tickets[:10]:
                        text += f"• #{t['ticket_number']} - {t['user_id']}: {t['message'][:50]}\n"
                else:
                    text = await _trans('no_tickets', lang, "📭 لا توجد تذاكر")
                
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(await _trans('delete_all_tickets', lang, "🗑️ حذف الكل"), callback_data=CB.ADMIN_DEL_TICKETS)],
                    [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]
                ])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif data == CB.ADMIN_DEL_TICKETS:
                await DB.delete_all_tickets()
                await safe_edit(query, await _trans('tickets_deleted', lang, "✅ تم حذف جميع التذاكر"), bot=context.bot)
                return

            elif data == CB.ADMIN_PAYMENT_LOGS:
                logs = await DB.fetchall("SELECT user_id, event_type, created_at FROM payment_logs ORDER BY id DESC LIMIT 20")
                if logs:
                    text = await _trans('payment_logs', lang, "💳 سجلات الدفع") + "\n\n"
                    for l in logs:
                        text += f"• {l['user_id']} - {l['event_type']} ({l['created_at']})\n"
                else:
                    text = await _trans('none', lang, "📭 لا توجد")
                await safe_edit(query, text, bot=context.bot)
                return

            elif data == CB.ADMIN_SET_UPDATE_CH:
                StateManager.set(user_id, UserState.WAIT_UPDATE_CH)
                await safe_edit(query, await _trans('send_update_channel', lang, "📢 أرسل معرف قناة التحديثات:"), bot=context.bot)
                return

            elif data == CB.ADMIN_SEND_UPDATE:
                StateManager.set(user_id, UserState.WAIT_UPDATE)
                await safe_edit(query, await _trans('send_update_text', lang, "📝 أرسل نص التحديث:"), bot=context.bot)
                return

            elif data == CB.ADMIN_SHOW_UPDATE:
                ch = await DB.get_updates_channel()
                if ch:
                    text = f"{await _trans('update_channel', lang, '📢 قناة التحديثات')}: {ch}"
                else:
                    text = await _trans('no_update_channel', lang, "📭 لم يتم تعيين قناة تحديثات")
                await safe_edit(query, text, bot=context.bot)
                return

            elif data == CB.ADMIN_SET_LOG_CH:
                StateManager.set(user_id, UserState.WAIT_LOG_CH)
                await safe_edit(query, await _trans('send_log_channel', lang, "📋 أرسل معرف قناة السجلات:"), bot=context.bot)
                return

            elif data == CB.ADMIN_LOG_CH:
                ch = await DB.get_log_channel()
                if ch:
                    text = f"{await _trans('log_channel', lang, '📋 قناة السجلات')}: {ch}"
                else:
                    text = await _trans('no_log_channel', lang, "📭 لم يتم تعيين قناة سجلات")
                await safe_edit(query, text, bot=context.bot)
                return

            elif data == CB.ADMIN_FORCE_SUB:
                sub = await DB.get_force_subscribe_channel()
                if sub:
                    text = f"{await _trans('force_subscribe', lang, '🔒 الاشتراك الإجباري')}: ✅ {await _trans('enabled', lang, 'مفعل')}\n"
                    text += f"{await _trans('channel', lang, 'القناة')}: {sub}"
                else:
                    text = f"{await _trans('force_subscribe', lang, '🔒 الاشتراك الإجباري')}: ❌ {await _trans('disabled', lang, 'معطل')}"
                await safe_edit(query, text, bot=context.bot)
                return

            elif data == CB.ADMIN_SET_FORCE:
                StateManager.set(user_id, UserState.WAIT_FORCE)
                await safe_edit(query, await _trans('send_force_channel', lang, "🔒 أرسل معرف قناة الاشتراك الإجباري:"), bot=context.bot)
                return

            elif data == CB.ADMIN_REFRESH_CACHE:
                await safe_edit(query, await _trans('cache_refreshed', lang, "🔄 تم تحديث الكاش"), bot=context.bot)
                return

            elif data == CB.ADMIN_BANNED_CH:
                banned_channels = await DB.fetchall("SELECT channel_id, channel_name FROM user_channels WHERE banned=1 LIMIT 20")
                if banned_channels:
                    text = await _trans('banned_channels', lang, "🚫 القنوات المحظورة") + "\n\n"
                    for c in banned_channels:
                        text += f"• {c['channel_name']} ({c['channel_id']})\n"
                else:
                    text = await _trans('none', lang, "📭 لا توجد")
                
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(await _trans('activate_all', lang, "✅ تفعيل الكل"), callback_data=CB.ADMIN_ACTIVATE_CH)],
                    [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]
                ])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif data == CB.ADMIN_ACTIVATE_CH:
                await DB.execute("UPDATE user_channels SET banned=0 WHERE banned=1")
                await safe_edit(query, await _trans('all_channels_activated', lang, "✅ تم تفعيل جميع القنوات"), bot=context.bot)
                return

            elif data == CB.ADMIN_BANNED_GR:
                banned_groups = await DB.fetchall("SELECT chat_id, chat_name FROM bot_groups WHERE banned=1 LIMIT 20")
                if banned_groups:
                    text = await _trans('banned_groups', lang, "🚫 المجموعات المحظورة") + "\n\n"
                    for g in banned_groups:
                        text += f"• {g['chat_name']} ({g['chat_id']})\n"
                else:
                    text = await _trans('none', lang, "📭 لا توجد")
                
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(await _trans('unban_all_groups', lang, "🔓 إلغاء حظر الكل"), callback_data=CB.ADMIN_UNBAN_GR)],
                    [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]
                ])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif data == CB.ADMIN_UNBAN_GR:
                await DB.execute("UPDATE bot_groups SET banned=0 WHERE banned=1")
                await safe_edit(query, await _trans('all_groups_unbanned', lang, "✅ تم إلغاء حظر جميع المجموعات"), bot=context.bot)
                return

            elif data == CB.ADMIN_REPLIES:
                await CallbackHandlers._show_admin_replies(update, context, query, user_id, lang)
                return

            elif data == "admin_add_reply":
                StateManager.set(user_id, UserState.WAIT_KEYWORD)
                context.user_data['auto_chat'] = -1
                await safe_edit(query, await _trans('send_keyword', lang, "📝 أرسل الكلمة:"), bot=context.bot)
                return

            elif data == "admin_del_reply":
                StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
                context.user_data['auto_chat'] = -1
                await safe_edit(query, await _trans('send_keyword_delete', lang, "🗑️ أرسل الكلمة:"), bot=context.bot)
                return

            elif data == "admin_list_replies":
                replies = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=-1 LIMIT 50")
                if replies:
                    text = await _trans('general_replies_list', lang, "📋 قائمة الردود العامة") + "\n\n"
                    for r in replies:
                        text += f"• {r['keyword']}\n"
                else:
                    text = await _trans('none', lang, "📭 لا توجد")
                await safe_edit(query, text, bot=context.bot)
                return

            elif data == CB.ADMIN_EXPORT_REPLIES:
                await CallbackHandlers._handle_export_replies(update, context, query, user_id, lang)
                return

            elif data == CB.ADMIN_IMPORT_REPLIES:
                StateManager.set(user_id, UserState.WAIT_IMPORT_FILE)
                await safe_edit(query, await _trans('send_json_file', lang, "📤 أرسل ملف JSON:"), bot=context.bot)
                return

            elif data == CB.ADMIN_IMPORT_GITHUB:
                StateManager.set(user_id, UserState.WAIT_GITHUB_URL)
                await safe_edit(query, await _trans('send_github_url', lang, "📥 أرسل الرابط:"), bot=context.bot)
                return

            elif data == CB.ADMIN_BANNED_WORDS:
                words = await DB.get_banned_words(-1)
                if words:
                    text = await _trans('global_banned_words', lang, "🚫 الكلمات المحظورة العامة") + "\n\n"
                    for w in words[:30]:
                        text += f"• {w}\n"
                else:
                    text = await _trans('none', lang, "📭 لا توجد")
                
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(await _trans('add', lang, "➕ إضافة"), callback_data="admin_add_banned"),
                     InlineKeyboardButton(await _trans('delete', lang, "🗑️ حذف"), callback_data="admin_rem_banned")],
                    [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]
                ])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif data == "admin_add_banned":
                StateManager.set(user_id, UserState.WAIT_GLOBAL_BAN)
                await safe_edit(query, await _trans('send_word', lang, "📝 أرسل الكلمة:"), bot=context.bot)
                return

            elif data == "admin_rem_banned":
                StateManager.set(user_id, UserState.WAIT_REM_GLOBAL_BAN)
                await safe_edit(query, await _trans('send_word_delete', lang, "🗑️ أرسل الكلمة:"), bot=context.bot)
                return

            elif data == "admin_list_banned":
                words = await DB.get_banned_words(-1)
                if words:
                    text = await _trans('global_banned_words_list', lang, "📋 قائمة الكلمات المحظورة العامة") + "\n\n"
                    for w in words:
                        text += f"• {w}\n"
                else:
                    text = await _trans('none', lang, "📭 لا توجد")
                await safe_edit(query, text, bot=context.bot)
                return

            elif data == CB.ADMIN_CREATE_CONTEST:
                StateManager.set(user_id, UserState.WAIT_CONTEST_TITLE)
                await safe_edit(query, await _trans('send_contest_title', lang, "🏆 أرسل العنوان:"), bot=context.bot)
                return

            elif data == CB.ADMIN_DECLARE_WINNER:
                await CallbackHandlers._show_active_contests(update, context, query, user_id, lang)
                return

            elif data == CB.ADMIN_DEL_CONTEST:
                await CallbackHandlers._show_contests_for_delete(update, context, query, user_id, lang)
                return

            elif data.startswith("admin_delete_contest:"):
                await CallbackHandlers._handle_delete_contest(update, context, query, user_id, lang, data)
                return

            elif data == CB.ADMIN_HELP:
                await CallbackHandlers._show_admin_help(update, context, query, user_id, lang)
                return

            elif data == CB.ADMIN_PUSH:
                StateManager.set(user_id, UserState.WAIT_PUSH_NOTIFY)
                await safe_edit(query, await _trans('send_push_notification', lang, "📨 أرسل نص الإشعار العام:"), bot=context.bot)
                return

            elif data == CB.ADMIN_FILES:
                await CallbackHandlers._show_files_manager(update, context, query, user_id, lang)
                return

            elif data.startswith("admin_del_file:"):
                await CallbackHandlers._handle_delete_file(update, context, query, user_id, lang, data)
                return

            elif data == CB.ADMIN_PING:
                await CallbackHandlers._check_server_status(update, context, query, user_id, lang)
                return

            else:
                await _safe_answer(query, await _trans('not_available', lang, "⚠️ غير متوفر"), show_alert=True)

        except BadRequest as e:
            if "query is too old" not in str(e).lower():
                logger.error(f"خطأ في لوحة الأدمن: {e}", exc_info=True)
                await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في لوحة الأدمن: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ دوال مساعدة للأدمن ============
    @staticmethod
    async def _show_admin_help(update, context, query, user_id, lang):
        """عرض مساعدة الأدمن"""
        try:
            text = await _trans('admin_help_title', lang, "📖 دليل الأدمن") + "\n\n"
            text += await _trans('admin_help_content', lang, 
                "• 👥 إدارة المستخدمين: عرض وحظر المستخدمين\n"
                "• 📡 إدارة القنوات: التحكم في القنوات\n"
                "• 📨 البث: إرسال رسائل لجميع المستخدمين\n"
                "• 💾 النسخ الاحتياطي: إنشاء واستعادة النسخ\n"
                "• 🏆 المسابقات: إنشاء وإدارة المسابقات\n"
                "• 🚫 الكلمات المحظورة: إدارة الكلمات الممنوعة\n"
                "• 🤖 الردود التلقائية: إدارة الردود\n"
                "• 📊 الإحصائيات: عرض إحصائيات البوت")
            
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]])
            await safe_edit(query, text, reply_markup=kb, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض مساعدة الأدمن: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _show_files_manager(update, context, query, user_id, lang):
        """عرض مدير الملفات"""
        try:
            temp_files = []
            backup_files = []
            
            if PATHS.BACKUPS.exists():
                backup_files = sorted(PATHS.BACKUPS.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
            
            if hasattr(PATHS, 'TEMP') and PATHS.TEMP.exists():
                temp_files = sorted(PATHS.TEMP.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            
            text = await _trans('files_manager', lang, "📁 مدير الملفات") + "\n\n"
            text += f"📦 {await _trans('backup_files', lang, 'ملفات النسخ الاحتياطي')}: {len(backup_files)}\n"
            text += f"📄 {await _trans('temp_files', lang, 'الملفات المؤقتة')}: {len(temp_files)}\n\n"
            
            kb = []
            
            if backup_files:
                text += await _trans('backup_files', lang, "📦 ملفات النسخ الاحتياطي:") + "\n"
                for f in backup_files[:5]:
                    size_kb = f.stat().st_size / 1024
                    text += f"• {f.name} ({size_kb:.1f} KB)\n"
                    kb.append([InlineKeyboardButton(f"🗑️ حذف {f.name[:20]}", callback_data=f"admin_del_file:backup:{f.name}")])
            
            if temp_files:
                text += "\n" + await _trans('temp_files', lang, "📄 الملفات المؤقتة:") + "\n"
                for f in temp_files[:5]:
                    size_kb = f.stat().st_size / 1024
                    text += f"• {f.name} ({size_kb:.1f} KB)\n"
                    kb.append([InlineKeyboardButton(f"🗑️ حذف {f.name[:20]}", callback_data=f"admin_del_file:temp:{f.name}")])
            
            kb.append([InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)])
            await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في عرض مدير الملفات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _handle_delete_file(update, context, query, user_id, lang, data):
        """معالجة حذف ملف"""
        try:
            parts = data.split(":")
            if len(parts) < 3:
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            file_type = parts[1]
            file_name = os.path.basename(parts[2])
            
            if file_type == "backup":
                if not file_name.startswith("backup_") and not file_name.startswith("pre_restore_"):
                    await _safe_answer(query, await _trans('invalid_file', lang, "❌ ملف غير صالح"), show_alert=True)
                    return
                file_path = PATHS.BACKUPS / file_name
            elif file_type == "temp":
                file_path = PATHS.TEMP / file_name if hasattr(PATHS, 'TEMP') else None
            else:
                await _safe_answer(query, await _trans('invalid_file', lang, "❌ نوع ملف غير صالح"), show_alert=True)
                return
            
            if not file_path or not file_path.exists():
                await _safe_answer(query, await _trans('file_not_found', lang, "❌ الملف غير موجود"), show_alert=True)
                return
            
            if file_type == "backup" and file_path.resolve().parent != PATHS.BACKUPS.resolve():
                await _safe_answer(query, await _trans('invalid_path', lang, "❌ مسار غير صالح"), show_alert=True)
                return
            
            try:
                file_path.unlink()
                await _safe_answer(query, await _trans('file_deleted', lang, "✅ تم حذف الملف"))
                await CallbackHandlers._show_files_manager(update, context, query, user_id, lang)
            except Exception as e:
                logger.error(f"خطأ في حذف الملف: {e}")
                await _safe_answer(query, await _trans('delete_failed', lang, "❌ فشل الحذف"), show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في معالجة حذف الملف: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _check_server_status(update, context, query, user_id, lang):
        """فحص حالة الخادم"""
        try:
            start_time = time.monotonic()
            
            db_status = "✅"
            db_latency = 0
            try:
                db_start = time.monotonic()
                await DB.fetchval("SELECT 1")
                db_latency = (time.monotonic() - db_start) * 1000
            except:
                db_status = "❌"
            
            ram = get_ram_usage()
            
            bot_status = "✅"
            bot_latency = 0
            try:
                bot_start = time.monotonic()
                me = await context.bot.get_me()
                bot_latency = (time.monotonic() - bot_start) * 1000
            except:
                bot_status = "❌"
            
            total_time = (time.monotonic() - start_time) * 1000
            
            text = await _trans('server_status', lang, "🖥️ حالة الخادم") + "\n\n"
            text += f"🤖 {await _trans('bot_status', lang, 'البوت')}: {bot_status} ({bot_latency:.1f} ms)\n"
            text += f"💾 {await _trans('db_status', lang, 'قاعدة البيانات')}: {db_status} ({db_latency:.1f} ms)\n"
            text += f"🧠 {await _trans('ram', lang, 'الذاكرة')}: {ram['used']}/{ram['total']} GB ({ram['percent']}%)\n"
            text += f"⏱️ {await _trans('total_time', lang, 'زمن الاستجابة')}: {total_time:.1f} ms\n"
            
            uptime = time.monotonic() - context.bot_data.get('start_time', time.monotonic())
            hours, remainder = divmod(uptime, 3600)
            minutes, seconds = divmod(remainder, 60)
            text += f"⏳ {await _trans('uptime', lang, 'فترة التشغيل')}: {int(hours)}h {int(minutes)}m {int(seconds)}s"
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(await _trans('refresh', lang, "🔄 تحديث"), callback_data=CB.ADMIN_PING)],
                [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]
            ])
            await safe_edit(query, text, reply_markup=kb, bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في فحص حالة الخادم: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _show_metrics(update, context, query, user_id, lang):
        """عرض مقاييس النظام مع زر فحص الخادم"""
        stats = await DB.get_general_stats()
        db_size = PATHS.DB.stat().st_size / 1024 if PATHS.DB.exists() else 0
        
        text = f"{await _trans('system_metrics', lang, '📊 مقاييس النظام')}\n\n"
        text += f"👥 {await _trans('users', lang, 'المستخدمون')}: {stats['users']}\n"
        text += f"📡 {await _trans('channels', lang, 'القنوات')}: {stats['channels']}\n"
        text += f"👥 {await _trans('groups', lang, 'المجموعات')}: {stats['groups']}\n"
        text += f"📝 {await _trans('posts', lang, 'المنشورات')}: {stats['posts']}\n"
        text += f"✅ {await _trans('published_posts', lang, 'المنشورة')}: {stats['published']}\n"
        text += f"🧾 {await _trans('invoices', lang, 'الفواتير')}: {stats['invoices']}\n"
        text += f"🎫 {await _trans('pending_tickets', lang, 'تذاكر معلقة')}: {stats['tickets']}\n"
        text += f"💾 {await _trans('db_size', lang, 'حجم قاعدة البيانات')}: {db_size:.1f} KB"
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(await _trans('server_status', lang, "🖥️ فحص الخادم"), callback_data=CB.ADMIN_PING)],
            [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]
        ])
        await safe_edit(query, text, reply_markup=kb, bot=context.bot)

    @staticmethod
    async def _show_restore_backups(update, context, query, user_id):
        """عرض النسخ الاحتياطية المتاحة"""
        lang = await DB.get_user_language(user_id) or 'ar'
        backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        if not backups:
            await safe_edit(query, await _trans('no_backups', lang, "📭 لا توجد نسخ احتياطية"), bot=context.bot)
            return
        
        kb = []
        for b in backups[:10]:
            fname = b.name
            kb.append([InlineKeyboardButton(f"📁 {fname}", callback_data=f"admin_restore_file:{fname}")])
        
        kb.append([InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)])
        await safe_edit(query, await _trans('choose_backup', lang, "📂 اختر نسخة احتياطية للاستعادة:"), reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)

    @staticmethod
    async def _handle_restore_backup(update, context, query, user_id, lang, data):
        """معالجة استعادة نسخة احتياطية"""
        try:
            fname = os.path.basename(data.split(":", 1)[1])
            
            if not fname.startswith("backup_") or not fname.endswith(".db"):
                logger.warning(f"🚫 محاولة استعادة ملف غير صالح: {fname}")
                await _safe_answer(query, await _trans('invalid_file', lang, "❌ اسم ملف غير صالح"), show_alert=True)
                return
            
            backup_file = PATHS.BACKUPS / fname
            
            if not backup_file.exists():
                await _safe_answer(query, await _trans('file_not_found', lang, "❌ الملف غير موجود"), show_alert=True)
                return
            
            if backup_file.stat().st_size > 100 * 1024 * 1024:
                await _safe_answer(query, await _trans('file_too_large', lang, "❌ الملف كبير جداً"), show_alert=True)
                return
            
            try:
                pre_restore_backup = PATHS.BACKUPS / f"pre_restore_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2(PATHS.DB, pre_restore_backup)
                
                shutil.copy2(backup_file, PATHS.DB)
                
                await safe_edit(query, await _trans('restore_success', lang, "✅ تمت الاستعادة بنجاح! أعد تشغيل البوت لتفعيل التغييرات."), bot=context.bot)
            except Exception as e:
                logger.error(f"فشل الاستعادة: {e}")
                await safe_edit(query, await _trans('restore_failed', lang, "❌ فشل الاستعادة: {error}").format(error=str(e)[:100]), bot=context.bot)
        except Exception as e:
            logger.error(f"خطأ في استعادة النسخة الاحتياطية: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _show_admin_channels(update, context, query, user_id, lang):
        """عرض قنوات الأدمن"""
        channels = await DB.fetchall(
            "SELECT id, channel_id, channel_name, banned FROM user_channels ORDER BY channel_name LIMIT 50"
        )
        kb = []
        for c in channels:
            action = await _trans('unban', lang, "🔓 فك حظر") if c['banned'] else await _trans('ban', lang, "🔒 حظر")
            icon = "🚫" if c['banned'] else "✅"
            kb.append([
                InlineKeyboardButton(
                    f"{icon} {c['channel_name'][:20]} - {action}",
                    callback_data=f"admin_toggle_ch:{c['id']}"
                )
            ])
        
        kb.append([InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)])
        text = await _trans('manage_channels', lang, "📡 إدارة القنوات") + f" ({len(channels)})\n\n"
        text += await _trans('click_to_toggle', lang, "اضغط على القناة للتبديل بين الحظر وفك الحظر:")
        
        await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)

    @staticmethod
    async def _handle_toggle_channel(update, context, query, user_id, lang, data):
        """معالجة تبديل حالة القناة"""
        try:
            try:
                ch_db_id = int(data.split(":")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            row = await DB.fetchone("SELECT banned FROM user_channels WHERE id=?", (ch_db_id,))
            if row:
                new_val = 0 if row['banned'] else 1
                await DB.execute("UPDATE user_channels SET banned=? WHERE id=?", (new_val, ch_db_id))
                
                if new_val == 0:
                    await _safe_answer(query, await _trans('channel_unbanned', lang, "✅ تم فك الحظر"))
                else:
                    await _safe_answer(query, await _trans('channel_banned', lang, "✅ تم حظر القناة"))
                
                await CallbackHandlers._show_admin_channels(update, context, query, user_id, lang)
        except Exception as e:
            logger.error(f"خطأ في تبديل حالة القناة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _show_admin_groups(update, context, query, user_id, lang):
        """عرض مجموعات الأدمن"""
        groups = await DB.fetchall(
            "SELECT chat_id, chat_name, banned FROM bot_groups ORDER BY chat_name LIMIT 50"
        )
        kb = []
        for g in groups:
            action = await _trans('unban', lang, "🔓 فك حظر") if g['banned'] else await _trans('ban', lang, "🔒 حظر")
            icon = "🚫" if g['banned'] else "✅"
            kb.append([
                InlineKeyboardButton(
                    f"{icon} {g['chat_name'][:20]} - {action}",
                    callback_data=f"admin_toggle_gr:{g['chat_id']}"
                )
            ])
        
        kb.append([InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)])
        text = await _trans('manage_groups', lang, "👥 إدارة المجموعات") + f" ({len(groups)})\n\n"
        text += await _trans('click_to_toggle', lang, "اضغط على المجموعة للتبديل بين الحظر وفك الحظر:")
        
        await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)

    @staticmethod
    async def _handle_toggle_group(update, context, query, user_id, lang, data):
        """معالجة تبديل حالة المجموعة"""
        try:
            try:
                chat_id = int(data.split(":")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            row = await DB.fetchone("SELECT banned FROM bot_groups WHERE chat_id=?", (chat_id,))
            if row:
                new_val = 0 if row['banned'] else 1
                
                if new_val == 1:
                    try:
                        await context.bot.leave_chat(chat_id)
                        leave_msg = await _trans('group_banned_left', lang, "تم حظر المجموعة ومغادرتها")
                    except Exception as e:
                        leave_msg = await _trans('group_banned_no_leave', lang, "تم حظر المجموعة (تعذر المغادرة)")
                else:
                    leave_msg = await _trans('group_unbanned', lang, "تم فك حظر المجموعة")
                
                await DB.execute("UPDATE bot_groups SET banned=? WHERE chat_id=?", (new_val, chat_id))
                await _safe_answer(query, f"✅ {leave_msg}")
                await CallbackHandlers._show_admin_groups(update, context, query, user_id, lang)
        except Exception as e:
            logger.error(f"خطأ في تبديل حالة المجموعة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    @staticmethod
    async def _show_admin_replies(update, context, query, user_id, lang):
        """عرض الردود العامة"""
        replies = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=-1 LIMIT 30")
        if replies:
            text = await _trans('general_replies', lang, "💬 الردود العامة") + "\n\n"
            for r in replies:
                text += f"• {r['keyword']}\n"
        else:
            text = await _trans('none', lang, "📭 لا توجد")
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(await _trans('add', lang, "➕ إضافة"), callback_data="admin_add_reply"),
             InlineKeyboardButton(await _trans('delete', lang, "🗑️ حذف"), callback_data="admin_del_reply")],
            [InlineKeyboardButton(await _trans('export', lang, "📤 تصدير"), callback_data=CB.ADMIN_EXPORT_REPLIES),
             InlineKeyboardButton(await _trans('import', lang, "📥 استيراد"), callback_data=CB.ADMIN_IMPORT_REPLIES)],
            [InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)]
        ])
        await safe_edit(query, text, reply_markup=kb, bot=context.bot)

    @staticmethod
    async def _handle_export_replies(update, context, query, user_id, lang):
        """معالجة تصدير الردود"""
        file_path = await DB.export_auto_replies_to_file()
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    await context.bot.send_document(chat_id=user_id, document=f, filename=Path(file_path).name)
            except Exception as e:
                await safe_send(context.bot, user_id, await _trans('send_failed', lang, "❌ فشل الإرسال: {error}").format(error=e))
            finally:
                try:
                    os.remove(file_path)
                except OSError:
                    pass
        else:
            await safe_edit(query, await _trans('no_replies', lang, "📭 لا توجد ردود"), bot=context.bot)

    @staticmethod
    async def _show_active_contests(update, context, query, user_id, lang):
        """عرض المسابقات النشطة"""
        contests = await DB.get_active_contests(5)
        if not contests:
            await safe_edit(query, await _trans('no_active_contests', lang, "📭 لا توجد مسابقات نشطة"), bot=context.bot)
            return
        
        kb = []
        for c in contests:
            kb.append([InlineKeyboardButton(f"🏆 {c['title'][:20]}", callback_data=f"{CB.DECLARE_WINNER_SEL}:{c['id']}")])
        
        kb.append([InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)])
        await safe_edit(query, await _trans('choose_contest', lang, "🏆 اختر المسابقة:"), reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)

    @staticmethod
    async def _show_contests_for_delete(update, context, query, user_id, lang):
        """عرض المسابقات للحذف"""
        contests = await DB.fetchall("SELECT id, title FROM contests WHERE status='active' LIMIT 10")
        if not contests:
            await safe_edit(query, await _trans('no_contests', lang, "📭 لا توجد مسابقات"), bot=context.bot)
            return
        
        kb = []
        for c in contests:
            kb.append([InlineKeyboardButton(f"🗑️ {c['title'][:20]}", callback_data=f"admin_delete_contest:{c['id']}")])
        
        kb.append([InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=CB.ADMIN)])
        await safe_edit(query, await _trans('choose_contest_delete', lang, "🗑️ اختر المسابقة للحذف:"), reply_markup=InlineKeyboardMarkup(kb), bot=context.bot)

    @staticmethod
    async def _handle_delete_contest(update, context, query, user_id, lang, data):
        """معالجة حذف مسابقة"""
        try:
            try:
                contest_id = int(data.split(":")[-1])
            except (ValueError, IndexError):
                await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                return
            
            if await DB.delete_contest(contest_id, user_id):
                await safe_edit(query, await _trans('contest_deleted', lang, "✅ تم حذف المسابقة"), bot=context.bot)
            else:
                await _safe_answer(query, await _trans('failed', lang, "❌ فشل"), show_alert=True)
        except Exception as e:
            logger.error(f"خطأ في حذف المسابقة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات الردود التلقائية ============
    @staticmethod
    async def _handle_auto_reply(update, context, query, user_id, lang=None):
        """معالجة أزرار الردود التلقائية"""
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        
        data = query.data
        parts = data.split(":")
        action = parts[0].replace("auto_reply_", "")

        if len(parts) < 2 or not parts[1].lstrip('-').isdigit():
            await _safe_answer(query, await _trans('group_not_specified', lang, "❌ لم يتم تحديد المجموعة"), show_alert=True)
            return
        
        try:
            chat_id = int(parts[1])
        except (ValueError, IndexError):
            await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
            return

        if chat_id != -1 and not await is_authorized_in_group(context.bot, chat_id, user_id):
            await _safe_answer(query, await _trans('no_permission', lang, "❌ لا صلاحية"), show_alert=True)
            return

        if action == "menu":
            kb = KeyboardFactory.build("auto_reply", chat_id=chat_id, lang=lang)
            await safe_edit(query, await _trans('auto_reply_settings', lang, "🤖 إعدادات الردود التلقائية:"), reply_markup=kb, bot=context.bot)
            return

        try:
            if action == "toggle":
                settings = await DB.get_auto_reply_settings(chat_id) or {}
                new_status = not settings.get('enabled', False)
                await DB.update_auto_reply_settings(chat_id, enabled=new_status)
                kb = KeyboardFactory.build("auto_reply", chat_id=chat_id, lang=lang)
                text = (
                    f"{await _trans('auto_reply_settings', lang, '🤖 إعدادات الردود التلقائية')}\n\n"
                    f"{await _trans('status', lang, 'الحالة')}: {'✅ ' + await _trans('enabled', lang, 'مفعلة') if new_status else '❌ ' + await _trans('disabled', lang, 'معطلة')}\n"
                    f"{await _trans('admins_only', lang, 'للمشرفين فقط')}: {'✅ ' + await _trans('yes', lang, 'نعم') if settings.get('only_admins') else '❌ ' + await _trans('no', lang, 'لا')}"
                )
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif action == "admins":
                settings = await DB.get_auto_reply_settings(chat_id) or {}
                new_status = not settings.get('only_admins', 0)
                await DB.update_auto_reply_settings(chat_id, only_admins=new_status)
                kb = KeyboardFactory.build("auto_reply", chat_id=chat_id, lang=lang)
                text = (
                    f"{await _trans('auto_reply_settings', lang, '🤖 إعدادات الردود التلقائية')}\n\n"
                    f"{await _trans('status', lang, 'الحالة')}: {'✅ ' + await _trans('enabled', lang, 'مفعلة') if settings.get('enabled') else '❌ ' + await _trans('disabled', lang, 'معطلة')}\n"
                    f"{await _trans('admins_only', lang, 'للمشرفين فقط')}: {'✅ ' + await _trans('yes', lang, 'نعم') if new_status else '❌ ' + await _trans('no', lang, 'لا')}"
                )
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif action == "add":
                StateManager.set(user_id, UserState.WAIT_AUTO_KEY)
                context.user_data['auto_chat'] = chat_id
                await safe_edit(query, await _trans('send_keyword', lang, "📝 أرسل الكلمة:"), bot=context.bot)
                return

            elif action == "del":
                StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
                context.user_data['auto_chat'] = chat_id
                await safe_edit(query, await _trans('send_keyword_delete', lang, "🗑️ أرسل الكلمة:"), bot=context.bot)
                return

            elif action == "reset":
                await DB.reset_auto_replies(chat_id)
                await safe_edit(query, await _trans('deleted_success', lang, "✅ تم الحذف"), bot=context.bot)
                return

            elif action == "list":
                rows = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=? LIMIT 20", (chat_id,))
                if rows:
                    text = await _trans('replies_list', lang, "📋 الردود") + "\n\n"
                    for r in rows:
                        text += f"• {r['keyword']}\n"
                else:
                    text = await _trans('none', lang, "📭 لا يوجد")
                
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"auto_reply_menu:{chat_id}")]])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

            elif action == "stats":
                stats = await DB.get_auto_reply_stats(chat_id, 20)
                if stats:
                    text = await _trans('replies_stats', lang, "📊 إحصائيات الردود") + "\n\n"
                    for s in stats:
                        source = await _trans('global', lang, "🌐 عام") if s['source'] == 'global' else await _trans('group', lang, "👥 مجموعة")
                        text += f"• {s['keyword']} ({source}): {s['usage_count']} {await _trans('usage', lang, 'استخدام')}\n"
                else:
                    text = await _trans('no_replies', lang, "📭 لا توجد ردود")
                
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(await _trans('back', lang, "🔙 رجوع"), callback_data=f"auto_reply_menu:{chat_id}")]])
                await safe_edit(query, text, reply_markup=kb, bot=context.bot)
                return

        except Exception as e:
            logger.error(f"خطأ في الردود التلقائية: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات الجدولة ============
    @staticmethod
    async def _handle_schedule(update, context, query, user_id):
        """معالجة أزرار الجدولة"""
        lang = await DB.get_user_language(user_id) or 'ar'
        data = query.data
        parts = data.split(":")
        
        if len(parts) < 2:
            return
        
        action = parts[0].replace("sched_", "")
        
        try:
            ch_id = int(parts[1])
        except (ValueError, IndexError):
            await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
            return
        
        if not await _is_channel_owner(user_id, ch_id):
            await _safe_answer(query, await _trans('not_channel_owner', lang, "❌ لا تملك هذه القناة"), show_alert=True)
            return

        if action == "open":
            await CallbackHandlers._show_schedule_menu(update, context, query, ch_id, user_id)
            return
        elif action == "min":
            StateManager.set(user_id, UserState.WAIT_MIN)
            context.user_data['schedule_ch'] = ch_id
            await safe_edit(query, await _trans('send_minutes', lang, "📅 أرسل الدقائق:"), bot=context.bot)
            return
        elif action == "hour":
            StateManager.set(user_id, UserState.WAIT_HOUR)
            context.user_data['schedule_ch'] = ch_id
            await safe_edit(query, await _trans('send_hours', lang, "📅 أرسل الساعات:"), bot=context.bot)
            return
        elif action == "day":
            StateManager.set(user_id, UserState.WAIT_DAY)
            context.user_data['schedule_ch'] = ch_id
            await safe_edit(query, await _trans('send_days', lang, "📅 أرسل الأيام:"), bot=context.bot)
            return
        elif action == "time":
            StateManager.set(user_id, UserState.WAIT_PUB_TIME)
            context.user_data['schedule_ch'] = ch_id
            await safe_edit(query, await _trans('send_time', lang, "🕐 أرسل الوقت HH:MM:"), bot=context.bot)
            return

    @staticmethod
    async def _show_schedule_menu(update, context, query, ch_id, user_id):
        """عرض قائمة الجدولة"""
        lang = await DB.get_user_language(user_id) or 'ar'
        kb = KeyboardFactory.build("channel_settings", chat_id=ch_id, lang=lang)
        await safe_edit(query, await _trans('channel_schedule', lang, "📅 جدولة القناة"), reply_markup=kb, bot=context.bot)

    # ============ معالجات الإجراءات المتقدمة ============
    @staticmethod
    async def _handle_advanced_actions(update, context, query, user_id):
        """معالجة الإجراءات المتقدمة والعقوبات"""
        lang = await DB.get_user_language(user_id) or 'ar'
        data = query.data
        parts = data.split(":")
        
        if len(parts) < 2:
            return
        
        action = parts[0].replace("act_", "").replace("pen_", "").replace("ban_", "")
        
        try:
            chat_id = int(parts[1])
        except (ValueError, IndexError):
            await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
            return

        if chat_id == -1 and (parts[0].startswith("act_") or parts[0].startswith("pen_")):
            await _safe_answer(query, await _trans('invalid_id', lang, "❌ معرف غير صالح"), show_alert=True)
            return

        if chat_id != -1 and not await is_authorized_in_group(context.bot, chat_id, user_id):
            await _safe_answer(query, await _trans('no_permission', lang, "❌ لا صلاحية"), show_alert=True)
            return
        
        if chat_id == -1 and not CONFIG.is_developer(user_id):
            await _safe_answer(query, await _trans('unauthorized', lang, "❌ غير مصرح"), show_alert=True)
            return

        if parts[0].startswith("ban_"):
            if action == "add":
                StateManager.set(user_id, UserState.WAIT_GROUP_BAN if chat_id != -1 else UserState.WAIT_GLOBAL_BAN)
                context.user_data['ban_chat'] = chat_id
                await safe_edit(query, await _trans('send_word', lang, "📝 أرسل الكلمة:"), bot=context.bot)
                return
            elif action == "list":
                words = await DB.get_banned_words(chat_id)
                if words:
                    text = await _trans('banned_words', lang, "🚫 الكلمات") + "\n\n"
                    for w in words[:50]:
                        text += f"• {w}\n"
                else:
                    text = await _trans('none', lang, "📭 لا يوجد")
                await safe_edit(query, text, bot=context.bot)
                return
            elif action == "rem":
                StateManager.set(user_id, UserState.WAIT_REM_GROUP_BAN if chat_id != -1 else UserState.WAIT_REM_GLOBAL_BAN)
                context.user_data['ban_chat'] = chat_id
                await safe_edit(query, await _trans('send_word_delete', lang, "🗑️ أرسل الكلمة:"), bot=context.bot)
                return

        elif parts[0].startswith("act_"):
            user_actions = {
                "ban": (UserState.WAIT_BAN, await _trans('send_user_id_ban', lang, "🚫 أرسل معرف المستخدم:")),
                "mute": (UserState.WAIT_MUTE, await _trans('send_user_id_mute', lang, "🔇 أرسل معرف المستخدم:")),
                "warn": (UserState.WAIT_WARN, await _trans('send_user_id_warn', lang, "⚠️ أرسل معرف المستخدم:")),
                "kick": (UserState.WAIT_KICK, await _trans('send_user_id_kick', lang, "👢 أرسل معرف المستخدم:")),
                "restrict": (UserState.WAIT_RESTRICT, await _trans('send_user_id_restrict', lang, "🔒 أرسل معرف المستخدم:")),
                "unban": (UserState.WAIT_UNBAN, await _trans('send_user_id_unban', lang, "🔓 أرسل معرف المستخدم:")),
            }
            
            if action in user_actions:
                state, msg = user_actions[action]
                StateManager.set(user_id, state)
                context.user_data['adv_chat'] = chat_id
                await safe_edit(query, msg, bot=context.bot)
                return
            elif action == "pin":
                StateManager.set(user_id, UserState.WAIT_PIN)
                context.user_data['adv_chat'] = chat_id
                await safe_edit(query, await _trans('reply_to_pin', lang, "📌 قم بالرد على الرسالة المطلوب تثبيتها ثم أرسل أي شيء:"), bot=context.bot)
                return
            elif action == "log":
                await CallbackHandlers._show_admin_logs(update, context, query, chat_id, lang)
                StateManager.clear(user_id)
                return

        elif parts[0].startswith("pen_"):
            if action in VALID_PENALTY_TYPES:
                await DB.update_security_settings(chat_id, auto_penalty=action)
                text = await _trans('penalty_set_type', lang, "✅ تم تعيين العقوبة: {type}")
                try:
                    text = text.format(type=action)
                except:
                    text = f"✅ تم تعيين العقوبة: {action}"
                await _safe_answer(query, text)
                return

        await _safe_answer(query, await _trans('unknown_action', lang, "⚠️ غير معروف"), show_alert=True)

    # ============ معالجات اللوحة الخاصة ============
    @staticmethod
    async def _handle_panel(update, context, query, user_id, data):
        """معالجة أزرار اللوحة الخاصة"""
        lang = await DB.get_user_language(user_id) or 'ar'
        chat_id = update.effective_chat.id
        
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await _safe_answer(query, await _trans('no_permission', lang, "❌ لا صلاحية"), show_alert=True)
            return
        
        try:
            if data == "panel_lock":
                await context.bot.set_chat_permissions(chat_id, permissions=ChatPermissions(can_send_messages=False))
                await safe_edit(query, await _trans('group_locked', lang, "🔒 تم قفل المجموعة"), bot=context.bot)
            elif data == "panel_unlock":
                await context.bot.set_chat_permissions(chat_id, permissions=ChatPermissions(can_send_messages=True))
                await safe_edit(query, await _trans('group_unlocked', lang, "🔓 تم فتح المجموعة"), bot=context.bot)
            elif data == "panel_close":
                StateManager.clear(user_id)
                context.user_data.clear()
                await safe_delete_message(query)
        except Exception as e:
            logger.error(f"خطأ في معالجة اللوحة: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات المسابقات ============
    @staticmethod
    async def _handle_contests(update, context, query, user_id):
        """معالجة أزرار المسابقات"""
        lang = await DB.get_user_language(user_id) or 'ar'
        data = query.data
        
        try:
            if data.startswith(CB.CONTEST_JOIN + ":"):
                try:
                    cid = int(data.split(":")[-1])
                except (ValueError, IndexError):
                    await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                    return
                
                contest = await DB.get_contest_by_id(cid)
                if not contest or contest['status'] != 'active':
                    await _safe_answer(query, await _trans('contest_unavailable', lang, "❌ المسابقة غير متاحة"), show_alert=True)
                    StateManager.clear(user_id)
                    return
                
                StateManager.set(user_id, UserState.WAIT_CONTEST_ANSWER)
                context.user_data['contest_join'] = cid
                await safe_edit(query, await _trans('send_answer', lang, "📝 أرسل إجابتك:"), bot=context.bot)
                
            elif data == CB.CONTEST_WINNERS:
                winners = await DB.get_contest_winners(10)
                if winners:
                    text = await _trans('contest_winners_title', lang, "🏆 الفائزون") + "\n\n"
                    for w in winners:
                        text += f"• {w['title']} - {w['winner_id']}\n"
                else:
                    text = await _trans('none', lang, "📭 لا يوجد")
                await safe_edit(query, text, bot=context.bot)
                StateManager.clear(user_id)
                
            elif data.startswith(CB.DECLARE_WINNER_SEL + ":"):
                if not CONFIG.is_developer(user_id):
                    await _safe_answer(query, await _trans('unauthorized', lang, "❌ غير مصرح"), show_alert=True)
                    return
                
                try:
                    cid = int(data.split(":")[-1])
                except (ValueError, IndexError):
                    await _safe_answer(query, await _trans('invalid_data', lang, "❌ بيانات غير صالحة"), show_alert=True)
                    return
                
                winner = await DB.fetchone("SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1", (cid,))
                if winner:
                    if await DB.declare_winner(cid, winner['user_id']):
                        text = await _trans('winner_declared', lang, "✅ الفائز: {user_id}")
                        try:
                            text = text.format(user_id=winner['user_id'])
                        except:
                            text = f"✅ الفائز: {winner['user_id']}"
                        await safe_edit(query, text, bot=context.bot)
                        
                        try:
                            await context.bot.send_message(winner['user_id'], await _trans('contest_won', lang, "🎉 مبروك! فزت بالمسابقة!"))
                        except:
                            pass
                    else:
                        await _safe_answer(query, await _trans('failed', lang, "❌ فشل"), show_alert=True)
                else:
                    await safe_edit(query, await _trans('no_participants', lang, "❌ لا يوجد مشاركون"), bot=context.bot)
                    
        except Exception as e:
            logger.error(f"خطأ في المسابقات: {e}", exc_info=True)
            await _safe_answer(query, await _trans('error_occurred', lang, "❌ حدث خطأ"), show_alert=True)

    # ============ معالجات الاستيراد ============
    @staticmethod
    async def _handle_import(update, context, query, user_id):
        """معالجة أزرار الاستيراد"""
        lang = await DB.get_user_language(user_id) or 'ar'
        
        if not CONFIG.is_developer(user_id):
            await _safe_answer(query, await _trans('unauthorized', lang, "❌ غير مصرح"), show_alert=True)
            return
        
        if query.data == CB.ADMIN_IMPORT_REPLIES:
            StateManager.set(user_id, UserState.WAIT_IMPORT_FILE)
            await safe_edit(query, await _trans('send_json_file', lang, "📤 أرسل ملف JSON:"), bot=context.bot)
        elif query.data == CB.ADMIN_IMPORT_GITHUB:
            StateManager.set(user_id, UserState.WAIT_GITHUB_URL)
            await safe_edit(query, await _trans('send_github_url', lang, "📥 أرسل الرابط:"), bot=context.bot)

    # ============ النسخ الاحتياطي ============
    @staticmethod
    async def _do_backup(context, user_id):
        """إنشاء نسخة احتياطية"""
        lang = await DB.get_user_language(user_id) or 'ar'
        
        try:
            PATHS.BACKUPS.mkdir(parents=True, exist_ok=True)
            backup_file = PATHS.BACKUPS / f"backup_{TimeUtils.mecca_now().strftime('%Y%m%d_%H%M%S')}.db"
            
            success = await DB.backup_database(backup_file)
            if not success:
                await safe_send(context.bot, user_id, await _trans('backup_failed', lang, "❌ فشل النسخ الاحتياطي"))
                return
            
            backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in backups[MAX_BACKUPS:]:
                old.unlink(missing_ok=True)
            
            with open(backup_file, 'rb') as f:
                await context.bot.send_document(chat_id=user_id, document=f, filename=backup_file.name)
                
        except Exception as e:
            logger.error(f"❌ فشل النسخ: {e}")
            text = await _trans('backup_failed_error', lang, "❌ فشل النسخ: {error}")
            try:
                text = text.format(error=str(e)[:100])
            except:
                text = f"❌ فشل النسخ: {str(e)[:100]}"
            await safe_send(context.bot, user_id, text)
