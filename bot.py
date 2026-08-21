#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🌿 Relax Manager – البوت الرئيسي (نسخة نهائية محسّنة)
- معالجات دفع آمنة (pre_checkout + successful_payment)
- جميع الأوامر الأساسية والإشرافية والمتقدمة
- تحديد allowed_updates
- إعادة تشغيل المهام الخلفية عند الفشل
- دعم Webhook و Polling
"""

import asyncio
import os
import logging
import traceback
import json

from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ChatJoinRequestHandler, filters,
    PreCheckoutQueryHandler
)

from config import CONFIG, PATHS
from database import DB, initialize_db
from handlers import CommandHandlers, CallbackHandlers, MessageHandlers
from utils import (
    TranslationManager, KeyboardFactory, BackgroundTasks,
    ErrorHandler, setup_webhook, safe_send
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# التحديثات المسموحة
ALLOWED_UPDATES = [
    "message",
    "callback_query",
    "chat_join_request",
    "pre_checkout_query"
]

# =====================================================================
# دوال مساعدة للتحقق من الفاتورة
# =====================================================================

async def _validate_invoice_for_payment(user_id: int, payload: str):
    try:
        data = json.loads(payload)
    except:
        return None, None, None

    invoice_number = data.get('invoice')
    if not invoice_number:
        return None, None, None

    invoice = await DB.get_invoice(invoice_number)
    if not invoice or invoice['user_id'] != user_id or invoice['status'] != 'pending':
        return None, None, None

    if data.get('type') != 'subscription':
        return None, None, None

    plan_id = data.get('plan_id')
    plan = await DB.get_plan(plan_id)
    if not plan or not plan.get('is_active'):
        return None, None, None

    return invoice, plan, data

# =====================================================================
# معالجات الدفع
# =====================================================================

async def pre_checkout(update, context):
    query = update.pre_checkout_query
    user_id = query.from_user.id
    payload = query.invoice_payload

    invoice, plan, data = await _validate_invoice_for_payment(user_id, payload)

    if invoice is None or plan is None:
        logger.warning(f"❌ Pre-checkout rejected for user {user_id}")
        try:
            await query.answer(ok=False, error_message="الفاتورة غير صالحة أو انتهت صلاحيتها.")
        except Exception as e:
            logger.error(f"❌ Error answering pre_checkout: {e}")
        return

    try:
        await query.answer(ok=True)
        logger.info(f"✅ Pre-checkout success: {query.id}")
    except Exception as e:
        logger.error(f"❌ Pre-checkout error: {e}")
        try:
            await query.answer(ok=False, error_message="حدث خطأ، حاول مرة أخرى")
        except:
            pass

async def successful_payment(update, context):
    user_id = update.effective_user.id
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    total_amount = payment.total_amount

    invoice, plan, data = await _validate_invoice_for_payment(user_id, payload)

    if invoice is None or plan is None:
        logger.error(f"❌ Payment with invalid invoice for user {user_id}")
        await safe_send(context.bot, user_id, "❌ حدث خطأ في معالجة الدفع، يرجى التواصل مع الدعم.")
        return

    if plan.get('price') != total_amount:
        logger.error(f"❌ Payment amount mismatch for user {user_id}")
        await safe_send(context.bot, user_id, "❌ المبلغ المدفوع غير مطابق لسعر الخطة، يرجى التواصل مع الدعم.")
        return

    try:
        invoice_number = invoice['number']
        provider_payment_id = payment.provider_payment_charge_id

        await DB.mark_invoice_paid(invoice_number, provider_payment_id)
        await DB.create_subscription(user_id, plan['id'], 'xtr', provider_payment_id)

        await safe_send(context.bot, user_id, f"✅ تم تفعيل اشتراك {plan['name']} بنجاح!")
        logger.info(f"✅ Subscription activated for user {user_id}, plan {plan['id']}")
    except Exception as e:
        logger.error(f"❌ Error processing successful payment: {e}", exc_info=True)
        try:
            await DB.execute("UPDATE invoices SET status='pending' WHERE number=?", (invoice_number,))
        except:
            pass
        await safe_send(context.bot, user_id, "❌ حدث خطأ في معالجة الدفع، يرجى التواصل مع الدعم.")

# =====================================================================
# تشغيل البوت
# =====================================================================

async def main():
    global app

    logger.info(f"🌿 {CONFIG.BOT_NAME}")
    logger.info(f"👨‍💼 المالك: {CONFIG.PRIMARY_OWNER_ID}")

    try:
        CONFIG.validate()
    except ValueError as e:
        logger.error(f"❌ خطأ في الإعدادات: {e}")
        return

    await initialize_db()

    for dev_id in CONFIG.DEVELOPER_IDS:
        await DB.register_user(dev_id)
    await DB.register_user(CONFIG.PRIMARY_OWNER_ID)

    KeyboardFactory.load_config()
    available_langs = TranslationManager.get_available_languages()
    for lang in available_langs:
        TranslationManager.load_translation(lang)
    logger.info(f"✅ تم تحميل {len(available_langs)} لغة")

    port = int(CONFIG.WEB_PORT)
    hostname = (
        os.getenv("RENDER_EXTERNAL_HOSTNAME") or
        os.getenv("RAILWAY_PUBLIC_DOMAIN") or
        os.getenv("HEROKU_APP_NAME")
    )

    app = Application.builder().token(CONFIG.TOKEN).build()
    await app.initialize()

    # ========== تسجيل الأوامر في قائمة تيليجرام ==========
    await app.bot.set_my_commands([
        ("start", "🏠 القائمة الرئيسية"),
        ("help", "📚 المساعدة"),
        ("trial", "🎁 تجربة مجانية"),
        ("subscribe", "💎 اشتراك"),
        ("support", "📞 دعم فني"),
        ("language", "🌐 اللغة"),
        ("developer", "👨‍💻 المطور"),
        ("contests", "🏆 المسابقات"),
        ("stats", "📊 الإحصائيات"),
        ("replies", "💬 الردود التلقائية"),
        ("gift_plans", "🎁 شراء كود هدية"),
        ("redeem_gift", "🎟️ استخدام كود هدية"),
        ("grant", "🎖️ منح اشتراك (للمطور)"),
        ("set_min_interval", "⏱️ تعيين الحد الأدنى للنشر (للمطور)"),
    ])

    # ========== الأوامر العامة ==========
    app.add_handler(CommandHandler("start", CommandHandlers.start))
    app.add_handler(CommandHandler("help", CommandHandlers.help_command))
    app.add_handler(CommandHandler("trial", CommandHandlers.trial))
    app.add_handler(CommandHandler("subscribe", CommandHandlers.subscribe))
    app.add_handler(CommandHandler("support", CommandHandlers.support))
    app.add_handler(CommandHandler("developer", CommandHandlers.developer))
    app.add_handler(CommandHandler("stats", CommandHandlers.stats))
    app.add_handler(CommandHandler("language", CommandHandlers.language))
    app.add_handler(CommandHandler("contests", CommandHandlers.contests))
    app.add_handler(CommandHandler("replies", CommandHandlers.replies_command))

    # ========== أوامر المجموعة ==========
    app.add_handler(CommandHandler("syncgroup", CommandHandlers.syncgroup))
    app.add_handler(CommandHandler("security", CommandHandlers.security))
    app.add_handler(CommandHandler("panel", CommandHandlers.panel))
    app.add_handler(CommandHandler("lock", CommandHandlers.lock))
    app.add_handler(CommandHandler("unlock", CommandHandlers.unlock))

    # ========== أوامر الإشراف ==========
    app.add_handler(CommandHandler("ban", CommandHandlers.ban))
    app.add_handler(CommandHandler("mute", CommandHandlers.mute))
    app.add_handler(CommandHandler("warn", CommandHandlers.warn))
    app.add_handler(CommandHandler("kick", CommandHandlers.kick))
    app.add_handler(CommandHandler("restrict", CommandHandlers.restrict))
    app.add_handler(CommandHandler("unban", CommandHandlers.unban))
    app.add_handler(CommandHandler("pin", CommandHandlers.pin))
    app.add_handler(CommandHandler("promote", CommandHandlers.promote))

    # ========== أوامر المالكين والمشرفين المخفيين ==========
    app.add_handler(CommandHandler("register_hidden_owner", CommandHandlers.register_hidden_owner))
    app.add_handler(CommandHandler("remove_hidden_owner", CommandHandlers.remove_hidden_owner))
    app.add_handler(CommandHandler("add_hidden_admin", CommandHandlers.add_hidden_admin))
    app.add_handler(CommandHandler("remove_hidden_admin", CommandHandlers.remove_hidden_admin))
    app.add_handler(CommandHandler("list_hidden_admins", CommandHandlers.list_hidden_admins))

    # ========== أوامر المطور والهدايا ==========
    app.add_handler(CommandHandler("grant", CommandHandlers.grant))
    app.add_handler(CommandHandler("gift_plans", CommandHandlers.gift_plans))
    app.add_handler(CommandHandler("redeem_gift", CommandHandlers.redeem_gift))
    app.add_handler(CommandHandler("set_min_interval", CommandHandlers.set_min_interval))

    # ========== معالجات الدفع ==========
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    # ========== الكولباك ==========
    app.add_handler(CallbackQueryHandler(CallbackHandlers.handle))

    # ========== الرسائل الخاصة ==========
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL |
         filters.AUDIO | filters.VOICE | filters.ANIMATION | filters.Sticker.ALL) &
        filters.ChatType.PRIVATE & ~filters.COMMAND,
        MessageHandlers.handle_private
    ))

    # ========== رسائل المجموعات ==========
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL |
         filters.AUDIO | filters.VOICE | filters.ANIMATION | filters.Sticker.ALL) &
        filters.ChatType.GROUPS & ~filters.COMMAND,
        MessageHandlers.handle_group
    ))

    # ========== رسائل الخدمة ==========
    app.add_handler(MessageHandler(
        filters.StatusUpdate.ALL & filters.ChatType.GROUPS,
        MessageHandlers.handle_service
    ))

    # ========== طلبات الانضمام ==========
    app.add_handler(ChatJoinRequestHandler(MessageHandlers.handle_join_request))

    # ========== معالج الأخطاء ==========
    app.add_error_handler(ErrorHandler.handle_error)

    # ========== المهام الخلفية مع إعادة تشغيل ==========
    async def run_task_with_retry(task_func, *args, task_name=""):
        while True:
            try:
                await task_func(*args)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"❌ Task {task_name} crashed: {e}", exc_info=True)
                logger.info(f"🔄 إعادة تشغيل المهمة {task_name} بعد 5 ثوانٍ...")
                await asyncio.sleep(5)

    tasks = [
        asyncio.create_task(run_task_with_retry(BackgroundTasks.auto_publish, app.bot, task_name="auto_publish")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.auto_backup, task_name="auto_backup")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.reminders, app.bot, task_name="reminders")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.heartbeat, app.bot, task_name="heartbeat")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.flush_usage_periodically, task_name="flush_usage")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.expire_subscriptions, task_name="expire_subscriptions")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.sync_admins_periodically, app.bot, task_name="sync_admins")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.expire_penalties_periodically, task_name="expire_penalties")),
    ]

    # ========== تشغيل Webhook أو Polling ==========
    try:
        if hostname:
            webhook_url = f"https://{hostname}/{CONFIG.TOKEN}"
            logger.info(f"🔗 Webhook: {webhook_url}")
            await app.bot.delete_webhook(drop_pending_updates=True)
            await app.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=ALLOWED_UPDATES
            )
            logger.info("✅ Webhook تم التعيين")
            runner = await setup_webhook(app, port)
            try:
                await asyncio.Event().wait()
            finally:
                await runner.cleanup()
        else:
            logger.info("⚠️ Polling")
            await app.run_polling(
                drop_pending_updates=True,
                allowed_updates=ALLOWED_UPDATES
            )
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 تم الإيقاف")
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
        traceback.print_exc()
