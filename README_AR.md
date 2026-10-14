# Your Assistant Agent v0.6 — GitHub Ready

هذه النسخة هي التحديث الكامل التالي للمشروع، ومجهزة للرفع إلى GitHub وتشغيل Workflow تلقائي لبناء نسخة Windows.

## التغييرات الرئيسية في v0.6

### 1) إصلاح تعليق شاشة البداية
- شاشة البداية لا تبقى فوق نافذة PIN بعد الآن.
- تظهر لمدة قصيرة تقريبًا 1.1 ثانية ثم تُغلق قبل نافذة الحماية.
- تم حذف الأيقونة الصغيرة السفلية من تصميم البداية.
- تظهر العلامة الكبيرة واسم **Your Assistant Agent** مع تعريف مختصر عن وظائف البرنامج.

### 2) العربية والإنجليزية من أول تشغيل
- أول نافذة عند أول تشغيل هي اختيار: **العربية | English**.
- العربية تطبق اتجاه RTL وواجهة عربية.
- English تطبق LTR وواجهة إنجليزية.
- يمكن تغيير اللغة لاحقًا من Settings / الإعدادات، ويعاد تشغيل البرنامج لتطبيقها بالكامل.

### 3) دعم Unicode للعربية والإنجليزية
- ملفات المشروع UTF-8.
- Qt وSQLite يستقبلان النص العربي والإنجليزي والرموز Unicode.
- البحث يدعم اختلافات شائعة في العربية مثل: أ / إ / آ / ا، ويزيل التشكيل والتطويل من نسخة المقارنة فقط.
- النص الأصلي المخزن لا يتم تغييره.
- استيراد CSV يستخدم UTF-8-SIG لملفات العربية والإنجليزية.

### 4) Facebook
- نفس نظام الجروبات والحملات المجدولة.
- متصفح مخصص ظاهر للمستخدم.
- لغة متصفح Facebook تتبع لغة البرنامج: `ar-JO` أو `en-US`.
- محددات النشر تتعرف على العبارات العربية والإنجليزية الأساسية.
- لا يتم تخزين كلمة مرور Facebook.

### 5) WhatsApp
تم إضافة قسم WhatsApp متكامل داخل البرنامج:

- جهات اتصال محلية.
- اسم + رقم دولي + وسوم.
- Opt-in / موافقة على الاستلام.
- استيراد جهات الاتصال من CSV.
- حملات Broadcast داخلية.
- تقسيم تلقائي للجهات إلى دفعات من 1 إلى 256، والافتراضي 100.
- جدولة الحملات.
- فاصل زمني بين المستلمين.
- تشغيل يدوي فوري للحملة.
- نوعا رسائل:
  - Text message.
  - Approved template.
- سجل نجاح/فشل ضمن Audit Log.

**مهم:** البرنامج لا ينشئ Native Broadcast Lists داخل تطبيق WhatsApp على الهاتف. الإرسال الآلي يستخدم **WhatsApp Business Platform / Cloud API الرسمي** ويرسل للمستلمين كرسائل فردية ضمن دفعات يديرها البرنامج.

للتفعيل أدخل داخل WhatsApp > Business Platform settings:
- Phone Number ID
- Graph API version
- Access Token

يتم حفظ Access Token بواسطة Windows DPAPI وليس كنص عادي في قاعدة البيانات.

## الحماية
- PIN محلي باستخدام Argon2id.
- Access Token محمي بواسطة Windows DPAPI.
- Facebook browser profile منفصل.
- Audit Log.
- Emergency Stop يلغي طوابير Facebook وWhatsApp المعلقة.

## أول رفع إلى GitHub

1. فك ضغط الحزمة.
2. تأكد أن `.github` موجود بجانب `app.py` مباشرة.
3. افتح هذا المجلد في GitHub Desktop.
4. Commit.
5. Publish / Push.
6. اذهب إلى GitHub > Actions.
7. يعمل Workflow باسم **Build Your Assistant Agent for Windows** تلقائيًا على أي Push.
8. بعد نجاحه ستجد Artifacts:
   - `YourAssistantAgent-Windows-Portable`
   - `YourAssistantAgent-Windows-Setup`

## ملفات مهمة
- `.github/workflows/windows-build.yml` — البناء التلقائي.
- `your_assistant_agent/ui.py` — الواجهة العربية/الإنجليزية.
- `your_assistant_agent/i18n.py` — النصوص المترجمة.
- `your_assistant_agent/text_utils.py` — Unicode والبحث العربي/الإنجليزي.
- `your_assistant_agent/whatsapp.py` — WhatsApp Business Platform.
- `your_assistant_agent/facebook.py` — Facebook browser automation.
- `your_assistant_agent/engine.py` — محرك Facebook + WhatsApp.
- `your_assistant_agent/db.py` — قاعدة البيانات والطوابير والحملات.
- `assets/brand_mark.png` — العلامة الكبيرة المستخدمة في شاشة البداية.

## الاختبارات
الاختبارات الحالية تشمل:
- Facebook groups/campaign queue.
- الجدولة.
- Unicode العربي/الإنجليزي.
- WhatsApp contacts والبث على دفعات.
