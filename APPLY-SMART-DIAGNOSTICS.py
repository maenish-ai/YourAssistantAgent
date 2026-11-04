from pathlib import Path
import sys, shutil
root=Path('android/app/src/main/java/ai/maenish/yourassistant')
p=root/'MainActivity.java'
if not p.exists(): sys.exit('ERROR: Run from repository root containing android/')
s=p.read_text(encoding='utf-8')
if 'SMART_CRASH_DIAGNOSTICS_V1' in s: sys.exit('Already applied')
def replace(old,new):
 global s
 if s.count(old)!=1: sys.exit('ERROR: Source differs; nothing changed at: '+old[:85])
 s=s.replace(old,new,1)
replace('''        credentials = new SecureStore(this);
        buildViews();''','''        // SMART_CRASH_DIAGNOSTICS_V1
        CrashDiagnostics.install(this);
        CrashDiagnostics.mark(this, "activity-created");
        credentials = new SecureStore(this);
        CrashDiagnostics.mark(this, "before-build-views");
        buildViews();
        CrashDiagnostics.mark(this, "views-ready");''')
replace('''        bundledVoice.initialize();
        initializeVoiceEngine();
        dictation=new PhoneDictation''','''        // Voice engines intentionally start only when the user requests a call.
        CrashDiagnostics.mark(this, "voice-deferred");
        dictation=new PhoneDictation''')
replace('''        if(voice!=null && !ttsInitializing){
            String engine=android.provider.Settings.Secure.getString(
                getContentResolver(),"tts_default_synth");
            if(engine!=null && !engine.equals(activeTtsEngine))initializeVoiceEngine();
        }
''','''        CrashDiagnostics.mark(this, "resumed");
''')
replace('''        callMode=true;waitingForReply=false;updateButtons();
        say("أهلاً، أنا جاهزة. احكي لي شو بدك أعمل على الكمبيوتر.");''','''        callMode=true;waitingForReply=false;updateButtons();
        try {
            if(bundledVoice!=null)bundledVoice.initialize();
            if(voice==null)initializeVoiceEngine();
        } catch(RuntimeException e) {
            CrashDiagnostics.record(this,"voice-initialization",e);
            status.setText("تعذر تشغيل الصوت. افتح تقرير التشخيص.");
        }
        say("أهلاً، أنا جاهزة. احكي لي شو بدك أعمل على الكمبيوتر.");''')
replace('''        root.addView(pairing,AppUi.space(this));''','''        root.addView(pairing,AppUi.space(this));
        root.addView(AppUi.button(this,"تقرير الأعطال / تشخيص التطبيق",()->{
            new android.app.AlertDialog.Builder(this)
                .setTitle("تقرير التشخيص")
                .setMessage(CrashDiagnostics.report(this))
                .setPositiveButton("حسنًا",(d,w)->{})
                .setNeutralButton("مشاركة التقرير",(d,w)->{
                    Intent share=new Intent(Intent.ACTION_SEND);
                    share.setType("text/plain");
                    share.putExtra(Intent.EXTRA_TEXT,CrashDiagnostics.report(this));
                    startActivity(Intent.createChooser(share,"مشاركة تقرير الأعطال"));
                }).show();
        },false),AppUi.space(this));''')
replace('''        if (allowReconnect&&api==null&&!busy)connect();''','''        if (allowReconnect&&api==null&&!busy)connect();''') if False else None
# Avoid partial updates if the exact source changed.
backup=p.with_suffix('.java.before-diagnostics.bak')
shutil.copy2(p,backup)
p.write_text(s,encoding='utf-8')
(root/'CrashDiagnostics.java').write_text(r'''package ai.maenish.yourassistant;

import android.content.Context;
import android.os.Build;
import android.os.Process;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** Local, opt-in crash diagnostics. Never saves tokens, URLs, user messages or exception messages. */
final class CrashDiagnostics {
    private static final String LOG="crash_diagnostics.txt";
    private static final int LIMIT=12000;
    private static volatile String stage="initializing";
    private static volatile boolean installed;
    static void install(Context context) {
        if(installed)return;
        installed=true;
        final Context app=context.getApplicationContext();
        Thread.UncaughtExceptionHandler prior=Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread,error)->{
            try { record(app,"uncaught:"+stage,error); }catch(Throwable ignored){}
            if(prior!=null)prior.uncaughtException(thread,error);
            else { Process.killProcess(Process.myPid());System.exit(10); }
        });
        mark(app,"diagnostics-installed");
    }
    static synchronized void mark(Context context,String step){
        stage=step;
        append(context,"STEP "+step);
    }
    static synchronized void record(Context context,String label,Throwable error){
        StringBuilder b=new StringBuilder("CRASH ").append(label).append(" type=")
            .append(error==null?"unknown":error.getClass().getName());
        if(error!=null){
            StackTraceElement[] frames=error.getStackTrace();
            for(int i=0;i<Math.min(frames.length,12);i++){
                StackTraceElement f=frames[i];
                b.append("\n  at ").append(f.getClassName()).append(".")
                  .append(f.getMethodName()).append(":").append(f.getLineNumber());
            }
        }
        append(context,b.toString());
    }
    private static void append(Context context,String line){
        try {
            File file=new File(context.getFilesDir(),LOG);
            String prior=read(file);
            if(prior.length()>LIMIT)prior=prior.substring(prior.length()-LIMIT);
            String stamp=new SimpleDateFormat("yyyy-MM-dd HH:mm:ss",Locale.US).format(new Date());
            String result=prior+stamp+" "+line+"\n";
            if(result.length()>LIMIT)result=result.substring(result.length()-LIMIT);
            try(FileOutputStream out=new FileOutputStream(file,false)){
                out.write(result.getBytes(StandardCharsets.UTF_8));
                out.getFD().sync();
            }
        }catch(Throwable ignored){}
    }
    private static String read(File file){
        try(FileInputStream in=new FileInputStream(file)){
            byte[] data=new byte[(int)Math.min(file.length(),LIMIT+4096)];
            int n=in.read(data);
            return n>0?new String(data,0,n,StandardCharsets.UTF_8):"";
        }catch(Exception e){return "";}
    }
    static String report(Context context){
        return "YourAssistantAgent Android diagnostics\nAndroid "+Build.VERSION.RELEASE+
            " (SDK "+Build.VERSION.SDK_INT+")\nDevice "+Build.MANUFACTURER+" "+Build.MODEL+
            "\nApp "+BuildConfig.VERSION_NAME+"\n\n"+
            read(new File(context.getFilesDir(),LOG))+
            "\nNote: process kills/native crashes may not produce a Java exception.";
    }
}
''',encoding='utf-8')
print('DONE: Crash diagnostics installed; backup:',backup)
