#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
advertising.py - نظام الإعلانات المدفوعة
=========================================
- يمكن لأصحاب القنوات تفعيل استقبال الإعلانات وتحديد السعر.
- يمكن للمعلنين تصفح القنوات المتاحة ودفع Stars لنشر إعلاناتهم.
- بعد الدفع الناجح يتم نشر الإعلان تلقائيًا في القناة المستهدفة.
- توزيع الأرباح: 80% لصاحب القناة، 20% للمنصة.

طريقة الاستخدام:
- صاحب القناة: /enable_ads <السعر> لتفعيل الإعلانات في قناته.
- صاحب القناة: /disable_ads لإيقاف استقبال الإعلانات.
- المعلن: /advertise لعرض القنوات المتاحة.
"""

import asyncio
import logging
import json
from typing import Optional, Dict, Any, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import BadRequest, Forbidden

from config import CONFIG
from database import DB
from utils import safe_send, StateManager, UserState

logger = logging.getLogger(__name__)

# ========== ثوابت ==========
AD_CALLBACKS = {
    "select": "ad_select",
    "cancel": "ad_cancel",
}

# نسبة المنصة من كل إعلان
PLATFORM_SHARE_PERCENT = 20
OWNER_SHARE_PERCENT = 80

# ========== دوال قاعدة البيانات ==========

class AdvertisingDB:
    """تعامل مع قاعدة البيانات الخاصة بالإعلانات"""

    @staticmethod
    async def init_tables():
        """إنشاء الجداول إذا لم تكن موجودة"""
        await DB.execute("""
            CREATE TABLE IF NOT EXISTS ad_spots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_db_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL,
                price INTEGER NOT NULL DEFAULT 100,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (channel_db_id) REFERENCES user_channels(id) ON DELETE CASCADE,
                FOREIGN KEY (owner_id) REFERENCES users(user_id)
            )
        """)

        await DB.execute("""
            CREATE TABLE IF NOT EXISTS ad_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ad_spot_id INTEGER NOT NULL,
                advertiser_id INTEGER NOT NULL,
                ad_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                invoice_number TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                paid_at TEXT,
                published_at TEXT,
                platform_share INTEGER DEFAULT 0,
                owner_share INTEGER DEFAULT 0,
                FOREIGN KEY (ad_spot_id) REFERENCES ad_spots(id) ON DELETE CASCADE,
                FOREIGN KEY (advertiser_id) REFERENCES users(user_id)
            )
        """)
        await DB.execute("CREATE INDEX IF NOT EXISTS idx_ad_spots_status ON ad_spots(status)")
        await DB.execute("CREATE INDEX IF NOT EXISTS idx_ad_orders_status ON ad_orders(status)")
        logger.info("✅ تم تهيئة جداول الإعلانات")

    @staticmethod
    async def enable_ad_spot(channel_db_id: int, owner_id: int, price: int) -> bool:
        if not await DB.is_channel_owner(owner_id, channel_db_id):
            return False
        await DB.execute("DELETE FROM ad_spots WHERE channel_db_id=?", (channel_db_id,))
        await DB.execute(
            "INSERT INTO ad_spots (channel_db_id, owner_id, price, status) VALUES (?,?,?,?)",
            (channel_db_id, owner_id, price, 'active')
        )
        return True

    @staticmethod
    async def disable_ad_spot(channel_db_id: int, owner_id: int) -> bool:
        if not await DB.is_channel_owner(owner_id, channel_db_id):
            return False
        await DB.execute("UPDATE ad_spots SET status='paused' WHERE channel_db_id=? AND owner_id=?", (channel_db_id, owner_id))
        return True

    @staticmethod
    async def get_active_ad_spots() -> List[Dict[str, Any]]:
        rows = await DB.fetchall("""
            SELECT s.id, s.channel_db_id, s.owner_id, s.price, c.channel_name, c.channel_id AS tele_channel_id
            FROM ad_spots s
            JOIN user_channels c ON s.channel_db_id = c.id
            WHERE s.status='active'
            ORDER BY s.price ASC
        """)
        return rows or []

    @staticmethod
    async def get_ad_spot_by_id(spot_id: int) -> Optional[Dict[str, Any]]:
        return await DB.fetchone("""
            SELECT s.id, s.channel_db_id, s.owner_id, s.price, s.status, c.channel_name, c.channel_id AS tele_channel_id
            FROM ad_spots s
            JOIN user_channels c ON s.channel_db_id = c.id
            WHERE s.id=?
        """, (spot_id,))

    @staticmethod
    async def create_ad_order(ad_spot_id: int, advertiser_id: int, ad_text: str) -> Optional[int]:
        spot = await AdvertisingDB.get_ad_spot_by_id(ad_spot_id)
        if not spot or spot['status'] != 'active':
            return None
        await DB.execute(
            "INSERT INTO ad_orders (ad_spot_id, advertiser_id, ad_text, status) VALUES (?,?,?,?)",
            (ad_spot_id, advertiser_id, ad_text, 'pending')
        )
        return await DB.fetchval("SELECT last_insert_rowid()")

    @staticmethod
    async def mark_order_paid(order_id: int, invoice_number: str) -> bool:
        await DB.execute(
            "UPDATE ad_orders SET status='paid', invoice_number=?, paid_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
            (invoice_number, order_id)
        )
        return True

    @staticmethod
    async def mark_order_published(order_id: int) -> bool:
        await DB.execute(
            "UPDATE ad_orders SET status='published', published_at=CURRENT_TIMESTAMP WHERE id=? AND status='paid'",
            (order_id,)
        )
        return True

    @staticmethod
    async def update_order_shares(order_id: int, platform_share: int, owner_share: int) -> bool:
        await DB.execute(
            "UPDATE ad_orders SET platform_share=?, owner_share=? WHERE id=?",
            (platform_share, owner_share, order_id)
        )
        return True

    @staticmethod
    async def get_order_by_id(order_id: int) -> Optional[Dict[str, Any]]:
        return await DB.fetchone("""
            SELECT o.*, s.channel_db_id, s.owner_id, s.price, c.channel_name, c.channel_id AS tele_channel_id
            FROM ad_orders o
            JOIN ad_spots s ON o.ad_spot_id = s.id
            JOIN user_channels c ON s.channel_db_id = c.id
            WHERE o.id=?
        """, (order_id,))


# ========== أوامر البوت ==========

class AdvertisingHandlers:

    @staticmethod
    async def enable_ads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        args = context.args or []

        if not args:
            await safe_send(context.bot, user_id, "❌ استخدم: /enable_ads <السعر بالنجوم>")
            return
        try:
            price = int(args[0])
            if price <= 0:
                raise ValueError
        except:
            await safe_send(context.bot, user_id, "❌ السعر يجب أن يكون رقمًا موجبًا")
            return

        active_channel_db_id = await DB.get_active_channel(user_id)
        if not active_channel_db_id:
            await safe_send(context.bot, user_id, "❌ لا توجد قناة نشطة. اختر قناة أولاً من /channels")
            return

        success = await AdvertisingDB.enable_ad_spot(active_channel_db_id, user_id, price)
        if success:
            await safe_send(context.bot, user_id, f"✅ تم تفعيل الإعلانات في قناتك بسعر {price} ⭐")
        else:
            await safe_send(context.bot, user_id, "❌ لا يمكنك تفعيل الإعلانات. تأكد من أنك تملك القناة.")

    @staticmethod
    async def disable_ads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        active_channel_db_id = await DB.get_active_channel(user_id)
        if not active_channel_db_id:
            await safe_send(context.bot, user_id, "❌ لا توجد قناة نشطة.")
            return
        success = await AdvertisingDB.disable_ad_spot(active_channel_db_id, user_id)
        if success:
            await safe_send(context.bot, user_id, "✅ تم إيقاف استقبال الإعلانات في قناتك.")
        else:
            await safe_send(context.bot, user_id, "❌ لا يمكنك إيقاف الإعلانات.")

    @staticmethod
    async def advertise(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        spots = await AdvertisingDB.get_active_ad_spots()
        if not spots:
            await safe_send(context.bot, user_id, "📭 لا توجد قنوات متاحة للإعلانات حاليًا.")
            return

        kb = []
        for spot in spots:
            btn_text = f"📢 {spot['channel_name']} - {spot['price']} ⭐"
            kb.append([InlineKeyboardButton(btn_text, callback_data=f"{AD_CALLBACKS['select']}:{spot['id']}")])
        kb.append([InlineKeyboardButton("🔙 إغلاق", callback_data=AD_CALLBACKS['cancel'])])

        await safe_send(
            context.bot,
            user_id,
            "📢 **القنوات المتاحة للإعلانات:**\nاختر قناة لعرض الإعلان فيها.",
            reply_markup=InlineKeyboardMarkup(kb)
        )


# ========== معالجات الأزرار ==========

async def handle_ad_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == AD_CALLBACKS['cancel']:
        try:
            await query.message.delete()
        except:
            pass
        return

    if data.startswith(AD_CALLBACKS['select'] + ":"):
        try:
            spot_id = int(data.split(":")[-1])
        except:
            return
        spot = await AdvertisingDB.get_ad_spot_by_id(spot_id)
        if not spot:
            await safe_send(context.bot, user_id, "❌ هذه القناة لم تعد متاحة.")
            return

        context.user_data['ad_spot_id'] = spot_id
        context.user_data['ad_price'] = spot['price']

        await safe_send(
            context.bot,
            user_id,
            f"📝 أرسل نص الإعلان الذي تريد نشره في {spot['channel_name']} (السعر: {spot['price']} ⭐)"
        )
        StateManager.set(user_id, UserState.WAIT_AD_TEXT)
        return


async def handle_ad_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    ad_spot_id = context.user_data.get('ad_spot_id')
    if not ad_spot_id:
        return

    ad_text = update.message.text.strip()
    if not ad_text:
        await safe_send(context.bot, user_id, "❌ نص الإعلان فارغ.")
        return

    order_id = await AdvertisingDB.create_ad_order(ad_spot_id, user_id, ad_text)
    if not order_id:
        await safe_send(context.bot, user_id, "❌ فشل إنشاء طلب الإعلان.")
        return

    spot = await AdvertisingDB.get_ad_spot_by_id(ad_spot_id)
    price = spot['price']

    try:
        await context.bot.send_invoice(
            chat_id=user_id,
            title="📢 إعلان ممول",
            description=f"نشر إعلانك في قناة {spot['channel_name']}",
            payload=json.dumps({'type': 'ad', 'order_id': order_id}),
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("نشر إعلان", price)]
        )
        await safe_send(context.bot, user_id, "🔄 تم إرسال فاتورة الدفع. أكمل الدفع لبدء النشر.")
    except Exception as e:
        logger.error(f"فشل إرسال فاتورة الإعلان: {e}")
        await DB.execute("UPDATE ad_orders SET status='cancelled' WHERE id=?", (order_id,))
        await safe_send(context.bot, user_id, "❌ فشل إنشاء الفاتورة. حاول لاحقًا.")

    context.user_data.pop('ad_spot_id', None)
    context.user_data.pop('ad_price', None)
    StateManager.clear(user_id)


async def handle_ad_payment_success(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payment = update.message.successful_payment
    try:
        payload = json.loads(payment.invoice_payload)
    except:
        return

    if payload.get('type') != 'ad':
        return

    order_id = payload.get('order_id')
    order = await AdvertisingDB.get_order_by_id(order_id)
    if not order:
        logger.error(f"طلب الإعلان غير موجود: {order_id}")
        return

    await AdvertisingDB.mark_order_paid(order_id, payment.telegram_payment_charge_id)

    # توزيع الأرباح (20% للمنصة، 80% لصاحب القناة)
    platform_share = int(order['price'] * PLATFORM_SHARE_PERCENT / 100)
    owner_share = order['price'] - platform_share

    if owner_share > 0:
        await DB.add_to_balance(order['owner_id'], owner_share)

    await AdvertisingDB.update_order_shares(order_id, platform_share, owner_share)

    try:
        await context.bot.send_message(
            chat_id=order['tele_channel_id'],
            text=f"📢 **إعلان ممول**\n\n{order['ad_text']}\n\n- تم النشر عبر @{CONFIG.BOT_USERNAME}"
        )
        await AdvertisingDB.mark_order_published(order_id)

        await safe_send(context.bot, order['advertiser_id'], "✅ تم نشر إعلانك بنجاح في القناة!")
        await safe_send(
            context.bot,
            order['owner_id'],
            f"💰 تم نشر إعلان ممول في قناتك {order['channel_name']}.\n"
            f"المبلغ: {order['price']} ⭐\n"
            f"ربحك: {owner_share} ⭐\n"
            f"نسبة المنصة: {platform_share} ⭐\n"
            f"المعلن: {order['advertiser_id']}"
        )
    except Exception as e:
        logger.error(f"فشل نشر الإعلان: {e}")
        await safe_send(context.bot, order['advertiser_id'], "❌ فشل نشر الإعلان. سيتم استرجاع المبلغ.")


# ========== دوال التسجيل في main.py ==========

def register_advertising_handlers(app):
    """تسجيل جميع معالجات نظام الإعلانات في التطبيق"""
    app.add_handler(CommandHandler("enable_ads", AdvertisingHandlers.enable_ads))
    app.add_handler(CommandHandler("disable_ads", AdvertisingHandlers.disable_ads))
    app.add_handler(CommandHandler("advertise", AdvertisingHandlers.advertise))

    app.add_handler(CallbackQueryHandler(handle_ad_callback, pattern=r"^ad_"))

    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND,
        handle_ad_text_message
    ))

    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_ad_payment_success))
