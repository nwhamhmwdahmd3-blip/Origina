#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_command.py - معالجات الأوامر (CommandHandlers) - النسخة النهائية الكاملة
===================================================================================
جميع الأوامر النصية للبوت مع دعم المشرفين المخفيين وإصلاح جميع المشاكل.
+ الأوامر الإضافية: /admin /broadcast /set_force /set_update_ch /set_log_ch
+ /add_admin /remove_admin /export_replies /import_replies /backup /restore
+ /auto_publish /auto_recycle /channels /posts /mood
"""

import asyncio
import logging
from typing import Optional
from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest, TimedOut

from config import CONFIG, PATHS
from database import DB
from utils import (
    TimeUtils, TextUtils, safe_send, is_authorized_in_group,
    check_bot_permissions, invalidate_auth_cache, apply_penalty,
    RATE_LIMITER, METRICS, get_text, StateManager, UserState,
    KeyboardFactory, TranslationManager, CB,
    export_auto_replies, import_auto_replies,
)

logger = logging.getLogger(__name__)


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


class CommandHandlers:
    """جميع معالجات الأوامر"""

    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /start - القائمة الرئيسية"""
        user_id = update.effective_user.id
        username = update.effective_user.username or ""
        first_name = update.effective_user.first_name or ""
        await DB.register_user(user_id, username, first_name)

        # معالجة الإحالات
        args = context.args or []
        if args and args[0].startswith('ref_'):
            ref_code = args[0][4:]
            referrer = await DB.get_user_by_referral_code(ref_code)
            if referrer and referrer != user_id and not await DB.is_user_banned(referrer):
                existing = await DB.fetchone("SELECT 1 FROM referrals WHERE referred_id=?", (user_id,))
                if not existing:
                    if await DB.add_referral(referrer, user_id):
                        reward = await DB.get_referral_stats(referrer)
                        try:
                            await context.bot.send_message(
                                referrer,
                                f"🎁 تمت إحالة `{_mask_id(user_id)}`. لديك {reward['available']} يوم متاح للصرف."
                            )
                        except Exception as e:
                            logger.warning(f"⚠️ فشل إرسال إشعار الإحالة: {e}")

        # التحقق من الاشتراك الإجباري
        force_ch = await DB.get_force_subscribe_channel()
        if force_ch and user_id != CONFIG.PRIMARY_OWNER_ID:
            try:
                if force_ch.lstrip('-').isdigit():
                    chat = await context.bot.get_chat(int(force_ch))
                else:
                    chat = await context.bot.get_chat(f"@{force_ch}")
                member = await context.bot.get_chat_member(chat.id, user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    invite_link = None
                    try:
                        invite_link = await context.bot.export_chat_invite_link(chat.id)
                    except Exception:
                        pass

                    if invite_link:
                        kb = InlineKeyboardMarkup([[
                            InlineKeyboardButton("📢 اشترك", url=invite_link),
                            InlineKeyboardButton("✅ تحقق", callback_data=CB.CHECK_SUB)
                        ]])
                    else:
                        kb = InlineKeyboardMarkup([[
                            InlineKeyboardButton("✅ تحقق", callback_data=CB.CHECK_SUB)
                        ]])
                    await safe_send(context.bot, user_id, "⚠️ اشترك في القناة أولاً", reply_markup=kb)
                    return
            except Exception as e:
                logger.error(f"❌ خطأ في التحقق من الاشتراك الإجباري: {e}")

        # جمع بيانات المستخدم
        lang = await DB.get_user_language(user_id) or 'ar'
        active = await DB.get_active_channel(user_id)
        cnt = 0
        ch_display = "لا توجد قنوات"
        if active:
            cnt = await DB.get_unpublished_posts_count(user_id, active)
            ch_info = await DB.get_channel_info(user_id, active)
            if ch_info:
                ch_display = ch_info['channel_name']

        groups = len(await DB.get_user_groups(user_id))
        has_sub = await DB.has_active_subscription(user_id)
        sub_text = "✅ مفعل" if has_sub else "❌ غير مفعل"
        auto = await DB.get_auto_publish_status(user_id)
        auto_text = "مفعل" if auto else "معطل"
        recycle = await DB.get_auto_recycle_status(user_id)
        recycle_text = "مفعل" if recycle else "معطل"

        # بناء لوحة المفاتيح
        kb_rows = KeyboardFactory.get_menu("main_menu", lang)
        keyboard = []

        for row in kb_rows:
            btn_row = []
            for item in row:
                if item == "admin_panel_btn":
                    if CONFIG.is_developer(user_id):
                        text_btn = KeyboardFactory.get_text("admin_panel_btn", lang)
                        btn_row.append(InlineKeyboardButton(text_btn, callback_data=CB.ADMIN))
                else:
                    text_btn = KeyboardFactory.get_text(item, lang)
                    if item.endswith("_url"):
                        url = f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup"
                        btn_row.append(InlineKeyboardButton(text_btn, url=url))
                    else:
                        btn_row.append(InlineKeyboardButton(text_btn, callback_data=item))
            if btn_row:
                keyboard.append(btn_row)

        if CONFIG.is_developer(user_id):
            admin_text = KeyboardFactory.get_text("admin_panel_btn", lang)
            if not any(btn.callback_data == CB.ADMIN for row in keyboard for btn in row):
                keyboard.append([InlineKeyboardButton(admin_text, callback_data=CB.ADMIN)])

        kb = InlineKeyboardMarkup(keyboard)

        title = await get_text(lang, 'main_menu',
                               user_id=user_id, groups=groups,
                               sub=sub_text, channel=ch_display,
                               pending=cnt, auto=auto_text,
                               recycle=recycle_text,
                               bot_name=CONFIG.BOT_NAME)

        await safe_send(context.bot, user_id, title, reply_markup=kb)

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /help - المساعدة"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id) or 'ar'
        await safe_send(context.bot, user_id, await get_text(lang, 'help_text'))

    @staticmethod
    async def trial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /trial - تفعيل التجربة المجانية"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id) or 'ar'
        if await DB.has_used_trial(user_id):
            await safe_send(context.bot, user_id, await get_text(lang, 'trial_used'))
            return
        days = await DB.activate_trial(user_id)
        if days > 0:
            await safe_send(context.bot, user_id, await get_text(lang, 'trial_activated', days=days))
        else:
            await safe_send(context.bot, user_id, "❌ تعذر تفعيل التجربة")

    @staticmethod
    async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /subscribe - عرض الباقات"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id) or 'ar'
        kb = KeyboardFactory.build("plans", lang=lang)
        await safe_send(context.bot, user_id, await get_text(lang, 'plan_selector'), reply_markup=kb)

    @staticmethod
    async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /support - الدعم الفني"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id) or 'ar'
        kb = KeyboardFactory.build("support", lang=lang)
        await safe_send(context.bot, user_id, await get_text(lang, 'send_support_message'), reply_markup=kb)

    @staticmethod
    async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /developer - معلومات المطور"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id) or 'ar'
        text = await get_text(lang, 'developer_info',
                              owner_id=CONFIG.PRIMARY_OWNER_ID,
                              bot_name=CONFIG.BOT_NAME,
                              bot_username=CONFIG.BOT_USERNAME)
        await safe_send(context.bot, user_id, text)

    @staticmethod
    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /stats - إحصائيات البوت (للمطورين فقط)"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id) or 'ar'
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        stats = await DB.get_bot_stats()
        text = f"👥 المستخدمون: {stats.get('users',0)}\n"
        text += f"📡 القنوات: {stats.get('channels',0)}\n"
        text += f"👥 المجموعات: {stats.get('groups',0)}\n"
        text += f"📝 المنشورات: {stats.get('posts',0)}\n"
        text += f"✅ المنشورة: {stats.get('published',0)}\n"
        text += f"💎 الاشتراكات النشطة: {stats.get('active_subs',0)}\n"
        text += f"🎫 التذاكر المعلقة: {stats.get('tickets',0)}"
        await safe_send(context.bot, user_id, text)

    @staticmethod
    async def language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /language - تغيير اللغة"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id) or 'ar'
        available = TranslationManager.get_available_languages()
        buttons = []
        row = []
        for code, name in available.items():
            row.append(InlineKeyboardButton(name, callback_data=f"lang_{code}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        back_text = KeyboardFactory.get_text("back", lang)
        buttons.append([InlineKeyboardButton(back_text, callback_data=CB.BACK)])
        kb = InlineKeyboardMarkup(buttons)
        await safe_send(context.bot, user_id, f"🌐 اختر اللغة:\n\nالحالية: {lang}", reply_markup=kb)

    @staticmethod
    async def replies_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /replies - الردود التلقائية"""
        await safe_send(context.bot, update.effective_user.id, "📚 الردود التلقائية تعمل!")

    @staticmethod
    async def contests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /contests - المسابقات النشطة مع أزرار المشاركة"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id) or 'ar'
        contests = await DB.get_active_contests(10)
        if not contests:
            await safe_send(context.bot, user_id, "📭 لا توجد مسابقات نشطة")
            return

        text = "🏆 <b>المسابقات النشطة</b>\n\n"
        kb = []
        for c in contests:
            text += (
                f"• <b>{escape(c['title'])}</b>\n"
                f"  🎁 {escape(c['prize'])}\n"
                f"  📅 {escape(c['end_date'][:10])}\n"
                f"  👥 المشاركون: {c.get('participants', 0)}\n\n"
            )
            kb.append([
                InlineKeyboardButton(
                    f"✍️ المشاركة في {escape(c['title'])[:20]}",
                    callback_data=f"{CB.CONTEST_JOIN}:{c['id']}"
                )
            ])

        kb.append([
            InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)
        ])

        await safe_send(
            context.bot,
            user_id,
            text,
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode='HTML'
        )

    # ========== الأوامر الإضافية الجديدة ==========

    @staticmethod
    async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /mood - تحليل المشاعر"""
        user_id = update.effective_user.id
        args = context.args or []

        if not args:
            StateManager.set(user_id, UserState.WAIT_MOOD)
            await safe_send(context.bot, user_id, "📝 أرسل النص الذي تريد تحليل مشاعره:")
            return

        text = " ".join(args)
        from handlers_message import analyze_sentiment
        if analyze_sentiment is None:
            await safe_send(context.bot, user_id, "❌ خدمة تحليل المشاعر غير متاحة حالياً")
            return
        result = analyze_sentiment(text)

        response = (
            f"{result['emoji']} <b>تحليل المشاعر</b>\n\n"
            f"📝 النص: <code>{escape(text[:100])}</code>\n"
            f"🎯 النتيجة: <b>{escape(result['sentiment'])}</b>\n\n"
            f"😊 إيجابي: {result['positive_percent']:.0f}%\n"
            f"😔 سلبي: {result['negative_percent']:.0f}%\n"
            f"📊 الكلمات: {result['total_words']}"
        )

        await safe_send(context.bot, user_id, response, parse_mode='HTML')

    @staticmethod
    async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /admin - لوحة الأدمن"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id) or 'ar'
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("👑 لوحة الأدمن", callback_data=CB.ADMIN)
        ]])
        await safe_send(context.bot, user_id, "👑 <b>لوحة الأدمن</b>\n\nاضغط الزر أدناه:", reply_markup=kb, parse_mode='HTML')

    @staticmethod
    async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /broadcast - بدء البث الجماعي"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id) or 'ar'
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        StateManager.set(user_id, UserState.WAIT_BROADCAST)
        await safe_send(context.bot, user_id, "📨 أرسل الرسالة التي تريد بثها:")

    @staticmethod
    async def set_force(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /set_force - تعيين الاشتراك الإجباري"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            return
        StateManager.set(user_id, UserState.WAIT_FORCE)
        await safe_send(context.bot, user_id, "🔒 أرسل معرف القناة:")

    @staticmethod
    async def set_update_ch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /set_update_ch - تعيين قناة التحديثات"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            return
        StateManager.set(user_id, UserState.WAIT_UPDATE_CH)
        await safe_send(context.bot, user_id, "📢 أرسل معرف قناة التحديثات:")

    @staticmethod
    async def set_log_ch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /set_log_ch - تعيين قناة السجلات"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            return
        StateManager.set(user_id, UserState.WAIT_LOG_CH)
        await safe_send(context.bot, user_id, "📋 أرسل معرف قناة السجلات:")

    @staticmethod
    async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /add_admin - إضافة مشرف للبوت"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            return
        StateManager.set(user_id, UserState.WAIT_ADMIN_ADD)
        await safe_send(context.bot, user_id, "👑 أرسل معرف المشرف:")

    @staticmethod
    async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /remove_admin - إزالة مشرف من البوت"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            return
        StateManager.set(user_id, UserState.WAIT_ADMIN_REM)
        await safe_send(context.bot, user_id, "🗑️ أرسل معرف المشرف:")

    @staticmethod
    async def export_replies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /export_replies - تصدير الردود"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            return
        count = await export_auto_replies(-1)
        await safe_send(context.bot, user_id, f"✅ تم تصدير {count} رد")

    @staticmethod
    async def import_replies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /import_replies - استيراد الردود"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            return
        StateManager.set(user_id, UserState.WAIT_IMPORT_FILE)
        await safe_send(context.bot, user_id, "📤 أرسل ملف JSON:")

    @staticmethod
    async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /backup - نسخ احتياطي"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            return
        await safe_send(context.bot, user_id, "⏳ جارٍ النسخ الاحتياطي...")
        try:
            from utils import BackgroundTasks
            asyncio.create_task(BackgroundTasks._do_backup())
            await safe_send(context.bot, user_id, "✅ تم أخذ نسخة احتياطية")
        except Exception as e:
            logger.error(f"❌ فشل النسخ الاحتياطي: {e}")
            await safe_send(context.bot, user_id, f"❌ فشل النسخ الاحتياطي: {str(e)[:50]}")

    @staticmethod
    async def restore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /restore - عرض النسخ الاحتياطية"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            return
        backups = sorted(PATHS.BACKUPS.glob("backup_*.db"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not backups:
            await safe_send(context.bot, user_id, "📭 لا توجد نسخ")
            return
        text = "🔄 <b>النسخ المتاحة:</b>\n\n" + "\n".join(b.name for b in backups[:10])
        await safe_send(context.bot, user_id, text, parse_mode='HTML')

    @staticmethod
    async def auto_publish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /auto_publish - تبديل النشر التلقائي"""
        user_id = update.effective_user.id
        cur = await DB.get_auto_publish_status(user_id)
        await DB.set_auto_publish(user_id, not cur)
        await safe_send(context.bot, user_id, f"✅ النشر التلقائي: {'مفعل' if not cur else 'معطل'}")

    @staticmethod
    async def auto_recycle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /auto_recycle - تبديل التدوير التلقائي"""
        user_id = update.effective_user.id
        cur = await DB.get_auto_recycle_status(user_id)
        await DB.set_auto_recycle(user_id, not cur)
        await safe_send(context.bot, user_id, f"✅ التدوير التلقائي: {'مفعل' if not cur else 'معطل'}")

    @staticmethod
    async def channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /channels - عرض القنوات"""
        user_id = update.effective_user.id
        channels = await DB.get_user_channels(user_id)
        if not channels:
            await safe_send(context.bot, user_id, "📭 لا توجد قنوات")
            return
        text = "📡 <b>قنواتك:</b>\n\n"
        for ch in channels:
            text += f"• {escape(ch['channel_name'])} (<code>{ch['channel_id']}</code>)\n"
        await safe_send(context.bot, user_id, text, parse_mode='HTML')

    @staticmethod
    async def posts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /posts - عرض المنشورات"""
        user_id = update.effective_user.id
        active = await DB.get_active_channel(user_id)
        if not active:
            await safe_send(context.bot, user_id, "❌ لا توجد قناة نشطة")
            return
        posts = await DB.get_user_posts(user_id, active, 10)
        if not posts:
            await safe_send(context.bot, user_id, "📭 لا توجد منشورات")
            return
        text = "📋 <b>منشوراتك:</b>\n\n"
        for p in posts:
            text += f"• <code>{p['id']}</code>: {(escape(p['text'] or '')[:30])}\n"
        await safe_send(context.bot, user_id, text, parse_mode='HTML')

    # ========== أوامر المجموعات ==========

    @staticmethod
    async def security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /security - إعدادات الأمان للمجموعة"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id) or 'ar'
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        lang = await DB.get_user_language(user_id) or 'ar'
        context.user_data['security_chat_id'] = chat_id
        settings = await DB.get_security_settings(chat_id)
        text = KeyboardFactory._format_security_text(settings)
        kb = KeyboardFactory.build("security", chat_id=chat_id, lang=lang)
        await safe_send(context.bot, user_id, text, reply_markup=kb)

    @staticmethod
    async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /panel - لوحة تحكم المجموعة"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id) or 'ar'
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        lang = await DB.get_user_language(user_id) or 'ar'
        kb = KeyboardFactory.build("panel", chat_id=chat_id, lang=lang)
        await safe_send(context.bot, user_id, "📋 لوحة تحكم المجموعة", reply_markup=kb)

    @staticmethod
    async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /lock - قفل المجموعة"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        await DB.execute("INSERT OR REPLACE INTO chat_locks (chat_id, locked, locked_at, locked_by) VALUES (?,1,?,?)",
                         (chat_id, TimeUtils.sql_iso(), user_id))
        await safe_send(context.bot, user_id, "🔒 تم القفل")

    @staticmethod
    async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """الأمر /unlock - فتح المجموعة"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        await DB.execute("DELETE FROM chat_locks WHERE chat_id=?", (chat_id,))
        await safe_send(context.bot, user_id, "🔓 تم الفتح")

    @staticmethod
    async def register_hidden_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """تسجيل مالك مخفي"""
        user_id = update.effective_user.id
        if user_id != CONFIG.PRIMARY_OWNER_ID:
            lang = await DB.get_user_language(user_id) or 'ar'
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        if not context.args:
            await safe_send(context.bot, user_id, "📝 /register_hidden_owner <user_id>")
            return
        try:
            owner_id = int(context.args[0])
            if owner_id <= 0:
                raise ValueError
        except (ValueError, TypeError):
            await safe_send(context.bot, user_id, "⚠️ معرف غير صالح")
            return
        chat_id = update.effective_chat.id
        await DB.execute("INSERT OR IGNORE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,1)", (chat_id, owner_id))
        invalidate_auth_cache(chat_id, owner_id)
        await safe_send(context.bot, user_id, f"✅ تم تسجيل <code>{owner_id}</code> كمالك مخفي", parse_mode='HTML')

    @staticmethod
    async def remove_hidden_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """إزالة مالك مخفي"""
        user_id = update.effective_user.id
        if user_id != CONFIG.PRIMARY_OWNER_ID:
            return
        if not context.args:
            return
        try:
            owner_id = int(context.args[0])
        except (ValueError, TypeError):
            return
        chat_id = update.effective_chat.id
        await DB.execute("DELETE FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, owner_id))
        invalidate_auth_cache(chat_id, owner_id)
        await safe_send(context.bot, user_id, f"✅ تم إزالة <code>{owner_id}</code>", parse_mode='HTML')

    @staticmethod
    async def add_hidden_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """إضافة مشرف مخفي"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        is_owner = user_id == CONFIG.PRIMARY_OWNER_ID
        if not is_owner:
            row = await DB.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
            is_owner = row is not None
        if not is_owner:
            lang = await DB.get_user_language(user_id) or 'ar'
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        if not context.args:
            return
        try:
            admin_id = int(context.args[0])
            if admin_id <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return
        await DB.add_hidden_admin(chat_id, admin_id, user_id)
        invalidate_auth_cache(chat_id, admin_id)
        await safe_send(context.bot, user_id, f"✅ تم إضافة <code>{admin_id}</code> كمشرف مخفي", parse_mode='HTML')

    @staticmethod
    async def remove_hidden_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """إزالة مشرف مخفي"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        is_owner = user_id == CONFIG.PRIMARY_OWNER_ID
        if not is_owner:
            row = await DB.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
            is_owner = row is not None
        if not is_owner:
            return
        if not context.args:
            return
        try:
            admin_id = int(context.args[0])
        except (ValueError, TypeError):
            return
        await DB.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
        invalidate_auth_cache(chat_id, admin_id)
        await safe_send(context.bot, user_id, f"✅ تم إزالة <code>{admin_id}</code>", parse_mode='HTML')

    @staticmethod
    async def list_hidden_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """عرض المخفيين"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        is_owner = user_id == CONFIG.PRIMARY_OWNER_ID
        if not is_owner:
            row = await DB.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
            is_owner = row is not None
        if not is_owner:
            return
        owners = await DB.fetchall("SELECT owner_id FROM hidden_owner_groups WHERE chat_id=?", (chat_id,))
        admins = await DB.fetchall("SELECT admin_id FROM hidden_admins WHERE chat_id=?", (chat_id,))
        text = "👤 <b>المخفيون</b>\n"
        for o in owners:
            text += f"👑 <code>{o['owner_id']}</code>\n"
        for a in admins:
            text += f"🛡️ <code>{a['admin_id']}</code>\n"
        await safe_send(context.bot, user_id, text if owners or admins else "📭 لا يوجد", parse_mode='HTML')

    @staticmethod
    async def syncgroup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """مزامنة المجموعة مع البوت - مع دعم المشرفين المخفيين"""
        if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
            await safe_send(context.bot, update.effective_user.id, "❌ هذا الأمر للمجموعات فقط")
            return

        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "بدون اسم"
        user_id = update.effective_user.id

        logger.info(f"🔍 محاولة تسجيل المجموعة: chat_id={chat_id}, user_id={user_id}")

        try:
            bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
            if bot_member.status != 'administrator':
                await safe_send(
                    context.bot, user_id,
                    "❌ <b>البوت ليس مشرفاً في المجموعة!</b>\n\n"
                    "يجب ترقية البوت إلى مشرف أولاً:\n"
                    "1. افتح إعدادات المجموعة\n"
                    "2. اختر «المشرفون»\n"
                    "3. أضف البوت كمشرف\n"
                    "4. منحه صلاحية حذف الرسائل على الأقل",
                    parse_mode='HTML'
                )
                return
        except Exception as e:
            logger.error(f"❌ فشل التحقق من حالة البوت: {e}")
            await safe_send(context.bot, user_id, f"❌ فشل التحقق من حالة البوت: {escape(str(e)[:50])}")
            return

        try:
            all_admins = await context.bot.get_chat_administrators(chat_id)
            logger.info(f"🔍 عدد المشرفين: {len(all_admins)}")
        except Exception as e:
            logger.error(f"❌ فشل جلب المشرفين: {e}")
            await safe_send(context.bot, user_id, "❌ فشل جلب المشرفين")
            return

        creator_id = None
        for admin in all_admins:
            if admin.status == 'creator' and not admin.user.is_bot:
                creator_id = admin.user.id
                break

        is_admin = False
        real_user_id = user_id

        if update.message and update.message.sender_chat and update.message.sender_chat.id == chat_id:
            is_admin = True
            real_user_id = update.message.sender_chat.id
        else:
            for admin in all_admins:
                if admin.user.id == user_id:
                    is_admin = True
                    real_user_id = admin.user.id
                    break

        if not is_admin and hasattr(CONFIG, 'ANONYMOUS_ADMIN_ID') and user_id == CONFIG.ANONYMOUS_ADMIN_ID:
            is_admin = True
            real_user_id = user_id

        if not is_admin:
            await safe_send(context.bot, user_id, "❌ <b>أنت لست مشرفاً في هذه المجموعة!</b>", parse_mode='HTML')
            return

        try:
            await DB.register_group(chat_id, chat_name, creator_id or real_user_id, update.effective_chat.username)
            logger.info("✅ تم تسجيل المجموعة")
        except Exception as e:
            logger.error(f"❌ فشل تسجيل المجموعة: {e}")
            await safe_send(context.bot, user_id, "❌ فشل تسجيل المجموعة")
            return

        try:
            if creator_id:
                await DB.execute(
                    "INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,0)",
                    (chat_id, creator_id)
                )
                await DB.execute(
                    "INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?,?)",
                    (creator_id, chat_id)
                )
                invalidate_auth_cache(chat_id, creator_id)

            await DB.execute(
                "INSERT OR IGNORE INTO user_groups_link (user_id, chat_id) VALUES (?,?)",
                (real_user_id, chat_id)
            )
            invalidate_auth_cache(chat_id, real_user_id)
            logger.info(f"✅ تم ربط المستخدم {real_user_id} بالمجموعة")
        except Exception as e:
            logger.error(f"❌ فشل ربط المستخدم: {e}")

        try:
            admin_ids = [a.user.id for a in all_admins if a.user and not a.user.is_bot and a.user.id != chat_id]
            admin_count = await DB.sync_group_admins(chat_id, admin_ids)
            logger.info(f"✅ تم مزامنة {admin_count} مشرف")
        except Exception as e:
            logger.error(f"❌ فشل مزامنة المشرفين: {e}")
            admin_count = 0

        msg = (
            f"🎉 <b>تم تفعيل المجموعة بنجاح!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>المجموعة:</b> {escape(chat_name)}\n"
            f"🆔 <b>المعرف:</b> <code>{chat_id}</code>\n"
        )
        if creator_id:
            msg += f"👑 <b>المالك:</b> <code>{creator_id}</code>\n"
        msg += f"👤 <b>مشرف:</b> <code>{real_user_id}</code>\n"
        msg += f"👥 <b>المشرفون:</b> {admin_count}\n"
        msg += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <b>الحماية:</b> مفعّلة\n"
            f"💡 استخدم /security للإعدادات"
        )

        is_anonymous = (
            update.message and
            update.message.sender_chat and
            update.message.sender_chat.id == chat_id
        )

        if not is_anonymous:
            try:
                await safe_send(context.bot, user_id, msg, parse_mode='HTML')
            except BadRequest as e:
                if "User_bot_to_bot_disabled" in str(e):
                    await safe_send(context.bot, chat_id, msg, parse_mode='HTML')
                else:
                    logger.error(f"❌ فشل إرسال رسالة التأكيد: {e}")

        sent_msg = await safe_send(context.bot, chat_id, "🤖 <b>تم تفعيل البوت!</b>", parse_mode='HTML')
        if sent_msg:
            try:
                await asyncio.sleep(5)
                await sent_msg.delete()
            except Exception as e:
                logger.warning(f"⚠️ فشل حذف رسالة التفعيل: {e}")

    # ========== أوامر الإشراف ==========

    @staticmethod
    async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "ban")

    @staticmethod
    async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "mute")

    @staticmethod
    async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "warn")

    @staticmethod
    async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "kick")

    @staticmethod
    async def restrict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "restrict")

    @staticmethod
    async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await CommandHandlers._moderation_command(update, context, "unban")

    @staticmethod
    async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """تثبيت رسالة"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        if update.message.reply_to_message:
            perms = await check_bot_permissions(context.bot, chat_id)
            if not perms.get('can_pin_messages', False):
                await safe_send(context.bot, user_id, "❌ البوت لا يملك صلاحية تثبيت الرسائل.")
                return
            try:
                await context.bot.pin_chat_message(chat_id, update.message.reply_to_message.message_id)
                await safe_send(context.bot, user_id, "📌 تم التثبيت")
            except Exception as e:
                logger.error(f"❌ فشل التثبيت: {e}")

    @staticmethod
    async def _moderation_command(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
        """معالجة أوامر الإشراف"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id) or 'ar'
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return

        perms = await check_bot_permissions(context.bot, chat_id)
        if not perms.get('can_act', False):
            await safe_send(context.bot, user_id, "❌ البوت لا يملك الصلاحيات الكافية.")
            return

        args = context.args or []
        if not args:
            await safe_send(context.bot, user_id, f"📝 /{action} معرف_المستخدم [مدة_بالدقائق]")
            return

        try:
            target = int(args[0])
            if target <= 0:
                raise ValueError
        except (ValueError, TypeError):
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            return

        if await is_authorized_in_group(context.bot, chat_id, target):
            await safe_send(context.bot, user_id, "❌ لا يمكن معاملة مشرف")
            return

        reason_parts = []
        duration_seconds = 60
        if len(args) > 1:
            try:
                minutes = int(args[1])
                if minutes > 0:
                    duration_seconds = minutes * 60
                    reason_parts = args[2:]
                else:
                    reason_parts = args[1:]
            except ValueError:
                reason_parts = args[1:]

        reason = " ".join(reason_parts)

        if action == 'unban':
            try:
                await context.bot.unban_chat_member(chat_id, target)
                await DB.remove_penalties_for_user(target, chat_id, penalty_type='ban')
                await safe_send(context.bot, user_id, "✅ تم إلغاء الحظر")
            except Exception as e:
                logger.error(f"❌ فشل إلغاء الحظر: {e}")
                await safe_send(context.bot, user_id, f"❌ فشل إلغاء الحظر: {escape(str(e)[:50])}")
            return

        success, msg = await apply_penalty(context.bot, chat_id, target, action, duration_seconds, reason, user_id)
        await safe_send(context.bot, user_id, msg)

        if success:
            await invalidate_auth_cache(chat_id=chat_id, user_id=target)

    # ========== أوامر المطور ==========

    @staticmethod
    async def set_min_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """تعيين الحد الأدنى للفاصل الزمني (للمطورين)"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id) or 'ar'
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return

        args = context.args or []
        if not args:
            await safe_send(context.bot, user_id, "📝 /set_min_interval <دقائق>\nمثال: /set_min_interval 15")
            return

        try:
            val = int(args[0])
            if val < 1:
                await safe_send(context.bot, user_id, "❌ الحد الأدنى يجب أن يكون 1 دقيقة على الأقل")
                return
            await DB.set_setting('min_publish_interval', str(val))
            await safe_send(context.bot, user_id, f"✅ تم تعيين الحد الأدنى إلى {val} دقيقة\n🔄 أعد تشغيل البوت لتطبيق التغيير")
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيمة غير صالحة، أدخل رقماً")

    @staticmethod
    async def grant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """منح اشتراك (للمطورين)"""
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id) or 'ar'
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return

        args = context.args or []
        if len(args) < 2:
            await safe_send(context.bot, user_id, "📝 /grant <user_id> <days>")
            return

        try:
            target_id = int(args[0])
            days = int(args[1])
            if target_id <= 0 or days < 1 or days > 365:
                raise ValueError
        except (ValueError, TypeError):
            await safe_send(context.bot, user_id, "❌ قيم غير صالحة")
            return

        user_row = await DB.fetchone("SELECT user_id FROM users WHERE user_id=?", (target_id,))
        if not user_row:
            await safe_send(context.bot, user_id, "❌ المستخدم غير موجود في قاعدة البيانات")
            return

        plan_row = await DB.fetchone("SELECT id FROM plans WHERE is_gift=1 LIMIT 1")
        if not plan_row:
            plan_row = await DB.fetchone("SELECT id FROM plans WHERE is_active=1 AND is_gift=0 LIMIT 1")
        plan_id = plan_row['id'] if plan_row else None

        if plan_id is None:
            await safe_send(context.bot, user_id, "❌ لا توجد خطط متاحة للمنح")
            return

        success = await DB.grant_subscription_days(target_id, days, plan_id=plan_id, provider='manual')
        if success:
            await safe_send(context.bot, user_id, f"✅ تم منح {days} يوم للمستخدم <code>{_mask_id(target_id)}</code>", parse_mode='HTML')
        else:
            await safe_send(context.bot, user_id, "❌ فشل المنح - تحقق من السجلات")

    @staticmethod
    async def gift_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """عرض خطط الهدايا"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id) or 'ar'

        plans = await DB.get_gift_plans()
        if not plans:
            await safe_send(context.bot, user_id, "📭 لا توجد خطط متاحة حالياً.")
            return

        kb = []
        for plan in plans:
            kb.append([InlineKeyboardButton(
                f"🎁 {plan['days']} يوم - {plan['price']} ⭐",
                callback_data=f"buy_gift:{plan['id']}"
            )])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])

        text = (
            "💎 <b>شراء كود هدية</b>\n\n"
            "اختر المدة المناسبة:\n\n"
            "• بعد الدفع، ستحصل على كود فريد.\n"
            "• يمكنك إرسال الكود لأي شخص.\n"
            "• الشخص الذي يستخدم الكود يحصل على اشتراك مجاني."
        )

        await safe_send(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

    @staticmethod
    async def redeem_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """استخدام كود هدية"""
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id) or 'ar'

        args = context.args or []
        if not args:
            await safe_send(context.bot, user_id, "📝 أرسل الكود: <code>/redeem_gift &lt;الكود&gt;</code>", parse_mode='HTML')
            return

        code = args[0].strip()

        if len(code) < 4 or len(code) > 50:
            await safe_send(context.bot, user_id, "❌ كود غير صالح")
            return

        success, days = await DB.redeem_gift_code(user_id, code)

        if success and days > 0:
            await safe_send(context.bot, user_id, f"🎉 <b>تم تفعيل الاشتراك بنجاح!</b>\n\n✅ {days} يوم اشتراك مجاني.", parse_mode='HTML')
        elif days == -1:
            await safe_send(context.bot, user_id, "❌ لا يمكنك استخدام كود هدية قمت بإنشائه بنفسك.")
        else:
            await safe_send(context.bot, user_id, "❌ كود غير صالح أو مستخدم مسبقاً.")
