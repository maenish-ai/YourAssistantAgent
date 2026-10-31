package ai.maenish.yourassistant;

import android.content.Context;
import android.media.MediaRecorder;
import java.io.File;

/** Foreground-only AAC capture. Audio goes to the paired PC, never a phone-held API key. */
final class PhoneDictation {
    interface Listener {void recording(boolean active);void ready(File audio);void error(String message);}
    private final Context context;private final Listener listener;
    private MediaRecorder recorder;private File file;private long started;
    PhoneDictation(Context context,Listener listener){
        this.context=context;this.listener=listener;
        File[] old=context.getCacheDir().listFiles((dir,name)->name.startsWith("dictation-")&&name.endsWith(".m4a"));
        if(old!=null)for(File item:old)if(System.currentTimeMillis()-item.lastModified()>600000)item.delete();
    }
    boolean active(){return recorder!=null;}
    void start(){
        if(active())return;
        try{
            file=File.createTempFile("dictation-",".m4a",context.getCacheDir());
            recorder=new MediaRecorder();recorder.setAudioSource(MediaRecorder.AudioSource.MIC);
            recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
            recorder.setAudioChannels(1);recorder.setAudioSamplingRate(44100);recorder.setAudioEncodingBitRate(64000);
            recorder.setMaxDuration(60000);recorder.setMaxFileSize(2L*1024*1024);recorder.setOutputFile(file.getAbsolutePath());
            recorder.setOnInfoListener((r,what,extra)->{if(what==MediaRecorder.MEDIA_RECORDER_INFO_MAX_DURATION_REACHED||what==MediaRecorder.MEDIA_RECORDER_INFO_MAX_FILESIZE_REACHED)finish();});
            recorder.setOnErrorListener((r,what,extra)->{cancel();listener.error("توقف الميكروفون. أعد المحاولة وتأكد أنه غير مستخدم بتطبيق آخر.");});
            recorder.prepare();recorder.start();started=android.os.SystemClock.elapsedRealtime();listener.recording(true);
        }catch(Exception e){cancel();listener.error("تعذر تشغيل الميكروفون. افحص إذن التسجيل وتوفر الميكروفون.");}
    }
    void finish(){
        if(!active())return;
        boolean valid=android.os.SystemClock.elapsedRealtime()-started>=700;
        MediaRecorder current=recorder;recorder=null;
        try{current.stop();}catch(RuntimeException e){valid=false;}
        finally{current.release();listener.recording(false);}
        File audio=file;file=null;
        if(!valid||audio==null||audio.length()<12){if(audio!=null)audio.delete();listener.error("التسجيل قصير جداً. اضغط الميكروفون وتحدث ثم اضغط إنهاء التسجيل.");return;}
        listener.ready(audio);
    }
    void cancel(){
        MediaRecorder current=recorder;recorder=null;
        if(current!=null){try{current.stop();}catch(RuntimeException ignored){}finally{current.release();listener.recording(false);}}
        if(file!=null){file.delete();file=null;}
    }
}
