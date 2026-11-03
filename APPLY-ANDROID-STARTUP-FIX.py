from pathlib import Path
import sys
p=Path(__file__).resolve().parent/'android/app/src/main/java/ai/maenish/yourassistant/MainActivity.java'
if not p.is_file():
    sys.exit('ERROR: Put this script in the YourAssistantAgent repository root, next to android folder.')
s=p.read_text(encoding='utf-8')
old='''        bundledVoice.initialize();
        initializeVoiceEngine();'''
new='''        // Initialize voice engines only when the user explicitly starts a voice call.
        // Eager native ONNX/TTS startup can crash the process on unsupported devices.
        // Keep the rest of the application and QR pairing available independently.'''
if old in s: s=s.replace(old,new,1)
elif new not in s: sys.exit('ERROR: expected voice startup code differs; no changes saved.')
old='''        callMode=true;waitingForReply=false;updateButtons();
        say("أهلاً، أنا جاهزة. احكي لي شو بدك أعمل على الكمبيوتر.");'''
new='''        callMode=true;waitingForReply=false;updateButtons();
        // Lazy voice initialization: never block QR pairing or text chat startup.
        if (voice == null && !ttsInitializing) {
            try { initializeVoiceEngine(); }
            catch (RuntimeException e) {
                callMode=false; updateButtons();
                status.setText("تعذر بدء الصوت على هذا الهاتف. يمكنك متابعة المحادثة النصية.");
                return;
            }
        }
        say("أهلاً، أنا جاهزة. احكي لي شو بدك أعمل على الكمبيوتر.");'''
if old in s:s=s.replace(old,new,1)
elif new not in s:sys.exit('ERROR: expected call start code differs; no changes saved.')
# Prevent polling event rendering exceptions from terminating Android UI thread.
old='''                    CharSequence before=status.getText();applyEvents(response);
                    if(android.text.TextUtils.equals(before,status.getText()))status.setText("متصل • التحديث تلقائي أثناء فتح التطبيق.");
                    schedulePoll();'''
new='''                    try {
                        CharSequence before=status.getText();
                        applyEvents(response);
                        if(android.text.TextUtils.equals(before,status.getText()))
                            status.setText("متصل • التحديث تلقائي أثناء فتح التطبيق.");
                    } catch (RuntimeException e) {
                        android.util.Log.e("YourAssistant", "Event display failed", e);
                        status.setText("تعذر عرض تحديث من الكمبيوتر؛ سيستمر الاتصال.");
                    }
                    schedulePoll();'''
if old in s:s=s.replace(old,new,1)
elif new not in s:sys.exit('ERROR: expected polling code differs; no changes saved.')
# TTS init can throw synchronously in onResume if the engine has changed.
old='''            if(engine!=null && !engine.equals(activeTtsEngine))initializeVoiceEngine();'''
new='''            if(engine!=null && !engine.equals(activeTtsEngine)) {
                try { initializeVoiceEngine(); }
                catch (RuntimeException e) {
                    android.util.Log.e("YourAssistant", "TTS initialization failed", e);
                    status.setText("محرك الصوت غير متاح؛ بقية التطبيق تعمل بشكل طبيعي.");
                }
            }'''
if old in s:s=s.replace(old,new,1)
elif new not in s:sys.exit('ERROR: expected resume code differs; no changes saved.')
p.write_text(s,encoding='utf-8')
print('DONE: Android startup fix applied to',p)
print('NEXT: GitHub Desktop > Commit to main > Push origin > install new APK')
