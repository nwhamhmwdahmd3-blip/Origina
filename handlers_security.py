#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_security.py - معالجات الأمان والمجموعات
تشمل: إعدادات الحماية، الكلمات المحظورة، الردود التلقائية، الإجراءات المتقدمة، العقوبات.
"""

import logging
from typing import Optional, Any, Dict, Union

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TimedOut

from config import CONFIG
from database import DB
from utils import (
    StateManager, UserState, KeyboardFactory,
    invalidate_banned_words_cache, _auto_reply_cache,
    is_authorized_in_group, get_text, TimeUtils, CB
)

logger = logging.getLogger(__name__)

# =====================================================================
# دوال مساعدة عامة (خاصة بهذا الملف)
# =====================================================================

async def _safe_answer(query, text: Optional[str] = None, show_alert: bool = False) -> bool:
    """إرسال رد آمن على استعلام (مع معالجة الأخطاء)."""
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


async def _safe_edit_message_text(query, text: str, reply_markup=None, parse_mode=None) -> bool:
    """تعديل رسالة بأمان مع تجاهل أخطاء 'not modified'."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except BadRequest as e:
        if "not modified" in str(e).lower():
            return True
        logger.debug(f"Edit message failed: {e}")
        return False
    except Exception as e:
        logger.warning(f"⚠️ فشل edit_message_text: {e}")
        return False


def _mask_id(id_value: Any, prefix: int = 3, suffix: int = 2) -> str:
    """إخفاء جزء من المعرف للخصوصية (تُستخدم عند عرض سجلات)."""
    if id_value is None:
        return "***"
    s = str(id_value)
    if len(s) <= 5:
        return "***"
    return s[:prefix] + "***" + s[-suffix:] if len(s) > prefix + suffix else s[:prefix] + "***"


def _safe_parse_int(value: str, default: Optional[int] = None) -> Optional[int]:
    """تحويل نص إلى رقم صحيح بأمان."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _escape_markdown(text: str) -> str:
    """تهريب أحرف ماركداون الخاصة."""
    if not text:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


async def _handle_error(query, error_type: str = 'default', lang: str = 'ar') -> None:
    """إرسال رسالة خطأ موحدة."""
    messages = {
        'ar': {
            'timeout': "⏰ انتهت المهلة، حاول مرة أخرى",
            'permission': "🔒 لا تملك الصلاحية",
            'not_found': "📭 غير موجود",
            'expired': "⏰ انتهت الجلسة، ابدأ من جديد",
            'old_message': "⚠️ هذه الرسالة قديمة، استخدم الأزرار الحديثة",
            'rate_limit': "⏳ يرجى الانتظار قليلاً قبل المحاولة مرة أخرى",
            'default': "❌ حدث خطأ غير متوقع، حاول مرة أخرى"
        },
        'en': {
            'default': "❌ Unexpected error, try again"
        }
    }
    msg = messages.get(lang, messages['ar']).get(error_type, messages['ar']['default'])
    await _safe_answer(query, msg, show_alert=True)


async def _verify_group_authorization(bot, chat_id: int, user_id: int) -> bool:
    """التحقق من صلاحية المستخدم في المجموعة."""
    try:
        return await is_authorized_in_group(bot, chat_id, user_id)
    except Exception:
        return False


# =====================================================================
# دوال مساعدة لبناء لوحات مفاتيح متكررة
# =====================================================================

def _build_antiflood_kb(chat_id: int, settings: Dict[str, Any]) -> InlineKeyboardMarkup:
    """بناء لوحة إعدادات الفيضان."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"الرسائل: {settings.get('antiflood_messages', 5)}",
                              callback_data=f"sec_antiflood_messages:{chat_id}")],
        [InlineKeyboardButton(f"الثواني: {settings.get('antiflood_seconds', 10)}",
                              callback_data=f"sec_antiflood_seconds:{chat_id}")],
        [InlineKeyboardButton(f"العقوبة: {settings.get('antiflood_penalty', 'mute')}",
                              callback_data=f"sec_antiflood_penalty:{chat_id}")],
        [InlineKeyboardButton("🔙", callback_data=f"sec_close:{chat_id}")]
    ])


