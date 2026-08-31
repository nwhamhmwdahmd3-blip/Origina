import json
import os

# قراءة الملف المجمّع
with open('all_translations.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# إنشاء مجلد locales
os.makedirs('locales', exist_ok=True)

# اللغات المدعومة
languages = ['ar', 'en', 'hi', 'fr', 'tr', 'zh', 'ru', 'de', 'es', 'it', 'pt', 'ja', 'ko', 'fa', 'ur', 'nl', 'pl']

# إنشاء ملف لكل لغة
for lang in languages:
    lang_data = {}
    for key, translations in data.items():
        if lang in translations:
            lang_data[key] = translations[lang]
    
    with open(f'locales/{lang}.json', 'w', encoding='utf-8') as f:
        json.dump(lang_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ تم إنشاء locales/{lang}.json ({len(lang_data)} مفتاح)")

print("🎉 تم إنشاء جميع ملفات الترجمة!")
