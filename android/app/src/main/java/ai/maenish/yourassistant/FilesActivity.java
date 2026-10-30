package ai.maenish.yourassistant;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class FilesActivity extends Activity {
    private final Handler main=new Handler(Looper.getMainLooper());
    private final ExecutorService network=Executors.newSingleThreadExecutor();
    private ApiClient api;private TextView status;private LinearLayout entries;private String folder="",downloadPath="";
    private boolean destroyed,busy;
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        if(state!=null){folder=state.getString("folder","");downloadPath=state.getString("downloadPath","");}
        LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setPadding(12,12,12,12);root.setFitsSystemWindows(true);setContentView(root);
        status=new TextView(this);status.setText("ملفات المجلد الذي أتحته في إعدادات الكمبيوتر. اضغط الملف لتنزيله إلى الهاتف.");root.addView(status);
        LinearLayout bar=new LinearLayout(this);
        Button up=new Button(this);up.setText("المجلد الأعلى");up.setOnClickListener(v->{int index=folder.lastIndexOf('/');load(index<0?"":folder.substring(0,index));});bar.addView(up,new LinearLayout.LayoutParams(0,-2,1));
        Button upload=new Button(this);upload.setText("ارفع ملفاً للكمبيوتر");upload.setOnClickListener(v->{if(busy)return;Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE);startActivityForResult(intent,1);});bar.addView(upload,new LinearLayout.LayoutParams(0,-2,1));
        Button refresh=new Button(this);refresh.setText("تحديث");refresh.setOnClickListener(v->load(folder));bar.addView(refresh,new LinearLayout.LayoutParams(0,-2,1));root.addView(bar);
        ScrollView scroll=new ScrollView(this);entries=new LinearLayout(this);entries.setOrientation(LinearLayout.VERTICAL);scroll.addView(entries);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        try{SecureStore store=new SecureStore(this);api=new ApiClient(store.url(),store.token());
            if (state==null && getIntent().hasExtra("download_path")) {
                downloadPath=getIntent().getStringExtra("download_path");
                Intent save=new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/octet-stream").addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE,getIntent().getStringExtra("download_name"));
                startActivityForResult(save,2);
            } else load(folder);}catch(Exception e){status.setText("ارجع للمحادثة واضبط الاتصال أولاً.");}
    }
    private void load(String target){if(api==null||busy||destroyed)return;busy=true;status.setText("جاري قراءة المجلد…");network.execute(()->{
        try{JSONObject response=api.files(target);JSONArray items=response.getJSONArray("entries");main.post(()->{if(destroyed)return;busy=false;folder=response.optString("path");status.setText(response.optString("root_name")+"/"+folder);entries.removeAllViews();
            for(int i=0;i<items.length();i++){JSONObject item=items.optJSONObject(i);if(item==null)continue;Button button=new Button(this);button.setText((item.optBoolean("directory")?"📁 ":"↓ ")+item.optString("name")+(item.optBoolean("directory")?"":" ("+item.optLong("size")+" B)"));
                button.setOnClickListener(v->{if(busy)return;if(item.optBoolean("directory")){load(item.optString("path"));}else{downloadPath=item.optString("path");Intent save=new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/octet-stream").addCategory(Intent.CATEGORY_OPENABLE).putExtra(Intent.EXTRA_TITLE,item.optString("name"));startActivityForResult(save,2);}});entries.addView(button);}
        });}catch(Exception e){error(e);}
    });}
    @Override protected void onActivityResult(int code,int result,Intent data){super.onActivityResult(code,result,data);if(result!=RESULT_OK||data==null||data.getData()==null||api==null||busy)return;Uri uri=data.getData();
        if(code==2){String path=downloadPath;busy=true;status.setText("جاري تنزيل الملف للهاتف…");network.execute(()->{try(OutputStream output=getContentResolver().openOutputStream(uri,"w")){if(output==null)throw new IOException();api.downloadFile(path,output);done("تم تنزيل الملف إلى المكان الذي اخترته.");}catch(Exception e){error(e);}});}
        else if(code==1){String name="upload.bin";try(Cursor cursor=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null)){if(cursor!=null&&cursor.moveToFirst())name=cursor.getString(0);}catch(Exception e){status.setText("تعذر قراءة اسم الملف.");return;}
            String fileName=name,target=folder;busy=true;status.setText("جاري إرسال الملف للكمبيوتر…");network.execute(()->{File temporary=null;try{temporary=File.createTempFile("transfer-",".bin",getCacheDir());try(InputStream input=getContentResolver().openInputStream(uri);OutputStream output=new FileOutputStream(temporary)){if(input==null)throw new IOException();byte[] buffer=new byte[65536];int count;long total=0;while((count=input.read(buffer))!=-1){total+=count;if(total>256L*1024*1024||destroyed)throw new IOException();output.write(buffer,0,count);}}
                api.uploadFile(temporary,target,fileName);done("وصل الملف لقائمة النقل. النتيجة النهائية تظهر في المحادثة؛ حدّث المجلد بعد لحظات.");
            }catch(Exception e){error(e);}finally{if(temporary!=null)temporary.delete();}});
        }
    }
    private void done(String message){main.post(()->{if(!destroyed){busy=false;status.setText(message);}});}
    private void error(Exception e){done(e instanceof ApiClient.ApiException?e.getMessage():"تعذر نقل الملف. افحص الاتصال أو حجم الملف؛ قد يوجد تنزيل جزئي.");}
    @Override protected void onSaveInstanceState(Bundle state){state.putString("folder",folder);state.putString("downloadPath",downloadPath);super.onSaveInstanceState(state);}
    @Override protected void onDestroy(){destroyed=true;main.removeCallbacksAndMessages(null);if(api!=null)api.close();network.shutdownNow();super.onDestroy();}
}
