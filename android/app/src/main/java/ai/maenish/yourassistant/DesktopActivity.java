package ai.maenish.yourassistant;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class DesktopActivity extends Activity {
    private final Handler main=new Handler(Looper.getMainLooper());
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    private ApiClient api;
    private RemoteScreenView screen;
    private TextView status;
    private boolean resumed, destroyed, polling;
    private final Runnable poll=this::frame;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(8,8,8,8); root.setFitsSystemWindows(true); setContentView(root);
        status=new TextView(this); status.setText("تكبير بإصبعين، نقرة للنقر، ضغط مطوّل للزر الأيمن. الشاشة الرئيسية فقط."); root.addView(status);
        screen=new RemoteScreenView(this,(action,x,y,endX,endY,id)->{
            try {
                JSONObject data=new JSONObject().put("action",action).put("x",x).put("y",y).put("frame_id",id);
                if("drag".equals(action)) data.put("end_x",endX).put("end_y",endY);
                input(data);
            } catch(Exception e){status.setText("تعذر تجهيز النقرة.");}
        });
        root.addView(screen,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout modes=new LinearLayout(this);
        add(modes,"تحديث",()->frame()); add(modes,"مفاتيح",()->{
            String[] labels={"←","→","↑","↓","Delete","Home","End","Page Up","Page Down","F5","Ctrl+S","Ctrl+F","Start"};
            String[][] values={{"LEFT"},{"RIGHT"},{"UP"},{"DOWN"},{"DELETE"},{"HOME"},{"END"},{"PAGEUP"},{"PAGEDOWN"},{"F5"},{"CTRL","S"},{"CTRL","F"},{"WIN"}};
            new android.app.AlertDialog.Builder(this).setTitle("لوحة المفاتيح").setItems(labels,(dialog,index)->keys(values[index])).show();
        }); add(modes,"ملاءمة",()->screen.reset());
        add(modes,"وضع السحب",()->{screen.dragMode=!screen.dragMode; status.setText(screen.dragMode?"وضع السحب: اسحب العنصر من مكانه للوجهة.":"وضع النقر؛ السحب عند التكبير يحرّك الصورة محلياً.");});
        add(modes,"إيقاف المهمة",()->post("/v1/desktop/stop",new JSONObject())); root.addView(modes);
        EditText text=new EditText(this);text.setHint("اكتب النص الذي تريد إدخاله على الكمبيوتر");text.setMaxLines(2);root.addView(text);
        LinearLayout keys=new LinearLayout(this);
        add(keys,"كتابة",()->{String value=text.getText().toString();if(value.isEmpty())return;try{input(new JSONObject().put("action","text").put("text",value));text.setText("");}catch(Exception ignored){}});
        add(keys,"Enter",()->keys("ENTER"));add(keys,"Tab",()->keys("TAB"));add(keys,"⌫",()->keys("BACKSPACE"));add(keys,"Esc",()->keys("ESC"));root.addView(keys);
        LinearLayout shortcuts=new LinearLayout(this);
        add(shortcuts,"العنوان",()->keys("CTRL","L"));add(shortcuts,"تحديد",()->keys("CTRL","A"));add(shortcuts,"نسخ",()->keys("CTRL","C"));add(shortcuts,"لصق",()->keys("CTRL","V"));add(shortcuts,"النوافذ",()->keys("ALT","TAB"));root.addView(shortcuts);
        LinearLayout scroll=new LinearLayout(this);add(scroll,"أعلى",()->wheel(3));add(scroll,"أسفل",()->wheel(-3));add(scroll,"سطح المكتب",()->keys("WIN","D"));root.addView(scroll);
        try{SecureStore store=new SecureStore(this);api=new ApiClient(store.url(),store.token());}
        catch(Exception e){status.setText("ارجع للمحادثة واضبط الاتصال أولاً.");}
    }
    private void add(LinearLayout row,String label,Runnable action){Button b=new Button(this);b.setText(label);b.setTextSize(11);b.setPadding(2,2,2,2);b.setOnClickListener(v->action.run());row.addView(b,new LinearLayout.LayoutParams(0,-2,1));}
    private void keys(String... values){try{input(new JSONObject().put("action","keys").put("keys",new JSONArray(values)));}catch(Exception ignored){}}
    private void wheel(int amount){try{input(new JSONObject().put("action","scroll").put("amount",amount));}catch(Exception ignored){}}
    private void input(JSONObject data){
        try{if(!data.has("frame_id"))data.put("frame_id",screen.frameId());post("/v1/desktop/input",data);}
        catch(Exception e){status.setText("تعذر تجهيز الإدخال. حدّث الشاشة.");}
    }
    private void post(String path,JSONObject data){
        if(api==null||destroyed)return;
        network.execute(()->{try{api.post(path,data);main.post(()->{if(!destroyed)status.setText("وصل الطلب؛ راقب الشاشة. رسائل فشل التنفيذ تظهر أيضاً في المحادثة.");});}catch(Exception e){showError(e);}});
    }
    private void frame(){
        if(api==null||destroyed||!resumed||polling)return;polling=true;
        network.execute(()->{try{
            JSONObject result=api.desktop();byte[] bytes=Base64.decode(result.getString("image_b64"),Base64.DEFAULT);
            Bitmap image=BitmapFactory.decodeByteArray(bytes,0,bytes.length);if(image==null)throw new Exception();
            main.post(()->{polling=false;if(destroyed){image.recycle();return;}screen.image(image,result.optString("frame_id"));schedule();});
        }catch(Exception e){main.post(()->{polling=false;schedule();});showError(e);}});
    }
    private void schedule(){main.removeCallbacks(poll);if(resumed&&!destroyed)main.postDelayed(poll,1000);}
    private void showError(Exception e){String message=e instanceof ApiClient.ApiException?e.getMessage():"تعذر تحديث الشاشة. افحص الكمبيوتر والاتصال.";main.post(()->{if(!destroyed)status.setText(message);});}
    @Override protected void onResume(){super.onResume();resumed=true;frame();}
    @Override protected void onPause(){resumed=false;main.removeCallbacks(poll);super.onPause();}
    @Override protected void onDestroy(){destroyed=true;main.removeCallbacksAndMessages(null);if(api!=null)api.close();network.shutdownNow();super.onDestroy();}
}
