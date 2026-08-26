#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_message.py - معالجات الرسائل - النسخة النهائية الكاملة
=====================================================================
- معالجة شاملة لجميع الأخطاء المحتملة
- تحسينات أمنية وأداء
- تنظيم أفضل للكود
- توثيق محسّن
"""

import asyncio
import logging
import time
import os
import re
import json
import tempfile
from html import escape
from typing import Optional, Dict, Any, List, Tuple, Union, Set
from functools import lru_cache

from telegram import Update, Message
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TimedOut, Forbidden

from config import CONFIG
from database import DB
from utils import (
    safe_send, is_authorized_in_group, apply_penalty,
    METRICS, StateManager, UserState,
    get_banned_words_cached, invalidate_banned_words_cache,
    get_reply_from_file, _increment_usage_async,
    fetch_json_from_url, import_auto_replies,
    TextUtils
)

from replies import analyze_sentiment

logger = logging.getLogger(__name__)

# =====================================================================
# الإعدادات والثوابت
# =====================================================================

CACHE_TTL_SECURITY = 30
CACHE_TTL_AUTO_REPLY = 60
MAX_MESSAGE_LENGTH = 4096
MAX_WARNINGS_DEFAULT = 3
DEFAULT_MUTE_DURATION = 60
BROADCAST_DELAY = 0.1
FETCH_TIMEOUT = 10
MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024
MAX_TEXT_ANALYSIS_LENGTH = 1000
MAX_TICKET_LENGTH = 2000
MAX_BROADCAST_LENGTH = 4000
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000
MAX_PRIZE_LENGTH = 200
VIOLATION_RESET_TIME = 3600

# =====================================================================
# إدارة الكاش المحسّنة
# =====================================================================

class CacheManager:
    """إدارة الكاش مع قفل للوصول المتزامن وتنظيف تلقائي"""
    
    def __init__(self):
        self._security_settings: Dict[int, Dict[str, Any]] = {}
        self._security_time: Dict[int, float] = {}
        self._auto_reply_settings: Dict[int, Dict[str, Any]] = {}
        self._auto_reply_time: Dict[int, float] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._last_cleanup: float = time.time()
    
    def _get_lock(self, key: str) -> asyncio.Lock:
        """الحصول على قفل مع تنظيف دوري"""
        now = time.time()
        if now - self._last_cleanup > 3600:
            self._cleanup_locks()
            self._last_cleanup = now
        
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]
    
    def _cleanup_locks(self) -> None:
        """تنظيف الأقفال غير المستخدمة"""
        # في asyncio، الأقفال خفيفة ولا تحتاج تنظيف فعلي
        # لكن نحتفظ بالطريقة للتوافق المستقبلي
        pass
    
    async def get_security_settings(self, chat_id: int, ttl: int = CACHE_TTL_SECURITY) -> Dict[str, Any]:
        """جلب إعدادات الأمان مع التخزين المؤقت"""
        now = time.time()
        cache_key = f"sec_{chat_id}"
        
        async with self._get_lock(cache_key):
            if chat_id in self._security_settings:
                if now - self._security_time.get(chat_id, 0) < ttl:
                    return self._security_settings[chat_id].copy()
            
            try:
                settings = await DB.get_security_settings(chat_id)
                if settings is None:
                    settings = {}
                self._security_settings[chat_id] = settings
                self._security_time[chat_id] = now
                return settings.copy()
            except Exception as e:
                logger.error(f"فشل جلب إعدادات الأمان للمجموعة {chat_id}: {e}")
                if chat_id in self._security_settings:
                    return self._security_settings[chat_id].copy()
                return {}
    
    async def get_auto_reply_settings(self, chat_id: int, ttl: int = CACHE_TTL_AUTO_REPLY) -> Dict[str, Any]:
        """جلب إعدادات الردود التلقائية مع التخزين المؤقت"""
        now = time.time()
        cache_key = f"ar_{chat_id}"
        
        async with self._get_lock(cache_key):
            if chat_id in self._auto_reply_settings:
                if now - self._auto_reply_time.get(chat_id, 0) < ttl:
                    return self._auto_reply_settings[chat_id].copy()
            
            try:
                settings = await DB.get_auto_reply_settings(chat_id)
                if settings is None:
                    settings = {}
                self._auto_reply_settings[chat_id] = settings
                self._auto_reply_time[chat_id] = now
                return settings.copy()
            except Exception as e:
                logger.error(f"فشل جلب إعدادات الردود للمجموعة {chat_id}: {e}")
                if chat_id in self._auto_reply_settings:
                    return self._auto_reply_settings[chat_id].copy()
                return {}
    
    async def invalidate_security(self, chat_id: Optional[int] = None) -> None:
        """إبطال الكاش الأمني"""
        if chat_id:
            self._security_settings.pop(chat_id, None)
            self._security_time.pop(chat_id, None)
        else:
            self._security_settings.clear()
            self._security_time.clear()
    
    async def invalidate_auto_reply(self, chat_id: Optional[int] = None) -> None:
        """إبطال كاش الردود التلقائية"""
        if chat_id:
            self._auto_reply_settings.pop(chat_id, None)
            self._auto_reply_time.pop(chat_id, None)
        else:
            self._auto_reply_settings.clear()
            self._auto_reply_time.clear()

cache_manager = CacheManager()

# =====================================================================
# دوال مساعدة
# =====================================================================

async def _delete_after_delay(bot, chat_id: int, message_id: int, delay: int = 10):
    """حذف رسالة بعد تأخير مع معالجة الأخطاء"""
    if not bot:
        return
    
    try:
        await asyncio.sleep(delay)
        await bot.delete_message(chat_id, message_id)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


def _is_valid_time(time_str: str) -> bool:
    """التحقق من أن السلسلة تمثل وقتًا صالحًا بصيغة HH:MM"""
    if not time_str or not re.match(r'^\d{1,2}:\d{2}$', time_str):
        return False
    try:
        hours, minutes = map(int, time_str.split(':'))
        return 0 <= hours <= 23 and 0 <= minutes <= 59
    except (ValueError, TypeError):
        return False


def _extract_channel_id(channel_data: Any) -> Optional[int]:
    """استخراج معرف القناة من بيانات متنوعة"""
    if channel_data is None:
        return None
    
    if isinstance(channel_data, dict):
        for key in ('id', 'channel_id', 'chat_id', 'telegram_id'):
            val = channel_data.get(key)
            if val:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    continue
    else:
        for attr in ('id', 'channel_id', 'chat_id', 'telegram_id'):
            val = getattr(channel_data, attr, None)
            if val:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    continue
    return None


def _safe_int(value: Any, default: int = 0) -> int:
    """تحويل آمن إلى رقم صحيح"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _truncate_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> str:
    """قص النص إلى الطول المسموح"""
    if not text:
        return ""
    return text[:max_length]


def _sanitize_html(text: str) -> str:
    """تنظيف النص من HTML tags الخطيرة"""
    if not text:
        return ""
    dangerous_tags = ['<script', '</script>', '<iframe', '</iframe>']
    for tag in dangerous_tags:
        text = text.replace(tag, '')
    return text


async def _check_bot_is_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    """التحقق من أن البوت مشرف في المجموعة"""
    try:
        bot_id = context.bot.id
        bot_member = await context.bot.get_chat_member(chat_id, bot_id)
        return bot_member.status in ['administrator', 'creator']
    except Exception as e:
        logger.warning(f"تعذر التحقق من صلاحيات البوت في {chat_id}: {e}")
        return False


async def _check_user_is_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    """التحقق من أن المستخدم مشرف في المجموعة"""
    if user_id == CONFIG.PRIMARY_OWNER_ID:
        return True
    try:
        return await is_authorized_in_group(context.bot, chat_id, user_id)
    except Exception as e:
        logger.warning(f"تعذر التحقق من صلاحية المستخدم {user_id} في {chat_id}: {e}")
        return False


def _cleanup_user_data(context: ContextTypes.DEFAULT_TYPE, keys: List[str]) -> None:
    """تنظيف مفاتيح محددة من user_data"""
    for key in keys:
        context.user_data.pop(key, None)


async def apply_violation_penalty(context: ContextTypes.DEFAULT_TYPE, 
                                  chat_id: int, user_id: int, violation_type: str,
                                  penalty_type: str, duration_seconds: int) -> Tuple[bool, str]:
    """تطبيق عقوبة مع معالجة الأخطاء"""
    try:
        success, msg = await apply_penalty(
            context.bot, chat_id, user_id, penalty_type, duration_seconds,
            f"مخالفة: {violation_type}", context.bot.id
        )
        return success, msg
    except Exception as e:
        logger.error(f"❌ فشل تطبيق العقوبة: {e}")
        return False, str(e)[:100]


# =====================================================================
# معالجات الرسائل الرئيسية
# =====================================================================

