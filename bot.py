import asyncio
import json
import logging
import shutil
import sys
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# =====================================================================
# 1. إعدادات التسجيل والاستيرادات
# =====================================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand, ChatPermissions, BadRequest
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, PreCheckoutQueryHandler,
    ChatMemberHandler, ContextTypes
)
from telegram.request import HTTPXRequest

from config import CONFIG, PATHS

# =====================================================================
# 2. أداة الوقت
# =====================================================================

class TimeUtils:
    @staticmethod
    def utc_now():
        return datetime.utcnow()
    
    @staticmethod
    def utc_iso():
        return datetime.utcnow().isoformat()
    
    @staticmethod
    def mecca_now():
        return datetime.utcnow() + timedelta(hours=3)
    
    @staticmethod
    def mecca_iso():
        return (datetime.utcnow() + timedelta(hours=3)).isoformat()
    
    @staticmethod
    def safe_parse_iso(iso_str):
        try:
            return datetime.fromisoformat(iso_str)
        except:
            return None

# =====================================================================
# 3. تعريفات الأزرار (CB - Callback Data)
# =====================================================================

class CB:
    MAIN = "main"
    BACK = "back"
    CANCEL = "cancel"
    HELP = "help"
    SETTINGS = "settings"
    LANGUAGE = "language"
    
    CH_ADD = "ch_add"
    CH_LIST = "ch_list"
    CH_DEL = "ch_del:"
    CH_SEL = "ch_sel:"
    CH_STATS = "ch_stats:"
    
    POST_ADD = "post_add"
    POST_PUB = "post_pub"
    POST_LIST = "post_list"
    POST_REC = "post_rec"
    POST_DEL = "post_del:"
    POST_CLEAR = "post_clear:"
    PUB_ALL = "pub_all"
    
    STATS_PEND = "stats_pend"
    STATS_FULL = "stats_full"
    
    GROUPS = "groups"
    GRP_SET = "grp_set:"
    
    TOGGLE_AUTO = "toggle_auto"
    TOGGLE_REC = "toggle_rec"
    
    SCHEDULE = "schedule:"
    SCHED_MIN = "sched_min:"
    SCHED_HOUR = "sched_hour:"
    SCHED_DAY = "sched_day:"
    SCHED_TIME = "sched_time:"
    
    SEC_LINKS = "sec_links:"
    SEC_MENTIONS = "sec_mentions:"
    SEC_SLOW = "sec_slow:"
    SEC_WELCOME = "sec_welcome:"
    SEC_GOODBYE = "sec_goodbye:"
    SEC_VIDEO = "sec_video:"
    SEC_AUDIO = "sec_audio:"
    SEC_ANIM = "sec_anim:"
    SEC_SERVICE = "sec_service:"
    SEC_DOC = "sec_doc:"
    SEC_STICKER = "sec_sticker:"
    SEC_FORWARD = "sec_forward:"
    SEC_POLL = "sec_poll:"
    SEC_GAME = "sec_game:"
    SEC_VOICE = "sec_voice:"
    SEC_VIDEONOTE = "sec_videonote:"
    SEC_FLOOD = "sec_flood:"
    SEC_NIGHT = "sec_night:"
    SEC_MAXLEN = "sec_maxlen:"
    SEC_WARN = "sec_warn:"
    SEC_BANNED = "sec_banned:"
    SEC_CLOSE = "sec_close"
    SEC_ENABLE_ALL = "sec_enable_all:"
    SEC_DISABLE_ALL = "sec_disable_all:"
    SEC_DEL_PEN = "sec_del_pen:"
    SEC_PENALTY = "sec_penalty:"
    SEC_ADV_ACT = "sec_adv_act:"
    SEC_ACT_LOG = "sec_act_log:"
    SEC_AUTO_REPLY_MENU = "sec_auto_reply_menu:"
    
    WARN_COUNT = "sec_warn_count:"
    WARN_PENALTY = "sec_warn_penalty:"
    SET_WARN_PENALTY = "sec_set_warn_penalty:"
    
    BAN_ADD = "ban_add:"
    BAN_LIST = "ban_list:"
    BAN_REM = "ban_rem:"
    
    PENALTY = "penalty:"
    PEN_KICK = "pen_kick:"
    PEN_BAN = "pen_ban:"
    PEN_MUTE = "pen_mute:"
    PEN_WARN = "pen_warn:"
    PEN_RESTRICT = "pen_restrict:"
    PEN_NONE = "pen_none:"
    
    ADV_ACT = "adv_act:"
    ACT_BAN = "act_ban:"
    ACT_MUTE = "act_mute:"
    ACT_WARN = "act_warn:"
    ACT_KICK = "act_kick:"
    ACT_RESTRICT = "act_restrict:"
    ACT_PIN = "act_pin:"
    ACT_LOG = "act_log:"
    ACT_UNBAN = "act_unban:"
    MUTE_DUR = "mute_dur:"
    
    PANEL_LOCK = "panel_lock:"
    PANEL_UNLOCK = "panel_unlock:"
    PANEL_CLOSE = "panel_close"
    
    SUPPORT = "support"
    SUPPORT_TICKET = "support_ticket"
    
    TRIAL = "trial"
    SUBSCRIBE = "subscribe"
    BUY_SUB = "buy_sub:"
    PLANS = "plans"
    INVOICES = "invoices"
    CHECK_SUB = "check_sub"
    
    DEVELOPER = "developer"
    UPDATES = "updates"
    
    REFERRAL = "referral"
    REF_CLAIM = "ref_claim"
    REF_LIST = "ref_list"
    
    REMINDER = "reminder"
    REM_TOGGLE_SUB = "rem_sub"
    REM_TOGGLE_DAILY = "rem_daily"
    REM_TOGGLE_WEEKLY = "rem_weekly"
    REM_SET_DAYS = "rem_days"
    REM_SET_LANG = "rem_lang"
    REM_LANG = "rem_lang:"
    
    TRANSLATION = "translation"
    TRANS_OFF = "trans_off"
    TRANS_SET = "trans_set:"
    
    CONTESTS = "contests"
    CONTEST_JOIN = "contest_join:"
    CONTEST_WINNERS = "contest_winners"
    DECLARE_WINNER_SEL = "declare_winner_sel:"
    
    ADMIN = "admin"
    ADMIN_USERS = "admin_users"
    ADMIN_BANNED = "admin_banned"
    ADMIN_UNBAN_ALL = "admin_unban_all"
    ADMIN_CHANNELS = "admin_channels"
    ADMIN_BANNED_CH = "admin_banned_ch"
    ADMIN_ACTIVATE_CH = "admin_activate_ch"
    ADMIN_GROUPS = "admin_groups"
    ADMIN_BANNED_GR = "admin_banned_gr"
    ADMIN_UNBAN_GR = "admin_unban_gr"
    ADMIN_ADD_ADMIN = "admin_add_admin"
    ADMIN_REM_ADMIN = "admin_rem_admin"
    ADMIN_RAM = "admin_ram"
    ADMIN_STATS = "admin_stats"
    ADMIN_METRICS = "admin_metrics"
    ADMIN_BACKUP = "admin_backup"
    ADMIN_RESTORE = "admin_restore"
    ADMIN_RESTORE_SEL = "admin_restore_sel:"
    ADMIN_SEND_UPDATE = "admin_send_update"
    ADMIN_SET_UPDATE_CH = "admin_set_update_ch"
    ADMIN_SHOW_UPDATE = "admin_show_update"
    ADMIN_FORCE_SUB = "admin_force_sub"
    ADMIN_SET_FORCE = "admin_set_force"
    ADMIN_BROADCAST = "admin_broadcast"
    ADMIN_CONFIRM_BROADCAST = "admin_confirm_broadcast"
    ADMIN_TICKETS = "admin_tickets"
    ADMIN_DEL_TICKETS = "admin_del_tickets"
    ADMIN_CONFIRM_DEL_TICKETS = "admin_confirm_del_tickets"
    ADMIN_LOG_CH = "admin_log_ch"
    ADMIN_SET_LOG_CH = "admin_set_log_ch"
    ADMIN_REPLIES = "admin_replies"
    ADMIN_ADD_REPLY = "admin_add_reply"
    ADMIN_LIST_REPLIES = "admin_list_replies"
    ADMIN_DEL_REPLY = "admin_del_reply"
    ADMIN_BANNED_WORDS = "admin_banned_words"
    ADMIN_ADD_BANNED = "admin_add_banned"
    ADMIN_LIST_BANNED = "admin_list_banned"
    ADMIN_REM_BANNED = "admin_rem_banned"
    ADMIN_CREATE_CONTEST = "admin_create_contest"
    ADMIN_DECLARE_WINNER = "admin_declare_winner"
    ADMIN_DEL_CONTEST = "admin_del_contest:"
    ADMIN_EXPORT_REPLIES = "admin_export_replies"
    ADMIN_IMPORT_REPLIES = "admin_import_replies"
    ADMIN_REFRESH_CACHE = "admin_refresh_cache"
    ADMIN_CONFIRM_IMPORT = "admin_confirm_import"
    ADMIN_IMPORT_GITHUB = "admin_import_github"
    
    AUTO_REPLY_MENU = "auto_reply_menu:"
    AUTO_REPLY_TOGGLE = "auto_reply_toggle:"
    AUTO_REPLY_ADMINS = "auto_reply_admins:"
    AUTO_REPLY_RESET = "auto_reply_reset:"
    AUTO_REPLY_CONFIRM_RESET = "auto_reply_confirm_reset:"
    AUTO_REPLY_STATS = "auto_reply_stats:"
    AUTO_REPLY_ADD = "auto_reply_add:"
    AUTO_REPLY_DEL = "auto_reply_del:"
    AUTO_REPLY_LIST = "auto_reply_list:"

