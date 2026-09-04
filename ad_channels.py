#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ad_channels.py - نظام قنوات الإعلانات (النشر التلقائي) (نسخة مكتملة ومعالجة)
====================================================================
- ✅ إدارة قنوات النشر التلقائي (إضافة، حذف، تفعيل، تعطيل، تحديد سعر)
- ✅ عرض القنوات المضافة
- ✅ دعم الأزرار والأوامر
- ✅ تكامل مع StateManager
- ✅ دعم الترجمة
- ✅ واجهة قاعدة بيانات AdChannelDB
- ✅ معالجات الأزرار والرسائل
- ✅ إصلاح جميع الأخطاء المحتملة
"""

import logging
import re
from typing import Optional, Dict, Any, List
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from config import CONFIG
from database import DB
from utils import safe_send, StateManager, UserState, get_text

logger = logging.getLogger(__name__)

# ========== ثوابت الأزرار ==========
AD_CH_MENU = "ad_ch_menu"
AD_CH_ADD = "ad_ch_add"
AD_CH_LIST = "ad_ch_list"
AD_CH_SET_PRICE = "ad_ch_set_price"
AD_CH_ENABLE = "ad_ch_enable"
AD_CH_DISABLE = "ad_ch_disable"
AD_CH_DELETE = "ad_ch_delete"
AD_CH_CANCEL = "ad_ch_cancel"

# استخدام getattr مع fallback آمن
try:
    MAX_AD_CHANNELS_PER_USER = getattr(CONFIG, 'MAX_AD_CHANNELS_PER_USER', 10)
except:
    MAX_AD_CHANNELS_PER_USER = 10

# ========== دوال مساعدة ==========

async def _get_text(key: str, lang: str = 'ar', default: str = "") -> str:
    """جلب نص مترجم مع fallback آمن"""
    try:
        text = await get_text(lang, key)
        if text and text != key:
            return text
    except:
        pass
    return default

def escape_html(text: str) -> str:
    """تهريب HTML لمنع الحقن"""
    if not text:
        return ""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

async def safe_send_html(bot, chat_id, text, reply_markup=None, parse_mode='HTML'):
    """إرسال رسالة HTML مع fallback آمن"""
    try:
        return await safe_send(bot, chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"HTML send failed: {e}")
        clean_text = re.sub(r'<[^>]+>', '', text)
        return await safe_send(bot, chat_id, clean_text, reply_markup=reply_markup)

async def resolve_channel_id(bot, text: str) -> Optional[int]:
    """تحويل نص إلى معرف قناة (رقمي أو @username)"""
    text = text.strip()
    if not text:
        return None
    
    # تنظيف @ الزائدة
    text = text.lstrip('@')
    
    # إذا كان رقمي
    if text.lstrip('-').isdigit():
        return int(text)
    
    # محاولة جلب القناة
    try:
        chat = await bot.get_chat(f"@{text}")
        return chat.id
    except Exception:
        return None

async def get_channel_name(bot, channel_id: int) -> str:
    """جلب اسم القناة من المعرف"""
    try:
        chat = await bot.get_chat(channel_id)
        return chat.title or f"قناة {channel_id}"
    except Exception:
        return f"قناة {channel_id}"

async def is_bot_in_channel(bot, channel_id: int) -> bool:
    """التحقق من أن البوت عضو في القناة"""
    try:
        member = await bot.get_chat_member(channel_id, bot.id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

async def is_user_channel_admin(bot, user_id: int, channel_id: int) -> bool:
    """التحقق من أن المستخدم مشرف أو مالك القناة"""
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        return member.status in ['creator', 'administrator']
    except Exception:
        return False

async def get_cancel_keyboard(lang: str = 'ar') -> InlineKeyboardMarkup:
    text = await _get_text('ad_cancel', lang, "❌ إلغاء")
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=AD_CH_CANCEL)]])

async def get_back_to_ad_menu_keyboard(lang: str = 'ar') -> InlineKeyboardMarkup:
    text = await _get_text('ad_back_to_menu', lang, "🔙 رجوع لقائمة الإعلانات")
    return InlineKeyboardMarkup([[InlineKeyboardButton(text, callback_data=AD_CH_MENU)]])

async def get_ad_channels_menu_keyboard(lang: str = 'ar') -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(await _get_text('ad_add', lang, "➕ إضافة قناة إعلانات"), callback_data=AD_CH_ADD)],
        [InlineKeyboardButton(await _get_text('ad_list', lang, "📋 قنواتي الإعلانية"), callback_data=AD_CH_LIST)],
        [
            InlineKeyboardButton(await _get_text('ad_set_price', lang, "💰 تحديد سعر"), callback_data=AD_CH_SET_PRICE),
            InlineKeyboardButton(await _get_text('ad_enable', lang, "✅ تفعيل"), callback_data=AD_CH_ENABLE)
        ],
        [
            InlineKeyboardButton(await _get_text('ad_disable', lang, "❌ تعطيل"), callback_data=AD_CH_DISABLE),
            InlineKeyboardButton(await _get_text('ad_delete', lang, "🗑️ حذف"), callback_data=AD_CH_DELETE)
        ],
        [InlineKeyboardButton(await _get_text('back', lang, "🔙 رجوع"), callback_data="back")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def _show_ad_channels_list(bot, chat_id, user_id, lang='ar', edit_message_id=None):
    """عرض قائمة القنوات الإعلانية للمستخدم"""
    channels = await AdChannelDB.get_user_ad_channels(user_id)
    if not channels:
        text = await _get_text('ad_no_channels', lang, "📭 لا توجد قنوات إعلانات مضافة.")
    else:
        text = await _get_text('ad_my_channels', lang, "📢 **قنوات الإعلانات الخاصة بك:**\n\n")
        for ch in channels:
            status_text = "✅ مفعلة" if ch.get('is_active', 1) else "❌ معطلة"
            text += (
                f"🆔 داخلي: {ch['id']}\n"
                f"📡 معرف: {ch['channel_id']}\n"
                f"📛 الاسم: {escape_html(ch.get('channel_name', 'غير معروف'))}\n"
                f"💰 السعر: {ch.get('price', 0)} ⭐\n"
                f"الحالة: {status_text}\n"
                f"━━━━━━━━━━━━━━━━\n"
            )
    
    reply_markup = await get_back_to_ad_menu_keyboard(lang)
    if edit_message_id:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_message_id, reply_markup=reply_markup, parse_mode='HTML')
        except Exception as e:
            logger.warning(f"تعذر تعديل الرسالة: {e}")
            await safe_send_html(bot, chat_id, text, reply_markup)
    else:
        await safe_send_html(bot, chat_id, text, reply_markup)

async def _build_channel_selection_keyboard(channels, operation, lang='ar'):
    """بناء لوحة اختيار القنوات"""
    keyboard = []
    for ch in channels:
        label = f"{ch['id']} - {ch.get('channel_name', 'قناة')}"
        callback = f"ad_ch_sel:{operation}:{ch['id']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
    
    cancel_text = await _get_text('ad_cancel', lang, "❌ إلغاء")
    keyboard.append([InlineKeyboardButton(cancel_text, callback_data=AD_CH_CANCEL)])
    return InlineKeyboardMarkup(keyboard)

# ========== واجهة قاعدة البيانات ==========

class AdChannelDB:
    """واجهة للتعامل مع جداول قنوات الإعلانات (النشر التلقائي)"""

    @staticmethod
    async def _ensure_table_exists():
        """التأكد من وجود الجدول وإنشائه إذا لزم"""
        try:
            # التحقق من وجود الجدول
            row = await DB.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='ad_channels'")
            if row:
                # التحقق من الأعمدة
                cols = await DB.fetchall("PRAGMA table_info(ad_channels)")
                col_names = [c['name'] for c in cols] if cols else []
                
                # الأعمدة المطلوبة
                required_columns = {
                    'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
                    'user_id': 'INTEGER NOT NULL',
                    'channel_id': 'INTEGER NOT NULL',
                    'channel_name': 'TEXT',
                    'price': 'INTEGER DEFAULT 0',
                    'is_active': 'INTEGER DEFAULT 1',
                    'created_at': 'DATETIME DEFAULT CURRENT_TIMESTAMP'
                }
                
                for col, definition in required_columns.items():
                    if col not in col_names:
                        logger.warning(f"العمود {col} غير موجود، جاري الإضافة...")
                        try:
                            await DB.execute(f"ALTER TABLE ad_channels ADD COLUMN {col} {definition}")
                        except Exception as e:
                            logger.error(f"فشل إضافة العمود {col}: {e}")
                
                # إنشاء الفهارس
                try:
                    await DB.execute("CREATE INDEX IF NOT EXISTS idx_ad_channels_user ON ad_channels(user_id)")
                    await DB.execute("CREATE INDEX IF NOT EXISTS idx_ad_channels_active ON ad_channels(is_active)")
                except Exception as e:
                    logger.warning(f"فشل إنشاء الفهارس: {e}")
                return
        except Exception as e:
            logger.warning(f"تعذر التحقق من الجدول: {e}")

        # إنشاء الجدول إذا لم يكن موجوداً
        logger.info("🔄 إنشاء جدول ad_channels...")
        await DB.execute("""
            CREATE TABLE IF NOT EXISTS ad_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                channel_name TEXT,
                price INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, channel_id)
            )
        """)
        await DB.execute("CREATE INDEX IF NOT EXISTS idx_ad_channels_user ON ad_channels(user_id)")
        await DB.execute("CREATE INDEX IF NOT EXISTS idx_ad_channels_active ON ad_channels(is_active)")
        logger.info("✅ تم إنشاء جدول ad_channels")

    @staticmethod
    async def init_tables():
        """تهيئة الجداول"""
        await AdChannelDB._ensure_table_exists()

    @staticmethod
    async def add_ad_channel(user_id, channel_id, channel_name=None):
        """إضافة قناة إعلانية جديدة"""
        await AdChannelDB._ensure_table_exists()
        
        # التحقق من عدم وجود القناة مسبقاً
        existing = await DB.fetchone(
            "SELECT id FROM ad_channels WHERE user_id=? AND channel_id=?", 
            (user_id, channel_id)
        )
        if existing:
            return existing['id']
        
        # إضافة القناة (بدون تحديد created_at ليأخذ القيمة الافتراضية)
        await DB.execute(
            "INSERT INTO ad_channels (user_id, channel_id, channel_name, is_active) VALUES (?, ?, ?, ?)",
            (user_id, channel_id, channel_name or f"Channel_{channel_id}", 1)
        )
        
        # جلب المعرف الجديد
        row = await DB.fetchone("SELECT last_insert_rowid() as id")
        return row['id'] if row else 0

    @staticmethod
    async def get_user_ad_channels(user_id):
        """الحصول على قنوات المستخدم"""
        await AdChannelDB._ensure_table_exists()
        rows = await DB.fetchall(
            "SELECT id, channel_id, channel_name, price, is_active, created_at FROM ad_channels WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)
        )
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def get_channel(channel_db_id):
        """الحصول على قناة بالمعرف الداخلي"""
        await AdChannelDB._ensure_table_exists()
        row = await DB.fetchone("SELECT * FROM ad_channels WHERE id=?", (channel_db_id,))
        return dict(row) if row else None

    @staticmethod
    async def is_ad_channel_owner(user_id, channel_db_id):
        """التحقق من ملكية القناة"""
        await AdChannelDB._ensure_table_exists()
        row = await DB.fetchone("SELECT 1 FROM ad_channels WHERE id=? AND user_id=?", (channel_db_id, user_id))
        return row is not None

    @staticmethod
    async def set_ad_channel_price(user_id, channel_db_id, price):
        """تحديد سعر القناة"""
        if not await AdChannelDB.is_ad_channel_owner(user_id, channel_db_id):
            return False
        await DB.execute("UPDATE ad_channels SET price=? WHERE id=?", (price, channel_db_id))
        return True

    @staticmethod
    async def enable_ad_channel(user_id, channel_db_id):
        """تفعيل قناة"""
        if not await AdChannelDB.is_ad_channel_owner(user_id, channel_db_id):
            return False
        await DB.execute("UPDATE ad_channels SET is_active=1 WHERE id=?", (channel_db_id,))
        return True

    @staticmethod
    async def disable_ad_channel(user_id, channel_db_id):
        """تعطيل قناة"""
        if not await AdChannelDB.is_ad_channel_owner(user_id, channel_db_id):
            return False
        await DB.execute("UPDATE ad_channels SET is_active=0 WHERE id=?", (channel_db_id,))
        return True

    @staticmethod
    async def remove_ad_channel(user_id, channel_db_id):
        """حذف قناة"""
        if not await AdChannelDB.is_ad_channel_owner(user_id, channel_db_id):
            return False
        await DB.execute("DELETE FROM ad_channels WHERE id=?", (channel_db_id,))
        return True

    @staticmethod
    async def count_user_ad_channels(user_id):
        """عدد قنوات المستخدم"""
        await AdChannelDB._ensure_table_exists()
        row = await DB.fetchone("SELECT COUNT(*) as cnt FROM ad_channels WHERE user_id=?", (user_id,))
        return row['cnt'] if row else 0

# ========== دوال تنظيف الحالة ==========

async def _cleanup_user_state(context, user_id):
    """تنظيف حالة المستخدم"""
    try:
        StateManager.clear(user_id)
    except:
        pass
    context.user_data.pop('ad_operation', None)
    context.user_data.pop('ad_channel_id', None)

# ========== معالج الأزرار ==========

async def handle_ad_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج أزرار قنوات الإعلانات"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    
    # جلب اللغة بأمان
    try:
        lang = await DB.get_user_language(user_id) or 'ar'
    except:
        lang = 'ar'

    if update.effective_chat.type != "private":
        await query.answer("⚠️ هذه الأزرار تعمل في المحادثة الخاصة فقط.", show_alert=True)
        return

    await query.answer()

    # ===== الإلغاء =====
    if data == AD_CH_CANCEL:
        await _cleanup_user_state(context, user_id)
        menu_text = await _get_text('ad_menu_title', lang, "📢 **إدارة قنوات الإعلانات**\nاختر العملية المطلوبة:")
        reply_markup = await get_ad_channels_menu_keyboard(lang)
        await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='HTML')
        return

    # ===== اختيار من القائمة =====
    if data.startswith("ad_ch_sel:"):
        parts = data.split(":")
        if len(parts) < 3:
            await query.answer("❌ بيانات غير صالحة", show_alert=True)
            return
        operation = parts[1]
        try:
            ch_db_id = int(parts[2])
        except ValueError:
            await query.answer("❌ معرف غير صالح", show_alert=True)
            return

        if not await AdChannelDB.is_ad_channel_owner(user_id, ch_db_id):
            await query.answer("❌ هذه القناة ليست ملكك", show_alert=True)
            await _cleanup_user_state(context, user_id)
            menu_text = await _get_text('ad_menu_title', lang, "📢 **إدارة قنوات الإعلانات**\nاختر العملية المطلوبة:")
            reply_markup = await get_ad_channels_menu_keyboard(lang)
            await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='HTML')
            return

        if operation == 'set_price':
            StateManager.set(user_id, "WAIT_AD_PRICE")
            context.user_data['ad_channel_id'] = ch_db_id
            context.user_data['ad_operation'] = 'set_price'
            await query.edit_message_text(
                await _get_text('ad_enter_price', lang, "💰 أرسل السعر (بالنجوم):"),
                reply_markup=await get_cancel_keyboard(lang)
            )
            return
        elif operation == 'enable':
            if await AdChannelDB.enable_ad_channel(user_id, ch_db_id):
                await query.answer("✅ تم التفعيل")
            else:
                await query.answer("❌ فشل", show_alert=True)
            await _cleanup_user_state(context, user_id)
            await _show_ad_channels_list(context.bot, chat_id, user_id, lang, edit_message_id=message_id)
            return
        elif operation == 'disable':
            if await AdChannelDB.disable_ad_channel(user_id, ch_db_id):
                await query.answer("✅ تم التعطيل")
            else:
                await query.answer("❌ فشل", show_alert=True)
            await _cleanup_user_state(context, user_id)
            await _show_ad_channels_list(context.bot, chat_id, user_id, lang, edit_message_id=message_id)
            return
        elif operation == 'delete':
            if await AdChannelDB.remove_ad_channel(user_id, ch_db_id):
                await query.answer("✅ تم الحذف")
            else:
                await query.answer("❌ فشل", show_alert=True)
            await _cleanup_user_state(context, user_id)
            await _show_ad_channels_list(context.bot, chat_id, user_id, lang, edit_message_id=message_id)
            return
        else:
            await query.answer("⚠️ عملية غير معروفة", show_alert=True)
            return

    # ===== الأزرار الرئيسية =====
    if data != AD_CH_ADD:
        await _cleanup_user_state(context, user_id)

    if data == AD_CH_MENU:
        menu_text = await _get_text('ad_menu_title', lang, "📢 **إدارة قنوات الإعلانات**\nاختر العملية المطلوبة:")
        reply_markup = await get_ad_channels_menu_keyboard(lang)
        await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='HTML')
        return

    elif data == AD_CH_ADD:
        # التحقق من الاشتراك بأمان
        try:
            has_sub = await DB.has_active_subscription(user_id)
        except:
            has_sub = True  # السماح في حالة عدم وجود الدالة
        
        if not has_sub and user_id != CONFIG.PRIMARY_OWNER_ID:
            await query.answer("❌ يتطلب اشتراكاً نشطاً", show_alert=True)
            return
        
        current_count = await AdChannelDB.count_user_ad_channels(user_id)
        if current_count >= MAX_AD_CHANNELS_PER_USER:
            await query.answer(f"❌ وصلت للحد الأقصى ({MAX_AD_CHANNELS_PER_USER}).", show_alert=True)
            return
        
        StateManager.set(user_id, "WAIT_AD_CHANNEL_ID")
        context.user_data['ad_operation'] = 'add'
        await query.edit_message_text(
            await _get_text('ad_enter_channel', lang, "📝 أرسل معرف القناة أو @username:"),
            reply_markup=await get_cancel_keyboard(lang)
        )
        return

    elif data == AD_CH_LIST:
        await _show_ad_channels_list(context.bot, chat_id, user_id, lang, edit_message_id=message_id)
        return

    elif data == AD_CH_SET_PRICE:
        channels = await AdChannelDB.get_user_ad_channels(user_id)
        if not channels:
            await query.answer("📭 لا توجد قنوات. أضف قناة أولاً.", show_alert=True)
            return
        context.user_data['ad_operation'] = 'set_price'
        await query.edit_message_text(
            await _get_text('ad_select_channel_price', lang, "💰 اختر القناة لتحديد سعرها:"),
            reply_markup=await _build_channel_selection_keyboard(channels, 'set_price', lang)
        )
        return

    elif data == AD_CH_ENABLE:
        channels = await AdChannelDB.get_user_ad_channels(user_id)
        if not channels:
            await query.answer("📭 لا توجد قنوات. أضف قناة أولاً.", show_alert=True)
            return
        context.user_data['ad_operation'] = 'enable'
        await query.edit_message_text(
            await _get_text('ad_select_channel_enable', lang, "✅ اختر القناة لتفعيلها:"),
            reply_markup=await _build_channel_selection_keyboard(channels, 'enable', lang)
        )
        return

    elif data == AD_CH_DISABLE:
        channels = await AdChannelDB.get_user_ad_channels(user_id)
        if not channels:
            await query.answer("📭 لا توجد قنوات. أضف قناة أولاً.", show_alert=True)
            return
        context.user_data['ad_operation'] = 'disable'
        await query.edit_message_text(
            await _get_text('ad_select_channel_disable', lang, "❌ اختر القناة لتعطيلها:"),
            reply_markup=await _build_channel_selection_keyboard(channels, 'disable', lang)
        )
        return

    elif data == AD_CH_DELETE:
        channels = await AdChannelDB.get_user_ad_channels(user_id)
        if not channels:
            await query.answer("📭 لا توجد قنوات. أضف قناة أولاً.", show_alert=True)
            return
        context.user_data['ad_operation'] = 'delete'
        await query.edit_message_text(
            await _get_text('ad_select_channel_delete', lang, "🗑️ اختر القناة لحذفها:"),
            reply_markup=await _build_channel_selection_keyboard(channels, 'delete', lang)
        )
        return

    else:
        await query.answer("⚠️ غير معروف", show_alert=True)

# ========== معالج الرسائل النصية ==========

async def handle_ad_channel_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج الرسائل النصية لقنوات الإعلانات"""
    user_id = update.effective_user.id
    state = StateManager.get(user_id)
    
    if state not in ("WAIT_AD_CHANNEL_ID", "WAIT_AD_PRICE"):
        return
    
    # جلب اللغة بأمان
    try:
        lang = await DB.get_user_language(user_id) or 'ar'
    except:
        lang = 'ar'
    
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # التحقق من الإلغاء
    if text.lower() in ["إلغاء", "cancel", "/cancel"]:
        await _cleanup_user_state(context, user_id)
        await safe_send_html(
            context.bot,
            chat_id,
            await _get_text('ad_cancelled', lang, "✅ تم إلغاء العملية."),
            reply_markup=await get_ad_channels_menu_keyboard(lang)
        )
        return

    # ===== معالجة إضافة قناة =====
    if state == "WAIT_AD_CHANNEL_ID":
        channel_id = await resolve_channel_id(context.bot, text)
        if not channel_id:
            await safe_send_html(
                context.bot,
                chat_id,
                await _get_text('ad_invalid_channel_id', lang, "❌ معرف قناة غير صالح.")
            )
            return
        
        # التحقق من أن البوت عضو في القناة
        if not await is_bot_in_channel(context.bot, channel_id):
            await safe_send_html(
                context.bot,
                chat_id,
                await _get_text('ad_bot_not_member', lang, "❌ البوت ليس عضواً في القناة. أضف البوت أولاً.")
            )
            return
        
        # التحقق من صلاحيات المستخدم في القناة
        if not await is_user_channel_admin(context.bot, user_id, channel_id):
            await safe_send_html(
                context.bot,
                chat_id,
                "❌ يجب أن تكون مشرفاً أو مالكاً في القناة لإضافتها."
            )
            return
        
        # التحقق من عدم وجود القناة مسبقاً
        row = await DB.fetchone(
            "SELECT COUNT(*) as cnt FROM ad_channels WHERE user_id=? AND channel_id=?", 
            (user_id, channel_id)
        )
        existing = row['cnt'] if row else 0
        
        if existing:
            await safe_send_html(
                context.bot,
                chat_id,
                await _get_text('ad_channel_exists', lang, "❌ هذه القناة مضافة بالفعل.")
            )
            await _cleanup_user_state(context, user_id)
            await safe_send_html(
                context.bot,
                chat_id,
                await _get_text('ad_menu_title', lang, "📢 **إدارة قنوات الإعلانات**"),
                reply_markup=await get_ad_channels_menu_keyboard(lang)
            )
            return
        
        # إضافة القناة
        channel_name = await get_channel_name(context.bot, channel_id)
        ch_db_id = await AdChannelDB.add_ad_channel(user_id, channel_id, channel_name)
        
        if ch_db_id:
            success_text = await _get_text(
                'ad_added_success', 
                lang, 
                "✅ تم حفظ قناة الإعلانات بنجاح!\n📛 الاسم: {name}\n🆔 المعرف الرقمي: {id}\n🆔 المعرف الداخلي: {db_id}"
            )
            await safe_send_html(
                context.bot,
                chat_id,
                success_text.format(name=escape_html(channel_name), id=channel_id, db_id=ch_db_id)
            )
        else:
            await safe_send_html(
                context.bot,
                chat_id,
                await _get_text('ad_add_failed', lang, "❌ فشل إضافة القناة.")
            )
        
        await _cleanup_user_state(context, user_id)
        await safe_send_html(
            context.bot,
            chat_id,
            await _get_text('ad_menu_title', lang, "📢 **إدارة قنوات الإعلانات**"),
            reply_markup=await get_ad_channels_menu_keyboard(lang)
        )
        return

    # ===== معالجة تحديد السعر =====
    elif state == "WAIT_AD_PRICE":
        ch_db_id = context.user_data.get('ad_channel_id')
        if not ch_db_id:
            await _cleanup_user_state(context, user_id)
            await safe_send_html(
                context.bot,
                chat_id,
                await _get_text('ad_error', lang, "❌ حدث خطأ."),
                reply_markup=await get_ad_channels_menu_keyboard(lang)
            )
            return
        
        # التحقق من الملكية
        if not await AdChannelDB.is_ad_channel_owner(user_id, ch_db_id):
            await _cleanup_user_state(context, user_id)
            await safe_send_html(
                context.bot,
                chat_id,
                await _get_text('ad_not_owner', lang, "❌ هذه القناة ليست ملكك."),
                reply_markup=await get_ad_channels_menu_keyboard(lang)
            )
            return
        
        # التحقق من صحة السعر
        try:
            price = int(text)
            if price <= 0:
                raise ValueError
        except ValueError:
            await safe_send_html(
                context.bot,
                chat_id,
                await _get_text('ad_invalid_price', lang, "❌ سعر غير صالح (يجب أن يكون عدداً صحيحاً موجباً).")
            )
            return
        
        # تحديد السعر
        if await AdChannelDB.set_ad_channel_price(user_id, ch_db_id, price):
            success_text = await _get_text('ad_price_set', lang, "✅ تم تحديد السعر: {price} ⭐")
            await safe_send_html(
                context.bot,
                chat_id,
                success_text.format(price=price)
            )
        else:
            await safe_send_html(
                context.bot,
                chat_id,
                await _get_text('ad_failed', lang, "❌ فشل تحديد السعر.")
            )
        
        await _cleanup_user_state(context, user_id)
        await safe_send_html(
            context.bot,
            chat_id,
            await _get_text('ad_menu_title', lang, "📢 **إدارة قنوات الإعلانات**"),
            reply_markup=await get_ad_channels_menu_keyboard(lang)
        )
        return

