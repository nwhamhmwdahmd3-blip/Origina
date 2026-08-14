#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🌿 Relax Manager – البوت الرئيسي v9.0.0
=========================================
يستدعي المعالجات من ملف handlers.py
"""

import asyncio
import os
import logging
import traceback

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
from aiohttp import web

from config import CONFIG, PATHS
from database import DB, initialize_db
from handlers import CommandHandlers, CallbackHandlers, MessageHandlers
from utils import TranslationManager, KeyboardFactory, BackgroundTasks, ErrorHandler, setup_webhook

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = None  # <---- متغير عام

async def main():
    global app  # <---- أعلن أن app عام

    print(f"🌿 {CONFIG.BOT_NAME} v9.0.0")
    print(f"👨‍💼 المالك الأساسي: {CONFIG.PRIMARY_OWNER_ID}")
    print(f"👨‍💻 عدد المطورين: {len(CONFIG.DEVELOPER_IDS)}")

    # تهيئة قاعدة البيانات
    await initialize_db()

    # تسجيل المطورين
    for dev_id in CONFIG.DEVELOPER_IDS:
        await DB.register_user(dev_id)

    # تحميل الأزرار والترجمات
    KeyboardFactory.load_config()
    available_langs = TranslationManager.get_available_languages()
    for lang in available_langs:
        TranslationManager.load_translation(lang)
    print(f"✅ تم تحميل {len(available_langs)} لغة")

    # إعدادات Webhook
    port = int(CONFIG.WEB_PORT)
    hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("HEROKU_APP_NAME")

    # إنشاء التطبيق
    app = Application.builder().token(CONFIG.TOKEN).build()  # <---- تعيين app
    await app.initialize()

    # إضافة المعالجات
    app.add_handler(CommandHandler("start", CommandHandlers.start))
    app.add_handler(CommandHandler("help", CommandHandlers.help_command))
    app.add_handler(CommandHandler("syncgroup", CommandHandlers.syncgroup))
    app.add_handler(CommandHandler("security", CommandHandlers.security))
    app.add_handler(CommandHandler("panel", CommandHandlers.panel))
    app.add_handler(CommandHandler("lock", CommandHandlers.lock))
    app.add_handler(CommandHandler("unlock", CommandHandlers.unlock))
    app.add_handler(CommandHandler("stats", CommandHandlers.stats))
    app.add_handler(CommandHandler("contests", CommandHandlers.contests))
    app.add_handler(CommandHandler("support", CommandHandlers.support))
    app.add_handler(CommandHandler("trial", CommandHandlers.trial))
    app.add_handler(CommandHandler("subscribe", CommandHandlers.subscribe))
    app.add_handler(CommandHandler("developer", CommandHandlers.developer))
    app.add_handler(CommandHandler("language", CommandHandlers.language))
    app.add_handler(CommandHandler("replies", CommandHandlers.replies_command))

    # أوامر الإدارة
    app.add_handler(CommandHandler("ban", CommandHandlers.ban))
    app.add_handler(CommandHandler("mute", CommandHandlers.mute))
    app.add_handler(CommandHandler("warn", CommandHandlers.warn))
    app.add_handler(CommandHandler("kick", CommandHandlers.kick))
    app.add_handler(CommandHandler("restrict", CommandHandlers.restrict))
    app.add_handler(CommandHandler("unban", CommandHandlers.unban))
    app.add_handler(CommandHandler("pin", CommandHandlers.pin))

    app.add_handler(CallbackQueryHandler(CallbackHandlers.handle))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, MessageHandlers.handle_private))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, MessageHandlers.handle_group))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.AUDIO | filters.VOICE | filters.ANIMATION, MessageHandlers.handle_private))

    # معالج الأخطاء
    app.add_error_handler(ErrorHandler.handle_error)

    # المهام الخلفية
    tasks = [
        asyncio.create_task(BackgroundTasks.auto_publish(app.bot)),
        asyncio.create_task(BackgroundTasks.auto_backup()),
        asyncio.create_task(BackgroundTasks.reminders(app.bot)),
        asyncio.create_task(BackgroundTasks.heartbeat(app.bot)),
        asyncio.create_task(BackgroundTasks.flush_usage_periodically()),
        asyncio.create_task(BackgroundTasks.flush_sentiment_periodically()),
        asyncio.create_task(BackgroundTasks.expire_subscriptions()),
    ]

    if hostname:
        webhook_url = f"https://{hostname}/{CONFIG.TOKEN}"
        print(f"🔗 تعيين Webhook إلى: {webhook_url}")
        await app.bot.delete_webhook(drop_pending_updates=True)
        await app.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
        print("✅ تم تعيين Webhook بنجاح")
        runner = await setup_webhook(app, port)
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()
    else:
        print("⚠️ لا يوجد اسم نطاق، سيتم استخدام Polling")
        await app.run_polling(drop_pending_updates=True)

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 تم إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")
        traceback.print_exc()