# =====================================================================
# 4. مصنع الكيبوردات - يقرأ من ملف buttons_config.json
# =====================================================================

class KeyboardFactory:
    _config: Dict = None
    _config_path: str = "buttons_config.json"
    
    @classmethod
    def load_config(cls):
        if cls._config is None:
            try:
                with open(cls._config_path, "r", encoding="utf-8") as f:
                    cls._config = json.load(f)
                logger.info(f"✅ تم تحميل {cls._config_path}")
            except FileNotFoundError:
                logger.warning(f"⚠️ ملف {cls._config_path} غير موجود")
                cls._config = {"texts": {}, "menus": {}}
        return cls._config
    
    @classmethod
    def get_text(cls, key: str) -> str:
        config = cls.load_config()
        return config.get("texts", {}).get(key, key)
    
    @classmethod
    def get_menu(cls, menu_name: str) -> List[List[str]]:
        config = cls.load_config()
        menu = config.get("menus", {}).get(menu_name, {})
        return menu.get("rows", [])
    
    @classmethod
    def build(cls, menu_name: str, chat_id: int = None, extra_data: Dict = None) -> InlineKeyboardMarkup:
        rows = cls.get_menu(menu_name)
        keyboard = []
        
        for row in rows:
            btn_row = []
            for item in row:
                # معالجة الأزرار الخاصة
                if item.endswith("_url"):
                    # زر رابط
                    key = item.replace("_url", "")
                    text = cls.get_text(key)
                    url = "https://t.me/" + CONFIG.BOT_USERNAME + "?startgroup"
                    if extra_data and "url" in extra_data:
                        url = extra_data["url"]
                    btn_row.append(InlineKeyboardButton(text, url=url))
                else:
                    # زر عادي
                    text = cls.get_text(item)
                    callback = item
                    
                    # إضافة chat_id إذا كان متاحاً والزر يحتاج إليه
                    if chat_id and ":" in item:
                        callback = f"{item}{chat_id}"
                    elif chat_id and item in ["sec_close", "panel_close", "back", "main"]:
                        callback = item
                    elif chat_id:
                        callback = f"{item}:{chat_id}"
                    
                    btn_row.append(InlineKeyboardButton(text, callback_data=callback))
            
            keyboard.append(btn_row)
        
        return InlineKeyboardMarkup(keyboard)
    
    @classmethod
    def _status_icon(cls, value: bool) -> str:
        return "✅" if value else "❌"
    
    @classmethod
    async def _format_security_text(cls, settings: dict) -> str:
        st = cls._status_icon
        lines = [
            "🔐 **إعدادات الأمان**",
            "━━━━━━━━━━━━━━━━━━━━\n",
            "🛡️ **الحماية**",
            f"🔗 الروابط: {st(settings.get('delete_links', False))}",
            f"👤 المعرفات: {st(settings.get('mentions', False))}",
            f"🌊 الفيضان: {st(settings.get('antiflood_enabled', False))}\n",
            "🎬 **المحتوى**",
            f"🎬 فيديو: {st(settings.get('delete_videos', False))}",
            f"🎵 موسيقى: {st(settings.get('delete_audio', False))}",
            f"🎞️ متحرك: {st(settings.get('delete_animation', False))}",
            f"🎤 صوتي: {st(settings.get('delete_voice', False))}",
            f"🎥 فيديو نوت: {st(settings.get('delete_video_note', False))}",
            f"🖼️ ملصقات: {st(settings.get('delete_stickers', False))}",
            f"📄 ملفات: {st(settings.get('delete_documents', False))}",
            f"📨 مُعاد: {st(settings.get('delete_forwarded', False))}",
            f"📊 استطلاع: {st(settings.get('delete_polls', False))}",
            f"🎮 ألعاب: {st(settings.get('delete_games', False))}",
            f"🛠️ خدمة: {st(settings.get('delete_service', False))}\n",
            "👋 **الترحيب**",
            f"🎯 ترحيب: {st(settings.get('welcome_enabled', False))}",
            f"👋 وداع: {st(settings.get('goodbye_enabled', False))}\n",
            "⚙️ **القيود**",
            f"⏱️ بطيء: {st(settings.get('slow_mode', False))} ({settings.get('slow_mode_seconds', 5)}ث)",
            f"📏 طول: {settings.get('max_message_length', 0) or 'غير محدود'}",
            f"🌙 ليلي: {st(settings.get('night_mode_enabled', False))}",
            f"⚠️ تحذيرات: {settings.get('max_warnings', 3)}\n",
            "⚖️ **العقوبات**",
            f"🗑️ حذف: {settings.get('delete_penalty', 'none')}",
            f"⚖️ أساسية: {settings.get('auto_penalty', 'none')}",
            "━━━━━━━━━━━━━━━━━━━━"
        ]
        return "\n".join(lines)
# =====================================================================
# 5. دوال مساعدة
# =====================================================================

async def safe_send(bot, user_id: int, text: str, reply_markup=None, parse_mode="Markdown", **kwargs):
    """إرسال رسالة بأمان مع دعم المشرفين المخفيين"""
    try:
        if user_id == 777000:
            logger.info(f"تجاهل إرسال رسالة لمشرف مخفي (777000)")
            return None
        if user_id < 0 and user_id != 777000:
            logger.info(f"تجاهل إرسال رسالة لمعرف غير صالح: {user_id}")
            return None
        
        if reply_markup:
            result = await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                **kwargs
            )
        else:
            result = await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=parse_mode,
                **kwargs
            )
        return result
    except Exception as e:
        error_msg = str(e).lower()
        if "bot" in error_msg or "user_bot" in error_msg:
            logger.warning(f"تجاهل إرسال لمشرف مخفي {user_id}: {e}")
            return None
        elif "blocked" in error_msg or "deactivated" in error_msg:
            logger.warning(f"المستخدم {user_id} قام بحظر البوت أو غير نشط")
            return None
        else:
            logger.error(f"فشل إرسال الرسالة إلى {user_id}: {e}")
            return None

