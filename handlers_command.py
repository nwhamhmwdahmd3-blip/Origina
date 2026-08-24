#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_command.py - معالجات الأوامر (CommandHandlers)
=====================================================
جميع الأوامر النصية للبوت.
"""

import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from config import CONFIG
from database import DB
from utils import (
    TimeUtils, TextUtils, safe_send, is_authorized_in_group,
    check_bot_permissions, invalidate_auth_cache, apply_penalty,
    RATE_LIMITER, METRICS, get_text, StateManager, UserState,
    KeyboardFactory, TranslationManager, CB,
)

logger = logging.getLogger(__name__)


class CommandHandlers:
    """جميع معالجات الأوامر"""

    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        username = update.effective_user.username or ""
        first_name = update.effective_user.first_name or ""
        await DB.register_user(user_id, username, first_name)

        args = context.args or []
        if args and args[0].startswith('ref_'):
            ref_code = args[0][4:]
            referrer = await DB.get_user_by_referral_code(ref_code)
            if referrer and referrer != user_id and not await DB.is_user_banned(referrer):
                existing = await DB.fetchone("SELECT 1 FROM referrals WHERE referred_id=?", (user_id,))
                if not existing:
                    if await DB.add_referral(referrer, user_id):
                        reward = await DB.get_referral_stats(referrer)
                        await safe_send(update.effective_chat.bot, referrer,
                                        f"🎁 تمت إحالة `{user_id}`. لديك {reward['available']} يوم متاح للصرف.")

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
                await safe_send(context.bot, user_id, "❌ تعذر التحقق من الاشتراك الإجباري، حاول لاحقًا")
                return

        lang = await DB.get_user_language(user_id)
        active = await DB.get_active_channel(user_id)
        cnt = 0
        ch_display = "لا توجد قنوات"
        if active:
            cnt = await DB.get_unpublished_posts_count(user_id, active)
            ch_info = await DB.get_channel_info(user_id, active)
            if ch_info:
                ch_display = f"{ch_info['channel_name']}"

        groups = len(await DB.get_user_groups(user_id))
        has_sub = await DB.has_active_subscription(user_id)
        sub_text = "✅ مفعل" if has_sub else "❌ غير مفعل"
        auto = await DB.get_auto_publish_status(user_id)
        auto_text = "مفعل" if auto else "معطل"
        recycle = await DB.get_auto_recycle_status(user_id)
        recycle_text = "مفعل" if recycle else "معطل"

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
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        await safe_send(context.bot, user_id, await get_text(lang, 'help_text'))

    @staticmethod
    async def trial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        if await DB.has_used_trial(user_id):
            await safe_send(context.bot, user_id, await get_text(lang, 'trial_used'))
            return
        days = await DB.activate_trial(user_id)
        await safe_send(context.bot, user_id, await get_text(lang, 'trial_activated', days=days))

    @staticmethod
    async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        kb = KeyboardFactory.build("plans", lang=lang)
        await safe_send(context.bot, user_id, await get_text(lang, 'plan_selector'), reply_markup=kb)

    @staticmethod
    async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        kb = KeyboardFactory.build("support", lang=lang)
        await safe_send(context.bot, user_id, await get_text(lang, 'send_support_message'), reply_markup=kb)

    @staticmethod
    async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        text = await get_text(lang, 'developer_info',
                              owner_id=CONFIG.PRIMARY_OWNER_ID,
                              bot_name=CONFIG.BOT_NAME,
                              bot_username=CONFIG.BOT_USERNAME)
        await safe_send(context.bot, user_id, text)

    @staticmethod
    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id)
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
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
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
        await safe_send(context.bot, update.effective_user.id, "📚 الردود التلقائية تعمل!")

    @staticmethod
    async def contests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)
        contests = await DB.get_active_contests(10)
        if not contests:
            await safe_send(context.bot, user_id, "📭 لا توجد مسابقات نشطة")
            return
        text = "🏆 **المسابقات النشطة**\n\n"
        for c in contests:
            text += f"• **{c['title']}**\n"
            text += f"  🎁 {c['prize']}\n"
            text += f"  📅 {c['end_date'][:10]}\n\n"
        kb = KeyboardFactory.build("contests", lang=lang)
        await safe_send(context.bot, user_id, text, reply_markup=kb)

    @staticmethod
    async def security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        lang = await DB.get_user_language(user_id)
        context.user_data['security_chat_id'] = chat_id
        settings = await DB.get_security_settings(chat_id)
        text = KeyboardFactory._format_security_text(settings)
        kb = KeyboardFactory.build("security", chat_id=chat_id, user_id=user_id, lang=lang)
        await safe_send(context.bot, user_id, text, reply_markup=kb)

    @staticmethod
    async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        lang = await DB.get_user_language(user_id)
        kb = KeyboardFactory.build("panel", chat_id=chat_id, user_id=user_id, lang=lang)
        await safe_send(context.bot, user_id, "📋 لوحة تحكم المجموعة", reply_markup=kb)

    @staticmethod
    async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        user_id = update.effective_user.id
        if user_id != CONFIG.PRIMARY_OWNER_ID:
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        if not context.args:
            await safe_send(context.bot, user_id, "📝 /register_hidden_owner <user_id>")
            return
        try:
            owner_id = int(context.args[0])
        except:
            await safe_send(context.bot, user_id, "⚠️ معرف غير صالح")
            return
        chat_id = update.effective_chat.id
        await DB.execute("INSERT OR IGNORE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,1)", (chat_id, owner_id))
        invalidate_auth_cache(chat_id, owner_id)
        await safe_send(context.bot, user_id, f"✅ تم تسجيل `{owner_id}` كمالك مخفي")

    @staticmethod
    async def remove_hidden_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id != CONFIG.PRIMARY_OWNER_ID:
            return
        if not context.args:
            return
        try:
            owner_id = int(context.args[0])
        except:
            return
        chat_id = update.effective_chat.id
        await DB.execute("DELETE FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, owner_id))
        invalidate_auth_cache(chat_id, owner_id)
        await safe_send(context.bot, user_id, f"✅ تم إزالة `{owner_id}`")

    @staticmethod
    async def add_hidden_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        is_owner = user_id == CONFIG.PRIMARY_OWNER_ID
        if not is_owner:
            row = await DB.fetchone("SELECT 1 FROM hidden_owner_groups WHERE chat_id=? AND owner_id=?", (chat_id, user_id))
            is_owner = row is not None
        if not is_owner:
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return
        if not context.args:
            return
        try:
            admin_id = int(context.args[0])
        except:
            return
        await DB.add_hidden_admin(chat_id, admin_id, user_id)
        invalidate_auth_cache(chat_id, admin_id)
        await safe_send(context.bot, user_id, f"✅ تم إضافة `{admin_id}` كمشرف مخفي")

    @staticmethod
    async def remove_hidden_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        except:
            return
        await DB.execute("DELETE FROM hidden_admins WHERE chat_id=? AND admin_id=?", (chat_id, admin_id))
        invalidate_auth_cache(chat_id, admin_id)
        await safe_send(context.bot, user_id, f"✅ تم إزالة `{admin_id}`")

    @staticmethod
    async def list_hidden_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        text = "👤 **المخفيون**\n"
        for o in owners:
            text += f"👑 `{o[0]}`\n"
        for a in admins:
            text += f"🛡️ `{a[0]}`\n"
        await safe_send(context.bot, user_id, text if owners or admins else "📭 لا يوجد")

    @staticmethod
    async def syncgroup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
            await safe_send(context.bot, update.effective_user.id, "❌ هذا الأمر للمجموعات فقط")
            return

        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "بدون اسم"
        user_id = update.effective_user.id

        logger.info(f"🔍 محاولة تسجيل المجموعة: chat_id={chat_id}, user_id={user_id}")

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
        logger.info(f"🔍 المالك: {creator_id}")

        is_admin = False
        is_anonymous = False

        for admin in all_admins:
            if admin.user.id == user_id:
                is_admin = True
                is_anonymous = getattr(admin, 'is_anonymous', False)
                break

        if not is_admin and user_id == CONFIG.ANONYMOUS_ADMIN_ID:
            is_admin = True
            is_anonymous = True
            logger.info("🔍 تم التعرف على مشرف مخفي")

        if not is_admin:
            await safe_send(context.bot, user_id, "❌ **أنت لست مشرفاً في هذه المجموعة!**")
            return

        logger.info(f"🔍 المستخدم مشرف: is_anonymous={is_anonymous}")

        try:
            await DB.register_group(chat_id, chat_name, creator_id or user_id, update.effective_chat.username)
            logger.info("✅ تم تسجيل المجموعة في bot_groups")
        except Exception as e:
            logger.error(f"❌ فشل تسجيل المجموعة في bot_groups: {e}")
            await safe_send(context.bot, user_id, "❌ فشل تسجيل المجموعة")
            return

        bot_perms = await check_bot_permissions(context.bot, chat_id)
        if not bot_perms.get('can_act', False):
            await safe_send(context.bot, user_id, "⚠️ **البوت ليس مشرفاً!**")
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
                (user_id, chat_id)
            )
            invalidate_auth_cache(chat_id, user_id)
            logger.info("✅ تم ربط المستخدم بالمجموعة")
        except Exception as e:
            logger.error(f"❌ فشل ربط المستخدم بالمجموعة: {e}")
            await safe_send(context.bot, user_id, "❌ فشل ربط المستخدم بالمجموعة")
            return

        try:
            admin_ids = [a.user.id for a in all_admins if a.user and not a.user.is_bot]
            admin_count = await DB.sync_group_admins(chat_id, admin_ids)
            logger.info(f"✅ تم مزامنة {admin_count} مشرف")
        except Exception as e:
            logger.error(f"❌ فشل مزامنة المشرفين: {e}")
            admin_count = 0

        msg = f"✅ **تم تفعيل المجموعة!**\n\n"
        msg += f"📌 {chat_name}\n"
        msg += f"🆔 `{chat_id}`\n"
        if creator_id:
            msg += f"👑 المالك: `{creator_id}`\n"
        msg += f"{'👻 مخفي' if is_anonymous else '👤 مشرف'}: `{user_id}`\n"
        msg += f"👥 {admin_count} مشرف"

        try:
            await safe_send(context.bot, user_id, msg)
        except BadRequest as e:
            if "User_bot_to_bot_disabled" in str(e):
                await safe_send(context.bot, chat_id, msg)
            else:
                logger.error(f"❌ فشل إرسال رسالة التأكيد: {e}")

        sent_msg = await safe_send(context.bot, chat_id, "🤖 **تم تفعيل البوت!**")
        if sent_msg:
            try:
                await asyncio.sleep(5)
                await sent_msg.delete()
            except Exception as e:
                logger.warning(f"⚠️ فشل حذف رسالة التفعيل: {e}")

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
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            return
        if update.message.reply_to_message:
            try:
                await context.bot.pin_chat_message(chat_id, update.message.reply_to_message.message_id)
                await safe_send(context.bot, user_id, "📌 تم التثبيت")
            except Exception as e:
                logger.error(f"❌ فشل التثبيت: {e}")

    @staticmethod
    async def _moderation_command(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return

        args = context.args or []
        if not args:
            await safe_send(context.bot, user_id, f"📝 /{action} معرف_المستخدم [مدة_بالدقائق]")
            return

        try:
            target = int(args[0])
        except:
            await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            return

        if target <= 0:
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
            return

        success, msg = await apply_penalty(context.bot, chat_id, target, action, duration_seconds, reason, user_id)
        await safe_send(context.bot, user_id, msg)

    @staticmethod
    async def set_min_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id)
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
        user_id = update.effective_user.id
        if not CONFIG.is_developer(user_id):
            lang = await DB.get_user_language(user_id)
            await safe_send(context.bot, user_id, await get_text(lang, 'unauthorized'))
            return

        args = context.args or []
        if len(args) < 2:
            await safe_send(context.bot, user_id, "📝 /grant <user_id> <days>")
            return

        try:
            target_id = int(args[0])
            days = int(args[1])
        except ValueError:
            await safe_send(context.bot, user_id, "❌ قيم غير صالحة")
            return

        if days < 1 or days > 365:
            await safe_send(context.bot, user_id, "❌ عدد الأيام يجب أن يكون بين 1 و 365")
            return

        user_row = await DB.fetchone("SELECT user_id FROM users WHERE user_id=?", (target_id,))
        if not user_row:
            await safe_send(context.bot, user_id, "❌ المستخدم غير موجود في قاعدة البيانات")
            return

        plan_row = await DB.fetchone("SELECT id FROM plans WHERE is_gift=1 LIMIT 1")
        if not plan_row:
            plan_row = await DB.fetchone("SELECT id FROM plans WHERE is_active=1 AND is_gift=0 LIMIT 1")
        plan_id = plan_row[0] if plan_row else None

        if plan_id is None:
            await safe_send(context.bot, user_id, "❌ لا توجد خطط متاحة للمنح")
            return

        success = await DB.grant_subscription_days(target_id, days, plan_id=plan_id, provider='manual')
        if success:
            await safe_send(context.bot, user_id, f"✅ تم منح {days} يوم للمستخدم `{target_id}`")
        else:
            await safe_send(context.bot, user_id, "❌ فشل المنح - تحقق من السجلات")

    @staticmethod
    async def gift_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)

        plans = await DB.get_gift_plans()
        if not plans:
            await safe_send(context.bot, user_id, "📭 لا توجد خطط متاحة حالياً.")
            return

        kb = []
        for plan in plans:
            days = plan['days']
            price = plan['price']
            kb.append([InlineKeyboardButton(
                f"🎁 {days} يوم - {price} ⭐",
                callback_data=f"buy_gift:{plan['id']}"
            )])
        kb.append([InlineKeyboardButton(KeyboardFactory.get_text("back", lang), callback_data=CB.BACK)])

        text = "💎 **شراء كود هدية**\n\nاختر المدة المناسبة:\n\n"
        text += "• بعد الدفع، ستحصل على كود فريد.\n"
        text += "• يمكنك إرسال الكود لأي شخص.\n"
        text += "• الشخص الذي يستخدم الكود يحصل على اشتراك مجاني."

        await safe_send(context.bot, user_id, text, reply_markup=InlineKeyboardMarkup(kb))

    @staticmethod
    async def redeem_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await DB.get_user_language(user_id)

        args = context.args or []
        if not args:
            await safe_send(context.bot, user_id, "📝 أرسل الكود: `/redeem_gift <الكود>`")
            return

        code = args[0].strip()
        success, days = await DB.redeem_gift_code(user_id, code)

        if success and days > 0:
            await safe_send(context.bot, user_id, f"🎉 **تم تفعيل الاشتراك بنجاح!**\n\n✅ {days} يوم اشتراك مجاني.")
        elif days == -1:
            await safe_send(context.bot, user_id, "❌ لا يمكنك استخدام كود هدية قمت بإنشائه بنفسك.")
        else:
            await safe_send(context.bot, user_id, "❌ كود غير صالح أو مستخدم مسبقاً.")
