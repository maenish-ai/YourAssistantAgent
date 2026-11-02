حزمة تحضير الصوت الأنثوي العربي لمشروع YourAssistantAgent

تم اختيار نموذج Arabic Emirati Female Piper بترخيص MIT من:
https://huggingface.co/vadimbelsky/arabic-emirati-female-piper

المحتويات:
1) MainActivity.java: دمج إعدادات اختيار محرك الصوت المحلي من داخل Android، واستئناف الصوت بعد تغيير المحرك.
2) tools/download_arabic_female_voice.py: تنزيل ملف ONNX وملف JSON من المستودع الأصلي؛ التشغيل: python tools/download_arabic_female_voice.py

مهم جدًا: لا تحتوي هذه الحزمة على ملف ONNX نفسه (63.5MB)، بسبب عدم توفر تنزيل الملفات الخارجية في بيئة الإنشاء الحالية. الأداة تنزّله على جهازك عند توفر الإنترنت.
ومهم أيضًا: هذا لا يشغّل ملف ONNX مباشرة داخل APK؛ يتطلب ذلك إضافة sherpa-onnx Android native runtime وربط النموذج مع واجهة توليد الصوت. حاليًا التطبيق يستخدم محرك Android TTS الذي تختاره، ويمكن استعمال HayaiTTS محليًا بعد تثبيته وتحميل نموذج متوافق فيه.

هذه حزمة مرحلية صادقة، وليست دمجًا مكتملًا للنموذج داخل التطبيق، ولم يتم اختبار APK أو الصوت فعليًا.