async def get_text(lang: str, key: str, **kwargs):
    """الحصول على نص مترجم"""
    texts = {
        'ar': {
            'main_menu': "🎯 **القائمة الرئيسية**\n\n👤 معرفك: `{user_id}`\n📊 المجموعات: {groups}\n💎 الاشتراك: {sub}\n📡 القناة النشطة: {channel}\n📝 المنشورات غير المنشورة: {pending}\n⚙️ النشر التلقائي: {auto}",
            'groups': "👥 المجموعات",
            'add_channel': "➕ إضافة قناة",
            'my_channels': "📡 قنواتي",
            'settings': "⚙️ الإعدادات",
            'add_posts': "📝 إضافة منشورات",
            'publish_one': "📤 نشر واحد",
            'my_posts': "📋 منشوراتي",
            'recycle': "♻️ تدوير",
            'stats': "📊 إحصائيات",
            'help': "🆘 مساعدة",
            'trial': "🎁 تجربة",
            'subscribe': "💎 اشتراك",
            'developer': "👨‍💻 المطور",
            'language': "🌐 اللغة",
            'support': "📞 الدعم",
            'referral': "👥 إحالات",
            'reminder': "⏰ تذكير",
            'translation': "🌍 ترجمة",
            'contests': "🏆 مسابقات",
            'add_group': "➕ إضافة مجموعة",
            'admin_panel_btn': "🛠️ لوحة الأدمن",
            'publish_all': "📤 نشر الكل",
            'settings_auto': "⚙️ النشر التلقائي: {status}",
            'settings_header': "⚙️ **الإعدادات**",
            'back': "🔙 رجوع",
            'close': "🔙 إغلاق",
            'plan_selector': "💎 **اختر الباقة المناسبة**",
            'subscribe_1_day': "💎 يوم واحد",
            'subscribe_7_days': "💎 7 أيام",
            'subscribe_30_days': "💎 30 يوم",
            'subscribe_90_days': "💎 90 يوم",
            'not_authorized': "❌ غير مصرح لك باستخدام هذا الأمر",
            'subscription_expired': "❌ اشتراكك منتهي أو لا يوجد اشتراك",
            'no_active_channel': "❌ لا توجد قناة نشطة",
            'max_posts_reached': "❌ لقد وصلت للحد الأقصى للمنشورات",
            'enter_posts': "📝 أرسل المنشورات (عدد: {count})",
            'post_saved': "✅ تم حفظ المنشور ({saved}/{target})\nتبقى {remaining}",
            'all_posts_saved': "✅ تم حفظ جميع المنشورات",
            'publish_success': "✅ تم النشر بنجاح",
            'publish_fail': "❌ فشل النشر: {error}",
            'posts_empty': "📭 لا توجد منشورات",
            'my_posts_title': "📋 **منشوراتي**",
            'enter_channel_id': "📡 أرسل معرف القناة (مثل @channel أو -100123456789)",
            'invalid_format': "❌ صيغة غير صالحة",
            'invalid_channel': "❌ هذا ليس قناة",
            'channel_exists': "❌ القناة موجودة مسبقاً",
            'channels_empty': "📭 لا توجد قنوات",
            'schedule_current': "⏰ **الجدولة الحالية**\nالنوع: {type}",
            'enter_minutes': "⏱️ أرسل عدد الدقائق (1-1440):",
            'enter_hours': "⏱️ أرسل عدد الساعات (1-168):",
            'enter_days': "⏱️ أرسل عدد الأيام (1-365):",
            'enter_publish_time': "🕐 أرسل وقت النشر (مثل 14:30):",
            'schedule_updated_ok': "✅ تم تحديث الجدولة",
            'trial_activated': "🎁 تم تفعيل النسخة التجريبية لمدة {days} أيام",
            'trial_used': "❌ لقد استخدمت النسخة التجريبية بالفعل",
            'send_support_message': "📝 أرسل رسالتك وسيتم إيصالها للدعم",
            'support_ticket_created': "✅ تم إنشاء التذكرة #{num}",
            'help_text': "🆘 **المساعدة**\n\n/publish - نشر المنشورات\n/add - إضافة قناة\n/mychannels - عرض قنواتي\n/security - إعدادات الأمان\n/panel - لوحة التحكم",
            'admin_panel': "🛠️ **لوحة الأدمن**",
            'admin_users': "👥 المستخدمين: {users}\n⛔ المحظورين: {banned}",
            'admin_banned_list': "⛔ **المحظورين**\n{list}",
            'admin_unbanned_all': "✅ تم إلغاء حظر الجميع",
            'admin_channels_list': "📡 **القنوات**\n{list}",
            'admin_groups_list': "👥 **المجموعات**\n{list}",
            'admin_add_admin': "👑 أرسل معرف المستخدم لإضافته كمشرف:",
            'admin_rem_admin': "🗑️ أرسل معرف المستخدم لإزالته من المشرفين:",
            'admin_added': "✅ تم إضافة `{user}` كمشرف",
            'admin_removed': "✅ تم إزالة `{user}` من المشرفين",
            'admin_ram': "🖥️ **الرام**\nالمستخدم: {used} MB / {total} MB\nالنسبة: {percent}%",
            'admin_stats_text': "📊 **الإحصائيات**\n👥 المستخدمين: {users}\n⛔ المحظورين: {banned}\n📝 المنشورات: {posts}\n👥 المجموعات: {groups}\n📡 القنوات: {channels}",
            'admin_metrics': "📊 **المراقبة**\n👤 نشطاء: {active}\n📝 اليوم: {today}\n💾 قاعدة البيانات: {db_size:.2f} MB\n📡 API: {api_calls}\n❌ أخطاء: {errors}\n⏱️ وقت التشغيل: {uptime}",
            'admin_backup_created': "✅ تم إنشاء نسخة احتياطية: {filename}",
            'admin_backup_failed': "❌ فشل النسخ الاحتياطي: {error}",
            'admin_restore_choose': "🔄 اختر النسخة لاستعادتها:",
            'admin_restore_success': "✅ تمت الاستعادة بنجاح",
            'admin_restore_failed': "❌ فشل الاستعادة: {error}",
            'admin_broadcast_confirm': "📨 **تأكيد البث**\n\nالرسالة:\n{text}\n\nهل أنت متأكد؟",
            'admin_broadcast_sent': "✅ تم إرسال البث لـ {sent} مستخدم",
            'no_backups': "📭 لا توجد نسخ احتياطية",
            'no_tickets': "📭 لا توجد تذاكر",
            'tickets_list': "📋 **التذاكر**\n{tickets}",
            'confirm_delete_tickets': "🗑️ هل أنت متأكد من حذف جميع التذاكر؟",
            'tickets_deleted': "✅ تم حذف جميع التذاكر",
            'admin_force_sub_set': "✅ تم تعيين قناة الاشتراك الإجباري: @{channel}",
            'admin_log_channel_set': "✅ تم تعيين قناة السجلات: {channel}",
            'admin_update_sent': "✅ تم إرسال التحديث",
            'admin_update_failed': "❌ فشل إرسال التحديث",
            'admin_update_channel_set': "✅ تم تعيين قناة التحديثات: @{channel}",
            'admin_contest_declared': "🏆 تم إعلان فائز مسابقة {title}: `{winner}`",
            'admin_contest_no_participants': "❌ لا يوجد مشاركين في هذه المسابقة",
            'admin_contest_deleted': "✅ تم حذف المسابقة",
            'admin_banned_words_global': "🚫 **الكلمات المحظورة عالمياً**\n{words}",
            'import_from_github_prompt': "📥 أرسل رابط ملف JSON من GitHub:",
            'import_github_invalid_url': "❌ رابط غير صالح",
            'import_github_loading': "⏳ جاري التحميل...",
            'import_github_failed': "❌ فشل التحميل",
            'import_github_success': "✅ تم استيراد {count} رد",
            'import_github_error': "❌ خطأ: {error}",
            'file_not_found': "❌ الملف غير موجود",
            'no_banned_words': "📭 لا توجد كلمات محظورة",
            'enter_word': "📝 أرسل الكلمة لإضافتها:",
            'enter_word_to_remove': "📝 أرسل الكلمة لحذفها:",
            'word_added': "✅ تم إضافة الكلمة: `{word}`",
            'word_removed': "✅ تم حذف الكلمة: `{word}`",
            'word_exists': "⚠️ الكلمة `{word}` موجودة مسبقاً",
            'word_too_short': "❌ الكلمة قصيرة جداً (حد أدنى حرفين)",
            'word_not_found': "❌ الكلمة غير موجودة",
            'enter_keyword': "📝 أرسل الكلمة المفتاحية:",
            'enter_reply': "📝 أرسل الرد:",
            'auto_reply_added': "✅ تم إضافة رد لـ `{keyword}`",
            'auto_reply_deleted': "✅ تم حذف رد `{keyword}`",
            'auto_reply_not_found': "❌ رد `{keyword}` غير موجود",
            'auto_reply_enabled': "مفعل ✅",
            'auto_reply_disabled': "معطل ❌",
            'auto_reply_mode_admins': "للمشرفين فقط",
            'auto_reply_mode_all': "للجميع",
            'auto_reply_settings': "📝 **إعدادات الردود التلقائية**",
            'auto_reply_stats': "📊 **إحصائيات الردود**\n{stats}",
            'auto_reply_list': "📋 **قائمة الردود**\n{replies}",
            'no_auto_replies': "📭 لا توجد ردود تلقائية",
            'no_auto_reply_stats': "📭 لا توجد إحصائيات",
            'contest_no_active': "🏆 لا توجد مسابقات نشطة",
            'contest_created': "✅ تم إنشاء المسابقة برقم {id}",
            'contest_joined': "✅ تم التسجيل في المسابقة",
            'contest_winners': "🏆 **الفائزون**\n{winners}",
            'no_contest_winners': "🏆 لا يوجد فائزين حتى الآن",
            'contest_not_found': "❌ المسابقة غير موجودة",
            'no_active_contests': "❌ لا توجد مسابقات نشطة",
            'referral_header': "👥 **الإحالات**\n\nرابط الإحالة: [اضغط هنا]({link})\nالإجمالي: {total}\nالمتاح للصرف: {available}",
            'referral_claimed': "🎁 تم صرف {days} أيام",
            'referral_list': "📋 **قائمة الإحالات**\n{list}",
            'no_referrals': "📭 لا توجد إحالات",
            'claim_reward': "🎁 صرف المكافأة",
            'reminder_header': "⏰ **إعدادات التذكيرات**",
            'reminder_days_updated': "✅ تم تحديث عدد الأيام إلى {days}",
            'translation_set': "✅ تم تغيير اللغة إلى {lang}",
            'translation_off': "🚫 تم إيقاف الترجمة",
            'warning_settings': "⚠️ **إعدادات التحذيرات**\nالحد الأقصى: {max_warnings}\nالعقوبة: {warn_penalty}",
            'warning_count_updated': "✅ تم تحديث عدد التحذيرات إلى {count}",
            'admin_stats': "📊 الإحصائيات",
            'admin_banned': "⛔ المحظورين",
            'admin_groups': "👥 المجموعات",
            'admin_metrics': "📊 المراقبة"
        }
    }
    
    lang_texts = texts.get(lang, texts.get('ar', {}))
    template = lang_texts.get(key, key)
    
    try:
        return template.format(**kwargs)
    except KeyError:
        return template

async def check_bot_permissions(bot, chat_id: int) -> Dict:
    """التحقق من صلاحيات البوت في المجموعة"""
    try:
        member = await bot.get_chat_member(chat_id, bot.id)
        if member.status == 'administrator':
            return {
                'can_act': True,
                'can_delete': member.can_delete_messages,
                'can_restrict': member.can_restrict_members,
                'can_pin': member.can_pin_messages,
                'can_promote': member.can_promote_members
            }
        return {'can_act': False}
    except:
        return {'can_act': False}

async def is_authorized_in_group(bot, chat_id: int, user_id: int) -> bool:
    """التحقق من أن المستخدم مصرح له في المجموعة"""
    try:
        # المالك الأساسي
        if user_id == CONFIG.PRIMARY_OWNER_ID:
            return True
        
        # مشرف مخفي
        if user_id == CONFIG.ANONYMOUS_ADMIN_ID:
            return True
        
        # التحقق من الصلاحيات
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

def invalidate_auth_cache(chat_id: int, user_id: int):
    """إبطال الكاش للصلاحيات"""
    pass

# =====================================================================
# 6. قاعدة بيانات محاكاة
# =====================================================================

