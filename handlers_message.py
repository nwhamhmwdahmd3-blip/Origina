#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_message.py - معالجات الرسائل (MessageHandlers) - النسخة الكاملة
===================================================================================
جميع معالجات الرسائل مع كاش للإعدادات وإصلاح الحذف التلقائي
"""

import asyncio
import logging
import time
import re
from typing import Optional

from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TimedOut

from config import CONFIG
from database import DB
from utils import (
    TimeUtils, TextUtils, safe_send, is_authorized_in_group,
    check_bot_permissions, invalidate_auth_cache, apply_penalty,
    RATE_LIMITER, METRICS, get_text, StateManager, UserState,
    KeyboardFactory, TranslationManager, CB,
    get_banned_words_cached, invalidate_banned_words_cache,
    _auto_reply_cache, get_reply_from_file, _REPLIES_FROM_FILE,
    reload_replies_from_file, _increment_usage_async,
)

logger = logging.getLogger(__name__)


# =====================================================================
# كاش الإعدادات (لتسريع الردود)
# =====================================================================

# كاش إعدادات الأمان (30 ثانية TTL)
_security_settings_cache = {}
_security_settings_time = {}

# كاش إعدادات الردود التلقائية (60 ثانية TTL)
_auto_reply_settings_cache = {}
_auto_reply_settings_time = {}


async def get_security_settings_cached(chat_id: int) -> dict:
    """جلب إعدادات الأمان مع الكاش"""
    now = time.time()
    if chat_id in _security_settings_cache and (now - _security_settings_time.get(chat_id, 0)) < 30:
        return _security_settings_cache[chat_id]
    
    settings = await DB.get_security_settings(chat_id)
    _security_settings_cache[chat_id] = settings
    _security_settings_time[chat_id] = now
    return settings


async def get_auto_reply_settings_cached(chat_id: int) -> dict:
    """جلب إعدادات الردود مع الكاش"""
    now = time.time()
    if chat_id in _auto_reply_settings_cache and (now - _auto_reply_settings_time.get(chat_id, 0)) < 60:
        return _auto_reply_settings_cache[chat_id]
    
    settings = await DB.get_auto_reply_settings(chat_id)
    _auto_reply_settings_cache[chat_id] = settings
    _auto_reply_settings_time[chat_id] = now
    return settings


async def invalidate_security_cache(chat_id: int = None) -> None:
    """إبطال كاش الأمان"""
    if chat_id:
        _security_settings_cache.pop(chat_id, None)
        _security_settings_time.pop(chat_id, None)
    else:
        _security_settings_cache.clear()
        _security_settings_time.clear()


async def invalidate_auto_reply_cache(chat_id: int = None) -> None:
    """إبطال كاش الردود"""
    if chat_id:
        _auto_reply_settings_cache.pop(chat_id, None)
        _auto_reply_settings_time.pop(chat_id, None)
    else:
        _auto_reply_settings_cache.clear()
        _auto_reply_settings_time.clear()


async def _delete_after_delay(bot, chat_id: int, message_id: int, delay: int = 10):
    """حذف رسالة بعد تأخير محدد"""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# =====================================================================
# معالجات الرسائل
# =====================================================================

class MessageHandlers:
    """جميع معالجات الرسائل"""

    @staticmethod
    async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة الرسائل الخاصة"""
        user_id = update.effective_user.id
        state = StateManager.get(user_id)

        if state == UserState.ADDING_POSTS:
            await MessageHandlers._handle_adding_posts(update, context)
            return

        if state == UserState.SUPPORT_MODE:
            await MessageHandlers._handle_support_message(update, context)
            return

        if state == UserState.WAIT_CHANNEL:
            await MessageHandlers._handle_channel_input(update, context)
            return

        if state == UserState.WAIT_BROADCAST:
            await MessageHandlers._handle_broadcast_input(update, context)
            return

        if state == UserState.WAIT_UPDATE:
            await MessageHandlers._handle_update_input(update, context)
            return

        if state == UserState.WAIT_UPDATE_CH:
            await MessageHandlers._handle_update_ch_input(update, context)
            return

        if state == UserState.WAIT_FORCE:
            await MessageHandlers._handle_force_input(update, context)
            return

        if state == UserState.WAIT_LOG_CH:
            await MessageHandlers._handle_log_ch_input(update, context)
            return

        if state == UserState.WAIT_ADMIN_ADD:
            await MessageHandlers._handle_admin_add_input(update, context)
            return

        if state == UserState.WAIT_ADMIN_REM:
            await MessageHandlers._handle_admin_rem_input(update, context)
            return

        if state == UserState.WAIT_KEYWORD:
            await MessageHandlers._handle_keyword_input(update, context)
            return

        if state == UserState.WAIT_REPLY:
            await MessageHandlers._handle_reply_input(update, context)
            return

        if state == UserState.WAIT_GLOBAL_BAN:
            await MessageHandlers._handle_global_ban_input(update, context)
            return

        if state == UserState.WAIT_REM_GLOBAL_BAN:
            await MessageHandlers._handle_rem_global_ban_input(update, context)
            return

        if state == UserState.WAIT_GROUP_BAN:
            await MessageHandlers._handle_group_ban_input(update, context)
            return

        if state == UserState.WAIT_REM_GROUP_BAN:
            await MessageHandlers._handle_rem_group_ban_input(update, context)
            return

        if state == UserState.WAIT_CONTEST_TITLE:
            await MessageHandlers._handle_contest_title(update, context)
            return

        if state == UserState.WAIT_CONTEST_DESC:
            await MessageHandlers._handle_contest_desc(update, context)
            return

        if state == UserState.WAIT_CONTEST_PRIZE:
            await MessageHandlers._handle_contest_prize(update, context)
            return

        if state == UserState.WAIT_CONTEST_DATE:
            await MessageHandlers._handle_contest_date(update, context)
            return

        if state == UserState.WAIT_CONTEST_ANSWER:
            await MessageHandlers._handle_contest_answer(update, context)
            return

        if state == UserState.WAIT_AUTO_KEY:
            await MessageHandlers._handle_auto_key(update, context)
            return

        if state == UserState.WAIT_AUTO_REPLY:
            await MessageHandlers._handle_auto_reply_input(update, context)
            return

        if state == UserState.WAIT_AUTO_DEL:
            await MessageHandlers._handle_auto_del(update, context)
            return

        if state == UserState.WAIT_IMPORT_FILE:
            await MessageHandlers._handle_import_file(update, context)
            return

        if state == UserState.WAIT_GITHUB_URL:
            await MessageHandlers._handle_github_url(update, context)
            return

        if state == UserState.WAIT_GRANT_FREE:
            await MessageHandlers._handle_grant_free(update, context)
            return

        if state == UserState.WAIT_MIN:
            await MessageHandlers._handle_min_input(update, context)
            return

        if state == UserState.WAIT_HOUR:
            await MessageHandlers._handle_hour_input(update, context)
            return

        if state == UserState.WAIT_DAY:
            await MessageHandlers._handle_day_input(update, context)
            return

        if state == UserState.WAIT_PUB_TIME:
            await MessageHandlers._handle_pub_time_input(update, context)
            return

        if state == UserState.WAIT_REM_DAYS:
            await MessageHandlers._handle_rem_days_input(update, context)
            return

        if state == UserState.WAIT_MAX_LEN:
            await MessageHandlers._handle_max_len_input(update, context)
            return

        if state == UserState.WAIT_WARN_COUNT:
            await MessageHandlers._handle_warn_count_input(update, context)
            return

        if state == UserState.WAIT_WELCOME_TEXT:
            await MessageHandlers._handle_welcome_text_input(update, context)
            return

        if state == UserState.WAIT_GOODBYE_TEXT:
            await MessageHandlers._handle_goodbye_text_input(update, context)
            return

        if state == UserState.WAIT_SLOW_MODE_SECONDS:
            await MessageHandlers._handle_slow_mode_input(update, context)
            return

        if state == UserState.WAIT_ANTIFLOOD_MESSAGES:
            await MessageHandlers._handle_antiflood_messages_input(update, context)
            return

        if state == UserState.WAIT_ANTIFLOOD_SECONDS:
            await MessageHandlers._handle_antiflood_seconds_input(update, context)
            return

        if state == UserState.WAIT_NIGHT_START:
            await MessageHandlers._handle_night_start_input(update, context)
            return

        if state == UserState.WAIT_NIGHT_END:
            await MessageHandlers._handle_night_end_input(update, context)
            return

        if state == UserState.WAIT_BAN:
            await MessageHandlers._handle_ban_input(update, context)
            return

        if state == UserState.WAIT_MUTE:
            await MessageHandlers._handle_mute_input(update, context)
            return

        if state == UserState.WAIT_WARN:
            await MessageHandlers._handle_warn_input(update, context)
            return

        if state == UserState.WAIT_KICK:
            await MessageHandlers._handle_kick_input(update, context)
            return

        if state == UserState.WAIT_RESTRICT:
            await MessageHandlers._handle_restrict_input(update, context)
            return

        if state == UserState.WAIT_UNBAN:
            await MessageHandlers._handle_unban_input(update, context)
            return

        if state == UserState.WAIT_PIN:
            await MessageHandlers._handle_pin_input(update, context)
            return

        # إذا لم تكن هناك حالة، فقط تجاهل أو رد افتراضي
        text = update.effective_message.text if update.effective_message else ""
        if text and text.startswith('/'):
            return

    @staticmethod
    async def handle_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة الرسائل في المجموعات"""
        if not update.effective_chat or not update.effective_message:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        message = update.effective_message
        text = message.text or ""

        METRICS.increment_messages()

        # ✅ استخدام الكاش للإعدادات
        settings = await get_security_settings_cached(chat_id)

        # فحص القفل
        if settings.get('slow_mode'):
            pass  # الوضع البطيء يتم التعامل معه في مكان آخر

        # فحص الروابط
        if settings.get('delete_links') and TextUtils.contains_link(text):
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "link")
            return

        # فحص المنشنات
        if settings.get('mentions') and TextUtils.contains_mention(text):
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "mention")
            return

        # فحص الكلمات المحظورة
        if settings.get('delete_banned_words'):
            banned_words = await get_banned_words_cached(chat_id)
            if banned_words:
                text_lower = text.lower()
                for word in banned_words:
                    if word in text_lower:
                        await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "banned_word")
                        return

        # فحص طول الرسالة
        max_len = settings.get('max_message_length', 0)
        if max_len > 0 and len(text) > max_len:
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "max_len")
            return

        # فحص الوسائط
        if message.photo and settings.get('delete_videos'):
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "video")
            return

        if message.video and settings.get('delete_videos'):
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "video")
            return

        if message.audio and settings.get('delete_audio'):
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "audio")
            return

        if message.voice and settings.get('delete_voice'):
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "voice")
            return

        if message.animation and settings.get('delete_animation'):
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "animation")
            return

        if message.document and settings.get('delete_documents'):
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "document")
            return

        if message.sticker and settings.get('delete_stickers'):
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "sticker")
            return

        if message.forward_date and settings.get('delete_forwarded'):
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "forwarded")
            return

        # فحص الردود التلقائية
        if text:
            await MessageHandlers._process_auto_reply(update, context, chat_id, text, user_id)

    @staticmethod
    async def _delete_and_warn(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                               chat_id: int, user_id: int, violation_type: str):
        """حذف الرسالة وإرسال إنذار"""
        try:
            await update.effective_message.delete()
        except Exception:
            pass

        # تسجيل المخالفة
        violation_count = await DB.increment_violation_count(user_id, chat_id)
        
        # الحصول على العقوبة المحددة لهذه المخالفة
        penalty_rule = await DB.get_violation_penalty(chat_id, violation_type)
        
        if penalty_rule:
            penalty_type = penalty_rule['penalty_type']
            duration_seconds = penalty_rule['duration_seconds']
        else:
            penalty_type = 'mute'
            duration_seconds = 60

        # إرسال رسالة الإنذار
        try:
            user_name = update.effective_user.first_name or "مستخدم"
            message_text = (
                f"⚠️ **تنبيه**\n"
                f"👤 {user_name}\n"
                f"🚫 المخالفة: {violation_type}\n"
                f"📊 عدد المخالفات: {violation_count}\n"
                f"⏳ سيتم حذف هذه الرسالة خلال 10 ثوانٍ"
            )
            
            sent_msg = await context.bot.send_message(chat_id, message_text, parse_mode='HTML')
            
            # ✅ استخدام asyncio.create_task بدلاً من job_queue
            asyncio.create_task(_delete_after_delay(context.bot, chat_id, sent_msg.message_id, 10))
        except Exception:
            pass

        # تطبيق العقوبة إذا تجاوز الحد
        security_settings = await get_security_settings_cached(chat_id)
        max_strikes = security_settings.get('violation_strikes', 3)
        
        if violation_count >= max_strikes:
            success, msg = await apply_penalty(
                context.bot, chat_id, user_id, penalty_type, duration_seconds,
                f"تجاوز الحد الأقصى للمخالفات ({violation_count})",
                context.bot.id
            )
            if success:
                await safe_send(context.bot, chat_id, f"🚨 {msg}")

    @staticmethod
    async def _process_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                   chat_id: int, text: str, user_id: int = None) -> bool:
        """معالجة الردود التلقائية مع الكاش"""
        try:
            # ✅ استخدام الكاش
            ars = await get_auto_reply_settings_cached(chat_id)
            
            if not ars.get('enabled', False):
                return False

            # التحقق من أن المستخدم ليس بوت إذا كان الإعداد يمنع البوتات
            if ars.get('ignore_bots', True) and update.effective_user.is_bot:
                return False

            # التحقق من الصلاحيات إذا كان الإعداد للمشرفين فقط
            if ars.get('only_admins', False):
                if not await is_authorized_in_group(context.bot, chat_id, user_id or update.effective_user.id):
                    return False

            # البحث في قاعدة البيانات
            reply = await DB.get_auto_reply(text, chat_id)
            if reply:
                reply_text = reply.get('reply', '')
                reply_type = reply.get('reply_type', 'text')
                reply_media_id = reply.get('reply_media_id')
                
                if reply_type == 'text' or not reply_media_id:
                    await safe_send(context.bot, chat_id, reply_text)
                elif reply_type == 'photo':
                    await context.bot.send_photo(chat_id, reply_media_id, caption=reply_text or None)
                elif reply_type == 'video':
                    await context.bot.send_video(chat_id, reply_media_id, caption=reply_text or None)
                elif reply_type == 'animation':
                    await context.bot.send_animation(chat_id, reply_media_id, caption=reply_text or None)
                elif reply_type == 'document':
                    await context.bot.send_document(chat_id, reply_media_id, caption=reply_text or None)
                elif reply_type == 'sticker':
                    await context.bot.send_sticker(chat_id, reply_media_id)
                elif reply_type == 'voice':
                    await context.bot.send_voice(chat_id, reply_media_id, caption=reply_text or None)
                elif reply_type == 'video_note':
                    await context.bot.send_video_note(chat_id, reply_media_id)
                
                await _increment_usage_async(chat_id, text)
                return True

            # البحث في الملف
            file_reply = get_reply_from_file(text)
            if file_reply:
                await safe_send(context.bot, chat_id, file_reply)
                return True

            return False
        except Exception as e:
            logger.error(f"❌ خطأ في الردود التلقائية: {e}")
            return False

    # =====================================================================
    # معالجات الحالات الخاصة
    # =====================================================================

    @staticmethod
    async def _handle_adding_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        active = await DB.get_active_channel(user_id)
        if not active:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ لا توجد قناة نشطة")
            return

        msg = update.effective_message
        media_type = None
        media_file_id = None
        text = msg.text or ""

        if msg.photo:
            media_type = 'photo'
            media_file_id = msg.photo[-1].file_id
            text = msg.caption or ""
        elif msg.video:
            media_type = 'video'
            media_file_id = msg.video.file_id
            text = msg.caption or ""
        elif msg.document:
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

        posts = [(text, media_type or 'text', media_file_id or '')]
        count = await DB.add_posts(user_id, active, posts)
        
        if count > 0:
            await safe_send(context.bot, user_id, f"✅ تمت إضافة المنشور ({count})")
        else:
            await safe_send(context.bot, user_id, "❌ فشل الإضافة")

    @staticmethod
    async def _handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        content = update.effective_message.text or ""
        username = update.effective_user.username or ""
        
        media_type = None
        media_file_id = None
        
        if update.effective_message.photo:
            media_type = 'photo'
            media_file_id = update.effective_message.photo[-1].file_id
        elif update.effective_message.document:
            media_type = 'document'
            media_file_id = update.effective_message.document.file_id

        ticket_number = await DB.create_ticket(user_id, username, content, media_type, media_file_id)
        StateManager.clear(user_id)
        await safe_send(context.bot, user_id, f"✅ تم استلام رسالتك!\n🎫 رقم التذكرة: {ticket_number}")

    @staticmethod
    async def _handle_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = (update.effective_message.text or "").strip()
        
        try:
            if text.lstrip('-').isdigit():
                channel_id = int(text)
            else:
                channel_id = text.lstrip('@')
            
            channel_name = f"قناة {channel_id}"
            ch_db_id = await DB.add_channel(user_id, channel_id, channel_name)
            
            if ch_db_id:
                await safe_send(context.bot, user_id, f"✅ تمت إضافة القناة!")
            else:
                await safe_send(context.bot, user_id, "❌ فشل إضافة القناة (تأكد من أن البوت مشرف في القناة)")
        except Exception as e:
            await safe_send(context.bot, user_id, f"❌ خطأ: {str(e)[:50]}")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        content = update.effective_message.text or ""
        users = await DB.get_all_users()
        
        sent_count = 0
        for uid, banned in users:
            if banned == 0:
                try:
                    await safe_send(context.bot, uid, content)
                    sent_count += 1
                    await asyncio.sleep(0.05)
                except:
                    pass
        
        await safe_send(context.bot, user_id, f"✅ تم البث إلى {sent_count} مستخدم")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_update_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        content = update.effective_message.text or ""
        update_ch = await DB.get_updates_channel()
        
        if update_ch:
            try:
                await safe_send(context.bot, update_ch, content)
                await safe_send(context.bot, user_id, "✅ تم إرسال التحديث")
            except:
                await safe_send(context.bot, user_id, "❌ فشل الإرسال")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_update_ch_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        text = (update.effective_message.text or "").strip()
        await DB.set_setting('updates_channel', text)
        await safe_send(context.bot, user_id, f"✅ تم تعيين قناة التحديثات: {text}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_force_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        text = (update.effective_message.text or "").strip()
        await DB.set_setting('force_subscribe_channel', text)
        await safe_send(context.bot, user_id, f"✅ تم تعيين الاشتراك الإجباري: {text}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_log_ch_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        text = (update.effective_message.text or "").strip()
        await DB.set_setting('log_channel_id', text)
        await safe_send(context.bot, user_id, f"✅ تم تعيين قناة السجلات: {text}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_admin_add_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        text = (update.effective_message.text or "").strip()
        try:
            admin_id = int(text)
            await DB.execute("INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)",
                             (admin_id, user_id, TimeUtils.sql_iso()))
            await safe_send(context.bot, user_id, f"✅ تم إضافة المشرف: {admin_id}")
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_admin_rem_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        text = (update.effective_message.text or "").strip()
        try:
            admin_id = int(text)
            await DB.execute("DELETE FROM bot_admins WHERE user_id=?", (admin_id,))
            await safe_send(context.bot, user_id, f"✅ تم إزالة المشرف: {admin_id}")
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_keyword_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        keyword = (update.effective_message.text or "").strip().lower()
        context.user_data['auto_keyword'] = keyword
        StateManager.set(user_id, UserState.WAIT_REPLY)
        await safe_send(context.bot, user_id, f"✅ الكلمة: {keyword}\n📝 الآن أرسل الرد:")

    @staticmethod
    async def _handle_reply_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        keyword = context.user_data.get('auto_keyword', '')
        reply = update.effective_message.text or ""
        
        await DB.add_auto_reply(-1, keyword, reply)
        await safe_send(context.bot, user_id, f"✅ تم إضافة الرد: {keyword}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_global_ban_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        word = (update.effective_message.text or "").strip().lower()
        added, exists = await DB.add_banned_word(word, -1, user_id)
        
        if added:
            await invalidate_banned_words_cache(-1)
            await safe_send(context.bot, user_id, f"✅ تمت إضافة: {word}")
        elif exists:
            await safe_send(context.bot, user_id, "⚠️ الكلمة موجودة مسبقاً")
        else:
            await safe_send(context.bot, user_id, "❌ فشل الإضافة")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_rem_global_ban_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        word = (update.effective_message.text or "").strip().lower()
        await DB.remove_banned_word(word, -1)
        await invalidate_banned_words_cache(-1)
        await safe_send(context.bot, user_id, f"✅ تمت الإزالة: {word}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_group_ban_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('ban_chat', -1)
        word = (update.effective_message.text or "").strip().lower()
        added, exists = await DB.add_banned_word(word, chat_id, user_id)
        
        if added:
            await invalidate_banned_words_cache(chat_id)
            await safe_send(context.bot, user_id, f"✅ تمت الإضافة: {word}")
        else:
            await safe_send(context.bot, user_id, "❌ فشل الإضافة")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_rem_group_ban_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('ban_chat', -1)
        word = (update.effective_message.text or "").strip().lower()
        await DB.remove_banned_word(word, chat_id)
        await invalidate_banned_words_cache(chat_id)
        await safe_send(context.bot, user_id, f"✅ تمت الإزالة: {word}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_contest_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        context.user_data['contest_title'] = update.effective_message.text or ""
        StateManager.set(user_id, UserState.WAIT_CONTEST_DESC)
        await safe_send(context.bot, user_id, "📝 أرسل وصف المسابقة:")

    @staticmethod
    async def _handle_contest_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        context.user_data['contest_desc'] = update.effective_message.text or ""
        StateManager.set(user_id, UserState.WAIT_CONTEST_PRIZE)
        await safe_send(context.bot, user_id, "🎁 أرسل الجائزة:")

    @staticmethod
    async def _handle_contest_prize(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        context.user_data['contest_prize'] = update.effective_message.text or ""
        StateManager.set(user_id, UserState.WAIT_CONTEST_DATE)
        await safe_send(context.bot, user_id, "📅 أرسل تاريخ النهاية (YYYY-MM-DD HH:MM):")

    @staticmethod
    async def _handle_contest_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        title = context.user_data.get('contest_title', '')
        desc = context.user_data.get('contest_desc', '')
        prize = context.user_data.get('contest_prize', '')
        date = update.effective_message.text or ""
        
        contest_id = await DB.create_contest(user_id, title, desc, prize, date)
        if contest_id:
            await safe_send(context.bot, user_id, f"✅ تم إنشاء المسابقة #{contest_id}")
        else:
            await safe_send(context.bot, user_id, "❌ فشل إنشاء المسابقة")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_contest_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        contest_id = context.user_data.get('contest_join')
        answer = update.effective_message.text or ""
        
        if contest_id:
            joined = await DB.join_contest(contest_id, user_id, answer)
            if joined:
                await safe_send(context.bot, user_id, "✅ تم اشتراكك في المسابقة!")
            else:
                await safe_send(context.bot, user_id, "❌ فشل الاشتراك")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_auto_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        keyword = (update.effective_message.text or "").strip().lower()
        context.user_data['auto_keyword'] = keyword
        StateManager.set(user_id, UserState.WAIT_AUTO_REPLY)
        await safe_send(context.bot, user_id, f"✅ الكلمة: {keyword}\n📝 الآن أرسل الرد:")

    @staticmethod
    async def _handle_auto_reply_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('auto_chat', -1)
        keyword = context.user_data.get('auto_keyword', '')
        reply = update.effective_message.text or ""
        
        await DB.add_auto_reply(chat_id, keyword, reply)
        await invalidate_auto_reply_cache(chat_id)
        await safe_send(context.bot, user_id, f"✅ تم إضافة الرد: {keyword}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_auto_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('auto_chat', -1)
        keyword = (update.effective_message.text or "").strip().lower()
        
        await DB.remove_auto_reply(chat_id, keyword)
        await invalidate_auto_reply_cache(chat_id)
        await safe_send(context.bot, user_id, f"✅ تم حذف: {keyword}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_import_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not update.effective_message.document:
            await safe_send(context.bot, user_id, "❌ أرسل ملف JSON")
            StateManager.clear(user_id)
            return
        
        file = await update.effective_message.document.get_file()
        file_path = await file.download_to_drive()
        count = await import_auto_replies(-1, str(file_path))
        await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_github_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        url = (update.effective_message.text or "").strip()
        data = await fetch_json_from_url(url)
        
        if data:
            count = await import_auto_replies(-1, data)
            await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
        else:
            await safe_send(context.bot, user_id, "❌ فشل جلب البيانات")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_grant_free(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        
        parts = (update.effective_message.text or "").strip().split()
        if len(parts) >= 2:
            try:
                target_id = int(parts[0])
                days = int(parts[1])
                await DB.grant_subscription_days(target_id, days)
                await safe_send(context.bot, user_id, f"✅ تم منح {days} يوم للمستخدم {target_id}")
            except:
                await safe_send(context.bot, user_id, "❌ صيغة غير صحيحة")
        else:
            await safe_send(context.bot, user_id, "📝 أرسل: معرف_المستخدم عدد_الأيام")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_min_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        try:
            minutes = int(update.effective_message.text or "0")
            if minutes > 0:
                await DB.update_schedule(ch_id, interval_minutes=minutes, schedule_type='interval_minutes')
                await safe_send(context.bot, user_id, f"✅ تم التعيين: {minutes} دقيقة")
        except:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_hour_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        try:
            hours = int(update.effective_message.text or "0")
            if hours > 0:
                await DB.update_schedule(ch_id, interval_hours=hours, schedule_type='interval_hours')
                await safe_send(context.bot, user_id, f"✅ تم التعيين: {hours} ساعة")
        except:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_day_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        try:
            days = int(update.effective_message.text or "0")
            if days > 0:
                await DB.update_schedule(ch_id, interval_days=days, schedule_type='interval_days')
                await safe_send(context.bot, user_id, f"✅ تم التعيين: {days} يوم")
        except:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_pub_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        time_val = (update.effective_message.text or "").strip()
        await DB.update_schedule(ch_id, publish_time=time_val)
        await safe_send(context.bot, user_id, f"✅ تم التعيين: {time_val}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_rem_days_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        try:
            days = int(update.effective_message.text or "3")
            if 1 <= days <= 30:
                await DB.update_reminder_settings(user_id, reminder_days_before=days)
                await safe_send(context.bot, user_id, f"✅ تم التعيين: {days} يوم")
        except:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_max_len_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        try:
            max_len = int(update.effective_message.text or "0")
            await DB.update_security_settings(chat_id, max_message_length=max_len)
            await invalidate_security_cache(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {max_len}")
        except:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_warn_count_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        try:
            count = int(update.effective_message.text or "3")
            await DB.update_security_settings(chat_id, max_warnings=count)
            await invalidate_security_cache(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {count}")
        except:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_welcome_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        text = update.effective_message.text or ""
        await DB.update_security_settings(chat_id, welcome_text=text)
        await invalidate_security_cache(chat_id)
        await safe_send(context.bot, user_id, "✅ تم حفظ نص الترحيب")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_goodbye_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        text = update.effective_message.text or ""
        await DB.update_security_settings(chat_id, goodbye_text=text)
        await invalidate_security_cache(chat_id)
        await safe_send(context.bot, user_id, "✅ تم حفظ نص الوداع")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_slow_mode_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        try:
            seconds = int(update.effective_message.text or "0")
            await DB.update_security_settings(chat_id, slow_mode_seconds=seconds)
            await invalidate_security_cache(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {seconds} ثانية")
        except:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_antiflood_messages_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        try:
            count = int(update.effective_message.text or "5")
            await DB.update_security_settings(chat_id, antiflood_messages=count)
            await invalidate_security_cache(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {count}")
        except:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_antiflood_seconds_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        try:
            seconds = int(update.effective_message.text or "10")
            await DB.update_security_settings(chat_id, antiflood_seconds=seconds)
            await invalidate_security_cache(chat_id)
            await safe_send(context.bot, user_id, f"✅ تم التعيين: {seconds} ثانية")
        except:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_night_start_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        time_val = (update.effective_message.text or "").strip()
        await DB.update_security_settings(chat_id, night_mode_start=time_val)
        await invalidate_security_cache(chat_id)
        await safe_send(context.bot, user_id, f"✅ تم التعيين: {time_val}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_night_end_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        time_val = (update.effective_message.text or "").strip()
        await DB.update_security_settings(chat_id, night_mode_end=time_val)
        await invalidate_security_cache(chat_id)
        await safe_send(context.bot, user_id, f"✅ تم التعيين: {time_val}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_ban_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        parts = (update.effective_message.text or "").strip().split()
        
        if not parts:
            await safe_send(context.bot, user_id, "❌ أرسل معرف المستخدم")
            StateManager.clear(user_id)
            return
        
        try:
            target = int(parts[0])
            duration = int(parts[1]) * 60 if len(parts) > 1 else 0
            await apply_penalty(context.bot, chat_id, target, 'ban', duration, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم الحظر")
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_mute_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        parts = (update.effective_message.text or "").strip().split()
        
        if not parts:
            await safe_send(context.bot, user_id, "❌ أرسل معرف المستخدم")
            StateManager.clear(user_id)
            return
        
        try:
            target = int(parts[0])
            duration = int(parts[1]) * 60 if len(parts) > 1 else 60
            await apply_penalty(context.bot, chat_id, target, 'mute', duration, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم الكتم")
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_warn_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        
        try:
            target = int((update.effective_message.text or "").strip())
            await apply_penalty(context.bot, chat_id, target, 'warn', 0, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم التحذير")
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_kick_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        
        try:
            target = int((update.effective_message.text or "").strip())
            await apply_penalty(context.bot, chat_id, target, 'kick', 0, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم الطرد")
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_restrict_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        parts = (update.effective_message.text or "").strip().split()
        
        if not parts:
            await safe_send(context.bot, user_id, "❌ أرسل معرف المستخدم")
            StateManager.clear(user_id)
            return
        
        try:
            target = int(parts[0])
            duration = int(parts[1]) * 60 if len(parts) > 1 else 1800
            await apply_penalty(context.bot, chat_id, target, 'restrict', duration, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم التقييد")
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_unban_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        
        try:
            target = int((update.effective_message.text or "").strip())
            await apply_penalty(context.bot, chat_id, target, 'unban', 0, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم إلغاء الحظر")
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_pin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        
        if update.effective_message.reply_to_message:
            try:
                await context.bot.pin_chat_message(chat_id, update.effective_message.reply_to_message.message_id)
                await safe_send(context.bot, user_id, "✅ تم التثبيت")
            except:
                await safe_send(context.bot, user_id, "❌ فشل التثبيت")
        else:
            await safe_send(context.bot, user_id, "❌ رد على الرسالة أولاً")
        
        StateManager.clear(user_id)

    @staticmethod
    async def handle_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة رسائل الخدمة (انضمام/مغادرة)"""
        if not update.effective_chat or not update.effective_message:
            return

        chat_id = update.effective_chat.id
        settings = await get_security_settings_cached(chat_id)

        # الترحيب بالأعضاء الجدد
        if update.effective_message.new_chat_members and settings.get('welcome_enabled'):
            for member in update.effective_message.new_chat_members:
                welcome_text = settings.get('welcome_text', 'مرحباً {user} في {chat} 🤍')
                welcome_text = welcome_text.replace('{user}', member.first_name or "عضو جديد")
                welcome_text = welcome_text.replace('{chat}', update.effective_chat.title or "")
                await safe_send(context.bot, chat_id, welcome_text)

        # وداع الأعضاء المغادرين
        if update.effective_message.left_chat_member and settings.get('goodbye_enabled'):
            member = update.effective_message.left_chat_member
            goodbye_text = settings.get('goodbye_text', 'وداعاً {user} 👋')
            goodbye_text = goodbye_text.replace('{user}', member.first_name or "عضو")
            await safe_send(context.bot, chat_id, goodbye_text)

    @staticmethod
    async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالجة طلبات الانضمام"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        settings = await get_security_settings_cached(chat_id)

        if settings.get('auto_approve_join'):
            try:
                await context.bot.approve_chat_join_request(chat_id, user_id)
            except:
                pass

        if settings.get('auto_reject_join'):
            try:
                await context.bot.decline_chat_join_request(chat_id, user_id)
            except:
                pass
