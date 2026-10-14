Your Assistant Agent v0.6.4 — PATCH ONLY

هذا الملف يحتوي فقط على الملفات المعدلة المطلوبة فوق v0.6.3.

طريقة التثبيت على مشروع GitHub:
1) فك ضغط هذا الملف.
2) انسخ مجلد your_assistant_agent فوق مجلد المشروع الحالي.
3) وافق على Replace للملفات الموجودة.
4) اعمل Commit ثم Push من GitHub Desktop.
5) الـ Workflow الحالي لا يحتاج تعديل وسيبني Windows Setup فقط.

ما تغير في v0.6.4:
- تسجيل دخول Facebook أصبح Manual Login حقيقيًا.
- عند الضغط على فتح تسجيل دخول فيسبوك، يتم تشغيل Chrome/Edge المثبت مباشرةً بدون Playwright أثناء إدخال كلمة المرور و2FA.
- يستخدم المتصفح نفس Profile الدائم الخاص بـ Your Assistant Agent، وليس Profile المتصفح الشخصي.
- لا يتم تمرير --no-sandbox في وضع تسجيل الدخول اليدوي.
- أتمتة Playwright بعد تسجيل الدخول تستخدم chromium_sandbox=True.
- بعد الانتهاء من تسجيل الدخول: أغلق نافذة المتصفح ثم اضغط "Check Facebook connection / التحقق من اتصال فيسبوك".
- إذا بقي متصفح تسجيل الدخول مفتوحًا، البرنامج يوضح أن Profile ما زال مستخدمًا بدل التعليق.
- إذا بقي تسجيل الدخول أكثر من 45 ثانية، Dashboard يعرض تنبيهًا واضحًا بدل أن يبدو البرنامج معلقًا.
- حالة الاتصال تبقى محفوظة ولا تتحول إلى "Browser closed" لمجرد أن نافذة Playwright غير مفتوحة.
- لا يوجد حل أو تجاوز تلقائي لـ CAPTCHA أو Security Challenge؛ هذه الخطوات تبقى يدوية.
- الإصدار أصبح 0.6.4.

الملفات المعدلة فقط:
- your_assistant_agent/facebook.py
- your_assistant_agent/engine.py
- your_assistant_agent/ui.py
- your_assistant_agent/i18n.py
- your_assistant_agent/__init__.py

الاختبارات الموجودة في المشروع بعد الدمج: 6/6 ناجحة.