class Database:
    _instance = None
    _data = {}
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self):
        if not self._initialized:
            self._data = {
                'users': {},
                'channels': {},
                'groups': {},
                'posts': {},
                'settings': {},
                'admins': [CONFIG.PRIMARY_OWNER_ID],
                'security': {},
                'auto_reply': {},
                'subscriptions': {},
                'referrals': {},
                'tickets': [],
                'reminders': {},
                'contests': {},
                'admin_logs': [],
                'schedules': {},
                'banned_words': {},
                'user_warnings': {}
            }
            self._initialized = True
            logger.info("✅ قاعدة البيانات مهيأة")
        return self
    
    async def execute(self, query: str, params: tuple = None):
        return None
    
    async def fetchone(self, query: str, params: tuple = None):
        return None
    
    async def fetchall(self, query: str, params: tuple = None):
        return []
    
    async def fetchval(self, query: str, params: tuple = None):
        return None

DB = Database()

# =====================================================================
# 7. المستودعات (Repositories) - محاكاة
# =====================================================================

class UserRepository:
    @staticmethod
    async def register(user_id: int):
        db = await DB.initialize()
        if user_id not in db._data['users']:
            db._data['users'][user_id] = {
                'banned': False,
                'auto_publish': False,
                'language': 'ar',
                'trial_used': False,
                'subscription_end': None,
                'referral_code': f"ref_{user_id}"
            }
        return True
    
    @staticmethod
    async def get_language(user_id: int) -> str:
        db = await DB.initialize()
        user = db._data['users'].get(user_id, {})
        return user.get('language', 'ar')
    
    @staticmethod
    async def set_language(user_id: int, lang: str):
        db = await DB.initialize()
        if user_id in db._data['users']:
            db._data['users'][user_id]['language'] = lang
        return True
    
    @staticmethod
    async def get_auto_status(user_id: int) -> bool:
        db = await DB.initialize()
        user = db._data['users'].get(user_id, {})
        return user.get('auto_publish', False)
    
    @staticmethod
    async def set_auto(user_id: int, status: bool):
        db = await DB.initialize()
        if user_id in db._data['users']:
            db._data['users'][user_id]['auto_publish'] = status
        return True
    
    @staticmethod
    async def is_banned(user_id: int) -> bool:
        db = await DB.initialize()
        user = db._data['users'].get(user_id, {})
        return user.get('banned', False)
    
    @staticmethod
    async def has_active_subscription(user_id: int) -> bool:
        db = await DB.initialize()
        user = db._data['users'].get(user_id, {})
        end = user.get('subscription_end')
        if end:
            return datetime.fromisoformat(end) > datetime.utcnow()
        return False
    
    @staticmethod
    async def has_used_trial(user_id: int) -> bool:
        db = await DB.initialize()
        user = db._data['users'].get(user_id, {})
        return user.get('trial_used', False)
    
    @staticmethod
    async def activate_trial(user_id: int) -> int:
        db = await DB.initialize()
        if user_id in db._data['users']:
            db._data['users'][user_id]['trial_used'] = True
            db._data['users'][user_id]['subscription_end'] = (datetime.utcnow() + timedelta(days=3)).isoformat()
        return 3
    
    @staticmethod
    async def get_stats() -> Dict:
        db = await DB.initialize()
        users = db._data['users']
        return {
            'users': len(users),
            'banned': sum(1 for u in users.values() if u.get('banned')),
            'posts': 0,
            'groups': len(db._data['groups']),
            'channels': len(db._data['channels'])
        }
    
    @staticmethod
    async def get_all_users():
        db = await DB.initialize()
        return [(uid, 1 if u.get('banned') else 0) for uid, u in db._data['users'].items()]
    
    @staticmethod
    async def update_username(user_id: int, username: str, first_name: str):
        pass
    
    @staticmethod
    async def get_referral_code(user_id: int) -> str:
        db = await DB.initialize()
        user = db._data['users'].get(user_id, {})
        return user.get('referral_code', f"ref_{user_id}")
    
    @staticmethod
    async def get_user_by_referral_code(code: str):
        db = await DB.initialize()
        for uid, u in db._data['users'].items():
            if u.get('referral_code') == code:
                return uid
        return None

class ChannelRepository:
    @staticmethod
    async def add(user_id: int, channel_id: str, channel_name: str) -> int:
        db = await DB.initialize()
        ch_id = len(db._data['channels']) + 1
        db._data['channels'][ch_id] = {
            'user_id': user_id,
            'channel_id': channel_id,
            'channel_name': channel_name,
            'banned': False
        }
        return ch_id
    
    @staticmethod
    async def get_all(user_id: int):
        db = await DB.initialize()
        return [{'id': cid, **c} for cid, c in db._data['channels'].items() if c.get('user_id') == user_id]
    
    @staticmethod
    async def get_active(user_id: int):
        db = await DB.initialize()
        for cid, c in db._data['channels'].items():
            if c.get('user_id') == user_id and not c.get('banned'):
                return cid
        return None
    
    @staticmethod
    async def set_active(user_id: int, ch_id: int):
        return True
    
    @staticmethod
    async def delete(user_id: int, ch_id: int):
        db = await DB.initialize()
        if ch_id in db._data['channels']:
            del db._data['channels'][ch_id]
        return True
    
    @staticmethod
    async def get_info(ch_id: int):
        db = await DB.initialize()
        c = db._data['channels'].get(ch_id)
        if c:
            return {'channel_name': c['channel_name'], 'channel_id': c['channel_id']}
        return None
    
    @staticmethod
    async def get_stats(ch_id: int):
        return {'total': 0, 'published': 0, 'unpublished': 0}

class GroupRepository:
    @staticmethod
    async def register(chat_id: int, chat_name: str, user_id: int, username: str = None):
        db = await DB.initialize()
        if chat_id not in db._data['groups']:
            db._data['groups'][chat_id] = {
                'chat_name': chat_name,
                'username': username,
                'banned': False,
                'admins': [user_id]
            }
        return True
    
    @staticmethod
    async def get_user_groups(user_id: int):
        db = await DB.initialize()
        return [(gid, g.get('chat_name', ''), g.get('username', ''), g.get('banned', False)) 
                for gid, g in db._data['groups'].items()]
    
    @staticmethod
    async def sync_admins(chat_id: int, bot):
        db = await DB.initialize()
        if chat_id in db._data['groups']:
            try:
                admins = await bot.get_chat_administrators(chat_id)
                admin_ids = [a.user.id for a in admins]
                db._data['groups'][chat_id]['admins'] = admin_ids
                return len(admin_ids)
            except:
                pass
        return 0
    
    @staticmethod
    async def link_user_to_group(user_id: int, chat_id: int):
        pass
    
    @staticmethod
    async def unlink_user_from_group(user_id: int, chat_id: int):
        pass

class PostRepository:
    @staticmethod
    async def get_unpublished_count(ch_id: int) -> int:
        return 0
    
    @staticmethod
    async def get_user_unpublished(user_id: int) -> int:
        return 0
    
    @staticmethod
    async def get_user_total(user_id: int) -> int:
        return 0
    
    @staticmethod
    async def get_next(ch_id: int):
        return None
    
    @staticmethod
    async def get_user_posts(ch_id: int, limit: int):
        return []
    
    @staticmethod
    async def save(ch_id: int, posts: list):
        return True
    
    @staticmethod
    async def mark_published(post_id: int):
        return True
    
    @staticmethod
    async def increment_fail(post_id: int):
        return True
    
    @staticmethod
    async def delete_single(post_id: int, user_id: int, ch_id: int):
        return True
    
    @staticmethod
    async def reset_all(ch_id: int):
        return True

class SecurityRepository:
    _cache = {}
    
    @staticmethod
    async def get(chat_id: int, force_refresh: bool = False):
        db = await DB.initialize()
        if chat_id not in db._data['security']:
            db._data['security'][chat_id] = {
                'delete_links': False,
                'mentions': False,
                'delete_videos': False,
                'delete_audio': False,
                'delete_animation': False,
                'delete_voice': False,
                'delete_video_note': False,
                'delete_stickers': False,
                'delete_documents': False,
                'delete_forwarded': False,
                'delete_polls': False,
                'delete_games': False,
                'delete_service': False,
                'welcome_enabled': False,
                'goodbye_enabled': False,
                'slow_mode': False,
                'slow_mode_seconds': 5,
                'max_message_length': 0,
                'night_mode_enabled': False,
                'max_warnings': 3,
                'delete_penalty': 'none',
                'auto_penalty': 'none',
                'antiflood_enabled': False,
                'warn_penalty': 'ban'
            }
        return db._data['security'][chat_id]
    
    @staticmethod
    async def set(chat_id: int, **kwargs):
        db = await DB.initialize()
        if chat_id not in db._data['security']:
            db._data['security'][chat_id] = {}
        db._data['security'][chat_id].update(kwargs)
        SecurityRepository._cache.pop(chat_id, None)
        return True
    
    @staticmethod
    def invalidate_cache(chat_id: int):
        SecurityRepository._cache.pop(chat_id, None)
    
    @staticmethod
    async def get_banned_words(chat_id: int):
        db = await DB.initialize()
        return db._data['banned_words'].get(chat_id, [])
    
    @staticmethod
    async def add_banned_word(word: str, chat_id: int, user_id: int):
        db = await DB.initialize()
        if chat_id not in db._data['banned_words']:
            db._data['banned_words'][chat_id] = []
        if word in db._data['banned_words'][chat_id]:
            return False, True
        db._data['banned_words'][chat_id].append(word)
        return True, False
    
    @staticmethod
    async def remove_banned_word(word: str, chat_id: int):
        db = await DB.initialize()
        if chat_id in db._data['banned_words']:
            if word in db._data['banned_words'][chat_id]:
                db._data['banned_words'][chat_id].remove(word)
                return True
        return False

