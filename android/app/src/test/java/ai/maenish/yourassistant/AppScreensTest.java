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
            assertFalse(text(activity,"إرسال").isEnabled());
            assertTrue(text(activity,"الإعدادات").performClick());
            assertTrue(text(activity,"إعدادات الربط").performClick());
            assertNotNull(text(activity,"تشخيص الاتصال"));assertFalse(text(activity,"تشخيص الاتصال").isEnabled());
            assertNotEquals(0,activity.getApplicationInfo().icon);
            assertTrue(text(activity,"المحادثة").performClick());
            assertTrue(text(activity,"إرسال").isShown());
            assertTrue(text(activity,"الكمبيوتر").performClick());
            assertTrue(text(activity,"سطح المكتب").isShown());
            assertFalse(text(activity,"إرسال").isShown());
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
    @Test public void reconnect_keeps_transcript_and_applies_only_new_events() throws Exception {
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=controller.get();
            java.lang.reflect.Method apply=MainActivity.class.getDeclaredMethod("applyConnectedEvents",JSONObject.class,boolean.class);
            apply.setAccessible(true);
            JSONObject first=new JSONObject().put("events",new JSONArray().put(new JSONObject().put("id",1).put("type","message").put("text","الرد الأول"))).put("cursor",1);
            JSONObject second=new JSONObject().put("events",new JSONArray().put(new JSONObject().put("id",2).put("type","message").put("text","الرد الثاني"))).put("cursor",2);
            apply.invoke(activity,first,false);apply.invoke(activity,second,true);
            assertNotNull(text(activity,"المساعد\nالرد الأول"));
            assertNotNull(text(activity,"المساعد\nالرد الثاني"));
            JSONObject restarted=new JSONObject().put("reset",true).put("events",new JSONArray().put(new JSONObject().put("id",1).put("type","message").put("text","جلسة جديدة"))).put("cursor",1);
            apply.invoke(activity,restarted,true);
            assertNull(text(activity,"المساعد\nالرد الأول"));
            assertNotNull(text(activity,"المساعد\nجلسة جديدة"));
        }
    }
    @Test public void reconnect_retains_approval_until_server_invalidates_it() throws Exception {
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=controller.get();
            java.lang.reflect.Method apply=MainActivity.class.getDeclaredMethod("applyConnectedEvents",JSONObject.class,boolean.class);apply.setAccessible(true);
            JSONObject approval=new JSONObject().put("id",1).put("type","approval").put("text","راجع الخطة")
                .put("token","valid-review-token").put("expires_at",System.currentTimeMillis()/1000.0+600);
            apply.invoke(activity,new JSONObject().put("events",new JSONArray().put(approval)).put("cursor",1),false);
            View button=text(activity,"موافق — نفّذ");assertNotNull(button);assertTrue(button.isEnabled());
            java.lang.reflect.Method disconnect=MainActivity.class.getDeclaredMethod("disconnect",boolean.class,boolean.class);disconnect.setAccessible(true);
            disconnect.invoke(activity,false,true);
            assertTrue(button.isEnabled());
            JSONObject cleared=new JSONObject().put("id",2).put("type","message").put("text","انتهت المراجعة").put("clear_approval",true);
            apply.invoke(activity,new JSONObject().put("events",new JSONArray().put(cleared)).put("cursor",2),true);
            assertFalse(button.isEnabled());
        }
    }
    @Test public void stalledVoiceReplyEndsCallWithoutRetryingRequest() throws Exception {
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=controller.get();
            java.lang.reflect.Field call=MainActivity.class.getDeclaredField("callMode");call.setAccessible(true);call.setBoolean(activity,true);
            java.lang.reflect.Field waiting=MainActivity.class.getDeclaredField("waitingForReply");waiting.setAccessible(true);waiting.setBoolean(activity,true);
            java.lang.reflect.Field timeout=MainActivity.class.getDeclaredField("voiceReplyTimeout");timeout.setAccessible(true);
            ((Runnable)timeout.get(activity)).run();
            assertFalse(call.getBoolean(activity));assertFalse(waiting.getBoolean(activity));
            assertNotNull(text(activity,"تأخر الرد الصوتي. قد يكون طلبك ما زال قيد التنفيذ؛ راجع المحادثة قبل إعادة الطلب."));
        }
    }
    @Test public void timelyVoiceReplyDoesNotTriggerTimeout() throws Exception {
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=controller.get();
            java.lang.reflect.Field call=MainActivity.class.getDeclaredField("callMode");call.setAccessible(true);call.setBoolean(activity,true);
            java.lang.reflect.Field waiting=MainActivity.class.getDeclaredField("waitingForReply");waiting.setAccessible(true);waiting.setBoolean(activity,true);
            JSONObject event=new JSONObject().put("id",1).put("type","message").put("text","وصل الرد");
            java.lang.reflect.Method apply=MainActivity.class.getDeclaredMethod("applyEvents",JSONObject.class);apply.setAccessible(true);
            apply.invoke(activity,new JSONObject().put("events",new JSONArray().put(event)).put("cursor",1));
            java.lang.reflect.Field timeout=MainActivity.class.getDeclaredField("voiceReplyTimeout");timeout.setAccessible(true);
            ((Runnable)timeout.get(activity)).run();
            assertTrue(call.getBoolean(activity));assertFalse(waiting.getBoolean(activity));
        }
    }
    @Test public void voiceReadsAllAssistantMessagesFromOnePoll() throws Exception {
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=controller.get();
            TextToSpeech tts=new TextToSpeech(activity,status->{});
            java.lang.reflect.Field voice=MainActivity.class.getDeclaredField("voice");voice.setAccessible(true);voice.set(activity,tts);
            java.lang.reflect.Field call=MainActivity.class.getDeclaredField("callMode");call.setAccessible(true);call.setBoolean(activity,true);
            JSONArray events=new JSONArray()
                .put(new JSONObject().put("id",1).put("type","message").put("text","الجزء الأول"))
                .put(new JSONObject().put("id",2).put("type","message").put("text","الجزء الثاني"));
            java.lang.reflect.Method apply=MainActivity.class.getDeclaredMethod("applyEvents",JSONObject.class);apply.setAccessible(true);
            apply.invoke(activity,new JSONObject().put("events",events).put("cursor",2));
            String spoken=Shadows.shadowOf(tts).getLastSpokenText();
            assertTrue(spoken.contains("الجزء الأول") && spoken.contains("الجزء الثاني"));
        }
    }
    @Test public void extraMessageDoesNotResumeListeningWhileApprovalIsPending() throws Exception {
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=controller.get();
            TextToSpeech tts=new TextToSpeech(activity,status->{});
            java.lang.reflect.Field voice=MainActivity.class.getDeclaredField("voice");voice.setAccessible(true);voice.set(activity,tts);
            java.lang.reflect.Field call=MainActivity.class.getDeclaredField("callMode");call.setAccessible(true);call.setBoolean(activity,true);
            java.lang.reflect.Field waiting=MainActivity.class.getDeclaredField("waitingForReply");waiting.setAccessible(true);
            JSONArray events=new JSONArray()
                .put(new JSONObject().put("id",1).put("type","approval").put("text","راجع المعاينة").put("token","pending-token").put("expires_at",System.currentTimeMillis()/1000.0+600))
                .put(new JSONObject().put("id",2).put("type","message").put("text","تفاصيل إضافية"));
            java.lang.reflect.Method apply=MainActivity.class.getDeclaredMethod("applyEvents",JSONObject.class);apply.setAccessible(true);
            apply.invoke(activity,new JSONObject().put("events",events).put("cursor",2));
            assertTrue(waiting.getBoolean(activity));
            String spoken=Shadows.shadowOf(tts).getLastSpokenText();
            assertTrue(spoken.contains("طلب موافقة") && spoken.contains("تفاصيل إضافية"));
        }
    }
    @Test public void reconnectDelayGrowsAndRemainsBounded(){
        assertEquals(3000,MainActivity.reconnectDelayMs(0,1));
        assertEquals(6000,MainActivity.reconnectDelayMs(1,1));
        assertEquals(12000,MainActivity.reconnectDelayMs(2,1));
        assertEquals(30000,MainActivity.reconnectDelayMs(100,1.2));
    }
    @Test public void oldConversationIsResumedOnlyForSamePairing(){
        assertTrue(MainActivity.samePairing("home+same","token","home+same","token"));
        assertFalse(MainActivity.samePairing("home+new","token","home+same","token"));
        assertFalse(MainActivity.samePairing("home+same","new-token","home+same","token"));
        assertFalse(MainActivity.samePairing(null,"token",null,"token"));
    }
    @Test public void reconnectsOnTransientNetworkFailuresWithoutRetryingEveryHttpError(){
        assertTrue(MainActivity.reconnectAfterPollFailure(-1,true));
        assertTrue(MainActivity.reconnectAfterPollFailure(503,true));
        assertTrue(MainActivity.reconnectAfterPollFailure(401,false));
        assertFalse(MainActivity.reconnectAfterPollFailure(400,true));
        assertFalse(MainActivity.reconnectAfterPollFailure(-1,false));
    }
}
