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
    private final java.util.concurrent.ThreadPoolExecutor network=new java.util.concurrent.ThreadPoolExecutor(1,1,0L,java.util.concurrent.TimeUnit.MILLISECONDS,new java.util.concurrent.LinkedBlockingQueue<>());
    private ApiClient api;
    private RemoteScreenView screen;
    private TextView status;
    private boolean resumed, destroyed, polling;
    private final Runnable poll=this::frame;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root=AppUi.root(this);
        AppUi.header(this,root,"سطح المكتب","تحكم مباشر • جلسة Windows المفتوحة",true);
        status=AppUi.label(this,"",12,true); status.setText("تكبير بإصبعين، نقرة للنقر، ضغط مطوّل للزر الأيمن. الشاشة الرئيسية فقط."); root.addView(status);
        screen=new RemoteScreenView(this,(action,x,y,endX,endY,id)->{
            try {
                JSONObject data=new JSONObject().put("action",action).put("x",x).put("y",y).put("frame_id",id);
                if("drag".equals(action)) data.put("end_x",endX).put("end_y",endY);
                input(data);
            } catch(Exception e){status.setText("تعذر تجهيز النقرة.");}
        });
        root.addView(screen,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout windows=new LinearLayout(this);
        add(windows,"اختيار نافذة",this::chooseWindow);
        add(windows,"تبويب جديد",()->keys("CTRL","T"));
        add(windows,"إغلاق تبويب",()->keys("CTRL","W"));
        add(windows,"إغلاق نافذة",()->new android.app.AlertDialog.Builder(this).setTitle("إغلاق النافذة الظاهرة؟")
            .setMessage("قد تظهر مطالبة بحفظ العمل. يمكنك التعامل معها من شاشة الهاتف.")
            .setPositiveButton("إغلاق",(d,w)->keys("ALT","F4")).setNegativeButton("إلغاء",null).show());root.addView(windows);
        LinearLayout keyboard=new LinearLayout(this);keyboard.setOrientation(LinearLayout.VERTICAL);keyboard.setVisibility(android.view.View.GONE);
        LinearLayout toolbar=new LinearLayout(this);
        add(toolbar,"لوحة المفاتيح",()->keyboard.setVisibility(keyboard.getVisibility()==android.view.View.VISIBLE?android.view.View.GONE:android.view.View.VISIBLE));
        add(toolbar,"ملاءمة",()->screen.reset());
        add(toolbar,"سحب / نقر",()->{screen.dragMode=!screen.dragMode;status.setText(screen.dragMode?"وضع سحب العناصر مفعّل":"وضع النقر مفعّل");});
        add(toolbar,"إيقاف المهمة",()->{network.getQueue().clear();polling=false;post("/v1/desktop/stop",new JSONObject());});
        root.addView(toolbar);root.addView(keyboard);
        LinearLayout modes=new LinearLayout(this);
        add(modes,"تحديث",()->frame()); add(modes,"مفاتيح",()->{
            String[] labels={"←","→","↑","↓","Delete","Home","End","Page Up","Page Down","F5","Ctrl+S","Ctrl+F","Start"};
            String[][] values={{"LEFT"},{"RIGHT"},{"UP"},{"DOWN"},{"DELETE"},{"HOME"},{"END"},{"PAGEUP"},{"PAGEDOWN"},{"F5"},{"CTRL","S"},{"CTRL","F"},{"WIN"}};
            new android.app.AlertDialog.Builder(this).setTitle("لوحة المفاتيح").setItems(labels,(dialog,index)->keys(values[index])).show();
        }); keyboard.addView(modes);
        EditText text=AppUi.field(this,"اكتب على الكمبيوتر…");text.setHint("اكتب النص الذي تريد إدخاله على الكمبيوتر");text.setMaxLines(2);keyboard.addView(text);
        LinearLayout keys=new LinearLayout(this);
        add(keys,"كتابة",()->{String value=text.getText().toString();if(value.isEmpty())return;try{input(new JSONObject().put("action","text").put("text",value));text.setText("");}catch(Exception ignored){}});
        add(keys,"Enter",()->keys("ENTER"));add(keys,"Tab",()->keys("TAB"));add(keys,"⌫",()->keys("BACKSPACE"));add(keys,"Esc",()->keys("ESC"));keyboard.addView(keys);
        LinearLayout shortcuts=new LinearLayout(this);
        add(shortcuts,"العنوان",()->keys("CTRL","L"));add(shortcuts,"تحديد",()->keys("CTRL","A"));add(shortcuts,"نسخ",()->keys("CTRL","C"));add(shortcuts,"لصق",()->keys("CTRL","V"));add(shortcuts,"النوافذ",()->keys("ALT","TAB"));keyboard.addView(shortcuts);
        LinearLayout scroll=new LinearLayout(this);add(scroll,"أعلى",()->wheel(3));add(scroll,"أسفل",()->wheel(-3));add(scroll,"سطح المكتب",()->keys("WIN","D"));keyboard.addView(scroll);
        try{SecureStore store=new SecureStore(this);api=new ApiClient(store.url(),store.token());}
        catch(Exception e){status.setText("ارجع للمحادثة واضبط الاتصال أولاً.");}
    }
    private void chooseWindow(){
        if(api==null||destroyed)return;
        network.execute(()->{try{
            JSONArray rows=api.windows().getJSONArray("windows");String[] titles=new String[rows.length()];
            for(int i=0;i<rows.length();i++)titles[i]=rows.getJSONObject(i).optString("title");
            main.post(()->{if(destroyed)return;if(titles.length==0){status.setText("لا توجد نوافذ ظاهرة قابلة للاختيار.");return;}
                new android.app.AlertDialog.Builder(this).setTitle("انتقل إلى نافذة الكمبيوتر").setItems(titles,(dialog,index)->{
                    try{post("/v1/windows/action",new JSONObject().put("id",rows.getJSONObject(index).getString("id")).put("action","focus"));}
                    catch(Exception e){status.setText("حدّث قائمة النوافذ ثم أعد الاختيار.");}
                }).setNegativeButton("إلغاء",null).show();
            });
        }catch(Exception e){showError(e);}});
    }

    private void add(LinearLayout row,String label,Runnable action){Button b=AppUi.button(this,label,action,false);b.setTextSize(12);b.setPadding(2,2,2,2);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-2,1);p.setMargins(2,3,2,3);row.addView(b,p);}
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
            main.post(()->{polling=false;if(destroyed){image.recycle();return;}screen.image(image,result.optString("frame_id"));status.setText("● مباشر • "+result.optInt("screen_width")+" × "+result.optInt("screen_height")+" • تكبير بإصبعين");schedule();});
        }catch(Exception e){main.post(()->{polling=false;schedule();});showError(e);}});
    }
    private void schedule(){main.removeCallbacks(poll);if(resumed&&!destroyed)main.postDelayed(poll,1000);}
    private void showError(Exception e){String message=e instanceof ApiClient.ApiException?e.getMessage():"تعذر تحديث الشاشة. افحص الكمبيوتر والاتصال.";main.post(()->{if(!destroyed)status.setText(message);});}
    @Override protected void onResume(){super.onResume();resumed=true;frame();}
    @Override protected void onPause(){resumed=false;main.removeCallbacks(poll);super.onPause();}
    @Override protected void onDestroy(){destroyed=true;main.removeCallbacksAndMessages(null);if(api!=null)api.close();network.shutdownNow();super.onDestroy();}
}
