Your Assistant Agent v0.7.1 — FACEBOOK GROUP DISCOVERY FIX

هذا Patch إصلاحي فوق v0.7.0 الحالية.

التعديلات:
- إصلاح Discover My Facebook Groups.
- تسجيل واضح في Audit Log عند Queue / Start / Done / Empty / Failed.
- قراءة صفحة Your Groups / Groups you've joined أولاً، مع fallback إلى Groups Feed.
- تحسين استخراج اسم ورابط الجروب من واجهة Facebook الحالية.
- إظهار حالة الاكتشاف مباشرة داخل تبويب Facebook Groups.
- إغلاق متصفح الأتمتة الخاص بالوكيل تلقائياً بعد انتهاء الاكتشاف.
- تحديث الإصدار إلى v0.7.1.

طريقة الدمج:
1) فك الضغط.
2) انسخ الملفات فوق مستودع v0.7.0 الحالي مع Replace.
3) Commit + Push إلى GitHub.
4) Workflow يبني Windows Setup الجديد.

بعد التثبيت:
- Dashboard يجب أن يكون Facebook Connected.
- Facebook Groups > Discover my Facebook groups.
- راقب سطر الحالة أسفل القائمة وAudit Log.