class ScheduleRepository:
    @staticmethod
    async def get(ch_id: int):
        return {'type': 'غير محدد'}
    
    @staticmethod
    async def save(ch_id: int, schedule_type: str, **kwargs):
        return True
    
    @staticmethod
    async def set_last_publish(ch_id: int, time):
        return True
    
    @staticmethod
    async def update_next(ch_id: int):
        return True

class BotAdminRepository:
    @staticmethod
    async def is_admin(user_id: int) -> bool:
        db = await DB.initialize()
        return user_id in db._data['admins']
    
    @staticmethod
    async def add(user_id: int):
        db = await DB.initialize()
        if user_id not in db._data['admins']:
            db._data['admins'].append(user_id)
        return True
    
    @staticmethod
    async def remove(user_id: int):
        db = await DB.initialize()
        if user_id in db._data['admins']:
            db._data['admins'].remove(user_id)
        return True
    
    @staticmethod
    async def get_all_admins():
        db = await DB.initialize()
        return db._data['admins']

class SettingRepository:
    @staticmethod
    async def get_force_subscribe_channel():
        return None
    
    @staticmethod
    async def get_updates_channel():
        return None
    
    @staticmethod
    async def get_log_channel_id():
        return None
    
    @staticmethod
    async def get_publish_interval():
        return 60
    
    @staticmethod
    async def get_auto_backup():
        return True
    
    @staticmethod
    async def set(key: str, value: str):
        return True

class ChatLockRepository:
    @staticmethod
    async def is_locked(chat_id: int) -> bool:
        return False
    
    @staticmethod
    async def set_lock(chat_id: int, locked: bool, user_id: int = None):
        return True

class ReferralRepository:
    @staticmethod
    async def add(referrer: int, user_id: int) -> bool:
        return True
    
    @staticmethod
    async def auto_reward(referrer: int) -> int:
        return 1
    
    @staticmethod
    async def get_stats(user_id: int):
        return {'total': 0, 'available': 0}
    
    @staticmethod
    async def claim(user_id: int) -> int:
        return 0
    
    @staticmethod
    async def get_list(user_id: int):
        return []

class ReminderRepository:
    @staticmethod
    async def get_settings(user_id: int):
        return {'sub': False, 'daily': False, 'weekly': False, 'days': 3}
    
    @staticmethod
    async def update_settings(user_id: int, **kwargs):
        return True
    
    @staticmethod
    async def get_users_needing_reminder():
        return []

class ContestRepository:
    @staticmethod
    async def get_active(limit: int):
        return []
    
    @staticmethod
    async def get_winners(limit: int):
        return []
    
    @staticmethod
    async def participate(user_id: int, contest_id: int, answer: str):
        return True
    
    @staticmethod
    async def create(user_id: int, title: str, desc: str, prize: str, end_date):
        return 1
    
    @staticmethod
    async def set_winner(contest_id: int, winner_id: int):
        return True
    
    @staticmethod
    async def delete(contest_id: int, user_id: int):
        return True

class AutoReplyRepository:
    @staticmethod
    async def get_settings(chat_id: int):
        db = await DB.initialize()
        if chat_id not in db._data['auto_reply']:
            db._data['auto_reply'][chat_id] = {
                'enabled': False,
                'only_admins': False,
                'ignore_bots': True
            }
        return db._data['auto_reply'][chat_id]
    
    @staticmethod
    async def set_enabled(chat_id: int, enabled: bool):
        db = await DB.initialize()
        if chat_id not in db._data['auto_reply']:
            db._data['auto_reply'][chat_id] = {}
        db._data['auto_reply'][chat_id]['enabled'] = enabled
        return True
    
    @staticmethod
    async def set_only_admins(chat_id: int, only_admins: bool):
        db = await DB.initialize()
        if chat_id not in db._data['auto_reply']:
            db._data['auto_reply'][chat_id] = {}
        db._data['auto_reply'][chat_id]['only_admins'] = only_admins
        return True
    
    @staticmethod
    async def reset(chat_id: int):
        return True
    
    @staticmethod
    async def get_stats(chat_id: int, limit: int):
        return []
    
    @staticmethod
    async def add_reply(chat_id: int, keyword: str, reply: str, **kwargs):
        return True
    
    @staticmethod
    async def remove_reply(chat_id: int, keyword: str) -> bool:
        return True
    
    @staticmethod
    async def get_reply(keyword: str, chat_id: int):
        return None
    
    @staticmethod
    async def reload_from_file():
        return True
    
    @staticmethod
    async def import_from_json_data(chat_id: int, data: dict, overwrite: bool = False) -> int:
        return 0

class TicketRepository:
    @staticmethod
    async def get_next_number():
        return 0
    
    @staticmethod
    async def save(user_id: int, username: str, content: str, num: int, media_type: str = None, media_file_id: str = None):
        return True
    
    @staticmethod
    async def get_all():
        return []
    
    @staticmethod
    async def delete_all():
        return True

class StateManager:
    _states = {}
    _data = {}
    
    @classmethod
    def get(cls, user_id: int):
        return cls._states.get(user_id)
    
    @classmethod
    def set(cls, user_id: int, state):
        cls._states[user_id] = state
    
    @classmethod
    def clear(cls, user_id: int):
        cls._states.pop(user_id, None)
        cls._data.pop(user_id, None)

class UserState:
    WAIT_CHANNEL = "wait_channel"
    ADDING_POSTS = "adding_posts"
    WAIT_MIN = "wait_min"
    WAIT_HOUR = "wait_hour"
    WAIT_DAY = "wait_day"
    WAIT_PUB_TIME = "wait_pub_time"
    WAIT_GROUP_BAN = "wait_group_ban"
    WAIT_REM_GROUP_BAN = "wait_rem_group_ban"
    WAIT_GLOBAL_BAN = "wait_global_ban"
    WAIT_REM_GLOBAL_BAN = "wait_rem_global_ban"
    WAIT_ADMIN_ADD = "wait_admin_add"
    WAIT_ADMIN_REM = "wait_admin_rem"
    WAIT_BROADCAST = "wait_broadcast"
    WAIT_UPDATE = "wait_update"
    WAIT_UPDATE_CH = "wait_update_ch"
    WAIT_FORCE = "wait_force"
    WAIT_REM_DAYS = "wait_rem_days"
    WAIT_BAN = "wait_ban"
    WAIT_MUTE = "wait_mute"
    WAIT_WARN = "wait_warn"
    WAIT_KICK = "wait_kick"
    WAIT_RESTRICT = "wait_restrict"
    WAIT_UNBAN = "wait_unban"
    WAIT_PIN = "wait_pin"
    WAIT_CONTEST_TITLE = "wait_contest_title"
    WAIT_CONTEST_DESC = "wait_contest_desc"
    WAIT_CONTEST_PRIZE = "wait_contest_prize"
    WAIT_CONTEST_DATE = "wait_contest_date"
    WAIT_CONTEST_ANSWER = "wait_contest_answer"
    WAIT_AUTO_KEY = "wait_auto_key"
    WAIT_AUTO_REPLY = "wait_auto_reply"
    WAIT_REPLY_BUTTONS = "wait_reply_buttons"
    WAIT_AUTO_DEL = "wait_auto_del"
    WAIT_KEYWORD = "wait_keyword"
    WAIT_REPLY = "wait_reply"
    WAIT_LOG_CH = "wait_log_ch"
    WAIT_MAX_LEN = "wait_max_len"
    WAIT_WARN_COUNT = "wait_warn_count"
    SUPPORT_MODE = "support_mode"
    WAIT_IMPORT_FILE = "wait_import_file"
    WAIT_GITHUB_URL = "wait_github_url"
# =====================================================================
# 8. معالج الأوامر - CommandHandlers
# =====================================================================