# ========== أوامر قنوات الإعلانات ==========

class AdChannelHandlers:
    """معالج أوامر قنوات الإعلانات (النشر التلقائي)"""

    @staticmethod
    async def ad_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        try:
            lang = await DB.get_user_language(user_id) or 'ar'
        except:
            lang = 'ar'
        menu_text = await _get_text('ad_menu_title', lang, "📢 **إدارة قنوات الإعلانات**\nاختر العملية المطلوبة:")
        reply_markup = await get_ad_channels_menu_keyboard(lang)
        await safe_send_html(context.bot, user_id, menu_text, reply_markup=reply_markup)

    @staticmethod
    async def add_ad_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        try:
            lang = await DB.get_user_language(user_id) or 'ar'
        except:
            lang = 'ar'
        args = context.args or []
        
        if not args:
            await safe_send_html(
                context.bot,
                user_id,
                await _get_text('ad_add_usage', lang, "📝 استخدم: /add_ad_channel <معرف_القناة أو @username> [اسم]")
            )
            return
        
        # التحقق من الاشتراك
        try:
            has_sub = await DB.has_active_subscription(user_id)
        except:
            has_sub = True
        
        if not has_sub and user_id != CONFIG.PRIMARY_OWNER_ID:
            await safe_send_html(context.bot, user_id, "❌ يتطلب اشتراكاً نشطاً")
            return
        
        current_count = await AdChannelDB.count_user_ad_channels(user_id)
        if current_count >= MAX_AD_CHANNELS_PER_USER:
            await safe_send_html(context.bot, user_id, f"❌ وصلت للحد الأقصى ({MAX_AD_CHANNELS_PER_USER}).")
            return
        
        channel_id = await resolve_channel_id(context.bot, args[0])
        if not channel_id:
            await safe_send_html(context.bot, user_id, "❌ معرف قناة غير صالح")
            return
        
        if not await is_bot_in_channel(context.bot, channel_id):
            await safe_send_html(context.bot, user_id, "❌ البوت ليس عضواً في القناة. أضف البوت أولاً.")
            return
        
        # التحقق من صلاحيات المستخدم
        if not await is_user_channel_admin(context.bot, user_id, channel_id):
            await safe_send_html(context.bot, user_id, "❌ يجب أن تكون مشرفاً أو مالكاً في القناة.")
            return
        
        # التحقق من عدم وجود القناة
        row = await DB.fetchone(
            "SELECT COUNT(*) as cnt FROM ad_channels WHERE user_id=? AND channel_id=?", 
            (user_id, channel_id)
        )
        existing = row['cnt'] if row else 0
        
        if existing:
            await safe_send_html(context.bot, user_id, "❌ هذه القناة مضافة بالفعل.")
            return
        
        channel_name = " ".join(args[1:]) if len(args) > 1 else await get_channel_name(context.bot, channel_id)
        ch_db_id = await AdChannelDB.add_ad_channel(user_id, channel_id, channel_name)
        
        if ch_db_id:
            success_text = await _get_text('ad_added_success_cmd', lang, "✅ تمت إضافة القناة، المعرف الداخلي: {db_id}")
            await safe_send_html(
                context.bot,
                user_id,
                success_text.format(db_id=ch_db_id)
            )
        else:
            await safe_send_html(context.bot, user_id, "❌ فشل الإضافة.")

    @staticmethod
    async def my_ad_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        try:
            lang = await DB.get_user_language(user_id) or 'ar'
        except:
            lang = 'ar'
        channels = await AdChannelDB.get_user_ad_channels(user_id)
        
        if not channels:
            await safe_send_html(context.bot, user_id, "📭 لا توجد قنوات")
            return
        
        text = await _get_text('ad_my_channels', lang, "📢 **قنوات الإعلانات:**\n\n")
        for ch in channels:
            status = "✅" if ch.get('is_active', 1) else "❌"
            text += f"{status} {ch['id']} - {ch.get('channel_name', 'قناة')} - {ch.get('price', 0)} ⭐\n"
        
        await safe_send_html(context.bot, user_id, text)

    @staticmethod
    async def set_ad_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        try:
            lang = await DB.get_user_language(user_id) or 'ar'
        except:
            lang = 'ar'
        args = context.args or []
        
        if len(args) < 2:
            await safe_send_html(
                context.bot,
                user_id,
                await _get_text('ad_set_price_usage', lang, "📝 استخدم: /set_ad_price <channel_db_id> <السعر>")
            )
            return
        
        try:
            ch_db_id = int(args[0])
            price = int(args[1])
            if price <= 0:
                raise ValueError
        except ValueError:
            await safe_send_html(context.bot, user_id, "❌ قيم غير صالحة")
            return
        
        if not await AdChannelDB.is_ad_channel_owner(user_id, ch_db_id):
            await safe_send_html(context.bot, user_id, "❌ هذه القناة ليست ملكك")
            return
        
        if await AdChannelDB.set_ad_channel_price(user_id, ch_db_id, price):
            success_text = await _get_text('ad_price_set', lang, "✅ تم تحديد السعر: {price} ⭐")
            await safe_send_html(
                context.bot,
                user_id,
                success_text.format(price=price)
            )
        else:
            await safe_send_html(context.bot, user_id, "❌ فشل")

    @staticmethod
    async def enable_ad_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        try:
            lang = await DB.get_user_language(user_id) or 'ar'
        except:
            lang = 'ar'
        args = context.args or []
        
        if not args:
            await safe_send_html(
                context.bot,
                user_id,
                await _get_text('ad_enable_usage', lang, "📝 استخدم: /enable_ad_channel <channel_db_id>")
            )
            return
        
        try:
            ch_db_id = int(args[0])
        except ValueError:
            await safe_send_html(context.bot, user_id, "❌ معرف غير صالح")
            return
        
        if not await AdChannelDB.is_ad_channel_owner(user_id, ch_db_id):
            await safe_send_html(context.bot, user_id, "❌ هذه القناة ليست ملكك")
            return
        
        if await AdChannelDB.enable_ad_channel(user_id, ch_db_id):
            await safe_send_html(context.bot, user_id, "✅ تم التفعيل")
        else:
            await safe_send_html(context.bot, user_id, "❌ فشل")

    @staticmethod
    async def disable_ad_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        try:
            lang = await DB.get_user_language(user_id) or 'ar'
        except:
            lang = 'ar'
        args = context.args or []
        
        if not args:
            await safe_send_html(
                context.bot,
                user_id,
                await _get_text('ad_disable_usage', lang, "📝 استخدم: /disable_ad_channel <channel_db_id>")
            )
            return
        
        try:
            ch_db_id = int(args[0])
        except ValueError:
            await safe_send_html(context.bot, user_id, "❌ معرف غير صالح")
            return
        
        if not await AdChannelDB.is_ad_channel_owner(user_id, ch_db_id):
            await safe_send_html(context.bot, user_id, "❌ هذه القناة ليست ملكك")
            return
        
        if await AdChannelDB.disable_ad_channel(user_id, ch_db_id):
            await safe_send_html(context.bot, user_id, "✅ تم التعطيل")
        else:
            await safe_send_html(context.bot, user_id, "❌ فشل")

    @staticmethod
    async def remove_ad_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        try:
            lang = await DB.get_user_language(user_id) or 'ar'
        except:
            lang = 'ar'
        args = context.args or []
        
        if not args:
            await safe_send_html(
                context.bot,
                user_id,
                await _get_text('ad_remove_usage', lang, "📝 استخدم: /remove_ad_channel <channel_db_id>")
            )
            return
        
        try:
            ch_db_id = int(args[0])
        except ValueError:
            await safe_send_html(context.bot, user_id, "❌ معرف غير صالح")
            return
        
        if not await AdChannelDB.is_ad_channel_owner(user_id, ch_db_id):
            await safe_send_html(context.bot, user_id, "❌ هذه القناة ليست ملكك")
            return
        
        if await AdChannelDB.remove_ad_channel(user_id, ch_db_id):
            await safe_send_html(context.bot, user_id, "✅ تم الحذف")
        else:
            await safe_send_html(context.bot, user_id, "❌ فشل")

