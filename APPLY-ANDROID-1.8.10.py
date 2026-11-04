from pathlib import Path
import re,sys
root=Path(__file__).resolve().parent
for base in [root,root/'YourAssistantAgent']:
 if (base/'android/app/build.gradle').exists(): root=base;break
else: sys.exit('ERROR: Put these files in repository root (beside android folder).')
java=root/'android/app/src/main/java/ai/maenish/yourassistant'
gradle=root/'android/app/build.gradle'; main=java/'MainActivity.java'
g=gradle.read_text(encoding='utf-8'); s=main.read_text(encoding='utf-8')
if 'private void toggleCall()' not in s or 'void onCreate(Bundle savedInstanceState)' not in s:sys.exit('ERROR: MainActivity differs from expected source. No changes made.')
g,n=re.subn(r'versionCode\s+\d+', 'versionCode 11',g,count=1)
if n!=1:sys.exit('ERROR: versionCode not found')
g,n=re.subn(r"versionName\s+['\"][^'\"]+['\"]", "versionName '1.8.10'",g,count=1)
if n!=1:sys.exit('ERROR: versionName not found')
# Defer TTS/native voice initialization until the user actually requests a call.
s=s.replace('        bundledVoice.initialize();\n        initializeVoiceEngine();','        // Voice initialization deferred to explicit call activation (startup crash isolation).')
needle='        callMode=true;waitingForReply=false;updateButtons();'
replacement='''        try {
            if (bundledVoice != null && !bundledVoice.ready()) bundledVoice.initialize();
            if (voice == null && !ttsInitializing) initializeVoiceEngine();
        } catch (RuntimeException e) {
            CrashDiagnostics.note(this, "voice_initialization_failed");
            status.setText("تعذر تشغيل الصوت. يمكنك استخدام المحادثة النصية.");
            return;
        }
        callMode=true;waitingForReply=false;updateButtons();'''
if needle in s:s=s.replace(needle,replacement,1)
else:sys.exit('ERROR: call mode initialization not found')
needle='        super.onCreate(savedInstanceState);'
if 'CrashDiagnostics.install(this)' not in s:
 s=s.replace(needle,needle+'\n        CrashDiagnostics.install(this);\n        CrashDiagnostics.note(this, "main_onCreate");',1)
needle='        buildViews();'
if 'CrashDiagnostics.note(this, "views_ready")' not in s:s=s.replace(needle,needle+'\n        CrashDiagnostics.note(this, "views_ready");',1)
needle='        resumed = true;'
if 'CrashDiagnostics.note(this, "main_onResume")' not in s:s=s.replace(needle,'        CrashDiagnostics.note(this, "main_onResume");\n'+needle,1)
needle='        status=label("غير مقترن • اعرض QR من برنامج Windows ثم امسحه هنا.",12);status.setTextColor(AppUi.GREEN);root.addView(status);'
if 'CrashDiagnostics.showReport' not in s:
 if needle not in s:sys.exit('ERROR: UI insertion point not found')
 s=s.replace(needle,needle+'\n        root.addView(button("تقرير الأعطال / تشخيص التطبيق", () -> CrashDiagnostics.showReport(this)));',1)
# Record last known startup stage; crash report remains on device until explicitly shared.
source=r'''package ai.maenish.yourassistant;

import android.app.Activity;
import android.app.ActivityManager;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;

final class CrashDiagnostics {
    private static final String FILE_NAME = "android-crash-report.txt";
    private static final String STAGE_NAME = "android-last-stage.txt";
    private static volatile boolean installed;
    private CrashDiagnostics() {}
    static void note(Context context, String stage) {
        try (FileOutputStream out = context.openFileOutput(STAGE_NAME, Context.MODE_PRIVATE)) {
            out.write((new Date().toString() + " | " + stage).getBytes(StandardCharsets.UTF_8));
        } catch (Exception ignored) { }
    }
    static synchronized void install(Context context) {
        if (installed) return;
        installed = true;
        final Context app = context.getApplicationContext();
        final Thread.UncaughtExceptionHandler previous = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
            try {
                StringBuilder report = new StringBuilder();
                report.append("Your Assistant Android crash\n");
                report.append("Time: ").append(new Date()).append("\n");
                report.append("Version: ").append(BuildConfig.VERSION_NAME).append("\n");
                report.append("Android API: ").append(Build.VERSION.SDK_INT).append("\n");
                report.append("Thread: ").append(thread.getName()).append("\n");
                report.append("Exception: ").append(error.getClass().getName()).append("\n");
                // Stack traces may include private data. Keep only class/method/file/line.
                for (StackTraceElement frame : error.getStackTrace()) {
                    report.append(" at ").append(frame.getClassName()).append(".")
                        .append(frame.getMethodName()).append(" (")
                        .append(frame.getFileName()).append(":")
                        .append(frame.getLineNumber()).append(")\n");
                    if (report.length() > 12000) break;
                }
                try (FileOutputStream out = app.openFileOutput(FILE_NAME, Context.MODE_PRIVATE)) {
                    out.write(report.toString().getBytes(StandardCharsets.UTF_8));
                }
            } catch (Throwable ignored) { }
            if (previous != null) previous.uncaughtException(thread, error);
            else android.os.Process.killProcess(android.os.Process.myPid());
        });
    }
    private static String read(Context context, String name) {
        try { return new String(java.nio.file.Files.readAllBytes(new File(context.getFilesDir(), name).toPath()), StandardCharsets.UTF_8); }
        catch (Exception ignored) { return "No saved report"; }
    }
    static void showReport(Activity activity) {
        StringBuilder result = new StringBuilder("Your Assistant Android diagnostics\nVersion: ")
            .append(BuildConfig.VERSION_NAME).append("\nAndroid API: ")
            .append(Build.VERSION.SDK_INT).append("\n\nLast startup stage:\n")
            .append(read(activity, STAGE_NAME)).append("\n\nLast Java crash:\n")
            .append(read(activity, FILE_NAME));
        if (Build.VERSION.SDK_INT >= 30) {
            try {
                ActivityManager am = (ActivityManager) activity.getSystemService(Context.ACTIVITY_SERVICE);
                List<ApplicationExitInfo> exits = am.getHistoricalProcessExitReasons(null, 0, 5);
                if (exits != null) for (ApplicationExitInfo info : exits) {
                    result.append("\nExit reason: ").append(info.getReason())
                          .append(" at ").append(new Date(info.getTimestamp()));
                }
            } catch (Exception ignored) { }
        }
        final String report = result.toString();
        new AlertDialog.Builder(activity).setTitle("تقرير الأعطال")
            .setMessage(report).setPositiveButton("إغلاق", null)
            .setNeutralButton("مشاركة التقرير", (d, which) -> {
                Intent share = new Intent(Intent.ACTION_SEND);
                share.setType("text/plain");
                share.putExtra(Intent.EXTRA_TEXT, report);
                activity.startActivity(Intent.createChooser(share, "مشاركة تقرير الأعطال"));
            }).show();
    }
}
'''
# Android API 30 ApplicationExitInfo is android.app.ApplicationExitInfo
source=source.replace('import android.app.ActivityManager;','import android.app.ActivityManager;\nimport android.app.ApplicationExitInfo;')
# Avoid modifying any project files until validation passes.
gradle.write_text(g,encoding='utf-8');main.write_text(s,encoding='utf-8');(java/'CrashDiagnostics.java').write_text(source,encoding='utf-8')
print('DONE: Android 1.8.10 (versionCode 11), startup isolation, local crash diagnostics.')
print('Changed: android/app/build.gradle, MainActivity.java, CrashDiagnostics.java')
