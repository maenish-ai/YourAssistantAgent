package ai.maenish.yourassistant;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import java.util.Date;

/** Small private crash journal. Never records tokens, URLs, messages or user content. */
final class CrashDiagnostics {
    private final SharedPreferences prefs;
    private final Thread.UncaughtExceptionHandler previous;
    CrashDiagnostics(Context context) {
        prefs=context.getApplicationContext().getSharedPreferences("local_crash_diagnostics",Context.MODE_PRIVATE);
        previous=Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread,error)->{
            try { failure("uncaught",error); } catch(Throwable ignored) {}
            if(previous!=null)previous.uncaughtException(thread,error);
            else { android.os.Process.killProcess(android.os.Process.myPid()); System.exit(10); }
        });
    }
    void begin(){
        int count=prefs.getBoolean("startup_pending",false)?prefs.getInt("failures",0)+1:0;
        prefs.edit().putInt("failures",count).putBoolean("startup_pending",true)
            .putString("stage","onCreate").putLong("start",System.currentTimeMillis()).commit();
    }
    void stage(String name){prefs.edit().putString("stage",name).apply();}
    void healthy(){prefs.edit().putBoolean("startup_pending",false).putInt("failures",0).apply();}
    boolean safeMode(){return prefs.getInt("failures",0)>=2 || prefs.getBoolean("force_safe",false);}
    void clearSafeMode(){prefs.edit().putInt("failures",0).putBoolean("force_safe",false).apply();}
    void failure(String source,Throwable t){
        // Exception class and app stack location only. No exception message (may contain secrets).
        String where="unknown";
        for(StackTraceElement e:t.getStackTrace()){
            if(e.getClassName().startsWith("ai.maenish.yourassistant")){
                where=e.getClassName()+"."+e.getMethodName()+":"+e.getLineNumber();break;
            }
        }
        prefs.edit().putString("last_crash",new Date()+" | "+source+" | "+t.getClass().getName()+" | "+where)
            .putString("crash_stage",prefs.getString("stage","unknown"))
            .putBoolean("startup_pending",true).commit();
    }
    String report(){
        return "Version: "+BuildConfig.VERSION_NAME+" ("+BuildConfig.VERSION_CODE+")"+
            "\nAndroid: "+Build.VERSION.RELEASE+" (API "+Build.VERSION.SDK_INT+")"+
            "\nDevice: "+Build.MANUFACTURER+" / "+Build.MODEL+
            "\nSafe mode: "+safeMode()+
            "\nPrevious interrupted starts: "+prefs.getInt("failures",0)+
            "\nCurrent startup stage: "+prefs.getString("stage","unknown")+
            "\nLast crash stage: "+prefs.getString("crash_stage","none")+
            "\nLast Java crash: "+prefs.getString("last_crash","none recorded")+
            "\nNote: native crashes and forced Android kills may not be recorded.";
    }
}
