#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
handlers_message.py - معالجات الرسائل
"""

import asyncio
import re
import logging
from pathlib import Path
from datetime import datetime, timedelta

from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from telegram.error import BadRequest

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


class MessageHandlers:
    @staticmethod
    async def handle_private(update, context):
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        msg = update.message
        text = msg.text.strip() if msg.text else ""
        state = StateManager.get(user_id)

        if state == UserState.WAIT_IMPORT_FILE:
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
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GITHUB_URL:
            url = text.strip()
            if not url.startswith('http'):
                await safe_send(context.bot, user_id, "❌ رابط غير صالح")
                StateManager.clear(user_id)
                return
            json_data = await fetch_json_from_url(url)
            if not json_data:
                await safe_send(context.bot, user_id, "❌ فشل التحميل")
                StateManager.clear(user_id)
                return
            count = await import_auto_replies(-1, json_data, overwrite=True)
            _auto_reply_cache.invalidate()
            await safe_send(context.bot, user_id, f"✅ تم استيراد {count} رد")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_CHANNEL:
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
                    await safe_send(context.bot, user_id, "❌ البوت ليس مشرفاً!")
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
                    has_sub = await DB.has_active_subscription(user_id)
                    if not has_sub:
                        await safe_send(context.bot, user_id, "❌ يجب أن يكون لديك اشتراك نشط لإضافة قناة")
                        StateManager.clear(user_id)
                        return

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
                    active_plan = await DB.get_active_plan(user_id)
                    if active_plan:
                        current_channels = len(await DB.get_user_channels(user_id))
                        if current_channels >= active_plan['max_channels']:
                            await safe_send(context.bot, user_id, f"❌ لقد وصلت للحد الأقصى ({active_plan['max_channels']} قنوات) في خطتك.")
                        else:
                            await safe_send(context.bot, user_id, "❌ فشلت الإضافة (ربما تجاوزت حد القنوات المسموح)")
                    else:
                        await safe_send(context.bot, user_id, "❌ يجب أن يكون لديك اشتراك نشط لإضافة قناة")
            except Exception as e:
                logger.error(f"❌ فشل إضافة القناة: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.ADDING_POSTS:
            if text.strip().lower() == "/done":
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, "✅ تم إنهاء إضافة المنشورات.")
                return

            if text.strip().isdigit():
                await safe_send(
                    context.bot, user_id,
                    "⚠️ أنت في وضع إضافة المنشورات.\n"
                    "إذا أردت ضبط الجدولة فاضغط زر «القائمة الرئيسية» أولاً أو أرسل /done."
                )
                return

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
            content = msg.caption or "" if media_type != 'text' else text

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

        if state == UserState.WAIT_BROADCAST:
            async def broadcast():
                offset = 0
                sent = 0
                try:
                    while True:
                        users = await DB.fetchall("SELECT user_id, banned FROM users ORDER BY user_id LIMIT 5000 OFFSET ?", (offset,))
                        if not users:
                            break
                        for uid, banned in users:
                            if not banned:
                                try:
                                    await safe_send(context.bot, uid, text)
                                    sent += 1
                                    await asyncio.sleep(0.05)
                                except:
                                    pass
                        offset += 5000
                    await safe_send(context.bot, user_id, f"✅ {sent}")
                except Exception as e:
                    logger.error(f"❌ فشل البث: {e}")
                    await safe_send(context.bot, user_id, "❌ فشل البث")

            asyncio.create_task(broadcast())
            await safe_send(context.bot, user_id, "⏳ جاري البث...")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_AUTO_KEY:
            context.user_data['auto_key'] = text.strip().lower()
            StateManager.set(user_id, UserState.WAIT_AUTO_REPLY)
            await safe_send(context.bot, user_id, "📝 الرد:")
            return

        if state == UserState.WAIT_AUTO_REPLY:
            chat_id_auto = context.user_data.get('auto_chat')
            keyword = context.user_data.get('auto_key')
            if chat_id_auto is not None and keyword:
                await DB.add_auto_reply(chat_id_auto, keyword, text)
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, "✅ تمت إضافة الرد")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_AUTO_DEL:
            chat_id_auto = context.user_data.get('auto_chat')
            if chat_id_auto is not None:
                await DB.remove_auto_reply(chat_id_auto, text.strip().lower())
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, "✅ تم حذف الرد")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GLOBAL_BAN:
            word = text.strip().lower()
            if len(word) >= 2:
                await DB.add_banned_word(word, -1, user_id)
                invalidate_banned_words_cache()
                await safe_send(context.bot, user_id, "✅ تمت الإضافة")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GLOBAL_BAN:
            await DB.remove_banned_word(text.strip().lower(), -1)
            invalidate_banned_words_cache()
            await safe_send(context.bot, user_id, "✅ تم الحذف")
            StateManager.clear(user_id)
            return

        if state == UserState.SUPPORT_MODE:
            content = msg.text or msg.caption or ""
            ticket_num = await DB.create_ticket(user_id, update.effective_user.username or "", content)
            await safe_send(context.bot, user_id, f"✅ #{ticket_num}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_MIN:
            try:
                val = int(text)
                min_val = await get_min_publish_interval()
                if val < min_val:
                    await safe_send(context.bot, user_id,
                                    f"❌ الحد الأدنى للفاصل الزمني هو {min_val} دقيقة")
                    StateManager.clear(user_id)
                    return
                if 1 <= val <= 1440:
                    ch = context.user_data.get('schedule_ch')
                    if ch:
                        await DB.update_schedule(ch, schedule_type='interval_minutes',
                                                 interval_minutes=val)
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
            if ':' in text:
                ch = context.user_data.get('schedule_ch')
                if ch:
                    await DB.update_schedule(ch, publish_time=text)
                    await safe_send(context.bot, user_id, f"✅ تم التحديث إلى {text}")
            else:
                await safe_send(context.bot, user_id, "❌ الصيغة غير صالحة، استخدم HH:MM")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            word = text.strip().lower()
            if chat_id_ban and len(word) >= 2:
                await DB.add_banned_word(word, chat_id_ban, user_id)
                invalidate_banned_words_cache(chat_id_ban)
                await safe_send(context.bot, user_id, f"✅ تمت إضافة: {word}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_GROUP_BAN:
            chat_id_ban = context.user_data.get('ban_chat')
            if chat_id_ban:
                await DB.remove_banned_word(text.strip().lower(), chat_id_ban)
                invalidate_banned_words_cache(chat_id_ban)
                await safe_send(context.bot, user_id, f"✅ تم حذف: {text}")
            StateManager.clear(user_id)
            return

        if state in (UserState.WAIT_BAN, UserState.WAIT_MUTE, UserState.WAIT_WARN,
                     UserState.WAIT_KICK, UserState.WAIT_RESTRICT, UserState.WAIT_UNBAN):
            chat_id_adv = context.user_data.get('adv_chat')
            try:
                parts = text.split()
                target = int(parts[0])
                if target <= 0:
                    await safe_send(context.bot, user_id, "❌ معرف غير صالح")
                    StateManager.clear(user_id)
                    return
                action_map = {
                    UserState.WAIT_BAN: "ban", UserState.WAIT_MUTE: "mute",
                    UserState.WAIT_WARN: "warn", UserState.WAIT_KICK: "kick",
                    UserState.WAIT_RESTRICT: "restrict", UserState.WAIT_UNBAN: "unban"
                }
                action = action_map.get(state)
                if action and chat_id_adv:
                    if action == 'unban':
                        await context.bot.unban_chat_member(chat_id_adv, target)
                        await DB.remove_penalties_for_user(target, chat_id_adv, penalty_type='ban')
                        await safe_send(context.bot, user_id, f"✅ تم إلغاء حظر `{target}`")
                    else:
                        duration_seconds = 60
                        if len(parts) > 1 and action in ('ban', 'mute', 'restrict'):
                            try:
                                minutes = int(parts[1])
                                if minutes > 0:
                                    duration_seconds = minutes * 60
                            except ValueError:
                                pass
                        success, msg = await apply_penalty(context.bot, chat_id_adv, target, action, duration_seconds)
                        await safe_send(context.bot, user_id, msg)
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            except Exception as e:
                logger.error(f"❌ خطأ في الإجراء: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PIN:
            chat_id_adv = context.user_data.get('adv_chat')
            try:
                if update.message.reply_to_message:
                    msg_id = update.message.reply_to_message.message_id
                else:
                    msg_id = int(text)
                await context.bot.pin_chat_message(chat_id_adv, msg_id)
                await safe_send(context.bot, user_id, f"📌 تم تثبيت الرسالة {msg_id}")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح أو رد على رسالة")
            except Exception as e:
                logger.error(f"❌ فشل التثبيت: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_CONTEST_TITLE:
            context.user_data['contest_title'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_DESC)
            await safe_send(context.bot, user_id, "📝 الوصف:")
            return

        if state == UserState.WAIT_CONTEST_DESC:
            context.user_data['contest_desc'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_PRIZE)
            await safe_send(context.bot, user_id, "🎁 الجائزة:")
            return

        if state == UserState.WAIT_CONTEST_PRIZE:
            context.user_data['contest_prize'] = text
            StateManager.set(user_id, UserState.WAIT_CONTEST_DATE)
            await safe_send(context.bot, user_id, "📅 التاريخ (YYYY-MM-DD HH:MM):")
            return

        if state == UserState.WAIT_CONTEST_DATE:
            try:
                end_date = datetime.strptime(text, "%Y-%m-%d %H:%M")
                cid = await DB.create_contest(
                    user_id,
                    context.user_data.pop('contest_title', ''),
                    context.user_data.pop('contest_desc', ''),
                    context.user_data.pop('contest_prize', ''),
                    TimeUtils.mecca_to_utc(end_date).strftime('%Y-%m-%d %H:%M:%S')
                )
                await safe_send(context.bot, user_id, f"✅ مسابقة #{cid}")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ صيغة غير صالحة، استخدم YYYY-MM-DD HH:MM")
            except Exception as e:
                logger.error(f"❌ فشل إنشاء المسابقة: {e}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_CONTEST_ANSWER:
            cid = context.user_data.get('contest_join')
            if cid:
                success = await DB.join_contest(cid, user_id, text)
                if success:
                    await safe_send(context.bot, user_id, "✅ تم المشاركة!")
                else:
                    await safe_send(context.bot, user_id, "❌ فشل المشاركة (ربما انتهت المسابقة أو شاركت مسبقًا)")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ADMIN_ADD:
            try:
                target = int(text)
                if target <= 0:
                    await safe_send(context.bot, user_id, "❌ معرف غير صالح")
                else:
                    await DB.execute("INSERT OR IGNORE INTO bot_admins (user_id, added_by, added_at) VALUES (?,?,?)",
                                     (target, user_id, TimeUtils.sql_iso()))
                    await safe_send(context.bot, user_id, f"✅ تم إضافة `{target}` كمشرف")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ADMIN_REM:
            try:
                target = int(text)
                if target <= 0:
                    await safe_send(context.bot, user_id, "❌ معرف غير صالح")
                else:
                    await DB.execute("DELETE FROM bot_admins WHERE user_id=?", (target,))
                    await safe_send(context.bot, user_id, f"✅ تم إزالة `{target}`")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ معرف غير صالح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GRANT_FREE:
            parts = text.split()
            if len(parts) < 2:
                await safe_send(context.bot, user_id, "❌ أرسل المعرف والأيام هكذا: `123456789 365`")
                StateManager.clear(user_id)
                return
            try:
                target_id = int(parts[0])
                days = int(parts[1])
            except ValueError:
                await safe_send(context.bot, user_id, "❌ قيم غير صالحة")
                StateManager.clear(user_id)
                return

            if days < 1 or days > 365:
                await safe_send(context.bot, user_id, "❌ عدد الأيام يجب أن يكون بين 1 و 365")
                StateManager.clear(user_id)
                return

            gift_plan = await DB.fetchone("SELECT id FROM plans WHERE is_gift=1 LIMIT 1")
            plan_id = gift_plan[0] if gift_plan else None
            if plan_id is None:
                await safe_send(context.bot, user_id, "❌ لا توجد خطة هدية متاحة")
                StateManager.clear(user_id)
                return

            success = await DB.grant_subscription_days(target_id, days, plan_id=plan_id, provider='manual')
            if success:
                await safe_send(context.bot, user_id, f"✅ تم منح {days} يوم للمستخدم `{target_id}`")
            else:
                await safe_send(context.bot, user_id, "❌ فشل المنح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_UPDATE:
            ch = await DB.get_updates_channel()
            if ch:
                try:
                    if ch.lstrip('-').isdigit():
                        await context.bot.send_message(int(ch), f"📢 {text}")
                    else:
                        await context.bot.send_message(f"@{ch}", f"📢 {text}")
                    await safe_send(context.bot, user_id, "✅ تم الإرسال")
                except Exception as e:
                    await safe_send(context.bot, user_id, f"❌ فشل الإرسال: {str(e)[:50]}")
            else:
                await safe_send(context.bot, user_id, "❌ لا توجد قناة تحديثات")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_UPDATE_CH:
            await DB.set_setting('updates_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, f"✅ تم تعيين قناة التحديثات: {text}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_FORCE:
            await DB.set_setting('force_subscribe_channel', text.replace('@', ''))
            await safe_send(context.bot, user_id, f"✅ تم تعيين الاشتراك الإجباري: {text}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_REM_DAYS:
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
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and val >= 0:
                    await DB.execute("UPDATE group_security SET max_message_length=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين الحد الأقصى إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_WARN_COUNT:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and 1 <= val <= 10:
                    await DB.execute("UPDATE group_security SET max_warnings=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين عدد التحذيرات إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ القيمة غير صالحة (1-10)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_LOG_CH:
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

        if state == UserState.WAIT_KEYWORD:
            context.user_data['keyword'] = text.strip().lower()
            StateManager.set(user_id, UserState.WAIT_REPLY)
            await safe_send(context.bot, user_id, "📝 الرد:")
            return

        if state == UserState.WAIT_REPLY:
            keyword = context.user_data.get('keyword')
            if keyword:
                await DB.add_auto_reply(-1, keyword, text)
                _auto_reply_cache.invalidate()
                await safe_send(context.bot, user_id, f"✅ تم إضافة الرد للكلمة: {keyword}")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PENALTY_DURATION:
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

        if state == UserState.WAIT_WELCOME_TEXT:
            chat_id_sec = context.user_data.get('sec_chat')
            if chat_id_sec:
                await DB.execute("UPDATE group_security SET welcome_text=? WHERE chat_id=?", (text, chat_id_sec))
                await safe_send(context.bot, user_id, "✅ تم تعيين نص الترحيب")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_GOODBYE_TEXT:
            chat_id_sec = context.user_data.get('sec_chat')
            if chat_id_sec:
                await DB.execute("UPDATE group_security SET goodbye_text=? WHERE chat_id=?", (text, chat_id_sec))
                await safe_send(context.bot, user_id, "✅ تم تعيين نص الوداع")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_SLOW_MODE_SECONDS:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and 0 <= val <= 3600:
                    await DB.execute("UPDATE group_security SET slow_mode_seconds=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين مدة الوضع البطيء إلى {val} ثانية")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة (0-3600)")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ANTIFLOOD_MESSAGES:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and val >= 1:
                    await DB.execute("UPDATE group_security SET antiflood_messages=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين عدد الرسائل إلى {val}")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_ANTIFLOOD_SECONDS:
            try:
                val = int(text)
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec and val >= 1:
                    await DB.execute("UPDATE group_security SET antiflood_seconds=? WHERE chat_id=?", (val, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين الفترة إلى {val} ثانية")
                else:
                    await safe_send(context.bot, user_id, "❌ قيمة غير صالحة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_NIGHT_START:
            if re.match(r'^\d{2}:\d{2}$', text):
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec:
                    await DB.execute("UPDATE group_security SET night_mode_start=? WHERE chat_id=?", (text, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين وقت البداية إلى {text}")
            else:
                await safe_send(context.bot, user_id, "❌ الصيغة غير صالحة (HH:MM)")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_NIGHT_END:
            if re.match(r'^\d{2}:\d{2}$', text):
                chat_id_sec = context.user_data.get('sec_chat')
                if chat_id_sec:
                    await DB.execute("UPDATE group_security SET night_mode_end=? WHERE chat_id=?", (text, chat_id_sec))
                    await safe_send(context.bot, user_id, f"✅ تم تعيين وقت النهاية إلى {text}")
            else:
                await safe_send(context.bot, user_id, "❌ الصيغة غير صالحة (HH:MM)")
            StateManager.clear(user_id)
            return

        if state == UserState.WAIT_PENALTY_DEFAULT_DURATION:
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
                    col_map = {
                        'mute': 'mute_default_duration',
                        'ban': 'ban_default_duration',
                        'restrict': 'restrict_default_duration'
                    }
                    col = col_map.get(p_type)
                    if col:
                        await DB.execute(f"UPDATE group_security SET {col}=? WHERE chat_id=?", (duration_seconds, chat_id_pen))
                        await safe_send(context.bot, user_id, f"✅ تم تعيين {p_type} إلى {dur_minutes} دقيقة")
            except ValueError:
                await safe_send(context.bot, user_id, "❌ يرجى إدخال رقم صحيح")
            StateManager.clear(user_id)
            return

        # الرسالة الافتراضية
        from handlers_command import CommandHandlers
        await CommandHandlers.start(update, context)

    @staticmethod
    async def handle_group(update, context):
        if not update.message or not update.effective_user:
            return
        chat = update.effective_chat
        if not chat or chat.type not in ['group', 'supergroup']:
            return
        chat_id = chat.id
        text = update.message.text or ""
        if update.effective_user.is_bot:
            return

        logger.info(f"🔍 handle_group: text={text[:30]}, replies_loaded={len(_REPLIES_FROM_FILE)}")

        locked = await DB.fetchone("SELECT locked FROM chat_locks WHERE chat_id=?", (chat_id,))
        if locked and locked[0] == 1:
            if not await is_authorized_in_group(context.bot, chat_id, update.effective_user.id):
                try:
                    await update.message.delete()
                except:
                    pass
                return

        settings = await DB.get_security_settings(chat_id)
        perms = await check_bot_permissions(context.bot, chat_id)
        can_delete = perms.get('can_delete_messages', perms.get('can_act', False))

        if await is_authorized_in_group(context.bot, chat_id, update.effective_user.id):
            ars = await DB.get_auto_reply_settings(chat_id)
            if ars.get('enabled', False):
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
                    except:
                        pass
            return

        if settings.get('delete_links', False) and TextUtils.contains_link(text):
            if can_delete:
                try:
                    await update.message.delete()
                except:
                    pass
            await apply_violation_penalty(context, chat_id, update.effective_user.id, 'links', "مخالفة روابط")
            return

        if settings.get('mentions', False) and TextUtils.contains_mention(text):
            if can_delete:
                try:
                    await update.message.delete()
                except:
                    pass
            await apply_violation_penalty(context, chat_id, update.effective_user.id, 'mentions', "مخالفة منشن")
            return

        if settings.get('delete_banned_words', False):
            banned_words = await get_banned_words_cached(chat_id)
            if any(word in text.lower() for word in banned_words):
                if can_delete:
                    try:
                        await update.message.delete()
                    except:
                        pass
                await apply_violation_penalty(context, chat_id, update.effective_user.id, 'banned_words', "كلمة محظورة")
                return

        ars = await DB.get_auto_reply_settings(chat_id)
        if ars.get('enabled', False):
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
                except:
                    pass

    @staticmethod
    async def handle_service(update, context):
        if not update.message or not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        settings = await DB.get_security_settings(chat_id)

        if settings.get('delete_service', False):
            try:
                await update.message.delete()
            except:
                pass
            user_id = update.message.from_user.id if update.message.from_user else None
            if user_id:
                await apply_violation_penalty(context, chat_id, user_id, 'service', "رسالة خدمة")

        if settings.get('welcome_enabled', False) and update.message.new_chat_members:
            for member in update.message.new_chat_members:
                if member.id != context.bot.id:
                    welcome_text = settings.get('welcome_text', "مرحباً {user} 🤍")
                    text = welcome_text.format(user=member.full_name or "العضو")
                    try:
                        await context.bot.send_message(chat_id, text)
                    except:
                        pass

        if settings.get('goodbye_enabled', False) and update.message.left_chat_member:
            member = update.message.left_chat_member
            if member.id != context.bot.id:
                goodbye_text = settings.get('goodbye_text', "وداعاً {user} 👋")
                text = goodbye_text.format(user=member.full_name or "العضو")
                try:
                    await context.bot.send_message(chat_id, text)
                except:
                    pass

    @staticmethod
    async def handle_join_request(update, context):
        join_request = update.chat_join_request
        chat_id = update.effective_chat.id
        settings = await DB.get_security_settings(chat_id)

        if settings.get('auto_approve_join', False):
            try:
                await join_request.approve()
                if settings.get('welcome_enabled', False):
                    await context.bot.send_message(chat_id, f"مرحباً {join_request.from_user.full_name} 🤍")
            except:
                pass
            return

        if settings.get('auto_reject_join', False):
            try:
                await join_request.decline()
            except:
                pass


async def apply_violation_penalty(context, chat_id, user_id, violation_type, reason="مخالفة"):
    if await is_authorized_in_group(context.bot, chat_id, user_id):
        return

    warnings = await DB.add_user_warning(user_id, chat_id)

    rule = await DB.get_violation_penalty(chat_id, violation_type)
    if not rule:
        settings = await DB.get_security_settings(chat_id)
        penalty_type = settings.get('warn_penalty', 'ban')
        duration_seconds = 0
    else:
        penalty_type = rule['penalty_type']
        duration_seconds = rule['duration_seconds']

    max_warnings = (await DB.get_security_settings(chat_id)).get('max_warnings', 3)

    if warnings < max_warnings:
        try:
            await context.bot.send_message(
                chat_id,
                f"⚠️ المستخدم `{user_id}` تلقى إنذارًا ({warnings}/{max_warnings}) بسبب: {reason}"
            )
        except:
            pass
        return

    try:
        if penalty_type in ('ban', 'mute', 'restrict'):
            until_date = TimeUtils.utc_now() + timedelta(seconds=duration_seconds) if duration_seconds > 0 else None
            if penalty_type == 'ban':
                await context.bot.ban_chat_member(chat_id, user_id, until_date=until_date)
            elif penalty_type == 'mute':
                await context.bot.restrict_chat_member(
                    chat_id, user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date
                )
            elif penalty_type == 'restrict':
                await context.bot.restrict_chat_member(
                    chat_id, user_id,
                    permissions=ChatPermissions(can_send_messages=False, can_send_media_messages=False),
                    until_date=until_date
                )
            await DB.add_penalty(
                user_id=user_id,
                chat_id=chat_id,
                penalty_type=penalty_type,
                duration=duration_seconds,
                reason=reason,
                issued_by=context.bot.id
            )
            await DB.reset_user_warnings(user_id, chat_id)
        else:
            logger.error(f"❌ نوع عقوبة غير صالح في apply_violation_penalty: {penalty_type}")
    except Exception as e:
        logger.error(f"❌ فشل تطبيق عقوبة {penalty_type} على {user_id}: {e}")
