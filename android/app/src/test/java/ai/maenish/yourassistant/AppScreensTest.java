package ai.maenish.yourassistant;

import android.app.Activity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
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
            assertNotEquals(0,activity.getApplicationInfo().icon);
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
}