class CommandHandlers:
    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        username = update.effective_user.username or ""
        first_name = update.effective_user.first_name or ""
        await UserRepository.register(user_id)
        
        args = context.args
        if args and args[0].startswith('ref_'):
            ref_code = args[0][4:]
            referrer = await UserRepository.get_user_by_referral_code(ref_code)
            if referrer and referrer != user_id and not await UserRepository.is_banned(referrer):
                if await ReferralRepository.add(referrer, user_id):
                    reward = await ReferralRepository.auto_reward(referrer)
                    await safe_send(update.effective_chat.bot, referrer, f"🎁 تمت إحالة `{user_id}` (+{reward} يوم)")
        
        lang = await UserRepository.get_language(user_id)
        channels = await ChannelRepository.get_all(user_id)
        active = await ChannelRepository.get_active(user_id)
        cnt = 0
        ch_display = "لا توجد قنوات"
        if active:
            cnt = await PostRepository.get_unpublished_count(active)
            ch_info = await ChannelRepository.get_info(active)
            if ch_info:
                ch_display = f"{ch_info['channel_name']} ({ch_info['channel_id']})"
        groups = len(await GroupRepository.get_user_groups(user_id))
        has_sub = await UserRepository.has_active_subscription(user_id)
        sub_text = "✅ مفعل" if has_sub else "❌ غير مفعل"
        auto = await UserRepository.get_auto_status(user_id)
        auto_text = "مفعل" if auto else "معطل"
        
        title = await get_text(lang, 'main_menu',
                         user_id=user_id,
                         groups=groups,
                         sub=sub_text,
                         channel=ch_display,
                         pending=cnt,
                         auto=auto_text)
        
        kb = KeyboardFactory.build("main_menu")
        await safe_send(context.bot, user_id, title, reply_markup=kb)

    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        await safe_send(context.bot, user_id, await get_text(lang, 'help_text'))

    @staticmethod
    async def trial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        if await UserRepository.has_used_trial(user_id):
            await safe_send(context.bot, user_id, await get_text(lang, 'trial_used'))
            return
        days = await UserRepository.activate_trial(user_id)
        await safe_send(context.bot, user_id, await get_text(lang, 'trial_activated', days=days))

    @staticmethod
    async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        kb = KeyboardFactory.build("plans")
        await safe_send(context.bot, user_id, await get_text(lang, 'plan_selector'), reply_markup=kb)

    @staticmethod
    async def support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        kb = KeyboardFactory.build("support")
        await safe_send(context.bot, user_id, await get_text(lang, 'send_support_message'), reply_markup=kb)

    @staticmethod
    async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        await safe_send(context.bot, user_id, f"👨‍💻 {CONFIG.BOT_NAME}\n@RelaxMgr")

    @staticmethod
    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        stats = await UserRepository.get_stats()
        await safe_send(context.bot, user_id,
                        await get_text(lang, 'admin_stats',
                                 users=stats['users'],
                                 banned=stats['banned'],
                                 posts=stats['posts'],
                                 groups=stats['groups'],
                                 channels=stats['channels']))

    @staticmethod
    async def security(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, await get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        lang = await UserRepository.get_language(user_id)
        settings = await SecurityRepository.get(chat_id)
        text = await KeyboardFactory._format_security_text(settings)
        kb = KeyboardFactory.build("security", chat_id)
        await safe_send(context.bot, user_id, text, reply_markup=kb)

    @staticmethod
    async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, await get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        kb = KeyboardFactory.build("panel", chat_id)
        await safe_send(context.bot, user_id, "📋 لوحة تحكم المجموعة", reply_markup=kb)

    @staticmethod
    async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, await get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        await ChatLockRepository.set_lock(chat_id, True, user_id)
        await safe_send(context.bot, user_id, "🔒 تم القفل")

    @staticmethod
    async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type not in ['group', 'supergroup']:
            return
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not await is_authorized_in_group(context.bot, chat_id, user_id):
            await safe_send(context.bot, user_id, await get_text(await UserRepository.get_language(user_id), 'not_authorized'))
            return
        await ChatLockRepository.set_lock(chat_id, False)
        await safe_send(context.bot, user_id, "🔓 تم الفتح")

    @staticmethod
    async def contests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        contests = await ContestRepository.get_active(10)
        if not contests:
            await safe_send(context.bot, user_id, await get_text(lang, 'contest_no_active'))
            return
        text = "🏆 **المسابقات**\n"
        kb = KeyboardFactory.build("contests")
        for c in contests:
            text += f"• {c['title']} - {c['participants']} مشارك\n"
        await safe_send(context.bot, user_id, text, reply_markup=kb)

    @staticmethod
    async def language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇸🇦 عربي", callback_data=CB.LANG_AR),
             InlineKeyboardButton("🇬🇧 English", callback_data=CB.LANG_EN)],
            [InlineKeyboardButton(await get_text('ar', 'back'), callback_data=CB.BACK)]
        ])
        await safe_send(context.bot, user_id, "🌐 اختر اللغة", reply_markup=kb)

    @staticmethod
    async def syncgroup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or update.effective_chat.type not in ['group', 'supergroup']:
            await safe_send(context.bot, update.effective_user.id, "❌ هذا الأمر يستخدم فقط في المجموعات")
            return
        
        chat_id = update.effective_chat.id
        chat_name = update.effective_chat.title or "بدون اسم"
        user_id = update.effective_user.id
        lang = await UserRepository.get_language(user_id)
        
        # التحقق من أن المستخدم ليس بوتاً
        if user_id < 0:
            await safe_send(context.bot, chat_id, "❌ البوتات لا تستطيع استخدام هذا الأمر")
            return
        
        await GroupRepository.register(chat_id, chat_name, user_id, update.effective_chat.username)
        bot_perms = await check_bot_permissions(context.bot, chat_id)
        
        if not bot_perms.get('can_act', False):
            msg = f"⚠️ **البوت ليس مشرفاً في المجموعة!**\n\n"
            msg += f"📌 تم تسجيل المجموعة `{chat_name}`.\n\n"
            msg += f"🔹 **لتفعيل الميزات المتقدمة:**\n"
            msg += f"• اجعل البوت مشرفاً في المجموعة\n"
            msg += f"• ثم استخدم `/syncgroup` مرة أخرى"
            
            if user_id == CONFIG.ANONYMOUS_ADMIN_ID:
                await safe_send(context.bot, chat_id, msg)
            else:
                await safe_send(context.bot, user_id, msg)
            return
        
        is_admin = False
        real_user_id = user_id
        is_hidden = (user_id == CONFIG.ANONYMOUS_ADMIN_ID)
        
        if is_hidden:
            try:
                admins = await context.bot.get_chat_administrators(chat_id)
                for admin in admins:
                    if admin.status == 'creator':
                        real_user_id = admin.user.id
                        is_admin = True
                        break
                if not is_admin and admins:
                    real_user_id = admins[0].user.id
                    is_admin = True
            except Exception as e:
                logger.error(f"فشل في الحصول على مشرفين من المجموعة {chat_id}: {e}")
                is_admin = False
        else:
            try:
                member = await context.bot.get_chat_member(chat_id, user_id)
                is_admin = member.status in ['administrator', 'creator']
                real_user_id = user_id
            except Exception as e:
                logger.error(f"فشل في التحقق من صلاحية المستخدم {user_id}: {e}")
                is_admin = False
        
        if is_admin:
            await DB.execute(
                "INSERT OR REPLACE INTO hidden_owner_groups (chat_id, owner_id, is_hidden) VALUES (?,?,?)",
                (chat_id, real_user_id, 1 if is_hidden else 0)
            )
            await GroupRepository.link_user_to_group(real_user_id, chat_id)
            invalidate_auth_cache(chat_id, real_user_id)
            admin_count = await GroupRepository.sync_admins(chat_id, context.bot)
            
            msg = f"✅ **تم تفعيل المجموعة بنجاح!**\n\n"
            msg += f"📌 اسم المجموعة: {chat_name}\n"
            msg += f"🆔 المعرف: {chat_id}\n"
            msg += f"👤 تم تسجيل {'المالك' if not is_hidden else 'المشرف المخفي'} (المعرف: `{real_user_id}`)\n"
            msg += f"👥 تم مزامنة {admin_count} مشرف\n\n"
            msg += f"🔐 استخدم `/security` لإعدادات الأمان\n"
            msg += f"🛠️ استخدم `/panel` للوحة التحكم"
            
            # إرسال للمستخدم المناسب
            if is_hidden:
                # مشرف مخفي - أرسل للمجموعة
                await safe_send(context.bot, chat_id, f"🤖 **تم تفعيل البوت بواسطة مشرف مخفي!**")
                await safe_send(context.bot, chat_id, msg)
                # حاول إرسال للمالك الحقيقي
                if real_user_id and real_user_id > 0 and real_user_id != CONFIG.ANONYMOUS_ADMIN_ID:
                    try:
                        await safe_send(context.bot, real_user_id, msg)
                    except Exception as e:
                        logger.warning(f"لا يمكن إرسال للمالك الحقيقي {real_user_id}: {e}")
            else:
                # مستخدم عادي
                await safe_send(context.bot, real_user_id, msg)
                await safe_send(context.bot, chat_id, f"🤖 **تم تفعيل البوت في المجموعة!**")
        else:
            msg = f"✅ **تم تسجيل المجموعة!**\n\n"
            msg += f"📌 اسم المجموعة: {chat_name}\n"
            msg += f"🆔 المعرف: {chat_id}\n\n"
            msg += f"🔹 **لتفعيل الميزات المتقدمة:**\n"
            msg += f"• تأكد من أن البوت مشرف في المجموعة\n"
            msg += f"• يجب أن يقوم أحد المشرفين بتنفيذ الأمر"
            
            if is_hidden:
                await safe_send(context.bot, chat_id, msg)
            else:
                await safe_send(context.bot, user_id, msg)
            
            try:
                admins = await context.bot.get_chat_administrators(chat_id)
                for admin in admins:
                    admin_id = admin.user.id
                    if admin_id != user_id and admin_id > 0 and admin_id != CONFIG.ANONYMOUS_ADMIN_ID:
                        try:
                            await safe_send(context.bot, admin_id,
                                            f"📢 **طلب تفعيل البوت في المجموعة**\n\n"
                                            f"📌 المجموعة: {chat_name}\n"
                                            f"👤 المستخدم: `{user_id}`\n\n"
                                            f"🔹 لتفعيل البوت، قم بتنفيذ الأمر `/syncgroup`")
                        except:
                            pass
            except:
                pass

# =====================================================================
# 9. معالج الكولباك - CallbackHandlers
# =====================================================================

