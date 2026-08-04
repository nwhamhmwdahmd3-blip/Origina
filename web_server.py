# ===================================================================
# web_server.py - خادم ويب منفصل باستخدام Flask
# ===================================================================
import os
from flask import Flask

# إنشاء تطبيق Flask
flask_app = Flask(__name__)

@flask_app.route('/')
@flask_app.route('/health')
def health_check():
    """نقطة نهاية للتحقق من صحة البوت (يستخدمها Render)"""
    return "✅ البوت يعمل بكفاءة!", 200

@flask_app.route('/ping')
def ping():
    """نقطة نهاية للنبض (Keep-Alive)"""
    return "pong", 200

def run_flask():
    """تشغيل خادم Flask على المنفذ المخصص"""
    port = int(os.environ.get("PORT", 10000))
    try:
        flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"⚠️ فشل تشغيل Flask: {e}")

if __name__ == "__main__":
    # للتشغيل المباشر (اختبار)
    run_flask()