def _build_night_kb(chat_id: int, settings: Dict[str, Any]) -> InlineKeyboardMarkup:
    """بناء لوحة الوضع الليلي."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"البداية: {settings.get('night_mode_start', '23:00')}",
                              callback_data=f"sec_night_start:{chat_id}")],
        [InlineKeyboardButton(f"النهاية: {settings.get('night_mode_end', '06:00')}",
                              callback_data=f"sec_night_end:{chat_id}")],
        [InlineKeyboardButton(f"الإجراء: {settings.get('night_mode_action', 'mute')}",
                              callback_data=f"sec_night_action:{chat_id}")],
        [InlineKeyboardButton("🔙", callback_data=f"sec_close:{chat_id}")]
    ])


def _build_penalty_durations_kb(chat_id: int, settings: Dict[str, Any]) -> InlineKeyboardMarkup:
    """بناء لوحة مدد العقوبات."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"كتم: {settings.get('mute_default_duration', 3600)//60}د",
                              callback_data=f"sec_penalty_mute:{chat_id}")],
        [InlineKeyboardButton(f"حظر: {settings.get('ban_default_duration', 0)//60}د",
                              callback_data=f"sec_penalty_ban:{chat_id}")],
        [InlineKeyboardButton(f"تقييد: {settings.get('restrict_default_duration', 1800)//60}د",
                              callback_data=f"sec_penalty_restrict:{chat_id}")],
        [InlineKeyboardButton("🔙", callback_data=f"sec_close:{chat_id}")]
    ])


# =====================================================================
# فئة معالجات الأمان
# =====================================================================