class CallbackHandlers:
    @staticmethod
    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        data = query.data
        if not data:
            return
        
        user_id = query.from_user.id
        lang = await UserRepository.get_language(user_id)
        
        try:
            # الأزرار الأساسية
            if data == CB.MAIN or data == CB.BACK:
                await query.answer()
                await CommandHandlers.start(update, context)
                return
            if data == CB.CANCEL:
                await query.answer()
                StateManager.clear(user_id)
                await query.edit_message_text("❌ تم الإلغاء")
                await CommandHandlers.start(update, context)
                return
            if data == CB.HELP:
                await query.answer()
                await CommandHandlers.help_command(update, context)
                return
            if data == CB.TRIAL:
                await query.answer()
                await CommandHandlers.trial(update, context)
                return
            if data == CB.DEVELOPER:
                await query.answer()
                await CommandHandlers.developer(update, context)
                return
            if data == CB.SUBSCRIBE:
                await query.answer()
                await CommandHandlers.subscribe(update, context)
                return
            if data == CB.SUPPORT:
                await query.answer()
                await CommandHandlers.support(update, context)
                return
            
            # إدارة القنوات
            if data == CB.CH_ADD:
                has_sub = await UserRepository.has_active_subscription(user_id)
                has_trial = await UserRepository.has_used_trial(user_id)
                if not has_sub and not has_trial:
                    await query.answer(await get_text(lang, 'subscription_expired'), show_alert=True)
                    return
                await query.answer()
                StateManager.set(user_id, UserState.WAIT_CHANNEL)
                await query.edit_message_text(await get_text(lang, 'enter_channel_id'))
                return
            
            if data == CB.CH_LIST:
                await query.answer()
                channels = await ChannelRepository.get_all(user_id)
                if not channels:
                    await query.edit_message_text(await get_text(lang, 'channels_empty'))
                    return
                text = "📡 **قنواتي**\n\n"
                for ch in channels:
                    st = "🚫" if ch['banned'] else "✅"
                    text += f"{st} {ch['channel_name']} (ID: {ch['id']})\n"
                kb = KeyboardFactory.build("main_menu")
                await query.edit_message_text(text, reply_markup=kb)
                return
            
            # لوحة الأدمن
            if data == CB.ADMIN:
                if user_id == CONFIG.PRIMARY_OWNER_ID or await BotAdminRepository.is_admin(user_id):
                    kb = KeyboardFactory.build("admin_panel")
                    await query.edit_message_text(await get_text(lang, 'admin_panel'), reply_markup=kb)
                    await query.answer()
                else:
                    await query.answer(await get_text(lang, 'not_authorized'), show_alert=True)
                return
            
            # أزرار الأمان
            if data.startswith("sec_"):
                parts = data.split(":")
                if data == CB.SEC_CLOSE:
                    await query.answer()
                    try:
                        await query.message.delete()
                    except:
                        pass
                    return
                
                if len(parts) < 2:
                    await query.answer("❌ خطأ في البيانات", show_alert=True)
                    return
                
                action = parts[0].replace("sec_", "")
                try:
                    chat_id = int(parts[1])
                except:
                    await query.answer("❌ خطأ في البيانات", show_alert=True)
                    return
                
                if not await is_authorized_in_group(context.bot, chat_id, user_id):
                    await query.answer(await get_text(lang, 'not_authorized'), show_alert=True)
                    return
                
                # تبديل الإعدادات
                field_map = {
                    "links": "delete_links", "mentions": "mentions", "slow": "slow_mode",
                    "video": "delete_videos", "audio": "delete_audio", "anim": "delete_animation",
                    "service": "delete_service", "doc": "delete_documents", "sticker": "delete_stickers",
                    "forward": "delete_forwarded", "poll": "delete_polls", "game": "delete_games",
                    "voice": "delete_voice", "videonote": "delete_video_note",
                    "welcome": "welcome_enabled", "goodbye": "goodbye_enabled",
                    "flood": "antiflood_enabled", "night": "night_mode_enabled"
                }
                
                if action in field_map:
                    col = field_map[action]
                    settings = await SecurityRepository.get(chat_id)
                    new_val = not settings.get(col, False)
                    await SecurityRepository.set(chat_id, **{col: new_val})
                    SecurityRepository.invalidate_cache(chat_id)
                    settings = await SecurityRepository.get(chat_id, force_refresh=True)
                    text = await KeyboardFactory._format_security_text(settings)
                    kb = KeyboardFactory.build("security", chat_id)
                    await query.edit_message_text(text, reply_markup=kb)
                    await query.answer()
                    return
                
                await query.answer()
                return
            
            # أزرار اللغة
            if data.startswith("lang_"):
                await query.answer()
                lang_set = data.split("_")[-1]
                await UserRepository.set_language(user_id, lang_set)
                await query.answer(f"✅ تم تغيير اللغة إلى {lang_set}")
                await CommandHandlers.start(update, context)
                return
            
            if data == CB.LANGUAGE:
                await query.answer()
                await CommandHandlers.language(update, context)
                return
            
            # الإعدادات
            if data == CB.SETTINGS:
                await query.answer()
                auto = "✅" if await UserRepository.get_auto_status(user_id) else "❌"
                kb = KeyboardFactory.build("settings")
                await query.edit_message_text(await get_text(lang, 'settings_auto', status=auto), reply_markup=kb)
                return
            
            if data == CB.TOGGLE_AUTO:
                await query.answer()
                cur = await UserRepository.get_auto_status(user_id)
                await UserRepository.set_auto(user_id, not cur)
                await CallbackHandlers.handle(update, context)
                return
            
            # أزرار أخرى
            if data == CB.PLANS:
                await query.answer()
                kb = KeyboardFactory.build("plans")
                await query.edit_message_text(await get_text(lang, 'plan_selector'), reply_markup=kb)
                return
            
            if data == CB.REFERRAL:
                await query.answer()
                stats = await ReferralRepository.get_stats(user_id)
                code = await UserRepository.get_referral_code(user_id)
                text = await get_text(lang, 'referral_header',
                                link=f"https://t.me/{CONFIG.BOT_USERNAME}?start=ref_{code}",
                                total=stats['total'],
                                available=stats['available'])
                kb = KeyboardFactory.build("referral")
                await query.edit_message_text(text, reply_markup=kb)
                return
            
            if data == CB.CONTESTS:
                await query.answer()
                await CommandHandlers.contests(update, context)
                return
            
            if data == CB.REMINDER:
                await query.answer()
                settings = await ReminderRepository.get_settings(user_id)
                sub = "✅" if settings['sub'] else "❌"
                daily = "✅" if settings['daily'] else "❌"
                weekly = "✅" if settings['weekly'] else "❌"
                days = settings['days']
                text = f"⏰ **إعدادات التذكيرات**\n\n🔔 تذكير الاشتراك: {sub}\n📊 يومي: {daily}\n📈 أسبوعي: {weekly}\n📅 عدد الأيام: {days}"
                kb = KeyboardFactory.build("reminder")
                await query.edit_message_text(text, reply_markup=kb)
                return
            
            if data == CB.TRANSLATION:
                await query.answer()
                current_lang = await UserRepository.get_language(user_id)
                text = f"🌐 الترجمة: {current_lang}"
                kb = KeyboardFactory.build("translation")
                await query.edit_message_text(text, reply_markup=kb)
                return
            
            if data == CB.SUPPORT_TICKET:
                await query.answer()
                StateManager.set(user_id, UserState.SUPPORT_MODE)
                await safe_send(context.bot, user_id, await get_text(lang, 'send_support_message'))
                try:
                    await query.message.delete()
                except:
                    pass
                return
            
            if data == CB.INVOICES:
                await query.answer()
                await safe_send(context.bot, user_id, "🧾 **فواتيري**\n\nلا توجد فواتير حتى الآن")
                return
            
            if data.startswith("buy_sub_"):
                await query.answer()
                days = int(data.split("_")[-1])
                await safe_send(context.bot, user_id, f"💎 **شراء اشتراك**\n\nمدة الاشتراك: {days} يوم\n\nللشراء، استخدم الأمر /subscribe")
                return
            
            # المجموعات
            if data == CB.GROUPS:
                await query.answer()
                groups = await GroupRepository.get_user_groups(user_id)
                if not groups:
                    text = await get_text(lang, 'groups_empty')
                    kb = InlineKeyboardMarkup([[InlineKeyboardButton(await get_text(lang, 'add_group'), url=f"https://t.me/{CONFIG.BOT_USERNAME}?startgroup")]])
                    await query.edit_message_text(text, reply_markup=kb)
                    return
                text = "👥 **المجموعات**\n\n"
                for gid, name, username, banned in groups:
                    st = "⛔" if banned else "✅"
                    text += f"{st} {name} (ID: {gid})\n"
                kb = KeyboardFactory.build("main_menu")
                await query.edit_message_text(text, reply_markup=kb)
                return
            
            # المنشورات
            if data == CB.POST_ADD:
                await query.answer()
                active = await ChannelRepository.get_active(user_id)
                if not active:
                    await query.edit_message_text(await get_text(lang, 'no_active_channel'))
                    return
                unpub = await PostRepository.get_unpublished_count(active)
                if unpub >= CONFIG.MAX_UNPUBLISHED_POSTS:
                    await query.edit_message_text(await get_text(lang, 'max_posts_reached'))
                    return
                target = min(15, CONFIG.MAX_UNPUBLISHED_POSTS - unpub)
                context.user_data[f"session_{user_id}"] = []
                context.user_data[f"session_target_{user_id}"] = target
                StateManager.set(user_id, UserState.ADDING_POSTS)
                await query.edit_message_text(await get_text(lang, 'enter_posts', count=target))
                return
            
            if data == CB.POST_PUB:
                await query.answer()
                active = await ChannelRepository.get_active(user_id)
                if not active:
                    await query.edit_message_text(await get_text(lang, 'no_active_channel'))
                    return
                await query.edit_message_text(await get_text(lang, 'publish_success'))
                return
            
            if data == CB.PUB_ALL:
                await query.answer()
                await query.edit_message_text(await get_text(lang, 'publish_success'))
                return
            
            if data == CB.STATS_PEND or data == CB.STATS_FULL:
                await query.answer()
                u = await PostRepository.get_user_unpublished(user_id)
                t = await PostRepository.get_user_total(user_id)
                ch = len(await ChannelRepository.get_all(user_id))
                g = len(await GroupRepository.get_user_groups(user_id))
                auto = "مفعل" if await UserRepository.get_auto_status(user_id) else "معطل"
                text = f"📊 **الإحصائيات**\n\n📝 منشورات: {t}\n⏳ غير منشورة: {u}\n📡 قنوات: {ch}\n👥 مجموعات: {g}\n⚙️ النشر التلقائي: {auto}"
                await query.edit_message_text(text)
                return
            
            # أزرار الأدمن (مختصرة)
            if data.startswith("admin_"):
                if user_id != CONFIG.PRIMARY_OWNER_ID and not await BotAdminRepository.is_admin(user_id):
                    await query.answer(await get_text(lang, 'not_authorized'), show_alert=True)
                    return
                
                if data == CB.ADMIN_USERS:
                    await query.answer()
                    stats = await UserRepository.get_stats()
                    await query.edit_message_text(await get_text(lang, 'admin_users', users=stats['users'], banned=stats['banned']))
                    return
                
                if data == CB.ADMIN_BANNED:
                    await query.answer()
                    users = await UserRepository.get_all_users()
                    banned_list = [str(u[0]) for u in users if u[1] == 1]
                    text = "⛔ **المحظورين**\n\n" + "\n".join([f"• `{u}`" for u in banned_list[:20]]) if banned_list else await get_text(lang, 'no_banned_words')
                    await query.edit_message_text(text)
                    return
                
                if data == CB.ADMIN_RAM:
                    await query.answer()
                    import psutil
                    mem = psutil.virtual_memory()
                    await query.edit_message_text(await get_text(lang, 'admin_ram', 
                                                         used=mem.used // (1024*1024),
                                                         total=mem.total // (1024*1024),
                                                         percent=mem.percent))
                    return
                
                if data == CB.ADMIN_STATS:
                    await query.answer()
                    stats = await UserRepository.get_stats()
                    await query.edit_message_text(await get_text(lang, 'admin_stats_text',
                                                           users=stats['users'], banned=stats['banned'],
                                                           posts=stats['posts'], groups=stats['groups'], channels=stats['channels']))
                    return
                
                if data == CB.ADMIN_BACKUP:
                    await query.answer()
                    try:
                        backup_file = PATHS.BACKUPS / f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db"
                        shutil.copy2(PATHS.DB, backup_file)
                        await safe_send(context.bot, user_id, await get_text(lang, 'admin_backup_created', filename=backup_file.name))
                    except Exception as e:
                        await safe_send(context.bot, user_id, await get_text(lang, 'admin_backup_failed', error=str(e)[:100]))
                    return
                
                if data == CB.ADMIN_BROADCAST:
                    await query.answer()
                    StateManager.set(user_id, UserState.WAIT_BROADCAST)
                    await query.edit_message_text(await get_text(lang, 'admin_broadcast_confirm', text="أرسل الرسالة:"))
                    return
                
                if data == CB.ADMIN_REFRESH_CACHE:
                    await query.answer()
                    await query.edit_message_text("🔄 تم تحديث الكاش بنجاح")
                    return
                
                await query.answer("⚠️ قيد التطوير", show_alert=True)
                return
            
            # الأزرار الأخرى
            if data == CB.PANEL_LOCK or data == CB.PANEL_UNLOCK:
                await query.answer()
                chat_id = int(data.split(":")[-1])
                locked = data == CB.PANEL_LOCK
                await ChatLockRepository.set_lock(chat_id, locked, user_id)
                await query.edit_message_text(f"🔒 تم القفل" if locked else "🔓 تم الفتح")
                return
            
            if data == CB.PANEL_CLOSE:
                await query.answer()
                try:
                    await query.message.delete()
                except:
                    pass
                return
            
            await query.answer("⚠️ قيد التطوير", show_alert=True)
            
        except Exception as e:
            logger.error(f"Callback error: {e}", exc_info=True)
            try:
                await query.answer("❌ حدث خطأ غير متوقع", show_alert=True)
            except:
                pass
        finally:
            try:
                await query.answer()
            except:
                pass

