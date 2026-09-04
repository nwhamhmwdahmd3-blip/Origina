#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_message.py - معالجات الرسائل (MessageHandlers) - النسخة النهائية الكاملة
====================================================================================
- معالجة الرسائل الخاصة
- معالجة رسائل المجموعات
- معالجة رسائل الخدمة
- معالجة طلبات الانضمام
- دعم الردود التلقائية
- دعم تحليل المشاعر
- دعم الأمان (حذف الروابط، المعرفات، الفيضان، الكلمات المحظورة)
- إصلاح جميع مشاكل الـ async
"""

import asyncio
import logging
import re
import html
import time
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from telegram import Update, ChatMember, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TimedOut

from config import CONFIG
from database import DB, TimeUtils
from utils import (
    safe_send, is_authorized_in_group, check_bot_permissions,
    get_security_settings_cached, get_auto_reply_settings_cached,
    get_banned_words_cached, TextUtils, StateManager, UserState,
    get_text, METRICS, RATE_LIMITER, apply_penalty,
    get_min_publish_interval, invalidate_banned_words_cache,
)

logger = logging.getLogger(__name__)

MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096

# ==================== دوال مساعدة ====================

async def _trans(key: str, lang: str, default_ar: str) -> str:
    """جلب النص المترجم مع fallback للعربية"""
    try:
        text = await get_text(lang, key)
        if not text or text == key:
            return default_ar
        return text
    except:
        return default_ar


async def _get_user_lang(user_id: int) -> str:
    """جلب لغة المستخدم"""
    return await DB.get_user_language(user_id) or 'ar'


async def _is_admin_in_group(bot, chat_id: int, user_id: int) -> bool:
    """التحقق من أن المستخدم مشرف في المجموعة"""
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False


async def _get_penalty_action(settings: dict, default: str = 'mute') -> str:
    """الحصول على إجراء العقوبة المناسب"""
    penalty = settings.get('auto_penalty', default)
    if penalty in ['ban', 'mute', 'kick', 'restrict', 'none']:
        return penalty
    return default


async def _get_penalty_duration(settings: dict, penalty_type: str) -> int:
    """الحصول على مدة العقوبة"""
    duration_map = {
        'mute': settings.get('mute_default_duration', 3600),
        'ban': settings.get('ban_default_duration', 86400),
        'restrict': settings.get('restrict_default_duration', 1800),
        'antiflood': settings.get('antiflood_penalty_duration', 3600),
        'night': settings.get('night_mode_action_duration', 3600),
        'warn_penalty': settings.get('warn_penalty_duration', 3600),
    }
    return duration_map.get(penalty_type, 3600)


# ==================== تحليل المشاعر ====================

def analyze_sentiment(text: str) -> dict:
    """تحليل مشاعر النص (نسخة مبسطة)"""
    if not text:
        return {
            'sentiment': 'محايد',
            'emoji': '😐',
            'positive_percent': 50,
            'negative_percent': 50,
            'total_words': 0
        }

    # كلمات إيجابية وسلبية (مبسطة)
    positive_words = {'احب', 'رائع', 'جميل', 'سعيد', 'ممتاز', 'شكرا', 'عظيم', 'حلو', 'ممتاز', 'جيد', 'ممتاز', 'مرح'}
    negative_words = {'اكره', 'سيئ', 'حزين', 'ممل', 'غبي', 'فاشل', 'مستفز', 'مزعج', 'كره', 'بائس'}

    words = text.lower().split()
    total_words = len(words)

    if total_words == 0:
        return {'sentiment': 'محايد', 'emoji': '😐', 'positive_percent': 50, 'negative_percent': 50, 'total_words': 0}

    positive_count = sum(1 for w in words if w in positive_words)
    negative_count = sum(1 for w in words if w in negative_words)

    if positive_count > negative_count:
        sentiment = 'إيجابي'
        emoji = '😊'
        pos_pct = min(100, 60 + (positive_count / total_words) * 40)
        neg_pct = 100 - pos_pct
    elif negative_count > positive_count:
        sentiment = 'سلبي'
        emoji = '😔'
        neg_pct = min(100, 60 + (negative_count / total_words) * 40)
        pos_pct = 100 - neg_pct
    else:
        sentiment = 'محايد'
        emoji = '😐'
        pos_pct = 50
        neg_pct = 50

    return {
        'sentiment': sentiment,
        'emoji': emoji,
        'positive_percent': pos_pct,
        'negative_percent': neg_pct,
        'total_words': total_words
    }


# ==================== معالج الرسائل ====================

class MessageHandlers:
    """معالج رسائل البوت"""

    @staticmethod
    async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالج الرسائل الخاصة"""
        user_id = update.effective_user.id
        text = update.message.text or update.message.caption or ""
        await METRICS.increment_messages()

        if not text:
            return

        state = StateManager.get(user_id)

        # ===== معالجة الحالات =====
        if state == UserState.ADDING_POSTS:
            await MessageHandlers._handle_adding_posts(update, context, user_id, text)
            return

        elif state == UserState.WAIT_CHANNEL:
            await MessageHandlers._handle_wait_channel(update, context, user_id, text)
            return

        elif state in [UserState.WAIT_MIN, UserState.WAIT_HOUR, UserState.WAIT_DAY, UserState.WAIT_PUB_TIME]:
            await MessageHandlers._handle_schedule_input(update, context, user_id, text, state)
            return

        elif state == UserState.WAIT_ADMIN_ADD:
            await MessageHandlers._handle_admin_add(update, context, user_id, text)
            return

        elif state == UserState.WAIT_ADMIN_REM:
            await MessageHandlers._handle_admin_remove(update, context, user_id, text)
            return

        elif state == UserState.WAIT_BROADCAST:
            await MessageHandlers._handle_broadcast(update, context, user_id, text)
            return

        elif state == UserState.WAIT_UPDATE:
            await MessageHandlers._handle_update(update, context, user_id, text)
            return

        elif state == UserState.WAIT_UPDATE_CH:
            await MessageHandlers._handle_update_ch(update, context, user_id, text)
            return

        elif state == UserState.WAIT_FORCE:
            await MessageHandlers._handle_force_sub(update, context, user_id, text)
            return

        elif state == UserState.WAIT_REM_DAYS:
            await MessageHandlers._handle_rem_days(update, context, user_id, text)
            return

        elif state in [UserState.WAIT_BAN, UserState.WAIT_MUTE, UserState.WAIT_WARN,
                       UserState.WAIT_KICK, UserState.WAIT_RESTRICT, UserState.WAIT_UNBAN]:
            await MessageHandlers._handle_moderation_input(update, context, user_id, text, state)
            return

        elif state == UserState.WAIT_PIN:
            await MessageHandlers._handle_pin(update, context, user_id)
            return

        elif state == UserState.WAIT_GROUP_BAN:
            await MessageHandlers._handle_group_ban(update, context, user_id, text)
            return

        elif state == UserState.WAIT_REM_GROUP_BAN:
            await MessageHandlers._handle_rem_group_ban(update, context, user_id, text)
            return

        elif state == UserState.WAIT_GLOBAL_BAN:
            await MessageHandlers._handle_global_ban(update, context, user_id, text)
            return

        elif state == UserState.WAIT_REM_GLOBAL_BAN:
            await MessageHandlers._handle_rem_global_ban(update, context, user_id, text)
            return

        elif state == UserState.WAIT_KEYWORD:
            await MessageHandlers._handle_add_reply(update, context, user_id, text)
            return

        elif state == UserState.WAIT_AUTO_REPLY:
            await MessageHandlers._handle_auto_reply_input(update, context, user_id, text)
            return

        elif state == UserState.WAIT_AUTO_DEL:
            await MessageHandlers._handle_auto_del(update, context, user_id, text)
            return

        elif state == UserState.WAIT_CONTEST_TITLE:
            await MessageHandlers._handle_contest_title(update, context, user_id, text)
            return

        elif state == UserState.WAIT_CONTEST_DESC:
            await MessageHandlers._handle_contest_desc(update, context, user_id, text)
            return

        elif state == UserState.WAIT_CONTEST_PRIZE:
            await MessageHandlers._handle_contest_prize(update, context, user_id, text)
            return

        elif state == UserState.WAIT_CONTEST_DATE:
            await MessageHandlers._handle_contest_date(update, context, user_id, text)
            return

        elif state == UserState.WAIT_CONTEST_ANSWER:
            await MessageHandlers._handle_contest_answer(update, context, user_id, text)
            return

        elif state == UserState.WAIT_CONTEST_WINNER:
            await MessageHandlers._handle_contest_winner(update, context, user_id, text)
            return

        elif state == UserState.WAIT_MAX_LEN:
            await MessageHandlers._handle_max_len(update, context, user_id, text)
            return

        elif state == UserState.WAIT_WARN_COUNT:
            await MessageHandlers._handle_warn_count(update, context, user_id, text)
            return

        elif state == UserState.WAIT_PENALTY_DURATION:
            await MessageHandlers._handle_penalty_duration(update, context, user_id, text)
            return

        elif state == UserState.WAIT_VIOLATION_STRIKES:
            await MessageHandlers._handle_violation_strikes(update, context, user_id, text)
            return

        elif state == UserState.WAIT_VIOLATION_DURATION:
            await MessageHandlers._handle_violation_duration(update, context, user_id, text)
            return

        elif state == UserState.WAIT_ANTIFLOOD_MESSAGES:
            await MessageHandlers._handle_antiflood_messages(update, context, user_id, text)
            return

        elif state == UserState.WAIT_ANTIFLOOD_SECONDS:
            await MessageHandlers._handle_antiflood_seconds(update, context, user_id, text)
            return

        elif state == UserState.WAIT_NIGHT_START:
            await MessageHandlers._handle_night_start(update, context, user_id, text)
            return

        elif state == UserState.WAIT_NIGHT_END:
            await MessageHandlers._handle_night_end(update, context, user_id, text)
            return

        elif state == UserState.WAIT_WELCOME_TEXT:
            await MessageHandlers._handle_welcome_text(update, context, user_id, text)
            return

        elif state == UserState.WAIT_GOODBYE_TEXT:
            await MessageHandlers._handle_goodbye_text(update, context, user_id, text)
            return

        elif state == UserState.WAIT_SLOW_MODE_SECONDS:
            await MessageHandlers._handle_slow_mode(update, context, user_id, text)
            return

        elif state == UserState.WAIT_GRANT_FREE:
            await MessageHandlers._handle_grant_free(update, context, user_id, text)
            return

        elif state == UserState.WAIT_IMPORT_FILE:
            await MessageHandlers._handle_import_file(update, context, user_id)
            return

        elif state == UserState.WAIT_GITHUB_URL:
            await MessageHandlers._handle_github_url(update, context, user_id, text)
            return

        elif state == UserState.WAIT_AUTO_KEY:
            await MessageHandlers._handle_auto_key(update, context, user_id, text)
            return

        elif state == UserState.WAIT_MOOD:
            await MessageHandlers._handle_mood(update, context, user_id, text)
            return

        elif state == UserState.WAIT_REDEEM_GIFT:
            await MessageHandlers._handle_redeem_gift(update, context, user_id, text)
            return

        elif state == UserState.SUPPORT_MODE:
            await MessageHandlers._handle_support(update, context, user_id, text)
            return

        elif state == UserState.WAIT_AD_CHANNEL_ID:
            # معالجة إضافة قناة إعلانات - توجيه إلى ad_channels
            from ad_channels import handle_ad_channel_text_message
            await handle_ad_channel_text_message(update, context)
            return

        elif state == UserState.WAIT_AD_PRICE:
            # معالجة تحديد سعر الإعلان - توجيه إلى ad_channels
            from ad_channels import handle_ad_channel_text_message
            await handle_ad_channel_text_message(update, context)
            return

        # ===== معالجة الرسائل العادية =====
        await MessageHandlers._handle_normal_private(update, context, user_id, text)

    @staticmethod
    async def handle_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالج رسائل المجموعات"""
        if not update.effective_chat:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else None

        # تجاهل رسائل البوت
        if user_id == context.bot.id:
            return

        # تجاهل إذا كانت الرسالة من قناة
        if update.message and update.message.sender_chat:
            return

        await METRICS.increment_messages()

        # التحقق من القفل
        locked = await DB.fetchone("SELECT 1 FROM chat_locks WHERE chat_id=? AND locked=1", (chat_id,))
        if locked:
            try:
                await update.message.delete()
            except Exception:
                pass
            return

        # جلب إعدادات الأمان
        settings = await get_security_settings_cached(chat_id)

        # معالجة الرسائل
        text = update.message.text or update.message.caption or ""

        # ===== معالجة الفيضان =====
        if settings.get('antiflood_enabled', 0):
            await MessageHandlers._handle_antiflood(update, context, chat_id, user_id, settings)

        # ===== معالجة الوضع الليلي =====
        if settings.get('night_mode_enabled', 0):
            if await MessageHandlers._is_night_mode(settings):
                await MessageHandlers._handle_night_mode(update, context, chat_id, user_id, settings)
                return

        # ===== معالجة الروابط =====
        if settings.get('delete_links', 0) and TextUtils.contains_link(text):
            await MessageHandlers._handle_violation(update, context, chat_id, user_id, "links", settings)
            return

        # ===== معالجة المعرفات =====
        if settings.get('mentions', 0) and TextUtils.contains_mention(text):
            await MessageHandlers._handle_violation(update, context, chat_id, user_id, "mentions", settings)
            return

        # ===== معالجة الكلمات المحظورة =====
        if settings.get('delete_banned_words', 0):
            if await MessageHandlers._check_banned_words(update, context, chat_id, text):
                return

        # ===== معالجة الحد الأقصى للطول =====
        max_len = settings.get('max_message_length', 0)
        if max_len > 0 and len(text) > max_len:
            await MessageHandlers._handle_violation(update, context, chat_id, user_id, "maxlen", settings)
            return

        # ===== معالجة الوسائط =====
        if update.message:
            await MessageHandlers._handle_media(update, context, chat_id, user_id, settings)

        # ===== معالجة الردود التلقائية =====
        if text:
            await MessageHandlers._handle_auto_reply(update, context, chat_id, user_id, text)

    @staticmethod
    async def handle_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالج رسائل الخدمة (انضمام/مغادرة)"""
        if not update.effective_chat:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else None

        if not update.message:
            return

        # جلب إعدادات الأمان
        settings = await get_security_settings_cached(chat_id)

        # ===== رسائل الترحيب =====
        if settings.get('welcome_enabled', 0) and update.message.new_chat_members:
            await MessageHandlers._handle_welcome(update, context, chat_id, settings)

        # ===== رسائل الوداع =====
        if settings.get('goodbye_enabled', 0) and update.message.left_chat_member:
            await MessageHandlers._handle_goodbye(update, context, chat_id, settings)

        # ===== حذف رسائل الخدمة =====
        if settings.get('delete_service', 0):
            try:
                await update.message.delete()
            except Exception:
                pass

    @staticmethod
    async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالج طلبات الانضمام"""
        chat_id = update.chat_join_request.chat.id
        user_id = update.chat_join_request.from_user.id

        settings = await get_security_settings_cached(chat_id)

        if settings.get('auto_approve_join', 0):
            try:
                await context.bot.approve_chat_join_request(chat_id, user_id)
                logger.info(f"✅ تم قبول طلب انضمام {user_id} في {chat_id}")
            except Exception as e:
                logger.error(f"❌ فشل قبول طلب الانضمام: {e}")

        elif settings.get('auto_reject_join', 0):
            try:
                await context.bot.decline_chat_join_request(chat_id, user_id)
                logger.info(f"✅ تم رفض طلب انضمام {user_id} في {chat_id}")
            except Exception as e:
                logger.error(f"❌ فشل رفض طلب الانضمام: {e}")

    # ==================== دوال معالجة الحالات ====================

    @staticmethod
    async def _handle_adding_posts(update, context, user_id, text):
        """معالجة إضافة منشورات"""
        active = await DB.get_active_channel(user_id)
        if not active:
            await safe_send(context.bot, user_id, "❌ لا توجد قناة نشطة")
            StateManager.clear(user_id)
            return

        # حفظ المنشور
        media_type = None
        media_file_id = None

        if update.message.photo:
            media_type = 'photo'
            media_file_id = update.message.photo[-1].file_id
        elif update.message.video:
            media_type = 'video'
            media_file_id = update.message.video.file_id
        elif update.message.document:
            media_type = 'document'
            media_file_id = update.message.document.file_id
        elif update.message.audio:
            media_type = 'audio'
            media_file_id = update.message.audio.file_id
        elif update.message.voice:
            media_type = 'voice'
            media_file_id = update.message.voice.file_id
        elif update.message.animation:
            media_type = 'animation'
            media_file_id = update.message.animation.file_id
        elif update.message.sticker:
            media_type = 'sticker'
            media_file_id = update.message.sticker.file_id
        elif update.message.video_note:
            media_type = 'video_note'
            media_file_id = update.message.video_note.file_id

        await DB.add_post(active, text, media_type, media_file_id)
        await safe_send(context.bot, user_id, "✅ تم حفظ المنشور")

    @staticmethod
    async def _handle_wait_channel(update, context, user_id, text):
        """معالجة إضافة قناة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            if text.lstrip('-').isdigit():
                channel_id = int(text)
                chat = await context.bot.get_chat(channel_id)
            else:
                chat = await context.bot.get_chat(f"@{text}")
                channel_id = chat.id

            if chat.type not in ['channel']:
                await safe_send(context.bot, user_id, "❌ هذا ليس قناة")
                return

            # التحقق من أن البوت عضو
            try:
                member = await context.bot.get_chat_member(channel_id, context.bot.id)
                if member.status not in ['member', 'administrator', 'creator']:
                    await safe_send(context.bot, user_id, "❌ البوت ليس عضواً في القناة")
                    return
            except Exception:
                await safe_send(context.bot, user_id, "❌ البوت ليس عضواً في القناة")
                return

            ch_id = await DB.add_channel(user_id, channel_id, chat.title)
            if ch_id:
                await safe_send(context.bot, user_id, f"✅ تم إضافة القناة: {chat.title}")
            else:
                await safe_send(context.bot, user_id, "❌ فشل إضافة القناة")
        except Exception as e:
            await safe_send(context.bot, user_id, f"❌ {str(e)[:50]}")

        StateManager.clear(user_id)

    @staticmethod
    async def _handle_schedule_input(update, context, user_id, text, state):
        """معالجة إدخال الجدولة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            value = int(text)
            if value <= 0:
                raise ValueError

            ch_id = context.user_data.get('schedule_ch')
            if not ch_id:
                await safe_send(context.bot, user_id, "❌ لم يتم تحديد قناة")
                StateManager.clear(user_id)
                return

            if state == UserState.WAIT_MIN:
                await DB.update_schedule(ch_id, interval_minutes=value)
                await safe_send(context.bot, user_id, f"✅ تم تعيين الفاصل إلى {value} دقيقة")
            elif state == UserState.WAIT_HOUR:
                await DB.update_schedule(ch_id, interval_hours=value)
                await safe_send(context.bot, user_id, f"✅ تم تعيين الفاصل إلى {value} ساعة")
            elif state == UserState.WAIT_DAY:
                await DB.update_schedule(ch_id, interval_days=value)
                await safe_send(context.bot, user_id, f"✅ تم تعيين الفاصل إلى {value} يوم")
            elif state == UserState.WAIT_PUB_TIME:
                if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', text):
                    await safe_send(context.bot, user_id, "❌ صيغة غير صالحة (HH:MM)")
                    return
                await DB.update_schedule(ch_id, publish_time=text)
                await safe_send(context.bot, user_id, f"✅ تم تعيين وقت النشر إلى {text}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")

        StateManager.clear(user_id)
        context.user_data.pop('schedule_ch', None)

    @staticmethod
    async def _handle_admin_add(update, context, user_id, text):
        """معالجة إضافة مشرف"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            admin_id = int(text)
            if admin_id <= 0:
                raise ValueError
            await DB.add_admin(admin_id)
            await safe_send(context.bot, user_id, f"✅ تم إضافة المشرف {admin_id}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_admin_remove(update, context, user_id, text):
        """معالجة إزالة مشرف"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            admin_id = int(text)
            if admin_id <= 0:
                raise ValueError
            await DB.remove_admin(admin_id)
            await safe_send(context.bot, user_id, f"✅ تم إزالة المشرف {admin_id}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_broadcast(update, context, user_id, text):
        """معالجة البث"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return

        await safe_send(context.bot, user_id, "⏳ جاري البث...")

        users = await DB.get_all_users()
        sent = 0
        failed = 0

        for u in users:
            try:
                await safe_send(context.bot, u['user_id'], text)
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                failed += 1

        await safe_send(context.bot, user_id, f"✅ تم الإرسال إلى {sent} مستخدم\n❌ فشل: {failed}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_update(update, context, user_id, text):
        """معالجة إرسال تحديث"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return

        ch = await DB.get_updates_channel()
        if not ch:
            await safe_send(context.bot, user_id, "❌ لم يتم تعيين قناة تحديثات")
            StateManager.clear(user_id)
            return

        try:
            await safe_send(context.bot, ch, text)
            await safe_send(context.bot, user_id, "✅ تم إرسال التحديث")
        except Exception as e:
            await safe_send(context.bot, user_id, f"❌ {str(e)[:50]}")

        StateManager.clear(user_id)

    @staticmethod
    async def _handle_update_ch(update, context, user_id, text):
        """معالجة تعيين قناة التحديثات"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return

        try:
            if text.lstrip('-').isdigit():
                channel_id = int(text)
            else:
                chat = await context.bot.get_chat(f"@{text}")
                channel_id = chat.id

            await DB.set_updates_channel(channel_id)
            await safe_send(context.bot, user_id, f"✅ تم تعيين قناة التحديثات: {channel_id}")
        except Exception as e:
            await safe_send(context.bot, user_id, f"❌ {str(e)[:50]}")

        StateManager.clear(user_id)

    @staticmethod
    async def _handle_force_sub(update, context, user_id, text):
        """معالجة تعيين الاشتراك الإجباري"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return

        try:
            if text.lower() == "none":
                await DB.set_force_subscribe_channel(None)
                await safe_send(context.bot, user_id, "✅ تم إلغاء الاشتراك الإجباري")
            else:
                if text.lstrip('-').isdigit():
                    channel_id = int(text)
                else:
                    chat = await context.bot.get_chat(f"@{text}")
                    channel_id = chat.id
                await DB.set_force_subscribe_channel(channel_id)
                await safe_send(context.bot, user_id, f"✅ تم تعيين الاشتراك الإجباري: {channel_id}")
        except Exception as e:
            await safe_send(context.bot, user_id, f"❌ {str(e)[:50]}")

        StateManager.clear(user_id)

    @staticmethod
    async def _handle_rem_days(update, context, user_id, text):
        """معالجة تعيين أيام التذكير"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            days = int(text)
            if days < 1 or days > 30:
                raise ValueError
            await DB.update_reminder_settings(user_id, reminder_days=days)
            await safe_send(context.bot, user_id, f"✅ تم تعيين التذكير إلى {days} يوم")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (1-30)")

        StateManager.clear(user_id)

    @staticmethod
    async def _handle_moderation_input(update, context, user_id, text, state):
        """معالجة إدخال الإشراف"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            target = int(text)
            if target <= 0:
                raise ValueError

            chat_id = context.user_data.get('adv_chat')
            if not chat_id:
                await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
                StateManager.clear(user_id)
                return

            # تحديد نوع العقوبة
            penalty_map = {
                UserState.WAIT_BAN: 'ban',
                UserState.WAIT_MUTE: 'mute',
                UserState.WAIT_WARN: 'warn',
                UserState.WAIT_KICK: 'kick',
                UserState.WAIT_RESTRICT: 'restrict',
                UserState.WAIT_UNBAN: 'unban',
            }
            action = penalty_map.get(state, 'mute')

            # التحقق من الصلاحيات
            if not await is_authorized_in_group(context.bot, chat_id, user_id):
                await safe_send(context.bot, user_id, "❌ لا صلاحية")
                StateManager.clear(user_id)
                return

            if await is_authorized_in_group(context.bot, chat_id, target):
                await safe_send(context.bot, user_id, "❌ لا يمكن معاملة مشرف")
                StateManager.clear(user_id)
                return

            duration = 3600  # افتراضي
            if action in ['ban', 'mute', 'restrict']:
                duration = context.user_data.get('duration', 3600)

            success, msg = await apply_penalty(
                context.bot, chat_id, target, action, duration,
                reason="عن طريق الأمر", moderator=user_id
            )
            await safe_send(context.bot, user_id, msg)

        except ValueError:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")

        StateManager.clear(user_id)
        context.user_data.pop('adv_chat', None)
        context.user_data.pop('duration', None)

    @staticmethod
    async def _handle_pin(update, context, user_id):
        """معالجة تثبيت رسالة"""
        chat_id = context.user_data.get('adv_chat')
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
            StateManager.clear(user_id)
            return

        if update.message.reply_to_message:
            try:
                await context.bot.pin_chat_message(chat_id, update.message.reply_to_message.message_id)
                await safe_send(context.bot, user_id, "📌 تم التثبيت")
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ {str(e)[:50]}")
        else:
            await safe_send(context.bot, user_id, "❌ قم بالرد على الرسالة المطلوب تثبيتها")

        StateManager.clear(user_id)
        context.user_data.pop('adv_chat', None)

    @staticmethod
    async def _handle_group_ban(update, context, user_id, text):
        """معالجة إضافة كلمة محظورة للمجموعة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        chat_id = context.user_data.get('ban_chat')
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
            StateManager.clear(user_id)
            return

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ لا صلاحية")
            StateManager.clear(user_id)
            return

        word = text.strip().lower()
        if len(word) < 2:
            await safe_send(context.bot, user_id, "❌ الكلمة قصيرة جداً")
            return

        await DB.add_banned_word(chat_id, word)
        invalidate_banned_words_cache(chat_id)
        await safe_send(context.bot, user_id, f"✅ تم إضافة: {word}")
        StateManager.clear(user_id)
        context.user_data.pop('ban_chat', None)

    @staticmethod
    async def _handle_rem_group_ban(update, context, user_id, text):
        """معالجة حذف كلمة محظورة من المجموعة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        chat_id = context.user_data.get('ban_chat')
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
            StateManager.clear(user_id)
            return

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ لا صلاحية")
            StateManager.clear(user_id)
            return

        word = text.strip().lower()
        await DB.remove_banned_word(chat_id, word)
        invalidate_banned_words_cache(chat_id)
        await safe_send(context.bot, user_id, f"✅ تم حذف: {word}")
        StateManager.clear(user_id)
        context.user_data.pop('ban_chat', None)

    @staticmethod
    async def _handle_global_ban(update, context, user_id, text):
        """معالجة إضافة كلمة محظورة عامة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return

        word = text.strip().lower()
        if len(word) < 2:
            await safe_send(context.bot, user_id, "❌ الكلمة قصيرة جداً")
            return

        await DB.add_banned_word(-1, word)
        invalidate_banned_words_cache(-1)
        await safe_send(context.bot, user_id, f"✅ تم إضافة الكلمة العامة: {word}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_rem_global_ban(update, context, user_id, text):
        """معالجة حذف كلمة محظورة عامة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return

        word = text.strip().lower()
        await DB.remove_banned_word(-1, word)
        invalidate_banned_words_cache(-1)
        await safe_send(context.bot, user_id, f"✅ تم حذف الكلمة العامة: {word}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_add_reply(update, context, user_id, text):
        """معالجة إضافة رد تلقائي"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        chat_id = context.user_data.get('auto_chat', -1)
        context.user_data['auto_keyword'] = text.strip().lower()
        StateManager.set(user_id, UserState.WAIT_AUTO_REPLY)
        await safe_send(context.bot, user_id, "📝 أرسل الرد:")

    @staticmethod
    async def _handle_auto_reply_input(update, context, user_id, text):
        """معالجة إدخال الرد التلقائي"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        chat_id = context.user_data.get('auto_chat', -1)
        keyword = context.user_data.get('auto_keyword', '')

        if not keyword:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد الكلمة")
            StateManager.clear(user_id)
            return

        await DB.add_auto_reply(chat_id, keyword, text.strip())
        await safe_send(context.bot, user_id, f"✅ تم إضافة الرد للكلمة: {keyword}")
        StateManager.clear(user_id)
        context.user_data.pop('auto_keyword', None)
        context.user_data.pop('auto_chat', None)

    @staticmethod
    async def _handle_auto_del(update, context, user_id, text):
        """معالجة حذف رد تلقائي"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        chat_id = context.user_data.get('auto_chat', -1)
        keyword = text.strip().lower()

        await DB.remove_auto_reply(chat_id, keyword)
        await safe_send(context.bot, user_id, f"✅ تم حذف الرد للكلمة: {keyword}")
        StateManager.clear(user_id)
        context.user_data.pop('auto_chat', None)

    @staticmethod
    async def _handle_contest_title(update, context, user_id, text):
        """معالجة عنوان المسابقة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        context.user_data['contest_title'] = text.strip()
        StateManager.set(user_id, UserState.WAIT_CONTEST_DESC)
        await safe_send(context.bot, user_id, "📝 أرسل وصف المسابقة:")

    @staticmethod
    async def _handle_contest_desc(update, context, user_id, text):
        """معالجة وصف المسابقة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        context.user_data['contest_desc'] = text.strip()
        StateManager.set(user_id, UserState.WAIT_CONTEST_PRIZE)
        await safe_send(context.bot, user_id, "🎁 أرسل الجائزة:")

    @staticmethod
    async def _handle_contest_prize(update, context, user_id, text):
        """معالجة جائزة المسابقة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        context.user_data['contest_prize'] = text.strip()
        StateManager.set(user_id, UserState.WAIT_CONTEST_DATE)
        await safe_send(context.bot, user_id, "📅 أرسل تاريخ الانتهاء (YYYY-MM-DD):")

    @staticmethod
    async def _handle_contest_date(update, context, user_id, text):
        """معالجة تاريخ المسابقة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            end_date = datetime.strptime(text.strip(), '%Y-%m-%d')
            if end_date < datetime.now():
                await safe_send(context.bot, user_id, "❌ التاريخ يجب أن يكون في المستقبل")
                return

            contest_id = await DB.create_contest(
                title=context.user_data.get('contest_title', ''),
                description=context.user_data.get('contest_desc', ''),
                prize=context.user_data.get('contest_prize', ''),
                end_date=end_date,
                created_by=user_id
            )

            if contest_id:
                await safe_send(context.bot, user_id, f"✅ تم إنشاء المسابقة ID: {contest_id}")
            else:
                await safe_send(context.bot, user_id, "❌ فشل إنشاء المسابقة")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ صيغة تاريخ غير صالحة (YYYY-MM-DD)")

        StateManager.clear(user_id)
        context.user_data.pop('contest_title', None)
        context.user_data.pop('contest_desc', None)
        context.user_data.pop('contest_prize', None)

    @staticmethod
    async def _handle_contest_answer(update, context, user_id, text):
        """معالجة إجابة المسابقة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        contest_id = context.user_data.get('contest_join')
        if not contest_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المسابقة")
            StateManager.clear(user_id)
            return

        await DB.add_contest_participant(contest_id, user_id, text.strip())
        await safe_send(context.bot, user_id, "✅ تم تسجيل مشاركتك!")
        StateManager.clear(user_id)
        context.user_data.pop('contest_join', None)

    @staticmethod
    async def _handle_contest_winner(update, context, user_id, text):
        """معالجة إعلان فائز"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            contest_id = int(text.strip())
            winner = await DB.fetchone(
                "SELECT user_id FROM contest_participants WHERE contest_id=? ORDER BY RANDOM() LIMIT 1",
                (contest_id,)
            )
            if winner:
                await DB.declare_winner(contest_id, winner['user_id'])
                await safe_send(context.bot, user_id, f"✅ الفائز: {winner['user_id']}")
            else:
                await safe_send(context.bot, user_id, "❌ لا يوجد مشاركون")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")

        StateManager.clear(user_id)

    @staticmethod
    async def _handle_max_len(update, context, user_id, text):
        """معالجة تعيين الحد الأقصى للطول"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            value = int(text)
            if value < 0:
                raise ValueError

            chat_id = context.user_data.get('sec_chat')
            if not chat_id:
                await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
                StateManager.clear(user_id)
                return

            await DB.update_security_settings(chat_id, max_message_length=value)
            await safe_send(context.bot, user_id, f"✅ تم تعيين الحد الأقصى إلى {value}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")

        StateManager.clear(user_id)
        context.user_data.pop('sec_chat', None)

    @staticmethod
    async def _handle_warn_count(update, context, user_id, text):
        """معالجة تعيين عدد التحذيرات"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            value = int(text)
            if value < 1 or value > 10:
                raise ValueError

            chat_id = context.user_data.get('sec_chat')
            if not chat_id:
                await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
                StateManager.clear(user_id)
                return

            await DB.update_security_settings(chat_id, max_warnings=value)
            await safe_send(context.bot, user_id, f"✅ تم تعيين عدد التحذيرات إلى {value}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (1-10)")

        StateManager.clear(user_id)
        context.user_data.pop('sec_chat', None)

    @staticmethod
    async def _handle_penalty_duration(update, context, user_id, text):
        """معالجة تعيين مدة العقوبة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            minutes = int(text)
            if minutes < 0:
                raise ValueError
            seconds = minutes * 60

            chat_id = context.user_data.get('adv_chat')
            if not chat_id:
                await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
                StateManager.clear(user_id)
                return

            await DB.update_security_settings(chat_id, delete_penalty_duration=seconds)
            await safe_send(context.bot, user_id, f"✅ تم تعيين المدة إلى {minutes} دقيقة")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")

        StateManager.clear(user_id)
        context.user_data.pop('adv_chat', None)

    @staticmethod
    async def _handle_violation_strikes(update, context, user_id, text):
        """معالجة تعيين عدد ضربات المخالفة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            value = int(text)
            if value < 1 or value > 10:
                raise ValueError

            chat_id = context.user_data.get('sec_chat')
            if not chat_id:
                await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
                StateManager.clear(user_id)
                return

            await DB.update_security_settings(chat_id, violation_strikes=value)
            await safe_send(context.bot, user_id, f"✅ تم تعيين عدد الضربات إلى {value}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (1-10)")

        StateManager.clear(user_id)
        context.user_data.pop('sec_chat', None)

    @staticmethod
    async def _handle_violation_duration(update, context, user_id, text):
        """معالجة تعيين مدة المخالفة"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            seconds = int(text)
            if seconds < 0:
                raise ValueError

            chat_id = context.user_data.get('sec_chat')
            if not chat_id:
                await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
                StateManager.clear(user_id)
                return

            await DB.update_security_settings(chat_id, violation_duration=seconds)
            await safe_send(context.bot, user_id, f"✅ تم تعيين المدة إلى {seconds} ثانية")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")

        StateManager.clear(user_id)
        context.user_data.pop('sec_chat', None)

    @staticmethod
    async def _handle_antiflood_messages(update, context, user_id, text):
        """معالجة تعيين عدد رسائل الفيضان"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            value = int(text)
            if value < 1 or value > 100:
                raise ValueError

            chat_id = context.user_data.get('sec_chat')
            if not chat_id:
                await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
                StateManager.clear(user_id)
                return

            await DB.update_security_settings(chat_id, antiflood_messages=value)
            await safe_send(context.bot, user_id, f"✅ تم تعيين عدد الرسائل إلى {value}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (1-100)")

        StateManager.clear(user_id)
        context.user_data.pop('sec_chat', None)

    @staticmethod
    async def _handle_antiflood_seconds(update, context, user_id, text):
        """معالجة تعيين ثواني الفيضان"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            seconds = int(text)
            if seconds < 1 or seconds > 3600:
                raise ValueError

            chat_id = context.user_data.get('sec_chat')
            if not chat_id:
                await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
                StateManager.clear(user_id)
                return

            await DB.update_security_settings(chat_id, antiflood_seconds=seconds)
            await safe_send(context.bot, user_id, f"✅ تم تعيين الفترة إلى {seconds} ثانية")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (1-3600)")

        StateManager.clear(user_id)
        context.user_data.pop('sec_chat', None)

    @staticmethod
    async def _handle_night_start(update, context, user_id, text):
        """معالجة تعيين وقت بدء الوضع الليلي"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', text):
            await safe_send(context.bot, user_id, "❌ صيغة غير صالحة (HH:MM)")
            return

        chat_id = context.user_data.get('sec_chat')
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
            StateManager.clear(user_id)
            return

        await DB.update_security_settings(chat_id, night_start=text)
        await safe_send(context.bot, user_id, f"✅ تم تعيين وقت البدء إلى {text}")
        StateManager.clear(user_id)
        context.user_data.pop('sec_chat', None)

    @staticmethod
    async def _handle_night_end(update, context, user_id, text):
        """معالجة تعيين وقت نهاية الوضع الليلي"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', text):
            await safe_send(context.bot, user_id, "❌ صيغة غير صالحة (HH:MM)")
            return

        chat_id = context.user_data.get('sec_chat')
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
            StateManager.clear(user_id)
            return

        await DB.update_security_settings(chat_id, night_end=text)
        await safe_send(context.bot, user_id, f"✅ تم تعيين وقت النهاية إلى {text}")
        StateManager.clear(user_id)
        context.user_data.pop('sec_chat', None)

    @staticmethod
    async def _handle_welcome_text(update, context, user_id, text):
        """معالجة تعيين نص الترحيب"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        chat_id = context.user_data.get('sec_chat')
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
            StateManager.clear(user_id)
            return

        await DB.update_security_settings(chat_id, welcome_text=text.strip())
        await safe_send(context.bot, user_id, "✅ تم تعيين نص الترحيب")
        StateManager.clear(user_id)
        context.user_data.pop('sec_chat', None)

    @staticmethod
    async def _handle_goodbye_text(update, context, user_id, text):
        """معالجة تعيين نص الوداع"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        chat_id = context.user_data.get('sec_chat')
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
            StateManager.clear(user_id)
            return

        await DB.update_security_settings(chat_id, goodbye_text=text.strip())
        await safe_send(context.bot, user_id, "✅ تم تعيين نص الوداع")
        StateManager.clear(user_id)
        context.user_data.pop('sec_chat', None)

    @staticmethod
    async def _handle_slow_mode(update, context, user_id, text):
        """معالجة تعيين الوضع البطيء"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        try:
            seconds = int(text)
            if seconds < 0 or seconds > 3600:
                raise ValueError

            chat_id = context.user_data.get('sec_chat')
            if not chat_id:
                await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
                StateManager.clear(user_id)
                return

            await DB.update_security_settings(chat_id, slow_mode=seconds)
            await safe_send(context.bot, user_id, f"✅ تم تعيين الوضع البطيء إلى {seconds} ثانية")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (0-3600)")

        StateManager.clear(user_id)
        context.user_data.pop('sec_chat', None)

    @staticmethod
    async def _handle_grant_free(update, context, user_id, text):
        """معالجة منح اشتراك مجاني"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return

        parts = text.strip().split()
        if len(parts) < 2:
            await safe_send(context.bot, user_id, "❌ استخدم: معرف_المستخدم عدد_الأيام")
            return

        try:
            target_id = int(parts[0])
            days = int(parts[1])
            if target_id <= 0 or days < 1 or days > 365:
                raise ValueError

            await DB.grant_subscription_days(target_id, days, provider='free_grant')
            await safe_send(context.bot, user_id, f"✅ تم منح {days} يوم للمستخدم {target_id}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيم غير صالحة")

        StateManager.clear(user_id)

    @staticmethod
    async def _handle_import_file(update, context, user_id):
        """معالجة استيراد ملف"""
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return

        if update.message.document:
            file = update.message.document
            if file.file_name and file.file_name.endswith('.json'):
                try:
                    file_obj = await context.bot.get_file(file.file_id)
                    import io
                    file_content = await file_obj.download_as_bytearray()
                    import json
                    data = json.loads(file_content.decode('utf-8'))

                    from utils import import_auto_replies
                    count = await import_auto_replies(-1, data, overwrite=True)
                    await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
                except Exception as e:
                    await safe_send(context.bot, user_id, f"❌ فشل الاستيراد: {str(e)[:50]}")
            else:
                await safe_send(context.bot, user_id, "❌ يرجى إرسال ملف JSON")
        else:
            await safe_send(context.bot, user_id, "❌ يرجى إرسال ملف")

        StateManager.clear(user_id)

    @staticmethod
    async def _handle_github_url(update, context, user_id, text):
        """معالجة استيراد من GitHub"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return

        from utils import fetch_json_from_url, import_auto_replies
        data = await fetch_json_from_url(text.strip())
        if data:
            count = await import_auto_replies(-1, data, overwrite=True)
            await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد من GitHub")
        else:
            await safe_send(context.bot, user_id, "❌ فشل جلب البيانات")

        StateManager.clear(user_id)

    @staticmethod
    async def _handle_auto_key(update, context, user_id, text):
        """معالجة إضافة رد تلقائي (نظام الردود التلقائية)"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        chat_id = context.user_data.get('auto_chat')
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد مجموعة")
            StateManager.clear(user_id)
            return

        context.user_data['auto_keyword'] = text.strip().lower()
        StateManager.set(user_id, UserState.WAIT_REPLY)
        await safe_send(context.bot, user_id, "📝 أرسل الرد:")

    @staticmethod
    async def _handle_mood(update, context, user_id, text):
        """معالجة تحليل المشاعر"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        result = analyze_sentiment(text)
        response = (
            f"{result['emoji']} <b>تحليل المشاعر</b>\n\n"
            f"📝 النص: <code>{html.escape(text[:100])}</code>\n"
            f"🎯 النتيجة: <b>{result['sentiment']}</b>\n\n"
            f"😊 إيجابي: {result['positive_percent']:.0f}%\n"
            f"😔 سلبي: {result['negative_percent']:.0f}%\n"
            f"📊 الكلمات: {result['total_words']}"
        )
        await safe_send(context.bot, user_id, response, parse_mode='HTML')
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_redeem_gift(update, context, user_id, text):
        """معالجة استرداد كود هدية"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        code = text.strip()
        if len(code) < 4:
            await safe_send(context.bot, user_id, "❌ كود غير صالح")
            StateManager.clear(user_id)
            return

        success, days = await DB.redeem_gift_code(user_id, code)
        if success and days > 0:
            await safe_send(context.bot, user_id, f"🎉 تم تفعيل اشتراك {days} يوم")
        elif days == -1:
            await safe_send(context.bot, user_id, "❌ لا يمكنك استخدام كودك الخاص")
        else:
            await safe_send(context.bot, user_id, "❌ كود غير صالح")

        StateManager.clear(user_id)

    @staticmethod
    async def _handle_support(update, context, user_id, text):
        """معالجة رسالة الدعم"""
        if text.lower() in ["إلغاء", "cancel", "/cancel"]:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ تم الإلغاء")
            return

        ticket_number = await DB.add_ticket(user_id, text.strip())
        if ticket_number:
            await safe_send(context.bot, user_id, f"✅ تم استلام رسالتك (رقم التذكرة: {ticket_number})")
            # إشعار المطورين
            for dev_id in CONFIG.DEVELOPER_IDS:
                try:
                    await safe_send(
                        context.bot, dev_id,
                        f"🎫 تذكرة جديدة #{ticket_number}\n"
                        f"👤 المستخدم: {user_id}\n"
                        f"📝 الرسالة: {text[:200]}"
                    )
                except Exception:
                    pass
        else:
            await safe_send(context.bot, user_id, "❌ فشل إرسال الرسالة")

        StateManager.clear(user_id)

    @staticmethod
    async def _handle_normal_private(update, context, user_id, text):
        """معالجة الرسائل الخاصة العادية"""
        if text and text.startswith('/'):
            return

        # ردود تلقائية عامة
        from utils import get_reply_from_file
        reply = get_reply_from_file(text)
        if reply:
            await safe_send(context.bot, user_id, reply)

    # ==================== دوال معالجة المجموعات ====================

    @staticmethod
    async def _handle_antiflood(update, context, chat_id, user_id, settings):
        """معالجة الفيضان"""
        if await is_authorized_in_group(context.bot, chat_id, user_id):
            return

        # سجل وقت الرسالة
        key = f"flood_{chat_id}_{user_id}"
        now = time.time()
        messages = context.bot_data.get(key, [])
        messages.append(now)

        # احتفظ بالرسائل في الفترة الزمنية
        period = settings.get('antiflood_seconds', 10)
        messages = [t for t in messages if now - t < period]
        context.bot_data[key] = messages

        limit = settings.get('antiflood_messages', 5)
        if len(messages) > limit:
            try:
                await update.message.delete()
            except Exception:
                pass

            penalty = await _get_penalty_action(settings, 'mute')
            duration = await _get_penalty_duration(settings, 'antiflood')

            if penalty != 'none':
                await apply_penalty(
                    context.bot, chat_id, user_id, penalty, duration,
                    reason="تجاوز حد الفيضان"
                )

            context.bot_data[key] = []

    @staticmethod
    async def _is_night_mode(settings: dict) -> bool:
        """التحقق من أن الوقت في الوضع الليلي"""
        start = settings.get('night_start', '')
        end = settings.get('night_end', '')
        if not start or not end:
            return False

        now = datetime.now().time()
        try:
            start_time = datetime.strptime(start, '%H:%M').time()
            end_time = datetime.strptime(end, '%H:%M').time()
        except ValueError:
            return False

        if start_time < end_time:
            return start_time <= now <= end_time
        else:
            return now >= start_time or now <= end_time

    @staticmethod
    async def _handle_night_mode(update, context, chat_id, user_id, settings):
        """معالجة الوضع الليلي"""
        if await is_authorized_in_group(context.bot, chat_id, user_id):
            return

        try:
            await update.message.delete()
        except Exception:
            pass

        penalty = settings.get('night_action', 'mute')
        duration = await _get_penalty_duration(settings, 'night')

        if penalty != 'none':
            await apply_penalty(
                context.bot, chat_id, user_id, penalty, duration,
                reason="رسالة في الوضع الليلي"
            )

    @staticmethod
    async def _handle_violation(update, context, chat_id, user_id, violation_type, settings):
        """معالجة المخالفات"""
        if await is_authorized_in_group(context.bot, chat_id, user_id):
            return

        # حذف الرسالة
        try:
            await update.message.delete()
        except Exception:
            pass

        # تسجيل المخالفة
        strikes = await DB.add_violation(user_id, chat_id, violation_type)

        # تطبيق العقوبة إذا تجاوز الحد
        max_strikes = settings.get('violation_strikes', 3)
        if strikes >= max_strikes:
            duration = settings.get('violation_duration', 60)
            penalty = await _get_penalty_action(settings, 'mute')

            if penalty != 'none':
                await apply_penalty(
                    context.bot, chat_id, user_id, penalty, duration,
                    reason=f"تجاوز حد المخالفات ({violation_type})"
                )
                await DB.reset_violations(user_id, chat_id)

    @staticmethod
    async def _check_banned_words(update, context, chat_id, text) -> bool:
        """التحقق من الكلمات المحظورة"""
        if not text:
            return False

        banned_words = await get_banned_words_cached(chat_id)
        if not banned_words:
            return False

        text_lower = text.lower()
        for word in banned_words:
            if word in text_lower:
                try:
                    await update.message.delete()
                except Exception:
                    pass

                settings = await get_security_settings_cached(chat_id)
                penalty = settings.get('auto_penalty', 'mute')
                duration = await _get_penalty_duration(settings, penalty)

                await apply_penalty(
                    context.bot, chat_id, update.effective_user.id,
                    penalty, duration, reason=f"كلمة محظورة: {word}"
                )
                return True

        return False

    @staticmethod
    async def _handle_media(update, context, chat_id, user_id, settings):
        """معالجة الوسائط"""
        if await is_authorized_in_group(context.bot, chat_id, user_id):
            return

        message = update.message
        should_delete = False
        media_type = None

        if message.photo:
            should_delete = settings.get('delete_photos', 0)
            media_type = 'photo'
        elif message.video:
            should_delete = settings.get('delete_videos', 0)
            media_type = 'video'
        elif message.audio:
            should_delete = settings.get('delete_audio', 0)
            media_type = 'audio'
        elif message.voice:
            should_delete = settings.get('delete_voice', 0)
            media_type = 'voice'
        elif message.document:
            should_delete = settings.get('delete_documents', 0)
            media_type = 'document'
        elif message.sticker:
            should_delete = settings.get('delete_stickers', 0)
            media_type = 'sticker'
        elif message.animation:
            should_delete = settings.get('delete_animation', 0)
            media_type = 'animation'
        elif message.video_note:
            should_delete = settings.get('delete_video_note', 0)
            media_type = 'video_note'
        elif message.poll:
            should_delete = settings.get('delete_polls', 0)
            media_type = 'poll'
        elif message.game:
            should_delete = settings.get('delete_games', 0)
            media_type = 'game'

        if should_delete:
            try:
                await message.delete()
            except Exception:
                pass

    @staticmethod
    async def _handle_auto_reply(update, context, chat_id, user_id, text):
        """معالجة الردود التلقائية"""
        if not text:
            return

        # التحقق من الإعدادات
        settings = await get_auto_reply_settings_cached(chat_id)
        if not settings.get('enabled', False):
            return

        # التحقق من صلاحية المشرفين
        if settings.get('only_admins', 0):
            if not await is_authorized_in_group(context.bot, chat_id, user_id):
                return

        # البحث عن رد
        text_lower = text.lower().strip()
        reply_data = await DB.get_auto_reply(chat_id, text_lower)

        if not reply_data:
            # البحث عن رد عام
            reply_data = await DB.get_auto_reply(-1, text_lower)

        if reply_data:
            reply_text = reply_data.get('reply', '')
            reply_type = reply_data.get('reply_type', 'text')
            media_id = reply_data.get('media_file_id')
            buttons = reply_data.get('buttons')

            reply_markup = None
            if buttons:
                try:
                    import json
                    btn_data = json.loads(buttons) if isinstance(buttons, str) else buttons
                    keyboard = []
                    for row in btn_data:
                        btn_row = []
                        for btn in row:
                            btn_row.append(InlineKeyboardButton(btn['text'], callback_data=btn['callback']))
                        keyboard.append(btn_row)
                    reply_markup = InlineKeyboardMarkup(keyboard)
                except Exception:
                    pass

            # إرسال الرد
            if reply_type == 'text':
                await safe_send(context.bot, chat_id, reply_text, reply_markup=reply_markup)
            elif reply_type in ['photo', 'video', 'document', 'audio', 'voice', 'animation', 'sticker', 'video_note'] and media_id:
                kwargs = {
                    'chat_id': chat_id,
                    'text': reply_text if reply_text else None,
                    'reply_markup': reply_markup
                }
                if reply_type == 'photo':
                    await safe_send(context.bot, chat_id, photo=media_id, **kwargs)
                elif reply_type == 'video':
                    await safe_send(context.bot, chat_id, video=media_id, **kwargs)
                elif reply_type == 'document':
                    await safe_send(context.bot, chat_id, document=media_id, **kwargs)
                elif reply_type == 'audio':
                    await safe_send(context.bot, chat_id, audio=media_id, **kwargs)
                elif reply_type == 'voice':
                    await safe_send(context.bot, chat_id, voice=media_id, **kwargs)
                elif reply_type == 'animation':
                    await safe_send(context.bot, chat_id, animation=media_id, **kwargs)
                elif reply_type == 'sticker':
                    await safe_send(context.bot, chat_id, sticker=media_id, **kwargs)
                elif reply_type == 'video_note':
                    await safe_send(context.bot, chat_id, video_note=media_id, **kwargs)

            # تحديث الإحصائيات
            try:
                from utils import _increment_usage_async
                await _increment_usage_async(chat_id, text_lower)
            except Exception:
                pass

    @staticmethod
    async def _handle_welcome(update, context, chat_id, settings):
        """معالجة رسالة الترحيب"""
        welcome_text = settings.get('welcome_text', '')
        if not welcome_text:
            welcome_text = "👋 مرحباً بك في المجموعة!"

        for member in update.message.new_chat_members:
            if member.id == context.bot.id:
                continue
            try:
                text = welcome_text.replace('{user}', member.first_name or '')
                await safe_send(context.bot, chat_id, text)
            except Exception:
                pass

    @staticmethod
    async def _handle_goodbye(update, context, chat_id, settings):
        """معالجة رسالة الوداع"""
        goodbye_text = settings.get('goodbye_text', '')
        if not goodbye_text:
            goodbye_text = "👋 وداعاً!"

        member = update.message.left_chat_member
        if member.id == context.bot.id:
            return

        try:
            text = goodbye_text.replace('{user}', member.first_name or '')
            await safe_send(context.bot, chat_id, text)
        except Exception:
            pass
