#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🌿 Relax Manager – البوت الرئيسي (نسخة مصححة ومحسّنة)
- إصلاحات أمنية في معالجة الدفع (الاشتراكات والهدايا)
- تحسينات في المعاملات والتحقق من الفواتير
- تحديد allowed_updates
- إعادة تشغيل المهام الخلفية عند الفشل
- تشغيل مهمة expire_penalties_periodically
- معالجة أكواد الهدايا بشكل صحيح
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

# التحديثات المسموحة للويب هوك / البولينج
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
    """
    التحقق من صحة الفاتورة ومطابقتها للمستخدم قبل معالجة الدفع.
    تُرجع (invoice, plan, data) إذا كانت صالحة، وإلا (None, None, None)
    """
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

    # التحقق من نوع العملية
    payment_type = data.get('type')
    if payment_type not in ('subscription', 'gift'):
        return None, None, None

    plan_id = data.get('plan_id') or data.get('gift_plan_id')
    plan = await DB.get_plan(plan_id) if payment_type == 'subscription' else await DB.get_gift_plan(plan_id)
    if not plan:
        return None, None, None

    return invoice, plan, data


# =====================================================================
# معالجات الدفع
# =====================================================================

async def pre_checkout(update, context):
    """معالجة ما قبل الدفع (التحقق من صحة الفاتورة)"""
    query = update.pre_checkout_query
    user_id = query.from_user.id
    payload = query.invoice_payload

    invoice, plan, data = await _validate_invoice_for_payment(user_id, payload)

    if invoice is None or plan is None:
        logger.warning(f"❌ Pre-checkout rejected for user {user_id}, payload: {payload}")
        try:
            await query.answer(ok=False, error_message="الفاتورة غير صالحة أو انتهت صلاحيتها.")
        except Exception as e:
            logger.error(f"❌ Error answering pre_checkout: {e}")
        return

    # التحقق من تطابق المبلغ (إذا كان total_amount متاحًا)
    if hasattr(query, 'total_amount'):
        expected_amount = plan.get('price')
        if expected_amount is not None and query.total_amount != expected_amount:
            try:
                await query.answer(ok=False, error_message="المبلغ غير مطابق لسعر الخطة.")
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
    """معالجة الدفع الناجح"""
    user_id = update.effective_user.id
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    total_amount = payment.total_amount
    telegram_payment_charge_id = payment.telegram_payment_charge_id
    provider_payment_charge_id = payment.provider_payment_charge_id

    invoice, plan, data = await _validate_invoice_for_payment(user_id, payload)

    if invoice is None or plan is None:
        logger.error(f"❌ Payment with invalid invoice for user {user_id}, payload: {payload}")
        await safe_send(context.bot, user_id, "❌ حدث خطأ في معالجة الدفع، يرجى التواصل مع الدعم.")
        return

    # التحقق من تطابق المبلغ المدفوع مع سعر الخطة
    if plan.get('price') != total_amount:
        logger.error(f"❌ Payment amount mismatch for user {user_id}: paid={total_amount}, expected={plan.get('price')}")
        await safe_send(context.bot, user_id, "❌ المبلغ المدفوع غير مطابق لسعر الخطة، يرجى التواصل مع الدعم.")
        return

    payment_type = data.get('type')
    payment_id = telegram_payment_charge_id or provider_payment_charge_id

    if payment_type == 'subscription':
        # تفعيل الاشتراك بشكل ذري
        success = await DB.activate_subscription_with_payment(
            user_id=user_id,
            invoice_number=invoice['number'],
            payment_id=payment_id,
            plan_id=plan['id']
        )
        if success:
            await DB.add_payment_log(user_id, 'xtr', 'subscription_paid', {'invoice': invoice['number'], 'plan_id': plan['id'], 'amount': total_amount})
            await safe_send(context.bot, user_id, f"✅ تم تفعيل اشتراك {plan['name']} بنجاح!")
            logger.info(f"✅ Subscription activated for user {user_id}, plan {plan['id']}, invoice {invoice['number']}")
        else:
            # محاولة الرجوع عن تعليم الفاتورة إذا فشلت العملية الذرية
            await DB.execute("UPDATE invoices SET status='pending' WHERE number=?", (invoice['number'],))
            await safe_send(context.bot, user_id, "❌ حدث خطأ في معالجة الدفع، يرجى التواصل مع الدعم.")
            logger.error(f"❌ Failed to activate subscription for user {user_id}, invoice {invoice['number']}")

    elif payment_type == 'gift':
        # توليد كود هدية وإرساله
        code = await DB.create_gift_code(plan_id=plan['id'], creator_id=user_id)
        if code:
            # تعليم الفاتورة مدفوعة
            await DB.mark_invoice_paid(invoice['number'], payment_id)
            await DB.add_payment_log(user_id, 'xtr', 'gift_paid', {'invoice': invoice['number'], 'gift_plan_id': plan['id'], 'amount': total_amount})
            await safe_send(
                context.bot,
                user_id,
                f"🎉 **تم شراء كود الهدية بنجاح!**\n\n"
                f"🎁 الكود: `{code}`\n"
                f"📅 المدة: {plan['days']} يوم\n\n"
                f"يمكنك إرسال هذا الكود لأي شخص لاستخدامه."
            )
            logger.info(f"✅ Gift code {code} created for user {user_id}, invoice {invoice['number']}")
        else:
            await safe_send(context.bot, user_id, "❌ حدث خطأ في توليد كود الهدية، يرجى التواصل مع الدعم.")
            logger.error(f"❌ Failed to create gift code for user {user_id}, invoice {invoice['number']}")

    else:
        logger.error(f"❌ Unknown payment type: {payment_type}")
        await safe_send(context.bot, user_id, "❌ نوع دفع غير معروف.")


# =====================================================================
# تشغيل البوت
# =====================================================================

async def main():
    global app

    logger.info(f"🌿 {CONFIG.BOT_NAME}")
    logger.info(f"👨‍💼 المالك: {CONFIG.PRIMARY_OWNER_ID}")

    await initialize_db()

    # تسجيل المطورين
    for dev_id in CONFIG.DEVELOPER_IDS:
        await DB.register_user(dev_id)
    await DB.register_user(CONFIG.PRIMARY_OWNER_ID)

    # تحميل الإعدادات
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

    # بناء التطبيق
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
    ])

    # ========== الأوامر الأساسية ==========
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

    # ========== أوامر المالكين والمشرفين المخفيين ==========
    app.add_handler(CommandHandler("register_hidden_owner", CommandHandlers.register_hidden_owner))
    app.add_handler(CommandHandler("remove_hidden_owner", CommandHandlers.remove_hidden_owner))
    app.add_handler(CommandHandler("add_hidden_admin", CommandHandlers.add_hidden_admin))
    app.add_handler(CommandHandler("remove_hidden_admin", CommandHandlers.remove_hidden_admin))
    app.add_handler(CommandHandler("list_hidden_admins", CommandHandlers.list_hidden_admins))

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

    # ========== المهام الخلفية (مع إعادة تشغيل عند الفشل) ==========
    async def run_task_with_retry(task_func, *args, task_name=""):
        """تشغيل مهمة خلفية مع إعادة المحاولة عند حدوث استثناء غير متوقع."""
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
        # إلغاء المهام
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
