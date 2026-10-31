package ai.maenish.yourassistant;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.view.View;
import android.view.ViewGroup;
import android.widget.EditText;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.Shadows;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.util.ReflectionHelpers;
import java.io.File;
import java.util.ArrayList;
import java.util.List;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk={28,35})
public class PhoneDictationTest {
    private View text(View view,String label){
        if(view instanceof TextView&&label.contentEquals(((TextView)view).getText()))return view;
        if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=text(group.getChildAt(i),label);if(found!=null)return found;}}
        return null;
    }
    private View text(Activity activity,String label){return text(activity.findViewById(android.R.id.content),label);}
    @Test public void micIsVisibleAndDisabledBeforeConnection(){
        try(ActivityController<MainActivity> c=Robolectric.buildActivity(MainActivity.class).setup()){
            assertNotNull(text(c.get(),"🎙 إملاء صوتي"));assertFalse(text(c.get(),"🎙 إملاء صوتي").isEnabled());
        }
    }
    @Test public void micRequestsPermissionAndDenialKeepsTypedText(){
        try(ActivityController<MainActivity> c=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity a=c.get();Shadows.shadowOf(a.getApplication()).denyPermissions(Manifest.permission.RECORD_AUDIO);
            ReflectionHelpers.setField(a,"connected",true);ReflectionHelpers.setField(a,"dictationAllowed",true);
            EditText composer=ReflectionHelpers.getField(a,"composer");composer.setText("نص سابق");
            ReflectionHelpers.callInstanceMethod(a,"updateButtons");text(a,"🎙 إملاء صوتي").performClick();
            int request=Shadows.shadowOf(a).getLastRequestedPermission().requestCode;
            assertArrayEquals(new String[]{Manifest.permission.RECORD_AUDIO},Shadows.shadowOf(a).getLastRequestedPermission().requestedPermissions);
            a.onRequestPermissionsResult(request,new String[]{Manifest.permission.RECORD_AUDIO},new int[]{PackageManager.PERMISSION_DENIED});
            assertEquals("نص سابق",composer.getText().toString());assertFalse(((PhoneDictation)ReflectionHelpers.getField(a,"dictation")).active());
        }
    }
    @Test public void resultIsEditableAndIsNeverAutoSentOrRepeated()throws Exception{
        try(ActivityController<MainActivity> c=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity a=c.get();EditText composer=ReflectionHelpers.getField(a,"composer");composer.setText("من فضلك");
            ReflectionHelpers.setField(a,"pendingDictationId","my-recording-123");
            JSONObject event=new JSONObject().put("id",1).put("type","dictation").put("dictation_id","other-recording-123").put("dictation_text","لا تضف هذا");
            ReflectionHelpers.callInstanceMethod(a,"applyEvents",ReflectionHelpers.ClassParameter.from(JSONObject.class,new JSONObject().put("events",new JSONArray().put(event)).put("cursor",1)));
            assertEquals("من فضلك",composer.getText().toString());
            event.put("id",2).put("dictation_id","my-recording-123").put("dictation_text","اغلق النافذة");
            ReflectionHelpers.callInstanceMethod(a,"applyEvents",ReflectionHelpers.ClassParameter.from(JSONObject.class,new JSONObject().put("events",new JSONArray().put(event)).put("cursor",2)));
            assertEquals("من فضلك اغلق النافذة",composer.getText().toString());assertNull(ReflectionHelpers.getField(a,"pendingDictationId"));
            event.put("id",3);
            ReflectionHelpers.callInstanceMethod(a,"applyEvents",ReflectionHelpers.ClassParameter.from(JSONObject.class,new JSONObject().put("events",new JSONArray().put(event)).put("cursor",3)));
            assertEquals("من فضلك اغلق النافذة",composer.getText().toString());assertFalse(text(a,"إرسال الطلب").isEnabled());
        }
    }
    @Test public void pendingTextSurvivesBackgroundAndReconnectPreparation()throws Exception{
        try(ActivityController<MainActivity> c=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity a=c.get();ReflectionHelpers.setField(a,"pendingDictationId","resume-audio-123");
            c.pause().resume();
            ReflectionHelpers.callInstanceMethod(a,"disconnect",ReflectionHelpers.ClassParameter.from(boolean.class,false));
            assertEquals("resume-audio-123",ReflectionHelpers.getField(a,"pendingDictationId"));
            JSONObject event=new JSONObject().put("id",1).put("type","dictation").put("dictation_id","resume-audio-123").put("dictation_text","افتح الصفحة");
            ReflectionHelpers.callInstanceMethod(a,"applyEvents",ReflectionHelpers.ClassParameter.from(JSONObject.class,new JSONObject().put("events",new JSONArray().put(event)).put("cursor",1)));
            EditText composer=ReflectionHelpers.getField(a,"composer");assertEquals("افتح الصفحة",composer.getText().toString());
        }
    }
    @Test public void leavingTheScreenCancelsAndDeletesForegroundAudio(){
        try(ActivityController<MainActivity> c=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity a=c.get();Shadows.shadowOf(a.getApplication()).grantPermissions(Manifest.permission.RECORD_AUDIO);
            PhoneDictation recorder=ReflectionHelpers.getField(a,"dictation");recorder.start();assertTrue(recorder.active());
            c.pause();assertFalse(recorder.active());
            File[] audio=a.getCacheDir().listFiles((dir,name)->name.startsWith("dictation-")&&name.endsWith(".m4a"));
            assertNotNull(audio);assertEquals(0,audio.length);assertNull(ReflectionHelpers.getField(a,"pendingDictationId"));
        }
    }
}
