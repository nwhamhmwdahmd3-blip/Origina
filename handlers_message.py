#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_message.py - معالجات الرسائل (النسخة النهائية الكاملة)
=============================================================
تشمل معالجة جميع حالات الرسائل الخاصة والمجموعات.
- إصلاح معاقبة رسائل الخدمة
- إصلاح استخراج المحتوى
- إزالة حظر المحتوى الرقمي
- التحقق من صلاحية المطور في WAIT_BROADCAST
- تحديد طول الرسالة في handle_group
"""

import asyncio
import re
import logging
from pathlib import Path
from datetime import datetime

from telegram import Update, ChatPermissions
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

logger = logging.getLogger(__name__)

MAX_CAPTION_LENGTH = 1024
MAX_MESSAGE_LENGTH = 4096


async def _safe_answer(query, text=None, show_alert=False):
    """دالة مساعدة للإجابة على الاستعلامات بأمان"""
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
    """إخفاء جزء من المعرفات الحساسة"""
    if id_value is None:
        return "***"
    s = str(id_value)
    if len(s) <= 5:
        return "***"
    return s[:prefix] + "***" + s[-suffix:] if len(s) > prefix + suffix else s[:prefix] + "***"


async def _check_admin_simple(bot, chat_id: int, user_id: int) -> bool:
    """تتحقق ببساطة مما إذا كان المستخدم مشرفاً في المجموعة."""
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


async def apply_violation_penalty(context, chat_id, user_id, violation_type, reason="مخالفة"):
    """تطبق عقوبة على مستخدم بناءً على نوع المخالفة"""
    # ✅ لا تعاقب البوت نفسه
    if user_id == context.bot.id:
        return
    
    # ✅ لا تعاقب البوتات
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.user.is_bot:
            return
    except Exception:
        pass
    
    # لا تعاقب المشرفين
    if await is_authorized_in_group(context.bot, chat_id, user_id):
        return

    warnings = await DB.add_user_warning(user_id, chat_id)
    info = await _get_penalty_info(chat_id, violation_type)
    penalty_type = info['penalty_type']
    duration_seconds = info['duration_seconds']
    settings = await DB.get_security_settings(chat_id)
    max_warnings = settings.get('max_warnings', 3)

    if warnings < max_warnings:
        try:
            await context.bot.send_message(
                chat_id,
                f"⚠️ المستخدم `{_mask_id(user_id)}` تلقى إنذارًا ({warnings}/{max_warnings}) بسبب: {reason}"
            )
        except Exception as e:
            logger.warning(f"⚠️ فشل إرسال إشعار التحذير: {e}")
        return

    try:
        success, msg = await apply_penalty(
            context.bot,
            chat_id,
            user_id,
            penalty=penalty_type,
            duration=duration_seconds,
            reason=f"تجاوز الحد الأقصى للتحذيرات ({max_warnings}): {reason}",
            moderator=context.bot.id
        )
        if success:
            await DB.reset_user_warnings(user_id, chat_id)
            try:
                await context.bot.send_message(
                    chat_id,
                    f"🚫 تم تطبيق عقوبة {penalty_type} على `{_mask_id(user_id)}` لتجاوز {max_warnings} تحذيرات"
                )
            except Exception as e:
                logger.warning(f"⚠️ فشل إرسال إشعار العقوبة: {e}")
        else:
            logger.error(f"❌ فشل تطبيق العقوبة: {msg}")
    except Exception as e:
        logger.error(f"❌ فشل تطبيق عقوبة {penalty_type} على {user_id}: {e}")


class MessageHandlers:
    """معالجات الرسائل"""

    @staticmethod
    async def handle_private(update, context):
        """معالجة الرسائل الخاصة"""
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        msg = update.message
        text = msg.text.strip() if msg.text else ""
        state = StateManager.get(user_id)

        # ============ استيراد ملف JSON ============
        if state == UserState.WAIT_IMPORT_FILE:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return

            if not msg.document:
                await safe_send(context.bot, user_id, "❌ أرسل ملف JSON")
                StateManager.clear(user_id)
                return

            file = msg.document
            if not file.file_name.endswith('.json'):
                await safe_send(context.bot, user_id, "❌ الملف يجب أن يكون JSON")
                StateManager.clear(user_id)
                return

            try:
                file_obj = await context.bot.get_file(file.file_id)
                temp_path = f"/tmp/import_{user_id}.json"
                await file_obj.download_to_drive(temp_path)
                import_chat_id = context.user_data.get('import_chat_id', -1)
                count = await import_auto_replies(import_chat_id, temp_path, overwrite=True)
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
                Path(temp_path).unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"❌ فشل الاستيراد: {e}")
                await safe_send(context.bot, user_id, f"❌ فشل الاستيراد: {str(e)[:50]}")
            StateManager.clear(user_id)
            return

        # ============ استيراد من GitHub ============
        if state == UserState.WAIT_GITHUB_URL:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return

            url = text.strip()
            if not url.startswith('http'):
                await safe_send(context.bot, user_id, "❌ رابط غير صالح")
                StateManager.clear(user_id)
                return

            json_data = await fetch_json_from_url(url)
            if not json_data:
                await safe_send(context.bot, user_id, "❌ فشل التحميل من الرابط")
                StateManager.clear(user_id)
                return

            count = await import_auto_replies(-1, json_data, overwrite=True)
            _auto_reply_cache.invalidate()
            await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
            StateManager.clear(user_id)
            return

        # ============ إضافة قناة ============
        if state == UserState.WAIT_CHANNEL:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return

            # ✅ التحقق من الاشتراك أولاً
            if user_id != CONFIG.PRIMARY_OWNER_ID:
                has_sub = await DB.has_active_subscription(user_id)
                if not has_sub:
                    await safe_send(context.bot, user_id, "❌ يجب أن يكون لديك اشتراك نشط لإضافة قناة")
                    StateManager.clear(user_id)
                    return

            try:
                chat = await context.bot.get_chat(text)
                if chat.type != 'channel':
                    await safe_send(context.bot, user_id, "❌ ليس قناة!")
                    StateManager.clear(user_id)
                    return

                try:
                    bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
                except Exception as e:
                    if "Member list is inaccessible" in str(e):
                        await safe_send(
                            context.bot, user_id,
                            "⚠️ **البوت ليس مشرفًا في هذه القناة.**\n"
                            "يرجى إضافة البوت كمشرف في القناة أولاً ثم حاول مجددًا."
                        )
                    else:
                        await safe_send(context.bot, user_id, f"❌ خطأ: {str(e)[:50]}")
                    StateManager.clear(user_id)
                    return

                if bot_member.status != 'administrator':
                    await safe_send(context.bot, user_id, "❌ البوت ليس مشرفاً في القناة!")
                    StateManager.clear(user_id)
                    return

                try:
                    user_member = await context.bot.get_chat_member(chat.id, user_id)
                except Exception as e:
                    if "Member list is inaccessible" in str(e):
                        await safe_send(
                            context.bot, user_id,
                            "⚠️ **تعذر التحقق من صلاحياتك.**\n"
                            "تأكد من أنك مشرف في القناة وأن البوت لديه صلاحية الوصول لقائمة الأعضاء."
                        )
                    else:
                        await safe_send(context.bot, user_id, f"❌ خطأ: {str(e)[:50]}")
                    StateManager.clear(user_id)
                    return

                if user_member.status not in ['creator', 'administrator']:
                    await safe_send(context.bot, user_id, "❌ يجب أن تكون مشرفًا في القناة لإضافتها.")
                    StateManager.clear(user_id)
                    return

                existing_channel = await DB.get_channel_by_user(user_id, chat.id)
                if existing_channel:
                    await safe_send(context.bot, user_id, "⚠️ هذه القناة مضافة مسبقاً")
                    StateManager.clear(user_id)
                    return

                if user_id != CONFIG.PRIMARY_OWNER_ID:
                    active_plan = await DB.get_active_plan(user_id)
                    if active_plan:
                        current_channels = len(await DB.get_user_channels(user_id))
                        if current_channels >= active_plan['max_channels']:
                            await safe_send(
                                context.bot,
                                user_id,
                                f"❌ لقد وصلت للحد الأقصى ({active_plan['max_channels']} قنوات) في خطتك."
                            )
                            StateManager.clear(user_id)
                            return

                result = await DB.add_channel(user_id, chat.id, chat.title or "قناة")
                if result:
                    await DB.set_active_channel(user_id, result)
                    await safe_send(context.bot, user_id, f"✅ تمت إضافة {chat.title}!")
                else:
                    await safe_send(context.bot, user_id, "❌ فشلت إضافة القناة (ربما تجاوزت الحد المسموح)")
            except Exception as e:
                logger.error(f"❌ فشل إضافة القناة: {e}")
                await safe_send(context.bot, user_id, f"❌ فشل إضافة القناة: {str(e)[:50]}")
            StateManager.clear(user_id)
            return

        # ============ إضافة منشورات ============
        if state == UserState.ADDING_POSTS:
            if text.strip().lower() == "/done":
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "✅ تم إنهاء إضافة المنشورات.")
                return

            # ✅ السماح بإضافة أي محتوى (بدون حظر المحتوى الرقمي)
            media_type = 'text'
            media_file_id = None
            if msg.photo:
                media_type = 'photo'
                media_file_id = msg.photo[-1].file_id
            elif msg.video:
                media_type = 'video'
                media_file_id = msg.video.file_id
            elif msg.document:
                media_type = 'document'
                media_file_id = msg.document.file_id
            elif msg.audio:
                media_type = 'audio'
                media_file_id = msg.audio.file_id
            elif msg.voice:
                media_type = 'voice'
                media_file_id = msg.voice.file_id
            elif msg.animation:
                media_type = 'animation'
                media_file_id = msg.animation.file_id
            elif msg.sticker:
                media_type = 'sticker'
                media_file_id = msg.sticker.file_id
            elif msg.video_note:
                media_type = 'video_note'
                media_file_id = msg.video_note.file_id

            # ✅ إصلاح استخراج المحتوى
            content = text if media_type == 'text' else (msg.caption or "")

            active = await DB.get_active_channel(user_id)
            if active:
                active_plan = await DB.get_active_plan(user_id)
                limit = active_plan['max_posts'] if active_plan else CONFIG.MAX_POSTS_PER_CHANNEL
                row = await DB.fetchone("SELECT COUNT(*) FROM posts WHERE channel_db_id=?", (active,))
                total_posts = row[0] if row else 0
                if total_posts >= limit and user_id != CONFIG.PRIMARY_OWNER_ID:
                    await safe_send(
                        context.bot,
                        user_id,
                        f"❌ وصلت للحد الأقصى ({limit} منشور) في هذه القناة.\n"
                        "احذف بعض المنشورات أو استخدم قناة أخرى."
                    )
                    StateManager.clear(user_id)
                    return

                added = await DB.add_posts(user_id, active, [(content, media_type, media_file_id)])
                if added > 0:
                    await safe_send(context.bot, user_id, "✅ تم حفظ المنشور!\nأرسل منشورًا آخر أو /done للإنهاء.")
                else:
                    await safe_send(context.bot, user_id, "❌ فشل حفظ المنشور (ربما تجاوزت الحد المسموح).")
            else:
                await safe_send(context.bot, user_id, "❌ لا توجد قناة نشطة.")
            return

        # ============ البث ============
        if state == UserState.WAIT_BROADCAST:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return

            # ✅ التحقق من صلاحية المطور
            if not CONFIG.is_developer(user_id):
                await safe_send(context.bot, user_id, "❌ غير مصرح لك بهذا الإجراء.")
                StateManager.clear(user_id)
                return

            async def broadcast():
                offset = 0
                sent = 0
                max_messages = 5000
                try:
                    while sent < max_messages:
                        users = await DB.fetchall(
                            "SELECT user_id, banned FROM users ORDER BY user_id LIMIT 5000 OFFSET ?",
                            (offset,)
                        )
                        if not users:
                            break
                        for user in users:
                            if not user['banned']:
                                try:
                                    await safe_send(context.bot, user['user_id'], text)
                                    sent += 1
                                    await asyncio.sleep(0.05)
                                except Exception:
                                    pass
                        offset += 5000
                    await safe_send(context.bot, user_id, f"✅ تم إرسال البث إلى {sent} مستخدم")
                except Exception as e:
                    logger.error(f"❌ فشل البث: {e}")
                    await safe_send(context.bot, user_id, f"❌ فشل البث: {str(e)[:50]}")

            asyncio.create_task(broadcast())
            await safe_send(context.bot, user_id, "⏳ جاري البث...")
            StateManager.clear(user_id)
            return

        # ============ الردود التلقائية ============
        if state == UserState.WAIT_AUTO_KEY:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            context.user_data['auto_key'] = text.strip().lower()
            StateManager.set(user_id, UserState.WAIT_AUTO_REPLY)
            await safe_send(context.bot, user_id, "📝 الرد:")
            return

        if state == UserState.WAIT_AUTO_REPLY:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            chat_id_auto = context.user_data.get('auto_chat')
            keyword = context.user_data.get('auto_key')
            if chat_id_auto is not None and keyword:
                await DB.add_auto_reply(chat_id_auto, keyword, text)
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, f"✅ تمت إضافة الرد على '{keyword}'")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_AUTO_DEL:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            chat_id_auto = context.user_data.get('auto_chat')
            if chat_id_auto is not None:
                await DB.remove_auto_reply(chat_id_auto, text.strip().lower())
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, f"✅ تم حذف الرد على '{text}'")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_KEYWORD:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            context.user_data['keyword'] = text.strip().lower()
            StateManager.set(user_id, UserState.WAIT_REPLY)
            await safe_send(context.bot, user_id, "📝 الرد:")
            return

        if state == UserState.WAIT_REPLY:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            keyword = context.user_data.get('keyword')
            if keyword:
                await DB.add_auto_reply(-1, keyword, text)
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, f"✅ تم إضافة الرد للكلمة: {keyword}")
            StateManager.clear(user_id)
            return

        # ============ الدعم ============
        if state == UserState.SUPPORT_MODE:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            content = msg.text or msg.caption or ""
            if not content:
                await safe_send(context.bot, user_id, "❌ أرسل رسالة تحتوي على نص.")
                StateManager.clear(user_id)
                return
            ticket_num = await DB.create_ticket(user_id, update.effective_user.username or "", content)
            await safe_send(context.bot, user_id, f"✅ تم إنشاء تذكرة #{ticket_num}")
            StateManager.clear(user_id)
            return

        # ============ الجدولة ============
        if state == UserState.WAIT_MIN:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                val = int(text)
                min_val = await get_min_publish_interval()
                if val < min_val:
                    await safe_send(context.bot, user_id, f"❌ الحد الأدنى للفاصل الزمني هو {min_val} دقيقة")
                    StateManager.clear(user_id)
                    return
                if 1 <= val <= 1440:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_minutes', interval_minutes=val)
                        await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {val} دقيقة")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-1440)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            except Exception as e:
                logger.error(f"❌ خطأ في WAIT_MIN: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_HOUR:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                val = int(text)
                if 1 <= val <= 168:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_hours', interval_hours=val)
                        await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {val} ساعة")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-168)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_DAY:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                val = int(text)
                if 1 <= val <= 365:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_days', interval_days=val)
                        await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {val} يوم")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-365)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PUB_TIME:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            if re.match(r'^\d{2}:\d{2}$', text):
                ch = context.user_data.get('schedule_ch')
                if ch:
                    await DB.update_schedule(ch, publish_time=text)
                    await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {text}")
            else:
                await safe_send(context.bot, user_id, "❌ الصيغة غير صالحة، استخدم HH:MM")
            StateManager.clear(user_id)
            return

        # ============ الكلمات الممنوعة ============
        if state == UserState.WAIT_GLOBAL_BAN:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            word = text.strip().lower()
            if len(word) >= 2:
                await DB.add_banned_word(word, -1, user_id)
                invalidate_banned_words_cache()
                await safe_send(context.bot, user_id, f"✅ تمت إضافة '{word}' إلى القائمة العالمية")
            else:
                await safe_send(context.bot, user_id, "❌ الكلمة قصيرة جداً")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GLOBAL_BAN:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            await DB.remove_banned_word(text.strip().lower(), -1)
            invalidate_banned_words_cache()
            await safe_send(context.bot, user_id, "✅ تم الحذف من القائمة العالمية")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GROUP_BAN:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            chat_id_ban = context.user_data.get('ban_chat')
            word = text.strip().lower()
            if chat_id_ban and len(word) >= 2:
                await DB.add_banned_word(word, chat_id_ban, user_id)
                invalidate_banned_words_cache(chat_id_ban)
                await safe_send(context.bot, user_id, f"✅ تمت إضافة: {word}")
            else:
                await safe_send(context.bot, user_id, "❌ كلمة غير صالحة أو مجموعة غير محددة")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GROUP_BAN:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            chat_id_ban = context.user_data.get('ban_chat')
            if chat_id_ban:
                await DB.remove_banned_word(text.strip().lower(), chat_id_ban)
                invalidate_banned_words_cache(chat_id_ban)
                await safe_send(context.bot, user_id, f"✅ تم حذف: {text}")
            StateManager.clear(user_id)
            return

        # ============ العقوبات ============
        if state in (UserState.WAIT_BAN, UserState.WAIT_MUTE, UserState.WAIT_WARN,
                     UserState.WAIT_KICK, UserState.WAIT_RESTRICT, UserState.WAIT_UNBAN):
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            chat_id_adv = context.user_data.get('adv_chat')
            if not chat_id_adv:
                await safe_send(context.bot, user_id, "❌ خطأ: لم يتم تحديد المجموعة")
                StateManager.clear(user_id)
                return
            if not await _check_admin_simple(context.bot, chat_id_adv, user_id):
                await safe_send(context.bot, user_id, "❌ غير مصرح لك بهذا الإجراء.")
                StateManager.clear(user_id)
                return
            try:
                parts = text.split()
                target = int(parts[0])
                if target <= 0:
                    await safe_send(context.bot, user_id, "❌ معرف غير صالح")
                    StateManager.clear(user_id)
                    return
                action_map = {
                    UserState.WAIT_BAN: "ban",
                    UserState.WAIT_MUTE: "mute",
                    UserState.WAIT_WARN: "warn",
                    UserState.WAIT_KICK: "kick",
                    UserState.WAIT_RESTRICT: "restrict",
                    UserState.WAIT_UNBAN: "unban"
                }
                action = action_map.get(state)
                if action:
                    duration_seconds = 60
                    if len(parts) > 1 and action in ('ban', 'mute', 'restrict'):
                        try:
                            minutes = int(parts[1])
                            if minutes > 0:
                                duration_seconds = minutes * 60
                        except ValueError:
                            pass
                    success, msg = await apply_penalty(
                        context.bot, chat_id_adv, target,
                        penalty=action,
                        duration=duration_seconds,
                        reason="بواسطة لوحة التحكم",
                        moderator=user_id
                    )
                    await safe_send(context.bot, user_id, msg)
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            except Exception as e:
                logger.error(f"❌ خطأ في الإجراء: {e}")
                await safe_send(context.bot, user_id, f"❌ خطأ: {str(e)[:50]}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PIN:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            chat_id_adv = context.user_data.get('adv_chat')
            if not chat_id_adv:
                await safe_send(context.bot, user_id, "❌ خطأ: لم يتم تحديد المجموعة")
                StateManager.clear(user_id)
                return
            if not await _check_admin_simple(context.bot, chat_id_adv, user_id):
                await safe_send(context.bot, user_id, "❌ غير مصرح لك بهذا الإجراء.")
                StateManager.clear(user_id)
                return
            try:
                if update.message.reply_to_message:
                    msg_id = update.message.reply_to_message.message_id
                else:
                    msg_id = int(text)
                perms = await check_bot_permissions(context.bot, chat_id_adv)
                if not perms.get('can_pin_messages', False):
                    await safe_send(context.bot, user_id, "❌ البوت لا يملك صلاحية تثبيت الرسائل.")
                    StateManager.clear(user_id)
                    return
                await context.bot.pin_chat_message(chat_id_adv, msg_id)
                await safe_send(context.bot, user_id, f"📌 تم تثبيت الرسالة {msg_id}")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح أو رد على رسالة")
            except Exception as e:
                logger.error(f"❌ فشل التثبيت: {e}")
                await safe_send(context.bot, user_id, f"❌ فشل التثبيت: {str(e)[:50]}")
            StateManager.clear(user_id)
            return

        # ============ المسابقات ============
        if state == UserState.WAIT_CONTEST_TITLE:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            context.user_data['contest_title'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_DESC)
            await safe_send(context.bot, user_id, "📝 الوصف:")
            return

        if state == UserState.WAIT_CONTEST_DESC:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            context.user_data['contest_desc'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_PRIZE)
            await safe_send(context.bot, user_id, "🎁 الجائزة:")
            return

        if state == UserState.WAIT_CONTEST_PRIZE:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            context.user_data['contest_prize'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_DATE)
            await safe_send(context.bot, user_id, "📅 التاريخ (YYYY-MM-DD HH:MM):")
            return

        if state == UserState.WAIT_CONTEST_DATE:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                end_date = datetime.strptime(text, "%Y-%m-%d %H:%M")
                # ✅ التحقق من أن التاريخ في المستقبل
                if end_date <= datetime.now():
                    await safe_send(context.bot, user_id, "❌ التاريخ يجب أن يكون في المستقبل")
                    StateManager.clear(user_id)
                    return
                cid = await DB.create_contest(
                    user_id,
                    context.user_data.pop('contest_title', ''),
                    context.user_data.pop('contest_desc', ''),
                    context.user_data.pop('contest_prize', ''),
                    TimeUtils.mecca_to_utc(end_date).strftime('%Y-%m-%d %H:%M:%S')
                )
                await safe_send(context.bot, user_id, f"✅ تم إنشاء المسابقة #{cid}")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ صيغة غير صالحة، استخدم YYYY-MM-DD HH:MM")
            except Exception as e:
                logger.error(f"❌ فشل إنشاء المسابقة: {e}")
                await safe_send(context.bot, user_id, f"❌ فشل إنشاء المسابقة: {str(e)[:50]}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_CONTEST_ANSWER:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            cid = context.user_data.get('contest_join')
            if cid:
                success = await DB.join_contest(cid, user_id, text)
                if success:
                    await safe_send(context.bot, user_id, "✅ تم المشاركة في المسابقة!")
                else:
                    await safe_send(context.bot, user_id, "❌ فشل المشاركة (ربما انتهت المسابقة أو شاركت مسبقًا)")
            StateManager.clear(user_id)
            return

        # ============ إدارة المشرفين ============
        if state == UserState.WAIT_ADMIN_ADD:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            if not CONFIG.is_developer(user_id):
                await safe_send(context.bot, user_id, "❌ غير مصرح لك بهذا الإجراء.")
                StateManager.clear(user_id)
                return
            try:
                target = int(text)
                if target <= 0:
                    await safe_send(context.bot, user_id, "❌ معرف غير صالح")
                else:
                    await DB.execute(
                        "INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)",
                        (target, user_id, TimeUtils.sql_iso())
                    )
                    await safe_send(context.bot, user_id, f"✅ تم إضافة `{_mask_id(target)}` كمشرف")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ADMIN_REM:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            if not CONFIG.is_developer(user_id):
                await safe_send(context.bot, user_id, "❌ غير مصرح لك بهذا الإجراء.")
                StateManager.clear(user_id)
                return
            try:
                target = int(text)
                if target <= 0:
                    await safe_send(context.bot, user_id, "❌ معرف غير صالح")
                else:
                    await DB.execute("DELETE FROM bot_admins WHERE user_id=?", (target,))
                    await safe_send(context.bot, user_id, f"✅ تم إزالة `{_mask_id(target)}`")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            StateManager.clear(user_id)
            return

        # ============ منح اشتراك مجاني ============
        if state == UserState.WAIT_GRANT_FREE:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            if not CONFIG.is_developer(user_id):
                await safe_send(context.bot, user_id, "❌ غير مصرح لك بهذا الإجراء.")
                StateManager.clear(user_id)
                return
            parts = text.split()
            if len(parts) < 2:
                await safe_send(context.bot, user_id, "❌ أرسل المعرف والأيام هكذا: `123456789 365`")
                StateManager.clear(user_id)
                return
            try:
                target_id = int(parts[0])
                days = int(parts[1])
                if target_id <= 0 or days < 1 or days > 365:
                    raise ValueError
            except (ValueError, TypeError):
                await safe_send(context.bot, user_id, "❌ قيم غير صالحة")
                StateManager.clear(user_id)
                return

            gift_plan = await DB.fetchone("SELECT id FROM plans WHERE is_gift=1 LIMIT 1")
            plan_id = gift_plan['id'] if gift_plan else None
            if plan_id is None:
                await safe_send(context.bot, user_id, "❌ لا توجد خطة هدية متاحة")
                StateManager.clear(user_id)
                return

            success = await DB.grant_subscription_days(target_id, days, plan_id=plan_id, provider='manual')
            if success:
                await safe_send(context.bot, user_id, f"✅ تم منح {days} يوم للمستخدم `{_mask_id(target_id)}`")
            else:
                await safe_send(context.bot, user_id, "❌ فشل المنح - تحقق من السجلات")
            StateManager.clear(user_id)
            return

        # ============ إعدادات المطور ============
        if state == UserState.WAIT_UPDATE:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            if not CONFIG.is_developer(user_id):
                await safe_send(context.bot, user_id, "❌ غير مصرح لك بهذا الإجراء.")
                StateManager.clear(user_id)
                return
            ch = await DB.get_updates_channel()
            if ch:
                try:
                    if ch.lstrip('-').isdigit():
                        await context.bot.send_message(int(ch), f"📢 {text}")
                    else:
                        await context.bot.send_message(f"@{ch}", f"📢 {text}")
                    await safe_send(context.bot, user_id, "✅ تم إرسال التحديث")
                except Exception as e:
                    await safe_send(context.bot, user_id, f"❌ فشل الإرسال: {str(e)[:50]}")
            else:
                await safe_send(context.bot, user_id, "❌ لا توجد قناة تحديثات")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_UPDATE_CH:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            if not CONFIG.is_developer(user_id):
                await safe_send(context.bot, user_id, "❌ غير مصرح لك بهذا الإجراء.")
                StateManager.clear(user_id)
                return
            await DB.set_setting('updates_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, f"✅ تم تعيين قناة التحديثات: {text}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_FORCE:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            if not CONFIG.is_developer(user_id):
                await safe_send(context.bot, user_id, "❌ غير مصرح لك بهذا الإجراء.")
                StateManager.clear(user_id)
                return
            await DB.set_setting('force_subscribe_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, f"✅ تم تعيين الاشتراك الإجباري: {text}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_LOG_CH:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            if not CONFIG.is_developer(user_id):
                await safe_send(context.bot, user_id, "❌ غير مصرح لك بهذا الإجراء.")
                StateManager.clear(user_id)
                return
            try:
                chat = await context.bot.get_chat(text)
                if chat.type == 'channel':
                    await DB.set_setting('log_channel_id', str(chat.id))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين قناة السجلات: {text}")
                else:
                    await safe_send(context.bot, user_id, "❌ هذه ليست قناة")
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ فشل التعيين: {str(e)[:50]}")
            StateManager.clear(user_id)
            return

        # ============ إعدادات الأمان ============
        if state == UserState.WAIT_REM_DAYS:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                val = int(text)
                if 1 <= val <= 30:
                    await DB.update_reminder_settings(user_id, reminder_days_before=val)
                    await safe_send(context.bot, user_id, f"✅ تم تعيين الأيام إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-30)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_MAX_LEN:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and val >= 0:
                    await DB.execute(
                        "UPDATE group_security SET max_message_length=? WHERE chat_id=?",
                        (val, chat_id_sec)
                    )
                    await safe_send(context.bot, user_id, f"✅ تم تعيين الحد الأقصى إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_WARN_COUNT:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and 1 <= val <= 10:
                    await DB.execute(
                        "UPDATE group_security SET max_warnings=? WHERE chat_id=?",
                        (val, chat_id_sec)
                    )
                    await safe_send(context.bot, user_id, f"✅ تم تعيين عدد التحذيرات إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-10)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_WELCOME_TEXT:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            chat_id_sec = context.user_data.get('sec_chat')
            if chat_id_sec:
                await DB.execute(
                    "UPDATE group_security SET welcome_text=? WHERE chat_id=?",
                    (text, chat_id_sec)
                )
                await safe_send(context.bot, user_id, "✅ تم تعيين نص الترحيب")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GOODBYE_TEXT:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            chat_id_sec = context.user_data.get('sec_chat')
            if chat_id_sec:
                await DB.execute(
                    "UPDATE group_security SET goodbye_text=? WHERE chat_id=?",
                    (text, chat_id_sec)
                )
                await safe_send(context.bot, user_id, "✅ تم تعيين نص الوداع")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_SLOW_MODE_SECONDS:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and 0 <= val <= 3600:
                    await DB.execute(
                        "UPDATE group_security SET slow_mode_seconds=? WHERE chat_id=?",
                        (val, chat_id_sec)
                    )
                    await safe_send(context.bot, user_id, f"✅ تم تعيين مدة الوضع البطيء إلى {val} ثانية")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (0-3600)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ANTIFLOOD_MESSAGES:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and val >= 1:
                    await DB.execute(
                        "UPDATE group_security SET antiflood_messages=? WHERE chat_id=?",
                        (val, chat_id_sec)
                    )
                    await safe_send(context.bot, user_id, f"✅ تم تعيين عدد الرسائل إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ANTIFLOOD_SECONDS:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and val >= 1:
                    await DB.execute(
                        "UPDATE group_security SET antiflood_seconds=? WHERE chat_id=?",
                        (val, chat_id_sec)
                    )
                    await safe_send(context.bot, user_id, f"✅ تم تعيين الفترة إلى {val} ثانية")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_NIGHT_START:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            if re.match(r'^\d{2}:\d{2}$', text):
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec:
                    await DB.execute(
                        "UPDATE group_security SET night_mode_start=? WHERE chat_id=?",
                        (text, chat_id_sec)
                    )
                    await safe_send(context.bot, user_id, f"✅ تم تعيين وقت البداية إلى {text}")
            else:
                await safe_send(context.bot, user_id, "❌ الصيغة غير صالحة (HH:MM)")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_NIGHT_END:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            if re.match(r'^\d{2}:\d{2}$', text):
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec:
                    await DB.execute(
                        "UPDATE group_security SET night_mode_end=? WHERE chat_id=?",
                        (text, chat_id_sec)
                    )
                    await safe_send(context.bot, user_id, f"✅ تم تعيين وقت النهاية إلى {text}")
            else:
                await safe_send(context.bot, user_id, "❌ الصيغة غير صالحة (HH:MM)")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PENALTY_DEFAULT_DURATION:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                dur_minutes = int(text)
                if dur_minutes < 0:
                    await safe_send(context.bot, user_id, "❌ المدة غير صالحة")
                    StateManager.clear(user_id)
                    return
                chat_id_pen = context.user_data.get('penalty_chat')
                p_type = context.user_data.get('penalty_type')
                if chat_id_pen and p_type:
                    duration_seconds = dur_minutes * 60 if dur_minutes > 0 else 0
                    # ✅ استعلامات ثابتة بدلاً من f-string
                    if p_type == 'mute':
                        await DB.execute("UPDATE group_security SET mute_default_duration=? WHERE chat_id=?", (duration_seconds, chat_id_pen))
                    elif p_type == 'ban':
                        await DB.execute("UPDATE group_security SET ban_default_duration=? WHERE chat_id=?", (duration_seconds, chat_id_pen))
                    elif p_type == 'restrict':
                        await DB.execute("UPDATE group_security SET restrict_default_duration=? WHERE chat_id=?", (duration_seconds, chat_id_pen))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين {p_type} إلى {dur_minutes} دقيقة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PENALTY_DURATION:
            if _is_command_cancel(text):
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "❌ تم الإلغاء.")
                return
            try:
                dur_minutes = int(text)
                if dur_minutes < 0 or dur_minutes > 1440:
                    await safe_send(context.bot, user_id, "❌ المدة غير صالحة (0-1440 دقيقة)")
                    StateManager.clear(user_id)
                    return
                chat_id_pen = context.user_data.get('penalty_chat')
                v_type = context.user_data.get('penalty_vtype')
                p_type = context.user_data.get('penalty_ptype')
                if chat_id_pen and v_type and p_type:
                    duration_seconds = dur_minutes * 60 if dur_minutes > 0 else 0
                    await DB.set_violation_penalty(chat_id_pen, v_type, p_type, duration_seconds)
                    await safe_send(context.bot, user_id, "✅ تم حفظ العقوبة بنجاح")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        # ============ افتراضي ============
        from handlers_command import CommandHandlers
        await CommandHandlers.start(update, context)

    @staticmethod
    async def handle_group(update, context):
        """معالجة الرسائل في المجموعات"""
        if not update.message or not update.effective_user:
            return
        chat = update.effective_chat
        if not chat or chat.type not in ['group', 'supergroup']:
            return
        chat_id = chat.id
        text = update.message.text or ""
        
        # ✅ تحديد طول الرسالة
        if len(text) > MAX_MESSAGE_LENGTH:
            text = text[:MAX_MESSAGE_LENGTH]
        
        if update.effective_user.is_bot:
            return

        logger.info(f"🔍 handle_group: text={text[:30]}, replies_loaded={len(_REPLIES_FROM_FILE)}")

        # التحقق من القفل
        locked = await DB.fetchone("SELECT locked FROM chat_locks WHERE chat_id=?", (chat_id,))
        if locked and locked['locked'] == 1:
            if not await is_authorized_in_group(context.bot, chat_id, update.effective_user.id):
                try:
                    await update.message.delete()
                except Exception as e:
                    logger.warning(f"⚠️ فشل حذف رسالة في مجموعة مقفلة: {e}")
                return

        settings = await DB.get_security_settings(chat_id)
        perms = await check_bot_permissions(context.bot, chat_id)
        can_delete = perms.get('can_delete_messages', perms.get('can_act', False))

        # التحقق من صلاحيات المستخدم
        if await is_authorized_in_group(context.bot, chat_id, update.effective_user.id):
            # المشرفون يرون الردود التلقائية
            await MessageHandlers._process_auto_reply(update, context, chat_id, text)
            return

        # تطبيق قواعد الأمان على الأعضاء العاديين
        # 1. حذف الروابط
        if settings.get('delete_links', False) and TextUtils.contains_link(text):
            if can_delete:
                try:
                    await update.message.delete()
                except Exception as e:
                    logger.warning(f"⚠️ فشل حذف رسالة تحتوي رابط: {e}")
            await apply_violation_penalty(context, chat_id, update.effective_user.id, 'links', "مخالفة روابط")
            return

        # 2. حذف المعرفات
        if settings.get('mentions', False) and TextUtils.contains_mention(text):
            if can_delete:
                try:
                    await update.message.delete()
                except Exception as e:
                    logger.warning(f"⚠️ فشل حذف رسالة تحتوي منشن: {e}")
            await apply_violation_penalty(context, chat_id, update.effective_user.id, 'mentions', "مخالفة منشن")
            return

        # 3. حذف الكلمات الممنوعة
        if settings.get('delete_banned_words', False):
            banned_words = await get_banned_words_cached(chat_id)
            if banned_words and any(word in text.lower() for word in banned_words):
                if can_delete:
                    try:
                        await update.message.delete()
                    except Exception as e:
                        logger.warning(f"⚠️ فشل حذف رسالة تحتوي كلمة ممنوعة: {e}")
                await apply_violation_penalty(context, chat_id, update.effective_user.id, 'banned_words', "كلمة محظورة")
                return

        # 4. الردود التلقائية
        await MessageHandlers._process_auto_reply(update, context, chat_id, text)

    @staticmethod
    async def _process_auto_reply(update, context, chat_id, text):
        """معالجة الردود التلقائية"""
        ars = await DB.get_auto_reply_settings(chat_id)
        if not ars.get('enabled', False):
            return False
        
        if not _REPLIES_FROM_FILE:
            reload_replies_from_file()
        
        reply = get_reply_from_file(text.lower().strip())
        if not reply:
            reply_data = await DB.get_auto_reply(text.lower().strip(), chat_id)
            if reply_data:
                reply = reply_data.get('reply')
        
        if reply:
            try:
                await update.message.reply_text(reply)
                await _increment_usage_async(chat_id, text.lower().strip())
                return True
            except Exception as e:
                logger.warning(f"⚠️ فشل إرسال رد تلقائي: {e}")
        
        return False

    @staticmethod
    async def handle_service(update, context):
        """معالجة رسائل الخدمة (الأعضاء الجدد، المغادرون)"""
        if not update.message or not update.effective_chat:
            return

        chat_id = update.effective_chat.id
        settings = await DB.get_security_settings(chat_id)

        # ✅ إصلاح: لا معاقبة على رسائل الانضمام/المغادرة
        is_join = bool(update.message.new_chat_members)
        is_leave = bool(update.message.left_chat_member)

        # حذف رسائل الخدمة (بدون معاقبة)
        if settings.get('delete_service', False) and not is_join and not is_leave:
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"⚠️ فشل حذف رسالة خدمة: {e}")

        # رسالة الترحيب
        if settings.get('welcome_enabled', False) and is_join:
            for member in update.message.new_chat_members:
                if member.id != context.bot.id:
                    welcome_text = settings.get('welcome_text', "مرحباً {user} 🤍")
                    text = welcome_text.format(user=member.full_name or "العضو")
                    try:
                        await context.bot.send_message(chat_id, text)
                    except Exception as e:
                        logger.warning(f"⚠️ فشل إرسال رسالة ترحيب: {e}")

        # رسالة الوداع
        if settings.get('goodbye_enabled', False) and is_leave:
            member = update.message.left_chat_member
            if member.id != context.bot.id:
                goodbye_text = settings.get('goodbye_text', "وداعاً {user} 👋")
                text = goodbye_text.format(user=member.full_name or "العضو")
                try:
                    await context.bot.send_message(chat_id, text)
                except Exception as e:
                    logger.warning(f"⚠️ فشل إرسال رسالة وداع: {e}")

    @staticmethod
    async def handle_join_request(update, context):
        """معالجة طلبات الانضمام"""
        join_request = update.chat_join_request
        chat_id = update.effective_chat.id
        settings = await DB.get_security_settings(chat_id)

        if settings.get('auto_approve_join', False):
            try:
                await join_request.approve()
                if settings.get('welcome_enabled', False):
                    await context.bot.send_message(
                        chat_id,
                        f"مرحباً {join_request.from_user.full_name} 🤍"
                    )
            except Exception as e:
                logger.warning(f"⚠️ فشل قبول طلب الانضمام: {e}")
            return

        if settings.get('auto_reject_join', False):
            try:
                await join_request.decline()
            except Exception as e:
                logger.warning(f"⚠️ فشل رفض طلب الانضمام: {e}")
