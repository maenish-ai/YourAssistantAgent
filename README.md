# إصلاح تكرار GitHub Actions - Windows

1. افتح GitHub Desktop ثم Repository > Show in Explorer.
2. فك ZIP وانسخ `REMOVE-DUPLICATE-WORKFLOW.bat` إلى جذر المستودع (نفس المجلد الذي يحتوي `.git`).
3. شغّل ملف BAT بالنقر المزدوج.
4. في GitHub Desktop يجب أن يظهر حذف `.github/workflows/android-female-voice.yml`.
5. اضغط Commit to main ثم Push origin.

الملف لا يعدّل كود Windows أو Android. إنه يحذف Workflow المكرر الذي تسبب في فشل Windows، ويترك `.github/workflows/build-windows.yml` كما هو. إذا لم يظهر الحذف في GitHub Desktop فتأكد أنك داخل نسخة المستودع الصحيحة.
