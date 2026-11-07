package ai.maenish.yourassistant;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Looper;
import android.speech.tts.TextToSpeech;
import android.speech.tts.Voice;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.Shadows;
import org.robolectric.shadows.ShadowAlertDialog;
import org.robolectric.shadows.ShadowTextToSpeech;
import java.util.HashSet;
import java.util.Locale;
import org.json.JSONArray;
import org.json.JSONObject;
import static org.junit.Assert.*;

/** Starts the actual activities with packaged resources, without opening sockets. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk=28)
public class AppScreensTest {
    private View text(View view,String label){
        if(view instanceof TextView && label.contentEquals(((TextView)view).getText()))return view;
        if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=text(group.getChildAt(i),label);if(found!=null)return found;}}
        return null;
    }
    private View text(Activity activity,String label){return text(activity.findViewById(android.R.id.content),label);}
    @Test public void firstLaunchShowsQrAndKeepsUnpairedComputerControlsDisabled(){
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=controller.get();View scan=text(activity,"مسح QR وإقران الكمبيوتر");
            assertNotNull(scan);assertEquals(View.VISIBLE,scan.getVisibility());assertTrue(scan.isEnabled());
            assertFalse(text(activity,"سطح المكتب").isEnabled());assertFalse(text(activity,"الملفات").isEnabled());
            assertFalse(text(activity,"إرسال الطلب").isEnabled());
            assertTrue(text(activity,"إعدادات الربط").performClick());
            assertNotNull(text(activity,"تشخيص الاتصال"));assertFalse(text(activity,"تشخيص الاتصال").isEnabled());
            assertNotEquals(0,activity.getApplicationInfo().icon);
            assertNotNull(text(activity,"المحادثة الذكية تستخدم Groq؛ التحكم اليدوي والملفات لهما أزرار منفصلة."));
        }
    }
    @Test public void desktopLaunchesAndKeyboardCanBeExpandedWithoutAConnection(){
        try(ActivityController<DesktopActivity> controller=Robolectric.buildActivity(DesktopActivity.class).setup()){
            DesktopActivity activity=controller.get();assertNotNull(text(activity,"سطح المكتب"));
            assertTrue(text(activity,"لوحة المفاتيح").performClick());assertNotNull(text(activity,"Enter"));
        }
    }
    @Test public void filesLaunchesWithTransferAndCancelControls(){
        try(ActivityController<FilesActivity> controller=Robolectric.buildActivity(FilesActivity.class).setup()){
            FilesActivity activity=controller.get();assertNotNull(text(activity,"ملفات الكمبيوتر"));
            assertNotNull(text(activity,"رفع ملف"));assertNotNull(text(activity,"إلغاء النقل والرجوع"));
        }
    }
    @Test public void arabicVoiceCanBeSelectedAndSampled(){
        Voice option=new Voice("test-arabic",new Locale("ar","JO"),400,200,false,new HashSet<>());
        ShadowTextToSpeech.addVoice(option);
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=controller.get();
            assertTrue(text(activity,"🔊 تجربة واختيار صوت عربي").performClick());
            TextToSpeech tts=ShadowTextToSpeech.getLastTextToSpeechInstance();
            assertNotNull(tts);
            ShadowTextToSpeech shadow=Shadows.shadowOf(tts);
            shadow.getOnInitListener().onInit(TextToSpeech.SUCCESS);
            Shadows.shadowOf(Looper.getMainLooper()).idle();
            AlertDialog dialog=ShadowAlertDialog.getLatestAlertDialog();
            assertNotNull(dialog);
            int selected=-1;
            for(int i=0;i<dialog.getListView().getCount();i++){
                if(String.valueOf(dialog.getListView().getItemAtPosition(i)).contains("test-arabic")){selected=i;break;}
            }
            assertTrue(selected>=0);
            dialog.getListView().performItemClick(null,selected,selected);
            assertEquals("test-arabic",shadow.getCurrentVoice().getName());
            assertTrue(shadow.getLastSpokenText().contains("مساعدتك"));
        }
    }
    @Test public void unverifiedActionIsNotShownAsCompleted() throws Exception {
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=controller.get();
            JSONObject event=new JSONObject().put("id",1).put("type","progress")
                .put("text","راجع الوجهة").put("progress",new JSONObject().put("state","unverified"));
            JSONObject response=new JSONObject().put("events",new JSONArray().put(event)).put("cursor",1);
            java.lang.reflect.Method apply=MainActivity.class.getDeclaredMethod("applyEvents",JSONObject.class);
            apply.setAccessible(true);apply.invoke(activity,response);
            assertNotNull(text(activity,"تقدم المهمة\n؟ لم يُتحقق من النتيجة\nراجع الوجهة"));
            assertNull(text(activity,"تقدم المهمة\n✓ اكتملت المهمة\nراجع الوجهة"));
        }
    }
}
