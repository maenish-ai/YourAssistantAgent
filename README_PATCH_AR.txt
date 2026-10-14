Your Assistant Agent v0.6.2 — PATCH ONLY

انسخ الملفين فوق مشروع GitHub الحالي مع Replace:

1) installer/YourAssistantAgent.iss
2) your_assistant_agent/__init__.py

بعدها اعمل Commit + Push.

ما تغير:
- الـSetup يعرض تنبيه واحد فقط قبل التحديث.
- عند الموافقة يغلق YourAssistantAgent.exe مع شجرة العمليات التابعة له تلقائياً.
- هذا يشمل عادةً Node/Playwright/Chrome for Testing التابعة للبرنامج.
- لا يستهدف Chrome العادي أو البرامج الأخرى بشكل عام.
- أزيلت شاشة Inno Setup القديمة التي تعرض قائمة التطبيقات المستخدمة للملفات.
- بعد التثبيت يمكن تشغيل النسخة الجديدة من شاشة Finish.
- أضيفت لغة العربية والإنجليزية إلى الـSetup نفسه.
- الإصدار أصبح 0.6.2.
- لا يوجد أي تعديل على Workflow؛ v0.6.1 عندك بالفعل يرفع Setup فقط بدون Portable.
