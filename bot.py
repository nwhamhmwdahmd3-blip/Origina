#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🌿 Relax Manager – البوت الرئيسي
"""

import asyncio
import os
import logging
import traceback

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

app = None


async def pre_checkout(update, context):
    """معالجة ما قبل الدفع (التحقق من صحة الفاتورة)"""
    query = update.pre_checkout_query
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
    
    try:
        import json
        data = json.loads(payload)
        logger.info(f"💰 Payment success: user={user_id}, data={data}")
        
        if data.get('type') == 'gift':
            plan_id = data.get('gift_plan_id')
            plan = await DB.fetchone("SELECT * FROM gift_plans WHERE id=?", (plan_id,))
            if plan:
                plan = dict(plan)
                days = plan['days']
                code = await DB.generate_gift_code(user_id, days, plan_id)
                text = (
                    f"🎁 **تم شراء كود الهدية بنجاح!**\n\n"
                    f"الكود: `{code}`\n"
                    f"المدة: {days} يوم\n\n"
                    f"أرسل هذا الكود لأي شخص ليحصل على اشتراك مجاني!\n"
                    f"يمكنه استخدام الأمر: `/redeem_gift {code}`"
                )
                await safe_send(context.bot, user_id, text)
                
                dev_text = f"💰 تم شراء كود هدية\n👤 المستخدم: `{user_id}`\n📅 المدة: {days} يوم\n🔑 الكود: `{code}`"
                await safe_send(context.bot, CONFIG.PRIMARY_OWNER_ID, dev_text)
            else:
                await safe_send(context.bot, user_id, "❌ حدث خطأ في معالجة الدفع، يرجى التواصل مع الدعم.")
        
        elif data.get('type') == 'subscription':
            plan_id = data.get('plan_id')
            invoice_number = data.get('invoice')
            plan = await DB.get_plan(plan_id)
            if plan:
                await DB.mark_invoice_paid(invoice_number, payment.provider_payment_charge_id)
                await DB.create_subscription(user_id, plan_id, 'xtr', payment.provider_payment_charge_id)
                await safe_send(context.bot, user_id, f"✅ تم تفعيل اشتراك {plan['name']} بنجاح!")
        
        else:
            await safe_send(context.bot, user_id, "✅ تم الدفع بنجاح، شكراً لك!")
            
    except Exception as e:
        logger.error(f"❌ Error in successful_payment: {e}")
        await safe_send(context.bot, user_id, "❌ حدث خطأ في معالجة الدفع، يرجى التواصل مع الدعم.")


async def main():
    global app

    print(f"🌿 {CONFIG.BOT_NAME}")
    print(f"👨‍💼 المالك: {CONFIG.PRIMARY_OWNER_ID}")

    await initialize_db()

    for dev_id in CONFIG.DEVELOPER_IDS:
        await DB.register_user(dev_id)
    await DB.register_user(CONFIG.PRIMARY_OWNER_ID)

    KeyboardFactory.load_config()
    available_langs = TranslationManager.get_available_languages()
    for lang in available_langs:
        TranslationManager.load_translation(lang)
    print(f"✅ تم تحميل {len(available_langs)} لغة")

    port = int(CONFIG.WEB_PORT)
    hostname = (
        os.getenv("RENDER_EXTERNAL_HOSTNAME") or
        os.getenv("RAILWAY_PUBLIC_DOMAIN") or
        os.getenv("HEROKU_APP_NAME")
    )

    app = Application.builder().token(CONFIG.TOKEN).build()
    await app.initialize()

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

    # ========== أوامر الهدايا ==========
    app.add_handler(CommandHandler("gift_plans", CommandHandlers.gift_plans))
    app.add_handler(CommandHandler("redeem_gift", CommandHandlers.redeem_gift))

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

    # ========== المهام الخلفية ==========
    tasks = [
        asyncio.create_task(BackgroundTasks.auto_publish(app.bot)),
        asyncio.create_task(BackgroundTasks.auto_backup()),
        asyncio.create_task(BackgroundTasks.reminders(app.bot)),
        asyncio.create_task(BackgroundTasks.heartbeat(app.bot)),
        asyncio.create_task(BackgroundTasks.flush_usage_periodically()),
        asyncio.create_task(BackgroundTasks.expire_subscriptions()),
        asyncio.create_task(BackgroundTasks.sync_admins_periodically(app.bot)),
    ]

    if hostname:
        webhook_url = f"https://{hostname}/{CONFIG.TOKEN}"
        print(f"🔗 Webhook: {webhook_url}")
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
        print("✅ Webhook تم التعيين")
        runner = await setup_webhook(app, port)
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()
    else:
        print("⚠️ Polling")
        await app.run_polling(drop_pending_updates=True)

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 تم الإيقاف")
    except Exception as e:
        print(f"❌ خطأ: {e}")
        traceback.print_exc()
