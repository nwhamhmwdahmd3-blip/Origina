#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🌿 Relax Manager – البوت الرئيسي (نسخة نهائية كاملة)
- جميع الأوامر مسجلة
- جميع المعالجات (أزرار، رسائل، دفع) مسجلة
- نظام النشر التلقائي
- نظام الإعلانات المدفوعة
- نظام قنوات الإعلانات المنفصل
- دعم Webhook و Polling
- دعم Termux و Render
"""

import asyncio
import os
import logging
import traceback
import json
import time

from telegram import (
    BotCommandScopeAllPrivateChats,
    BotCommandScopeAllGroupChats,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ChatJoinRequestHandler,
    PreCheckoutQueryHandler,
    filters,
)

from config import CONFIG, PATHS
from database import DB, initialize_db
from handlers import CommandHandlers, CallbackHandlers, MessageHandlers
from utils import (
    TranslationManager,
    KeyboardFactory,
    BackgroundTasks,
    ErrorHandler,
    setup_webhook,
    safe_send,
)
from cache import cache_cleanup_task

# ==== نظام الإعلانات المدفوعة ====
from advertising import AdvertisingDB, register_advertising_handlers

# ==== نظام قنوات الإعلانات المنفصل ====
from ad_channels import (
    AdChannelHandlers,
    handle_ad_channel_callback,
    handle_ad_channel_text_message,
    AdChannelDB,  # تمت إضافة هذا الاستيراد
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ALLOWED_UPDATES = [
    "message",
    "callback_query",
    "chat_join_request",
    "pre_checkout_query",
]


async def _validate_invoice_for_payment(user_id: int, payload: str):
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logger.error(f"❌ Invalid JSON payload: {payload}")
        return None, None, None

    invoice_number = data.get("invoice")
    if not invoice_number:
        return None, None, None

    invoice = await DB.get_invoice(invoice_number)
    if not invoice or invoice["user_id"] != user_id or invoice["status"] != "pending":
        logger.warning(f"❌ Invoice invalid for user {user_id}")
        return None, None, None

    payment_type = data.get("type")
    if payment_type not in ("subscription", "gift"):
        logger.warning(f"❌ Unknown payment type: {payment_type}")
        return None, None, None

    plan_id = data.get("plan_id") or data.get("gift_plan_id")
    plan = (
        await DB.get_plan(plan_id)
        if payment_type == "subscription"
        else await DB.get_gift_plan(plan_id)
    )
    if not plan:
        logger.warning(f"❌ Plan not found: {plan_id}")
        return None, None, None

    return invoice, plan, data


async def pre_checkout(update, context):
    query = update.pre_checkout_query
    user_id = query.from_user.id
    payload = query.invoice_payload

    invoice, plan, _ = await _validate_invoice_for_payment(user_id, payload)

    if invoice is None or plan is None:
        try:
            await query.answer(ok=False, error_message="الفاتورة غير صالحة أو منتهية.")
        except Exception as e:
            logger.error(f"❌ Failed to answer pre-checkout rejection: {e}")
        return

    try:
        await query.answer(ok=True)
    except Exception as e:
        logger.error(f"❌ Failed to answer pre-checkout success: {e}")


async def successful_payment(update, context):
    user_id = update.effective_user.id
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    total_amount = payment.total_amount

    invoice, plan, data = await _validate_invoice_for_payment(user_id, payload)

    if invoice is None or plan is None:
        await safe_send(context.bot, user_id, "❌ حدث خطأ في معالجة الدفع.")
        return

    if plan.get("price", 0) > 0 and plan.get("price") != total_amount:
        await safe_send(context.bot, user_id, "❌ المبلغ المدفوع غير مطابق.")
        return

    payment_type = data.get("type")
    payment_id = payment.telegram_payment_charge_id or payment.provider_payment_charge_id

    if payment_type == "subscription":
        success = await DB.activate_subscription_with_payment(
            user_id=user_id,
            invoice_number=invoice["number"],
            payment_id=payment_id,
            plan_id=plan["id"],
        )
        if success:
            await DB.add_payment_log(user_id, "xtr", "subscription_paid", {"invoice": invoice["number"]})
            await safe_send(context.bot, user_id, f"✅ تم تفعيل اشتراك {plan['name']} بنجاح!")
        else:
            await safe_send(context.bot, user_id, "❌ حدث خطأ في معالجة الدفع.")

    elif payment_type == "gift":
        code = await DB.create_gift_code(plan_id=plan["id"], creator_id=user_id)
        if code:
            await DB.mark_invoice_paid(invoice["number"], payment_id)
            await safe_send(
                context.bot,
                user_id,
                f"🎉 تم شراء كود الهدية!\n🎁 الكود: `{code}`\n📅 المدة: {plan['days']} يوم",
            )
        else:
            await safe_send(context.bot, user_id, "❌ حدث خطأ في توليد كود الهدية.")


async def main():
    try:
        CONFIG.validate()
    except ValueError as e:
        logger.error(f"❌ {e}")
        raise SystemExit(1)

    logger.info(f"🌿 {CONFIG.BOT_NAME}")
    logger.info(f"👨‍💼 المالك: {CONFIG.PRIMARY_OWNER_ID}")

    # تهيئة قاعدة البيانات
    await initialize_db()

    # تهيئة جداول الإعلانات المدفوعة
    await AdvertisingDB.init_tables()

    # تهيئة جداول قنوات الإعلانات (تمت إضافتها)
    await AdChannelDB.init_tables()

    # تسجيل المطورين
    for dev_id in CONFIG.DEVELOPER_IDS:
        try:
            await DB.register_user(dev_id)
        except Exception as e:
            logger.error(f"❌ Failed to register developer {dev_id}: {e}")
    try:
        await DB.register_user(CONFIG.PRIMARY_OWNER_ID)
    except Exception as e:
        logger.error(f"❌ Failed to register owner: {e}")

    # تحميل الإعدادات (تم إضافة await)
    await KeyboardFactory.load_config()
    available_langs = TranslationManager.get_available_languages()
    for lang in available_langs:
        TranslationManager.load_translation(lang)
    logger.info(f"✅ تم تحميل {len(available_langs)} لغة")

    # المنفذ
    port = int(os.getenv("PORT", CONFIG.WEB_PORT))

    # Webhook hostname
    hostname = (
        os.getenv("RENDER_EXTERNAL_HOSTNAME")
        or os.getenv("RENDER_EXTERNAL_URL")
        or os.getenv("RAILWAY_PUBLIC_DOMAIN")
        or os.getenv("HEROKU_APP_NAME")
        or os.getenv("WEBHOOK_URL")
    )

    # بناء التطبيق
    app = (
        Application.builder()
        .token(CONFIG.TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )
    app.bot_data["start_time"] = time.monotonic()
    await app.initialize()

    # ========== قائمة الأوامر الخاصة ==========
    private_commands = [
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
        ("grant", "🎁 منح اشتراك يدوي"),
        ("set_min_interval", "⏱️ تعيين الحد الأدنى للفاصل"),
        ("gift_plans", "🎁 خطط الهدايا"),
        ("redeem_gift", "🎟️ استرداد كود هدية"),
        ("mood", "🎭 تحليل المشاعر"),
        ("admin", "👑 لوحة الأدمن"),
        ("broadcast", "📨 بث جماعي"),
        ("set_force", "🔒 تعيين الاشتراك الإجباري"),
        ("set_update_ch", "📢 تعيين قناة التحديثات"),
        ("set_log_ch", "📋 تعيين قناة السجلات"),
        ("add_admin", "👑 إضافة مشرف"),
        ("remove_admin", "🗑️ إزالة مشرف"),
        ("export_replies", "📤 تصدير الردود"),
        ("import_replies", "📥 استيراد الردود"),
        ("backup", "💾 نسخ احتياطي"),
        ("restore", "🔄 عرض النسخ"),
        ("auto_publish", "📤 تبديل النشر التلقائي"),
        ("auto_recycle", "♻️ تبديل التدوير"),
        ("channels", "📡 قنواتي"),
        ("posts", "📋 منشوراتي"),
        # ==== أوامر الإعلانات ====
        ("advertise", "📢 عرض القنوات للإعلان"),
        ("enable_ads", "💼 تفعيل الإعلانات لقناتك"),
        ("disable_ads", "🚫 إيقاف الإعلانات"),
        # ==== أوامر قنوات الإعلانات المنفصلة ====
        ("adchannels", "📢 الإعلانات"),
        ("add_ad_channel", "➕ إضافة قناة إعلانات"),
        ("my_ad_channels", "📋 قنوات الإعلانات"),
        ("set_ad_price", "💰 تحديد سعر الإعلان"),
        ("enable_ad_channel", "✅ تفعيل قناة إعلانات"),
        ("disable_ad_channel", "❌ تعطيل قناة إعلانات"),
        ("remove_ad_channel", "🗑️ حذف قناة إعلانات"),
    ]

    group_commands = [
        ("syncgroup", "🔗 تفعيل المجموعة"),
        ("security", "🛡️ إعدادات الأمان"),
        ("panel", "📋 لوحة التحكم"),
        ("lock", "🔒 قفل المجموعة"),
        ("unlock", "🔓 فتح المجموعة"),
        ("ban", "🚫 حظر مستخدم"),
        ("mute", "🔇 كتم مستخدم"),
        ("warn", "⚠️ تحذير مستخدم"),
        ("kick", "👢 طرد مستخدم"),
        ("restrict", "🔒 تقييد مستخدم"),
        ("unban", "🔓 إلغاء حظر"),
        ("pin", "📌 تثبيت رسالة"),
    ]

    await app.bot.set_my_commands(private_commands, scope=BotCommandScopeAllPrivateChats())
    await app.bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())

    # ========== تسجيل الأوامر الأساسية ==========
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
    app.add_handler(CommandHandler("grant", CommandHandlers.grant))
    app.add_handler(CommandHandler("set_min_interval", CommandHandlers.set_min_interval))
    app.add_handler(CommandHandler("gift_plans", CommandHandlers.gift_plans))
    app.add_handler(CommandHandler("redeem_gift", CommandHandlers.redeem_gift))

    # ========== أوامر المجموعات ==========
    app.add_handler(CommandHandler("syncgroup", CommandHandlers.syncgroup))
    app.add_handler(CommandHandler("security", CommandHandlers.security))
    app.add_handler(CommandHandler("panel", CommandHandlers.panel))
    app.add_handler(CommandHandler("lock", CommandHandlers.lock))
    app.add_handler(CommandHandler("unlock", CommandHandlers.unlock))
    app.add_handler(CommandHandler("ban", CommandHandlers.ban))
    app.add_handler(CommandHandler("mute", CommandHandlers.mute))
    app.add_handler(CommandHandler("warn", CommandHandlers.warn))
    app.add_handler(CommandHandler("kick", CommandHandlers.kick))
    app.add_handler(CommandHandler("restrict", CommandHandlers.restrict))
    app.add_handler(CommandHandler("unban", CommandHandlers.unban))
    app.add_handler(CommandHandler("pin", CommandHandlers.pin))

    # ========== أوامر المشرفين المخفيين ==========
    app.add_handler(CommandHandler("register_hidden_owner", CommandHandlers.register_hidden_owner))
    app.add_handler(CommandHandler("remove_hidden_owner", CommandHandlers.remove_hidden_owner))
    app.add_handler(CommandHandler("add_hidden_admin", CommandHandlers.add_hidden_admin))
    app.add_handler(CommandHandler("remove_hidden_admin", CommandHandlers.remove_hidden_admin))
    app.add_handler(CommandHandler("list_hidden_admins", CommandHandlers.list_hidden_admins))

    # ========== الأوامر الإدارية ==========
    app.add_handler(CommandHandler("mood", CommandHandlers.mood))
    app.add_handler(CommandHandler("admin", CommandHandlers.admin))
    app.add_handler(CommandHandler("broadcast", CommandHandlers.broadcast))
    app.add_handler(CommandHandler("set_force", CommandHandlers.set_force))
    app.add_handler(CommandHandler("set_update_ch", CommandHandlers.set_update_ch))
    app.add_handler(CommandHandler("set_log_ch", CommandHandlers.set_log_ch))
    app.add_handler(CommandHandler("add_admin", CommandHandlers.add_admin))
    app.add_handler(CommandHandler("remove_admin", CommandHandlers.remove_admin))
    app.add_handler(CommandHandler("export_replies", CommandHandlers.export_replies))
    app.add_handler(CommandHandler("import_replies", CommandHandlers.import_replies))
    app.add_handler(CommandHandler("backup", CommandHandlers.backup))
    app.add_handler(CommandHandler("restore", CommandHandlers.restore))
    app.add_handler(CommandHandler("auto_publish", CommandHandlers.auto_publish))
    app.add_handler(CommandHandler("auto_recycle", CommandHandlers.auto_recycle))
    app.add_handler(CommandHandler("channels", CommandHandlers.channels))
    app.add_handler(CommandHandler("posts", CommandHandlers.posts))

    # ========== تسجيل أوامر قنوات الإعلانات ==========
    app.add_handler(CommandHandler("adchannels", AdChannelHandlers.ad_channels_menu))
    app.add_handler(CommandHandler("add_ad_channel", AdChannelHandlers.add_ad_channel))
    app.add_handler(CommandHandler("my_ad_channels", AdChannelHandlers.my_ad_channels))
    app.add_handler(CommandHandler("set_ad_price", AdChannelHandlers.set_ad_price))
    app.add_handler(CommandHandler("enable_ad_channel", AdChannelHandlers.enable_ad_channel))
    app.add_handler(CommandHandler("disable_ad_channel", AdChannelHandlers.disable_ad_channel))
    app.add_handler(CommandHandler("remove_ad_channel", AdChannelHandlers.remove_ad_channel))

    # ========== تسجيل معالجات أزرار ورسائل قنوات الإعلانات ==========
    app.add_handler(CallbackQueryHandler(handle_ad_channel_callback, pattern=r"^ad_ch_"))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_ad_channel_text_message
    ))

    # ========== تسجيل معالجات الإعلانات المدفوعة ==========
    register_advertising_handlers(app)

    # ========== معالجات الدفع ==========
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    # ========== المعالج العام للأزرار (يجب أن يكون آخر معالج أزرار) ==========
    app.add_handler(CallbackQueryHandler(CallbackHandlers.handle))

    # ========== معالجات الرسائل ==========
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL |
         filters.AUDIO | filters.VOICE | filters.ANIMATION | filters.Sticker.ALL |
         filters.VIDEO_NOTE) & filters.ChatType.PRIVATE & ~filters.COMMAND,
        MessageHandlers.handle_private
    ))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL |
         filters.AUDIO | filters.VOICE | filters.ANIMATION | filters.Sticker.ALL |
         filters.VIDEO_NOTE) & filters.ChatType.GROUPS & ~filters.COMMAND,
        MessageHandlers.handle_group
    ))
    app.add_handler(MessageHandler(
        filters.StatusUpdate.ALL & filters.ChatType.GROUPS,
        MessageHandlers.handle_service
    ))
    app.add_handler(ChatJoinRequestHandler(MessageHandlers.handle_join_request))
    app.add_error_handler(ErrorHandler.handle_error)

    # ========== المهام الخلفية ==========
    async def run_task_with_retry(task_func, *args, task_name=""):
        while True:
            try:
                await task_func(*args)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"❌ Task {task_name} crashed: {e}")
                await asyncio.sleep(5)

    async def cleanup_locks():
        while True:
            await DB.cleanup_user_locks(max_idle_seconds=3600)
            await asyncio.sleep(3600)

    tasks = [
        asyncio.create_task(run_task_with_retry(BackgroundTasks.auto_publish, app.bot, task_name="auto_publish")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.auto_backup, task_name="auto_backup")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.reminders, app.bot, task_name="reminders")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.heartbeat, app.bot, task_name="heartbeat")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.flush_usage_periodically, task_name="flush_usage")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.expire_subscriptions, task_name="expire_subscriptions")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.sync_admins_periodically, app.bot, task_name="sync_admins")),
        asyncio.create_task(run_task_with_retry(BackgroundTasks.expire_penalties_periodically, task_name="expire_penalties")),
        asyncio.create_task(run_task_with_retry(cache_cleanup_task, task_name="cache_cleanup")),
        asyncio.create_task(run_task_with_retry(cleanup_locks, task_name="cleanup_locks")),
    ]

    # ========== بدء التشغيل ==========
    try:
        if hostname:
            webhook_url = f"https://{hostname}/{CONFIG.TOKEN}"
            await app.bot.delete_webhook(drop_pending_updates=True)
            await app.bot.set_webhook(url=webhook_url, drop_pending_updates=True, allowed_updates=ALLOWED_UPDATES)
            runner = await setup_webhook(app, port)
            await asyncio.Event().wait()
        else:
            await app.start()
            await app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=ALLOWED_UPDATES,
                poll_interval=1.0,
                timeout=30,
                read_timeout=30,
                connect_timeout=30,
                write_timeout=30
            )
            await asyncio.Event().wait()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 تم الإيقاف")
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
        traceback.print_exc()