class SecurityHandlers:

    # =================================================================
    # معالجة عامة للبادئات المختلفة
    # =================================================================

    @staticmethod
    async def handle_security(update, context, query, user_id, lang):
        """معالجة أزرار sec_ (إعدادات الأمان) العامة."""
        data = query.data
        parts = data.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            chat_id = _safe_parse_int(parts[1])
            if chat_id is None:
                await _handle_error(query, 'permission', lang)
                return
        else:
            chat_id = context.user_data.get('security_chat_id')
        if chat_id is None:
            return

        action = parts[0].replace("sec_", "")
        if not await _verify_group_authorization(context.bot, chat_id, user_id):
            await _handle_error(query, 'permission', lang)
            return

        # تفويض إلى معالجات فرعية حسب الفئة
        if action.startswith("auto_reply"):
            await SecurityHandlers._handle_auto_reply_menu(update, context, query, user_id, chat_id, lang, action)
            return
        if action.startswith("adv_act"):
            await SecurityHandlers._handle_advanced_actions_menu(update, context, query, user_id, chat_id, lang, action)
            return
        if action.startswith("penalty"):
            await SecurityHandlers._handle_penalty_menu(update, context, query, user_id, chat_id, lang, action)
            return
        if action == "act_log":
            await SecurityHandlers._handle_act_log(update, context, query, user_id, chat_id, lang)
            return
        if action in ("banned", "banned_words"):
            await SecurityHandlers.handle_banned_words_direct(update, context, query, user_id, chat_id, lang)
            return

        # معالجة التبديلات
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
            "toggle_banned_words": "UPDATE group_security SET delete_banned_words = 1 - delete_banned_words WHERE chat_id=?",
            "approve_join": "UPDATE group_security SET auto_approve_join = 1 - auto_approve_join WHERE chat_id=?",
            "reject_join": "UPDATE group_security SET auto_reject_join = 1 - auto_reject_join WHERE chat_id=?",
            "nsfw": "UPDATE group_security SET nsfw_filter = 1 - nsfw_filter WHERE chat_id=?",
            "del_pen": "UPDATE group_security SET delete_penalty_messages = 1 - delete_penalty_messages WHERE chat_id=?",
            "warn": "UPDATE group_security SET warn_enabled = 1 - warn_enabled WHERE chat_id=?"
        }
        if action in toggle_queries:
            await SecurityHandlers._handle_toggle(update, context, query, user_id, chat_id, lang, action, toggle_queries[action])
            return

        # معالجة القوائم الفرعية
        if action == "violation_penalties":
            await SecurityHandlers._show_violation_penalties(update, context, query, user_id, chat_id, lang)
            return
        if action == "set_violation_strikes":
            StateManager.set(user_id, UserState.WAIT_VIOLATION_STRIKES)
            context.user_data['sec_chat'] = chat_id
            await _safe_edit_message_text(query, "⚠️ أرسل عدد المخالفات المسموح بها:")
            return
        if action == "set_violation_duration":
            StateManager.set(user_id, UserState.WAIT_VIOLATION_DURATION)
            context.user_data['sec_chat'] = chat_id
            await _safe_edit_message_text(query, "⏳ أرسل مدة العقوبة بالدقائق:")
            return
        if action in ("penalty_mute", "penalty_ban", "penalty_restrict"):
            penalty_type = action.replace("penalty_", "")
            await SecurityHandlers.show_duration_menu(update, context, query, user_id, lang, penalty_type, chat_id)
            return
        if action == "enable_all":
            await SecurityHandlers._enable_all(update, context, query, user_id, chat_id, lang)
            return
        if action == "disable_all":
            await SecurityHandlers._disable_all(update, context, query, user_id, chat_id, lang)
            return

        # إعدادات تتطلب إدخال نصي
        text_input_mapping = {
            "maxlen": (UserState.WAIT_MAX_LEN, "📏 أرسل الحد الأقصى:"),
            "warn_count": (UserState.WAIT_WARN_COUNT, "📝 أرسل العدد (1-10):"),
            "welcome_text": (UserState.WAIT_WELCOME_TEXT, "👋 أرسل نص الترحيب:"),
            "goodbye_text": (UserState.WAIT_GOODBYE_TEXT, "👋 أرسل نص الوداع:"),
            "slow_mode_seconds": (UserState.WAIT_SLOW_MODE_SECONDS, "⏱️ أرسل الثواني (0-3600):"),
            "antiflood_messages": (UserState.WAIT_ANTIFLOOD_MESSAGES, "📝 أرسل عدد الرسائل:"),
            "antiflood_seconds": (UserState.WAIT_ANTIFLOOD_SECONDS, "⏱️ أرسل الفترة:"),
            "night_start": (UserState.WAIT_NIGHT_START, "🌙 وقت البداية:"),
            "night_end": (UserState.WAIT_NIGHT_END, "🌙 وقت النهاية:"),
        }
        if action in text_input_mapping:
            state, prompt = text_input_mapping[action]
            StateManager.set(user_id, state)
            context.user_data['sec_chat'] = chat_id
            await _safe_edit_message_text(query, prompt)
            return

        # قوائم الإعدادات الفرعية
        if action == "antiflood_settings":
            settings = await DB.get_security_settings(chat_id)
            kb = _build_antiflood_kb(chat_id, settings)
            await _safe_edit_message_text(query, "🌊 **إعدادات الفيضان**", reply_markup=kb)
            return
        if action == "night_settings":
            settings = await DB.get_security_settings(chat_id)
            kb = _build_night_kb(chat_id, settings)
            await _safe_edit_message_text(query, "🌙 **الوضع الليلي**", reply_markup=kb)
            return
        if action == "penalty_durations":
            settings = await DB.get_security_settings(chat_id)
            kb = _build_penalty_durations_kb(chat_id, settings)
            await _safe_edit_message_text(query, "⏳ **مدد العقوبات**", reply_markup=kb)
            return

        # تغيير ديناميكي لقيمة (مثل عقوبة الفيضان، إجراء الليل)
        if action == "antiflood_penalty":
            await SecurityHandlers._cycle_antiflood_penalty(update, context, query, user_id, chat_id, lang)
            return
        if action == "night_action":
            await SecurityHandlers._cycle_night_action(update, context, query, user_id, chat_id, lang)
            return

        # إغلاق
        if action == "close":
            try:
                await query.message.delete()
            except Exception:
                pass
            return

        await _safe_answer(query)

    # =================================================================
    # دوال مساعدة فرعية لـ handle_security
    # =================================================================

    @staticmethod
    async def _handle_toggle(update, context, query, user_id, chat_id, lang, action, sql):
        """تنفيذ تبديل حالة إعداد معين."""
        await DB.execute(sql, (chat_id,))
        if action == "toggle_banned_words":
            invalidate_banned_words_cache()
        settings = await DB.get_security_settings(chat_id)
        kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
        await _safe_edit_message_text(query, KeyboardFactory._format_security_text(settings), reply_markup=kb)

    @staticmethod
    async def _enable_all(update, context, query, user_id, chat_id, lang):
        """تفعيل جميع إعدادات الأمان."""
        await DB.execute("""UPDATE group_security SET delete_links=1, mentions=1, slow_mode=1,
            delete_videos=1, delete_audio=1, delete_animation=1, delete_service=1,
            delete_documents=1, delete_stickers=1, delete_forwarded=1, delete_polls=1,
            delete_games=1, delete_voice=1, delete_video_note=1, welcome_enabled=1,
            goodbye_enabled=1, antiflood_enabled=1, night_mode_enabled=1,
            delete_banned_words=1, auto_approve_join=1, auto_reject_join=1,
            nsfw_filter=1, delete_penalty_messages=1, warn_enabled=1 WHERE chat_id=?""", (chat_id,))
        invalidate_banned_words_cache()
        await _safe_answer(query, "✅ تم تفعيل الكل", show_alert=True)
        settings = await DB.get_security_settings(chat_id)
        kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
        await _safe_edit_message_text(query, KeyboardFactory._format_security_text(settings), reply_markup=kb)

    @staticmethod
    async def _disable_all(update, context, query, user_id, chat_id, lang):
        """تعطيل جميع إعدادات الأمان."""
        await DB.execute("""UPDATE group_security SET delete_links=0, mentions=0, slow_mode=0,
            delete_videos=0, delete_audio=0, delete_animation=0, delete_service=0,
            delete_documents=0, delete_stickers=0, delete_forwarded=0, delete_polls=0,
            delete_games=0, delete_voice=0, delete_video_note=0, welcome_enabled=0,
            goodbye_enabled=0, antiflood_enabled=0, night_mode_enabled=0,
            delete_banned_words=0, auto_approve_join=0, auto_reject_join=0,
            nsfw_filter=0, delete_penalty_messages=0, warn_enabled=0 WHERE chat_id=?""", (chat_id,))
        invalidate_banned_words_cache()
        await _safe_answer(query, "✅ تم تعطيل الكل", show_alert=True)
        settings = await DB.get_security_settings(chat_id)
        kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
        await _safe_edit_message_text(query, KeyboardFactory._format_security_text(settings), reply_markup=kb)

    @staticmethod
    async def _show_violation_penalties(update, context, query, user_id, chat_id, lang):
        """عرض إعدادات عقوبات المخالفات."""
        settings = await DB.get_security_settings(chat_id)
        strikes = settings.get('violation_strikes', 3)
        duration = settings.get('violation_duration', 60)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⚠️ عدد المخالفات: {strikes}",
                                  callback_data=f"sec_set_violation_strikes:{chat_id}")],
            [InlineKeyboardButton(f"⏳ مدة العقوبة: {duration} دقيقة",
                                  callback_data=f"sec_set_violation_duration:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"sec_close:{chat_id}")]
        ])
        await _safe_edit_message_text(query, "⚖️ **عقوبات المخالفات**", reply_markup=kb)

    @staticmethod
    async def _cycle_antiflood_penalty(update, context, query, user_id, chat_id, lang):
        """التنقل بين عقوبات الفيضان (mute, ban, restrict)."""
        settings = await DB.get_security_settings(chat_id)
        current = settings.get('antiflood_penalty', 'mute')
        penalties = ['mute', 'ban', 'restrict']
        next_pen = penalties[(penalties.index(current) + 1) % len(penalties)]
        await DB.execute("UPDATE group_security SET antiflood_penalty=? WHERE chat_id=?", (next_pen, chat_id))
        settings = await DB.get_security_settings(chat_id)
        kb = _build_antiflood_kb(chat_id, settings)
        await _safe_edit_message_text(query, "🌊 **إعدادات الفيضان**", reply_markup=kb)
        await _safe_answer(query, f"✅ العقوبة: {next_pen}", show_alert=True)

    @staticmethod
    async def _cycle_night_action(update, context, query, user_id, chat_id, lang):
        """التنقل بين إجراءات الوضع الليلي."""
        settings = await DB.get_security_settings(chat_id)
        current = settings.get('night_mode_action', 'mute')
        actions = ['mute', 'ban', 'restrict', 'nothing']
        next_action = actions[(actions.index(current) + 1) % len(actions)]
        await DB.execute("UPDATE group_security SET night_mode_action=? WHERE chat_id=?", (next_action, chat_id))
        settings = await DB.get_security_settings(chat_id)
        kb = _build_night_kb(chat_id, settings)
        await _safe_edit_message_text(query, "🌙 **الوضع الليلي**", reply_markup=kb)
        await _safe_answer(query, f"✅ الإجراء: {next_action}", show_alert=True)

    @staticmethod
    async def _handle_auto_reply_menu(update, context, query, user_id, chat_id, lang, action):
        """توجيه إلى قائمة الردود التلقائية أو معالجتها."""
        if action == "auto_reply_menu":
            kb = KeyboardFactory.build("auto_reply_manage", chat_id=chat_id, lang=lang)
            await _safe_edit_message_text(query, "📝 **إدارة الردود**", reply_markup=kb)
            return
        # يمكن إضافة معالجات أخرى إذا لزم الأمر
        await _safe_answer(query)

    @staticmethod
    async def _handle_advanced_actions_menu(update, context, query, user_id, chat_id, lang, action):
        """توجيه إلى قائمة الإجراءات المتقدمة."""
        if action == "adv_act":
            kb = KeyboardFactory.build("advanced_actions", chat_id=chat_id, lang=lang)
            await _safe_edit_message_text(query, "🛠️ **إجراءات متقدمة**", reply_markup=kb)
            return
        await _safe_answer(query)

    @staticmethod
    async def _handle_penalty_menu(update, context, query, user_id, chat_id, lang, action):
        """توجيه إلى قائمة العقوبات."""
        if action == "penalty":
            kb = KeyboardFactory.build("penalty", chat_id=chat_id, lang=lang)
            await _safe_edit_message_text(query, "⚖️ **العقوبات**", reply_markup=kb)
            return
        await _safe_answer(query)

    @staticmethod
    async def _handle_act_log(update, context, query, user_id, chat_id, lang):
        """عرض سجل الإجراءات."""
        logs = await DB.get_admin_logs(chat_id, 20)
        text = "📜 **السجل**\n\n" + "\n".join(f"• {log['action']}" for log in logs) if logs else "📭 لا توجد"
        await _safe_edit_message_text(query, text)

    # =================================================================
    # معالجة الكلمات المحظورة (ban_)
    # =================================================================

    @staticmethod
    async def handle_banned_words(update, context, query, user_id):
        """معالجة أزرار ban_ (إضافة/عرض/حذف الكلمات المحظورة)."""
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("ban_", "")
        chat_id = _safe_parse_int(parts[1])
        if chat_id is None:
            return
        lang = await DB.get_user_language(user_id) or 'ar'
        if not await _verify_group_authorization(context.bot, chat_id, user_id):
            await _handle_error(query, 'permission', lang)
            return
        if action == "add":
            StateManager.set(user_id, UserState.WAIT_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            await _safe_edit_message_text(query, "📝 أرسل الكلمة:")
        elif action == "list":
            try:
                words = await DB.get_banned_words(chat_id)
                if words:
                    if isinstance(words[0], str):
                        word_list = words
                    else:
                        word_list = [w.get('word', str(w)) for w in words]
                    text = f"🚫 **الكلمات المحظورة** ({len(word_list)})\n\n"
                    for i, w in enumerate(word_list[:50], 1):
                        text += f"{i}. {w}\n"
                else:
                    text = "📭 لا توجد كلمات محظورة"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"sec_banned:{chat_id}")]])
                await _safe_edit_message_text(query, text[:4000], reply_markup=kb)
            except Exception as e:
                logger.error(f"❌ خطأ: {e}")
                await _handle_error(query, 'default', lang)
        elif action == "rem":
            StateManager.set(user_id, UserState.WAIT_REM_GROUP_BAN)
            context.user_data['ban_chat'] = chat_id
            await _safe_edit_message_text(query, "🗑️ أرسل الكلمة:")

    @staticmethod
    async def handle_banned_words_direct(update, context, query, user_id, chat_id=None, lang=None):
        """عرض قائمة الكلمات المحظورة مباشرة (من قائمة الأمان أو المطور)."""
        if lang is None:
            lang = await DB.get_user_language(user_id) or 'ar'
        if chat_id is None:
            data = query.data
            parts = data.split(":")
            chat_id = _safe_parse_int(parts[1]) if len(parts) > 1 else -1
        if chat_id != -1:
            if not await _verify_group_authorization(context.bot, chat_id, user_id):
                await _handle_error(query, 'permission', lang)
                return
        else:
            if not CONFIG.is_developer(user_id):
                await _handle_error(query, 'permission', lang)
                return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕", callback_data=f"ban_add:{chat_id}"),
             InlineKeyboardButton("📋", callback_data=f"ban_list:{chat_id}")],
            [InlineKeyboardButton("🗑️", callback_data=f"ban_rem:{chat_id}")],
            [InlineKeyboardButton("🔙", callback_data=CB.ADMIN if chat_id == -1 else f"sec_close:{chat_id}")]
        ])
        await _safe_edit_message_text(query, "🚫 **الكلمات المحظورة**", reply_markup=kb)

    # =================================================================
    # معالجة الردود التلقائية (auto_reply_)
    # =================================================================

    @staticmethod
    async def handle_auto_reply(update, context, query, user_id, lang=None):
        """معالجة أزرار auto_reply_ (إدارة الردود التلقائية)."""
        if not lang:
            lang = await DB.get_user_language(user_id) or 'ar'
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("auto_reply_", "")
        chat_id = _safe_parse_int(parts[1])
        if chat_id is None:
            return
        if not await _verify_group_authorization(context.bot, chat_id, user_id):
            await _handle_error(query, 'permission', lang)
            return
        settings = await DB.get_auto_reply_settings(chat_id)
        if action == "toggle":
            new_val = not settings.get('enabled', False)
            await DB.update_auto_reply_settings(chat_id, enabled=new_val)
            _auto_reply_cache.invalidate()
            await _safe_answer(query, f"{'✅ مفعل' if new_val else '❌ معطل'}", show_alert=True)
            kb = KeyboardFactory.build("auto_reply_manage", chat_id=chat_id, lang=lang)
            await _safe_edit_message_text(query, "📝 **إدارة الردود**", reply_markup=kb)
            return
        if action == "admins":
            new_val = not settings.get('only_admins', False)
            await DB.update_auto_reply_settings(chat_id, only_admins=new_val)
            await _safe_answer(query, f"{'✅ مشرفون فقط' if new_val else '👥 الجميع'}", show_alert=True)
            kb = KeyboardFactory.build("auto_reply_manage", chat_id=chat_id, lang=lang)
            await _safe_edit_message_text(query, "📝 **إدارة الردود**", reply_markup=kb)
            return
        if action == "reset":
            await DB.reset_auto_replies(chat_id)
            _auto_reply_cache.invalidate()
            await _safe_answer(query, "✅ تم", show_alert=True)
            kb = KeyboardFactory.build("auto_reply_manage", chat_id=chat_id, lang=lang)
            await _safe_edit_message_text(query, "📝 **إدارة الردود**", reply_markup=kb)
            return
        if action == "add":
            StateManager.set(user_id, UserState.WAIT_AUTO_KEY)
            context.user_data['auto_chat'] = chat_id
            await _safe_edit_message_text(query, "📝 أرسل الكلمة:")
            return
        if action == "del":
            StateManager.set(user_id, UserState.WAIT_AUTO_DEL)
            context.user_data['auto_chat'] = chat_id
            await _safe_edit_message_text(query, "🗑️ أرسل الكلمة:")
            return
        if action == "stats":
            rows = await DB.fetchall("SELECT keyword, usage_count FROM auto_replies WHERE chat_id=? LIMIT 10", (chat_id,))
            text = "📊 **الإحصائيات**\n\n" + "\n".join(f"• {r['keyword']}: {r['usage_count']}" for r in rows) if rows else "📭 لا يوجد"
            await _safe_edit_message_text(query, text)
            return
        if action == "list":
            rows = await DB.fetchall("SELECT keyword FROM auto_replies WHERE chat_id=? LIMIT 20", (chat_id,))
            text = "📋 **الردود**\n\n" + "\n".join(f"• {r['keyword']}" for r in rows) if rows else "📭 لا يوجد"
            await _safe_edit_message_text(query, text)
            return

    # =================================================================
    # معالجة الإجراءات المتقدمة (act_)
    # =================================================================

    @staticmethod
    async def handle_advanced_actions(update, context, query, user_id):
        """معالجة أزرار act_ (تنفيذ إجراءات متقدمة)."""
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[0].replace("act_", "")
        chat_id = _safe_parse_int(parts[1])
        if chat_id is None:
            return
        lang = await DB.get_user_language(user_id) or 'ar'
        if not await _verify_group_authorization(context.bot, chat_id, user_id):
            await _handle_error(query, 'permission', lang)
            return
        actions = {
            "ban": (UserState.WAIT_BAN, "🚫 معرف المستخدم:"),
            "mute": (UserState.WAIT_MUTE, "🔇 معرف المستخدم:"),
            "warn": (UserState.WAIT_WARN, "⚠️ معرف المستخدم:"),
            "kick": (UserState.WAIT_KICK, "👢 معرف المستخدم:"),
            "restrict": (UserState.WAIT_RESTRICT, "🔒 معرف المستخدم:"),
            "unban": (UserState.WAIT_UNBAN, "🔓 معرف المستخدم:"),
            "pin": (UserState.WAIT_PIN, "📌 معرف الرسالة:"),
        }
        if action in actions:
            state, text = actions[action]
            StateManager.set(user_id, state)
            context.user_data['adv_chat'] = chat_id
            await _safe_edit_message_text(query, text)

    # =================================================================
    # معالجة تغيير العقوبة التلقائية (pen_)
    # =================================================================

    @staticmethod
    async def handle_penalty(update, context, query, user_id):
        """تعيين نوع العقوبة التلقائية (mute/ban/restrict)."""
        data = query.data
        parts = data.split(":")
        if len(parts) < 2:
            return
        penalty = parts[0].replace("pen_", "")
        if penalty not in ("mute", "ban", "restrict"):
            # نوع غير معروف، تجاهل
            await _safe_answer(query, "❌ نوع عقوبة غير معروف", show_alert=True)
            return
        chat_id = _safe_parse_int(parts[1])
        if chat_id is None:
            return
        lang = await DB.get_user_language(user_id) or 'ar'
        if not await _verify_group_authorization(context.bot, chat_id, user_id):
            await _handle_error(query, 'permission', lang)
            return
        await DB.execute("UPDATE group_security SET auto_penalty=? WHERE chat_id=?", (penalty, chat_id))
        await _safe_edit_message_text(query, f"✅ {penalty}")

    # =================================================================
    # عرض إعدادات الأمان للمجموعة (من قائمة المجموعات)
    # =================================================================

    @staticmethod
    async def show_group_security(update, context, query, user_id, lang):
        """عرض لوحة إعدادات الأمان لمجموعة محددة."""
        chat_id = _safe_parse_int(query.data.split(":")[-1])
        if chat_id is None:
            return
        context.user_data['security_chat_id'] = chat_id
        if not await _verify_group_authorization(context.bot, chat_id, user_id):
            await _handle_error(query, 'permission', lang)
            return
        settings = await DB.get_security_settings(chat_id)
        kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
        await _safe_edit_message_text(query, KeyboardFactory._format_security_text(settings), reply_markup=kb)
        await _safe_answer(query)

    # =================================================================
    # قفل / فتح المجموعة
    # =================================================================

    @staticmethod
    async def lock_group(update, context, query, user_id, lang, chat_id):
        """قفل المجموعة (منع الرسائل)."""
        await DB.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?,1,?,?)",
                         (chat_id, TimeUtils.sql_iso(), user_id))
        await _safe_answer(query, "🔒 تم قفل المجموعة", show_alert=True)
        await _safe_edit_message_text(query, "🔒 تم قفل المجموعة!")

    @staticmethod
    async def unlock_group(update, context, query, user_id, lang, chat_id):
        """فتح المجموعة."""
        await DB.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await _safe_answer(query, "🔓 تم فتح المجموعة", show_alert=True)
        await _safe_edit_message_text(query, "🔓 تم فتح المجموعة!")

    # =================================================================
    # قوائم مدد العقوبات السريعة
    # =================================================================

    @staticmethod
    async def show_duration_menu(update, context, query, user_id, lang, penalty_type: str, chat_id: int):
        """عرض قائمة اختيار مدة العقوبة."""
        type_names = {
            'mute': 'الكتم',
            'ban': 'الحظر',
            'restrict': 'التقييد'
        }
        type_name = type_names.get(penalty_type, penalty_type)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🕐 ساعة", callback_data=f"set_dur:{penalty_type}:60:{chat_id}"),
             InlineKeyboardButton("📅 يوم", callback_data=f"set_dur:{penalty_type}:1440:{chat_id}")],
            [InlineKeyboardButton("🗓️ شهر", callback_data=f"set_dur:{penalty_type}:43200:{chat_id}"),
             InlineKeyboardButton("📆 سنة", callback_data=f"set_dur:{penalty_type}:525600:{chat_id}")],
            [InlineKeyboardButton("♾️ دائم", callback_data=f"set_dur:{penalty_type}:0:{chat_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"sec_penalty_durations:{chat_id}")]
        ])
        await _safe_edit_message_text(query, f"⏳ اختر مدة {type_name}:", reply_markup=kb)
        await _safe_answer(query)

    @staticmethod
    async def set_penalty_duration(update, context, query, user_id, lang, penalty_type: str, minutes: int, chat_id: int):
        """تعيين مدة افتراضية لعقوبة معينة."""
        column_map = {
            'mute': 'mute_default_duration',
            'ban': 'ban_default_duration',
            'restrict': 'restrict_default_duration'
        }
        column = column_map.get(penalty_type)
        if not column:
            await _safe_answer(query, "❌ نوع غير معروف", show_alert=True)
            return
        seconds = minutes * 60
        await DB.execute(f"UPDATE group_security SET {column}=? WHERE chat_id=?", (seconds, chat_id))
        duration_text = "دائم" if minutes == 0 else f"{minutes} دقيقة"
        await _safe_answer(query, f"✅ تم تعيين مدة {penalty_type} إلى {duration_text}", show_alert=True)
        settings = await DB.get_security_settings(chat_id)
        kb = _build_penalty_durations_kb(chat_id, settings)
        await _safe_edit_message_text(query, "⏳ **مدد العقوبات**", reply_markup=kb)