# =====================================================================
# تسجيل المعالجات
# =====================================================================

def register_ad_channel_handlers(application):
    """تسجيل معالجات قنوات الإعلانات"""
    
    # الأوامر
    application.add_handler(CommandHandler("ad_channels", AdChannelHandlers.ad_channels_menu))
    application.add_handler(CommandHandler("add_ad_channel", AdChannelHandlers.add_ad_channel))
    application.add_handler(CommandHandler("my_ad_channels", AdChannelHandlers.my_ad_channels))
    application.add_handler(CommandHandler("set_ad_price", AdChannelHandlers.set_ad_price))
    application.add_handler(CommandHandler("enable_ad_channel", AdChannelHandlers.enable_ad_channel))
    application.add_handler(CommandHandler("disable_ad_channel", AdChannelHandlers.disable_ad_channel))
    application.add_handler(CommandHandler("remove_ad_channel", AdChannelHandlers.remove_ad_channel))
    
    # الأزرار
    application.add_handler(CallbackQueryHandler(handle_ad_channel_callback, pattern="^ad_ch_"))
    
    # الرسائل النصية
    application.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE,
        handle_ad_channel_text_message
    ))
    
    logger.info("✅ تم تسجيل معالجات قنوات الإعلانات")
    return application

# =====================================================================
# تصدير الدوال الرئيسية
# =====================================================================

__all__ = [
    # الثوابت
    'AD_CH_MENU', 'AD_CH_ADD', 'AD_CH_LIST', 'AD_CH_SET_PRICE',
    'AD_CH_ENABLE', 'AD_CH_DISABLE', 'AD_CH_DELETE', 'AD_CH_CANCEL',
    'MAX_AD_CHANNELS_PER_USER',
    # الدوال المساعدة
    'resolve_channel_id', 'get_channel_name', 'is_bot_in_channel',
    'is_user_channel_admin',
    'get_cancel_keyboard', 'get_back_to_ad_menu_keyboard',
    'get_ad_channels_menu_keyboard',
    # المعالجات
    'handle_ad_channel_callback', 'handle_ad_channel_text_message',
    'AdChannelHandlers',
    'register_ad_channel_handlers',
    # واجهة قاعدة البيانات
    'AdChannelDB',
]