# =====================================================================
# 10. معالج الرسائل - MessageHandlers
# =====================================================================

class MessageHandlers:
    @staticmethod
    async def handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        msg = update.message
        text = msg.text.strip() if msg.text else ""
        state = StateManager.get(user_id)
        lang = await UserRepository.get_language(user_id)
        
        # معالجة إضافة القناة
        if state == UserState.WAIT_CHANNEL:
            channel_input = text.strip()
            if not channel_input:
                await safe_send(context.bot, user_id, await get_text(lang, 'invalid_format'))
                StateManager.clear(user_id)
                return
            
            try:
                chat = await context.bot.get_chat(channel_input)
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ خطأ: {str(e)[:100]}")
                StateManager.clear(user_id)
                return
            
            if chat.type != 'channel':
                await safe_send(context.bot, user_id, await get_text(lang, 'invalid_channel'))
                StateManager.clear(user_id)
                return
            
            try:
                channel_id = str(chat.id)
                channel_name = chat.title or "بدون اسم"
                result = await ChannelRepository.add(user_id, channel_id, channel_name)
                if result:
                    await ChannelRepository.set_active(user_id, result)
                    await safe_send(context.bot, user_id, f"✅ تمت إضافة القناة **{channel_name}** بنجاح!")
                else:
                    await safe_send(context.bot, user_id, await get_text(lang, 'channel_exists'))
            except Exception as e:
                await safe_send(context.bot, user_id, f"❌ فشل إضافة القناة: {str(e)[:100]}")
            
            StateManager.clear(user_id)
            await CommandHandlers.start(update, context)
            return
        
        # إضافة المنشورات
        if state == UserState.ADDING_POSTS:
            session = context.user_data.get(f"session_{user_id}", [])
            target = context.user_data.get(f"session_target_{user_id}", 15)
            
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
            elif msg.text:
                media_type = 'text'
            else:
                await safe_send(context.bot, user_id, "⚠️ غير مدعوم")
                return
            
            content = msg.caption or "" if media_type != 'text' else text
            session.append((content, media_type, media_file_id))
            context.user_data[f"session_{user_id}"] = session
            remaining = target - len(session)
            await safe_send(context.bot, user_id, await get_text(lang, 'post_saved', saved=len(session), target=target, remaining=remaining))
            
            if len(session) >= target:
                active = await ChannelRepository.get_active(user_id)
                if active:
                    await PostRepository.save(active, session)
                context.user_data.pop(f"session_{user_id}", None)
                context.user_data.pop(f"session_target_{user_id}", None)
                StateManager.clear(user_id)
                await safe_send(context.bot, user_id, await get_text(lang, 'all_posts_saved'))
            return
        
        # البث
        if state == UserState.WAIT_BROADCAST:
            context.user_data['broadcast_text'] = text
            StateManager.clear(user_id)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ تأكيد", callback_data=CB.ADMIN_CONFIRM_BROADCAST),
                 InlineKeyboardButton("❌ إلغاء", callback_data=CB.ADMIN)]
            ])
            await safe_send(context.bot, user_id, await get_text(lang, 'admin_broadcast_confirm', text=text[:200]), reply_markup=kb)
            return
        
        # وضع الدعم
        if state == UserState.SUPPORT_MODE:
            await safe_send(context.bot, user_id, await get_text(lang, 'support_ticket_created', num=1))
            StateManager.clear(user_id)
            return
        
        # بدء القائمة الرئيسية
        await CommandHandlers.start(update, context)

    @staticmethod
    async def handle_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # معالجة رسائل المجموعة (بسيطة)
        pass

# =====================================================================
# 11. الدالة الرئيسية
# =====================================================================

async def main():
    logger.info(f"🚀 Starting {CONFIG.BOT_NAME}")
    
    # تهيئة قاعدة البيانات
    await DB.initialize()
    await UserRepository.register(CONFIG.PRIMARY_OWNER_ID)
    await BotAdminRepository.add(CONFIG.PRIMARY_OWNER_ID)
    
    # تحميل الأزرار
    KeyboardFactory.load_config()
    
    # إعداد البوت
    app = Application.builder().token(CONFIG.TOKEN).build()
    
    # تسجيل الأوامر
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
    
    # تسجيل معالج الكولباك
    app.add_handler(CallbackQueryHandler(CallbackHandlers.handle))
    
    # تسجيل معالج الرسائل
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, MessageHandlers.handle_private))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, MessageHandlers.handle_group))
    
    # تشغيل البوت
    logger.info("✅ البوت جاهز للتشغيل")
    await app.run_polling(drop_pending_updates=True)

# =====================================================================
# 12. تشغيل البرنامج
# =====================================================================

if __name__ == "__main__":
    print(f"🌿 {CONFIG.BOT_NAME}")
    print("✅ الأزرار تُقرأ من ملف buttons_config.json")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 تم الإيقاف")
    except Exception as e:
        print(f"❌ {e}")
        traceback.print_exc()

