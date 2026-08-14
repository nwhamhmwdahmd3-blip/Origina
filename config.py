import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Config:
    # توكن البوت
    TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")
    BOT_NAME = os.getenv("BOT_NAME", "Relax Manager")
    
    # المالك الأساسي
    PRIMARY_OWNER_ID = int(os.getenv("PRIMARY_OWNER_ID", "123456789"))
    
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

CONFIG = Config()

# مسارات الملفات
class Paths:
    BASE = Path(__file__).parent
    DB = BASE / "bot_data.db"
    BACKUPS = BASE / "backups"
    BUTTONS_FILE = BASE / "buttons_config.json"
    
    @classmethod
    def ensure_dirs(cls):
        cls.BACKUPS.mkdir(exist_ok=True)

PATHS = Paths()
PATHS.ensure_dirs()
