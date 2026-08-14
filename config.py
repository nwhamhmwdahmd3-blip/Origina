import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    # توكن البوت
    TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")
    BOT_NAME = os.getenv("BOT_NAME", "Relax Manager")
    
    # المالك الأساسي (المطور الرئيسي)
    PRIMARY_OWNER_ID = int(os.getenv("PRIMARY_OWNER_ID", "123456789"))
    
    # قائمة المطورين (يمكن إضافة أكثر من مطور)
    # أضف معرفات المطورين هنا مفصولة بفواصل في ملف .env
    # مثال: DEVELOPER_IDS=123456789,987654321,555555555
    DEVELOPER_IDS = []
    
    @classmethod
    def load_developers(cls):
        """تحميل قائمة المطورين من متغير البيئة"""
        dev_ids_str = os.getenv("DEVELOPER_IDS", "")
        if dev_ids_str:
            try:
                cls.DEVELOPER_IDS = [int(x.strip()) for x in dev_ids_str.split(",") if x.strip()]
            except ValueError:
                cls.DEVELOPER_IDS = []
        
        # التأكد من وجود المالك الأساسي في القائمة
        if cls.PRIMARY_OWNER_ID not in cls.DEVELOPER_IDS:
            cls.DEVELOPER_IDS.append(cls.PRIMARY_OWNER_ID)
        
        return cls.DEVELOPER_IDS
    
    # معرف المشرف المخفي (المعرف الخاص بتليجرام)
    ANONYMOUS_ADMIN_ID = 777000
    
    # إعدادات النشر
    MAX_UNPUBLISHED_POSTS = 50
    MAX_CHANNELS_PER_CYCLE = 20
    
    # إعدادات الويب
    WEB_PORT = int(os.getenv("PORT", 8080))
    USE_PROXY = os.getenv("USE_PROXY", "False").lower() == "true"
    PROXY_URL = os.getenv("PROXY_URL", "")
    
    # إعدادات النسخ الاحتياطي
    MAX_BACKUPS = 10
    
    # إعدادات المهام الخلفية
    HEARTBEAT_INTERVAL = 3600
    
    @classmethod
    def is_developer(cls, user_id: int) -> bool:
        """التحقق مما إذا كان المستخدم مطوراً"""
        return user_id in cls.DEVELOPER_IDS
    
    @classmethod
    def is_owner(cls, user_id: int) -> bool:
        """التحقق مما إذا كان المستخدم هو المالك الأساسي"""
        return user_id == cls.PRIMARY_OWNER_ID

# تحميل إعدادات المطورين
CONFIG = Config()
CONFIG.load_developers()

# مسارات الملفات
class Paths:
    BASE = Path(__file__).parent
    DB = BASE / "bot_data.db"
    BACKUPS = BASE / "backups"
    BUTTONS_FILE = BASE / "buttons_config.json"
    LOCALES_DIR = BASE / "locales"
    
    @classmethod
    def ensure_dirs(cls):
        cls.BACKUPS.mkdir(exist_ok=True)
        cls.LOCALES_DIR.mkdir(exist_ok=True)

PATHS = Paths()
PATHS.ensure_dirs()

# طباعة معلومات المطورين عند بدء التشغيل
print(f"👨‍💼 المالك الأساسي: {CONFIG.PRIMARY_OWNER_ID}")
print(f"👨‍💻 عدد المطورين: {len(CONFIG.DEVELOPER_IDS)}")
print(f"📋 قائمة المطورين: {CONFIG.DEVELOPER_IDS}")
