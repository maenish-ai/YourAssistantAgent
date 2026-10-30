package ai.maenish.yourassistant;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import com.journeyapps.barcodescanner.CaptureActivity;
import com.google.zxing.integration.android.IntentIntegrator;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.Shadows;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowActivity;
import org.robolectric.shadows.ShadowAlertDialog;
import static org.junit.Assert.*;

/** Exercise the camera activity lifecycle, not just QR image decoding. */
@RunWith(RobolectricTestRunner.class)
@Config(sdk={28,35})
public class QrScannerTest {
    private View text(View view,String label){
        if(view instanceof TextView && label.contentEquals(((TextView)view).getText()))return view;
        if(view instanceof ViewGroup){ViewGroup group=(ViewGroup)view;for(int i=0;i<group.getChildCount();i++){View found=text(group.getChildAt(i),label);if(found!=null)return found;}}
        return null;
    }

    @Test public void scanButtonLaunchesCameraAndRequestsPermissionWithoutCrashing(){
        try(ActivityController<MainActivity> main=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=main.get();
            Shadows.shadowOf(activity.getApplication()).denyPermissions(Manifest.permission.CAMERA);
            assertTrue(text(activity.findViewById(android.R.id.content),"مسح QR وإقران الكمبيوتر").performClick());
            ShadowActivity.IntentForResult launch=Shadows.shadowOf(activity).getNextStartedActivityForResult();
            assertNotNull(launch);
            assertEquals(CaptureActivity.class.getName(),launch.intent.getComponent().getClassName());
            try(ActivityController<CaptureActivity> camera=Robolectric.buildActivity(CaptureActivity.class,launch.intent)){
                camera.setup();
                assertFalse(camera.get().isFinishing());
                assertArrayEquals(new String[]{Manifest.permission.CAMERA},Shadows.shadowOf(camera.get()).getLastRequestedPermission().requestedPermissions);
            }
            assertFalse(activity.isFinishing());
        }
    }

    @Test public void cameraCanResumeWithPermissionAlreadyGranted(){
        try(ActivityController<MainActivity> main=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=main.get();
            Shadows.shadowOf(activity.getApplication()).grantPermissions(Manifest.permission.CAMERA);
            text(activity.findViewById(android.R.id.content),"مسح QR وإقران الكمبيوتر").performClick();
            Intent launch=Shadows.shadowOf(activity).getNextStartedActivityForResult().intent;
            try(ActivityController<CaptureActivity> camera=Robolectric.buildActivity(CaptureActivity.class,launch)){
                camera.setup();camera.pause().resume();
                assertFalse(camera.get().isFinishing());
                assertNull(Shadows.shadowOf(camera.get()).getLastRequestedPermission());
                assertNotNull(camera.get().findViewById(com.google.zxing.client.android.R.id.zxing_barcode_scanner));
            }
        }
    }

    @Test public void deniedPermissionReturnsAnExplanationToMainScreen(){
        try(ActivityController<MainActivity> main=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=main.get();
            Shadows.shadowOf(activity.getApplication()).denyPermissions(Manifest.permission.CAMERA);
            text(activity.findViewById(android.R.id.content),"مسح QR وإقران الكمبيوتر").performClick();
            ShadowActivity.IntentForResult launch=Shadows.shadowOf(activity).getNextStartedActivityForResult();
            try(ActivityController<CaptureActivity> camera=Robolectric.buildActivity(CaptureActivity.class,launch.intent)){
                camera.setup();
                int requestCode=Shadows.shadowOf(camera.get()).getLastRequestedPermission().requestCode;
                camera.get().onRequestPermissionsResult(requestCode,new String[]{Manifest.permission.CAMERA},new int[]{PackageManager.PERMISSION_DENIED});
                assertNotNull(ShadowAlertDialog.getLatestAlertDialog());
                Intent result=Shadows.shadowOf(camera.get()).getResultIntent();
                assertTrue(result.getBooleanExtra("MISSING_CAMERA_PERMISSION",false));
                activity.onActivityResult(launch.requestCode,Activity.RESULT_CANCELED,result);
                assertNotNull(text(activity.findViewById(android.R.id.content),"لم يُسمح بالكاميرا. فعّل إذن الكاميرا لهذا التطبيق ثم اضغط مسح QR مجدداً."));
                assertFalse(activity.isFinishing());
            }
        }
    }

    @Test public void cancellationAndUnrelatedQrKeepTheAppOpen(){
        try(ActivityController<MainActivity> main=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity activity=main.get();
            activity.onActivityResult(IntentIntegrator.REQUEST_CODE,Activity.RESULT_CANCELED,null);
            assertNotNull(text(activity.findViewById(android.R.id.content),"أُلغي مسح QR. يمكنك المحاولة مجدداً من زر المسح."));
            Intent unrelated=new Intent().putExtra("SCAN_RESULT","https://unrelated.example/qr").putExtra("SCAN_RESULT_FORMAT","QR_CODE");
            activity.onActivityResult(IntentIntegrator.REQUEST_CODE,Activity.RESULT_OK,unrelated);
            assertNotNull(text(activity.findViewById(android.R.id.content),"هذا ليس رمز إقران صالحاً. امسح الرمز من برنامج الكمبيوتر الجديد."));
            assertFalse(activity.isFinishing());
            assertFalse(text(activity.findViewById(android.R.id.content),"سطح المكتب").isEnabled());
        }
    }
}
