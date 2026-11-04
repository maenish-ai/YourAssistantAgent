from pathlib import Path
import sys
root=Path(__file__).resolve().parent
for p in [root,*root.parents]:
    if (p/'android/app/build.gradle').exists():
        root=p;break
else:
    print('ERROR: Put these files in the repository root.');sys.exit(1)
java=root/'android/app/src/main/java/ai/maenish/yourassistant/MainActivity.java'
gradle=root/'android/app/build.gradle'
s=java.read_text(encoding='utf-8');g=gradle.read_text(encoding='utf-8')
old='        bundledVoice.initialize();\n        initializeVoiceEngine();'
new='        // Initialize voice engines only when the user starts a voice call.\n        // Avoid loading device-specific native/audio libraries during startup.'
if old in s:s=s.replace(old,new,1)
elif new not in s:sys.exit('ERROR: Unexpected MainActivity startup structure; no files changed.')
oldcall='        callMode=true;waitingForReply=false;updateButtons();'
newcall='''        try {
            if (bundledVoice != null && !bundledVoice.ready()) bundledVoice.initialize();
            if (voice == null && !ttsInitializing) initializeVoiceEngine();
        } catch (RuntimeException error) {
            status.setText("تعذر بدء الصوت. يمكنك استخدام المحادثة النصية.");
            return;
        }
        callMode=true;waitingForReply=false;updateButtons();'''
if oldcall in s:s=s.replace(oldcall,newcall,1)
elif newcall not in s:sys.exit('ERROR: Unexpected call flow; no files changed.')
if "versionCode 10" in g:g=g.replace('versionCode 10','versionCode 11',1)
elif 'versionCode 11' not in g:sys.exit('ERROR: Unexpected versionCode; no files changed.')
if "versionName '1.7.0'" in g:g=g.replace("versionName '1.7.0'","versionName '1.8.0'",1)
elif "versionName '1.8.0'" not in g:sys.exit('ERROR: Unexpected versionName; no files changed.')
java.write_text(s,encoding='utf-8');gradle.write_text(g,encoding='utf-8')
print('DONE: Android 1.8.0 (versionCode 11), deferred speech startup.')
