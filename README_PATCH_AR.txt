Your Assistant Agent v0.8.0 — UNIFIED PATCH ONLY

هذا Patch واحد فوق v0.7.1، ويجمع التعديلات الأخيرة بدل تنزيل عدة تحديثات.

يشمل:
- تحسين فهم Smart Agent للعربية، ومنها:
  "جميع المجموعات التي جزء من اسمها يكون صويلح".
- دعم أوامر "اليوم" و"غداً" كموعد مرة واحدة بدل تفسيرها كقاعدة يومية.
- Preview يعرض عدد الجروبات المطابقة قبل اعتماد القاعدة، مع أمثلة من أسمائها.
- زر إلغاء/مسح للـ Preview.
- تحرير القاعدة المحددة Edit.
- حذف القاعدة مع تأكيد.
- إلغاء المشاركات المعلقة لقاعدة محددة.
- Telegram Remote:
  /status
  /rules
  /run ID
  /enable ID
  /disable ID
  /delete ID
  /pause
  /resume
  /wake
  /stop
  بالإضافة للأوامر الطبيعية للحملات.
- إعداد Wake / Sleep في Settings.
- Auto Wake: ينشئ Windows WakeToRun task لإيقاظ الكمبيوتر قبل موعد Smart Rule المحفوظ.
- Wake-on-LAN: MAC + Broadcast IP + Port + Test Magic Packet.
- الإصدار أصبح 0.8.0.
- لا يحتاج requirements جديدة.
- GitHub Workflow الحالي يبقى كما هو ويولد Windows Setup فقط.

مهم بخصوص Telegram Wake:
الكمبيوتر وهو في Sleep لا يستطيع تشغيل بوت Telegram الموجود على نفس الكمبيوتر، لذلك أمر /wake الفوري
يحتاج جهاز/راوتر/Relay آخر دائم التشغيل لإرسال Magic Packet.
أما الاستيقاظ التلقائي قبل الحملات المجدولة فهو يعمل محلياً بواسطة Windows WakeToRun
ولا يحتاج جهازاً آخر بعد إعداد القاعدة بينما الكمبيوتر مستيقظ.

طريقة الرفع:
1) فك الضغط.
2) انسخ الملفات فوق مشروع v0.7.1 الحالي مع Replace.
3) Commit.
4) Push إلى GitHub.
5) انتظر GitHub Actions ثم حمّل Windows Setup.

الاختبارات المحلية بعد الدمج: 15 اختبار نجح.