class MessageHandlers:
    """معالجات الرسائل الرئيسية"""

    _private_handlers = None
    
    @classmethod
    def _get_private_handlers(cls) -> Dict:
        """الحصول على قاموس معالجات الرسائل الخاصة"""
        if cls._private_handlers is None:
            cls._private_handlers = {
                UserState.WAIT_MOOD: cls._handle_mood_analysis,
                UserState.WAIT_CHANNEL: cls._handle_channel_input,
                UserState.ADDING_POSTS: cls._handle_adding_posts,
                UserState.SUPPORT_MODE: cls._handle_support_message,
                UserState.WAIT_BROADCAST: cls._handle_broadcast_input,
                UserState.WAIT_UPDATE: cls._handle_update_input,
                UserState.WAIT_UPDATE_CH: cls._handle_update_ch_input,
                UserState.WAIT_FORCE: cls._handle_force_input,
                UserState.WAIT_LOG_CH: cls._handle_log_ch_input,
                UserState.WAIT_ADMIN_ADD: cls._handle_admin_add_input,
                UserState.WAIT_ADMIN_REM: cls._handle_admin_rem_input,
                UserState.WAIT_KEYWORD: cls._handle_keyword_input,
                UserState.WAIT_REPLY: cls._handle_reply_input,
                UserState.WAIT_GLOBAL_BAN: cls._handle_global_ban_input,
                UserState.WAIT_REM_GLOBAL_BAN: cls._handle_rem_global_ban_input,
                UserState.WAIT_GROUP_BAN: cls._handle_group_ban_input,
                UserState.WAIT_REM_GROUP_BAN: cls._handle_rem_group_ban_input,
                UserState.WAIT_CONTEST_TITLE: cls._handle_contest_title,
                UserState.WAIT_CONTEST_DESC: cls._handle_contest_desc,
                UserState.WAIT_CONTEST_PRIZE: cls._handle_contest_prize,
                UserState.WAIT_CONTEST_DATE: cls._handle_contest_date,
                UserState.WAIT_CONTEST_ANSWER: cls._handle_contest_answer,
                UserState.WAIT_AUTO_KEY: cls._handle_auto_key,
                UserState.WAIT_AUTO_REPLY: cls._handle_auto_reply_input,
                UserState.WAIT_AUTO_DEL: cls._handle_auto_del,
                UserState.WAIT_IMPORT_FILE: cls._handle_import_file,
                UserState.WAIT_GITHUB_URL: cls._handle_github_url,
                UserState.WAIT_GRANT_FREE: cls._handle_grant_free,
                UserState.WAIT_MIN: cls._handle_min_input,
                UserState.WAIT_HOUR: cls._handle_hour_input,
                UserState.WAIT_DAY: cls._handle_day_input,
                UserState.WAIT_PUB_TIME: cls._handle_pub_time_input,
                UserState.WAIT_REM_DAYS: cls._handle_rem_days_input,
                UserState.WAIT_MAX_LEN: cls._handle_max_len_input,
                UserState.WAIT_WARN_COUNT: cls._handle_warn_count_input,
                UserState.WAIT_WELCOME_TEXT: cls._handle_welcome_text_input,
                UserState.WAIT_GOODBYE_TEXT: cls._handle_goodbye_text_input,
                UserState.WAIT_SLOW_MODE_SECONDS: cls._handle_slow_mode_input,
                UserState.WAIT_ANTIFLOOD_MESSAGES: cls._handle_antiflood_messages_input,
                UserState.WAIT_ANTIFLOOD_SECONDS: cls._handle_antiflood_seconds_input,
                UserState.WAIT_NIGHT_START: cls._handle_night_start_input,
                UserState.WAIT_NIGHT_END: cls._handle_night_end_input,
                UserState.WAIT_BAN: cls._handle_ban_input,
                UserState.WAIT_MUTE: cls._handle_mute_input,
                UserState.WAIT_WARN: cls._handle_warn_input,
                UserState.WAIT_KICK: cls._handle_kick_input,
                UserState.WAIT_RESTRICT: cls._handle_restrict_input,
                UserState.WAIT_UNBAN: cls._handle_unban_input,
                UserState.WAIT_PIN: cls._handle_pin_input,
            }
        return cls._private_handlers

    # =================================================================
    # الرسائل الخاصة
    # =================================================================

    @staticmethod
    async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة الرسائل الخاصة حسب حالة المستخدم"""
        if not update.effective_user or not update.effective_message:
            return
        
        user_id = update.effective_user.id
        state = StateManager.get(user_id)
        
        if state is None:
            return
        
        handlers = MessageHandlers._get_private_handlers()
        handler = handlers.get(state)
        
        if handler:
            try:
                await handler(update, context)
            except Exception as e:
                logger.error(f"خطأ في معالجة الحالة {state} للمستخدم {user_id}: {e}", exc_info=True)
                await safe_send(context.bot, user_id, "❌ حدث خطأ غير متوقع")
                StateManager.clear(user_id)

    @staticmethod
    async def _handle_mood_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة تحليل المشاعر"""
        user_id = update.effective_user.id
        text = update.effective_message.text or ""
        
        if not text.strip():
            await safe_send(context.bot, user_id, "❌ يرجى إرسال نص لتحليله.")
            StateManager.clear(user_id)
            return
        
        if len(text) > MAX_TEXT_ANALYSIS_LENGTH:
            await safe_send(
                context.bot, user_id, 
                f"❌ النص طويل جداً. الحد الأقصى {MAX_TEXT_ANALYSIS_LENGTH} حرف."
            )
            StateManager.clear(user_id)
            return
        
        try:
            result = analyze_sentiment(text)
            
            sentiment = result.get('sentiment', 'غير معروف')
            emoji = result.get('emoji', '📊')
            response = result.get('response', '')
            positive_percent = result.get('positive_percent', 0)
            negative_percent = result.get('negative_percent', 0)
            total_words = result.get('total_words', 0)
            
            response_text = (
                f"{emoji} <b>تحليل المشاعر</b>\n\n"
                f"📝 النص: <code>{escape(text[:100])}</code>\n"
                f"🎯 النتيجة: {escape(sentiment)}\n"
                f"💬 {escape(response)}\n\n"
                f"😊 إيجابي: {positive_percent:.0f}%\n"
                f"😔 سلبي: {negative_percent:.0f}%\n"
                f"📊 الكلمات: {total_words}"
            )
            await safe_send(context.bot, user_id, response_text, parse_mode='HTML')
        except Exception as e:
            logger.error(f"خطأ في تحليل المشاعر: {e}")
            await safe_send(context.bot, user_id, "❌ فشل تحليل النص")
        finally:
            StateManager.clear(user_id)

    # =================================================================
    # رسائل المجموعات
    # =================================================================

    @staticmethod
    async def handle_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة رسائل المجموعات مع الفحوصات الأمنية"""
        if not update.effective_chat or not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        message = update.effective_message
        
        if update.effective_user and update.effective_user.id == context.bot.id:
            return
        
        if update.effective_user and update.effective_user.is_bot:
            return
        
        user_id = update.effective_user.id if update.effective_user else None
        if not user_id:
            return
        
        if message.text and message.text.startswith('/'):
            return
        
        is_admin = False
        try:
            is_admin = await _check_user_is_admin(context, chat_id, user_id)
        except Exception:
            pass
        
        msg_text = message.text or ""
        msg_caption = message.caption or ""
        full_text = f"{msg_text} {msg_caption}".strip()
        
        if not full_text and not any([
            message.photo, message.video, message.audio, message.voice,
            message.animation, message.document, message.sticker, message.video_note
        ]):
            return
        
        METRICS.increment_messages()
        
        if not is_admin:
            settings = await cache_manager.get_security_settings(chat_id)
            
            if settings.get('delete_links', False) and TextUtils.contains_link(full_text):
                await MessageHandlers._delete_and_warn(
                    update, context, chat_id, user_id, "link", settings
                )
                return
            
            if settings.get('mentions', False) and TextUtils.contains_mention(full_text):
                await MessageHandlers._delete_and_warn(
                    update, context, chat_id, user_id, "mention", settings
                )
                return
            
            if settings.get('delete_banned_words', False) and full_text:
                banned_words = await get_banned_words_cached(chat_id)
                if banned_words:
                    text_lower = full_text.lower()
                    for word in banned_words:
                        if word and word in text_lower:
                            await MessageHandlers._delete_and_warn(
                                update, context, chat_id, user_id, "banned_word", settings
                            )
                            return
            
            max_len = _safe_int(settings.get('max_message_length', 0))
            if max_len > 0 and len(full_text) > max_len:
                await MessageHandlers._delete_and_warn(
                    update, context, chat_id, user_id, "max_len", settings
                )
                return
            
            is_forwarded = any([
                getattr(message, 'forward_from', None),
                getattr(message, 'forward_from_chat', None),
                getattr(message, 'forward_date', None),
                getattr(message, 'forward_sender_name', None)
            ])
            if is_forwarded and settings.get('delete_forwarded', False):
                await MessageHandlers._delete_and_warn(
                    update, context, chat_id, user_id, "forwarded", settings
                )
                return
            
            media_checks = [
                (message.photo, 'delete_photos', 'photo'),
                (message.video, 'delete_videos', 'video'),
                (message.audio, 'delete_audio', 'audio'),
                (message.voice, 'delete_voice', 'voice'),
                (message.animation, 'delete_animation', 'animation'),
                (message.document, 'delete_documents', 'document'),
                (message.sticker, 'delete_stickers', 'sticker'),
                (message.video_note, 'delete_video_notes', 'video_note'),
            ]
            for media, setting_key, violation_type in media_checks:
                if media and settings.get(setting_key, False):
                    await MessageHandlers._delete_and_warn(
                        update, context, chat_id, user_id, violation_type, settings
                    )
                    return
        
        if msg_text:
            await MessageHandlers._process_auto_reply(
                update, context, chat_id, msg_text, user_id
            )

    # =================================================================
    # حذف وتحذير
    # =================================================================

    @staticmethod
    async def _delete_and_warn(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                               chat_id: int, user_id: int, violation_type: str, 
                               settings: Dict[str, Any]) -> None:
        """حذف الرسالة وإرسال تنبيه وتطبيق العقوبات"""
        if not settings:
            settings = {}
        
        try:
            try:
                await update.effective_message.delete()
                logger.info(f"تم حذف رسالة مخالفة من {user_id} في {chat_id} بسبب {violation_type}")
            except Forbidden:
                logger.warning(f"البوت ليس لديه صلاحية حذف الرسائل في {chat_id}")
            except Exception as e:
                logger.warning(f"تعذر حذف الرسالة: {e}")
            
            try:
                violation_count = await DB.increment_violation_count(user_id, chat_id)
            except Exception as e:
                logger.error(f"فشل زيادة عداد المخالفات: {e}")
                violation_count = 1
            
            try:
                penalty_rule = await DB.get_violation_penalty(chat_id, violation_type)
            except Exception as e:
                logger.error(f"فشل جلب قاعدة العقوبة: {e}")
                penalty_rule = None
            
            if penalty_rule:
                penalty_type = penalty_rule.get('penalty_type', 'mute')
                duration_seconds = _safe_int(
                    penalty_rule.get('duration_seconds'), 
                    DEFAULT_MUTE_DURATION
                )
            else:
                penalty_type = 'mute'
                duration_seconds = DEFAULT_MUTE_DURATION
            
            try:
                user_name = "مستخدم"
                if update.effective_user:
                    user_name = escape(update.effective_user.first_name or "مستخدم")
                
                message_text = (
                    f"⚠️ <b>تنبيه</b>\n"
                    f"👤 {user_name}\n"
                    f"🚫 المخالفة: {escape(violation_type)}\n"
                    f"📊 عدد المخالفات: {violation_count}\n"
                    f"⏳ سيتم حذف هذه الرسالة خلال 10 ثوانٍ"
                )
                sent_msg = await safe_send(context.bot, chat_id, message_text, parse_mode='HTML')
                if sent_msg:
                    asyncio.create_task(
                        _delete_after_delay(context.bot, chat_id, sent_msg.message_id, 10)
                    )
            except Exception as e:
                logger.warning(f"تعذر إرسال تنبيه المخالفة: {e}")
            
            max_warnings = _safe_int(settings.get('max_warnings'), MAX_WARNINGS_DEFAULT)
            
            if max_warnings > 0 and violation_count >= max_warnings:
                success, msg = await apply_violation_penalty(
                    context, chat_id, user_id, violation_type, 
                    penalty_type, duration_seconds
                )
                if success:
                    await safe_send(context.bot, chat_id, f"🚨 {msg}")
                    try:
                        await DB.reset_violation_count(user_id, chat_id)
                    except Exception as e:
                        logger.error(f"فشل إعادة تعيين عداد المخالفات: {e}")
        
        except Exception as e:
            logger.error(f"خطأ غير متوقع في _delete_and_warn: {e}", exc_info=True)

    # =================================================================
    # الردود التلقائية
    # =================================================================

    @staticmethod
    async def _process_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  chat_id: int, text: str, user_id: int = None) -> bool:
        """معالجة الردود التلقائية"""
        try:
            if not text or text.startswith('/'):
                return False
            
            text = _sanitize_html(text)
            
            ars = await cache_manager.get_auto_reply_settings(chat_id)
            
            if not ars.get('enabled', False):
                return False
            
            if update.effective_user and update.effective_user.is_bot and ars.get('ignore_bots', True):
                return False
            
            if ars.get('only_admins', False):
                if not user_id:
                    return False
                if not await _check_user_is_admin(context, chat_id, user_id):
                    return False
            
            try:
                reply = await DB.get_auto_reply(text, chat_id)
                if reply:
                    reply_text = _sanitize_html(reply.get('reply', ''))
                    if reply_text:
                        await safe_send(context.bot, chat_id, reply_text)
                        try:
                            await _increment_usage_async(chat_id, text)
                        except Exception as e:
                            logger.warning(f"فشل زيادة عداد الاستخدام: {e}")
                        return True
            except Exception as e:
                logger.error(f"خطأ في البحث عن رد تلقائي: {e}")
            
            try:
                file_reply = get_reply_from_file(text)
                if file_reply:
                    file_reply = _sanitize_html(file_reply)
                    await safe_send(context.bot, chat_id, file_reply)
                    return True
            except Exception as e:
                logger.error(f"خطأ في البحث عن رد من الملف: {e}")
            
            return False
        except Exception as e:
            logger.error(f"❌ خطأ في الردود: {e}")
            return False

    # =================================================================
    # إضافة القناة
    # =================================================================

    @staticmethod
    async def _handle_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال القناة"""
        user_id = update.effective_user.id
        text = (update.effective_message.text or "").strip()
        
        try:
            if user_id != CONFIG.PRIMARY_OWNER_ID:
                has_sub = await DB.has_active_subscription(user_id)
                if not has_sub:
                    await safe_send(
                        context.bot, user_id,
                        "❌ <b>يجب أن يكون لديك اشتراك نشط لإضافة قناة!</b>\n\n"
                        "📌 استخدم /subscribe للاشتراك\n"
                        "🎁 أو /trial للتجربة المجانية",
                        parse_mode='HTML'
                    )
                    return
            
            if not text:
                await safe_send(context.bot, user_id, "❌ يرجى إرسال معرف القناة أو رابطها")
                return
            
            if text.lstrip('-').isdigit():
                channel_id = int(text)
            else:
                try:
                    chat = await context.bot.get_chat(text)
                    channel_id = chat.id
                except Exception:
                    await safe_send(context.bot, user_id, "❌ القناة غير موجودة!")
                    return
            
            try:
                chat_info = await context.bot.get_chat(channel_id)
                channel_name = chat_info.title or chat_info.username or f"قناة {channel_id}"
            except Exception:
                channel_name = f"قناة {channel_id}"
            
            if not await _check_bot_is_admin(context, channel_id):
                await safe_send(context.bot, user_id, "❌ البوت ليس مشرفًا في القناة!")
                return
            
            if user_id != CONFIG.PRIMARY_OWNER_ID:
                if not await _check_user_is_admin(context, channel_id, user_id):
                    await safe_send(context.bot, user_id, "❌ يجب أن تكون مشرفًا في القناة لإضافتها!")
                    return
            
            if hasattr(DB, 'get_channel_by_id'):
                try:
                    existing_channel = await DB.get_channel_by_id(user_id, channel_id)
                    if existing_channel:
                        await safe_send(context.bot, user_id, "❌ هذه القناة مضافة بالفعل!")
                        return
                except Exception:
                    pass
            
            ch_db_id = await DB.add_channel(user_id, channel_id, channel_name)
            
            if ch_db_id:
                await safe_send(context.bot, user_id, f"✅ تمت إضافة القناة: {escape(channel_name)}")
            else:
                await safe_send(context.bot, user_id, "❌ فشل إضافة القناة")
        except Exception as e:
            logger.exception("خطأ غير متوقع في إضافة القناة")
            await safe_send(context.bot, user_id, f"❌ خطأ: {escape(str(e)[:200])}")
        finally:
            StateManager.clear(user_id)

    # =================================================================
    # إضافة المنشورات
    # =================================================================

    @staticmethod
    async def _handle_adding_posts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إضافة المنشورات"""
        user_id = update.effective_user.id
        
        try:
            active_channel = await DB.get_active_channel(user_id)
            if not active_channel:
                await safe_send(context.bot, user_id, "❌ لا توجد قناة نشطة")
                return
            
            channel_id = _extract_channel_id(active_channel)
            if not channel_id:
                await safe_send(context.bot, user_id, "❌ بيانات القناة غير صالحة")
                return
            
            msg = update.effective_message
            media_type = 'text'
            media_file_id = ''
            text = msg.text or msg.caption or ""
            
            if msg.photo:
                media_type = 'photo'
                media_file_id = msg.photo[-1].file_id
                text = msg.caption or ""
            elif msg.video:
                media_type = 'video'
                media_file_id = msg.video.file_id
                text = msg.caption or ""
            elif msg.document:
                if msg.document.file_size and msg.document.file_size > 50 * 1024 * 1024:
                    await safe_send(context.bot, user_id, "❌ الملف كبير جداً. الحد الأقصى 50MB")
                    return
                media_type = 'document'
                media_file_id = msg.document.file_id
                text = msg.caption or ""
            elif msg.audio:
                media_type = 'audio'
                media_file_id = msg.audio.file_id
                text = msg.caption or ""
            elif msg.voice:
                media_type = 'voice'
                media_file_id = msg.voice.file_id
            elif msg.animation:
                media_type = 'animation'
                media_file_id = msg.animation.file_id
                text = msg.caption or ""
            elif msg.sticker:
                media_type = 'sticker'
                media_file_id = msg.sticker.file_id
            elif msg.video_note:
                media_type = 'video_note'
                media_file_id = msg.video_note.file_id
            
            if not text and not media_file_id:
                await safe_send(context.bot, user_id, "❌ لا يمكن إضافة منشور فارغ!")
                return
            
            if text:
                text = _truncate_text(text)
                text = _sanitize_html(text)
            
            posts = [(text, media_type, media_file_id)]
            count = await DB.add_posts(user_id, channel_id, posts)
            
            if count > 0:
                await safe_send(context.bot, user_id, "✅ تمت إضافة المنشور")
            else:
                await safe_send(context.bot, user_id, "❌ فشل الإضافة")
        except Exception as e:
            logger.error(f"خطأ في إضافة المنشور: {e}", exc_info=True)
            await safe_send(context.bot, user_id, "❌ حدث خطأ غير متوقع")
        finally:
            StateManager.clear(user_id)

    # =================================================================
    # الدعم الفني
    # =================================================================

    @staticmethod
    async def _handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة رسائل الدعم الفني"""
        user_id = update.effective_user.id
        
        try:
            content = update.effective_message.text or ""
            username = update.effective_user.username or ""
            
            if not content.strip():
                await safe_send(context.bot, user_id, "❌ لا يمكن إرسال رسالة فارغة!")
                return
            
            if len(content) > MAX_TICKET_LENGTH:
                content = content[:MAX_TICKET_LENGTH] + "..."
            
            ticket_number = await DB.create_ticket(user_id, username, content)
            
            if ticket_number:
                await safe_send(
                    context.bot, user_id, 
                    f"✅ تم استلام رسالتك!\n🎫 رقم التذكرة: {ticket_number}"
                )
            else:
                await safe_send(context.bot, user_id, "❌ فشل إنشاء التذكرة")
        except Exception as e:
            logger.error(f"خطأ في الدعم الفني: {e}")
            await safe_send(context.bot, user_id, "❌ حدث خطأ غير متوقع")
        finally:
            StateManager.clear(user_id)

    # =================================================================
    # البث الجماعي
    # =================================================================

    @staticmethod
    async def _handle_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة البث الجماعي"""
        user_id = update.effective_user.id
        
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        content = update.effective_message.text or ""
        
        if not content.strip():
            await safe_send(context.bot, user_id, "❌ لا يمكن إرسال بث فارغ!")
            StateManager.clear(user_id)
            return
        
        if len(content) > MAX_BROADCAST_LENGTH:
            await safe_send(
                context.bot, user_id,
                f"❌ الرسالة طويلة جداً. الحد الأقصى {MAX_BROADCAST_LENGTH} حرف"
            )
            StateManager.clear(user_id)
            return
        
        try:
            users = await DB.get_all_users()
            if not users:
                await safe_send(context.bot, user_id, "ℹ️ لا يوجد مستخدمون للبث")
                StateManager.clear(user_id)
                return
            
            sent_count = 0
            failed_count = 0
            blocked_users = []
            
            batch_size = 25
            for i in range(0, len(users), batch_size):
                batch = users[i:i + batch_size]
                
                for user_entry in batch:
                    try:
                        if isinstance(user_entry, (tuple, list)):
                            uid = user_entry[0]
                            banned = user_entry[1] if len(user_entry) > 1 else 0
                        elif isinstance(user_entry, dict):
                            uid = user_entry.get('id') or user_entry.get('user_id')
                            banned = user_entry.get('banned', 0)
                        else:
                            uid = getattr(user_entry, 'id', None) or getattr(user_entry, 'user_id', None)
                            banned = getattr(user_entry, 'banned', 0)
                        
                        if uid and banned == 0:
                            try:
                                success = await safe_send(context.bot, uid, content)
                                if success:
                                    sent_count += 1
                                else:
                                    failed_count += 1
                                
                                await asyncio.sleep(BROADCAST_DELAY)
                            except Forbidden:
                                blocked_users.append(uid)
                                failed_count += 1
                            except Exception as e:
                                failed_count += 1
                                logger.warning(f"فشل الإرسال إلى {uid}: {e}")
                    except Exception as e:
                        logger.warning(f"تخطي سجل غير صالح: {e}")
                
                await asyncio.sleep(1)
            
            if blocked_users:
                try:
                    await DB.mark_users_as_blocked(blocked_users)
                except Exception as e:
                    logger.warning(f"فشل تحديث حالة المستخدمين المحظورين: {e}")
            
            await safe_send(
                context.bot, user_id, 
                f"✅ تم البث إلى {sent_count} مستخدم\n"
                f"❌ فشل: {failed_count}\n"
                f"🚫 محظورون: {len(blocked_users)}"
            )
        except Exception as e:
            logger.error(f"خطأ في البث الجماعي: {e}", exc_info=True)
            await safe_send(context.bot, user_id, "❌ فشل البث")
        finally:
            StateManager.clear(user_id)

    # =================================================================
    # التحديثات والإعدادات
    # =================================================================

    @staticmethod
    async def _handle_update_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إرسال التحديثات"""
        user_id = update.effective_user.id
        
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        content = update.effective_message.text or ""
        
        if not content.strip():
            await safe_send(context.bot, user_id, "❌ لا يمكن إرسال تحديث فارغ!")
            StateManager.clear(user_id)
            return
        
        try:
            update_ch = await DB.get_updates_channel()
            if update_ch:
                try:
                    success = await safe_send(context.bot, update_ch, content)
                    if success:
                        await safe_send(context.bot, user_id, "✅ تم إرسال التحديث")
                    else:
                        await safe_send(context.bot, user_id, "❌ فشل الإرسال")
                except Exception as e:
                    logger.error(f"فشل إرسال التحديث: {e}")
                    await safe_send(context.bot, user_id, "❌ فشل الإرسال")
            else:
                await safe_send(context.bot, user_id, "❌ لم يتم تعيين قناة التحديثات")
        except Exception as e:
            logger.error(f"خطأ في إرسال التحديث: {e}")
            await safe_send(context.bot, user_id, "❌ حدث خطأ غير متوقع")
        finally:
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_update_ch_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة تعيين قناة التحديثات"""
        user_id = update.effective_user.id
        
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        text = (update.effective_message.text or "").strip()
        
        if not text:
            await safe_send(context.bot, user_id, "❌ قيمة فارغة!")
            StateManager.clear(user_id)
            return
        
        try:
            await DB.set_setting('updates_channel', text)
            await safe_send(context.bot, user_id, f"✅ تم تعيين: {escape(text)}")
        except Exception as e:
            logger.error(f"فشل تعيين قناة التحديثات: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التعيين")
        finally:
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_force_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة تعيين قناة الاشتراك الإجباري"""
        user_id = update.effective_user.id
        
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        text = (update.effective_message.text or "").strip()
        
        try:
            await DB.set_setting('force_subscribe_channel', text)
            await safe_send(context.bot, user_id, f"✅ تم تعيين: {escape(text)}")
        except Exception as e:
            logger.error(f"فشل تعيين قناة الاشتراك الإجباري: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التعيين")
        finally:
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_log_ch_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة تعيين قناة السجلات"""
        user_id = update.effective_user.id
        
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        text = (update.effective_message.text or "").strip()
        
        try:
            await DB.set_setting('log_channel_id', text)
            await safe_send(context.bot, user_id, f"✅ تم تعيين: {escape(text)}")
        except Exception as e:
            logger.error(f"فشل تعيين قناة السجلات: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التعيين")
        finally:
            StateManager.clear(user_id)

    # =================================================================
    # المشرفين
    # =================================================================

    @staticmethod
    async def _handle_admin_add_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إضافة مشرف"""
        user_id = update.effective_user.id
        
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        text = (update.effective_message.text or "").strip()
        
        try:
            admin_id = int(text)
            if admin_id <= 0:
                raise ValueError("معرف غير صالح")
            
            if admin_id == CONFIG.PRIMARY_OWNER_ID:
                await safe_send(context.bot, user_id, "ℹ️ هذا المستخدم هو المالك الأساسي بالفعل")
                return
            
            success = await DB.add_admin(admin_id, user_id)
            
            if success:
                await safe_send(context.bot, user_id, "✅ تمت الإضافة")
            else:
                await safe_send(context.bot, user_id, "ℹ️ هذا المستخدم مشرف بالفعل")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        except Exception as e:
            logger.error(f"فشل إضافة مشرف: {e}")
            await safe_send(context.bot, user_id, "❌ حدث خطأ")
        finally:
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_admin_rem_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إزالة مشرف"""
        user_id = update.effective_user.id
        
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        text = (update.effective_message.text or "").strip()
        
        try:
            admin_id = int(text)
            
            if admin_id == CONFIG.PRIMARY_OWNER_ID:
                await safe_send(context.bot, user_id, "❌ لا يمكن إزالة المالك الأساسي!")
                return
            
            success = await DB.remove_admin(admin_id)
            
            if success:
                await safe_send(context.bot, user_id, "✅ تمت الإزالة")
            else:
                await safe_send(context.bot, user_id, "ℹ️ هذا المستخدم ليس مشرفًا")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        except Exception as e:
            logger.error(f"فشل إزالة مشرف: {e}")
            await safe_send(context.bot, user_id, "❌ حدث خطأ")
        finally:
            StateManager.clear(user_id)

    # =================================================================
    # الردود التلقائية - إدارة
    # =================================================================

    @staticmethod
    async def _handle_keyword_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال الكلمة المفتاحية للرد التلقائي"""
        user_id = update.effective_user.id
        keyword = (update.effective_message.text or "").strip().lower()
        
        if not keyword:
            await safe_send(context.bot, user_id, "❌ الكلمة لا يمكن أن تكون فارغة.")
            StateManager.clear(user_id)
            return
        
        context.user_data['auto_keyword'] = keyword
        context.user_data['auto_chat'] = -1
        StateManager.set(user_id, UserState.WAIT_REPLY)
        await safe_send(context.bot, user_id, f"✅ الكلمة: {escape(keyword)}\n📝 أرسل الرد:")

    @staticmethod
    async def _handle_reply_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال الرد التلقائي"""
        user_id = update.effective_user.id
        keyword = context.user_data.get('auto_keyword', '')
        reply = update.effective_message.text or ""
        chat_id = context.user_data.get('auto_chat', -1)
        
        try:
            if not reply.strip():
                await safe_send(context.bot, user_id, "❌ الرد لا يمكن أن يكون فارغًا.")
                return
            
            if not keyword:
                await safe_send(context.bot, user_id, "❌ الكلمة المفتاحية مفقودة.")
                return
            
            await DB.add_auto_reply(chat_id, keyword, reply)
            await cache_manager.invalidate_auto_reply(chat_id)
            await safe_send(context.bot, user_id, "✅ تمت الإضافة")
        except Exception as e:
            logger.error(f"فشل إضافة رد تلقائي: {e}")
            await safe_send(context.bot, user_id, "❌ فشل الإضافة")
        finally:
            _cleanup_user_data(context, ['auto_keyword', 'auto_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_auto_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال الكلمة المفتاحية (مسار بديل)"""
        user_id = update.effective_user.id
        keyword = (update.effective_message.text or "").strip().lower()
        
        if not keyword:
            await safe_send(context.bot, user_id, "❌ الكلمة لا يمكن أن تكون فارغة.")
            StateManager.clear(user_id)
            return
        
        context.user_data['auto_keyword'] = keyword
        context.user_data['auto_chat'] = -1
        StateManager.set(user_id, UserState.WAIT_AUTO_REPLY)
        await safe_send(context.bot, user_id, f"✅ الكلمة: {escape(keyword)}\n📝 أرسل الرد:")

    @staticmethod
    async def _handle_auto_reply_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال الرد التلقائي (مسار بديل)"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('auto_chat', -1)
        keyword = context.user_data.get('auto_keyword', '')
        reply = update.effective_message.text or ""
        
        try:
            if not reply.strip():
                await safe_send(context.bot, user_id, "❌ الرد لا يمكن أن يكون فارغًا.")
                return
            
            if not keyword:
                await safe_send(context.bot, user_id, "❌ الكلمة المفتاحية مفقودة.")
                return
            
            await DB.add_auto_reply(chat_id, keyword, reply)
            await cache_manager.invalidate_auto_reply(chat_id)
            await safe_send(context.bot, user_id, "✅ تمت الإضافة")
        except Exception as e:
            logger.error(f"فشل إضافة رد تلقائي: {e}")
            await safe_send(context.bot, user_id, "❌ فشل الإضافة")
        finally:
            _cleanup_user_data(context, ['auto_keyword', 'auto_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_auto_del(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة حذف رد تلقائي"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('auto_chat', -1)
        keyword = (update.effective_message.text or "").strip().lower()
        
        try:
            if not keyword:
                await safe_send(context.bot, user_id, "❌ الكلمة لا يمكن أن تكون فارغة.")
                return
            
            success = await DB.remove_auto_reply(chat_id, keyword)
            await cache_manager.invalidate_auto_reply(chat_id)
            
            if success:
                await safe_send(context.bot, user_id, "✅ تم الحذف")
            else:
                await safe_send(context.bot, user_id, "ℹ️ لم يتم العثور على هذا الرد")
        except Exception as e:
            logger.error(f"فشل حذف رد تلقائي: {e}")
            await safe_send(context.bot, user_id, "❌ فشل الحذف")
        finally:
            _cleanup_user_data(context, ['auto_chat'])
            StateManager.clear(user_id)

    # =================================================================
    # الكلمات المحظورة - إدارة
    # =================================================================

    @staticmethod
    async def _handle_global_ban_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إضافة كلمة محظورة عامة"""
        user_id = update.effective_user.id
        word = (update.effective_message.text or "").strip().lower()
        
        if not word:
            await safe_send(context.bot, user_id, "❌ الكلمة لا يمكن أن تكون فارغة.")
            StateManager.clear(user_id)
            return
        
        try:
            result = await DB.add_banned_word(word, -1, user_id)
            
            if isinstance(result, tuple):
                added = result[0]
            else:
                added = result
            
            if added:
                await invalidate_banned_words_cache(-1)
                await safe_send(context.bot, user_id, f"✅ تمت الإضافة: {escape(word)}")
            else:
                await safe_send(context.bot, user_id, "ℹ️ هذه الكلمة محظورة بالفعل")
        except Exception as e:
            logger.error(f"فشل إضافة كلمة محظورة: {e}")
            await safe_send(context.bot, user_id, "❌ فشل الإضافة")
        finally:
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_rem_global_ban_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إزالة كلمة محظورة عامة"""
        user_id = update.effective_user.id
        word = (update.effective_message.text or "").strip().lower()
        
        try:
            success = await DB.remove_banned_word(word, -1)
            await invalidate_banned_words_cache(-1)
            
            if success:
                await safe_send(context.bot, user_id, "✅ تمت الإزالة")
            else:
                await safe_send(context.bot, user_id, "ℹ️ لم يتم العثور على هذه الكلمة")
        except Exception as e:
            logger.error(f"فشل إزالة كلمة محظورة: {e}")
            await safe_send(context.bot, user_id, "❌ فشل الإزالة")
        finally:
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_group_ban_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إضافة كلمة محظورة لمجموعة"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('ban_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        word = (update.effective_message.text or "").strip().lower()
        
        if not word:
            await safe_send(context.bot, user_id, "❌ الكلمة لا يمكن أن تكون فارغة.")
            StateManager.clear(user_id)
            return
        
        try:
            result = await DB.add_banned_word(word, chat_id, user_id)
            
            if isinstance(result, tuple):
                added = result[0]
            else:
                added = result
            
            if added:
                await invalidate_banned_words_cache(chat_id)
                await safe_send(context.bot, user_id, "✅ تمت الإضافة")
            else:
                await safe_send(context.bot, user_id, "ℹ️ هذه الكلمة محظورة بالفعل")
        except Exception as e:
            logger.error(f"فشل إضافة كلمة محظورة: {e}")
            await safe_send(context.bot, user_id, "❌ فشل الإضافة")
        finally:
            _cleanup_user_data(context, ['ban_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_rem_group_ban_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إزالة كلمة محظورة من مجموعة"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('ban_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        word = (update.effective_message.text or "").strip().lower()
        
        try:
            success = await DB.remove_banned_word(word, chat_id)
            await invalidate_banned_words_cache(chat_id)
            
            if success:
                await safe_send(context.bot, user_id, "✅ تمت الإزالة")
            else:
                await safe_send(context.bot, user_id, "ℹ️ لم يتم العثور على هذه الكلمة")
        except Exception as e:
            logger.error(f"فشل إزالة كلمة محظورة: {e}")
            await safe_send(context.bot, user_id, "❌ فشل الإزالة")
        finally:
            _cleanup_user_data(context, ['ban_chat'])
            StateManager.clear(user_id)

    # =================================================================
    # المسابقات
    # =================================================================

    @staticmethod
    async def _handle_contest_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال عنوان المسابقة"""
        user_id = update.effective_user.id
        title = update.effective_message.text or ""
        
        if not title.strip():
            await safe_send(context.bot, user_id, "❌ العنوان لا يمكن أن يكون فارغًا.")
            StateManager.clear(user_id)
            return
        
        if len(title) > MAX_TITLE_LENGTH:
            await safe_send(
                context.bot, user_id,
                f"❌ العنوان طويل جداً. الحد الأقصى {MAX_TITLE_LENGTH} حرف"
            )
            StateManager.clear(user_id)
            return
        
        context.user_data['contest_title'] = title
        StateManager.set(user_id, UserState.WAIT_CONTEST_DESC)
        await safe_send(context.bot, user_id, "📝 أرسل الوصف:")

    @staticmethod
    async def _handle_contest_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال وصف المسابقة"""
        user_id = update.effective_user.id
        description = update.effective_message.text or ""
        
        if len(description) > MAX_DESCRIPTION_LENGTH:
            await safe_send(
                context.bot, user_id,
                f"❌ الوصف طويل جداً. الحد الأقصى {MAX_DESCRIPTION_LENGTH} حرف"
            )
            StateManager.clear(user_id)
            return
        
        context.user_data['contest_desc'] = description
        StateManager.set(user_id, UserState.WAIT_CONTEST_PRIZE)
        await safe_send(context.bot, user_id, "🎁 أرسل الجائزة:")

    @staticmethod
    async def _handle_contest_prize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال جائزة المسابقة"""
        user_id = update.effective_user.id
        prize = update.effective_message.text or ""
        
        if len(prize) > MAX_PRIZE_LENGTH:
            await safe_send(
                context.bot, user_id,
                f"❌ الجائزة طويلة جداً. الحد الأقصى {MAX_PRIZE_LENGTH} حرف"
            )
            StateManager.clear(user_id)
            return
        
        context.user_data['contest_prize'] = prize
        StateManager.set(user_id, UserState.WAIT_CONTEST_DATE)
        await safe_send(context.bot, user_id, "📅 أرسل التاريخ:")

    @staticmethod
    async def _handle_contest_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال تاريخ المسابقة"""
        user_id = update.effective_user.id
        title = context.user_data.get('contest_title', '')
        desc = context.user_data.get('contest_desc', '')
        prize = context.user_data.get('contest_prize', '')
        date = update.effective_message.text or ""
        
        try:
            contest_id = await DB.create_contest(user_id, title, desc, prize, date)
            
            if contest_id:
                await safe_send(context.bot, user_id, f"✅ تم الإنشاء #{contest_id}")
            else:
                await safe_send(context.bot, user_id, "❌ فشل الإنشاء")
        except Exception as e:
            logger.error(f"فشل إنشاء المسابقة: {e}")
            await safe_send(context.bot, user_id, "❌ حدث خطأ")
        finally:
            _cleanup_user_data(context, ['contest_title', 'contest_desc', 'contest_prize'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_contest_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إجابة المسابقة"""
        user_id = update.effective_user.id
        contest_id = context.user_data.get('contest_join')
        answer = update.effective_message.text or ""
        
        try:
            if not contest_id:
                await safe_send(context.bot, user_id, "❌ لا توجد مسابقة محددة")
                return
            
            if hasattr(DB, 'check_contest_joined'):
                already_joined = await DB.check_contest_joined(contest_id, user_id)
                if already_joined:
                    await safe_send(context.bot, user_id, "ℹ️ أنت مشترك بالفعل في هذه المسابقة!")
                    return
            
            joined = await DB.join_contest(contest_id, user_id, answer)
            
            if joined:
                await safe_send(context.bot, user_id, "✅ تم الاشتراك!")
            else:
                await safe_send(context.bot, user_id, "❌ فشل الاشتراك")
        except Exception as e:
            logger.error(f"فشل الاشتراك في المسابقة: {e}")
            await safe_send(context.bot, user_id, "❌ حدث خطأ")
        finally:
            _cleanup_user_data(context, ['contest_join'])
            StateManager.clear(user_id)

    # =================================================================
    # الاستيراد
    # =================================================================

    @staticmethod
    async def _handle_import_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة استيراد ملف JSON"""
        user_id = update.effective_user.id
        
        if not update.effective_message.document:
            await safe_send(context.bot, user_id, "❌ أرسل ملف JSON")
            StateManager.clear(user_id)
            return
        
        file_name = update.effective_message.document.file_name or ""
        if not file_name.endswith('.json'):
            await safe_send(context.bot, user_id, "❌ يجب أن يكون الملف بصيغة JSON")
            StateManager.clear(user_id)
            return
        
        if update.effective_message.document.file_size > MAX_IMPORT_FILE_SIZE:
            await safe_send(
                context.bot, user_id, 
                f"❌ الملف كبير جداً. الحد الأقصى {MAX_IMPORT_FILE_SIZE // (1024*1024)}MB"
            )
            StateManager.clear(user_id)
            return
        
        try:
            file = await update.effective_message.document.get_file()
            file_path = await file.download()
            
            if not file_path:
                raise Exception("فشل تنزيل الملف")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
            except json.JSONDecodeError:
                await safe_send(context.bot, user_id, "❌ الملف ليس JSON صالح")
                return
            
            count = import_auto_replies(-1, str(file_path))
            
            try:
                os.remove(file_path)
            except OSError as e:
                logger.warning(f"تعذر حذف الملف المؤقت {file_path}: {e}")
            
            await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
        except Exception as e:
            logger.exception("خطأ في استيراد الملف")
            await safe_send(context.bot, user_id, "❌ حدث خطأ أثناء الاستيراد")
        finally:
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_github_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة الاستيراد من URL"""
        user_id = update.effective_user.id
        url = (update.effective_message.text or "").strip()
        tmp_path = None
        
        if not url:
            await safe_send(context.bot, user_id, "❌ الرابط فارغ!")
            StateManager.clear(user_id)
            return
        
        if not url.startswith(('http://', 'https://')):
            await safe_send(context.bot, user_id, "❌ رابط غير صالح!")
            StateManager.clear(user_id)
            return
        
        try:
            data = await fetch_json_from_url(url)
            
            if not data:
                await safe_send(context.bot, user_id, "❌ فشل جلب البيانات")
                return
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
                json.dump(data, tmp, ensure_ascii=False)
                tmp_path = tmp.name
            
            count = import_auto_replies(-1, tmp_path)
            await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
        except Exception as e:
            logger.error(f"خطأ في الاستيراد من URL: {e}")
            await safe_send(context.bot, user_id, "❌ فشل الاستيراد")
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError as e:
                    logger.warning(f"تعذر حذف الملف المؤقت: {e}")
            StateManager.clear(user_id)

    # =================================================================
    # منح اشتراك
    # =================================================================

    @staticmethod
    async def _handle_grant_free(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة منح اشتراك مجاني"""
        user_id = update.effective_user.id
        
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        parts = (update.effective_message.text or "").strip().split()
        
        if len(parts) < 2:
            await safe_send(context.bot, user_id, "❌ الصيغة: /grant_free <id> <days>")
            StateManager.clear(user_id)
            return
        
        try:
            target_id = int(parts[0])
            days = int(parts[1])
            
            if target_id <= 0 or days <= 0:
                raise ValueError("أرقام غير صالحة")
            
            if target_id == CONFIG.PRIMARY_OWNER_ID:
                await safe_send(context.bot, user_id, "ℹ️ المالك الأساسي لديه صلاحيات كاملة")
                return
            
            if days > 365:
                await safe_send(context.bot, user_id, "❌ الحد الأقصى للأيام هو 365")
                return
            
            await DB.grant_subscription_days(target_id, days)
            await safe_send(context.bot, user_id, f"✅ تم منح {days} يوم للمستخدم {target_id}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ صيغة خاطئة (يجب أرقام موجبة)")
        except Exception as e:
            logger.error(f"فشل منح اشتراك: {e}")
            await safe_send(context.bot, user_id, "❌ فشل المنح")
        finally:
            StateManager.clear(user_id)

    # =================================================================
    # الجدولة
    # =================================================================

    @staticmethod
    async def _handle_min_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال الدقائق للجدولة"""
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        
        if not ch_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد القناة")
            StateManager.clear(user_id)
            return
        
        try:
            minutes = int(update.effective_message.text or "0")
            
            if minutes <= 0:
                await safe_send(context.bot, user_id, "❌ يجب أن يكون الرقم موجبًا")
                return
            
            if minutes > 59:
                await safe_send(context.bot, user_id, "❌ الدقائق يجب أن تكون أقل من 60")
                return
            
            await DB.update_schedule(ch_id, interval_minutes=minutes, schedule_type='interval_minutes')
            await safe_send(context.bot, user_id, f"✅ تم التعيين: كل {minutes} دقيقة")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ رقم غير صالح")
        except Exception as e:
            logger.error(f"خطأ في تحديث الجدولة: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            _cleanup_user_data(context, ['schedule_ch'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_hour_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال الساعات للجدولة"""
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        
        if not ch_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد القناة")
            StateManager.clear(user_id)
            return
        
        try:
            hours = int(update.effective_message.text or "0")
            
            if hours <= 0:
                await safe_send(context.bot, user_id, "❌ يجب أن يكون الرقم موجبًا")
                return
            
            if hours > 23:
                await safe_send(context.bot, user_id, "❌ الساعات يجب أن تكون أقل من 24")
                return
            
            await DB.update_schedule(ch_id, interval_hours=hours, schedule_type='interval_hours')
            await safe_send(context.bot, user_id, f"✅ تم التعيين: كل {hours} ساعة")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ رقم غير صالح")
        except Exception as e:
            logger.error(f"خطأ في تحديث الجدولة: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            _cleanup_user_data(context, ['schedule_ch'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_day_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال الأيام للجدولة"""
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        
        if not ch_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد القناة")
            StateManager.clear(user_id)
            return
        
        try:
            days = int(update.effective_message.text or "0")
            
            if days <= 0:
                await safe_send(context.bot, user_id, "❌ يجب أن يكون الرقم موجبًا")
                return
            
            if days > 30:
                await safe_send(context.bot, user_id, "❌ الأيام يجب أن تكون أقل من 31")
                return
            
            await DB.update_schedule(ch_id, interval_days=days, schedule_type='interval_days')
            await safe_send(context.bot, user_id, f"✅ تم التعيين: كل {days} يوم")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ رقم غير صالح")
        except Exception as e:
            logger.error(f"خطأ في تحديث الجدولة: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            _cleanup_user_data(context, ['schedule_ch'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_pub_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال وقت النشر"""
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        
        if not ch_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد القناة")
            StateManager.clear(user_id)
            return
        
        time_val = (update.effective_message.text or "").strip()
        
        if not _is_valid_time(time_val):
            await safe_send(context.bot, user_id, "❌ تنسيق غير صالح (مثال: 14:30)")
            StateManager.clear(user_id)
            return
        
        try:
            await DB.update_schedule(ch_id, publish_time=time_val)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {time_val}")
        except Exception as e:
            logger.error(f"خطأ في تحديث وقت النشر: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            _cleanup_user_data(context, ['schedule_ch'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_rem_days_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال أيام التذكير"""
        user_id = update.effective_user.id
        
        try:
            days = int(update.effective_message.text or "3")
            
            if not 1 <= days <= 30:
                await safe_send(context.bot, user_id, "❌ يجب أن يكون بين 1 و 30")
                return
            
            await DB.update_reminder_settings(user_id, reminder_days_before=days)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {days} يوم")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ رقم غير صالح")
        except Exception as e:
            logger.error(f"خطأ في تحديث التذكير: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            StateManager.clear(user_id)

    # =================================================================
    # إعدادات الأمان
    # =================================================================

    @staticmethod
    async def _handle_max_len_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال الحد الأقصى لطول الرسالة"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        try:
            max_len = int(update.effective_message.text or "0")
            
            if max_len < 0:
                raise ValueError("رقم سالب")
            
            await DB.update_security_settings(chat_id, max_message_length=max_len)
            await cache_manager.invalidate_security(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {max_len}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ رقم غير صالح")
        except Exception as e:
            logger.error(f"خطأ في تحديث الإعدادات: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            _cleanup_user_data(context, ['sec_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_warn_count_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال عدد التحذيرات"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        try:
            count = int(update.effective_message.text or "3")
            
            if count < 0:
                raise ValueError("رقم سالب")
            
            if count > 10:
                await safe_send(context.bot, user_id, "❌ الحد الأقصى هو 10 تحذيرات")
                return
            
            await DB.update_security_settings(chat_id, max_warnings=count)
            await cache_manager.invalidate_security(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {count}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ رقم غير صالح")
        except Exception as e:
            logger.error(f"خطأ في تحديث الإعدادات: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            _cleanup_user_data(context, ['sec_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_welcome_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال نص الترحيب"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        text = update.effective_message.text or ""
        
        if len(text) > MAX_MESSAGE_LENGTH:
            await safe_send(context.bot, user_id, f"❌ النص طويل جداً. الحد الأقصى {MAX_MESSAGE_LENGTH} حرف")
            StateManager.clear(user_id)
            return
        
        try:
            await DB.update_security_settings(chat_id, welcome_text=text)
            await cache_manager.invalidate_security(chat_id)
            await safe_send(context.bot, user_id, "✅ تم الحفظ")
        except Exception as e:
            logger.error(f"خطأ في تحديث نص الترحيب: {e}")
            await safe_send(context.bot, user_id, "❌ فشل الحفظ")
        finally:
            _cleanup_user_data(context, ['sec_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_goodbye_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال نص الوداع"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        text = update.effective_message.text or ""
        
        if len(text) > MAX_MESSAGE_LENGTH:
            await safe_send(context.bot, user_id, f"❌ النص طويل جداً. الحد الأقصى {MAX_MESSAGE_LENGTH} حرف")
            StateManager.clear(user_id)
            return
        
        try:
            await DB.update_security_settings(chat_id, goodbye_text=text)
            await cache_manager.invalidate_security(chat_id)
            await safe_send(context.bot, user_id, "✅ تم الحفظ")
        except Exception as e:
            logger.error(f"خطأ في تحديث نص الوداع: {e}")
            await safe_send(context.bot, user_id, "❌ فشل الحفظ")
        finally:
            _cleanup_user_data(context, ['sec_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_slow_mode_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال الوضع البطيء"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        try:
            seconds = int(update.effective_message.text or "0")
            
            if seconds < 0:
                raise ValueError("رقم سالب")
            
            if seconds > 300:
                await safe_send(context.bot, user_id, "❌ الحد الأقصى هو 300 ثانية")
                return
            
            await DB.update_security_settings(chat_id, slow_mode_seconds=seconds)
            await cache_manager.invalidate_security(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {seconds}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ رقم غير صالح")
        except Exception as e:
            logger.error(f"خطأ في تحديث الإعدادات: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            _cleanup_user_data(context, ['sec_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_antiflood_messages_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال عدد رسائل مكافحة الفيضان"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        try:
            count = int(update.effective_message.text or "5")
            
            if count <= 0:
                raise ValueError("رقم غير موجب")
            
            if count > 20:
                await safe_send(context.bot, user_id, "❌ الحد الأقصى هو 20 رسالة")
                return
            
            await DB.update_security_settings(chat_id, antiflood_messages=count)
            await cache_manager.invalidate_security(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {count}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ رقم غير صالح")
        except Exception as e:
            logger.error(f"خطأ في تحديث الإعدادات: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            _cleanup_user_data(context, ['sec_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_antiflood_seconds_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال ثواني مكافحة الفيضان"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        try:
            seconds = int(update.effective_message.text or "10")
            
            if seconds <= 0:
                raise ValueError("رقم غير موجب")
            
            if seconds > 60:
                await safe_send(context.bot, user_id, "❌ الحد الأقصى هو 60 ثانية")
                return
            
            await DB.update_security_settings(chat_id, antiflood_seconds=seconds)
            await cache_manager.invalidate_security(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {seconds}")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ رقم غير صالح")
        except Exception as e:
            logger.error(f"خطأ في تحديث الإعدادات: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            _cleanup_user_data(context, ['sec_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_night_start_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال بداية الوضع الليلي"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        time_val = (update.effective_message.text or "").strip()
        
        if not _is_valid_time(time_val):
            await safe_send(context.bot, user_id, "❌ تنسيق غير صالح (مثال: 23:00)")
            StateManager.clear(user_id)
            return
        
        try:
            await DB.update_security_settings(chat_id, night_mode_start=time_val)
            await cache_manager.invalidate_security(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {time_val}")
        except Exception as e:
            logger.error(f"خطأ في تحديث الإعدادات: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            _cleanup_user_data(context, ['sec_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_night_end_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة إدخال نهاية الوضع الليلي"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        time_val = (update.effective_message.text or "").strip()
        
        if not _is_valid_time(time_val):
            await safe_send(context.bot, user_id, "❌ تنسيق غير صالح (مثال: 06:00)")
            StateManager.clear(user_id)
            return
        
        try:
            await DB.update_security_settings(chat_id, night_mode_end=time_val)
            await cache_manager.invalidate_security(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {time_val}")
        except Exception as e:
            logger.error(f"خطأ في تحديث الإعدادات: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التحديث")
        finally:
            _cleanup_user_data(context, ['sec_chat'])
            StateManager.clear(user_id)

    # =================================================================
    # العقوبات - مع التحقق من الصلاحيات
    # =================================================================

    @staticmethod
    async def _handle_ban_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة أمر الحظر اليدوي"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        if not await _check_user_is_admin(context, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ لم تعد مشرفًا في هذه المجموعة")
            StateManager.clear(user_id)
            return
        
        parts = (update.effective_message.text or "").strip().split()
        
        if not parts:
            await safe_send(context.bot, user_id, "❌ أرسل معرف المستخدم")
            StateManager.clear(user_id)
            return
        
        try:
            target = int(parts[0])
            duration = int(parts[1]) * 60 if len(parts) > 1 else 0
            
            if target <= 0:
                raise ValueError("معرف غير صالح")
            
            if duration < 0:
                raise ValueError("مدة غير صالحة")
            
            if target == CONFIG.PRIMARY_OWNER_ID:
                await safe_send(context.bot, user_id, "❌ لا يمكن حظر المالك الأساسي!")
                return
            
            await apply_penalty(context.bot, chat_id, target, 'ban', duration, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم الحظر")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ صيغة غير صحيحة")
        except Exception as e:
            logger.error(f"فشل الحظر: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التنفيذ")
        finally:
            _cleanup_user_data(context, ['adv_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_mute_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة أمر الكتم اليدوي"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        if not await _check_user_is_admin(context, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ لم تعد مشرفًا في هذه المجموعة")
            StateManager.clear(user_id)
            return
        
        parts = (update.effective_message.text or "").strip().split()
        
        if not parts:
            await safe_send(context.bot, user_id, "❌ أرسل معرف المستخدم")
            StateManager.clear(user_id)
            return
        
        try:
            target = int(parts[0])
            duration = int(parts[1]) * 60 if len(parts) > 1 else DEFAULT_MUTE_DURATION
            
            if target <= 0 or duration <= 0:
                raise ValueError("قيم غير صالحة")
            
            await apply_penalty(context.bot, chat_id, target, 'mute', duration, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم الكتم")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ صيغة غير صحيحة")
        except Exception as e:
            logger.error(f"فشل الكتم: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التنفيذ")
        finally:
            _cleanup_user_data(context, ['adv_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_warn_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة أمر التحذير اليدوي"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        if not await _check_user_is_admin(context, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ لم تعد مشرفًا في هذه المجموعة")
            StateManager.clear(user_id)
            return
        
        try:
            target = int((update.effective_message.text or "").strip())
            
            if target <= 0:
                raise ValueError("معرف غير صالح")
            
            await apply_penalty(context.bot, chat_id, target, 'warn', 0, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم التحذير")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        except Exception as e:
            logger.error(f"فشل التحذير: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التنفيذ")
        finally:
            _cleanup_user_data(context, ['adv_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_kick_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة أمر الطرد اليدوي"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        if not await _check_user_is_admin(context, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ لم تعد مشرفًا في هذه المجموعة")
            StateManager.clear(user_id)
            return
        
        try:
            target = int((update.effective_message.text or "").strip())
            
            if target <= 0:
                raise ValueError("معرف غير صالح")
            
            await apply_penalty(context.bot, chat_id, target, 'kick', 0, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم الطرد")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        except Exception as e:
            logger.error(f"فشل الطرد: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التنفيذ")
        finally:
            _cleanup_user_data(context, ['adv_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_restrict_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة أمر التقييد اليدوي"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        if not await _check_user_is_admin(context, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ لم تعد مشرفًا في هذه المجموعة")
            StateManager.clear(user_id)
            return
        
        parts = (update.effective_message.text or "").strip().split()
        
        if not parts:
            await safe_send(context.bot, user_id, "❌ أرسل معرف المستخدم")
            StateManager.clear(user_id)
            return
        
        try:
            target = int(parts[0])
            duration = int(parts[1]) * 60 if len(parts) > 1 else 1800
            
            if target <= 0 or duration <= 0:
                raise ValueError("قيم غير صالحة")
            
            await apply_penalty(context.bot, chat_id, target, 'restrict', duration, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم التقييد")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ صيغة غير صحيحة")
        except Exception as e:
            logger.error(f"فشل التقييد: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التنفيذ")
        finally:
            _cleanup_user_data(context, ['adv_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_unban_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة أمر إلغاء الحظر"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        if not await _check_user_is_admin(context, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ لم تعد مشرفًا في هذه المجموعة")
            StateManager.clear(user_id)
            return
        
        try:
            target = int((update.effective_message.text or "").strip())
            
            if target <= 0:
                raise ValueError("معرف غير صالح")
            
            await apply_penalty(context.bot, chat_id, target, 'unban', 0, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم إلغاء الحظر")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        except Exception as e:
            logger.error(f"فشل إلغاء الحظر: {e}")
            await safe_send(context.bot, user_id, "❌ فشل التنفيذ")
        finally:
            _cleanup_user_data(context, ['adv_chat'])
            StateManager.clear(user_id)

    @staticmethod
    async def _handle_pin_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة أمر التثبيت"""
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        
        if not chat_id:
            await safe_send(context.bot, user_id, "❌ لم يتم تحديد المجموعة")
            StateManager.clear(user_id)
            return
        
        if not await _check_user_is_admin(context, chat_id, user_id):
            await safe_send(context.bot, user_id, "❌ لم تعد مشرفًا في هذه المجموعة")
            StateManager.clear(user_id)
            return
        
        if update.effective_message.reply_to_message:
            try:
                await context.bot.pin_chat_message(chat_id, update.effective_message.reply_to_message.message_id)
                await safe_send(context.bot, user_id, "✅ تم التثبيت")
            except Forbidden:
                await safe_send(context.bot, user_id, "❌ البوت ليس لديه صلاحية التثبيت")
            except Exception as e:
                logger.error(f"فشل التثبيت: {e}")
                await safe_send(context.bot, user_id, "❌ فشل التثبيت")
        else:
            await safe_send(context.bot, user_id, "❌ قم بالرد على رسالة لتثبيتها")
        
        _cleanup_user_data(context, ['adv_chat'])
        StateManager.clear(user_id)

    # =================================================================
    # رسائل الخدمة
    # =================================================================

    @staticmethod
    async def handle_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة رسائل الخدمة"""
        if not update.effective_chat or not update.effective_message:
            return
        
        chat_id = update.effective_chat.id
        settings = await cache_manager.get_security_settings(chat_id)
        
        if update.effective_message.new_chat_members and settings.get('welcome_enabled', False):
            for member in update.effective_message.new_chat_members:
                if member.is_bot:
                    continue
                
                welcome_text = settings.get('welcome_text', 'مرحباً {user} 🤍')
                welcome_text = _sanitize_html(welcome_text)
                user_name = escape(member.first_name or "عضو")
                welcome_text = welcome_text.replace('{user}', user_name)
                await safe_send(context.bot, chat_id, welcome_text, parse_mode='HTML')
        
        if update.effective_message.left_chat_member and settings.get('goodbye_enabled', False):
            member = update.effective_message.left_chat_member
            
            if not member.is_bot:
                goodbye_text = settings.get('goodbye_text', 'وداعاً {user} 👋')
                goodbye_text = _sanitize_html(goodbye_text)
                user_name = escape(member.first_name or "عضو")
                goodbye_text = goodbye_text.replace('{user}', user_name)
                await safe_send(context.bot, chat_id, goodbye_text, parse_mode='HTML')

    # =================================================================
    # طلبات الانضمام
    # =================================================================

    @staticmethod
    async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة طلبات الانضمام"""
        if not update.effective_chat or not update.effective_user:
            return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        settings = await cache_manager.get_security_settings(chat_id)
        
        if settings.get('auto_reject_join', False):
            try:
                await context.bot.decline_chat_join_request(chat_id, user_id)
                logger.info(f"تم رفض طلب انضمام من {user_id} في {chat_id}")
                return
            except Exception as e:
                logger.warning(f"فشل رفض طلب الانضمام: {e}")
                return
        
        if settings.get('auto_approve_join', False):
            try:
                await context.bot.approve_chat_join_request(chat_id, user_id)
                logger.info(f"تمت الموافقة على طلب انضمام من {user_id} في {chat_id}")
            except Exception as e:
                logger.warning(f"فشل الموافقة على طلب الانضمام: {e}")


# =====================================================================
# دوال التصدير للاستخدام الخارجي
# =====================================================================

async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نقطة دخول الرسائل الخاصة"""
    await MessageHandlers.handle_private(update, context)


async def handle_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نقطة دخول رسائل المجموعات"""
    await MessageHandlers.handle_group(update, context)


async def handle_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نقطة دخول رسائل الخدمة"""
    await MessageHandlers.handle_service(update, context)


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نقطة دخول طلبات الانضمام"""
    await MessageHandlers.handle_join_request(update, context)
