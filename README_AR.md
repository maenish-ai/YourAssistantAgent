# Your Assistant Agent v1.2.0

مساعد ويندوز شخصي لإدارة حملات Facebook، التحكم عبر Telegram، WhatsApp Business، الجدولة، Wake/Sleep، ورفع تحديثات المشروع إلى GitHub.

## الجديد: موظف AI محلي مجاني

الإصدار 1.2.0 يضيف Dual Local Brain مجانيًا مدمجًا في نسخة ويندوز:

- **Qwen3-0.6B GGUF** للعقل العام.
- **RightNow-Arabic-0.5B-Turbo GGUF Q4_K_M** للعربية.
- وضع **Auto** يختار الموديل حسب لغة الرسالة، ويحمّل موديلًا واحدًا فقط في الذاكرة في كل لحظة.
- **llama.cpp** كمحرك تشغيل محلي.
- يعمل على `127.0.0.1` داخل نفس الجهاز.
- لا يحتاج API Key أو Token أو اشتراك.
- بعد تثبيت البرنامج لا يحتاج إرسال كلام المستخدم إلى خدمة سحابية عند اختيار Local AI.
- يفهم الكلام الطبيعي والعامي والسياق والتعديلات القصيرة مثل: «لا، خليها بكرة الساعة 9 بدل 8».

إذا أراد المستخدم مزود AI خارجي لاحقًا، يوجد خيار **OpenAI-compatible endpoint** عام، وليس البرنامج مربوطًا بشركة واحدة. وإذا فشل المزود الخارجي يحاول البرنامج الرجوع للـAI المحلي المجاني.

## مثال طبيعي

يمكن أن تقول:

> اليوم الساعة 8 خذ آخر إعلان من صفحة معن حنونة للساتلايت وانشره على الجروبات اللي إلها علاقة بخلدة، وإذا الجروب بده موافقة أدمن اعتبره تم الإرسال وما تعيده.

المفروض أن يفهم الوكيل: مرة واحدة اليوم، آخر منشور، فلترة خلدة، ومعاملة مراجعة الأدمن كـPending Approval وليس فشل. قبل حفظ القاعدة يعرض الخطة وعدد الجروبات المطابقة.

ثم يمكن أن تقول:

> لا، خليها بكرة الساعة 9 وصويلح بدل خلدة.

فيستخدم سياق الخطة السابقة بدل مطالبتك بإعادة كل التفاصيل.

## Facebook

- تسجيل الدخول يدويًا في بروفايل متصفح مخصص.
- Discover للجروبات المحفوظة في الحساب.
- الاستهداف حسب الاسم/الوسم.
- Native Share -> Share to a group.
- الحالات: Published / Submitted / Pending Approval / Failed / Blocked / Skipped.
- Pending Approval لا يُعاد إرساله كأنه فشل.
- لا يوجد تجاوز CAPTCHA أو Checkpoint؛ يتوقف البرنامج ويطلب تدخل المستخدم.

## Telegram

- تحكم خاص ببوت Telegram وUser ID مصرح.
- أوامر /status و/rules و/run و/pause و/resume و/wake و/stop.
- ويمكن الكتابة بالكلام الطبيعي؛ نفس عقل الـSmart Agent يحاول فهم الرسالة.
- العمليات الحساسة تبقى خلف تأكيد Approve/Cancel.

## GitHub Deployment

تبويب داخل البرنامج لفحص Patch، تطبيقه على فرع جديد، تشغيل الاختبارات/البناء، ثم Commit + Push بعد موافقة المستخدم، مع متابعة GitHub Actions وعدم استخدام Force Push.

## Wake / Sleep

- دعم Windows WakeToRun قبل الحملات المجدولة.
- Wake-on-LAN عبر MAC/Broadcast.
- أمر Telegram `/wake` الفوري يحتاج Relay أو جهازًا آخر دائم التشغيل إذا كان الكمبيوتر نفسه نائمًا؛ البرنامج الموجود على جهاز نائم لا يستطيع استقبال Telegram أثناء النوم.

## بناء نسخة ويندوز من GitHub

المستودع لا يحتوي ملف الموديل الكبير ولا ملفات llama.cpp التنفيذية. هذا مقصود حتى يبقى Git صالحًا للرفع.

عند GitHub Actions:
1. تثبيت Python والمتطلبات.
2. تشغيل الاختبارات.
3. تنزيل llama.cpp Windows x64 المقيّد بالإصدار المحدد.
4. تنزيل Qwen3-0.6B GGUF.
5. تنزيل RightNow-Arabic-0.5B-Turbo GGUF.
6. التحقق من SHA-256 للملفات المثبتة.
7. تثبيت Playwright Chromium fallback.
8. بناء PyInstaller.
9. بناء Windows Setup عبر Inno Setup.
10. رفع **YourAssistantAgent-Windows-Setup** فقط كـArtifact.

للبناء محليًا على Windows يمكن تشغيل:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_local_ai.ps1
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

## ملفات الذكاء المحلي

المصادر والتراخيص موثقة في `THIRD_PARTY_NOTICES_LOCAL_AI.md`.
