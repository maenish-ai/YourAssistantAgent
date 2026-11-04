from pathlib import Path
import sys, shutil
p=Path('android/app/src/main/java/ai/maenish/yourassistant/MainActivity.java')
if not p.exists():
 print('ERROR: Run from repository root (folder containing android).');sys.exit(1)
s=p.read_text(encoding='utf-8')
backup=p.with_suffix('.java.before-startup-fix.bak')
if 'STARTUP_AUDIO_LAZY_FIX_V2' in s:
 print('Already applied.');sys.exit(0)
# Match exact code from repository main. Fail closed rather than silently corrupting code.
old='''        bundledVoice.initialize();
        initializeVoiceEngine();
        dictation=new PhoneDictation(this,new PhoneDictation.Listener(){'''
new='''        // STARTUP_AUDIO_LAZY_FIX_V2: avoid starting native audio/TTS engines on app launch.
        // Some devices crash asynchronously while these engines initialize.
        dictation=new PhoneDictation(this,new PhoneDictation.Listener(){'''
if s.count(old)!=1: print('ERROR: startup block changed; no changes made.');sys.exit(2)
s=s.replace(old,new,1)
old='''        if(voice!=null && !ttsInitializing){
            String engine=android.provider.Settings.Secure.getString(
                getContentResolver(),"tts_default_synth");
            if(engine!=null && !engine.equals(activeTtsEngine))initializeVoiceEngine();
        }
'''
if s.count(old)!=1:print('ERROR: resume block changed; no changes made.');sys.exit(2)
s=s.replace(old,'''        // Audio engines are initialized only when the user starts a voice call.
''',1)
old='''        callMode=true;waitingForReply=false;updateButtons();
        say("أهلاً، أنا جاهزة. احكي لي شو بدك أعمل على الكمبيوتر.");'''
new='''        callMode=true;waitingForReply=false;updateButtons();
        // Lazy initialization: do not create native audio resources until explicitly requested.
        if(bundledVoice!=null) {
            try { bundledVoice.initialize(); } catch(RuntimeException e) {
                status.setText("تعذر تهيئة الصوت المحلي. جرّب إعدادات الصوت في الهاتف.");
            }
        }
        if(voice==null && !ttsInitializing) {
            try { initializeVoiceEngine(); } catch(RuntimeException e) {
                status.setText("تعذر تهيئة تحويل النص إلى كلام.");
            }
        }
        say("أهلاً، أنا جاهزة. احكي لي شو بدك أعمل على الكمبيوتر.");'''
if s.count(old)!=1:print('ERROR: voice call block changed; no changes made.');sys.exit(2)
s=s.replace(old,new,1)
# Avoid calling voice.stop() when an engine never initialized; existing code checks for null.
shutil.copy2(p,backup)
p.write_text(s,encoding='utf-8')
print('DONE: Android audio initialization moved out of startup.')
print('Changed: '+str(p))
print('Backup: '+str(backup))
print('NEXT: Commit and push the changed MainActivity.java, rebuild APK, install NEW APK.')
