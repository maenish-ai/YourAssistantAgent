# Your Assistant Agent v0.5 — First GitHub Upload Ready

هذه النسخة مجهزة خصيصًا لأن هذا المشروع سيُرفع إلى GitHub لأول مرة.

## مهم جدًا
بعد فك الضغط، افتح **المجلد نفسه** في GitHub Desktop.  
يجب أن ترى هذه الملفات مباشرة داخل جذر المشروع:

- `.github`
- `app.py`
- `requirements.txt`
- `assets`
- `your_assistant_agent`
- `installer`
- `scripts`

لا ترفع ملف ZIP نفسه إلى المستودع كملف وحيد.

## ماذا يحدث عند أول Push؟
الـ Workflow الموجود في:

`.github/workflows/windows-build.yml`

يعمل تلقائيًا عند **أي Push**، بغض النظر عن اسم الفرع، بما في ذلك أول رفع للمشروع.

يقوم تلقائيًا بـ:
1. تنزيل كود المشروع.
2. تثبيت Python.
3. تثبيت المتطلبات.
4. تشغيل الاختبارات.
5. تنزيل Chromium الخاص بـ Playwright.
6. بناء البرنامج بواسطة PyInstaller.
7. إنشاء نسخة Windows Portable.
8. تثبيت Inno Setup داخل GitHub Actions.
9. إنشاء ملف تثبيت `YourAssistantAgent-Setup.exe`.
10. رفع الناتج داخل GitHub Actions كـ Artifacts.

## طريقة الرفع لأول مرة عبر GitHub Desktop
1. فك الضغط عن الملف.
2. افتح GitHub Desktop.
3. اختر **File > New repository**.
4. اختر اسم المستودع، مثلاً: `YourAssistantAgent`.
5. اجعل Local Path هو المجلد الذي فككت إليه هذه الملفات.
6. إذا أنشأ GitHub Desktop مجلدًا جديدًا فارغًا بدل استخدام المجلد الحالي:
   - انسخ جميع ملفات هذه الحزمة داخله، بما فيها `.github`.
7. في GitHub Desktop سيظهر لك جميع الملفات كـ Changes.
8. اكتب Commit message مثل: `Initial Your Assistant Agent project`.
9. اضغط **Commit to main**.
10. اضغط **Publish repository**.
11. افتح المستودع على GitHub.
12. ادخل إلى **Actions**.
13. ستجد: **Build Your Assistant Agent for Windows**.
14. انتظر حتى يصبح أخضر.
15. افتح الـ run وانزل إلى **Artifacts**.

## الملفات الناتجة
- `YourAssistantAgent-Windows-Portable`
- `YourAssistantAgent-Windows-Setup`

الملف الثاني يحتوي على مثبت Windows EXE.

## الهوية البصرية
تم تضمين:
- شعار البرنامج.
- App icon.
- Windows icon.
- Splash Screen.
- UI showcase.
- ملفات branding داخل `assets/`.

## ملاحظة
هذه الحزمة تحتوي على المشروع نفسه جاهزًا للرفع، وليست تحديثًا لمستودع سابق.
