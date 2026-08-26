#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_message.py - معالجات الرسائل - النسخة النهائية المتوافقة
=====================================================================
- متوافق مع database.py الحالي
- جميع الدوال موجودة بدون أخطاء
- تنظيم منطقي كامل
"""

import asyncio
import logging
import time
import re
import os
from typing import Optional

from telegram import Update
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
    fetch_json_from_url, import_auto_replies,
)

from replies import analyze_sentiment

logger = logging.getLogger(__name__)


# =====================================================================
# الكاش
# =====================================================================

_security_settings_cache = {}
_security_settings_time = {}
_auto_reply_settings_cache = {}
_auto_reply_settings_time = {}


async def get_security_settings_cached(chat_id: int) -> dict:
    now = time.time()
    if chat_id in _security_settings_cache and (now - _security_settings_time.get(chat_id, 0)) < 30:
        return _security_settings_cache[chat_id]
    settings = await DB.get_security_settings(chat_id)
    _security_settings_cache[chat_id] = settings
    _security_settings_time[chat_id] = now
    return settings


async def get_auto_reply_settings_cached(chat_id: int) -> dict:
    now = time.time()
    if chat_id in _auto_reply_settings_cache and (now - _auto_reply_settings_time.get(chat_id, 0)) < 60:
        return _auto_reply_settings_cache[chat_id]
    settings = await DB.get_auto_reply_settings(chat_id)
    _auto_reply_settings_cache[chat_id] = settings
    _auto_reply_settings_time[chat_id] = now
    return settings


async def invalidate_security_cache(chat_id: int = None) -> None:
    if chat_id:
        _security_settings_cache.pop(chat_id, None)
        _security_settings_time.pop(chat_id, None)
    else:
        _security_settings_cache.clear()
        _security_settings_time.clear()


async def invalidate_auto_reply_cache(chat_id: int = None) -> None:
    if chat_id:
        _auto_reply_settings_cache.pop(chat_id, None)
        _auto_reply_settings_time.pop(chat_id, None)
    else:
        _auto_reply_settings_cache.clear()
        _auto_reply_settings_time.clear()


async def _delete_after_delay(bot, chat_id: int, message_id: int, delay: int = 10):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def apply_violation_penalty(update, context, chat_id, user_id, violation_type, penalty_type, duration_seconds):
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
# معالجات الرسائل
# =====================================================================

class MessageHandlers:

    # =================================================================
    # الرسائل الخاصة
    # =================================================================

    @staticmethod
    async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        state = StateManager.get(user_id)

        if state == UserState.WAIT_MOOD:
            text = update.effective_message.text or ""
            result = analyze_sentiment(text)
            response = (
                f"{result['emoji']} **تحليل المشاعر**\n\n"
                f"📝 النص: `{text[:100]}`\n"
                f"🎯 النتيجة: {result['sentiment']}\n"
                f"💬 {result.get('response', '')}\n\n"
                f"😊 إيجابي: {result['positive_percent']:.0f}%\n"
                f"😔 سلبي: {result['negative_percent']:.0f}%\n"
                f"📊 الكلمات: {result['total_words']}"
            )
            await safe_send(context.bot, user_id, response)
            StateManager.clear(user_id)
            return

        handlers = {
            UserState.WAIT_CHANNEL: MessageHandlers._handle_channel_input,
            UserState.ADDING_POSTS: MessageHandlers._handle_adding_posts,
            UserState.SUPPORT_MODE: MessageHandlers._handle_support_message,
            UserState.WAIT_BROADCAST: MessageHandlers._handle_broadcast_input,
            UserState.WAIT_UPDATE: MessageHandlers._handle_update_input,
            UserState.WAIT_UPDATE_CH: MessageHandlers._handle_update_ch_input,
            UserState.WAIT_FORCE: MessageHandlers._handle_force_input,
            UserState.WAIT_LOG_CH: MessageHandlers._handle_log_ch_input,
            UserState.WAIT_ADMIN_ADD: MessageHandlers._handle_admin_add_input,
            UserState.WAIT_ADMIN_REM: MessageHandlers._handle_admin_rem_input,
            UserState.WAIT_KEYWORD: MessageHandlers._handle_keyword_input,
            UserState.WAIT_REPLY: MessageHandlers._handle_reply_input,
            UserState.WAIT_GLOBAL_BAN: MessageHandlers._handle_global_ban_input,
            UserState.WAIT_REM_GLOBAL_BAN: MessageHandlers._handle_rem_global_ban_input,
            UserState.WAIT_GROUP_BAN: MessageHandlers._handle_group_ban_input,
            UserState.WAIT_REM_GROUP_BAN: MessageHandlers._handle_rem_group_ban_input,
            UserState.WAIT_CONTEST_TITLE: MessageHandlers._handle_contest_title,
            UserState.WAIT_CONTEST_DESC: MessageHandlers._handle_contest_desc,
            UserState.WAIT_CONTEST_PRIZE: MessageHandlers._handle_contest_prize,
            UserState.WAIT_CONTEST_DATE: MessageHandlers._handle_contest_date,
            UserState.WAIT_CONTEST_ANSWER: MessageHandlers._handle_contest_answer,
            UserState.WAIT_AUTO_KEY: MessageHandlers._handle_auto_key,
            UserState.WAIT_AUTO_REPLY: MessageHandlers._handle_auto_reply_input,
            UserState.WAIT_AUTO_DEL: MessageHandlers._handle_auto_del,
            UserState.WAIT_IMPORT_FILE: MessageHandlers._handle_import_file,
            UserState.WAIT_GITHUB_URL: MessageHandlers._handle_github_url,
            UserState.WAIT_GRANT_FREE: MessageHandlers._handle_grant_free,
            UserState.WAIT_MIN: MessageHandlers._handle_min_input,
            UserState.WAIT_HOUR: MessageHandlers._handle_hour_input,
            UserState.WAIT_DAY: MessageHandlers._handle_day_input,
            UserState.WAIT_PUB_TIME: MessageHandlers._handle_pub_time_input,
            UserState.WAIT_REM_DAYS: MessageHandlers._handle_rem_days_input,
            UserState.WAIT_MAX_LEN: MessageHandlers._handle_max_len_input,
            UserState.WAIT_WARN_COUNT: MessageHandlers._handle_warn_count_input,
            UserState.WAIT_WELCOME_TEXT: MessageHandlers._handle_welcome_text_input,
            UserState.WAIT_GOODBYE_TEXT: MessageHandlers._handle_goodbye_text_input,
            UserState.WAIT_SLOW_MODE_SECONDS: MessageHandlers._handle_slow_mode_input,
            UserState.WAIT_ANTIFLOOD_MESSAGES: MessageHandlers._handle_antiflood_messages_input,
            UserState.WAIT_ANTIFLOOD_SECONDS: MessageHandlers._handle_antiflood_seconds_input,
            UserState.WAIT_NIGHT_START: MessageHandlers._handle_night_start_input,
            UserState.WAIT_NIGHT_END: MessageHandlers._handle_night_end_input,
            UserState.WAIT_BAN: MessageHandlers._handle_ban_input,
            UserState.WAIT_MUTE: MessageHandlers._handle_mute_input,
            UserState.WAIT_WARN: MessageHandlers._handle_warn_input,
            UserState.WAIT_KICK: MessageHandlers._handle_kick_input,
            UserState.WAIT_RESTRICT: MessageHandlers._handle_restrict_input,
            UserState.WAIT_UNBAN: MessageHandlers._handle_unban_input,
            UserState.WAIT_PIN: MessageHandlers._handle_pin_input,
        }

        handler = handlers.get(state)
        if handler:
            await handler(update, context)

    # =================================================================
    # رسائل المجموعات
    # =================================================================

    @staticmethod
    async def handle_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.effective_message:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        message = update.effective_message
        text = message.text or ""

        METRICS.increment_messages()
        settings = await get_security_settings_cached(chat_id)

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

        # فحص الرسائل المعاد توجيهها
        if getattr(message, 'forward_origin', None) and settings.get('delete_forwarded'):
            await MessageHandlers._delete_and_warn(update, context, chat_id, user_id, "forwarded")
            return

        # فحص الوسائط
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

        # الردود التلقائية
        if text:
            await MessageHandlers._process_auto_reply(update, context, chat_id, text, user_id)

    # =================================================================
    # حذف وتحذير
    # =================================================================

    @staticmethod
    async def _delete_and_warn(update, context, chat_id, user_id, violation_type):
        try:
            await update.effective_message.delete()
        except Exception:
            pass

        violation_count = await DB.increment_violation_count(user_id, chat_id)
        penalty_rule = await DB.get_violation_penalty(chat_id, violation_type)
        
        if penalty_rule:
            penalty_type = penalty_rule['penalty_type']
            duration_seconds = penalty_rule['duration_seconds']
        else:
            penalty_type = 'mute'
            duration_seconds = 60

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
            asyncio.create_task(_delete_after_delay(context.bot, chat_id, sent_msg.message_id, 10))
        except Exception:
            pass

        security_settings = await get_security_settings_cached(chat_id)
        max_strikes = security_settings.get('violation_strikes', 3)
        
        if violation_count >= max_strikes:
            success, msg = await apply_violation_penalty(
                update, context, chat_id, user_id, violation_type, penalty_type, duration_seconds
            )
            if success:
                await safe_send(context.bot, chat_id, f"🚨 {msg}")

    # =================================================================
    # الردود التلقائية
    # =================================================================

    @staticmethod
    async def _process_auto_reply(update, context, chat_id, text, user_id=None):
        try:
            ars = await get_auto_reply_settings_cached(chat_id)
            if not ars.get('enabled', False):
                return False
            if ars.get('ignore_bots', True) and update.effective_user.is_bot:
                return False
            if ars.get('only_admins', False):
                if not await is_authorized_in_group(context.bot, chat_id, user_id or update.effective_user.id):
                    return False

            reply = await DB.get_auto_reply(text, chat_id)
            if reply:
                reply_text = reply.get('reply', '')
                await safe_send(context.bot, chat_id, reply_text)
                await _increment_usage_async(chat_id, text)
                return True

            file_reply = get_reply_from_file(text)
            if file_reply:
                await safe_send(context.bot, chat_id, file_reply)
                return True
            return False
        except Exception as e:
            logger.error(f"❌ خطأ في الردود: {e}")
            return False

    # =================================================================
    # إضافة القناة
    # =================================================================

    @staticmethod
    async def _handle_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = (update.effective_message.text or "").strip()
        
        # التحقق من الاشتراك
        if user_id != CONFIG.PRIMARY_OWNER_ID:
            has_sub = await DB.has_active_subscription(user_id)
            if not has_sub:
                await safe_send(
                    context.bot, user_id,
                    "❌ **يجب أن يكون لديك اشتراك نشط لإضافة قناة!**\n\n"
                    "📌 استخدم /subscribe للاشتراك\n"
                    "🎁 أو /trial للتجربة المجانية"
                )
                StateManager.clear(user_id)
                return
        
        try:
            # تحديد معرف القناة
            if text.lstrip('-').isdigit():
                channel_id = int(text)
            else:
                try:
                    chat = await context.bot.get_chat(text)
                    channel_id = chat.id
                except:
                    await safe_send(context.bot, user_id, "❌ القناة غير موجودة!")
                    StateManager.clear(user_id)
                    return
            
            # جلب اسم القناة
            try:
                chat_info = await context.bot.get_chat(channel_id)
                channel_name = chat_info.title or chat_info.username or f"قناة {channel_id}"
            except:
                channel_name = f"قناة {channel_id}"
            
            # التحقق من أن البوت مشرف
            try:
                bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
                if bot_member.status != 'administrator':
                    await safe_send(context.bot, user_id, "❌ البوت ليس مشرفًا في القناة!")
                    StateManager.clear(user_id)
                    return
            except:
                pass
            
            # إضافة القناة
            ch_db_id = await DB.add_channel(user_id, channel_id, channel_name)
            
            if ch_db_id:
                await safe_send(context.bot, user_id, f"✅ تمت إضافة القناة: {channel_name}")
            else:
                await safe_send(context.bot, user_id, "❌ فشل إضافة القناة")
        except Exception as e:
            await safe_send(context.bot, user_id, f"❌ خطأ: {str(e)[:50]}")
        
        StateManager.clear(user_id)

    # =================================================================
    # إضافة المنشورات
    # =================================================================

    @staticmethod
    async def _handle_adding_posts(update, context):
        user_id = update.effective_user.id
        active = await DB.get_active_channel(user_id)
        if not active:
            StateManager.clear(user_id)
            await safe_send(context.bot, user_id, "❌ لا توجد قناة نشطة")
            return

        msg = update.effective_message
        media_type = 'text'
        media_file_id = ''
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

        posts = [(text, media_type, media_file_id)]
        count = await DB.add_posts(user_id, active, posts)
        
        if count > 0:
            await safe_send(context.bot, user_id, "✅ تمت إضافة المنشور")
        else:
            await safe_send(context.bot, user_id, "❌ فشل الإضافة")

    # =================================================================
    # الدعم الفني
    # =================================================================

    @staticmethod
    async def _handle_support_message(update, context):
        user_id = update.effective_user.id
        content = update.effective_message.text or ""
        username = update.effective_user.username or ""
        ticket_number = await DB.create_ticket(user_id, username, content)
        StateManager.clear(user_id)
        await safe_send(context.bot, user_id, f"✅ تم استلام رسالتك!\n🎫 رقم التذكرة: {ticket_number}")

    # =================================================================
    # البث الجماعي
    # =================================================================

    @staticmethod
    async def _handle_broadcast_input(update, context):
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

    # =================================================================
    # التحديثات والإعدادات
    # =================================================================

    @staticmethod
    async def _handle_update_input(update, context):
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
    async def _handle_update_ch_input(update, context):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        text = (update.effective_message.text or "").strip()
        await DB.set_setting('updates_channel', text)
        await safe_send(context.bot, user_id, f"✅ تم تعيين: {text}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_force_input(update, context):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        text = (update.effective_message.text or "").strip()
        await DB.set_setting('force_subscribe_channel', text)
        await safe_send(context.bot, user_id, f"✅ تم تعيين: {text}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_log_ch_input(update, context):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        text = (update.effective_message.text or "").strip()
        await DB.set_setting('log_channel_id', text)
        await safe_send(context.bot, user_id, f"✅ تم تعيين: {text}")
        StateManager.clear(user_id)

    # =================================================================
    # المشرفين
    # =================================================================

    @staticmethod
    async def _handle_admin_add_input(update, context):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        text = (update.effective_message.text or "").strip()
        try:
            admin_id = int(text)
            await DB.execute("INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)",
                             (admin_id, user_id, TimeUtils.sql_iso()))
            await safe_send(context.bot, user_id, "✅ تمت الإضافة")
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_admin_rem_input(update, context):
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            StateManager.clear(user_id)
            return
        text = (update.effective_message.text or "").strip()
        try:
            admin_id = int(text)
            await DB.execute("DELETE FROM bot_admins WHERE user_id=?", (admin_id,))
            await safe_send(context.bot, user_id, "✅ تمت الإزالة")
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
        StateManager.clear(user_id)

    # =================================================================
    # الردود التلقائية - إدارة
    # =================================================================

    @staticmethod
    async def _handle_keyword_input(update, context):
        user_id = update.effective_user.id
        keyword = (update.effective_message.text or "").strip().lower()
        context.user_data['auto_keyword'] = keyword
        StateManager.set(user_id, UserState.WAIT_REPLY)
        await safe_send(context.bot, user_id, f"✅ الكلمة: {keyword}\n📝 أرسل الرد:")

    @staticmethod
    async def _handle_reply_input(update, context):
        user_id = update.effective_user.id
        keyword = context.user_data.get('auto_keyword', '')
        reply = update.effective_message.text or ""
        await DB.add_auto_reply(-1, keyword, reply)
        await safe_send(context.bot, user_id, "✅ تمت الإضافة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_auto_key(update, context):
        user_id = update.effective_user.id
        keyword = (update.effective_message.text or "").strip().lower()
        context.user_data['auto_keyword'] = keyword
        StateManager.set(user_id, UserState.WAIT_AUTO_REPLY)
        await safe_send(context.bot, user_id, f"✅ الكلمة: {keyword}\n📝 أرسل الرد:")

    @staticmethod
    async def _handle_auto_reply_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('auto_chat', -1)
        keyword = context.user_data.get('auto_keyword', '')
        reply = update.effective_message.text or ""
        await DB.add_auto_reply(chat_id, keyword, reply)
        await invalidate_auto_reply_cache(chat_id)
        await safe_send(context.bot, user_id, "✅ تمت الإضافة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_auto_del(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('auto_chat', -1)
        keyword = (update.effective_message.text or "").strip().lower()
        await DB.remove_auto_reply(chat_id, keyword)
        await invalidate_auto_reply_cache(chat_id)
        await safe_send(context.bot, user_id, "✅ تم الحذف")
        StateManager.clear(user_id)

    # =================================================================
    # الكلمات المحظورة - إدارة
    # =================================================================

    @staticmethod
    async def _handle_global_ban_input(update, context):
        user_id = update.effective_user.id
        word = (update.effective_message.text or "").strip().lower()
        added, _ = await DB.add_banned_word(word, -1, user_id)
        if added:
            await invalidate_banned_words_cache(-1)
            await safe_send(context.bot, user_id, f"✅ تمت الإضافة: {word}")
        else:
            await safe_send(context.bot, user_id, "❌ فشل")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_rem_global_ban_input(update, context):
        user_id = update.effective_user.id
        word = (update.effective_message.text or "").strip().lower()
        await DB.remove_banned_word(word, -1)
        await invalidate_banned_words_cache(-1)
        await safe_send(context.bot, user_id, "✅ تمت الإزالة")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_group_ban_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('ban_chat', -1)
        word = (update.effective_message.text or "").strip().lower()
        added, _ = await DB.add_banned_word(word, chat_id, user_id)
        if added:
            await invalidate_banned_words_cache(chat_id)
            await safe_send(context.bot, user_id, "✅ تمت الإضافة")
        else:
            await safe_send(context.bot, user_id, "❌ فشل")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_rem_group_ban_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('ban_chat', -1)
        word = (update.effective_message.text or "").strip().lower()
        await DB.remove_banned_word(word, chat_id)
        await invalidate_banned_words_cache(chat_id)
        await safe_send(context.bot, user_id, "✅ تمت الإزالة")
        StateManager.clear(user_id)

    # =================================================================
    # المسابقات
    # =================================================================

    @staticmethod
    async def _handle_contest_title(update, context):
        user_id = update.effective_user.id
        context.user_data['contest_title'] = update.effective_message.text or ""
        StateManager.set(user_id, UserState.WAIT_CONTEST_DESC)
        await safe_send(context.bot, user_id, "📝 أرسل الوصف:")

    @staticmethod
    async def _handle_contest_desc(update, context):
        user_id = update.effective_user.id
        context.user_data['contest_desc'] = update.effective_message.text or ""
        StateManager.set(user_id, UserState.WAIT_CONTEST_PRIZE)
        await safe_send(context.bot, user_id, "🎁 أرسل الجائزة:")

    @staticmethod
    async def _handle_contest_prize(update, context):
        user_id = update.effective_user.id
        context.user_data['contest_prize'] = update.effective_message.text or ""
        StateManager.set(user_id, UserState.WAIT_CONTEST_DATE)
        await safe_send(context.bot, user_id, "📅 أرسل التاريخ:")

    @staticmethod
    async def _handle_contest_date(update, context):
        user_id = update.effective_user.id
        title = context.user_data.get('contest_title', '')
        desc = context.user_data.get('contest_desc', '')
        prize = context.user_data.get('contest_prize', '')
        date = update.effective_message.text or ""
        contest_id = await DB.create_contest(user_id, title, desc, prize, date)
        if contest_id:
            await safe_send(context.bot, user_id, f"✅ تم الإنشاء #{contest_id}")
        else:
            await safe_send(context.bot, user_id, "❌ فشل")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_contest_answer(update, context):
        user_id = update.effective_user.id
        contest_id = context.user_data.get('contest_join')
        answer = update.effective_message.text or ""
        if contest_id:
            joined = await DB.join_contest(contest_id, user_id, answer)
            if joined:
                await safe_send(context.bot, user_id, "✅ تم الاشتراك!")
            else:
                await safe_send(context.bot, user_id, "❌ فشل")
        StateManager.clear(user_id)

    # =================================================================
    # الاستيراد
    # =================================================================

    @staticmethod
    async def _handle_import_file(update, context):
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
    async def _handle_github_url(update, context):
        user_id = update.effective_user.id
        url = (update.effective_message.text or "").strip()
        data = await fetch_json_from_url(url)
        if data:
            count = await import_auto_replies(-1, data)
            await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
        else:
            await safe_send(context.bot, user_id, "❌ فشل")
        StateManager.clear(user_id)

    # =================================================================
    # منح اشتراك
    # =================================================================

    @staticmethod
    async def _handle_grant_free(update, context):
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
                await safe_send(context.bot, user_id, "✅ تم المنح")
            except:
                await safe_send(context.bot, user_id, "❌ صيغة خاطئة")
        StateManager.clear(user_id)

    # =================================================================
    # الجدولة
    # =================================================================

    @staticmethod
    async def _handle_min_input(update, context):
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        try:
            minutes = int(update.effective_message.text or "0")
            if minutes > 0:
                await DB.update_schedule(ch_id, interval_minutes=minutes, schedule_type='interval_minutes')
                await safe_send(context.bot, user_id, f"✅ {minutes} دقيقة")
        except:
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_hour_input(update, context):
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        try:
            hours = int(update.effective_message.text or "0")
            if hours > 0:
                await DB.update_schedule(ch_id, interval_hours=hours, schedule_type='interval_hours')
                await safe_send(context.bot, user_id, f"✅ {hours} ساعة")
        except:
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_day_input(update, context):
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        try:
            days = int(update.effective_message.text or "0")
            if days > 0:
                await DB.update_schedule(ch_id, interval_days=days, schedule_type='interval_days')
                await safe_send(context.bot, user_id, f"✅ {days} يوم")
        except:
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_pub_time_input(update, context):
        user_id = update.effective_user.id
        ch_id = context.user_data.get('schedule_ch')
        time_val = (update.effective_message.text or "").strip()
        await DB.update_schedule(ch_id, publish_time=time_val)
        await safe_send(context.bot, user_id, f"✅ {time_val}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_rem_days_input(update, context):
        user_id = update.effective_user.id
        try:
            days = int(update.effective_message.text or "3")
            if 1 <= days <= 30:
                await DB.update_reminder_settings(user_id, reminder_days_before=days)
                await safe_send(context.bot, user_id, f"✅ {days} يوم")
        except:
            pass
        StateManager.clear(user_id)

    # =================================================================
    # إعدادات الأمان
    # =================================================================

    @staticmethod
    async def _handle_max_len_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        try:
            max_len = int(update.effective_message.text or "0")
            await DB.update_security_settings(chat_id, max_message_length=max_len)
            await invalidate_security_cache(chat_id)
            await safe_send(context.bot, user_id, f"✅ {max_len}")
        except:
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_warn_count_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        try:
            count = int(update.effective_message.text or "3")
            await DB.update_security_settings(chat_id, max_warnings=count)
            await invalidate_security_cache(chat_id)
            await safe_send(context.bot, user_id, f"✅ {count}")
        except:
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_welcome_text_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        text = update.effective_message.text or ""
        await DB.update_security_settings(chat_id, welcome_text=text)
        await invalidate_security_cache(chat_id)
        await safe_send(context.bot, user_id, "✅ تم الحفظ")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_goodbye_text_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        text = update.effective_message.text or ""
        await DB.update_security_settings(chat_id, goodbye_text=text)
        await invalidate_security_cache(chat_id)
        await safe_send(context.bot, user_id, "✅ تم الحفظ")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_slow_mode_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        try:
            seconds = int(update.effective_message.text or "0")
            await DB.update_security_settings(chat_id, slow_mode_seconds=seconds)
            await invalidate_security_cache(chat_id)
            await safe_send(context.bot, user_id, f"✅ {seconds}")
        except:
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_antiflood_messages_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        try:
            count = int(update.effective_message.text or "5")
            await DB.update_security_settings(chat_id, antiflood_messages=count)
            await invalidate_security_cache(chat_id)
            await safe_send(context.bot, user_id, f"✅ {count}")
        except:
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_antiflood_seconds_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        try:
            seconds = int(update.effective_message.text or "10")
            await DB.update_security_settings(chat_id, antiflood_seconds=seconds)
            await invalidate_security_cache(chat_id)
            await safe_send(context.bot, user_id, f"✅ {seconds}")
        except:
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_night_start_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        time_val = (update.effective_message.text or "").strip()
        await DB.update_security_settings(chat_id, night_mode_start=time_val)
        await invalidate_security_cache(chat_id)
        await safe_send(context.bot, user_id, f"✅ {time_val}")
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_night_end_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('sec_chat')
        time_val = (update.effective_message.text or "").strip()
        await DB.update_security_settings(chat_id, night_mode_end=time_val)
        await invalidate_security_cache(chat_id)
        await safe_send(context.bot, user_id, f"✅ {time_val}")
        StateManager.clear(user_id)

    # =================================================================
    # العقوبات
    # =================================================================

    @staticmethod
    async def _handle_ban_input(update, context):
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
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_mute_input(update, context):
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
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_warn_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        try:
            target = int((update.effective_message.text or "").strip())
            await apply_penalty(context.bot, chat_id, target, 'warn', 0, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم التحذير")
        except:
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_kick_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        try:
            target = int((update.effective_message.text or "").strip())
            await apply_penalty(context.bot, chat_id, target, 'kick', 0, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم الطرد")
        except:
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_restrict_input(update, context):
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
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_unban_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        try:
            target = int((update.effective_message.text or "").strip())
            await apply_penalty(context.bot, chat_id, target, 'unban', 0, "", user_id)
            await safe_send(context.bot, user_id, "✅ تم إلغاء الحظر")
        except:
            pass
        StateManager.clear(user_id)

    @staticmethod
    async def _handle_pin_input(update, context):
        user_id = update.effective_user.id
        chat_id = context.user_data.get('adv_chat')
        if update.effective_message.reply_to_message:
            try:
                await context.bot.pin_chat_message(chat_id, update.effective_message.reply_to_message.message_id)
                await safe_send(context.bot, user_id, "✅ تم التثبيت")
            except:
                pass
        StateManager.clear(user_id)

    # =================================================================
    # رسائل الخدمة
    # =================================================================

    @staticmethod
    async def handle_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not update.effective_message:
            return
        chat_id = update.effective_chat.id
        settings = await get_security_settings_cached(chat_id)

        if update.effective_message.new_chat_members and settings.get('welcome_enabled'):
            for member in update.effective_message.new_chat_members:
                welcome_text = settings.get('welcome_text', 'مرحباً {user} 🤍')
                welcome_text = welcome_text.replace('{user}', member.first_name or "عضو")
                await safe_send(context.bot, chat_id, welcome_text)

        if update.effective_message.left_chat_member and settings.get('goodbye_enabled'):
            member = update.effective_message.left_chat_member
            goodbye_text = settings.get('goodbye_text', 'وداعاً {user} 👋')
            goodbye_text = goodbye_text.replace('{user}', member.first_name or "عضو")
            await safe_send(context.bot, chat_id, goodbye_text)

    # =================================================================
    # طلبات الانضمام
    # =================================================================

    @staticmethod
    async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
